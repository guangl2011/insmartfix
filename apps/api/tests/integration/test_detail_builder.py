"""build_detail (FR-3.5 schema split, FR-3.6) and the accept-time prediction snapshot (D10 L-4)."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.clock import wall_now
from app.contract.workorders import OwnerWorkOrderDetail, WorkOrderDetail
from app.dispatch.accept import refresh_prediction_snapshot
from app.workorders.detail import build_detail
from tests.integration.factories import add_event, make_offer, make_tenant

pytestmark = pytest.mark.integration


def test_contractor_and_owner_variants(app_engine: Engine) -> None:
    with app_engine.begin() as conn:
        t = make_tenant(conn, ["marco", "ana"])
        m, a = t.contractors["marco"], t.contractors["ana"]
        wo = make_offer(conn, t, [(m, "ACCEPTED"), (a, "EXPIRED")], state="IN_PROGRESS", current=m)
        add_event(conn, t, wo, m, type_="ADVANCE", stage="EN_ROUTE", at=wall_now())
    with Session(app_engine) as db:
        mine = build_detail(db, wo, contractor_id=m.cid, owner_view=False, now=wall_now())
        owner = build_detail(db, wo, contractor_id=None, owner_view=True, now=wall_now())
    assert type(mine) is WorkOrderDetail
    assert "ranked_candidates" not in mine.model_dump()
    assert [e.stage for e in mine.lifecycle_history] == ["EN_ROUTE"]
    assert mine.lifecycle_stage == "EN_ROUTE"
    assert isinstance(owner, OwnerWorkOrderDetail)
    assert [(c.contractor_id, c.rank, c.state) for c in owner.ranked_candidates] == [
        (m.cid, 1, "ACCEPTED"),
        (a.cid, 2, "EXPIRED"),
    ]


def test_owner_view_without_a_current_contractor_uses_the_top_rank(app_engine: Engine) -> None:
    with app_engine.begin() as conn:
        t = make_tenant(conn, ["marco"])
        wo = make_offer(conn, t, [(t.contractors["marco"], "DECLINED")], state="NO_CONTRACTORS")
    with Session(app_engine) as db:
        owner = build_detail(db, wo, contractor_id=None, owner_view=True, now=wall_now())
        with pytest.raises(LookupError):
            build_detail(db, uuid.uuid4(), contractor_id=None, owner_view=True, now=wall_now())
    assert owner.dispatch_state == "NO_CONTRACTORS"
    assert owner.match_reason == "Nearby"


def test_L_4_prediction_snapshot_only_overwritten_with_a_prediction(app_engine: Engine) -> None:
    with app_engine.begin() as conn:
        t = make_tenant(conn, ["marco"])
        wo = make_offer(
            conn, t, [(t.contractors["marco"], "OFFERED")], current=t.contractors["marco"]
        )
    for code, expected in (
        (None, None),
        ("COMP-CONTACTOR", "COMP-CONTACTOR"),
        (None, "COMP-CONTACTOR"),
    ):
        with Session(app_engine) as db, db.begin():
            refresh_prediction_snapshot(db, wo, code)
        with app_engine.connect() as conn:
            got = conn.execute(
                text("SELECT predicted_failure_code FROM workorders WHERE id = :w"), {"w": wo}
            ).scalar_one()
        assert got == expected

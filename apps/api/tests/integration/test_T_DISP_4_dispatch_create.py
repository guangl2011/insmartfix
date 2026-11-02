"""T-DISP-4 (service layer) and FR-10.1: dispatch create is tenant-bounded on every input (H-6)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import Asset, Dispatch, DispatchCandidate, WorkOrder
from app.dispatch.create import (
    AssetNotFoundError,
    CandidateSpec,
    DispatchSpec,
    InvalidCandidatesError,
    create_dispatch,
)
from tests.integration.conftest import World, make_world

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


@pytest.fixture
def session(app_engine: Engine) -> Iterator[Session]:
    with Session(app_engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def worlds(app_engine: Engine) -> tuple[World, World]:
    with app_engine.begin() as conn:
        return make_world(conn), make_world(conn)


def _second_contractor(session: Session, w: World) -> uuid.UUID:
    from app.db.models import Contractor

    c = Contractor(id=uuid.uuid4(), tenant_id=w.tenant_id, name="Ana")
    session.add(c)
    session.flush()
    return c.id


def _spec(asset_id: uuid.UUID, *contractors: uuid.UUID, sla: int = 30) -> DispatchSpec:
    return DispatchSpec(
        asset_id=asset_id,
        symptom="Not cooling",
        sla_minutes=sla,
        candidates=[
            CandidateSpec(contractor_id=c, match_score=0.9 - i / 10, reason=f"r{i}")
            for i, c in enumerate(contractors)
        ],
    )


def test_create_offers_rank_one_with_sla_deadline(
    session: Session, worlds: tuple[World, World]
) -> None:
    w, _ = worlds
    second = _second_contractor(session, w)
    seen: list[Asset] = []

    def predict(asset: Asset) -> str | None:
        seen.append(asset)
        return "COMP-CONTACTOR"

    wo_id = create_dispatch(
        session,
        tenant_id=w.tenant_id,
        created_by_user_id=w.owner_user_id,
        spec=_spec(w.asset_id, w.contractor_id, second, sla=15),
        now=NOW,
        predict=predict,
    )
    assert wo_id.version == 4
    wo = session.get_one(WorkOrder, wo_id)
    assert (wo.tenant_id, wo.asset_id, wo.status, wo.wo_source) == (
        w.tenant_id,
        w.asset_id,
        "OPEN",
        "dispatch",
    )
    assert wo.predicted_failure_code == "COMP-CONTACTOR"  # L-4 snapshot
    assert [a.id for a in seen] == [w.asset_id]

    deadline = NOW + timedelta(minutes=15)
    d = session.get_one(Dispatch, wo_id)
    assert (d.state, d.current_contractor_id, d.sla_deadline, d.version) == (
        "PENDING",
        w.contractor_id,
        deadline,
        0,
    )
    cands = session.scalars(
        select(DispatchCandidate)
        .where(DispatchCandidate.wo_id == wo_id)
        .order_by(DispatchCandidate.rank)
    ).all()
    assert [(c.contractor_id, c.rank, c.state) for c in cands] == [
        (w.contractor_id, 1, "OFFERED"),
        (second, 2, "QUEUED"),
    ]
    assert (cands[0].offered_at, cands[0].sla_deadline) == (NOW, deadline)
    assert (cands[1].offered_at, cands[1].sla_deadline) == (None, None)
    assert str(cands[0].match_score) == "0.900"


def test_T_DISP_4_asset_in_another_tenant_is_not_found(
    session: Session, worlds: tuple[World, World]
) -> None:
    mine, other = worlds
    with pytest.raises(AssetNotFoundError):
        create_dispatch(
            session,
            tenant_id=mine.tenant_id,
            created_by_user_id=mine.owner_user_id,
            spec=_spec(other.asset_id, mine.contractor_id),
            now=NOW,
        )
    with pytest.raises(AssetNotFoundError):
        create_dispatch(
            session,
            tenant_id=mine.tenant_id,
            created_by_user_id=mine.owner_user_id,
            spec=_spec(uuid.uuid4(), mine.contractor_id),
            now=NOW,
        )


@pytest.mark.parametrize("case", ["other_tenant", "unknown", "duplicate", "empty"])
def test_T_DISP_4_candidates_must_be_in_the_callers_tenant(
    session: Session, worlds: tuple[World, World], case: str
) -> None:
    mine, other = worlds
    contractors = {
        "other_tenant": (mine.contractor_id, other.contractor_id),
        "unknown": (mine.contractor_id, uuid.uuid4()),
        "duplicate": (mine.contractor_id, mine.contractor_id),
        "empty": (),
    }[case]
    with pytest.raises(InvalidCandidatesError):
        create_dispatch(
            session,
            tenant_id=mine.tenant_id,
            created_by_user_id=mine.owner_user_id,
            spec=_spec(mine.asset_id, *contractors),
            now=NOW,
        )
    # Nothing was written (the world's own WO is the only one), and the other tenant's
    # contractor has no candidacy.
    wos = session.scalars(select(WorkOrder.id).where(WorkOrder.tenant_id == mine.tenant_id)).all()
    assert list(wos) == [mine.wo_id]
    assert (
        session.scalars(
            select(DispatchCandidate).where(DispatchCandidate.contractor_id == other.contractor_id)
        ).all()
        == []
    )
    assert session.scalars(select(Dispatch).where(Dispatch.tenant_id == mine.tenant_id)).all() == []

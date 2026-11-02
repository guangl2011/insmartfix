"""FR-10.2: `make seed` loads the TEST_PLAN §5 fixtures, and running it twice is safe."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.db.models import Dispatch, DispatchCandidate, MemoryEvent, User, WorkOrder
from app.seed import fixtures as fx
from app.seed.load import load

pytestmark = pytest.mark.integration

T0 = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def fake_hash(password: str) -> str:
    return f"fake${password[::-1]}"


def _load(engine: Engine, now: datetime) -> None:
    with Session(engine) as s, s.begin():
        load(s, now=now, password="not-a-real-password", hash_password=fake_hash)


def _counts(engine: Engine) -> dict[str, int]:
    seed_wos = [o.wo_id for o in fx.OFFERS] + [fx.WO_ACCEPTED, fx.WO_ARRIVED]
    with Session(engine) as s:
        return {
            "users": s.scalar(
                select(func.count()).select_from(User).where(User.id.in_([u[0] for u in fx.USERS]))
            )
            or 0,
            "wos": s.scalar(
                select(func.count()).select_from(WorkOrder).where(WorkOrder.id.in_(seed_wos))
            )
            or 0,
            "candidates": s.scalar(
                select(func.count())
                .select_from(DispatchCandidate)
                .where(DispatchCandidate.wo_id.in_(seed_wos))
            )
            or 0,
            "events": s.scalar(
                select(func.count())
                .select_from(MemoryEvent)
                .where(MemoryEvent.wo_id == fx.WO_ARRIVED)
            )
            or 0,
        }


def test_seed_loads_fixtures_and_is_idempotent(app_engine: Engine) -> None:
    _load(app_engine, T0)
    first = _counts(app_engine)
    assert first == {"users": 4, "wos": 7, "candidates": 11, "events": 2}

    with Session(app_engine) as s:
        marco = s.get_one(User, fx.U_MARCO)
        assert (marco.role, marco.contractor_id, marco.tenant_id) == (
            "contractor",
            fx.C_MARCO,
            fx.TENANT_MIDTOWN,
        )
        assert marco.password_hash == fake_hash("not-a-real-password")
        owner = s.get_one(User, fx.U_OWNER)
        assert (owner.role, owner.contractor_id) == ("owner", None)
        zed = s.get_one(User, fx.U_ZED)
        assert zed.tenant_id == fx.TENANT_OTHER

        offers = s.scalars(
            select(Dispatch).where(
                Dispatch.state == "PENDING", Dispatch.current_contractor_id == fx.C_MARCO
            )
        ).all()
        remaining = sorted(
            (d.sla_deadline - T0)
            for d in offers
            if d.sla_deadline is not None and d.wo_id in {o.wo_id for o in fx.OFFERS}
        )
        assert remaining == [
            timedelta(minutes=-2),
            timedelta(seconds=45),
            timedelta(minutes=4),
            timedelta(minutes=12),
        ]
        assert s.get_one(Dispatch, fx.WO_ACCEPTED).state == "ACCEPTED"
        assert s.get_one(Dispatch, fx.WO_ARRIVED).state == "IN_PROGRESS"
        stages = s.scalars(
            select(MemoryEvent.stage)
            .where(MemoryEvent.wo_id == fx.WO_ARRIVED)
            .order_by(MemoryEvent.at)
        ).all()
        assert list(stages) == ["EN_ROUTE", "ARRIVED"]
        assert s.get_one(WorkOrder, fx.WO_OFFER_12M).predicted_failure_code == "COMP-CONTACTOR"
        assert s.get_one(WorkOrder, fx.WO_OFFER_4M).predicted_failure_code is None

    # Second run, later: no duplicates, untouched countdowns refreshed.
    t1 = T0 + timedelta(hours=1)
    _load(app_engine, t1)
    assert _counts(app_engine) == first
    with Session(app_engine) as s:
        d = s.get_one(Dispatch, fx.WO_OFFER_12M)
        assert d.sla_deadline == t1 + timedelta(minutes=12)
        c = s.get_one(DispatchCandidate, (fx.WO_OFFER_12M, fx.C_MARCO))
        assert c.sla_deadline == d.sla_deadline


def test_seed_leaves_touched_offers_alone(app_engine: Engine) -> None:
    _load(app_engine, T0)
    with Session(app_engine) as s, s.begin():
        s.get_one(DispatchCandidate, (fx.WO_OFFER_4M, fx.C_MARCO)).state = "DECLINED"
    try:
        _load(app_engine, T0 + timedelta(hours=2))
        with Session(app_engine) as s:
            assert s.get_one(Dispatch, fx.WO_OFFER_4M).sla_deadline == T0 + timedelta(minutes=4)
    finally:
        with Session(app_engine) as s, s.begin():
            s.get_one(DispatchCandidate, (fx.WO_OFFER_4M, fx.C_MARCO)).state = "OFFERED"


def test_seed_ids_are_uuid_v4() -> None:
    ids = [v for k, v in vars(fx).items() if k.isupper() and hasattr(v, "version")]
    assert len(ids) >= 20
    assert all(i.version == 4 for i in ids)

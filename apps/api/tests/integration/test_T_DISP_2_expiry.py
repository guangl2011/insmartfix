"""SLA expiry: T-DISP-2 (A, sweeper with no traffic and lazily on read), T-DISP-3 (A, expiry
half). FR-5.1, FR-5.2."""

import os
import threading
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.clock import clock, wall_now
from app.db.session import get_engine
from app.dispatch.sweeper import SWEEPER_LOCK_KEY, Sweeper, sweep_once
from app.main import create_app
from app.settings import normalize_database_url
from tests.conftest import make_settings
from tests.integration.factories import Tenant, make_offer, make_tenant

pytestmark = pytest.mark.integration


@pytest.fixture
def fake_clock() -> Iterator[None]:
    clock.enable_fake(True)
    yield
    clock.enable_fake(False)


@pytest.fixture
def t(app_engine: Engine) -> Tenant:
    with app_engine.begin() as conn:
        return make_tenant(conn, ["marco", "ana"])


def _offer(engine: Engine, t: Tenant, minutes: float, *, with_next: bool = True) -> uuid.UUID:
    m, a = t.contractors["marco"], t.contractors["ana"]
    cands = [(m, "OFFERED"), (a, "QUEUED")] if with_next else [(m, "OFFERED")]
    with engine.begin() as conn:
        return make_offer(
            conn,
            t,
            cands,
            current=m,
            deadline=wall_now() + timedelta(minutes=minutes),
            sla_minutes=10,
        )


def _state(engine: Engine, wo: uuid.UUID) -> dict[str, Any]:
    with engine.connect() as conn:
        d = (
            conn.execute(
                text(
                    "SELECT state, current_contractor_id, sla_deadline "
                    "FROM dispatch WHERE wo_id = :w"
                ),
                {"w": wo},
            )
            .mappings()
            .one()
        )
        cands: dict[uuid.UUID, str] = dict(
            conn.execute(
                text("SELECT contractor_id, state FROM dispatch_candidates WHERE wo_id = :w"),
                {"w": wo},
            ).all()
        )
    return {**d, "cands": cands}


@pytest.mark.usefixtures("fake_clock")
def test_T_DISP_2_sweeper_expires_with_no_traffic(app_engine: Engine, t: Tenant) -> None:
    m, a = t.contractors["marco"], t.contractors["ana"]
    wo = _offer(app_engine, t, 2)
    clock.set(wall_now() + timedelta(minutes=1))
    sweep_once(app_engine)
    assert _state(app_engine, wo)["current_contractor_id"] == m.cid  # not due yet
    later = wall_now() + timedelta(minutes=3)
    clock.set(later)
    assert (sweep_once(app_engine) or 0) >= 1
    s = _state(app_engine, wo)
    assert (s["state"], s["current_contractor_id"]) == ("PENDING", a.cid)  # T-DISP-3 re-offer
    assert s["cands"] == {m.cid: "EXPIRED", a.cid: "OFFERED"}
    assert s["sla_deadline"] == later + timedelta(minutes=10)  # new deadline


@pytest.mark.usefixtures("fake_clock")
def test_T_DISP_3_expiry_of_the_last_candidate_is_no_contractors(
    app_engine: Engine, t: Tenant
) -> None:
    wo = _offer(app_engine, t, 1, with_next=False)
    clock.set(wall_now() + timedelta(minutes=2))
    sweep_once(app_engine)
    s = _state(app_engine, wo)
    assert (s["state"], s["current_contractor_id"], s["sla_deadline"]) == (
        "NO_CONTRACTORS",
        None,
        None,
    )


@pytest.mark.usefixtures("fake_clock")
def test_T_DISP_2_lazily_on_read(app_engine: Engine, t: Tenant) -> None:
    """No sweeper: Ana's own schedule read expires Marco's due offer and shows it re-offered."""
    a = t.contractors["ana"]
    wo = _offer(app_engine, t, 1)
    clock.set(wall_now() + timedelta(minutes=2))
    url = normalize_database_url(os.environ["DATABASE_URL"])
    with TestClient(create_app(make_settings(url, env="test", fake_clock=True))) as api:
        clock.set(wall_now() + timedelta(minutes=2))  # create_app resets the fake clock
        body = api.get("/v1/me/schedule", headers=a.auth).json()
    get_engine.cache_clear()
    assert [o["wo_id"] for o in body["offers"]] == [str(wo)]
    assert _state(app_engine, wo)["current_contractor_id"] == a.cid


def test_T_DISP_2_sweeper_is_single_flight(app_engine: Engine, t: Tenant) -> None:
    with app_engine.connect() as holder, holder.begin():
        holder.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": SWEEPER_LOCK_KEY})
        assert sweep_once(app_engine) is None
    assert sweep_once(app_engine) is not None


def test_T_DISP_2_background_sweeper_runs_on_its_own(app_engine: Engine, t: Tenant) -> None:
    m, a = t.contractors["marco"], t.contractors["ana"]
    with app_engine.begin() as conn:
        wo = make_offer(
            conn,
            t,
            [(m, "OFFERED"), (a, "QUEUED")],
            current=m,
            deadline=wall_now() + timedelta(milliseconds=300),
        )
    sweeper = Sweeper(app_engine, interval_seconds=0.1)
    done = threading.Event()
    sweeper.start()
    try:
        for _ in range(60):
            if _state(app_engine, wo)["current_contractor_id"] == a.cid:
                done.set()
                break
            threading.Event().wait(0.1)
    finally:
        sweeper.stop()
    assert done.is_set()


def test_app_lifespan_starts_and_stops_the_sweeper(migrated_db: None) -> None:
    url = normalize_database_url(os.environ["DATABASE_URL"])
    settings = make_settings(url, env="ci", sweeper_enabled=True, sweeper_interval_seconds=0.05)
    with TestClient(create_app(settings)) as api:
        assert api.get("/v1/healthz").status_code == 200
        names = [th.name for th in threading.enumerate()]
        assert "sla-sweeper" in names
    get_engine.cache_clear()
    assert "sla-sweeper" not in [th.name for th in threading.enumerate()]

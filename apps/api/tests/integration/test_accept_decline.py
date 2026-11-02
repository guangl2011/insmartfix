"""Accept / decline / re-offer against Postgres.

T-DISP-1 (A, 100-iteration concurrent property test), T-DISP-3 (A, decline half), T-DEC-1 (A),
T-INBOX-5 (A), T-AUTH-9 (A). FR-4.1-4.3, FR-5.3, FR-2.6, FR-3.6; D10 H-2, L-5.
"""

import os
import threading
import time
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.clock import wall_now
from app.contract.schedule import DeclineRequest
from app.contract.workorders import WorkOrderDetail
from app.core.errors import ApiError
from app.db.models import Dispatch, DispatchCandidate
from app.db.session import get_engine
from app.dispatch.accept import accept, lock
from app.dispatch.decline import decline
from app.dispatch.reoffer import reoffer_next
from app.main import create_app
from app.settings import normalize_database_url
from tests.conftest import make_settings
from tests.integration.factories import Person, Tenant, make_offer, make_tenant

pytestmark = pytest.mark.integration


@pytest.fixture
def api(migrated_db: None) -> Iterator[TestClient]:
    url = normalize_database_url(os.environ["DATABASE_URL"])
    with TestClient(create_app(make_settings(url, env="ci"))) as c:
        yield c
    get_engine.cache_clear()


@pytest.fixture
def t(app_engine: Engine) -> Tenant:
    with app_engine.begin() as conn:
        return make_tenant(conn, ["marco", "ana", "lee"])


def _offer(engine: Engine, t: Tenant, cands: list[tuple[str, str]], current: str, **kw: Any) -> Any:
    with engine.begin() as conn:
        return make_offer(
            conn, t, [(t.contractors[n], s) for n, s in cands], current=t.contractors[current], **kw
        )


def _dispatch(engine: Engine, wo: uuid.UUID) -> dict[str, Any]:
    with engine.connect() as conn:
        return dict(
            conn.execute(
                text(
                    "SELECT state, current_contractor_id, version, sla_deadline, decline_reason, "
                    "decline_note FROM dispatch WHERE wo_id = :w"
                ),
                {"w": wo},
            )
            .mappings()
            .one()
        )


def _cands(engine: Engine, wo: uuid.UUID) -> dict[uuid.UUID, dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM dispatch_candidates WHERE wo_id = :w ORDER BY rank"), {"w": wo}
        ).mappings()
        return {r["contractor_id"]: dict(r) for r in rows}


# --- accept -------------------------------------------------------------------------------


def test_accept_binds_and_returns_the_detail_synchronously(
    api: TestClient, t: Tenant, app_engine: Engine
) -> None:
    m = t.contractors["marco"]
    wo = _offer(app_engine, t, [("marco", "OFFERED"), ("ana", "QUEUED")], "marco")
    res = api.post(f"/v1/me/accept/{wo}", headers=m.auth)
    assert res.status_code == 200, res.text
    assert "ranked_candidates" not in res.json()  # FR-3.5
    detail = WorkOrderDetail.model_validate(res.json())
    assert detail.dispatch_state == "ACCEPTED"
    assert detail.wo_id == wo
    assert detail.pre_diagnostic_available is False  # null engine until M2-T1 (FR-3.4)
    assert detail.decision is not None
    assert detail.decision.root_cause is None
    d = _dispatch(app_engine, wo)
    assert (d["state"], d["current_contractor_id"], d["version"]) == (
        "ACCEPTED",
        m.cid,
        1,
    )
    assert _cands(app_engine, wo)[m.cid]["state"] == "ACCEPTED"
    # Retry by the bound contractor: same result, never re-binds (§2.1 row 15).
    again = api.post(f"/v1/contractor/{m.cid}/accept/{wo}", headers=m.auth)
    assert again.status_code == 200
    assert _dispatch(app_engine, wo)["version"] == 1
    sched = api.get("/v1/me/schedule", headers=m.auth).json()
    assert [o["wo_id"] for o in sched["active"]] == [str(wo)]
    assert sched["offers"] == []


def test_accept_after_deadline_is_409_expired_and_changes_nothing(
    api: TestClient, t: Tenant, app_engine: Engine
) -> None:
    m = t.contractors["marco"]
    wo = _offer(
        app_engine,
        t,
        [("marco", "OFFERED"), ("ana", "QUEUED")],
        "marco",
        deadline=wall_now() - timedelta(seconds=1),
    )
    before = _dispatch(app_engine, wo)
    res = api.post(f"/v1/me/accept/{wo}", headers=m.auth)
    assert res.status_code == 409
    assert res.json()["error"]["reason"] == "expired"
    assert _dispatch(app_engine, wo) == before


def test_T_INBOX_5_stale_offer_race_marco_taps_accept_after_reassignment(
    api: TestClient, t: Tenant, app_engine: Engine
) -> None:
    """Marco's offer expired and was re-offered to Ana while his countdown still showed time."""
    m = t.contractors["marco"]
    wo = _offer(app_engine, t, [("marco", "EXPIRED"), ("ana", "OFFERED")], "ana")
    res = api.post(f"/v1/me/accept/{wo}", headers=m.auth)
    assert res.status_code == 409
    err = res.json()["error"]
    assert (err["code"], err["reason"]) == ("OFFER_UNAVAILABLE", "reassigned")
    assert str(t.contractors["ana"].cid) not in res.text
    assert str(wo) not in str(api.get("/v1/me/schedule", headers=m.auth).json()["offers"])
    assert _dispatch(app_engine, wo)["current_contractor_id"] == t.contractors["ana"].cid


# --- decline ------------------------------------------------------------------------------


def test_T_DEC_1_decline_with_reason_is_persisted(
    api: TestClient, t: Tenant, app_engine: Engine
) -> None:
    m = t.contractors["marco"]
    wo = _offer(app_engine, t, [("marco", "OFFERED"), ("ana", "QUEUED")], "marco")
    res = api.post(
        f"/v1/me/decline/{wo}", json={"reason": "too_far", "note": "Across town"}, headers=m.auth
    )
    assert res.status_code == 204
    assert res.content == b""
    c = _cands(app_engine, wo)[m.cid]
    assert (c["state"], c["decline_reason"], c["decline_note"]) == (
        "DECLINED",
        "too_far",
        "Across town",
    )
    d = _dispatch(app_engine, wo)
    assert (d["decline_reason"], d["decline_note"]) == ("too_far", "Across town")


def test_T_DEC_1_skip_declines_in_one_tap_with_no_reason(
    api: TestClient, t: Tenant, app_engine: Engine
) -> None:
    m = t.contractors["marco"]
    wo = _offer(app_engine, t, [("marco", "OFFERED"), ("ana", "QUEUED")], "marco")
    assert api.post(f"/v1/me/decline/{wo}", json={}, headers=m.auth).status_code == 204
    c = _cands(app_engine, wo)[m.cid]
    assert (c["state"], c["decline_reason"], c["decline_note"]) == ("DECLINED", None, None)


@pytest.mark.parametrize(
    "body",
    [{"note": "x" * 501}, {"reason": "bored"}, {"reason": "other", "extra": 1}],
)
def test_T_DEC_1_invalid_decline_bodies_are_422_and_change_nothing(
    api: TestClient, t: Tenant, app_engine: Engine, body: dict[str, Any]
) -> None:
    m = t.contractors["marco"]
    wo = _offer(app_engine, t, [("marco", "OFFERED"), ("ana", "QUEUED")], "marco")
    before = _dispatch(app_engine, wo)
    assert api.post(f"/v1/me/decline/{wo}", json=body, headers=m.auth).status_code == 422
    assert _dispatch(app_engine, wo) == before


def test_T_DISP_3_decline_reoffers_to_next_rank_then_no_contractors(
    api: TestClient, t: Tenant, app_engine: Engine
) -> None:
    m, a = t.contractors["marco"], t.contractors["ana"]
    wo = _offer(app_engine, t, [("marco", "OFFERED"), ("ana", "QUEUED")], "marco", sla_minutes=10)
    before = wall_now()
    assert api.post(f"/v1/me/decline/{wo}", json={}, headers=m.auth).status_code == 204
    d = _dispatch(app_engine, wo)
    assert (d["state"], d["current_contractor_id"]) == ("PENDING", a.cid)
    assert before + timedelta(minutes=9) < d["sla_deadline"] <= wall_now() + timedelta(minutes=10)
    ana = _cands(app_engine, wo)[a.cid]
    assert ana["state"] == "OFFERED"
    assert ana["sla_deadline"] == d["sla_deadline"]
    assert [o["wo_id"] for o in api.get("/v1/me/schedule", headers=a.auth).json()["offers"]] == [
        str(wo)
    ]
    # Ana declines too: nobody left.
    assert api.post(f"/v1/me/decline/{wo}", json={}, headers=a.auth).status_code == 204
    d = _dispatch(app_engine, wo)
    assert (d["state"], d["current_contractor_id"], d["sla_deadline"]) == (
        "NO_CONTRACTORS",
        None,
        None,
    )
    owner = api.get(f"/v1/contractor/{a.cid}/schedule", headers=t.owner.auth)
    assert owner.status_code == 200


def test_decline_of_a_bound_job_is_refused(api: TestClient, t: Tenant, app_engine: Engine) -> None:
    m = t.contractors["marco"]
    wo = _offer(app_engine, t, [("marco", "ACCEPTED")], "marco", state="ACCEPTED")
    before = _dispatch(app_engine, wo)
    res = api.post(f"/v1/me/decline/{wo}", json={}, headers=m.auth)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "INVALID_TRANSITION"
    assert _dispatch(app_engine, wo) == before


# --- T-AUTH-9: a past candidate can't take or disturb a live offer --------------------------


def test_T_AUTH_9_past_candidate_gets_409_and_disturbs_nothing(
    api: TestClient, t: Tenant, app_engine: Engine
) -> None:
    """Ana's offer expired → re-offered to Marco. Ana accept/decline → 409, Marco keeps it,
    `version` unchanged, rank 3 still queued (no re-offer)."""
    a, m, lee = (t.contractors[n] for n in ("ana", "marco", "lee"))
    wo = _offer(
        app_engine, t, [("ana", "EXPIRED"), ("marco", "OFFERED"), ("lee", "QUEUED")], "marco"
    )
    before, cands = _dispatch(app_engine, wo), _cands(app_engine, wo)
    for path in (f"/v1/me/accept/{wo}", f"/v1/contractor/{a.cid}/decline/{wo}"):
        res = api.post(path, json={"reason": "no_capacity"}, headers=a.auth)
        assert res.status_code == 409, path
        assert res.json()["error"]["code"] == "OFFER_UNAVAILABLE"
    assert _dispatch(app_engine, wo) == before
    assert _cands(app_engine, wo) == cands
    assert cands[lee.cid]["state"] == "QUEUED"
    assert api.post(f"/v1/me/accept/{wo}", headers=m.auth).status_code == 200


def _expire_and_reoffer(engine: Engine, wo: uuid.UUID, at: datetime) -> bool:
    """What the sweeper does (M1-T9): under the lock, expire the current offer if it is still
    pending and due, then re-offer. Returns True if it moved the offer."""
    with Session(engine) as db, db.begin():
        d = db.execute(
            text("SELECT 1 FROM dispatch WHERE wo_id = :w FOR UPDATE"), {"w": wo}
        ).scalar_one()
        assert d == 1
        dispatch = db.get(Dispatch, wo)
        assert dispatch is not None
        if (
            dispatch.state != "PENDING"
            or dispatch.sla_deadline is None
            or dispatch.sla_deadline > at
        ):
            return False
        cand = db.get(DispatchCandidate, (wo, dispatch.current_contractor_id))
        assert cand is not None
        cand.state = "EXPIRED"
        reoffer_next(db, dispatch, at)
        return True


@settings(max_examples=25, deadline=None, suppress_health_check=list(HealthCheck))
@given(st.sampled_from(["accept", "decline"]))
def test_T_AUTH_9_offeree_turns_past_between_gate_and_lock(
    app_engine: Engine, t: Tenant, op: str
) -> None:
    """The gate allowed Marco as offeree; before his request takes the lock the offer expires
    and moves to Ana. Inside the lock → 409, no bind, no second re-offer."""
    m, a = t.contractors["marco"], t.contractors["ana"]
    deadline = wall_now() + timedelta(seconds=30)
    wo = _offer(
        app_engine,
        t,
        [("marco", "OFFERED"), ("ana", "QUEUED"), ("lee", "QUEUED")],
        "marco",
        deadline=deadline,
    )
    assert _expire_and_reoffer(app_engine, wo, deadline + timedelta(milliseconds=1))
    moved = _dispatch(app_engine, wo)
    late = deadline - timedelta(seconds=1)  # Marco's clock: still before his deadline

    def call(db: Session) -> None:
        if op == "accept":
            accept(db, wo, m.cid, late)
        else:
            decline(db, wo, m.cid, DeclineRequest(), late)

    with Session(app_engine) as db, pytest.raises(ApiError) as exc:
        call(db)
    assert (exc.value.status_code, exc.value.reason) == (409, "reassigned")
    assert _dispatch(app_engine, wo) == moved
    assert moved["current_contractor_id"] == a.cid
    assert _cands(app_engine, wo)[t.contractors["lee"].cid]["state"] == "QUEUED"


# --- T-DISP-1: exactly one winner -----------------------------------------------------------


def _try(fn: Any) -> str:
    try:
        fn()
        return "ok"
    except ApiError as e:
        return f"{e.status_code}"


@settings(max_examples=100, deadline=None, suppress_health_check=list(HealthCheck))
@given(jitter=st.floats(min_value=0, max_value=0.004))
def test_T_DISP_1_concurrent_accept_single_winner(
    app_engine: Engine, t: Tenant, jitter: float
) -> None:
    """Marco accepts at the last moment while the sweeper expires his offer and Ana, its next
    offeree, accepts. Exactly one accept wins; the WO is bound to exactly one contractor."""
    m, a = t.contractors["marco"], t.contractors["ana"]
    deadline = wall_now() + timedelta(seconds=30)
    wo = _offer(
        app_engine, t, [("marco", "OFFERED"), ("ana", "QUEUED")], "marco", deadline=deadline
    )
    results: dict[str, str] = {}
    start = threading.Barrier(2)

    def run_marco() -> None:
        start.wait()

        def go() -> None:
            with Session(app_engine) as db, db.begin():
                accept(db, wo, m.cid, deadline - timedelta(milliseconds=1))

        results["marco"] = _try(go)

    def run_sweep_then_ana() -> None:
        start.wait()
        time.sleep(jitter)
        _expire_and_reoffer(app_engine, wo, deadline + timedelta(milliseconds=1))

        def go() -> None:
            with Session(app_engine) as db, db.begin():
                accept(db, wo, a.cid, deadline)

        results["ana"] = _try(go)

    threads = [threading.Thread(target=run_marco), threading.Thread(target=run_sweep_then_ana)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert sorted(results.values()) == ["409", "ok"], results
    winner = m if results["marco"] == "ok" else a
    d = _dispatch(app_engine, wo)
    assert (d["state"], d["current_contractor_id"]) == ("ACCEPTED", winner.cid)
    accepted = [c for c in _cands(app_engine, wo).values() if c["state"] == "ACCEPTED"]
    assert [c["contractor_id"] for c in accepted] == [winner.cid]


def test_T_DISP_1_same_contractor_two_devices_bind_once(app_engine: Engine, t: Tenant) -> None:
    m = t.contractors["marco"]
    wo = _offer(app_engine, t, [("marco", "OFFERED")], "marco")
    start = threading.Barrier(4)
    out: list[str] = []

    def go() -> None:
        start.wait()
        with Session(app_engine) as db, db.begin():
            out.append(_try(lambda: accept(db, wo, m.cid, wall_now())))

    threads = [threading.Thread(target=go) for _ in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert out == ["ok"] * 4
    assert _dispatch(app_engine, wo)["version"] == 1


def test_lock_requires_an_existing_dispatch(app_engine: Engine, t: Tenant) -> None:
    from sqlalchemy.exc import NoResultFound

    with Session(app_engine) as db, pytest.raises(NoResultFound):
        lock(db, uuid.uuid4(), t.contractors["marco"].cid)
    _ = Person

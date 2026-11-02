"""Lifecycle transitions against Postgres: T-LIFE-1, T-LIFE-2, T-LIFE-3, T-LIFE-5 (A) and
T-IDEM-1 (A, transition). FR-6.1, FR-6.3, FR-6.4; D10 H-3, H-4."""

import os
import threading
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.contract.workorders import TransitionResponse
from app.db.session import get_engine
from app.main import create_app
from app.settings import normalize_database_url
from tests.conftest import make_settings
from tests.integration.factories import Person, Tenant, make_offer, make_tenant

pytestmark = pytest.mark.integration

EN_ROUTE = {"action": "advance", "stage": "EN_ROUTE"}
ARRIVED = {"action": "advance", "stage": "ARRIVED"}
UNDO = {"action": "undo"}


@pytest.fixture
def api(migrated_db: None) -> Iterator[TestClient]:
    url = normalize_database_url(os.environ["DATABASE_URL"])
    with TestClient(create_app(make_settings(url, env="ci"))) as c:
        yield c
    get_engine.cache_clear()


@pytest.fixture
def t(app_engine: Engine) -> Tenant:
    with app_engine.begin() as conn:
        return make_tenant(conn, ["marco", "ana"])


def _job(engine: Engine, t: Tenant, who: str = "marco", state: str = "ACCEPTED") -> uuid.UUID:
    p = t.contractors[who]
    with engine.begin() as conn:
        return make_offer(conn, t, [(p, "ACCEPTED")], state=state, current=p)


def _post(
    api: TestClient, wo: uuid.UUID, body: dict[str, Any], who: Person, key: str | None = None
) -> Any:
    headers = dict(who.auth)
    if key:
        headers["Idempotency-Key"] = key
    return api.post(f"/v1/workorders/{wo}/transition", json=body, headers=headers)


def _ok(res: Any) -> TransitionResponse:
    assert res.status_code == 200, res.text
    return TransitionResponse.model_validate(res.json())


def _events(engine: Engine, wo: uuid.UUID) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                text("SELECT * FROM memory_events WHERE wo_id = :w ORDER BY at, id"), {"w": wo}
            ).mappings()
        ]


def _dispatch_state(engine: Engine, wo: uuid.UUID) -> str:
    with engine.connect() as conn:
        state = conn.execute(
            text("SELECT state FROM dispatch WHERE wo_id = :w"), {"w": wo}
        ).scalar_one()
    assert isinstance(state, str)
    return state


def _409(res: Any) -> None:
    assert res.status_code == 409, res.text
    assert res.json()["error"]["code"] == "INVALID_TRANSITION"


def test_T_LIFE_1_en_route_then_arrived_appends_events(
    api: TestClient, t: Tenant, app_engine: Engine
) -> None:
    m = t.contractors["marco"]
    wo = _job(app_engine, t)
    first = _ok(_post(api, wo, EN_ROUTE, m))
    assert first.lifecycle_stage == "EN_ROUTE"
    assert _dispatch_state(app_engine, wo) == "IN_PROGRESS"  # ACCEPTED → IN_PROGRESS
    second = _ok(_post(api, wo, ARRIVED, m))
    assert second.lifecycle_stage == "ARRIVED"
    assert [(h.type, h.stage) for h in second.history] == [
        ("ADVANCE", "EN_ROUTE"),
        ("ADVANCE", "ARRIVED"),
    ]
    rows = _events(app_engine, wo)
    assert [r["actor_user_id"] for r in rows] == [m.user_id, m.user_id]
    assert {r["asset_id"] for r in rows} == {t.asset_id}
    # Visible on the schedule (another device after refresh, FR-6.4).
    active = api.get("/v1/me/schedule", headers=m.auth).json()["active"]
    assert [(a["wo_id"], a["lifecycle_stage"]) for a in active] == [(str(wo), "ARRIVED")]


def test_T_LIFE_2_undo_appends_correction_and_reverts_stage(
    api: TestClient, t: Tenant, app_engine: Engine
) -> None:
    m = t.contractors["marco"]
    wo = _job(app_engine, t)
    _ok(_post(api, wo, EN_ROUTE, m))
    arrived = _ok(_post(api, wo, ARRIVED, m))
    undo = _ok(_post(api, wo, {"action": "undo", "corrects_event_id": str(arrived.event_id)}, m))
    assert undo.lifecycle_stage == "EN_ROUTE"
    assert [(h.type, h.corrects_event_id) for h in undo.history][-1] == (
        "CORRECTION",
        arrived.event_id,
    )
    assert len(_events(app_engine, wo)) == 3  # history intact, nothing deleted
    # Server-picked target when omitted, then the WO can advance again.
    back = _ok(_post(api, wo, UNDO, m))
    assert back.lifecycle_stage is None
    assert _ok(_post(api, wo, EN_ROUTE, m)).lifecycle_stage == "EN_ROUTE"


def test_T_LIFE_3_out_of_order_and_duplicate_key(
    api: TestClient, t: Tenant, app_engine: Engine
) -> None:
    m = t.contractors["marco"]
    wo = _job(app_engine, t)
    _409(_post(api, wo, ARRIVED, m))  # no ARRIVED before EN_ROUTE
    _409(_post(api, wo, {"action": "advance"}, m))  # advance needs a stage
    first = _ok(_post(api, wo, EN_ROUTE, m, key="key-life-0001"))
    again = _ok(_post(api, wo, EN_ROUTE, m, key="key-life-0001"))
    assert again.event_id == first.event_id
    assert again.history == first.history
    assert len(_events(app_engine, wo)) == 1
    _409(_post(api, wo, EN_ROUTE, m))  # a repeat without the key is out of order


def test_T_LIFE_5_undo_rules(api: TestClient, t: Tenant, app_engine: Engine) -> None:
    m = t.contractors["marco"]
    wo, other = _job(app_engine, t), _job(app_engine, t)
    a1 = _ok(_post(api, wo, EN_ROUTE, m))
    a2 = _ok(_post(api, wo, ARRIVED, m))
    o1 = _ok(_post(api, other, EN_ROUTE, m))
    _409(_post(api, wo, {"action": "undo", "corrects_event_id": str(o1.event_id)}, m))  # other WO
    _409(_post(api, wo, {"action": "undo", "corrects_event_id": str(a1.event_id)}, m))  # not latest
    c = _ok(_post(api, wo, {"action": "undo", "corrects_event_id": str(a2.event_id)}, m))
    _409(_post(api, wo, {"action": "undo", "corrects_event_id": str(a2.event_id)}, m))  # twice
    _409(
        _post(api, wo, {"action": "undo", "corrects_event_id": str(c.event_id)}, m)
    )  # a correction
    _409(_post(api, wo, {"action": "undo", "corrects_event_id": str(uuid.uuid4())}, m))
    # The other WO's stage is unaffected by anything above.
    other_stage = _ok(_post(api, other, ARRIVED, m)).lifecycle_stage
    assert other_stage == "ARRIVED"


def test_T_LIFE_5_actor_and_at_in_the_body_are_rejected(
    api: TestClient, t: Tenant, app_engine: Engine
) -> None:
    m = t.contractors["marco"]
    wo = _job(app_engine, t)
    for extra in ({"actor": str(uuid.uuid4())}, {"at": "2020-01-01T00:00:00Z"}):
        assert _post(api, wo, {**EN_ROUTE, **extra}, m).status_code == 422
    assert _events(app_engine, wo) == []


def test_T_LIFE_5_no_undo_after_completion(api: TestClient, t: Tenant, app_engine: Engine) -> None:
    m = t.contractors["marco"]
    wo = _job(app_engine, t)
    _ok(_post(api, wo, EN_ROUTE, m))
    with app_engine.begin() as conn:
        conn.execute(text("UPDATE dispatch SET state = 'COMPLETED' WHERE wo_id = :w"), {"w": wo})
    _409(_post(api, wo, UNDO, m))
    _409(_post(api, wo, ARRIVED, m))


def test_T_LIFE_5_concurrent_undos_exactly_one_succeeds(
    api: TestClient, t: Tenant, app_engine: Engine
) -> None:
    m = t.contractors["marco"]
    for _ in range(10):
        wo = _job(app_engine, t)
        a = _ok(_post(api, wo, EN_ROUTE, m))
        body = {"action": "undo", "corrects_event_id": str(a.event_id)}
        codes: list[int] = []
        start = threading.Barrier(3)

        def go(
            body: dict[str, Any] = body,
            wo: uuid.UUID = wo,
            start: threading.Barrier = start,
            codes: list[int] = codes,
        ) -> None:
            start.wait()
            codes.append(_post(api, wo, body, m).status_code)

        threads = [threading.Thread(target=go) for _ in range(3)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        assert sorted(codes) == [200, 409, 409]
        assert [e["type"] for e in _events(app_engine, wo)] == ["ADVANCE", "CORRECTION"]


def test_T_LIFE_5_only_the_bound_contractor_can_transition(
    api: TestClient, t: Tenant, app_engine: Engine
) -> None:
    wo = _job(app_engine, t)
    ana = t.contractors["ana"]
    assert _post(api, wo, EN_ROUTE, ana).status_code == 404  # stranger (§2.1 row 8)
    assert _post(api, wo, EN_ROUTE, t.owner).status_code == 403  # owner read-only (H-1)


def test_T_IDEM_1_transition_keys_are_scoped(
    api: TestClient, t: Tenant, app_engine: Engine
) -> None:
    m, a = t.contractors["marco"], t.contractors["ana"]
    marco_wo, marco_wo2, ana_wo = (
        _job(app_engine, t),
        _job(app_engine, t),
        _job(app_engine, t, "ana"),
    )
    key = "shared-key-0001"
    marco = _ok(_post(api, marco_wo, EN_ROUTE, m, key=key))
    # Ana reusing Marco's exact key: her own independent result, never Marco's event.
    ana = _ok(_post(api, ana_wo, EN_ROUTE, a, key=key))
    assert ana.event_id != marco.event_id
    assert str(marco.event_id) not in str(ana.model_dump())
    # Same user, same key, different WO: an independent request.
    other = _ok(_post(api, marco_wo2, EN_ROUTE, m, key=key))
    assert other.event_id not in {marco.event_id, ana.event_id}
    # Same user + scope + key, different body → 422 IDEMPOTENCY_KEY_REUSED; nothing stored.
    reused = _post(api, marco_wo, ARRIVED, m, key=key)
    assert reused.status_code == 422
    assert reused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert str(marco.event_id) not in reused.text
    # Same everything → the original response, no second event.
    replay = _ok(_post(api, marco_wo, EN_ROUTE, m, key=key))
    assert replay.event_id == marco.event_id
    assert len(_events(app_engine, marco_wo)) == 1

"""Identity gate through the real routes and Postgres: T-AUTH-15 and T-AUTH-16 (HTTP halves).

Routes behind the gate are still stubs here (501 once allowed), which is exactly what these
tests need: the gate decides before any handler runs, and a denied request changes nothing.
"""

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.db.session import get_engine
from app.main import create_app
from app.settings import normalize_database_url
from tests.conftest import make_settings
from tests.integration.factories import Tenant, make_offer, make_tenant

pytestmark = pytest.mark.integration

WO_ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/v1/workorders/{wo}", None),
    ("POST", "/v1/workorders/{wo}/transition", {"action": "advance", "stage": "EN_ROUTE"}),
    ("POST", "/v1/workorders/{wo}/photos", None),
    (
        "POST",
        "/v1/workorders/{wo}/complete",
        {
            "failure_code": "X",
            "actual_fault_matched": True,
            "labor_hours": 1,
            "technician_id": "M",
        },
    ),
    ("POST", "/v1/contractor/{cid}/accept/{wo}", None),
    ("POST", "/v1/contractor/{cid}/decline/{wo}", {}),
    ("POST", "/v1/me/accept/{wo}", None),
    ("POST", "/v1/me/decline/{wo}", {}),
]


@dataclass
class Setup:
    midtown: Tenant
    other: Tenant
    offer_wo: uuid.UUID  # Marco OFFERED (current), Ana QUEUED
    other_wo: uuid.UUID  # Zed's, other tenant


@pytest.fixture
def api(migrated_db: None) -> Iterator[TestClient]:
    url = normalize_database_url(os.environ["DATABASE_URL"])
    with TestClient(create_app(make_settings(url, env="ci"))) as c:
        yield c
    get_engine.cache_clear()


@pytest.fixture
def setup(app_engine: Engine) -> Setup:
    with app_engine.begin() as conn:
        midtown = make_tenant(conn, ["marco", "ana"])
        other = make_tenant(conn, ["zed"])
        m, a = midtown.contractors["marco"], midtown.contractors["ana"]
        offer = make_offer(conn, midtown, [(m, "OFFERED"), (a, "QUEUED")], current=m)
        z = other.contractors["zed"]
        other_wo = make_offer(conn, other, [(z, "OFFERED")], current=z)
    return Setup(midtown, other, offer, other_wo)


def _body(res: Any) -> dict[str, Any]:
    body = dict(res.json())
    body.pop("server_time")
    return body


def _call(api: TestClient, method: str, path: str, json: Any, auth: dict[str, str]) -> Any:
    if path.endswith("/photos"):
        return api.request(
            method, path, files={"file": ("p.jpg", b"\xff\xd8x", "image/jpeg")}, headers=auth
        )
    return api.request(method, path, json=json, headers=auth)


def test_T_AUTH_15_contractor_on_any_other_cid_gets_identical_403(
    api: TestClient, setup: Setup
) -> None:
    marco = setup.midtown.contractors["marco"]
    others = [
        setup.midtown.contractors["ana"].contractor_id,
        setup.other.contractors["zed"].contractor_id,
        uuid.uuid4(),
    ]
    bodies = []
    for cid in others:
        for path in (
            f"/v1/contractor/{cid}/schedule",
            f"/v1/contractor/{cid}/accept/{setup.offer_wo}",
            f"/v1/contractor/{cid}/decline/{uuid.uuid4()}",
        ):
            res = (
                api.post(path, json={}, headers=marco.auth)
                if "/schedule" not in path
                else (api.get(path, headers=marco.auth))
            )
            assert res.status_code == 403, path
            bodies.append(_body(res))
    assert all(b == bodies[0] for b in bodies)
    assert bodies[0] == {
        "error": {"code": "FORBIDDEN", "message": "You don't have access to this."}
    }


def test_T_AUTH_15_owner_on_unknown_or_cross_tenant_cid_gets_identical_404(
    api: TestClient, setup: Setup
) -> None:
    owner = setup.midtown.owner
    zed = setup.other.contractors["zed"].contractor_id
    a = api.get(f"/v1/contractor/{zed}/schedule", headers=owner.auth)
    b = api.get(f"/v1/contractor/{uuid.uuid4()}/schedule", headers=owner.auth)
    assert a.status_code == b.status_code == 404
    assert _body(a) == _body(b)
    own = setup.midtown.contractors["marco"].contractor_id
    assert api.get(f"/v1/contractor/{own}/schedule", headers=owner.auth).status_code == 200


def test_T_AUTH_15_contractor_404s_are_identical_for_every_wo_action(
    api: TestClient, setup: Setup, app_engine: Engine
) -> None:
    marco, ana = setup.midtown.contractors["marco"], setup.midtown.contractors["ana"]
    with app_engine.begin() as conn:
        stranger_wo = make_offer(
            conn, setup.midtown, [(ana, "OFFERED")], current=ana
        )  # Marco has no row
    targets = {
        "nonexistent": (marco, uuid.uuid4()),
        "cross_tenant": (marco, setup.other_wo),
        "stranger": (marco, stranger_wo),
        "queued_candidate": (ana, setup.offer_wo),  # Ana is rank 2, never offered
    }
    bodies = []
    for name, (who, wo) in targets.items():
        for method, template, json in WO_ROUTES:
            path = template.format(cid=who.contractor_id, wo=wo)
            res = _call(api, method, path, json, who.auth)
            assert res.status_code == 404, (name, path, res.text)
            bodies.append(_body(res))
    assert all(b == bodies[0] for b in bodies)
    assert bodies[0] == {"error": {"code": "NOT_FOUND", "message": "Not found."}}


def _dispatch_row(engine: Engine, wo: uuid.UUID) -> tuple[Any, ...]:
    with engine.connect() as conn:
        return tuple(
            conn.execute(
                text("SELECT state, current_contractor_id, version FROM dispatch WHERE wo_id = :w"),
                {"w": wo},
            ).one()
        )


def test_T_AUTH_16_owner_cannot_act_as_contractor(
    api: TestClient, setup: Setup, app_engine: Engine
) -> None:
    before = _dispatch_row(app_engine, setup.offer_wo)
    marco = setup.midtown.contractors["marco"]
    for owner in (setup.midtown.owner, setup.midtown.fm):
        for method, template, json in WO_ROUTES:
            if template.startswith("/v1/me/") or template == "/v1/workorders/{wo}":
                continue
            path = template.format(cid=marco.contractor_id, wo=setup.offer_wo)
            res = _call(api, method, path, json, owner.auth)
            assert res.status_code == 403, (owner.role, path, res.text)
        # Read is allowed (owner serializer; stub until M2-T2).
        assert api.get(f"/v1/workorders/{setup.offer_wo}", headers=owner.auth).status_code == 501
        # Owner/FM have no contractor_id: every /me action → 403.
        assert api.get("/v1/me/schedule", headers=owner.auth).status_code == 403
        for path in (f"/v1/me/accept/{setup.offer_wo}", f"/v1/me/decline/{setup.offer_wo}"):
            assert api.post(path, json={}, headers=owner.auth).status_code == 403
    assert _dispatch_row(app_engine, setup.offer_wo) == before


def test_gate_allows_the_offeree_through_to_the_handler(api: TestClient, setup: Setup) -> None:
    marco = setup.midtown.contractors["marco"]
    assert api.get(f"/v1/workorders/{setup.offer_wo}", headers=marco.auth).status_code == 501
    assert api.get("/v1/me/schedule", headers=marco.auth).status_code == 200
    res = api.post(f"/v1/me/accept/{setup.offer_wo}", headers=marco.auth)
    assert res.status_code == 501
    # Offeree may not do bound-only work yet (row 13).
    res = api.post(
        f"/v1/workorders/{setup.offer_wo}/transition",
        json={"action": "advance", "stage": "EN_ROUTE"},
        headers=marco.auth,
    )
    assert res.status_code == 403


def test_gate_answers_409_for_a_past_candidate_without_touching_dispatch(
    api: TestClient, setup: Setup, app_engine: Engine
) -> None:
    """§2.1 row 11 / D10 H-2: the 409 comes from the gate; no other candidate is named."""
    marco, ana = setup.midtown.contractors["marco"], setup.midtown.contractors["ana"]
    with app_engine.begin() as conn:
        wo = make_offer(conn, setup.midtown, [(ana, "EXPIRED"), (marco, "OFFERED")], current=marco)
    before = _dispatch_row(app_engine, wo)
    for path in (f"/v1/me/accept/{wo}", f"/v1/me/decline/{wo}"):
        res = api.post(path, json={}, headers=ana.auth)
        assert res.status_code == 409
        assert _body(res) == {
            "error": {
                "code": "OFFER_UNAVAILABLE",
                "message": "This offer is no longer available.",
                "reason": "reassigned",
            }
        }
    assert str(marco.contractor_id) not in res.text
    assert api.get(f"/v1/workorders/{wo}", headers=ana.auth).status_code == 404  # row 12
    assert _dispatch_row(app_engine, wo) == before

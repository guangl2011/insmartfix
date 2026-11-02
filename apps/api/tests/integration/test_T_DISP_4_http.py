"""T-DISP-4 over HTTP: dispatch create is owner/FM only and tenant-bounded (D10 H-6, FR-10.1)."""

import os
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.auth.tokens import issue_token
from app.contract.dispatch import DispatchCreateResponse
from app.db.models import Dispatch, DispatchCandidate, WorkOrder
from app.db.session import get_engine, get_sessionmaker
from app.main import create_app
from app.settings import normalize_database_url
from tests.conftest import TEST_JWT_SECRET, make_settings
from tests.integration.conftest import World, make_world

pytestmark = pytest.mark.integration


@pytest.fixture
def api(migrated_db: None) -> Iterator[TestClient]:
    url = normalize_database_url(os.environ["DATABASE_URL"])
    with TestClient(create_app(make_settings(url, env="ci"))) as c:
        yield c
    get_sessionmaker.cache_clear()
    get_engine.cache_clear()


@pytest.fixture
def worlds(app_engine: Engine) -> tuple[World, World]:
    with app_engine.begin() as conn:
        return make_world(conn), make_world(conn)


def _auth(engine: Engine, user_id: uuid.UUID) -> dict[str, str]:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT role, tenant_id, contractor_id, token_version FROM users WHERE id = :u"),
            {"u": user_id},
        ).one()
    token, _ = issue_token(
        user_id=user_id,
        role=row.role,
        tenant_id=row.tenant_id,
        contractor_id=row.contractor_id,
        token_version=row.token_version,
        secret=TEST_JWT_SECRET,
    )
    return {"Authorization": f"Bearer {token}"}


def _body(asset_id: uuid.UUID, *contractors: uuid.UUID, **extra: Any) -> dict[str, Any]:
    return {
        "asset_id": str(asset_id),
        "symptom": "Not cooling",
        "sla_minutes": 15,
        "candidates": [
            {"contractor_id": str(c), "match_score": 0.9, "reason": "near"} for c in contractors
        ],
        **extra,
    }


def _candidacies(engine: Engine, contractor_id: uuid.UUID) -> int:
    with Session(engine) as s:
        return (
            s.scalar(
                select(func.count())
                .select_from(DispatchCandidate)
                .where(DispatchCandidate.contractor_id == contractor_id)
            )
            or 0
        )


def test_owner_creates_a_dispatched_work_order(
    api: TestClient, app_engine: Engine, worlds: tuple[World, World]
) -> None:
    w, _ = worlds
    res = api.post(
        "/v1/dispatch/workorders",
        json=_body(w.asset_id, w.contractor_id),
        headers=_auth(app_engine, w.owner_user_id),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    DispatchCreateResponse.model_validate(body)  # contract conformance (excluded from the smoke)
    assert set(body) == {"wo_id", "server_time"}
    wo_id = uuid.UUID(body["wo_id"])
    with Session(app_engine) as s:
        assert s.get_one(WorkOrder, wo_id).tenant_id == w.tenant_id
        d = s.get_one(Dispatch, wo_id)
        assert (d.state, d.current_contractor_id) == ("PENDING", w.contractor_id)


def test_T_DISP_4_candidate_in_another_tenant_is_422_and_zed_is_untouched(
    api: TestClient, app_engine: Engine, worlds: tuple[World, World]
) -> None:
    mine, zed = worlds
    before = _candidacies(app_engine, zed.contractor_id)
    res = api.post(
        "/v1/dispatch/workorders",
        json=_body(mine.asset_id, mine.contractor_id, zed.contractor_id),
        headers=_auth(app_engine, mine.owner_user_id),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"
    assert str(zed.contractor_id) not in res.text  # no hint which id failed
    assert _candidacies(app_engine, zed.contractor_id) == before


def test_T_DISP_4_asset_in_another_tenant_is_404(
    api: TestClient, app_engine: Engine, worlds: tuple[World, World]
) -> None:
    mine, other = worlds
    res = api.post(
        "/v1/dispatch/workorders",
        json=_body(other.asset_id, mine.contractor_id),
        headers=_auth(app_engine, mine.owner_user_id),
    )
    unknown = api.post(
        "/v1/dispatch/workorders",
        json=_body(uuid.uuid4(), mine.contractor_id),
        headers=_auth(app_engine, mine.owner_user_id),
    )
    assert res.status_code == unknown.status_code == 404
    # Same answer for "another tenant's" and "doesn't exist" (no oracle).
    assert res.json()["error"] == unknown.json()["error"]


def test_T_DISP_4_contractor_caller_is_403(
    api: TestClient, app_engine: Engine, worlds: tuple[World, World]
) -> None:
    w, _ = worlds
    res = api.post(
        "/v1/dispatch/workorders",
        json=_body(w.asset_id, w.contractor_id),
        headers=_auth(app_engine, w.contractor_user_id),
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"
    with Session(app_engine) as s:
        assert (
            s.scalar(
                select(func.count())
                .select_from(WorkOrder)
                .where(WorkOrder.tenant_id == w.tenant_id)
            )
            == 1
        )


@pytest.mark.parametrize(
    "extra",
    [
        {"tenant_id": str(uuid.uuid4())},  # mass assignment
        {"predicted_failure_code": "COMP-CONTACTOR"},
        {"sla_minutes": 0},
        {"candidates": []},
        {"symptom": ""},
    ],
)
def test_T_DISP_4_unknown_fields_and_bad_values_are_422(
    api: TestClient, app_engine: Engine, worlds: tuple[World, World], extra: dict[str, Any]
) -> None:
    w, _ = worlds
    res = api.post(
        "/v1/dispatch/workorders",
        json=_body(w.asset_id, w.contractor_id, **extra),
        headers=_auth(app_engine, w.owner_user_id),
    )
    assert res.status_code == 422


def test_dispatch_create_requires_a_token(api: TestClient, worlds: tuple[World, World]) -> None:
    w, _ = worlds
    res = api.post("/v1/dispatch/workorders", json=_body(w.asset_id, w.contractor_id))
    assert res.status_code == 401

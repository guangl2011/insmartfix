"""M2-T1 over HTTP: `GET /v1/failure-codes` (FR-7.1) and the dispatch-time prediction snapshot
taken from the stub engine (D10 L-4)."""

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth.tokens import issue_token
from app.catalog.service import list_codes
from app.contract.catalog import FailureCodeList
from app.db.models import WorkOrder
from app.db.session import get_engine, get_sessionmaker
from app.main import create_app
from app.seed import fixtures as fx
from app.seed.load import load
from app.settings import normalize_database_url
from tests.conftest import TEST_JWT_SECRET, make_settings

pytestmark = pytest.mark.integration


@pytest.fixture
def api(app_engine: Engine) -> Iterator[TestClient]:
    with Session(app_engine) as s, s.begin():
        load(s, now=datetime.now(UTC), password="not-a-real-password", hash_password=lambda p: "x")
    url = normalize_database_url(os.environ["DATABASE_URL"])
    with TestClient(create_app(make_settings(url, env="ci"))) as c:
        yield c
    get_sessionmaker.cache_clear()
    get_engine.cache_clear()


def _bearer(user_id: uuid.UUID, role: str, cid: uuid.UUID | None) -> dict[str, str]:
    token, _ = issue_token(
        user_id=user_id,
        role=role,
        tenant_id=fx.TENANT_MIDTOWN,
        contractor_id=cid,
        token_version=0,
        secret=TEST_JWT_SECRET,
    )
    return {"Authorization": f"Bearer {token}"}


MARCO = (fx.U_MARCO, "contractor", fx.C_MARCO)
OWNER = (fx.U_OWNER, "owner", None)


def test_failure_codes_are_filtered_by_subtype_in_catalog_order(
    api: TestClient, app_engine: Engine
) -> None:
    res = api.get("/v1/failure-codes", params={"subtype": "RTU"}, headers=_bearer(*MARCO))
    assert res.status_code == 200, res.text
    body = res.json()
    FailureCodeList.model_validate(body)  # contract conformance (excluded from the DB-less smoke)
    with Session(app_engine) as s:
        expected = [(c.code, c.component_group, c.label) for c in list_codes(s, "RTU")]
    got = [(c["code"], c["component_group"], c["label"]) for c in body["failure_codes"]]
    assert got == expected
    assert {c["subtype"] for c in body["failure_codes"]} == {"RTU"}


def test_failure_codes_without_subtype_and_with_bad_input(api: TestClient) -> None:
    everything = api.get("/v1/failure-codes", headers=_bearer(*OWNER))
    assert {c["subtype"] for c in everything.json()["failure_codes"]} >= {"RTU", "AHU"}
    unknown = api.get("/v1/failure-codes", params={"subtype": "BOILER"}, headers=_bearer(*MARCO))
    assert unknown.json()["failure_codes"] == []
    too_long = api.get("/v1/failure-codes", params={"subtype": "x" * 65}, headers=_bearer(*MARCO))
    assert too_long.status_code == 422
    assert api.get("/v1/failure-codes").status_code == 401


@pytest.mark.parametrize(
    ("asset", "expected"), [(fx.A_RTU04, "COMP-CONTACTOR"), (fx.A_AHUNEW01, None)]
)
def test_dispatch_create_snapshots_the_engine_prediction(
    api: TestClient, app_engine: Engine, asset: uuid.UUID, expected: str | None
) -> None:
    res = api.post(
        "/v1/dispatch/workorders",
        json={
            "asset_id": str(asset),
            "symptom": "Not cooling",
            "sla_minutes": 30,
            "candidates": [{"contractor_id": str(fx.C_MARCO), "match_score": 0.9, "reason": "r"}],
        },
        headers=_bearer(*OWNER),
    )
    assert res.status_code == 201, res.text
    with Session(app_engine) as s:
        wo = s.get_one(WorkOrder, uuid.UUID(res.json()["wo_id"]))
        assert wo.predicted_failure_code == expected

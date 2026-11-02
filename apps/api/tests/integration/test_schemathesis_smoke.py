"""M1-T1: schemathesis schema-validity smoke (TEST_PLAN §2 "Contract"), against Postgres.

Loads the live app's OpenAPI document (fails if it is not a valid OpenAPI 3.1 schema), generates
requests for every operation and checks that each response is one the contract documents, with a
body that matches its declared schema. Requests run as a real contractor through the real
identity gate (random ids mostly meet its 404 path, which must also conform).
"""

import os
from typing import Any

import pytest
import schemathesis
from hypothesis import HealthCheck, settings
from schemathesis.specs.openapi.checks import (
    content_type_conformance,
    response_schema_conformance,
    status_code_conformance,
)
from sqlalchemy import Engine

from app.main import create_app
from app.settings import normalize_database_url
from tests.conftest import make_settings
from tests.integration.factories import make_tenant

pytestmark = pytest.mark.integration


@pytest.fixture
def api_schema(migrated_db: None) -> Any:
    url = normalize_database_url(os.environ["DATABASE_URL"])
    return schemathesis.openapi.from_asgi("/openapi.json", create_app(make_settings(url, env="ci")))


@pytest.fixture(scope="module")
def auth(app_engine: Engine) -> dict[str, str]:
    with app_engine.begin() as conn:
        return make_tenant(conn, ["fuzz"]).contractors["fuzz"].auth


schema = schemathesis.pytest.from_fixture("api_schema")


@schema.parametrize()
@settings(max_examples=8, deadline=None, suppress_health_check=list(HealthCheck))
def test_every_operation_conforms_to_its_schema(
    case: schemathesis.Case[Any], auth: dict[str, str]
) -> None:
    response = case.call(headers=auth)
    case.validate_response(
        response,
        checks=[status_code_conformance, content_type_conformance, response_schema_conformance],
    )
    assert response.status_code < 500 or response.status_code == 501

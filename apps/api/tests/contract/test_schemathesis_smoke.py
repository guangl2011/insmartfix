"""M1-T1: schemathesis schema-validity smoke (TEST_PLAN §2 "Contract").

Loads the live app's OpenAPI document (fails if it is not a valid OpenAPI 3.1 schema), generates
requests for every operation and checks that each response is one the contract documents, with a
body that matches its declared schema. Later tasks keep this green as stubs become real routes.
"""

from typing import Any

import schemathesis
from hypothesis import HealthCheck, settings
from schemathesis.specs.openapi.checks import (
    content_type_conformance,
    response_schema_conformance,
    status_code_conformance,
)

from app.main import create_app
from tests.conftest import make_settings

schema = schemathesis.openapi.from_asgi("/openapi.json", create_app(make_settings()))


@schema.exclude(path_regex=r"^/v1/readyz$").parametrize()
@settings(max_examples=8, deadline=None, suppress_health_check=list(HealthCheck))
def test_every_operation_conforms_to_its_schema(case: schemathesis.Case[Any]) -> None:
    response = case.call()
    case.validate_response(
        response,
        checks=[status_code_conformance, content_type_conformance, response_schema_conformance],
    )
    assert response.status_code < 500 or response.status_code == 501

"""M1-T1: the full v1 contract (spec §5) is declared, mounted and exported.

Every §5 route exists with its documented method, path, operation id and statuses; the schema
split (FR-3.5), the error envelope + codes (incl. D12), `server_time`, `Idempotency-Key` and
`extra="forbid"` request models are all visible in `openapi.json`.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.contract.common import ErrorCode, OfferUnavailableReason
from app.main import create_app
from tests.conftest import authed_app, make_settings

WO = "6f1c1d2e-0000-4000-8000-000000000001"
CID = "6f1c1d2e-0000-4000-8000-000000000002"

# (method, path, operation_id, success status) — spec §5 plus D11 logout.
V1_ROUTES: list[tuple[str, str, str, int]] = [
    ("post", "/v1/auth/login", "login", 200),
    ("post", "/v1/auth/logout", "logout", 204),
    ("get", "/v1/me", "get_me", 200),
    ("get", "/v1/contractor/{cid}/schedule", "get_contractor_schedule", 200),
    ("get", "/v1/me/schedule", "get_my_schedule", 200),
    ("post", "/v1/contractor/{cid}/accept/{wo}", "accept_offer", 200),
    ("post", "/v1/me/accept/{wo}", "accept_my_offer", 200),
    ("post", "/v1/contractor/{cid}/decline/{wo}", "decline_offer", 204),
    ("post", "/v1/me/decline/{wo}", "decline_my_offer", 204),
    ("get", "/v1/workorders/{wo}", "get_workorder", 200),
    ("post", "/v1/workorders/{wo}/transition", "transition_workorder", 200),
    ("post", "/v1/workorders/{wo}/photos", "upload_workorder_photo", 201),
    ("post", "/v1/workorders/{wo}/complete", "complete_workorder", 200),
    ("get", "/v1/failure-codes", "list_failure_codes", 200),
    ("post", "/v1/dispatch/workorders", "create_dispatch_workorder", 201),
    ("get", "/v1/healthz", "healthz", 200),
    ("get", "/v1/readyz", "readyz", 200),
]
PUBLIC = {"/v1/auth/login", "/v1/healthz", "/v1/readyz"}
IDEMPOTENT_MUTATIONS = {
    "accept_offer",
    "accept_my_offer",
    "decline_offer",
    "decline_my_offer",
    "transition_workorder",
    "upload_workorder_photo",
    "complete_workorder",
    "create_dispatch_workorder",
}

# Minimal valid bodies, so stubs reach the handler (and return 501) rather than 422.
BODIES: dict[str, dict[str, Any]] = {
    "login": {"email": "marco@test.insmart.ai", "password": "x"},
    "decline_offer": {},
    "decline_my_offer": {"reason": "too_far"},
    "transition_workorder": {"action": "advance", "stage": "EN_ROUTE"},
    "complete_workorder": {
        "failure_code": "COMP-CONTACTOR",
        "actual_fault_matched": True,
        "labor_hours": 1.5,
        "technician_id": "Marco Rossi",
    },
    "create_dispatch_workorder": {
        "asset_id": WO,
        "symptom": "Discharge air too warm",
        "sla_minutes": 15,
        "candidates": [{"contractor_id": CID, "match_score": 0.82, "reason": "Nearby"}],
    },
}


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return create_app(schema_only=True).openapi()


def _op(spec: dict[str, Any], method: str, path: str) -> dict[str, Any]:
    op: dict[str, Any] = spec["paths"][path][method]
    return op


def _resolve(spec: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if ref is None:
        return schema
    resolved: dict[str, Any] = spec["components"]["schemas"][ref.rsplit("/", 1)[1]]
    return resolved


def test_every_v1_route_is_mounted_with_its_operation_id(spec: dict[str, Any]) -> None:
    declared = {(m, p) for p, ops in spec["paths"].items() for m in ops}
    assert declared == {(m, p) for m, p, _, _ in V1_ROUTES}
    for method, path, op_id, status in V1_ROUTES:
        op = _op(spec, method, path)
        assert op["operationId"] == op_id
        assert str(status) in op["responses"]


def test_d11_logout_is_authenticated_204(spec: dict[str, Any]) -> None:
    op = _op(spec, "post", "/v1/auth/logout")
    assert set(op["responses"]) >= {"204", "401"}
    assert op["security"] == [{"bearerAuth": []}]


def test_error_envelope_and_codes(spec: dict[str, Any]) -> None:
    schemas = spec["components"]["schemas"]
    assert set(schemas["ErrorEnvelope"]["required"]) == {"error", "server_time"}
    assert set(schemas["ErrorBody"]["required"]) == {"code", "message"}
    codes = set(schemas["ErrorCode"]["enum"])
    assert {
        "INVALID_CREDENTIALS",
        "OFFER_UNAVAILABLE",
        "INVALID_TRANSITION",
        "ALREADY_COMPLETED",
        "IDEMPOTENCY_KEY_REUSED",  # D12
    } <= codes
    assert codes == {c.value for c in ErrorCode}
    assert (
        set(schemas["OfferUnavailableReason"]["enum"])
        == {r.value for r in OfferUnavailableReason}
        == {"expired", "reassigned", "withdrawn"}
    )
    assert "HTTPValidationError" not in schemas  # every 422 is the envelope


def test_every_error_response_uses_the_envelope(spec: dict[str, Any]) -> None:
    for method, path, _, _ in V1_ROUTES:
        for status, resp in _op(spec, method, path)["responses"].items():
            if int(status) >= 400:
                schema = resp["content"]["application/json"]["schema"]
                assert schema == {"$ref": "#/components/schemas/ErrorEnvelope"}, (path, status)


def test_every_json_success_body_carries_server_time(spec: dict[str, Any]) -> None:
    for method, path, _, status in V1_ROUTES:
        resp = _op(spec, method, path)["responses"][str(status)]
        if status == 204:
            assert "content" not in resp or not resp["content"].get("application/json")
            continue
        schema = resp["content"]["application/json"]["schema"]
        variants = schema.get("anyOf", [schema])
        for v in variants:
            assert "server_time" in _resolve(spec, v)["required"], (path, v)


def test_fr_3_5_ranked_candidates_only_on_owner_variant(spec: dict[str, Any]) -> None:
    schemas = spec["components"]["schemas"]
    assert "ranked_candidates" not in schemas["WorkOrderDetail"]["properties"]
    assert "ranked_candidates" in schemas["OwnerWorkOrderDetail"]["properties"]
    for name in ("OfferSummary", "ScheduleResponse"):
        assert "ranked_candidates" not in schemas[name]["properties"]
    accept = _op(spec, "post", "/v1/me/accept/{wo}")["responses"]["200"]
    assert accept["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/WorkOrderDetail"
    }


def test_mutations_take_idempotency_key_header(spec: dict[str, Any]) -> None:
    for method, path, op_id, _ in V1_ROUTES:
        params = _op(spec, method, path).get("parameters", [])
        headers = [p for p in params if p["in"] == "header"]
        if op_id in IDEMPOTENT_MUTATIONS:
            assert [h["name"] for h in headers] == ["Idempotency-Key"], op_id
            assert headers[0]["required"] is False
        else:
            assert headers == [], op_id


def test_authenticated_routes_declare_bearer_auth(spec: dict[str, Any]) -> None:
    assert spec["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
    for method, path, _, _ in V1_ROUTES:
        op = _op(spec, method, path)
        if path in PUBLIC:
            assert "security" not in op, path
        else:
            assert op["security"] == [{"bearerAuth": []}], path
            assert "401" in op["responses"], path


def test_request_models_forbid_unknown_fields(spec: dict[str, Any]) -> None:
    schemas = spec["components"]["schemas"]
    for name in (
        "LoginRequest",
        "DeclineRequest",
        "TransitionRequest",
        "CompletionReport",
        "PartUsed",
        "DispatchCreateRequest",
        "DispatchCandidateIn",
    ):
        assert schemas[name]["additionalProperties"] is False, name


def test_photo_upload_is_single_multipart_file(spec: dict[str, Any]) -> None:
    body = _op(spec, "post", "/v1/workorders/{wo}/photos")["requestBody"]
    schema = body["content"]["multipart/form-data"]["schema"]
    assert schema["required"] == ["file"]
    assert schema["properties"]["file"]["format"] == "binary"


IMPLEMENTED = {
    "login",
    "logout",
    "get_me",
    "healthz",
    "readyz",
    "create_dispatch_workorder",
    "list_failure_codes",
    "get_contractor_schedule",
    "get_my_schedule",
    "accept_offer",
    "accept_my_offer",
    "decline_offer",
    "decline_my_offer",
}


@pytest.mark.parametrize(
    ("method", "path", "op_id"),
    [(m, p, o) for m, p, o, _ in V1_ROUTES if o not in IMPLEMENTED],
)
def test_stubs_answer_501_envelope(method: str, path: str, op_id: str) -> None:
    url = path.replace("{cid}", CID).replace("{wo}", WO)
    with TestClient(authed_app()) as c:
        res = c.request(method, url, json=BODIES.get(op_id))
    assert res.status_code == 501, (op_id, res.text)
    body = res.json()
    assert body["error"]["code"] == "NOT_IMPLEMENTED"
    assert "server_time" in body


@pytest.mark.parametrize(
    ("method", "path", "op_id"),
    [(m, p, o) for m, p, o, _ in V1_ROUTES if p not in PUBLIC],
)
def test_every_non_public_route_needs_a_token(method: str, path: str, op_id: str) -> None:
    url = path.replace("{cid}", CID).replace("{wo}", WO)
    with TestClient(create_app(make_settings())) as c:
        res = c.request(method, url, json=BODIES.get(op_id))
    assert res.status_code == 401, (op_id, res.text)
    assert res.json()["error"]["code"] == "UNAUTHENTICATED"
    assert res.headers["www-authenticate"] == "Bearer"


def test_validation_error_is_enveloped_and_does_not_echo_input() -> None:
    with TestClient(create_app(make_settings())) as c:
        res = c.post("/v1/auth/login", json={"email": "a@b.c", "password": "hunter2", "x": 1})
    assert res.status_code == 422
    body = res.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "hunter2" not in res.text


def test_unknown_route_and_method_are_enveloped() -> None:
    with TestClient(create_app(make_settings())) as c:
        nf = c.get("/v1/nope")
        na = c.delete("/v1/healthz")
    assert (nf.status_code, nf.json()["error"]["code"]) == (404, "NOT_FOUND")
    assert (na.status_code, na.json()["error"]["code"]) == (405, "METHOD_NOT_ALLOWED")


def test_malformed_json_body_is_a_422_envelope() -> None:
    with TestClient(create_app(make_settings())) as c:
        res = c.post(
            "/v1/auth/login", content=b"\xff{not json", headers={"content-type": "application/json"}
        )
    assert (res.status_code, res.json()["error"]["code"]) == (422, "VALIDATION_ERROR")

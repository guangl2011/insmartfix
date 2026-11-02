"""Error envelope handlers (spec §5): codes, reason, generic 500, no input echo."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.contract.common import ErrorCode, OfferUnavailableReason
from app.core.errors import ApiError, install_error_handlers


def _app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/offer")
    def offer() -> None:
        raise ApiError(409, ErrorCode.OFFER_UNAVAILABLE, reason=OfferUnavailableReason.EXPIRED)

    @app.get("/limited")
    def limited() -> None:
        raise ApiError(429, ErrorCode.RATE_LIMITED, headers={"Retry-After": "60"})

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret detail marco@test.insmart.ai")

    return app


def test_api_error_carries_code_message_and_reason() -> None:
    res = TestClient(_app()).get("/offer")
    assert res.status_code == 409
    body = res.json()
    assert body["error"] == {
        "code": "OFFER_UNAVAILABLE",
        "message": "This offer is no longer available.",
        "reason": "expired",
    }
    assert "server_time" in body


def test_api_error_headers_pass_through_and_reason_omitted_when_unset() -> None:
    res = TestClient(_app()).get("/limited")
    assert res.status_code == 429
    assert res.headers["retry-after"] == "60"
    assert "reason" not in res.json()["error"]


def test_unhandled_exception_is_a_generic_500_envelope() -> None:
    res = TestClient(_app(), raise_server_exceptions=False).get("/boom")
    assert res.status_code == 500
    assert res.json()["error"]["code"] == "INTERNAL"
    assert "secret" not in res.text

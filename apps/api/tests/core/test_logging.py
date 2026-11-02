"""Structured JSON logs with request id and no PII (NFR-6, NFR-7)."""

import base64
import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.core.logging import REDACTED, JsonFormatter, redact, request_id_var, scrub
from app.main import create_app
from tests.conftest import make_settings


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


# A JWT-shaped string built at runtime (not a real token, and not a literal for secret scanners).
JWT = ".".join(_b64(p) for p in (b'{"alg":"HS256"}', b'{"sub":"marco"}', b"not-a-real-signature"))


def _format(msg: str, *args: object, **extra: object) -> dict[str, object]:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, msg, args, None)
    for k, v in extra.items():
        setattr(record, k, v)
    out: dict[str, object] = json.loads(JsonFormatter().format(record))
    return out


def test_message_text_is_scrubbed_of_tokens_and_emails() -> None:
    line = _format("login %s with Bearer %s and %s", "marco@test.insmart.ai", "abc.def", JWT)
    text = str(line["msg"])
    assert "marco@" not in text
    assert "abc.def" not in text
    assert JWT not in text
    assert "[EMAIL]" in text


def test_sensitive_extra_fields_are_masked_recursively() -> None:
    line = _format(
        "x",
        headers={"Authorization": "Bearer abc", "Accept": "json"},
        password="hunter2",
        items=[{"token": "t"}],
    )
    assert line["headers"] == {"Authorization": REDACTED, "Accept": "json"}
    assert line["password"] == REDACTED
    assert line["items"] == [{"token": REDACTED}]


def test_exception_logs_type_only() -> None:
    try:
        raise ValueError("password=hunter2")
    except ValueError:
        import sys

        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "boom", None, sys.exc_info())
    line = json.loads(JsonFormatter().format(record))
    assert line["exc_type"] == "ValueError"
    assert "hunter2" not in json.dumps(line)


def test_request_id_included_from_context() -> None:
    token = request_id_var.set("req-12345678")
    try:
        assert _format("hi")["request_id"] == "req-12345678"
    finally:
        request_id_var.reset(token)


def test_scrub_and_redact_leave_ordinary_values() -> None:
    assert scrub("GET /v1/me 200") == "GET /v1/me 200"
    assert redact(3) == 3


def test_access_log_has_route_template_and_request_id(caplog: pytest.LogCaptureFixture) -> None:
    c = TestClient(create_app(make_settings()))
    with caplog.at_level(logging.INFO, logger="app.access"):
        res = c.get(
            "/v1/workorders/6f1c1d2e-0000-4000-8000-000000000001",
            headers={"Authorization": f"Bearer {JWT}", "X-Request-ID": "client-req-0001"},
        )
    assert res.headers["x-request-id"] == "client-req-0001"
    rec = next(r for r in caplog.records if r.name == "app.access")
    assert rec.__dict__["route"] == "/v1/workorders/{wo}"
    assert rec.__dict__["status"] == 501
    rendered = JsonFormatter().format(rec)
    assert JWT not in rendered
    assert "6f1c1d2e" not in rendered


def test_malformed_inbound_request_id_is_replaced() -> None:
    res = TestClient(create_app(make_settings())).get(
        "/v1/healthz", headers={"X-Request-ID": "bad id\twith junk"}
    )
    rid = res.headers["x-request-id"]
    assert rid != "bad id\twith junk"
    assert len(rid) == 32

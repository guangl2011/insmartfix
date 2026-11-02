"""CORS allow-list (NFR-6, D10 L-7): empty in production, exact origins only, no credentials."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from tests.conftest import make_settings

PREFLIGHT = {"Access-Control-Request-Method": "POST"}


def test_production_refuses_any_cors_origin() -> None:
    with pytest.raises(ValidationError, match="production"):
        make_settings(env="production", cors_origins=["https://app.example"])


@pytest.mark.parametrize("origin", ["*", "https://*.example"])
def test_wildcard_origins_refused(origin: str) -> None:
    with pytest.raises(ValidationError, match="wildcard"):
        make_settings(env="local", cors_origins=[origin])


def test_no_cors_headers_when_allow_list_empty() -> None:
    c = TestClient(create_app(make_settings(env="production")))
    res = c.options("/v1/auth/login", headers={"Origin": "https://evil.example", **PREFLIGHT})
    assert "access-control-allow-origin" not in res.headers


def test_only_listed_origin_is_allowed_without_credentials() -> None:
    c = TestClient(create_app(make_settings(env="local", cors_origins=["http://localhost:3000"])))
    ok = c.options("/v1/auth/login", headers={"Origin": "http://localhost:3000", **PREFLIGHT})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-credentials" not in ok.headers
    bad = c.options("/v1/auth/login", headers={"Origin": "https://evil.example", **PREFLIGHT})
    assert "access-control-allow-origin" not in bad.headers

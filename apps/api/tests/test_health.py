"""M0 scaffold: liveness/readiness probes (spec §5, NFR-7)."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import get_settings
from tests.conftest import TEST_JWT_SECRET, ClientFactory

SQLITE_OK = "sqlite+pysqlite:///:memory:"
UNREACHABLE = "postgresql+psycopg://nobody:nothing@127.0.0.1:1/none"


def test_healthz_ok_with_server_time(client_for: ClientFactory) -> None:
    res = client_for(SQLITE_OK).get("/v1/healthz")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert datetime.fromisoformat(body["server_time"]).tzinfo is not None


def test_readyz_ok_when_database_answers(client_for: ClientFactory) -> None:
    res = client_for(SQLITE_OK).get("/v1/readyz")
    assert res.status_code == 200
    assert res.json()["checks"] == {"database": "ok"}


def test_readyz_503_with_error_envelope_when_database_down(client_for: ClientFactory) -> None:
    res = client_for(UNREACHABLE).get("/v1/readyz")
    assert res.status_code == 503
    body = res.json()
    assert body["error"] == {"code": "NOT_READY", "message": "Database is unavailable."}
    assert "server_time" in body


def test_factory_reads_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """`uvicorn --factory app.main:create_app` builds the app from env vars alone."""
    get_settings.cache_clear()
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("DATABASE_URL", SQLITE_OK)
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    try:
        with TestClient(create_app()) as c:
            assert c.get("/v1/healthz").status_code == 200
    finally:
        get_settings.cache_clear()

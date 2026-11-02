"""M0 scaffold: liveness/readiness probes (spec §5, NFR-7)."""

from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app as module_app
from tests.conftest import ClientFactory

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


def test_module_level_app_serves_health() -> None:
    with TestClient(module_app) as c:
        assert c.get("/v1/healthz").status_code == 200

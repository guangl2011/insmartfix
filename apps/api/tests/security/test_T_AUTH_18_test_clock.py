"""T-AUTH-18 (A): the test clock is absent outside local/test/ci and startup refuses misconfig.

D10 H-7. The image half (`import app.testing` fails in the production image) is the CI `build`
job step; this file checks the app half plus that the Dockerfile still deletes the package.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.clock import FakeClockDisabledError, clock
from app.core.routes import iter_http_routes
from app.main import create_app
from app.settings import get_settings
from tests.conftest import SQLITE_MEMORY, TEST_JWT_SECRET, make_settings


def _test_paths(app: FastAPI) -> list[str]:
    return [p for r in iter_http_routes(app) if (p := r.path or "").startswith("/__test")]


@pytest.mark.parametrize("env", ["staging", "production"])
def test_T_AUTH_18_no_test_route_outside_test_envs(env: str) -> None:
    app = create_app(make_settings(env=env))
    assert _test_paths(app) == []
    with TestClient(app) as c:
        res = c.post("/__test/clock", json={"advance_seconds": 3600})
    assert res.status_code == 404
    with pytest.raises(FakeClockDisabledError):
        clock.set(datetime(2030, 1, 1, tzinfo=UTC))


def test_T_AUTH_18_not_mounted_in_test_env_without_fake_clock() -> None:
    assert _test_paths(create_app(make_settings(env="ci", fake_clock=False))) == []
    assert clock.fake_enabled is False


@pytest.mark.parametrize("env", ["local", "test", "ci"])
def test_T_AUTH_18_mounted_only_with_fake_clock_in_allow_listed_env(env: str) -> None:
    app = create_app(make_settings(env=env, fake_clock=True))
    assert sorted(_test_paths(app)) == ["/__test/clock", "/__test/clock"]
    assert "/__test/clock" not in app.openapi()["paths"]


@pytest.mark.parametrize("env", ["staging", "production"])
def test_T_AUTH_18_startup_refuses_fake_clock_outside_allow_list(
    env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ENV", env)
    monkeypatch.setenv("FAKE_CLOCK", "1")
    monkeypatch.setenv("DATABASE_URL", SQLITE_MEMORY)
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    try:
        with pytest.raises(ValidationError, match="FAKE_CLOCK"):
            create_app()
    finally:
        get_settings.cache_clear()


def test_T_AUTH_18_startup_refuses_unset_env(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setenv("DATABASE_URL", SQLITE_MEMORY)
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    try:
        with pytest.raises(ValidationError, match="env"):
            create_app()
    finally:
        get_settings.cache_clear()


def test_T_AUTH_18_production_image_deletes_test_package() -> None:
    dockerfile = (Path(__file__).parents[2] / "Dockerfile").read_text(encoding="utf-8")
    stages = dockerfile.split("\nFROM ")
    # The last stage is the default build target (staging/production) and deletes the package.
    assert stages[-1].startswith("base AS runtime")
    assert "RUN rm -rf ./app/testing" in stages[-1]


def test_test_clock_route_moves_server_time() -> None:
    at = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    with TestClient(create_app(make_settings(env="test", fake_clock=True))) as c:
        moved = c.post("/__test/clock", json={"set": at.isoformat(), "advance_seconds": 90})
        assert moved.status_code == 200
        assert moved.json()["frozen"] is True
        health = c.get("/v1/healthz").json()
        assert datetime.fromisoformat(health["server_time"]) == at.replace(minute=1, second=30)
        assert c.get("/__test/clock").json()["frozen"] is True
        back = c.post("/__test/clock", json={"reset": True}).json()
        assert back["frozen"] is False
        assert c.post("/__test/clock", json={"bogus": 1}).status_code == 422

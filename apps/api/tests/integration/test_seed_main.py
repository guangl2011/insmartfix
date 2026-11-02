"""`python -m app.seed`: refuses production, needs SEED_PASSWORD, loads with real argon2 hashes."""

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth.passwords import verify_password
from app.db.models import User
from app.seed import __main__ as seed_main
from app.seed import fixtures as fx
from app.settings import get_settings

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _fresh_settings() -> None:
    get_settings.cache_clear()


def test_seed_refuses_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("SEED_PASSWORD", "long-enough-password")
    assert seed_main.main() == 2
    get_settings.cache_clear()


def test_seed_needs_a_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "ci")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.delenv("SEED_PASSWORD", raising=False)
    assert seed_main.main() == 2
    monkeypatch.setenv("SEED_PASSWORD", "short")
    assert seed_main.main() == 2
    get_settings.cache_clear()


def test_seed_loads_with_argon2_hashes(monkeypatch: pytest.MonkeyPatch, app_engine: Engine) -> None:
    monkeypatch.setenv("ENV", "ci")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("SEED_PASSWORD", "seed-test-password-1")
    assert seed_main.main() == 0
    get_settings.cache_clear()
    with Session(app_engine) as s:
        marco = s.get_one(User, fx.U_MARCO)
        assert marco.password_hash is not None
        assert marco.password_hash.startswith("$argon2id$")
        assert verify_password(marco.password_hash, "seed-test-password-1")
        assert "seed-test-password-1" not in marco.password_hash

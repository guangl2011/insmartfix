import pytest
from pydantic import ValidationError

from app.settings import Settings, get_settings, normalize_database_url
from tests.conftest import TEST_JWT_SECRET


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgres://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
        ("postgresql://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
        ("postgresql+psycopg://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
        ("sqlite+pysqlite:///:memory:", "sqlite+pysqlite:///:memory:"),
    ],
)
def test_database_url_normalised(raw: str, expected: str) -> None:
    assert normalize_database_url(raw) == expected
    settings = Settings(database_url=raw, jwt_secret=TEST_JWT_SECRET, env="test")
    assert settings.database_url == expected


def test_jwt_secret_must_be_at_least_256_bits() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="sqlite://", jwt_secret="too-short", env="test")


@pytest.mark.parametrize("env", ["staging", "production"])
def test_fake_clock_refused_outside_allow_list(env: str) -> None:
    with pytest.raises(ValidationError, match="FAKE_CLOCK"):
        Settings(database_url="sqlite://", jwt_secret=TEST_JWT_SECRET, env=env, fake_clock=True)


@pytest.mark.parametrize("env", ["local", "test", "ci"])
def test_fake_clock_allowed_in_test_envs(env: str) -> None:
    s = Settings(database_url="sqlite://", jwt_secret=TEST_JWT_SECRET, env=env, fake_clock=True)
    assert s.fake_clock is True


def test_env_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENV", raising=False)
    with pytest.raises(ValidationError, match="env"):
        Settings(database_url="sqlite://", jwt_secret=TEST_JWT_SECRET)


def test_env_must_be_known() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="sqlite://", jwt_secret=TEST_JWT_SECRET, env="prod")


def test_settings_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgres://a:b@c/d")
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("FAKE_CLOCK", "1")
    monkeypatch.setenv("ENV", "ci")
    s = get_settings()
    assert s.database_url == "postgresql+psycopg://a:b@c/d"
    assert s.fake_clock is True
    assert s.jwt_secret.get_secret_value() == TEST_JWT_SECRET
    get_settings.cache_clear()

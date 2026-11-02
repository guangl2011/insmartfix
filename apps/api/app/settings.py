"""Runtime configuration — environment variables only (TEST_PLAN §3 environment parity)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

TEST_CLOCK_ENVS = frozenset({"local", "test", "ci"})


def normalize_database_url(url: str) -> str:
    """Managed Postgres providers hand out postgres:// or postgresql:// URLs; we use psycopg 3."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    # D10 H-7: no default, so startup fails if ENV is unset or misspelled.
    env: Literal["local", "test", "ci", "staging", "production"]
    database_url: str
    # NFR-6: JWT secret >= 256 bits, from env only.
    jwt_secret: SecretStr = Field(min_length=32)

    s3_endpoint_url: str | None = None
    s3_bucket: str = "insmartfix"
    s3_region: str = "us-east-1"
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None

    # Deterministic SLA tests (TEST_PLAN §3). Allow-listed to TEST_CLOCK_ENVS only (D10 H-7).
    fake_clock: bool = False

    # NFR-6 / D10 L-7: no client needs CORS (web goes through the BFF, mobile is native). Empty in
    # production; dev/mock origins come from env only. Never a wildcard.
    cors_origins: list[str] = Field(default_factory=list)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("database_url")
    @classmethod
    def _normalize_driver(cls, v: str) -> str:
        return normalize_database_url(v)

    @model_validator(mode="after")
    def _fake_clock_allow_list(self) -> "Settings":
        if self.fake_clock and self.env not in TEST_CLOCK_ENVS:
            raise ValueError(
                f"FAKE_CLOCK=1 is only allowed with ENV in {sorted(TEST_CLOCK_ENVS)}, "
                f"got ENV={self.env}"
            )
        return self

    @model_validator(mode="after")
    def _cors_locked(self) -> "Settings":
        if any("*" in o for o in self.cors_origins):
            raise ValueError("CORS_ORIGINS must list exact origins, never a wildcard")
        if self.env == "production" and self.cors_origins:
            raise ValueError("CORS_ORIGINS must be empty in production (D10 L-7)")
        return self

    @property
    def test_clock_enabled(self) -> bool:
        """D10 H-7 allow-list: both conditions, checked again at app build."""
        return self.fake_clock and self.env in TEST_CLOCK_ENVS


@lru_cache
def get_settings() -> Settings:
    return Settings()  # populated from the environment

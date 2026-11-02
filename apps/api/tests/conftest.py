import os
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_engine, get_sessionmaker
from app.main import create_app
from app.settings import Settings, get_settings

TEST_JWT_SECRET = "test-only-jwt-secret-0123456789abcdef"  # not a real secret

ClientFactory = Callable[[str], TestClient]


def make_settings(database_url: str) -> Settings:
    return Settings(database_url=database_url, jwt_secret=TEST_JWT_SECRET, env="test")


@pytest.fixture
def client_for() -> Iterator[ClientFactory]:
    """Build a TestClient whose settings point at a given DATABASE_URL."""
    created: list[TestClient] = []

    def _make(database_url: str) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: make_settings(database_url)
        c = TestClient(app)
        created.append(c)
        return c

    yield _make
    for c in created:
        c.close()
    get_sessionmaker.cache_clear()
    get_engine.cache_clear()


@pytest.fixture
def postgres_url() -> str:
    """Postgres URL for integration tests; CI sets REQUIRE_INTEGRATION=1 so they never skip."""
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith(("postgres://", "postgresql")):
        if os.environ.get("REQUIRE_INTEGRATION") == "1":
            pytest.fail("REQUIRE_INTEGRATION=1 but DATABASE_URL is not a Postgres URL")
        pytest.skip("integration test needs DATABASE_URL pointing at Postgres")
    return url

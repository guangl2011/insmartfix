import os
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI, Request
from fastapi.dependencies.models import Dependant
from fastapi.testclient import TestClient

from app.auth.deps import get_principal
from app.auth.service import Principal
from app.contract.auth import Role
from app.core.routes import iter_http_routes
from app.db.session import get_engine, get_sessionmaker
from app.identity_gate.deps import AuthorizedTarget, GateDependency
from app.identity_gate.policy import Action, AllowedAs
from app.main import create_app
from app.settings import Settings

TEST_JWT_SECRET = "test-only-jwt-secret-0123456789abcdef"  # not a real secret

ClientFactory = Callable[[str], TestClient]


SQLITE_MEMORY = "sqlite+pysqlite:///:memory:"


def make_settings(database_url: str = SQLITE_MEMORY, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": database_url,
        "jwt_secret": TEST_JWT_SECRET,
        "env": "test",
        **overrides,
    }
    return Settings(**values)


@pytest.fixture
def client_for() -> Iterator[ClientFactory]:
    """Build a TestClient whose settings point at a given DATABASE_URL."""
    created: list[TestClient] = []

    def _make(database_url: str) -> TestClient:
        c = TestClient(create_app(make_settings(database_url)))
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


FAKE_CONTRACTOR = Principal(
    user_id=UUID("00000000-0000-4000-8000-00000000f001"),
    role=Role.CONTRACTOR,
    tenant_id=UUID("00000000-0000-4000-8000-00000000f0a1"),
    contractor_id=UUID("00000000-0000-4000-8000-00000000f0c1"),
    name="Fake Contractor",
    company=None,
)


def authed_app(settings: Settings | None = None, principal: Principal = FAKE_CONTRACTOR) -> FastAPI:
    """An app where `get_principal` returns `principal` and every identity gate allows, with no
    token or database. For unit tests of handlers and contract shape only; gate behaviour is
    tested in tests/security and tests/integration."""
    app = create_app(settings or make_settings())
    app.dependency_overrides[get_principal] = lambda: principal
    for rc in iter_http_routes(app):
        dependant = getattr(rc, "dependant", None)
        for gate in _gates(dependant) if dependant is not None else ():
            app.dependency_overrides[gate] = _allow(principal, gate.action)
    return app


def _allow(principal: Principal, action: Action) -> Callable[[Request], AuthorizedTarget]:
    def allow(request: Request) -> AuthorizedTarget:
        target = AuthorizedTarget(principal, action, AllowedAs.BOUND, principal.contractor_id, None)
        request.state.authorized_target = target
        return target

    return allow


def _gates(dep: Dependant) -> Iterator[GateDependency]:
    for sub in dep.dependencies:
        if isinstance(sub.call, GateDependency):
            yield sub.call
        yield from _gates(sub)

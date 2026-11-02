"""Integration fixtures: a migrated Postgres, reached as the runtime role and as the migrator.

`DATABASE_URL` is the app's runtime role (`insmartfix_app`); `MIGRATIONS_DATABASE_URL` is the
schema owner. CI sets both (and `REQUIRE_INTEGRATION=1`, so nothing here skips there).
"""

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text

from app.settings import normalize_database_url

API_DIR = Path(__file__).resolve().parents[2]


def _require_env(name: str) -> str:
    url = os.environ.get(name, "")
    if not url.startswith(("postgres://", "postgresql")):
        if os.environ.get("REQUIRE_INTEGRATION") == "1":
            pytest.fail(f"REQUIRE_INTEGRATION=1 but {name} is not a Postgres URL")
        pytest.skip(f"integration test needs {name} pointing at Postgres")
    return normalize_database_url(url)


@pytest.fixture(scope="session")
def migrated_db() -> None:
    """Upgrade the test database to head once per session, as the migrator."""
    _require_env("DATABASE_URL")
    _require_env("MIGRATIONS_DATABASE_URL")
    command.upgrade(Config(str(API_DIR / "alembic.ini")), "head")


@pytest.fixture(scope="session")
def app_engine(migrated_db: None) -> Iterator[Engine]:
    engine = create_engine(_require_env("DATABASE_URL"))
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def migrator_engine(migrated_db: None) -> Iterator[Engine]:
    engine = create_engine(_require_env("MIGRATIONS_DATABASE_URL"))
    yield engine
    engine.dispose()


@dataclass(frozen=True)
class World:
    """One tenant with a contractor user, an owner, a site, an asset and a work order."""

    tenant_id: uuid.UUID
    contractor_id: uuid.UUID
    contractor_user_id: uuid.UUID
    owner_user_id: uuid.UUID
    site_id: uuid.UUID
    asset_id: uuid.UUID
    wo_id: uuid.UUID


def make_world(conn: Connection) -> World:
    """Insert a fresh, uniquely named world. Tests never delete: the app role can't."""
    tag = uuid.uuid4().hex[:12]

    def insert(sql: str, **params: object) -> uuid.UUID:
        value = conn.execute(text(sql), params).scalar_one()
        assert isinstance(value, uuid.UUID)
        return value

    tenant = insert("INSERT INTO tenants (name) VALUES (:n) RETURNING id", n=f"T {tag}")
    contractor = insert(
        "INSERT INTO contractors (tenant_id, name) VALUES (:t, :n) RETURNING id",
        t=tenant,
        n=f"C {tag}",
    )
    user_sql = (
        "INSERT INTO users (tenant_id, email, name, role, contractor_id) "
        "VALUES (:t, :e, :n, :r, :c) RETURNING id"
    )
    contractor_user = insert(
        user_sql, t=tenant, e=f"c-{tag}@test.example", n="C", r="contractor", c=contractor
    )
    owner = insert(user_sql, t=tenant, e=f"o-{tag}@test.example", n="O", r="owner", c=None)
    site = insert(
        "INSERT INTO sites (tenant_id, name) VALUES (:t, :n) RETURNING id", t=tenant, n="S"
    )
    asset = insert(
        "INSERT INTO assets (tenant_id, site_id, name, subtype) "
        "VALUES (:t, :s, :n, 'RTU') RETURNING id",
        t=tenant,
        s=site,
        n=f"RTU-{tag}",
    )
    wo = insert(
        "INSERT INTO workorders (tenant_id, asset_id, symptom) VALUES (:t, :a, 'x') RETURNING id",
        t=tenant,
        a=asset,
    )
    return World(tenant, contractor, contractor_user, owner, site, asset, wo)

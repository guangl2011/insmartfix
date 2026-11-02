"""`app/db/models.py` must describe exactly what the migrations create (no autogenerate drift)."""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine

from app.db.models import Base

pytestmark = pytest.mark.integration


def test_models_match_migrated_schema(migrator_engine: Engine) -> None:
    with migrator_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []

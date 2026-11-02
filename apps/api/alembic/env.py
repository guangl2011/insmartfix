"""Alembic environment.

Migrations connect with MIGRATIONS_DATABASE_URL (the schema-owner role) when set, else DATABASE_URL.
The API itself uses DATABASE_URL, which from M1-T2 on points at the least-privilege app role
(D10 H-5: grants are bypassed by the table owner, so the app must never run as the owner).
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.settings import normalize_database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Normalised the same way the app does (postgres:// -> postgresql+psycopg://).
_url = os.environ.get("MIGRATIONS_DATABASE_URL") or os.environ["DATABASE_URL"]
config.set_main_option("sqlalchemy.url", normalize_database_url(_url))

target_metadata = None  # M1 points this at app.models.Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

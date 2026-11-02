"""Database engine, sessions and readiness probe (SQLAlchemy 2).

The app connects with `DATABASE_URL`, which must be the least-privilege runtime role
`insmartfix_app` (or a member of it), never the schema owner (D10 H-5, `app/db/roles.py`).
"""

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.settings import Settings, get_settings


@lru_cache(maxsize=4)
def get_engine(database_url: str) -> Engine:
    connect_args: dict[str, object] = {}
    if database_url.startswith("postgresql"):
        connect_args["connect_timeout"] = 3
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


@lru_cache(maxsize=4)
def get_sessionmaker(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(get_engine(database_url), expire_on_commit=False)


def get_db(settings: Annotated[Settings, Depends(get_settings)]) -> Iterator[Session]:
    """FastAPI dependency: one session per request; the handler commits, errors roll back."""
    with get_sessionmaker(settings.database_url)() as session:
        yield session


def ping(engine: Engine) -> None:
    """Raise if the database is unreachable."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

"""Database engine and readiness probe (SQLAlchemy 2)."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine, text


@lru_cache(maxsize=4)
def get_engine(database_url: str) -> Engine:
    connect_args: dict[str, object] = {}
    if database_url.startswith("postgresql"):
        connect_args["connect_timeout"] = 3
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


def ping(engine: Engine) -> None:
    """Raise if the database is unreachable."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

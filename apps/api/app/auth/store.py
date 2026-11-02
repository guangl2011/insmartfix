"""Postgres-backed auth adapters: users (`UserRepo`) and the shared rate-limit store."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import Engine, select, text, update
from sqlalchemy.orm import Session

from app.auth.ratelimit import Bucket
from app.auth.service import UserRecord
from app.db.models import Contractor, User

RETENTION = timedelta(hours=1)  # the longest rate-limit window


class SqlUserRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _one(self, *where: object) -> UserRecord | None:
        row = self.session.execute(
            select(User, Contractor.company)
            .outerjoin(Contractor, Contractor.id == User.contractor_id)
            .where(*where)  # type: ignore[arg-type]
        ).first()
        if row is None:
            return None
        u, company = row
        return UserRecord(
            id=u.id,
            tenant_id=u.tenant_id,
            email=u.email,
            name=u.name,
            password_hash=u.password_hash,
            role=u.role,
            contractor_id=u.contractor_id,
            token_version=u.token_version,
            disabled_at=u.disabled_at,
            company=company,
        )

    def by_email(self, normalized_email: str) -> UserRecord | None:
        return self._one(User.email == normalized_email)

    def by_id(self, user_id: UUID) -> UserRecord | None:
        return self._one(User.id == user_id)

    def bump_token_version(self, user_id: UUID) -> None:
        self.session.execute(
            update(User).where(User.id == user_id).values(token_version=User.token_version + 1)
        )
        self.session.commit()


class PgAttemptStore:
    """Shared across workers and instances. Each bucket is serialised with a transaction-scoped
    advisory lock (taken in sorted order, so concurrent logins can't deadlock), then counted."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def try_record(self, buckets: Sequence[Bucket], now: datetime) -> bool:
        with self.engine.begin() as conn:
            for key in sorted({b.key for b in buckets}):
                conn.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": key}
                )
            for b in buckets:
                count = conn.execute(
                    text("SELECT count(*) FROM auth_attempts WHERE bucket = :k AND at > :since"),
                    {"k": b.key, "since": now - b.limit.window},
                ).scalar_one()
                if count >= b.limit.limit:
                    return False
            conn.execute(
                text("DELETE FROM auth_attempts WHERE bucket = ANY(:ks) AND at < :old"),
                {"ks": [b.key for b in buckets], "old": now - RETENTION},
            )
            conn.execute(
                text("INSERT INTO auth_attempts (bucket, at) VALUES (:k, :at)"),
                [{"k": b.key, "at": now} for b in buckets],
            )
        return True

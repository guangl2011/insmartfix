"""Shared login rate-limit store (M1-T4; NFR-6; D10 M-7).

Revision ID: 0002_auth_attempts
Revises: 0001_core
Create Date: 2026-11-02

One row per counted login attempt. `bucket` is a SHA-256 digest of the limit name plus the
normalised email and/or client IP, so no email or IP is stored in clear. Rows are disposable:
the app deletes rows older than the longest window (1 h).
"""

from collections.abc import Sequence

from alembic import op

from app.db.roles import grant_runtime_sql

revision: str = "0002_auth_attempts"
down_revision: str | None = "0001_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE auth_attempts (
            bucket  char(64) NOT NULL,
            at      timestamptz NOT NULL
        );
        CREATE INDEX ix_auth_attempts_bucket_at ON auth_attempts (bucket, at);
        """
    )
    # Counted and pruned, never updated.
    op.execute(grant_runtime_sql("auth_attempts", "SELECT, INSERT, DELETE"))


def downgrade() -> None:
    op.execute("DROP TABLE auth_attempts;")

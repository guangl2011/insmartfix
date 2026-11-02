"""Seeded decision packets for the stub Decision Engine (M2-T1; spec §4.3, FR-3.2-3.4).

Revision ID: 0003_decision_packets
Revises: 0002_auth_attempts
Create Date: 2026-11-02

One row per asset that has history. No row means `pre_diagnostic_available = false` (FR-3.4).
"""

from collections.abc import Sequence

from alembic import op

from app.db.roles import MUTABLE_PRIVILEGES, grant_runtime_sql

revision: str = "0003_decision_packets"
down_revision: str | None = "0002_auth_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE decision_packets (
            asset_id                uuid PRIMARY KEY,
            tenant_id               uuid NOT NULL,
            predicted_failure_code  varchar(64),
            likely_cause            varchar(200),
            confidence              numeric(4, 3) CHECK (confidence BETWEEN 0 AND 1),
            decision                jsonb NOT NULL,
            packet                  jsonb NOT NULL,
            updated_at              timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_decision_packets_asset FOREIGN KEY (tenant_id, asset_id)
                REFERENCES assets (tenant_id, id),
            CONSTRAINT ck_decision_packets_objects
                CHECK (jsonb_typeof(decision) = 'object' AND jsonb_typeof(packet) = 'object')
        );
        """
    )
    op.execute(grant_runtime_sql("decision_packets", MUTABLE_PRIVILEGES))


def downgrade() -> None:
    op.execute("DROP TABLE decision_packets;")

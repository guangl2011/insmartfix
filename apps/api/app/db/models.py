"""SQLAlchemy 2 models for the spec §4.4 data model.

The schema itself is owned by `alembic/versions/0001_core.py` (constraints, triggers, grants); these
models mirror its tables and keys for the ORM and are checked against the migrated database by
`tests/integration/test_models_match_migrations.py`. CHECK constraints and triggers live only in
the migration.

All externally visible ids are UUIDv4 (D10 L-1).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

GEN_UUID = text("gen_random_uuid()")
NOW = text("now()")


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4, server_default=GEN_UUID)


def _tstz(*, nullable: bool = False, server_now: bool = False) -> Mapped[Any]:
    return mapped_column(
        DateTime(timezone=True), nullable=nullable, server_default=NOW if server_now else None
    )


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = _tstz(server_now=True)


class Contractor(Base):
    __tablename__ = "contractors"
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_contractors_tenant_id"),)
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(200))
    company: Mapped[str | None] = mapped_column(String(200))
    avg_rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    created_at: Mapped[datetime] = _tstz(server_now=True)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        ForeignKeyConstraint(
            ["tenant_id", "contractor_id"],
            ["contractors.tenant_id", "contractors.id"],
            name="fk_users_contractor",
        ),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    email: Mapped[str] = mapped_column(String(254))
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20))  # contractor | owner | fm
    contractor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    disabled_at: Mapped[datetime | None] = _tstz(nullable=True)
    created_at: Mapped[datetime] = _tstz(server_now=True)


class Site(Base):
    __tablename__ = "sites"
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_sites_tenant_id"),)
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(300))


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_assets_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "site_id"], ["sites.tenant_id", "sites.id"], name="fk_assets_site"
        ),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    site_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    name: Mapped[str] = mapped_column(String(200))
    subtype: Mapped[str] = mapped_column(String(64))
    make: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    install_year: Mapped[int | None] = mapped_column(Integer)
    location: Mapped[str | None] = mapped_column(String(300))
    duty: Mapped[str | None] = mapped_column(String(120))


class FailureCode(Base):
    __tablename__ = "failure_codes"
    __table_args__ = (PrimaryKeyConstraint("subtype", "code", name="failure_codes_pkey"),)
    subtype: Mapped[str] = mapped_column(String(64))
    code: Mapped[str] = mapped_column(String(64))
    component_group: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))


class WorkOrder(Base):
    __tablename__ = "workorders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_workorders_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "asset_id"], ["assets.tenant_id", "assets.id"], name="fk_workorders_asset"
        ),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    symptom: Mapped[str] = mapped_column(String(500))
    wo_source: Mapped[str] = mapped_column(
        String(20), default="dispatch", server_default=text("'dispatch'")
    )
    status: Mapped[str] = mapped_column(String(20), default="OPEN", server_default=text("'OPEN'"))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    predicted_failure_code: Mapped[str | None] = mapped_column(String(64))
    completed_at: Mapped[datetime | None] = _tstz(nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _tstz(server_now=True)


class DispatchCandidate(Base):
    __tablename__ = "dispatch_candidates"
    __table_args__ = (
        PrimaryKeyConstraint("wo_id", "contractor_id", name="dispatch_candidates_pkey"),
        UniqueConstraint("wo_id", "rank", name="uq_dispatch_candidates_rank"),
        ForeignKeyConstraint(
            ["tenant_id", "wo_id"],
            ["workorders.tenant_id", "workorders.id"],
            name="fk_dispatch_candidates_wo",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "contractor_id"],
            ["contractors.tenant_id", "contractors.id"],
            name="fk_dispatch_candidates_contractor",
        ),
    )
    wo_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    contractor_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    rank: Mapped[int] = mapped_column(Integer)
    match_score: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    match_reason: Mapped[str] = mapped_column(String(200))
    # QUEUED | OFFERED | ACCEPTED | DECLINED | EXPIRED | WITHDRAWN
    state: Mapped[str] = mapped_column(
        String(20), default="QUEUED", server_default=text("'QUEUED'")
    )
    offered_at: Mapped[datetime | None] = _tstz(nullable=True)
    sla_deadline: Mapped[datetime | None] = _tstz(nullable=True)
    responded_at: Mapped[datetime | None] = _tstz(nullable=True)
    decline_reason: Mapped[str | None] = mapped_column(String(20))
    decline_note: Mapped[str | None] = mapped_column(String(500))


class Dispatch(Base):
    __tablename__ = "dispatch"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "wo_id"], ["workorders.tenant_id", "workorders.id"], name="fk_dispatch_wo"
        ),
        ForeignKeyConstraint(
            ["wo_id", "current_contractor_id"],
            ["dispatch_candidates.wo_id", "dispatch_candidates.contractor_id"],
            name="fk_dispatch_current_candidate",
        ),
    )
    wo_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # UNDISPATCHED | PENDING | ACCEPTED | IN_PROGRESS | COMPLETED | ESCALATED | NO_CONTRACTORS
    state: Mapped[str] = mapped_column(
        String(20), default="UNDISPATCHED", server_default=text("'UNDISPATCHED'")
    )
    current_contractor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    sla_minutes: Mapped[int] = mapped_column(Integer)
    sla_deadline: Mapped[datetime | None] = _tstz(nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    decline_reason: Mapped[str | None] = mapped_column(String(20))
    decline_note: Mapped[str | None] = mapped_column(String(500))
    updated_at: Mapped[datetime] = _tstz(server_now=True)


class MemoryEvent(Base):
    """Append-only (FR-6.1). Write only through `memory.MemorySeam.append()` (plan rule 3)."""

    __tablename__ = "memory_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "wo_id"],
            ["workorders.tenant_id", "workorders.id"],
            name="fk_memory_events_wo",
        ),
        UniqueConstraint("wo_id", "id", name="uq_memory_events_wo_id"),
        ForeignKeyConstraint(
            ["wo_id", "corrects_event_id"],
            ["memory_events.wo_id", "memory_events.id"],
            name="fk_memory_events_corrects",
        ),
        UniqueConstraint(
            "actor_user_id", "idempotency_key", name="uq_memory_events_actor_idempotency"
        ),
        Index(
            "uq_memory_events_corrects_once",
            "corrects_event_id",
            unique=True,
            postgresql_where=text("corrects_event_id IS NOT NULL"),
        ),
        Index("ix_memory_events_wo_at", "wo_id", "at"),
        Index("ix_memory_events_asset_at", "asset_id", "at"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"))
    wo_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    type: Mapped[str] = mapped_column(String(20))  # ADVANCE | CORRECTION | OUTCOME
    stage: Mapped[str | None] = mapped_column(String(20))  # EN_ROUTE | ARRIVED, on ADVANCE
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    at: Mapped[datetime] = _tstz()
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    corrects_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = _tstz(server_now=True)


class CompletionReport(Base):
    """Append-only (FR-7.4): one row per work order, never updated."""

    __tablename__ = "completion_reports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "wo_id"],
            ["workorders.tenant_id", "workorders.id"],
            name="fk_completion_reports_wo",
        ),
    )
    wo_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    failure_code: Mapped[str] = mapped_column(String(64))
    actual_fault_matched: Mapped[bool] = mapped_column(Boolean)
    parts_used: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    labor_hours: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    notes: Mapped[str | None] = mapped_column(String(4000))
    technician_id: Mapped[str] = mapped_column(String(120))
    photo_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid), default=list, server_default=text("'{}'")
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    submitted_at: Mapped[datetime] = _tstz()


class CalibrationRecord(Base):
    """Append-only (FR-7.5). `label` is computed by the server only (D10 M-8)."""

    __tablename__ = "calibration_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "wo_id"],
            ["workorders.tenant_id", "workorders.id"],
            name="fk_calibration_records_wo",
        ),
    )
    wo_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"))
    predicted_code: Mapped[str | None] = mapped_column(String(64))
    actual_code: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(20))  # MATCH | PARTIAL | MISS | NO_PREDICTION
    actual_fault_matched: Mapped[bool] = mapped_column(Boolean)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _tstz()


class Photo(Base):
    __tablename__ = "photos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "wo_id"], ["workorders.tenant_id", "workorders.id"], name="fk_photos_wo"
        ),
        UniqueConstraint("key", name="uq_photos_key"),
        Index("ix_photos_wo", "wo_id"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    wo_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    key: Mapped[str] = mapped_column(String(200))  # wo/{wo_id}/{id}
    content_type: Mapped[str] = mapped_column(String(40))
    bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(CHAR(64))
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _tstz()


class IdempotencyRecord(Base):
    """D10 H-3: keyed by (principal, scope = route template + target, key)."""

    __tablename__ = "idempotency_records"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "scope", "key", name="idempotency_records_pkey"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    scope: Mapped[str] = mapped_column(String(200))
    key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(CHAR(64))
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _tstz(server_now=True)


class AuthAttempt(Base):
    """Login rate-limit counter rows (D10 M-7). Disposable; no primary key in the schema."""

    __tablename__ = "auth_attempts"
    __table_args__ = (Index("ix_auth_attempts_bucket_at", "bucket", "at"),)
    # The ORM needs an identity; the table itself has no PK (rows are never addressed one by one).
    bucket: Mapped[str] = mapped_column(CHAR(64), primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)


class DecisionPacket(Base):
    """Seeded packet for the stub Decision Engine (M2-T1). No row = no pre-diagnostic packet."""

    __tablename__ = "decision_packets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "asset_id"],
            ["assets.tenant_id", "assets.id"],
            name="fk_decision_packets_asset",
        ),
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    predicted_failure_code: Mapped[str | None] = mapped_column(String(64))
    likely_cause: Mapped[str | None] = mapped_column(String(200))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    decision: Mapped[dict[str, Any]] = mapped_column(JSONB)
    packet: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = _tstz(server_now=True)

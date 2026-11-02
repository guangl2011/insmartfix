"""Core data model, runtime DB role and append-only grants (M1-T2; spec §4.4; D10 H-3/H-4/H-5).

Revision ID: 0001_core
Revises:
Create Date: 2026-11-02

Hand-written DDL so every constraint, grant and trigger is explicit and reviewable.
`tests/integration/test_models_match_migrations.py` keeps `app/db/models.py` in step with it.

Ids are UUIDv4 (`gen_random_uuid()`, D10 L-1). Cross-table tenant consistency is enforced with
composite `(tenant_id, id)` foreign keys, so a row can never point at another tenant's row (H-6).
"""

from collections.abc import Sequence

from alembic import op

from app.db.roles import (
    APP_ROLE,
    APPEND_ONLY_PRIVILEGES,
    APPEND_ONLY_TABLES,
    DISPOSABLE_PRIVILEGES,
    MUTABLE_PRIVILEGES,
    ensure_app_role_sql,
    grant_runtime_sql,
)

revision: str = "0001_core"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = """
CREATE TABLE tenants (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        varchar(200) NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE contractors (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenants (id),
    name        varchar(200) NOT NULL,
    company     varchar(200),
    avg_rating  numeric(3, 2) CHECK (avg_rating BETWEEN 0 AND 5),
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_contractors_tenant_id UNIQUE (tenant_id, id)
);

CREATE TABLE users (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      uuid NOT NULL REFERENCES tenants (id),
    email          varchar(254) NOT NULL,
    name           varchar(200) NOT NULL,
    password_hash  text,
    role           varchar(20) NOT NULL,
    contractor_id  uuid,
    token_version  integer NOT NULL DEFAULT 0 CHECK (token_version >= 0),
    disabled_at    timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT ck_users_email_normalized CHECK (email = lower(btrim(email))),
    CONSTRAINT ck_users_role CHECK (role IN ('contractor', 'owner', 'fm')),
    -- FR-1.4: a contractor principal carries exactly one contractor_id; owner/FM carry none.
    CONSTRAINT ck_users_contractor_id CHECK ((role = 'contractor') = (contractor_id IS NOT NULL)),
    CONSTRAINT fk_users_contractor FOREIGN KEY (tenant_id, contractor_id)
        REFERENCES contractors (tenant_id, id)
);

CREATE TABLE sites (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenants (id),
    name        varchar(200) NOT NULL,
    location    varchar(300),
    CONSTRAINT uq_sites_tenant_id UNIQUE (tenant_id, id)
);

CREATE TABLE assets (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     uuid NOT NULL,
    site_id       uuid NOT NULL,
    name          varchar(200) NOT NULL,
    subtype       varchar(64) NOT NULL,
    make          varchar(120),
    model         varchar(120),
    install_year  integer CHECK (install_year BETWEEN 1900 AND 2200),
    location      varchar(300),
    duty          varchar(120),
    CONSTRAINT uq_assets_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT fk_assets_site FOREIGN KEY (tenant_id, site_id) REFERENCES sites (tenant_id, id)
);

CREATE TABLE failure_codes (
    subtype          varchar(64) NOT NULL,
    code             varchar(64) NOT NULL,
    component_group  varchar(64) NOT NULL,
    label            varchar(200) NOT NULL,
    sort_order       integer NOT NULL DEFAULT 0,
    PRIMARY KEY (subtype, code)
);

CREATE TABLE workorders (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               uuid NOT NULL,
    asset_id                uuid NOT NULL,
    symptom                 varchar(500) NOT NULL,
    wo_source               varchar(20) NOT NULL DEFAULT 'dispatch',
    status                  varchar(20) NOT NULL DEFAULT 'OPEN',
    -- FR-7.4: set once, by the completing contractor's choice only (trigger below).
    failure_code            varchar(64),
    -- D10 L-4: the prediction the contractor saw, snapshotted at dispatch create and accept.
    predicted_failure_code  varchar(64),
    completed_at            timestamptz,
    created_by_user_id      uuid REFERENCES users (id),
    created_at              timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_workorders_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT fk_workorders_asset FOREIGN KEY (tenant_id, asset_id)
        REFERENCES assets (tenant_id, id),
    CONSTRAINT ck_workorders_wo_source CHECK (wo_source IN ('dispatch', 'voice')),
    CONSTRAINT ck_workorders_status CHECK (status IN ('OPEN', 'IN_PROGRESS', 'COMPLETED')),
    CONSTRAINT ck_workorders_completed
        CHECK ((status = 'COMPLETED') = (completed_at IS NOT NULL))
);

CREATE TABLE dispatch_candidates (
    wo_id           uuid NOT NULL,
    contractor_id   uuid NOT NULL,
    tenant_id       uuid NOT NULL,
    rank            integer NOT NULL CHECK (rank >= 1),
    match_score     numeric(4, 3) NOT NULL CHECK (match_score BETWEEN 0 AND 1),
    match_reason    varchar(200) NOT NULL,
    state           varchar(20) NOT NULL DEFAULT 'QUEUED',
    offered_at      timestamptz,
    sla_deadline    timestamptz,
    responded_at    timestamptz,
    decline_reason  varchar(20),
    decline_note    varchar(500),
    PRIMARY KEY (wo_id, contractor_id),
    CONSTRAINT uq_dispatch_candidates_rank UNIQUE (wo_id, rank),
    -- H-6: a candidate is always in the work order's tenant.
    CONSTRAINT fk_dispatch_candidates_wo FOREIGN KEY (tenant_id, wo_id)
        REFERENCES workorders (tenant_id, id),
    CONSTRAINT fk_dispatch_candidates_contractor FOREIGN KEY (tenant_id, contractor_id)
        REFERENCES contractors (tenant_id, id),
    CONSTRAINT ck_dispatch_candidates_state
        CHECK (state IN ('QUEUED', 'OFFERED', 'ACCEPTED', 'DECLINED', 'EXPIRED', 'WITHDRAWN')),
    CONSTRAINT ck_dispatch_candidates_offered
        CHECK (state = 'QUEUED' OR (offered_at IS NOT NULL AND sla_deadline IS NOT NULL)),
    CONSTRAINT ck_dispatch_candidates_decline_reason
        CHECK (decline_reason IN ('too_far', 'no_capacity', 'wrong_skill', 'other'))
);

CREATE TABLE dispatch (
    wo_id                  uuid PRIMARY KEY,
    tenant_id              uuid NOT NULL,
    state                  varchar(20) NOT NULL DEFAULT 'UNDISPATCHED',
    current_contractor_id  uuid,
    sla_minutes            integer NOT NULL CHECK (sla_minutes BETWEEN 1 AND 1440),
    sla_deadline           timestamptz,
    -- FR-5.3: optimistic-locking compare-and-set counter.
    version                integer NOT NULL DEFAULT 0 CHECK (version >= 0),
    decline_reason         varchar(20),
    decline_note           varchar(500),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_dispatch_wo FOREIGN KEY (tenant_id, wo_id) REFERENCES workorders (tenant_id, id),
    -- The current contractor is always one of this work order's candidates.
    CONSTRAINT fk_dispatch_current_candidate FOREIGN KEY (wo_id, current_contractor_id)
        REFERENCES dispatch_candidates (wo_id, contractor_id),
    CONSTRAINT ck_dispatch_state CHECK (state IN (
        'UNDISPATCHED', 'PENDING', 'ACCEPTED', 'IN_PROGRESS', 'COMPLETED',
        'ESCALATED', 'NO_CONTRACTORS'
    )),
    CONSTRAINT ck_dispatch_bound CHECK (
        state NOT IN ('PENDING', 'ACCEPTED', 'IN_PROGRESS', 'COMPLETED')
        OR current_contractor_id IS NOT NULL
    ),
    CONSTRAINT ck_dispatch_pending_deadline CHECK (state <> 'PENDING' OR sla_deadline IS NOT NULL),
    CONSTRAINT ck_dispatch_decline_reason
        CHECK (decline_reason IN ('too_far', 'no_capacity', 'wrong_skill', 'other'))
);

CREATE TABLE memory_events (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          uuid NOT NULL,
    asset_id           uuid NOT NULL REFERENCES assets (id),
    wo_id              uuid NOT NULL,
    type               varchar(20) NOT NULL,
    stage              varchar(20),
    payload            jsonb NOT NULL DEFAULT '{}'::jsonb,
    actor_user_id      uuid NOT NULL REFERENCES users (id),
    at                 timestamptz NOT NULL,
    idempotency_key    varchar(255),
    corrects_event_id  uuid,
    created_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_memory_events_wo FOREIGN KEY (tenant_id, wo_id)
        REFERENCES workorders (tenant_id, id),
    -- Target of the same-WO correction FK below.
    CONSTRAINT uq_memory_events_wo_id UNIQUE (wo_id, id),
    -- H-4(a): a correction can only reference an event on the same work order.
    CONSTRAINT fk_memory_events_corrects FOREIGN KEY (wo_id, corrects_event_id)
        REFERENCES memory_events (wo_id, id),
    -- H-3 / C-2: idempotency keys are unique per actor, never globally.
    CONSTRAINT uq_memory_events_actor_idempotency UNIQUE (actor_user_id, idempotency_key),
    CONSTRAINT ck_memory_events_type CHECK (type IN ('ADVANCE', 'CORRECTION', 'OUTCOME')),
    CONSTRAINT ck_memory_events_stage CHECK (stage IN ('EN_ROUTE', 'ARRIVED')),
    CONSTRAINT ck_memory_events_advance_stage CHECK ((type = 'ADVANCE') = (stage IS NOT NULL)),
    -- H-4: exactly the CORRECTION events reference another event.
    CONSTRAINT ck_memory_events_correction
        CHECK ((type = 'CORRECTION') = (corrects_event_id IS NOT NULL)),
    CONSTRAINT ck_memory_events_not_self CHECK (corrects_event_id <> id)
);
-- H-4(b): an event is corrected at most once, even under concurrent undos.
CREATE UNIQUE INDEX uq_memory_events_corrects_once
    ON memory_events (corrects_event_id) WHERE corrects_event_id IS NOT NULL;
CREATE INDEX ix_memory_events_wo_at ON memory_events (wo_id, at);
CREATE INDEX ix_memory_events_asset_at ON memory_events (asset_id, at);

CREATE TABLE completion_reports (
    wo_id                 uuid PRIMARY KEY,
    tenant_id             uuid NOT NULL,
    actor_user_id         uuid NOT NULL REFERENCES users (id),
    failure_code          varchar(64) NOT NULL,
    actual_fault_matched  boolean NOT NULL,
    parts_used            jsonb NOT NULL DEFAULT '[]'::jsonb,
    labor_hours           numeric(4, 2) NOT NULL,
    notes                 varchar(4000),
    technician_id         varchar(120) NOT NULL,
    photo_ids             uuid[] NOT NULL DEFAULT '{}',
    idempotency_key       varchar(255),
    submitted_at          timestamptz NOT NULL,
    CONSTRAINT fk_completion_reports_wo FOREIGN KEY (tenant_id, wo_id)
        REFERENCES workorders (tenant_id, id),
    -- FR-7.1 bounds, as a backstop to request validation.
    CONSTRAINT ck_completion_reports_labor_hours
        CHECK (labor_hours > 0 AND labor_hours <= 24 AND mod(labor_hours * 4, 1) = 0),
    CONSTRAINT ck_completion_reports_photo_count CHECK (cardinality(photo_ids) <= 4),
    CONSTRAINT ck_completion_reports_parts_array CHECK (jsonb_typeof(parts_used) = 'array')
);

CREATE TABLE calibration_records (
    wo_id                 uuid PRIMARY KEY,
    tenant_id             uuid NOT NULL,
    asset_id              uuid NOT NULL REFERENCES assets (id),
    predicted_code        varchar(64),
    actual_code           varchar(64) NOT NULL,
    label                 varchar(20) NOT NULL,
    actual_fault_matched  boolean NOT NULL,
    actor_user_id         uuid NOT NULL REFERENCES users (id),
    created_at            timestamptz NOT NULL,
    CONSTRAINT fk_calibration_records_wo FOREIGN KEY (tenant_id, wo_id)
        REFERENCES workorders (tenant_id, id),
    CONSTRAINT ck_calibration_records_label
        CHECK (label IN ('MATCH', 'PARTIAL', 'MISS', 'NO_PREDICTION')),
    CONSTRAINT ck_calibration_records_no_prediction
        CHECK ((label = 'NO_PREDICTION') = (predicted_code IS NULL))
);

CREATE TABLE photos (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            uuid NOT NULL,
    wo_id                uuid NOT NULL,
    key                  varchar(200) NOT NULL,
    content_type         varchar(40) NOT NULL,
    bytes                integer NOT NULL CHECK (bytes > 0 AND bytes <= 10485760),
    sha256               char(64) NOT NULL,
    uploaded_by_user_id  uuid NOT NULL REFERENCES users (id),
    created_at           timestamptz NOT NULL,
    CONSTRAINT fk_photos_wo FOREIGN KEY (tenant_id, wo_id) REFERENCES workorders (tenant_id, id),
    CONSTRAINT uq_photos_key UNIQUE (key),
    -- D10 M-9: the object key is server-generated, never derived from the client filename.
    CONSTRAINT ck_photos_key CHECK (key = 'wo/' || wo_id::text || '/' || id::text),
    CONSTRAINT ck_photos_content_type CHECK (content_type IN ('image/jpeg', 'image/png'))
);
CREATE INDEX ix_photos_wo ON photos (wo_id);

-- D10 H-3: idempotency is scoped by (principal, route template + target, key).
CREATE TABLE idempotency_records (
    user_id          uuid NOT NULL REFERENCES users (id),
    scope            varchar(200) NOT NULL,
    key              varchar(255) NOT NULL,
    request_hash     char(64) NOT NULL,
    response_status  integer,
    response_ref     jsonb,
    created_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, scope, key)
);

-- D10 H-5 / FR-7.4: failure_code is set once. Triggers bind every role, including the owner.
CREATE FUNCTION workorders_failure_code_set_once() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.failure_code IS NOT NULL AND NEW.failure_code IS DISTINCT FROM OLD.failure_code THEN
        RAISE EXCEPTION 'workorders.failure_code is set once (wo %)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER trg_workorders_failure_code_set_once
    BEFORE UPDATE OF failure_code ON workorders
    FOR EACH ROW EXECUTE FUNCTION workorders_failure_code_set_once();

-- D10 H-4: only a lifecycle ADVANCE can be corrected (never a CORRECTION or an OUTCOME).
CREATE FUNCTION memory_events_correction_target() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.corrects_event_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM memory_events
        WHERE id = NEW.corrects_event_id AND wo_id = NEW.wo_id AND type = 'ADVANCE'
    ) THEN
        RAISE EXCEPTION 'a CORRECTION must reference an ADVANCE on the same work order'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER trg_memory_events_correction_target
    BEFORE INSERT ON memory_events
    FOR EACH ROW EXECUTE FUNCTION memory_events_correction_target();
"""

APPEND_ONLY = APPEND_ONLY_TABLES
MUTABLE = (
    "tenants",
    "contractors",
    "sites",
    "assets",
    "failure_codes",
    "workorders",
    "dispatch_candidates",
    "dispatch",
    "photos",
)
DISPOSABLE = ("idempotency_records",)
USERS_UPDATABLE = "name, password_hash, token_version, disabled_at"

def upgrade() -> None:
    op.execute(ensure_app_role_sql())
    op.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC;")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE};")
    op.execute(SCHEMA)
    for fn in ("workorders_failure_code_set_once", "memory_events_correction_target"):
        op.execute(f"REVOKE ALL ON FUNCTION {fn}() FROM PUBLIC;")
    for table in APPEND_ONLY:
        op.execute(grant_runtime_sql(table, APPEND_ONLY_PRIVILEGES))
    for table in MUTABLE:
        op.execute(grant_runtime_sql(table, MUTABLE_PRIVILEGES))
    for table in DISPOSABLE:
        op.execute(grant_runtime_sql(table, DISPOSABLE_PRIVILEGES))
    # Identity columns (role, tenant, contractor binding, email) are never rewritten by the app, so
    # a SQL-injection or ORM bug can't escalate a principal. Auth only bumps these (M-5, D11).
    op.execute(grant_runtime_sql("users", "SELECT, INSERT"))
    op.execute(f"GRANT UPDATE ({USERS_UPDATABLE}) ON TABLE users TO {APP_ROLE};")


def downgrade() -> None:
    # Reverse dependency order. The role is cluster-wide and may serve other databases: kept.
    op.execute(
        """
        DROP TABLE idempotency_records, photos, calibration_records, completion_reports,
            memory_events, dispatch, dispatch_candidates, workorders, failure_codes, assets,
            sites, users, contractors, tenants;
        DROP FUNCTION workorders_failure_code_set_once();
        DROP FUNCTION memory_events_correction_target();
        """
    )
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE};")

"""T-MEM-1, T-MEM-2: append-only memory and write-once tables, enforced by the database (D10 H-5).

Every assertion is made against the role the app's engine actually connects as (`current_user`
over `DATABASE_URL`), not a role created for the test, so the test fails if the app runs as the
schema owner.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from app.db.roles import APP_ROLE, APPEND_ONLY_TABLES
from tests.integration.conftest import World, make_world

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


@pytest.fixture
def app_conn(app_engine: Engine) -> Iterator[Connection]:
    with app_engine.connect() as conn:
        yield conn
        conn.rollback()


@pytest.fixture
def world(app_engine: Engine) -> World:
    with app_engine.begin() as conn:
        return make_world(conn)


def _event(
    conn: Connection,
    w: World,
    *,
    type_: str = "ADVANCE",
    stage: str | None = "EN_ROUTE",
    key: str | None = None,
    corrects: uuid.UUID | None = None,
    wo_id: uuid.UUID | None = None,
    actor: uuid.UUID | None = None,
) -> uuid.UUID:
    value = conn.execute(
        text(
            "INSERT INTO memory_events (tenant_id, asset_id, wo_id, type, stage, actor_user_id, "
            "at, idempotency_key, corrects_event_id) "
            "VALUES (:t, :a, :wo, :ty, :st, :actor, :at, :k, :c) RETURNING id"
        ),
        {
            "t": w.tenant_id,
            "a": w.asset_id,
            "wo": wo_id or w.wo_id,
            "ty": type_,
            "st": stage,
            "actor": actor or w.contractor_user_id,
            "at": NOW,
            "k": key,
            "c": corrects,
        },
    ).scalar_one()
    assert isinstance(value, uuid.UUID)
    return value


def _committed_event(engine: Engine, w: World) -> uuid.UUID:
    with engine.begin() as conn:
        return _event(conn, w)


# --- T-MEM-1 ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE memory_events SET payload = '{\"x\": 1}'::jsonb WHERE id = :id",
        "UPDATE memory_events SET stage = 'ARRIVED' WHERE id = :id",
        "DELETE FROM memory_events WHERE id = :id",
        "TRUNCATE memory_events",
    ],
)
def test_T_MEM_1_app_role_cannot_update_or_delete_memory_events(
    app_engine: Engine, world: World, statement: str
) -> None:
    event_id = _committed_event(app_engine, world)
    with app_engine.connect() as conn, pytest.raises(ProgrammingError, match="permission denied"):
        conn.execute(text(statement), {"id": event_id})
    with app_engine.connect() as conn:
        row = conn.execute(
            text("SELECT stage, payload FROM memory_events WHERE id = :id"), {"id": event_id}
        ).one()
    assert (row.stage, row.payload) == ("EN_ROUTE", {})


def test_T_MEM_1_app_role_can_append_and_read(app_conn: Connection, world: World) -> None:
    event_id = _event(app_conn, world, key="k-1")
    assert (
        app_conn.execute(
            text("SELECT count(*) FROM memory_events WHERE id = :id"), {"id": event_id}
        ).scalar_one()
        == 1
    )


# --- T-MEM-2: role shape ---------------------------------------------------------------------


def test_T_MEM_2_runtime_role_is_not_superuser_or_owner(app_conn: Connection) -> None:
    me = app_conn.execute(
        text(
            "SELECT current_user AS name, r.rolsuper, r.rolcreaterole, r.rolcreatedb, "
            "r.rolbypassrls FROM pg_roles r WHERE r.rolname = current_user"
        )
    ).one()
    assert not me.rolsuper
    assert not me.rolcreaterole
    assert not me.rolcreatedb
    assert not me.rolbypassrls
    # The app connects as insmartfix_app itself or as a login role that is a member of it.
    assert app_conn.execute(
        text("SELECT pg_has_role(current_user, :r, 'MEMBER')"), {"r": APP_ROLE}
    ).scalar_one()

    owned = app_conn.execute(
        text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND pg_has_role(current_user, c.relowner, 'USAGE')"
        )
    ).scalars()
    assert list(owned) == [], "runtime role owns (or inherits ownership of) tables"
    owns_functions = app_conn.execute(
        text(
            "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND pg_has_role(current_user, p.proowner, 'USAGE')"
        )
    ).scalars()
    assert list(owns_functions) == []


@pytest.mark.parametrize("table", APPEND_ONLY_TABLES)
def test_T_MEM_2_append_only_tables_grant_insert_select_only(
    app_conn: Connection, table: str
) -> None:
    def has(privilege: str) -> bool:
        result = app_conn.execute(
            text("SELECT has_table_privilege(current_user, :t, :p)"),
            {"t": table, "p": privilege},
        ).scalar_one()
        assert isinstance(result, bool)
        return result

    assert has("SELECT")
    assert has("INSERT")
    for privilege in ("UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
        assert not has(privilege), f"{privilege} on {table}"
    # No column-level UPDATE grant sneaking around the table-level one either.
    assert not app_conn.execute(
        text("SELECT has_any_column_privilege(current_user, :t, 'UPDATE')"), {"t": table}
    ).scalar_one()


def test_T_MEM_2_runtime_role_cannot_ddl(app_conn: Connection) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        app_conn.execute(text("CREATE TABLE t_mem_2_probe (id int)"))


def test_T_MEM_2_runtime_role_has_no_delete_or_truncate_anywhere(app_conn: Connection) -> None:
    rows = app_conn.execute(
        text(
            "SELECT c.relname, p.priv FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "CROSS JOIN (VALUES ('DELETE'), ('TRUNCATE')) AS p(priv) "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' "
            "AND has_table_privilege(current_user, c.oid, p.priv)"
        )
    ).all()
    # Idempotency records are disposable request bookkeeping, not history.
    assert {(r.relname, r.priv) for r in rows} == {("idempotency_records", "DELETE")}


# --- T-MEM-2: completion_reports / calibration_records are write-once ------------------------


def test_T_MEM_2_completion_and_calibration_rows_cannot_be_rewritten(
    app_engine: Engine, world: World
) -> None:
    with app_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO completion_reports (wo_id, tenant_id, actor_user_id, failure_code, "
                "actual_fault_matched, labor_hours, technician_id, submitted_at) "
                "VALUES (:wo, :t, :u, 'COMP-CONTACTOR', true, 1.25, 'Marco', :at)"
            ),
            {"wo": world.wo_id, "t": world.tenant_id, "u": world.contractor_user_id, "at": NOW},
        )
        conn.execute(
            text(
                "INSERT INTO calibration_records (wo_id, tenant_id, asset_id, predicted_code, "
                "actual_code, label, actual_fault_matched, actor_user_id, created_at) "
                "VALUES (:wo, :t, :a, 'COMP-CONTACTOR', 'COMP-CONTACTOR', 'MATCH', true, :u, :at)"
            ),
            {
                "wo": world.wo_id,
                "t": world.tenant_id,
                "a": world.asset_id,
                "u": world.contractor_user_id,
                "at": NOW,
            },
        )
    for statement in (
        "UPDATE completion_reports SET failure_code = 'X' WHERE wo_id = :wo",
        "DELETE FROM completion_reports WHERE wo_id = :wo",
        "UPDATE calibration_records SET label = 'MISS' WHERE wo_id = :wo",
        "DELETE FROM calibration_records WHERE wo_id = :wo",
    ):
        with app_engine.connect() as conn, pytest.raises(ProgrammingError, match="permission"):
            conn.execute(text(statement), {"wo": world.wo_id})
    # A second completion for the same work order is a key violation (FR-7.4).
    with app_engine.connect() as conn, pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO completion_reports (wo_id, tenant_id, actor_user_id, failure_code, "
                "actual_fault_matched, labor_hours, technician_id, submitted_at) "
                "VALUES (:wo, :t, :u, 'OTHER', false, 2, 'Marco', :at)"
            ),
            {"wo": world.wo_id, "t": world.tenant_id, "u": world.contractor_user_id, "at": NOW},
        )


# --- T-MEM-2: failure_code set-once trigger --------------------------------------------------


@pytest.mark.parametrize("as_role", ["runtime", "migrator"])
def test_T_MEM_2_failure_code_is_set_once_even_for_the_owner(
    app_engine: Engine, migrator_engine: Engine, world: World, as_role: str
) -> None:
    set_code = "UPDATE workorders SET failure_code = :c WHERE id = :wo"
    with app_engine.begin() as conn:
        conn.execute(text(set_code), {"c": "COMP-CONTACTOR", "wo": world.wo_id})
        # Re-writing the same value is a no-op, not a change.
        conn.execute(text(set_code), {"c": "COMP-CONTACTOR", "wo": world.wo_id})

    engine = app_engine if as_role == "runtime" else migrator_engine
    for new_value in ("COMP-CAPACITOR", None):
        with engine.connect() as conn, pytest.raises(IntegrityError, match="set once"):
            conn.execute(text(set_code), {"c": new_value, "wo": world.wo_id})

    with app_engine.connect() as conn:
        stored = conn.execute(
            text("SELECT failure_code FROM workorders WHERE id = :wo"), {"wo": world.wo_id}
        ).scalar_one()
    assert stored == "COMP-CONTACTOR"


# --- T-MEM-2: CHECK constraints and the correction chain (H-4) -------------------------------


def test_T_MEM_2_correction_requires_corrects_event_id(app_conn: Connection, world: World) -> None:
    with pytest.raises(IntegrityError, match="ck_memory_events_correction"):
        _event(app_conn, world, type_="CORRECTION", stage=None, corrects=None)


def test_T_MEM_2_only_corrections_reference_an_event(app_conn: Connection, world: World) -> None:
    target = _event(app_conn, world)
    with pytest.raises(IntegrityError, match="ck_memory_events_correction"):
        _event(app_conn, world, type_="ADVANCE", stage="ARRIVED", corrects=target)


@pytest.mark.parametrize(
    ("stage", "constraint"),
    [(None, "ck_memory_events_advance_stage"), ("TELEPORTED", "ck_memory_events_stage")],
)
def test_T_MEM_2_advance_requires_a_known_stage(
    app_conn: Connection, world: World, stage: str | None, constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        _event(app_conn, world, type_="ADVANCE", stage=stage)


def test_T_MEM_2_correction_cannot_cross_work_orders(app_engine: Engine) -> None:
    with app_engine.begin() as conn:
        mine, other = make_world(conn), make_world(conn)
        others_event = _event(conn, other)
    # The trigger reports it first; the composite FK (wo_id, corrects_event_id) backs it up.
    with app_engine.connect() as conn, pytest.raises(IntegrityError, match="same work order"):
        _event(conn, mine, type_="CORRECTION", stage=None, corrects=others_event)


def test_T_MEM_2_event_is_corrected_at_most_once(app_engine: Engine, world: World) -> None:
    with app_engine.begin() as conn:
        target = _event(conn, world)
        _event(conn, world, type_="CORRECTION", stage=None, corrects=target)
    with app_engine.connect() as conn, pytest.raises(IntegrityError, match="corrects_once"):
        _event(conn, world, type_="CORRECTION", stage=None, corrects=target)


def test_T_MEM_2_correction_of_a_correction_is_rejected(app_engine: Engine, world: World) -> None:
    with app_engine.begin() as conn:
        target = _event(conn, world)
        correction = _event(conn, world, type_="CORRECTION", stage=None, corrects=target)
    with app_engine.connect() as conn, pytest.raises(DBAPIError, match="must reference an ADVANCE"):
        _event(conn, world, type_="CORRECTION", stage=None, corrects=correction)


def test_T_MEM_2_idempotency_key_is_unique_per_actor_not_global(
    app_conn: Connection, world: World
) -> None:
    # C-2: Ana reusing Marco's key is an independent event...
    _event(app_conn, world, key="shared-key", actor=world.contractor_user_id)
    _event(app_conn, world, key="shared-key", actor=world.owner_user_id)
    # ...but the same actor reusing a key is a conflict.
    with pytest.raises(IntegrityError, match="uq_memory_events_actor_idempotency"):
        _event(app_conn, world, key="shared-key", actor=world.contractor_user_id)


# --- L-1 and tenant consistency --------------------------------------------------------------


def test_public_ids_are_uuid_v4(app_conn: Connection, world: World) -> None:
    event_id = _event(app_conn, world)
    for value in (
        world.tenant_id,
        world.contractor_id,
        world.contractor_user_id,
        world.asset_id,
        world.wo_id,
        event_id,
    ):
        assert value.version == 4


def test_candidate_from_another_tenant_is_rejected_by_the_schema(app_engine: Engine) -> None:
    """Defence in depth for D10 H-6: composite (tenant_id, id) foreign keys."""
    with app_engine.begin() as conn:
        midtown, other = make_world(conn), make_world(conn)
    with app_engine.connect() as conn, pytest.raises(IntegrityError, match="fk_dispatch_cand"):
        conn.execute(
            text(
                "INSERT INTO dispatch_candidates (wo_id, contractor_id, tenant_id, rank, "
                "match_score, match_reason) VALUES (:wo, :c, :t, 1, 0.9, 'near')"
            ),
            {"wo": midtown.wo_id, "c": other.contractor_id, "t": midtown.tenant_id},
        )


def test_user_role_and_contractor_id_agree(app_conn: Connection, world: World) -> None:
    with pytest.raises(IntegrityError, match="ck_users_contractor_id"):
        app_conn.execute(
            text(
                "INSERT INTO users (tenant_id, email, name, role) "
                "VALUES (:t, :e, 'X', 'contractor')"
            ),
            {"t": world.tenant_id, "e": f"{uuid.uuid4().hex}@test.example"},
        )

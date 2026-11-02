"""Database roles and runtime grants (D10 H-5, plan rule 3).

Two roles:
- the **migrator** (whoever `MIGRATIONS_DATABASE_URL` connects as) owns the schema;
- the **runtime** role `insmartfix_app` (what `DATABASE_URL` connects as, directly or as a member)
  owns nothing and is granted only what the app needs.

Append-only tables get `SELECT, INSERT` and nothing else: Postgres grants are bypassed by a table's
owner, so the guarantee only holds because the runtime role is never the owner (T-MEM-2).

Every later migration that creates a table must call `grant_runtime_sql()` for it; there are no
`ALTER DEFAULT PRIVILEGES`, so a table nobody grants on is simply unreachable by the app.
"""

APP_ROLE = "insmartfix_app"

# FR-6.1, FR-7.4: history and outcomes are never rewritten.
APPEND_ONLY_TABLES: tuple[str, ...] = ("memory_events", "completion_reports", "calibration_records")

APPEND_ONLY_PRIVILEGES = "SELECT, INSERT"
# No DELETE and no TRUNCATE anywhere for the runtime role, except where the row is disposable.
MUTABLE_PRIVILEGES = "SELECT, INSERT, UPDATE"
DISPOSABLE_PRIVILEGES = "SELECT, INSERT, UPDATE, DELETE"


def grant_runtime_sql(table: str, privileges: str) -> str:
    """The `REVOKE`/`GRANT` pair for one table. Revoking from PUBLIC first keeps grants explicit."""
    return (
        f"REVOKE ALL ON TABLE {table} FROM PUBLIC;\n"
        f"GRANT {privileges} ON TABLE {table} TO {APP_ROLE};"
    )


def ensure_app_role_sql() -> str:
    """Create the runtime role if the environment's bootstrap hasn't, and refuse an unsafe one.

    Environments create `insmartfix_app` with `LOGIN` and a password from their secret store
    (compose: `infra/postgres/init/`; CI: a workflow step). If it doesn't exist yet the migration
    creates it `NOLOGIN`, so schema setup never depends on a secret. An existing role with
    superuser, role-creation or RLS-bypass rights fails the migration instead of being trusted.
    """
    return _ENSURE_APP_ROLE.replace("__APP_ROLE__", APP_ROLE)


_ENSURE_APP_ROLE = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '__APP_ROLE__') THEN
        CREATE ROLE __APP_ROLE__ NOLOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB NOBYPASSRLS;
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = '__APP_ROLE__'
          AND (rolsuper OR rolcreaterole OR rolcreatedb OR rolbypassrls)
    ) THEN
        RAISE EXCEPTION '__APP_ROLE__ must be NOSUPERUSER NOCREATEROLE NOCREATEDB NOBYPASSRLS';
    END IF;
    IF current_user = '__APP_ROLE__' THEN
        RAISE EXCEPTION 'migrations must not run as the runtime role __APP_ROLE__';
    END IF;
END
$$;
"""

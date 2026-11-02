# apps/api — InsmartFix API (FastAPI)

Python 3.12 · uv · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · pytest · ruff · mypy.

```bash
uv sync                                   # install (creates .venv)
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest --cov --cov-report=json && uv run python scripts/check_coverage.py coverage.json
DATABASE_URL=postgresql+psycopg://insmartfix:insmartfix@localhost:55432/insmartfix \
  JWT_SECRET=dev-only-insecure-jwt-secret-change-me-0000 ENV=local uv run uvicorn app.main:app --reload
```

Integration tests (`-m integration`) need `DATABASE_URL` (runtime role) and `MIGRATIONS_DATABASE_URL`
(schema owner) pointing at Postgres (the compose stack or CI service); they migrate to head themselves,
skip locally without them and are forced on in CI with `REQUIRE_INTEGRATION=1`.

### Database roles (D10 H-5)
- **Migrator** (`MIGRATIONS_DATABASE_URL`) owns the schema and runs `alembic upgrade head`.
- **Runtime** `insmartfix_app` (`DATABASE_URL`) owns nothing: `SELECT, INSERT` only on `memory_events`,
  `completion_reports`, `calibration_records`; `SELECT, INSERT, UPDATE` on other tables; no `DELETE`/`TRUNCATE`
  (except `idempotency_records`). Each environment creates it with `LOGIN` and a secret password
  (compose: `infra/postgres/init/`; CI: a workflow step); the first migration creates it `NOLOGIN` if missing and
  refuses a role with superuser/createrole/createdb/bypassrls.
- `workorders.failure_code` is set-once by trigger, which binds the owner too.
- **New tables:** every migration that creates one must grant it with `app.db.roles.grant_runtime_sql()`; there are
  no default privileges, so an ungranted table is unreachable by the app.

Config is environment-only (`app/settings.py`): `DATABASE_URL`, `JWT_SECRET`, `S3_*`, `FAKE_CLOCK`, `ENV` (required: local|test|ci|staging|production), `CORS_ORIGINS`;
migrations use `MIGRATIONS_DATABASE_URL` when set (schema-owner role, D10 H-5).

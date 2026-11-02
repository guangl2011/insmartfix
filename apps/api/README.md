# apps/api — InsmartFix API (FastAPI)

Python 3.12 · uv · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · pytest · ruff · mypy.

```bash
uv sync                                   # install (creates .venv)
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest --cov --cov-report=json && uv run python scripts/check_coverage.py coverage.json
DATABASE_URL=postgresql+psycopg://insmartfix:insmartfix@localhost:55432/insmartfix \
  JWT_SECRET=dev-only-insecure-jwt-secret-change-me-0000 ENV=local uv run uvicorn app.main:app --reload
```

Integration tests (`-m integration`) need `DATABASE_URL` pointing at Postgres (the compose stack or CI service);
they skip locally without it and are forced on in CI with `REQUIRE_INTEGRATION=1`.

Config is environment-only (`app/settings.py`): `DATABASE_URL`, `JWT_SECRET`, `S3_*`, `FAKE_CLOCK`, `ENV` (required: local|test|ci|staging|production), `CORS_ORIGINS`;
migrations use `MIGRATIONS_DATABASE_URL` when set (schema-owner role, D10 H-5).

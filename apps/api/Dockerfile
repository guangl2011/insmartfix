# syntax=docker/dockerfile:1.7
# One image for local-stack, CI and staging/production (TEST_PLAN §3). Config via env vars only.
ARG PYTHON_IMAGE=python:3.12-slim

FROM ${PYTHON_IMAGE} AS deps
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
RUN pip install --no-cache-dir uv==0.11.32
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

FROM ${PYTHON_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH
RUN groupadd --system app && useradd --system --gid app --home-dir /app app
WORKDIR /app
COPY --from=deps /opt/venv /opt/venv
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=6 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/v1/healthz', timeout=2).status == 200 else 1)"]
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000"]

# local-stack / ci-ephemeral only (`target: test` in infra/docker-compose.yml): keeps app/testing so
# FAKE_CLOCK=1 can mount POST /__test/clock (TEST_PLAN §3). Never pushed or deployed.
FROM base AS test
USER app

# Default (last) stage: what staging and production run.
# D10 H-7: the test-clock package (app/testing) must not exist in this image.
# CI asserts `import app.testing` fails in it (T-AUTH-18, image half).
FROM base AS runtime
RUN rm -rf ./app/testing
USER app

"""FastAPI application factory."""

from fastapi import FastAPI

from app.routes import health

API_PREFIX = "/v1"


def create_app() -> FastAPI:
    app = FastAPI(
        title="InsmartFix API",
        version="1.0.0",
        description="Contract: docs/specs/INSMARTFIX_V1_SPEC.md §5.",
    )
    app.include_router(health.router, prefix=API_PREFIX)
    return app


app = create_app()

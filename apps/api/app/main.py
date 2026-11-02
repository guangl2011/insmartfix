"""FastAPI application factory."""

from fastapi import FastAPI

from app.core.errors import install_error_handlers
from app.routes import auth, catalog, contractor, dispatch, health, workorders

API_PREFIX = "/v1"


def create_app() -> FastAPI:
    app = FastAPI(
        title="InsmartFix API",
        version="1.0.0",
        description="Contract: docs/specs/INSMARTFIX_V1_SPEC.md §5.",
    )
    install_error_handlers(app)
    for module in (health, auth, contractor, workorders, catalog, dispatch):
        app.include_router(module.router, prefix=API_PREFIX)
    return app


app = create_app()

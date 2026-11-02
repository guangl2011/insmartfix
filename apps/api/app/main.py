"""FastAPI application factory. Run with `uvicorn --factory app.main:create_app`."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.clock import clock
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from app.routes import auth, catalog, contractor, dispatch, health, workorders
from app.settings import TEST_CLOCK_ENVS, Settings, get_settings


def create_app(settings: Settings | None = None, *, schema_only: bool = False) -> FastAPI:
    """Build the app from settings (read from the environment when not given).

    Startup fails if `ENV` is unset, `JWT_SECRET` is weak, or `FAKE_CLOCK=1` is combined with an
    `ENV` outside {local, test, ci} (D10 H-7, NFR-6). `schema_only` builds the route table without
    any settings, for the OpenAPI export.
    """
    app = FastAPI(
        title="InsmartFix API",
        version="1.0.0",
        description="Contract: docs/specs/INSMARTFIX_V1_SPEC.md §5.",
    )
    install_error_handlers(app)
    for module in (health, auth, contractor, workorders, catalog, dispatch):
        app.include_router(module.router)
    if schema_only:
        return app

    settings = settings or get_settings()
    app.dependency_overrides[get_settings] = lambda: settings
    configure_logging(settings.log_level)

    if settings.fake_clock:
        if settings.env not in TEST_CLOCK_ENVS:  # also refused by Settings; belt and braces
            raise RuntimeError("FAKE_CLOCK=1 is not allowed in ENV=" + settings.env)
        from app.testing import clock_routes

        app.include_router(clock_routes.router)
    clock.enable_fake(settings.test_clock_enabled)

    # Outermost first: request id wraps everything so even 413s and CORS rejections are logged.
    app.add_middleware(BodySizeLimitMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
        )
    app.add_middleware(RequestContextMiddleware)
    return app

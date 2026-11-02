"""Liveness and readiness probes (spec §5, NFR-7)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.clock import now
from app.db.session import get_engine, ping
from app.schemas import ErrorEnvelope, HealthResponse, ReadyChecks, ReadyResponse
from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/healthz", operation_id="healthz")
def healthz() -> HealthResponse:
    """Process is up. Never touches dependencies."""
    return HealthResponse(status="ok", server_time=now())


@router.get(
    "/readyz",
    operation_id="readyz",
    response_model=ReadyResponse,
    responses={503: {"model": ErrorEnvelope, "description": "A dependency is unavailable"}},
)
def readyz(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReadyResponse | JSONResponse:
    """Ready to serve: the database answers `SELECT 1`."""
    try:
        ping(get_engine(settings.database_url))
    except Exception as exc:  # any driver/network error means "not ready"
        logger.warning("readyz: database check failed: %s", type(exc).__name__)
        body = ErrorEnvelope.model_validate(
            {"error": {"code": "NOT_READY", "message": "Database is unavailable."}}
        )
        return JSONResponse(
            status_code=503,
            content={**body.model_dump(), "server_time": now().isoformat()},
        )
    return ReadyResponse(status="ready", checks=ReadyChecks(database="ok"), server_time=now())

"""Liveness and readiness probes (spec §5, NFR-7)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.clock import now
from app.contract.common import ErrorCode, ErrorEnvelope
from app.contract.health import HealthResponse, ReadyChecks, ReadyResponse
from app.core.errors import error_response
from app.db.session import get_engine, ping
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
        return error_response(503, ErrorCode.NOT_READY, "Database is unavailable.")
    return ReadyResponse(status="ready", checks=ReadyChecks(database="ok"), server_time=now())

"""Failure-code catalog (spec §5 `GET /failure-codes`, FR-7.1). Stub until M2-T1."""

from typing import Annotated

from fastapi import APIRouter, Query, Security
from fastapi.responses import JSONResponse

from app.contract.catalog import FailureCodeList
from app.contract.common import error_responses
from app.contract.security import bearer_scheme
from app.routes import API_PREFIX
from app.routes._stub import not_implemented

router = APIRouter(prefix=API_PREFIX, tags=["catalog"], dependencies=[Security(bearer_scheme)])


@router.get(
    "/failure-codes",
    operation_id="list_failure_codes",
    response_model=FailureCodeList,
    responses=error_responses(401, 422, 501),
)
def list_failure_codes(
    subtype: Annotated[str | None, Query(max_length=64)] = None,
) -> JSONResponse:
    """Codes for an asset subtype, ordered and grouped by component (FR-7.1)."""
    return not_implemented()

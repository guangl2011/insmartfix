"""Owner/FM dispatch API (spec §5 `POST /dispatch/workorders`, FR-10.1). Stub until M1-T6."""

from fastapi import APIRouter, Security
from fastapi.responses import JSONResponse

from app.contract.common import IdempotencyKeyHeader, error_responses
from app.contract.dispatch import DispatchCreateRequest, DispatchCreateResponse
from app.contract.security import bearer_scheme
from app.routes import API_PREFIX
from app.routes._stub import not_implemented

router = APIRouter(prefix=API_PREFIX, tags=["dispatch"], dependencies=[Security(bearer_scheme)])


@router.post(
    "/dispatch/workorders",
    operation_id="create_dispatch_workorder",
    status_code=201,
    response_model=DispatchCreateResponse,
    responses=error_responses(401, 403, 404, 422, 501),
)
def create_dispatch_workorder(
    body: DispatchCreateRequest, idempotency_key: IdempotencyKeyHeader = None
) -> JSONResponse:
    """Create a WO with ranked candidates; offers rank 1 with `sla_deadline = now + sla_minutes`."""
    return not_implemented()

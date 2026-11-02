"""Owner/FM dispatch API (spec §5 `POST /dispatch/workorders`, FR-10.1). Stub until M1-T6."""

from fastapi.responses import JSONResponse

from app.contract.common import IdempotencyKeyHeader, error_responses
from app.contract.dispatch import DispatchCreateRequest, DispatchCreateResponse
from app.identity_gate.deps import Authorized, gated_router
from app.identity_gate.policy import Action
from app.routes import API_PREFIX
from app.routes._stub import not_implemented

router = gated_router(prefix=API_PREFIX, tags=["dispatch"])


@router.post(
    "/dispatch/workorders",
    action=Action.DISPATCH_CREATE,
    operation_id="create_dispatch_workorder",
    status_code=201,
    response_model=DispatchCreateResponse,
    responses=error_responses(401, 403, 404, 422, 501),
)
def create_dispatch_workorder(
    target: Authorized, body: DispatchCreateRequest, idempotency_key: IdempotencyKeyHeader = None
) -> JSONResponse:
    """Create a WO with ranked candidates; offers rank 1 with `sla_deadline = now + sla_minutes`."""
    return not_implemented()

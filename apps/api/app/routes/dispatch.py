"""Owner/FM dispatch API (spec §5 `POST /dispatch/workorders`, FR-10.1).

Gated as `dispatch_create` (owner/FM only; a contractor gets 403, plan §2.1) and tenant-bounded on
every input (D10 H-6): an asset in another tenant → 404, any candidate outside the caller's
tenant → 422 with no hint which one. The tenant comes only from the gate's principal.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.clock import now
from app.contract.common import ErrorCode, IdempotencyKeyHeader, error_responses
from app.contract.dispatch import DispatchCreateRequest, DispatchCreateResponse
from app.core.errors import ApiError
from app.db.session import get_db
from app.dispatch.create import (
    AssetNotFoundError,
    CandidateSpec,
    DispatchSpec,
    InvalidCandidatesError,
    create_dispatch,
)
from app.identity_gate.deps import Authorized, gated_router
from app.identity_gate.policy import Action
from app.routes import API_PREFIX

router = gated_router(prefix=API_PREFIX, tags=["dispatch"])


@router.post(
    "/dispatch/workorders",
    action=Action.DISPATCH_CREATE,
    operation_id="create_dispatch_workorder",
    status_code=201,
    response_model=DispatchCreateResponse,
    responses=error_responses(401, 403, 404, 422),
)
def create_dispatch_workorder(
    target: Authorized,
    body: DispatchCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: IdempotencyKeyHeader = None,
) -> DispatchCreateResponse:
    """Create a WO with ranked candidates; offers rank 1 with `sla_deadline = now + sla_minutes`."""
    principal = target.principal
    spec = DispatchSpec(
        asset_id=body.asset_id,
        symptom=body.symptom,
        sla_minutes=body.sla_minutes,
        candidates=[
            CandidateSpec(contractor_id=c.contractor_id, match_score=c.match_score, reason=c.reason)
            for c in body.candidates
        ],
    )
    try:
        wo_id = create_dispatch(
            db,
            tenant_id=principal.tenant_id,
            created_by_user_id=principal.user_id,
            spec=spec,
            now=now(),
        )
    except AssetNotFoundError as exc:
        raise ApiError(404, ErrorCode.NOT_FOUND) from exc
    except InvalidCandidatesError as exc:
        raise ApiError(422, ErrorCode.VALIDATION_ERROR) from exc
    db.commit()
    return DispatchCreateResponse(wo_id=wo_id, server_time=now())

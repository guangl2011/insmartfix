"""Contractor schedule + accept/decline (spec §5; FR-1.4, FR-2.1, FR-4). Stubs until M1-T7/M1-T8.

Each `/contractor/{cid}/…` route has a `/me/…` alias that resolves `contractor_id` from the token.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from app.auth.deps import get_principal
from app.contract.common import IdempotencyKeyHeader, error_responses
from app.contract.schedule import DeclineRequest, ScheduleResponse
from app.contract.workorders import WorkOrderDetail
from app.routes import API_PREFIX
from app.routes._stub import not_implemented

router = APIRouter(prefix=API_PREFIX, tags=["contractor"], dependencies=[Depends(get_principal)])

SCHEDULE_ERRORS = error_responses(401, 403, 404, 422, 501)
ACCEPT_ERRORS = error_responses(401, 403, 404, 409, 422, 501)


@router.get(
    "/contractor/{cid}/schedule",
    operation_id="get_contractor_schedule",
    response_model=ScheduleResponse,
    responses=SCHEDULE_ERRORS,
)
def get_contractor_schedule(cid: UUID) -> JSONResponse:
    """Offers + active jobs for one contractor (own `cid`, or owner/FM in the same tenant)."""
    return not_implemented()


@router.get(
    "/me/schedule",
    operation_id="get_my_schedule",
    response_model=ScheduleResponse,
    responses=SCHEDULE_ERRORS,
)
def get_my_schedule() -> JSONResponse:
    """Alias of the schedule for the caller's own `contractor_id` (FR-1.4)."""
    return not_implemented()


@router.post(
    "/contractor/{cid}/accept/{wo}",
    operation_id="accept_offer",
    response_model=WorkOrderDetail,
    responses=ACCEPT_ERRORS,
)
def accept_offer(cid: UUID, wo: UUID, idempotency_key: IdempotencyKeyHeader = None) -> JSONResponse:
    """Server-authoritative accept (FR-4.1, FR-5.3). 409 OFFER_UNAVAILABLE on a lost race."""
    return not_implemented()


@router.post(
    "/me/accept/{wo}",
    operation_id="accept_my_offer",
    response_model=WorkOrderDetail,
    responses=ACCEPT_ERRORS,
)
def accept_my_offer(wo: UUID, idempotency_key: IdempotencyKeyHeader = None) -> JSONResponse:
    """Alias of accept for the caller's own `contractor_id`."""
    return not_implemented()


@router.post(
    "/contractor/{cid}/decline/{wo}",
    operation_id="decline_offer",
    status_code=204,
    response_class=Response,
    responses=ACCEPT_ERRORS,
)
def decline_offer(
    cid: UUID,
    wo: UUID,
    body: DeclineRequest,
    idempotency_key: IdempotencyKeyHeader = None,
) -> Response:
    """Decline with an optional reason (FR-4.2); re-offers to the next rank (FR-4.3)."""
    return not_implemented()


@router.post(
    "/me/decline/{wo}",
    operation_id="decline_my_offer",
    status_code=204,
    response_class=Response,
    responses=ACCEPT_ERRORS,
)
def decline_my_offer(
    wo: UUID, body: DeclineRequest, idempotency_key: IdempotencyKeyHeader = None
) -> Response:
    """Alias of decline for the caller's own `contractor_id`."""
    return not_implemented()

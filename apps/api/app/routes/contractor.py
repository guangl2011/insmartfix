"""Contractor schedule + accept/decline (spec §5; FR-1.4, FR-2.1, FR-4).

Each `/contractor/{cid}/…` route has a `/me/…` alias that resolves `contractor_id` from the token.
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Response
from sqlalchemy.orm import Session

from app.clock import now
from app.contract.common import IdempotencyKeyHeader, error_responses
from app.contract.schedule import DeclineRequest, ScheduleResponse
from app.contract.workorders import WorkOrderDetail
from app.db.session import get_db
from app.dispatch.accept import accept, refresh_prediction_snapshot
from app.dispatch.decline import decline
from app.dispatch.schedule import build_schedule
from app.identity_gate.deps import Authorized, AuthorizedTarget, gated_router
from app.identity_gate.policy import Action
from app.routes import API_PREFIX
from app.workorders.detail import NullDecisionSource, build_detail

DbSession = Annotated[Session, Depends(get_db)]
router = gated_router(prefix=API_PREFIX, tags=["contractor"])

SCHEDULE_ERRORS = error_responses(401, 403, 404, 422)
ACCEPT_ERRORS = error_responses(401, 403, 404, 409, 422)


@router.get(
    "/contractor/{cid}/schedule",
    action=Action.SCHEDULE,
    operation_id="get_contractor_schedule",
    response_model=ScheduleResponse,
    responses=SCHEDULE_ERRORS,
)
def get_contractor_schedule(target: Authorized, db: DbSession) -> ScheduleResponse:
    """Offers + active jobs for one contractor (own `cid`, or owner/FM in the same tenant)."""
    return _schedule(target, db)


@router.get(
    "/me/schedule",
    action=Action.SCHEDULE,
    operation_id="get_my_schedule",
    response_model=ScheduleResponse,
    responses=SCHEDULE_ERRORS,
)
def get_my_schedule(target: Authorized, db: DbSession) -> ScheduleResponse:
    """Alias of the schedule for the caller's own `contractor_id` (FR-1.4)."""
    return _schedule(target, db)


def _schedule(target: AuthorizedTarget, db: Session) -> ScheduleResponse:
    assert target.contractor_id is not None  # noqa: S101 — the gate resolved it (rows 5, 7)
    return build_schedule(db, target.contractor_id, now())


@router.post(
    "/contractor/{cid}/accept/{wo}",
    action=Action.ACCEPT,
    operation_id="accept_offer",
    response_model=WorkOrderDetail,
    responses=ACCEPT_ERRORS,
)
def accept_offer(
    target: Authorized, db: DbSession, idempotency_key: IdempotencyKeyHeader = None
) -> WorkOrderDetail:
    """Server-authoritative accept (FR-4.1, FR-5.3). 409 OFFER_UNAVAILABLE on a lost race.
    Returns the full detail and packet synchronously (FR-3.6)."""
    return _accept(target, db)


@router.post(
    "/me/accept/{wo}",
    action=Action.ACCEPT,
    operation_id="accept_my_offer",
    response_model=WorkOrderDetail,
    responses=ACCEPT_ERRORS,
)
def accept_my_offer(
    target: Authorized, db: DbSession, idempotency_key: IdempotencyKeyHeader = None
) -> WorkOrderDetail:
    """Alias of accept for the caller's own `contractor_id`."""
    return _accept(target, db)


def _accept(target: AuthorizedTarget, db: Session) -> WorkOrderDetail:
    cid, wo = _offer_target(target)
    at = now()
    accept(db, wo, cid, at)
    detail = build_detail(
        db, wo, contractor_id=cid, owner_view=False, now=at, decisions=NullDecisionSource()
    )
    # D10 L-4: snapshot the prediction the contractor saw when accepting.
    refresh_prediction_snapshot(db, wo, detail.predicted_failure_code)
    db.commit()
    return detail


@router.post(
    "/contractor/{cid}/decline/{wo}",
    action=Action.DECLINE,
    operation_id="decline_offer",
    status_code=204,
    response_class=Response,
    responses=ACCEPT_ERRORS,
)
def decline_offer(
    target: Authorized,
    db: DbSession,
    body: DeclineRequest,
    idempotency_key: IdempotencyKeyHeader = None,
) -> Response:
    """Decline with an optional reason (FR-4.2); re-offers to the next rank (FR-4.3)."""
    return _decline(target, db, body)


@router.post(
    "/me/decline/{wo}",
    action=Action.DECLINE,
    operation_id="decline_my_offer",
    status_code=204,
    response_class=Response,
    responses=ACCEPT_ERRORS,
)
def decline_my_offer(
    target: Authorized,
    db: DbSession,
    body: DeclineRequest,
    idempotency_key: IdempotencyKeyHeader = None,
) -> Response:
    """Alias of decline for the caller's own `contractor_id`."""
    return _decline(target, db, body)


def _decline(target: AuthorizedTarget, db: Session, body: DeclineRequest) -> Response:
    cid, wo = _offer_target(target)
    decline(db, wo, cid, body, now())
    db.commit()
    return Response(status_code=204)


def _offer_target(target: AuthorizedTarget) -> tuple[UUID, UUID]:
    """The gate allowed a contractor (offeree or bound) on an existing WO (§2.1 rows 10, 15)."""
    assert target.contractor_id is not None  # noqa: S101
    assert target.wo is not None  # noqa: S101
    return target.contractor_id, target.wo.wo_id

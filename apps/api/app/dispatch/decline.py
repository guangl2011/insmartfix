"""Decline (FR-4.2, FR-4.3; D10 H-2, L-5). Same in-lock offeree re-assertion as accept."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.contract.common import ErrorCode
from app.contract.schedule import DeclineRequest
from app.core.errors import ApiError
from app.dispatch.accept import is_bound, is_live_offeree, lock, unavailable
from app.dispatch.reoffer import reoffer_next


def decline(
    db: Session, wo_id: UUID, contractor_id: UUID, body: DeclineRequest, now: datetime
) -> None:
    """Persist the optional reason/note (FR-4.2) and re-offer to the next rank (FR-4.3)."""
    locked = lock(db, wo_id, contractor_id)
    if is_bound(locked, contractor_id):
        raise ApiError(409, ErrorCode.INVALID_TRANSITION)  # a bound job is not an offer
    if not is_live_offeree(locked, contractor_id, now):
        raise unavailable(locked, contractor_id)
    assert locked.candidate is not None  # noqa: S101
    reason = body.reason.value if body.reason else None
    locked.candidate.state = "DECLINED"
    locked.candidate.responded_at = now
    locked.candidate.decline_reason = reason
    locked.candidate.decline_note = body.note
    locked.dispatch.decline_reason = reason
    locked.dispatch.decline_note = body.note
    reoffer_next(db, locked.dispatch, now)
    db.flush()

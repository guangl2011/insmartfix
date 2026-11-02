"""Re-offer to the next ranked candidate (FR-4.3, FR-5.1). Caller holds the dispatch row lock."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Dispatch, DispatchCandidate


def reoffer_next(db: Session, dispatch: Dispatch, now: datetime) -> DispatchCandidate | None:
    """Offer to the best-ranked candidate never offered yet (`QUEUED`), with a fresh deadline of
    `now + sla_minutes`. With nobody left: `NO_CONTRACTORS` (visible to owner/FM, FR-4.3).
    Bumps `version` either way."""
    nxt = db.execute(
        select(DispatchCandidate)
        .where(DispatchCandidate.wo_id == dispatch.wo_id, DispatchCandidate.state == "QUEUED")
        .order_by(DispatchCandidate.rank)
        .limit(1)
        .with_for_update()
    ).scalar_one_or_none()
    dispatch.version += 1
    dispatch.updated_at = now
    if nxt is None:
        dispatch.state = "NO_CONTRACTORS"
        dispatch.current_contractor_id = None
        dispatch.sla_deadline = None
        return None
    deadline = now + timedelta(minutes=dispatch.sla_minutes)
    nxt.state = "OFFERED"
    nxt.offered_at = now
    nxt.sla_deadline = deadline
    dispatch.state = "PENDING"
    dispatch.current_contractor_id = nxt.contractor_id
    dispatch.sla_deadline = deadline
    return nxt

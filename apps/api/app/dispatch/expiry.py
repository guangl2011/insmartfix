"""SLA expiry and re-offer (FR-5.1, FR-5.2).

An offer whose `sla_deadline` has passed is marked EXPIRED for its candidate and re-offered to the
next ranked candidate with a new deadline, or the dispatch goes to `NO_CONTRACTORS` when nobody
is left (T-DISP-3). This runs:
- lazily, before any read or write that touches the offer (schedule reads, accept/decline inside
  their lock), and
- in the background sweeper every 15 s (`sweeper.py`), so state is right without traffic.

Rows are locked `FOR UPDATE SKIP LOCKED` and re-checked under the lock, so expiry never fights an
accept in progress: whichever takes the lock first wins (FR-5.3), and the other sees the result.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Dispatch, DispatchCandidate
from app.dispatch.reoffer import reoffer_next

BATCH = 200


def is_due(dispatch: Dispatch, now: datetime) -> bool:
    return (
        dispatch.state == "PENDING"
        and dispatch.sla_deadline is not None
        and dispatch.sla_deadline <= now
    )


def expire_locked(db: Session, dispatch: Dispatch, now: datetime) -> None:
    """Expire the current offer and re-offer. The caller holds the dispatch row lock. The new
    deadline is `now + sla_minutes`, so afterwards the offer is live or the dispatch terminal."""
    if is_due(dispatch, now):
        cand = db.execute(
            select(DispatchCandidate)
            .where(
                DispatchCandidate.wo_id == dispatch.wo_id,
                DispatchCandidate.contractor_id == dispatch.current_contractor_id,
            )
            .with_for_update()
        ).scalar_one()
        if cand.state == "OFFERED":
            cand.state = "EXPIRED"
        reoffer_next(db, dispatch, now)
    db.flush()


def expire_due(
    db: Session,
    now: datetime,
    *,
    contractor_id: UUID | None = None,
    wo_id: UUID | None = None,
    limit: int = BATCH,
) -> int:
    """Expire due offers: all of them, or only WOs where `contractor_id` is a candidate (offers
    their schedule read touches), or one WO. Returns how many were expired. Does not commit."""
    q = (
        select(Dispatch)
        .where(Dispatch.state == "PENDING", Dispatch.sla_deadline <= now)
        .order_by(Dispatch.sla_deadline)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    if contractor_id is not None:
        q = q.where(
            Dispatch.wo_id.in_(
                select(DispatchCandidate.wo_id).where(
                    DispatchCandidate.contractor_id == contractor_id
                )
            )
        )
    if wo_id is not None:
        q = q.where(Dispatch.wo_id == wo_id)
    rows = db.execute(q).scalars().all()
    for d in rows:
        expire_locked(db, d, now)
    return len(rows)


def expire_lazily(db: Session, now: datetime, *, contractor_id: UUID | None = None) -> None:
    """Lazy hook before a read: expire what is due and commit, so the read (and every later
    one) sees current state without waiting for the sweeper."""
    if expire_due(db, now, contractor_id=contractor_id):
        db.commit()

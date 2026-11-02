"""Accept (FR-4.1, FR-5.3; D10 H-2, L-4). Decline lives in `decline.py`.

The identity gate has already classified the caller, but outside any lock. Here the dispatch row
is locked (`SELECT … FOR UPDATE`) and the offeree binding is **re-asserted inside the lock**:
`state = PENDING AND current_contractor_id = C AND candidate OFFERED AND sla_deadline > now`
(§2.1 row 10). A miss is `409 OFFER_UNAVAILABLE` with no state change at all, and in particular
no `reoffer_next()`. Exactly one accept can win a race: the winner flips the state under the lock
and bumps `version`; everyone else re-reads the flipped row.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contract.common import ErrorCode, OfferUnavailableReason
from app.core.errors import ApiError
from app.db.models import Dispatch, DispatchCandidate, WorkOrder
from app.dispatch.expiry import expire_locked, is_due
from app.identity_gate.policy import WorkOrderFacts, past_reason

BOUND_STATES = ("ACCEPTED", "IN_PROGRESS", "COMPLETED")


@dataclass(frozen=True)
class Locked:
    dispatch: Dispatch
    candidate: DispatchCandidate | None


def lock(db: Session, wo_id: UUID, contractor_id: UUID) -> Locked:
    dispatch = db.execute(
        select(Dispatch).where(Dispatch.wo_id == wo_id).with_for_update()
    ).scalar_one()
    cand = db.execute(
        select(DispatchCandidate)
        .where(DispatchCandidate.wo_id == wo_id, DispatchCandidate.contractor_id == contractor_id)
        .with_for_update()
    ).scalar_one_or_none()
    return Locked(dispatch, cand)


def is_live_offeree(locked: Locked, contractor_id: UUID, now: datetime) -> bool:
    d, c = locked.dispatch, locked.candidate
    return (
        d.state == "PENDING"
        and d.current_contractor_id == contractor_id
        and c is not None
        and c.state == "OFFERED"
        and d.sla_deadline is not None
        and d.sla_deadline > now
    )


def is_bound(locked: Locked, contractor_id: UUID) -> bool:
    d = locked.dispatch
    return d.state in BOUND_STATES and d.current_contractor_id == contractor_id


def unavailable(locked: Locked, contractor_id: UUID) -> ApiError:
    facts = WorkOrderFacts(
        wo_id=locked.dispatch.wo_id,
        tenant_id=locked.dispatch.tenant_id,
        dispatch_state=locked.dispatch.state,
        current_contractor_id=locked.dispatch.current_contractor_id,
        sla_deadline=locked.dispatch.sla_deadline,
        candidate_state=locked.candidate.state if locked.candidate else None,
    )
    return ApiError(409, ErrorCode.OFFER_UNAVAILABLE, reason=past_reason(contractor_id, facts))


def lazy_expire_own(db: Session, locked: Locked, contractor_id: UUID, now: datetime) -> None:
    """FR-5.2 lazy expiry inside the lock, for the requester's own due offer: commit the expiry
    and re-offer (it is legitimate state), then the caller answers 409 `expired`. Another
    candidate's request never triggers it (D10 H-2: a miss changes nothing)."""
    if locked.dispatch.current_contractor_id == contractor_id and is_due(locked.dispatch, now):
        expire_locked(db, locked.dispatch, now)
        err = ApiError(409, ErrorCode.OFFER_UNAVAILABLE, reason=OfferUnavailableReason.EXPIRED)
        db.commit()
        raise err


def accept(db: Session, wo_id: UUID, contractor_id: UUID, now: datetime) -> None:
    """Bind the WO to the contractor (dispatch → ACCEPTED). A retry by the already-bound
    contractor is a no-op success (it never re-binds or re-offers, §2.1 row 15)."""
    locked = lock(db, wo_id, contractor_id)
    if is_bound(locked, contractor_id):
        return
    lazy_expire_own(db, locked, contractor_id, now)
    if not is_live_offeree(locked, contractor_id, now):
        raise unavailable(locked, contractor_id)
    assert locked.candidate is not None  # noqa: S101 — is_live_offeree checked it
    d = locked.dispatch
    d.state = "ACCEPTED"
    d.version += 1
    d.updated_at = now
    locked.candidate.state = "ACCEPTED"
    locked.candidate.responded_at = now
    db.flush()


def refresh_prediction_snapshot(db: Session, wo_id: UUID, predicted: str | None) -> None:
    """D10 L-4: label calibration against what the contractor saw at accept. Only overwrites the
    snapshot when the engine has a prediction."""
    if predicted is not None:
        wo = db.get(WorkOrder, wo_id)
        assert wo is not None  # noqa: S101 — the row is locked via dispatch
        wo.predicted_failure_code = predicted

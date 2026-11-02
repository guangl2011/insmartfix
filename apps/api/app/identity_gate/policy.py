"""The identity-gate policy: one pure function that decides every contractor-facing request.

IMPLEMENTATION_PLAN §2.1 (revised per D10: H-1, H-2, M-1, M-2, L-6). Rows are evaluated in order
and the first match wins; row numbers in comments refer to the §2.1 table. `decide()` does no I/O:
the gate dependency (`deps.py`) loads the facts and calls it, so the whole matrix is testable
in memory (T-AUTH-6 policy level, T-AUTH-15, T-AUTH-16).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.auth.service import Principal
from app.contract.common import OfferUnavailableReason


class Action(StrEnum):
    SCHEDULE = "schedule"
    ACCEPT = "accept"
    DECLINE = "decline"
    GET_WO = "get_wo"
    TRANSITION = "transition"
    PHOTO = "photo"
    COMPLETE = "complete"
    DISPATCH_CREATE = "dispatch_create"


OFFER_ACTIONS = frozenset({Action.ACCEPT, Action.DECLINE})
WORK_ACTIONS = frozenset({Action.TRANSITION, Action.PHOTO, Action.COMPLETE})
OWNER_READ_ACTIONS = frozenset({Action.SCHEDULE, Action.GET_WO})
ME_FORBIDDEN_FOR_OWNER = frozenset({Action.SCHEDULE, Action.ACCEPT, Action.DECLINE})


class Relationship(StrEnum):
    STRANGER = "stranger"
    OFFEREE = "offeree"
    PAST = "past"
    BOUND = "bound"


class AllowedAs(StrEnum):
    OFFEREE = "offeree"
    BOUND = "bound"
    OWNER = "owner"
    SELF = "self"  # contractor on their own schedule


BOUND_STATES = frozenset({"ACCEPTED", "IN_PROGRESS", "COMPLETED"})


@dataclass(frozen=True)
class WorkOrderFacts:
    """What the gate needs about a WO, for the calling contractor (None fields if no row)."""

    wo_id: UUID
    tenant_id: UUID
    dispatch_state: str | None
    current_contractor_id: UUID | None
    sla_deadline: datetime | None
    candidate_state: str | None  # the caller's dispatch_candidates.state, if any


@dataclass(frozen=True)
class ContractorFacts:
    contractor_id: UUID
    tenant_id: UUID


@dataclass(frozen=True)
class Allow:
    as_: AllowedAs


@dataclass(frozen=True)
class Deny403:
    pass


@dataclass(frozen=True)
class Deny404:
    pass


@dataclass(frozen=True)
class Unavailable409:
    reason: OfferUnavailableReason


Decision = Allow | Deny403 | Deny404 | Unavailable409


def relationship(contractor_id: UUID, wo: WorkOrderFacts, now: datetime) -> Relationship:
    """§2.1 relationship of contractor C to W, with lazy expiry applied (D10 L-6)."""
    state = wo.candidate_state
    if state is None or state == "QUEUED":
        return Relationship.STRANGER
    is_current = wo.current_contractor_id == contractor_id
    if is_current and wo.dispatch_state in BOUND_STATES:
        return Relationship.BOUND
    if (
        is_current
        and wo.dispatch_state == "PENDING"
        and state == "OFFERED"
        and wo.sla_deadline is not None
        and wo.sla_deadline > now
    ):
        return Relationship.OFFEREE
    return Relationship.PAST


def past_reason(contractor_id: UUID, wo: WorkOrderFacts) -> OfferUnavailableReason:
    """Why a past candidate's offer is gone. Names no other candidate (D10 Q1)."""
    if wo.candidate_state == "WITHDRAWN":
        return OfferUnavailableReason.WITHDRAWN
    if wo.current_contractor_id is not None and wo.current_contractor_id != contractor_id:
        return OfferUnavailableReason.REASSIGNED
    return OfferUnavailableReason.EXPIRED


def decide_path_cid(
    principal: Principal, path_cid: UUID | None, via_me: bool, action: Action
) -> Decision | None:
    """Rows 2-3: decided **before any lookup** (D10 M-1). None means "continue"."""
    if principal.contractor_id is not None:
        if path_cid is not None and path_cid != principal.contractor_id:
            return Deny403()  # row 2, identical whatever cid is
        return None
    if via_me and action in ME_FORBIDDEN_FOR_OWNER:
        return Deny403()  # row 3
    return None


def decide(
    principal: Principal,
    action: Action,
    *,
    now: datetime,
    path_cid: UUID | None = None,
    via_me: bool = False,
    contractor: ContractorFacts | None = None,
    wo: WorkOrderFacts | None = None,
    needs_wo: bool = False,
) -> Decision:
    """Decide one request. `contractor` is the looked-up `path_cid` (owner/FM only), `wo` the
    looked-up work order (None if it doesn't exist), `needs_wo` whether the route targets one."""
    early = decide_path_cid(principal, path_cid, via_me, action)
    if early is not None:
        return early

    is_contractor = principal.contractor_id is not None

    if action is Action.DISPATCH_CREATE:
        return Deny403() if is_contractor else Allow(AllowedAs.OWNER)

    # Row 4: target missing or in another tenant → 404 (owner: cid as well).
    if needs_wo and (wo is None or wo.tenant_id != principal.tenant_id):
        return Deny404()
    if (
        not is_contractor
        and path_cid is not None
        and (contractor is None or contractor.tenant_id != principal.tenant_id)
    ):
        return Deny404()

    if not is_contractor:
        # Rows 5-6: owner/FM override is read-only (D10 H-1, C-3).
        return Allow(AllowedAs.OWNER) if action in OWNER_READ_ACTIONS else Deny403()

    assert principal.contractor_id is not None  # noqa: S101 — narrowed above
    if action is Action.SCHEDULE:
        return Allow(AllowedAs.SELF)  # row 7

    assert wo is not None  # noqa: S101 — every non-schedule contractor action targets a WO
    rel = relationship(principal.contractor_id, wo, now)
    if rel is Relationship.STRANGER:
        return Deny404()  # row 8
    if rel is Relationship.BOUND:
        return Allow(AllowedAs.BOUND)  # rows 14-15
    if action in WORK_ACTIONS:
        return Deny403()  # row 13
    if rel is Relationship.OFFEREE:
        return Allow(AllowedAs.OFFEREE)  # rows 9-10
    # Past candidate.
    if action in OFFER_ACTIONS:
        return Unavailable409(past_reason(principal.contractor_id, wo))  # row 11
    return Deny404()  # row 12

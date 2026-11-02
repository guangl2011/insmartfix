"""T-AUTH-6 (A, policy level), T-AUTH-15 (policy half), T-AUTH-16 (policy half).

Exhaustive, in memory: principals, actions and WO relationships against the revised §2.1 table
(IMPLEMENTATION_PLAN §2.1; D10 H-1, H-2, M-1, M-2, L-6). Expected results are written out per
row here, independently of `policy.py`. The HTTP-level matrix comes in M2-T7.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.auth.service import Principal
from app.contract.auth import Role
from app.contract.common import OfferUnavailableReason as R
from app.identity_gate.policy import (
    Action,
    Allow,
    AllowedAs,
    ContractorFacts,
    Decision,
    Deny403,
    Deny404,
    Unavailable409,
    WorkOrderFacts,
    decide,
    relationship,
)

NOW = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
MIDTOWN, OTHER = uuid4(), uuid4()
MARCO_C, ANA_C, ZED_C = uuid4(), uuid4(), uuid4()


def _p(role: Role, tenant: UUID, cid: UUID | None) -> Principal:
    return Principal(uuid4(), role, tenant, cid, "x", None)


MARCO = _p(Role.CONTRACTOR, MIDTOWN, MARCO_C)
ANA = _p(Role.CONTRACTOR, MIDTOWN, ANA_C)
ZED = _p(Role.CONTRACTOR, OTHER, ZED_C)
OWNER = _p(Role.OWNER, MIDTOWN, None)
FM = _p(Role.FM, MIDTOWN, None)
OTHER_OWNER = _p(Role.OWNER, OTHER, None)

WO_ACTIONS = [
    Action.ACCEPT,
    Action.DECLINE,
    Action.GET_WO,
    Action.TRANSITION,
    Action.PHOTO,
    Action.COMPLETE,
]


def wo(
    *,
    tenant: UUID = MIDTOWN,
    state: str | None = "PENDING",
    current: UUID | None = MARCO_C,
    deadline: datetime | None = NOW + timedelta(minutes=5),
    cand: str | None = "OFFERED",
) -> WorkOrderFacts:
    return WorkOrderFacts(uuid4(), tenant, state, current, deadline, cand)


# Marco's relationship rows (D10 T-AUTH-6 ext): name → (facts, relationship)
REL_ROWS: dict[str, WorkOrderFacts | None] = {
    "stranger": wo(cand=None, current=ANA_C),
    "queued_candidate": wo(cand="QUEUED", current=ANA_C),
    "offeree": wo(),
    "offeree_past_deadline_unswept": wo(deadline=NOW - timedelta(seconds=1)),
    "past_expired_not_reoffered": wo(state="ESCALATED", current=None, cand="EXPIRED"),
    "past_reassigned": wo(current=ANA_C, cand="EXPIRED"),
    "past_declined": wo(current=ANA_C, cand="DECLINED"),
    "past_withdrawn": wo(state="PENDING", current=ANA_C, cand="WITHDRAWN"),
    "past_lost_race": wo(state="ACCEPTED", current=ANA_C, cand="EXPIRED"),
    "bound_accepted": wo(state="ACCEPTED", cand="ACCEPTED"),
    "bound_in_progress": wo(state="IN_PROGRESS", cand="ACCEPTED"),
    "bound_after_completion": wo(state="COMPLETED", cand="ACCEPTED"),
    "nonexistent": None,
    "cross_tenant": wo(tenant=OTHER, current=ZED_C, cand=None),
}

A403: Decision = Deny403()
A404: Decision = Deny404()
OFF: Decision = Allow(AllowedAs.OFFEREE)
BOUND: Decision = Allow(AllowedAs.BOUND)


def u409(r: R) -> Decision:
    return Unavailable409(r)


# Expected for Marco: row → [accept, decline, get_wo, transition, photo, complete]
MARCO_EXPECTED: dict[str, list[Decision]] = {
    "stranger": [A404] * 6,  # row 8
    "queued_candidate": [A404] * 6,  # row 8 (M-2)
    "offeree": [OFF, OFF, OFF, A403, A403, A403],  # rows 9, 10, 13
    "offeree_past_deadline_unswept": [u409(R.EXPIRED)] * 2 + [A404, A403, A403, A403],  # L-6
    "past_expired_not_reoffered": [u409(R.EXPIRED)] * 2 + [A404, A403, A403, A403],
    "past_reassigned": [u409(R.REASSIGNED)] * 2 + [A404, A403, A403, A403],  # rows 11-13
    "past_declined": [u409(R.REASSIGNED)] * 2 + [A404, A403, A403, A403],
    "past_withdrawn": [u409(R.WITHDRAWN)] * 2 + [A404, A403, A403, A403],
    "past_lost_race": [u409(R.REASSIGNED)] * 2 + [A404, A403, A403, A403],
    "bound_accepted": [BOUND] * 6,  # rows 14-15
    "bound_in_progress": [BOUND] * 6,
    "bound_after_completion": [BOUND] * 6,
    "nonexistent": [A404] * 6,  # row 4
    "cross_tenant": [A404] * 6,  # row 4
}


def _decide(p: Principal, a: Action, w: WorkOrderFacts | None, **kw: object) -> Decision:
    return decide(p, a, now=NOW, wo=w, needs_wo=True, **kw)  # type: ignore[arg-type]


@pytest.mark.parametrize("row", list(REL_ROWS))
@pytest.mark.parametrize("via_me", [False, True])
def test_T_AUTH_6_contractor_relationship_matrix(row: str, via_me: bool) -> None:
    facts = REL_ROWS[row]
    for action, expected in zip(WO_ACTIONS, MARCO_EXPECTED[row], strict=True):
        is_offer_route = action in (Action.ACCEPT, Action.DECLINE)
        kw = {"path_cid": None if via_me else MARCO_C} if is_offer_route else {}
        if via_me and not is_offer_route:
            continue  # /me aliases exist only for schedule/accept/decline
        kw["via_me"] = via_me and is_offer_route  # type: ignore[assignment]
        assert _decide(MARCO, action, facts, **kw) == expected, (row, action, via_me)


def test_T_AUTH_6_relationship_classification() -> None:
    expect = {
        "stranger": "stranger",
        "queued_candidate": "stranger",
        "offeree": "offeree",
        "offeree_past_deadline_unswept": "past",
        "past_expired_not_reoffered": "past",
        "past_reassigned": "past",
        "past_declined": "past",
        "past_withdrawn": "past",
        "past_lost_race": "past",
        "bound_accepted": "bound",
        "bound_in_progress": "bound",
        "bound_after_completion": "bound",
    }
    for row, rel in expect.items():
        facts = REL_ROWS[row]
        assert facts is not None
        assert relationship(MARCO_C, facts, NOW) == rel, row
    # Exactly at the deadline is no longer a live offer.
    assert relationship(MARCO_C, wo(deadline=NOW), NOW) == "past"
    assert relationship(MARCO_C, wo(deadline=None), NOW) == "past"


@pytest.mark.parametrize("row", [r for r in REL_ROWS if r not in {"nonexistent", "cross_tenant"}])
def test_T_AUTH_6_owner_and_fm_same_tenant_read_only(row: str) -> None:
    """Rows 5-6 (D10 H-1, C-3): read allowed, every mutation 403 — T-AUTH-16 policy half."""
    facts = REL_ROWS[row]
    for owner in (OWNER, FM):
        for action in WO_ACTIONS:
            kw = {"path_cid": MARCO_C} if action in (Action.ACCEPT, Action.DECLINE) else {}
            contractor = ContractorFacts(MARCO_C, MIDTOWN)
            got = _decide(owner, action, facts, contractor=contractor, **kw)
            want = Allow(AllowedAs.OWNER) if action is Action.GET_WO else A403
            assert got == want, (owner.role, row, action)


def test_T_AUTH_16_owner_without_contractor_id_on_me_routes() -> None:
    for owner in (OWNER, FM):
        for action in (Action.SCHEDULE, Action.ACCEPT, Action.DECLINE):
            facts = None if action is Action.SCHEDULE else REL_ROWS["offeree"]
            assert (
                decide(owner, action, now=NOW, via_me=True, wo=facts, needs_wo=facts is not None)
                == A403
            )


def test_T_AUTH_6_owner_other_tenant_gets_404_for_everything() -> None:
    contractor = ContractorFacts(MARCO_C, MIDTOWN)
    for action in WO_ACTIONS:
        kw = {"path_cid": MARCO_C} if action in (Action.ACCEPT, Action.DECLINE) else {}
        got = _decide(OTHER_OWNER, action, REL_ROWS["offeree"], contractor=contractor, **kw)
        assert got == A404, action
    sched = decide(OTHER_OWNER, Action.SCHEDULE, now=NOW, path_cid=MARCO_C, contractor=contractor)
    assert sched == A404


def test_T_AUTH_6_schedule() -> None:
    own = decide(MARCO, Action.SCHEDULE, now=NOW, path_cid=MARCO_C)
    me = decide(MARCO, Action.SCHEDULE, now=NOW, via_me=True)
    assert own == me == Allow(AllowedAs.SELF)  # row 7
    owner = decide(
        OWNER,
        Action.SCHEDULE,
        now=NOW,
        path_cid=MARCO_C,
        contractor=ContractorFacts(MARCO_C, MIDTOWN),
    )
    assert owner == Allow(AllowedAs.OWNER)  # row 5


@pytest.mark.parametrize(
    ("principal", "cid", "contractor"),
    [
        (MARCO, ANA_C, ContractorFacts(ANA_C, MIDTOWN)),  # same tenant
        (MARCO, ZED_C, ContractorFacts(ZED_C, OTHER)),  # other tenant
        (MARCO, uuid4(), None),  # nonexistent
        (ZED, MARCO_C, ContractorFacts(MARCO_C, MIDTOWN)),
    ],
)
def test_T_AUTH_15_contractor_on_other_cid_is_403_before_any_lookup(
    principal: Principal, cid: UUID, contractor: ContractorFacts | None
) -> None:
    """Row 2 (D10 M-1, C-1): identical 403 whatever cid is; for every action on that path."""
    for action in (Action.SCHEDULE, Action.ACCEPT, Action.DECLINE):
        for facts in (REL_ROWS["offeree"], REL_ROWS["nonexistent"], REL_ROWS["cross_tenant"]):
            got = decide(
                principal,
                action,
                now=NOW,
                path_cid=cid,
                contractor=contractor,
                wo=facts,
                needs_wo=action is not Action.SCHEDULE,
            )
            assert got == A403, (action, cid)


def test_T_AUTH_15_owner_on_unknown_or_cross_tenant_cid_is_404() -> None:
    for contractor in (None, ContractorFacts(ZED_C, OTHER)):
        got = decide(OWNER, Action.SCHEDULE, now=NOW, path_cid=ZED_C, contractor=contractor)
        assert got == A404


def test_T_AUTH_15_contractor_404_rows_are_indistinguishable() -> None:
    """Nonexistent, cross-tenant, stranger and queued-candidate WOs give the same decision for
    every action (and the HTTP layer maps a decision to one fixed body)."""
    rows = ["nonexistent", "cross_tenant", "stranger", "queued_candidate"]
    for action in WO_ACTIONS:
        decisions = {_decide(MARCO, action, REL_ROWS[r]) for r in rows}
        assert decisions == {A404}, action


def test_dispatch_create_is_owner_or_fm_only() -> None:
    assert decide(MARCO, Action.DISPATCH_CREATE, now=NOW) == A403
    assert decide(OWNER, Action.DISPATCH_CREATE, now=NOW) == Allow(AllowedAs.OWNER)
    assert decide(FM, Action.DISPATCH_CREATE, now=NOW) == Allow(AllowedAs.OWNER)


def test_ana_is_never_allowed_on_marcos_live_offer() -> None:
    """Ana as a past candidate (expired, then re-offered to Marco) gets the gate's 409."""
    facts = replace(REL_ROWS["offeree"], candidate_state="EXPIRED")  # type: ignore[type-var]
    for action in (Action.ACCEPT, Action.DECLINE):
        got = decide(ANA, action, now=NOW, path_cid=ANA_C, wo=facts, needs_wo=True)
        assert got == u409(R.REASSIGNED)

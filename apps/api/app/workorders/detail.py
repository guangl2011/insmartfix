"""`WorkOrderDetail` read model (spec §5; FR-3.5, FR-3.6, FR-4.1).

`build_detail()` is the single builder used by accept (synchronous packet, FR-3.6) and, from M2-T2,
by `GET /workorders/{wo}`. The decision and packet come from a `DecisionSource`; until M2-T1 wires
the stub engine, `NullDecisionSource` returns the honest no-history state: symptom-only decision,
`pre_diagnostic_available=false`, no packet, no predicted code (FR-3.4).

FR-3.5: the contractor variant is `WorkOrderDetail`, which has no `ranked_candidates` field at
all; only the owner/FM variant `OwnerWorkOrderDetail` carries it.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contract.workorders import (
    CandidateState,
    Decision,
    LifecycleEvent,
    LifecycleEventType,
    OwnerWorkOrderDetail,
    Packet,
    RankedCandidate,
    WorkOrderDetail,
)
from app.db.models import Contractor, DispatchCandidate, MemoryEvent
from app.workorders.summary import NullTeaserSource, TeaserSource, summary_for_workorder

NO_HISTORY_SUMMARY = "No history on this asset yet."


@dataclass(frozen=True)
class AssetDecision:
    decision: Decision
    packet: Packet | None
    predicted_failure_code: str | None


class DecisionSource(Protocol):
    def decision(self, asset_id: UUID, symptom: str) -> AssetDecision: ...


class NullDecisionSource:
    """No packet for any asset (FR-3.4): symptom-only, nothing fabricated."""

    def decision(self, asset_id: UUID, symptom: str) -> AssetDecision:
        return AssetDecision(Decision(evidence_summary=NO_HISTORY_SUMMARY), None, None)


def lifecycle_history(db: Session, wo_id: UUID) -> list[LifecycleEvent]:
    rows = db.execute(
        select(MemoryEvent)
        .where(MemoryEvent.wo_id == wo_id, MemoryEvent.type.in_(("ADVANCE", "CORRECTION")))
        .order_by(MemoryEvent.at, MemoryEvent.id)
    ).scalars()
    return [
        LifecycleEvent(
            event_id=e.id,
            type=LifecycleEventType(e.type),
            stage=e.stage,
            corrects_event_id=e.corrects_event_id,
            actor_user_id=e.actor_user_id,
            at=e.at,
        )
        for e in rows
    ]


def ranked_candidates(db: Session, wo_id: UUID) -> list[RankedCandidate]:
    rows = db.execute(
        select(DispatchCandidate, Contractor.name)
        .join(Contractor, Contractor.id == DispatchCandidate.contractor_id)
        .where(DispatchCandidate.wo_id == wo_id)
        .order_by(DispatchCandidate.rank)
    ).all()
    return [
        RankedCandidate(
            contractor_id=c.contractor_id,
            name=name,
            rank=c.rank,
            match_score=float(c.match_score),
            match_reason=c.match_reason,
            state=CandidateState(c.state),
        )
        for c, name in rows
    ]


def build_detail(
    db: Session,
    wo_id: UUID,
    *,
    contractor_id: UUID | None,
    owner_view: bool,
    now: datetime,
    decisions: DecisionSource | None = None,
    teasers: TeaserSource | None = None,
) -> WorkOrderDetail:
    """The detail for one WO. `owner_view=True` returns `OwnerWorkOrderDetail` (owner/FM only);
    otherwise the contractor variant, summarised from `contractor_id`'s own candidate row."""
    row = summary_for_workorder(db, wo_id, contractor_id, teasers or NullTeaserSource())
    if row is None:
        raise LookupError(wo_id)
    s = row.summary
    d = (decisions or NullDecisionSource()).decision(s.asset.id, s.symptom)
    base = {
        **s.model_dump(),
        "decision": d.decision,
        "pre_diagnostic_available": d.packet is not None,
        "packet": d.packet,
        "lifecycle_history": lifecycle_history(db, wo_id),
        "predicted_failure_code": d.predicted_failure_code,
        "server_time": now,
    }
    if owner_view:
        return OwnerWorkOrderDetail(**base, ranked_candidates=ranked_candidates(db, wo_id))
    return WorkOrderDetail(**base)

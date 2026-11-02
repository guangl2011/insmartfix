"""`OfferSummary` read model (spec §5; FR-2.1 to FR-2.3, FR-2.8).

One query for the work orders, one for their lifecycle events. The packet teaser and health/risk
come from a `TeaserSource` (the decision engine adapter, M2-T1); until it is wired in, the
`NullTeaserSource` gives an empty teaser and no score, which is the honest no-packet state.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contract.schedule import (
    AssetRef,
    DispatchState,
    FailureRisk,
    LifecycleStage,
    OfferSummary,
    SiteRef,
    Teaser,
    WoSource,
)
from app.db.models import Asset, Dispatch, DispatchCandidate, MemoryEvent, Site, WorkOrder
from app.workorders.lifecycle import LifecycleEventRow, LifecycleState, fold


@dataclass(frozen=True)
class AssetTeaser:
    teaser: Teaser
    health_score: int | None = None
    failure_risk: FailureRisk | None = None


class TeaserSource(Protocol):
    def teaser(self, asset_id: UUID) -> AssetTeaser: ...


class NullTeaserSource:
    def teaser(self, asset_id: UUID) -> AssetTeaser:
        return AssetTeaser(Teaser())


@dataclass(frozen=True)
class SummaryRow:
    """A work order seen by one contractor (their candidate row supplies match score/reason)."""

    summary: OfferSummary
    candidate_state: str
    accepted_at: datetime | None


def lifecycle_states(db: Session, wo_ids: Sequence[UUID]) -> dict[UUID, LifecycleState]:
    if not wo_ids:
        return {}
    by_wo: dict[UUID, list[LifecycleEventRow]] = defaultdict(list)
    for e in db.execute(
        select(
            MemoryEvent.wo_id,
            MemoryEvent.id,
            MemoryEvent.type,
            MemoryEvent.stage,
            MemoryEvent.corrects_event_id,
            MemoryEvent.at,
        ).where(MemoryEvent.wo_id.in_(wo_ids), MemoryEvent.type.in_(("ADVANCE", "CORRECTION")))
    ):
        by_wo[e.wo_id].append(LifecycleEventRow(e.id, e.type, e.stage, e.corrects_event_id, e.at))
    return {wo: fold(by_wo.get(wo, [])) for wo in wo_ids}


def summaries_for_contractor(
    db: Session,
    contractor_id: UUID,
    *,
    dispatch_states: Sequence[str],
    teasers: TeaserSource,
    only_current: bool = True,
) -> list[SummaryRow]:
    """Work orders whose dispatch is in `dispatch_states` and (by default) currently held by
    `contractor_id`, each summarised from that contractor's candidate row."""
    q = (
        select(WorkOrder, Asset, Site, Dispatch, DispatchCandidate)
        .join(Asset, Asset.id == WorkOrder.asset_id)
        .join(Site, Site.id == Asset.site_id)
        .join(Dispatch, Dispatch.wo_id == WorkOrder.id)
        .join(
            DispatchCandidate,
            (DispatchCandidate.wo_id == WorkOrder.id)
            & (DispatchCandidate.contractor_id == contractor_id),
        )
        .where(Dispatch.state.in_(dispatch_states))
    )
    if only_current:
        q = q.where(Dispatch.current_contractor_id == contractor_id)
    rows = db.execute(q).all()
    states = lifecycle_states(db, [r.WorkOrder.id for r in rows])
    out = []
    for wo, asset, site, dispatch, cand in rows:
        t = teasers.teaser(asset.id)
        life = states[wo.id]
        out.append(
            SummaryRow(
                OfferSummary(
                    wo_id=wo.id,
                    asset=AssetRef(id=asset.id, name=asset.name, subtype=asset.subtype),
                    site=SiteRef(name=site.name, location=site.location or ""),
                    symptom=wo.symptom,
                    wo_source=WoSource(wo.wo_source),
                    dispatch_state=DispatchState(dispatch.state),
                    lifecycle_stage=LifecycleStage(life.stage) if life.stage else None,
                    sla_deadline=dispatch.sla_deadline if dispatch.state == "PENDING" else None,
                    match_score=float(cand.match_score),
                    match_reason=cand.match_reason,
                    teaser=t.teaser,
                    health_score=t.health_score,
                    failure_risk=t.failure_risk,
                    last_advanced_at=life.last_advanced_at,
                ),
                candidate_state=cand.state,
                accepted_at=cand.responded_at if cand.state == "ACCEPTED" else None,
            )
        )
    return out

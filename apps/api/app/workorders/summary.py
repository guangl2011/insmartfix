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
    return [
        build_row(wo, asset, site, dispatch, cand, states[wo.id], teasers)
        for wo, asset, site, dispatch, cand in rows
    ]


def build_row(
    wo: WorkOrder,
    asset: Asset,
    site: Site,
    dispatch: Dispatch,
    cand: DispatchCandidate | None,
    life: LifecycleState,
    teasers: TeaserSource,
) -> SummaryRow:
    t = teasers.teaser(asset.id)
    return SummaryRow(
        OfferSummary(
            wo_id=wo.id,
            asset=AssetRef(id=asset.id, name=asset.name, subtype=asset.subtype),
            site=SiteRef(name=site.name, location=site.location or ""),
            symptom=wo.symptom,
            wo_source=WoSource(wo.wo_source),
            dispatch_state=DispatchState(dispatch.state),
            lifecycle_stage=LifecycleStage(life.stage) if life.stage else None,
            sla_deadline=dispatch.sla_deadline if dispatch.state == "PENDING" else None,
            match_score=float(cand.match_score) if cand else 0.0,
            match_reason=cand.match_reason if cand else "",
            teaser=t.teaser,
            health_score=t.health_score,
            failure_risk=t.failure_risk,
            last_advanced_at=life.last_advanced_at,
        ),
        candidate_state=cand.state if cand else "",
        accepted_at=cand.responded_at if cand and cand.state == "ACCEPTED" else None,
    )


def summary_for_workorder(
    db: Session, wo_id: UUID, contractor_id: UUID | None, teasers: TeaserSource
) -> SummaryRow | None:
    """One WO. Match score/reason come from `contractor_id`'s candidate row (a contractor sees
    only their own standing, FR-3.5); for owner/FM, from the current or top-ranked candidate."""
    row = db.execute(
        select(WorkOrder, Asset, Site, Dispatch)
        .join(Asset, Asset.id == WorkOrder.asset_id)
        .join(Site, Site.id == Asset.site_id)
        .join(Dispatch, Dispatch.wo_id == WorkOrder.id)
        .where(WorkOrder.id == wo_id)
    ).first()
    if row is None:
        return None
    wo, asset, site, dispatch = row
    who = contractor_id or dispatch.current_contractor_id
    cand_q = select(DispatchCandidate).where(DispatchCandidate.wo_id == wo_id)
    cand = (
        db.execute(cand_q.where(DispatchCandidate.contractor_id == who)).scalar_one_or_none()
        if who
        else db.execute(cand_q.order_by(DispatchCandidate.rank).limit(1)).scalar_one_or_none()
    )
    return build_row(wo, asset, site, dispatch, cand, lifecycle_states(db, [wo_id])[wo_id], teasers)

"""Create a dispatched work order (FR-10.1, spec §5 `POST /dispatch/workorders`).

Tenant-bounded on every input (D10 H-6): the asset must be in the caller's tenant (else
`AssetNotFoundError` → 404) and every candidate must be a contractor in the caller's tenant
(else `InvalidCandidatesError` → 422, without saying which id failed). The schema's composite
`(tenant_id, id)` foreign keys back this up. Role checks (owner/FM only) belong to the gate.

The work order snapshots the engine's predicted failure code at creation (D10 L-4).
"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Asset, Contractor, Dispatch, DispatchCandidate, WorkOrder


class AssetNotFoundError(Exception):
    """The asset doesn't exist or is in another tenant (same answer for both)."""


class InvalidCandidatesError(Exception):
    """A candidate is unknown, in another tenant, or listed twice."""


@dataclass(frozen=True)
class CandidateSpec:
    contractor_id: uuid.UUID
    match_score: float
    reason: str


@dataclass(frozen=True)
class DispatchSpec:
    asset_id: uuid.UUID
    symptom: str
    sla_minutes: int
    candidates: Sequence[CandidateSpec]  # ranked, best first


PredictFn = Callable[[Asset], str | None]


def no_prediction(_: Asset) -> str | None:
    return None


def create_dispatch(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    created_by_user_id: uuid.UUID | None,
    spec: DispatchSpec,
    now: datetime,
    predict: PredictFn = no_prediction,
) -> uuid.UUID:
    """Insert the WO, its ranked candidates and a PENDING offer to rank 1. Caller commits."""
    asset = session.scalar(
        select(Asset).where(Asset.id == spec.asset_id, Asset.tenant_id == tenant_id)
    )
    if asset is None:
        raise AssetNotFoundError

    ids = [c.contractor_id for c in spec.candidates]
    if not ids or len(set(ids)) != len(ids):
        raise InvalidCandidatesError
    in_tenant = set(
        session.scalars(
            select(Contractor.id).where(Contractor.tenant_id == tenant_id, Contractor.id.in_(ids))
        )
    )
    if in_tenant != set(ids):
        raise InvalidCandidatesError

    wo = WorkOrder(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        asset_id=asset.id,
        symptom=spec.symptom,
        wo_source="dispatch",
        status="OPEN",
        predicted_failure_code=predict(asset),
        created_by_user_id=created_by_user_id,
    )
    session.add(wo)
    session.flush()

    deadline = now + timedelta(minutes=spec.sla_minutes)
    for rank, c in enumerate(spec.candidates, start=1):
        first = rank == 1
        session.add(
            DispatchCandidate(
                wo_id=wo.id,
                contractor_id=c.contractor_id,
                tenant_id=tenant_id,
                rank=rank,
                match_score=Decimal(str(round(c.match_score, 3))),
                match_reason=c.reason,
                state="OFFERED" if first else "QUEUED",
                offered_at=now if first else None,
                sla_deadline=deadline if first else None,
            )
        )
    session.flush()

    session.add(
        Dispatch(
            wo_id=wo.id,
            tenant_id=tenant_id,
            state="PENDING",
            current_contractor_id=ids[0],
            sla_minutes=spec.sla_minutes,
            sla_deadline=deadline,
            version=0,
            updated_at=now,
        )
    )
    session.flush()
    return wo.id

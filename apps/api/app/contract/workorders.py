"""Work-order bodies (spec §5 WorkOrderDetail, transition, photos, CompletionReport; FR-3, 6, 7).

FR-3.5 schema split: `WorkOrderDetail` (contractor role) has **no** `ranked_candidates` field at
all; only `OwnerWorkOrderDetail` (owner/FM) carries it.
"""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.contract.common import RequestModel, ServerTimed
from app.contract.schedule import FailureRisk, LifecycleStage, OfferSummary


class EvidenceItem(BaseModel):
    kind: Literal["event", "maintenance", "insight"]
    summary: str
    at: datetime | None = None


class Decision(BaseModel):
    """Decision summary (FR-3.2). Without a packet: symptom-only, no cause or action (FR-3.4)."""

    health_score: int | None = Field(default=None, ge=0, le=100)
    failure_risk: FailureRisk | None = None
    root_cause: str | None = None
    recommended_action: str | None = None
    evidence_summary: str = Field(description='e.g. "Based on 3 recent events + 2 active insights"')
    evidence: list[EvidenceItem] = Field(default_factory=list)


class AssetIdentity(BaseModel):
    name: str
    subtype: str
    make: str | None = None
    model: str | None = None
    install_year: int | None = None
    location: str | None = None
    duty: str | None = None


class PacketEvent(BaseModel):
    at: datetime
    kind: str
    summary: str


class MaintenanceRecord(BaseModel):
    at: datetime
    summary: str
    performed_by: str | None = None


class Insight(BaseModel):
    summary: str
    confidence: float | None = Field(default=None, ge=0, le=1)


class PredictedPart(BaseModel):
    description: str
    part_code: str | None = None
    qty: int = Field(ge=1)
    likelihood: float | None = Field(default=None, ge=0, le=1)


class Packet(BaseModel):
    """Pre-diagnostic packet sections (FR-3.3)."""

    asset_identity: AssetIdentity
    recent_events: list[PacketEvent]
    recent_maintenance: list[MaintenanceRecord]
    active_insights: list[Insight]
    predicted_parts: list[PredictedPart]


class LifecycleEventType(StrEnum):
    ADVANCE = "ADVANCE"
    CORRECTION = "CORRECTION"


class LifecycleEvent(BaseModel):
    """One immutable lifecycle memory event (FR-6.1, FR-6.3)."""

    event_id: UUID
    type: LifecycleEventType
    stage: LifecycleStage | None = Field(default=None, description="Set on ADVANCE.")
    corrects_event_id: UUID | None = Field(default=None, description="Set on CORRECTION.")
    actor_user_id: UUID
    at: datetime


class WorkOrderDetail(OfferSummary, ServerTimed):
    """Contractor view (spec §5). Never includes `ranked_candidates` (FR-3.5)."""

    decision: Decision | None = None
    pre_diagnostic_available: bool
    packet: Packet | None = None
    lifecycle_history: list[LifecycleEvent]
    predicted_failure_code: str | None = None


class CandidateState(StrEnum):
    QUEUED = "QUEUED"
    OFFERED = "OFFERED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    WITHDRAWN = "WITHDRAWN"


class RankedCandidate(BaseModel):
    contractor_id: UUID
    name: str
    rank: int = Field(ge=1)
    match_score: float = Field(ge=0, le=1)
    match_reason: str
    state: CandidateState


class OwnerWorkOrderDetail(WorkOrderDetail):
    """Owner/FM view (FR-10.1): the contractor view plus the ranked candidate list."""

    ranked_candidates: list[RankedCandidate]


class TransitionAction(StrEnum):
    ADVANCE = "advance"
    UNDO = "undo"


class TransitionRequest(RequestModel):
    """`advance` needs `stage`. `undo` corrects `corrects_event_id`, or the latest advance (H-4)."""

    action: TransitionAction
    stage: LifecycleStage | None = None
    corrects_event_id: UUID | None = None


class TransitionResponse(ServerTimed):
    lifecycle_stage: LifecycleStage | None
    event_id: UUID
    history: list[LifecycleEvent]


class PhotoResponse(ServerTimed):
    photo_id: UUID


class PartUsed(RequestModel):
    part_code: str | None = Field(default=None, max_length=64)
    description: str = Field(min_length=1, max_length=200)
    qty: int = Field(ge=1, le=999)


class CompletionReport(RequestModel):
    """`POST /workorders/{wo}/complete` body (FR-7.1). Bounds per D10 M-8.

    Server-only values (`label`, `actor`, `at`, predicted code) are never accepted from the body.
    """

    failure_code: str = Field(min_length=1, max_length=64)
    actual_fault_matched: bool
    parts_used: list[PartUsed] = Field(default_factory=list, max_length=50)
    labor_hours: float = Field(gt=0, le=24, multiple_of=0.25)
    notes: str | None = Field(default=None, max_length=4000)
    technician_id: str = Field(min_length=1, max_length=120)
    photo_ids: list[UUID] = Field(default_factory=list, max_length=4)


class CalibrationLabel(StrEnum):
    MATCH = "MATCH"
    PARTIAL = "PARTIAL"
    MISS = "MISS"
    NO_PREDICTION = "NO_PREDICTION"


class CompletionResponse(ServerTimed):
    calibration_label: CalibrationLabel
    record_updated: Literal[True]

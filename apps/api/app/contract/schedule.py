"""Inbox / dispatch-offer bodies (spec §5 `OfferSummary`, schedule, accept/decline; FR-2, FR-4)."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.contract.common import RequestModel, ServerTimed


class DispatchState(StrEnum):
    """Dispatch states (spec §4.4). EXPIRED is per candidate, see `CandidateState`."""

    UNDISPATCHED = "UNDISPATCHED"
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ESCALATED = "ESCALATED"
    NO_CONTRACTORS = "NO_CONTRACTORS"


class LifecycleStage(StrEnum):
    """Derived from memory events (FR-6.1). Both sit inside backend `IN_PROGRESS`."""

    EN_ROUTE = "EN_ROUTE"
    ARRIVED = "ARRIVED"


class WoSource(StrEnum):
    """Where the work order came from. `voice` is the Voicequest seam (FR-2.1, D§14)."""

    DISPATCH = "dispatch"
    VOICE = "voice"


class FailureRisk(StrEnum):
    """Insmart failure-risk bands (COLOR_LANGUAGE §3)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AssetRef(BaseModel):
    id: UUID
    name: str
    subtype: str


class SiteRef(BaseModel):
    name: str
    location: str


class Teaser(BaseModel):
    """Packet teaser on the card: "Likely: X · NN% match" (FR-2.3). Empty when no packet."""

    likely_cause: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class OfferSummary(BaseModel):
    """One inbox card (spec §5 OfferSummary)."""

    wo_id: UUID
    asset: AssetRef
    site: SiteRef
    symptom: str
    wo_source: WoSource
    dispatch_state: DispatchState
    lifecycle_stage: LifecycleStage | None = None
    sla_deadline: datetime | None = None
    match_score: float = Field(ge=0, le=1, description="The caller's own match score, 0 to 1.")
    match_reason: str
    teaser: Teaser
    health_score: int | None = Field(default=None, ge=0, le=100)
    failure_risk: FailureRisk | None = None
    last_advanced_at: datetime | None = None


class ScheduleResponse(ServerTimed):
    """`GET /contractor/{cid}/schedule` and `GET /me/schedule` (FR-2.1, FR-2.2).

    `offers` sorted by soonest `sla_deadline`; `active` by most recent `last_advanced_at`.
    """

    offers: list[OfferSummary]
    active: list[OfferSummary]
    voice_bookings: list[OfferSummary] = Field(description="Always empty in v1 (FR-2.1).")


class DeclineReason(StrEnum):
    TOO_FAR = "too_far"
    NO_CAPACITY = "no_capacity"
    WRONG_SKILL = "wrong_skill"
    OTHER = "other"


class DeclineRequest(RequestModel):
    """Optional reason (FR-4.2); an empty body `{}` declines with no reason ("Skip")."""

    reason: DeclineReason | None = None
    note: str | None = Field(default=None, max_length=500)  # D10 L-5

"""Owner/FM dispatch-create bodies (spec §5 `POST /dispatch/workorders`, FR-10.1)."""

from uuid import UUID

from pydantic import Field

from app.contract.common import RequestModel, ServerTimed


class DispatchCandidateIn(RequestModel):
    contractor_id: UUID
    match_score: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=200)


class DispatchCreateRequest(RequestModel):
    asset_id: UUID
    symptom: str = Field(min_length=1, max_length=500)
    sla_minutes: int = Field(ge=1, le=1440)
    candidates: list[DispatchCandidateIn] = Field(
        min_length=1, max_length=20, description="Ranked best first; rank 1 is offered first."
    )


class DispatchCreateResponse(ServerTimed):
    wo_id: UUID

"""Auth and identity bodies (spec §5 `/auth/*`, `GET /me`; FR-1.1, FR-1.4; D11 logout)."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.contract.common import RequestModel, ServerTimed


class Role(StrEnum):
    CONTRACTOR = "contractor"
    OWNER = "owner"
    FM = "fm"


class LoginRequest(RequestModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class UserProfile(BaseModel):
    """The signed-in user. `contractor_id` is present only for the contractor role (FR-1.4)."""

    user_id: UUID
    name: str
    role: Role
    tenant_id: UUID
    contractor_id: UUID | None = None
    company: str | None = None


class MeResponse(UserProfile, ServerTimed):
    """`GET /me`."""


class LoginResponse(ServerTimed):
    """`POST /auth/login`. Web keeps `access_token` server-side in an httpOnly cookie (FR-1.2)."""

    access_token: str
    token_type: str = Field(default="bearer", description="Always `bearer`.")
    expires_at: datetime
    user: UserProfile

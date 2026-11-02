"""Shared contract primitives (spec §5): error envelope, `server_time`, request strictness.

Contract rule (IMPLEMENTATION_PLAN §0 rule 1): any change to a request/response shape edits the
models in `app/contract/`, re-exports `packages/contracts/openapi.json` and stays additive in `/v1`.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from fastapi import Header
from pydantic import BaseModel, ConfigDict, Field


class RequestModel(BaseModel):
    """Base for every request body. Unknown fields → 422 (D10 M-8, mass assignment)."""

    model_config = ConfigDict(extra="forbid")


class ServerTimed(BaseModel):
    """Base for every top-level JSON response body: spec §5 "every response includes server_time".

    Clients derive their clock offset from it (FR-2.4) to cancel device clock skew.
    """

    server_time: datetime = Field(description="Server clock at response time (ISO-8601 UTC).")


class ErrorCode(StrEnum):
    """Every `error.code` the API can return (spec §5; D12 adds IDEMPOTENCY_KEY_REUSED)."""

    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    RATE_LIMITED = "RATE_LIMITED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    OFFER_UNAVAILABLE = "OFFER_UNAVAILABLE"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    ALREADY_COMPLETED = "ALREADY_COMPLETED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    IDEMPOTENCY_KEY_REUSED = "IDEMPOTENCY_KEY_REUSED"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    NOT_READY = "NOT_READY"
    INTERNAL = "INTERNAL"


class OfferUnavailableReason(StrEnum):
    """`reason` on `409 OFFER_UNAVAILABLE` (spec §5). Never names another candidate (D10 Q1)."""

    EXPIRED = "expired"
    REASSIGNED = "reassigned"
    WITHDRAWN = "withdrawn"


class ErrorBody(BaseModel):
    code: ErrorCode
    message: str = Field(description="Human-readable text, safe to show to the user.")
    reason: OfferUnavailableReason | None = Field(
        default=None, description="Only on `OFFER_UNAVAILABLE`."
    )


class ErrorEnvelope(ServerTimed):
    """`{"error": {"code": "STRING", "message": "human text"}, "server_time": ...}` (spec §5)."""

    error: ErrorBody


# Mutations accept an `Idempotency-Key` header (spec §5, FR-6.4, FR-7.4). Scoped per user + route +
# target (D10 H-3, C-2); reuse with a different body → 422 IDEMPOTENCY_KEY_REUSED (D12).
IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9._:-]{8,128}$"
IdempotencyKeyHeader = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        pattern=IDEMPOTENCY_KEY_PATTERN,
        description=(
            "Client-generated key (e.g. a UUID) that makes a retry return the original result. "
            "Scoped to the caller, the route and its target. Reusing a key with a different body "
            "returns 422 IDEMPOTENCY_KEY_REUSED."
        ),
    ),
]


def error_responses(*statuses: int) -> dict[int | str, dict[str, object]]:
    """OpenAPI `responses` entries for the given error statuses, all using the envelope."""
    return {
        s: {"model": ErrorEnvelope, "description": ERROR_DESCRIPTIONS[s]} for s in sorted(statuses)
    }


ERROR_DESCRIPTIONS: dict[int, str] = {
    401: "UNAUTHENTICATED (or INVALID_CREDENTIALS on login): missing, invalid or revoked token",
    403: "FORBIDDEN: the caller may not perform this action",
    404: "NOT_FOUND: the target does not exist or is not visible to the caller",
    409: "Conflict: OFFER_UNAVAILABLE, INVALID_TRANSITION or ALREADY_COMPLETED",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR, or IDEMPOTENCY_KEY_REUSED for a reused key with a different body",
    429: "RATE_LIMITED",
    501: "NOT_IMPLEMENTED: route is declared in the contract but not built yet",
}

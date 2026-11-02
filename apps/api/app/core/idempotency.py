"""Scoped idempotency (spec §5, FR-6.4, FR-7.4; D10 H-3, C-2; D12).

A record is keyed by **(caller user_id, scope, key)**, where scope is the route template plus its
target id (e.g. `POST /v1/workorders/{wo}/complete#<wo>`), and stores a SHA-256 of the canonical
request body. A lookup never crosses users or scopes. Same hash → replay the original result;
different hash → `422 IDEMPOTENCY_KEY_REUSED`, and the stored result is never returned.

Persistence (`idempotency_records`, M1-T2) is used by each mutation's handler through
`IdempotencyRequest.check()`.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.contract.common import ErrorCode
from app.core.errors import ApiError


def canonical_hash(body: BaseModel | dict[str, Any] | list[Any] | None) -> str:
    """SHA-256 of the body as canonical JSON (sorted keys, no whitespace), so a retry with the
    same values hashes the same regardless of key order or formatting."""
    data = body.model_dump(mode="json") if isinstance(body, BaseModel) else body
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def bytes_hash(data: bytes) -> str:
    """SHA-256 of raw bytes (photo uploads hash the file digest, D10 H-3)."""
    return hashlib.sha256(data).hexdigest()


def scope_for(method: str, route_template: str, target_id: UUID | str) -> str:
    return f"{method.upper()} {route_template}#{target_id}"


@dataclass(frozen=True)
class IdempotencyRequest:
    user_id: UUID
    scope: str
    key: str
    request_hash: str

    def check(self, stored_hash: str | None) -> bool:
        """Given the hash stored under (user_id, scope, key) — or None if there is no record —
        return True to replay the stored result, False to process the request fresh.
        Raises 422 IDEMPOTENCY_KEY_REUSED when the key was used with a different body (D12)."""
        if stored_hash is None:
            return False
        if stored_hash != self.request_hash:
            raise ApiError(422, ErrorCode.IDEMPOTENCY_KEY_REUSED)
        return True


def idempotency_request(
    *,
    key: str | None,
    user_id: UUID,
    method: str,
    route_template: str,
    target_id: UUID | str,
    request_hash: str,
) -> IdempotencyRequest | None:
    """Build the scoped request, or None when the client sent no `Idempotency-Key`."""
    if key is None:
        return None
    return IdempotencyRequest(
        user_id=user_id,
        scope=scope_for(method, route_template, target_id),
        key=key,
        request_hash=request_hash,
    )

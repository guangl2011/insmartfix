"""Persistence for scoped idempotency records (`idempotency_records`, D10 H-3, D12).

Replay returns the stored status + body; a different body under the same (user, scope, key) is
`422 IDEMPOTENCY_KEY_REUSED` (raised by `IdempotencyRequest.check`). Callers hold a lock that
serialises requests on the same target before calling `lookup`, so check-then-insert is safe.
"""

import hashlib
from dataclasses import dataclass
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.core.idempotency import IdempotencyRequest
from app.db.models import IdempotencyRecord


@dataclass(frozen=True)
class StoredResponse:
    status: int
    body: dict[str, Any]


def lookup(db: Session, req: IdempotencyRequest) -> StoredResponse | None:
    row = db.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == req.user_id,
            IdempotencyRecord.scope == req.scope,
            IdempotencyRecord.key == req.key,
        )
    ).scalar_one_or_none()
    if row is None or not req.check(row.request_hash):
        return None
    return StoredResponse(row.response_status or 200, dict(row.response_ref or {}))


def save(db: Session, req: IdempotencyRequest, status: int, body: dict[str, Any]) -> None:
    db.execute(
        insert(IdempotencyRecord).values(
            user_id=req.user_id,
            scope=req.scope,
            key=req.key,
            request_hash=req.request_hash,
            response_status=status,
            response_ref=body,
        )
    )


def scoped_event_key(req: IdempotencyRequest) -> str:
    """The value stored in `memory_events.idempotency_key`. That column is unique per actor
    (C-2), so it must carry the scope too: the same client key on another WO is a different
    request (T-IDEM-1)."""
    return hashlib.sha256(f"{req.scope}\x1f{req.key}".encode()).hexdigest()

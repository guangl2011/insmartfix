"""`MemorySeam`: the only way to write `memory_events` (plan rule 3; FR-6.1, FR-6.3, FR-7.5).

Append-only by construction: the interface has no update or delete, and the runtime DB role has
only `INSERT, SELECT` on the table (D10 H-5, T-MEM-2). A correction is a new event naming the
event it voids. `actor` and `at` always come from the principal and `app.clock`, never a body.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True)
class NewEvent:
    tenant_id: UUID
    asset_id: UUID
    wo_id: UUID
    type: str  # ADVANCE | CORRECTION | OUTCOME
    actor_user_id: UUID
    at: datetime
    stage: str | None = None
    corrects_event_id: UUID | None = None
    idempotency_key: str | None = None  # already scoped by the caller (D10 H-3, C-2)
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StoredEvent:
    id: UUID
    wo_id: UUID
    type: str
    stage: str | None
    corrects_event_id: UUID | None
    actor_user_id: UUID
    at: datetime


class MemorySeam(Protocol):
    def append(self, event: NewEvent) -> UUID: ...
    def list(self, wo_id: UUID) -> list[StoredEvent]: ...

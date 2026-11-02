"""Postgres `MemorySeam` over `memory_events` (insert + select only)."""

from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.db.models import MemoryEvent
from app.memory.seam import NewEvent, StoredEvent


class PostgresMemorySeam:
    def __init__(self, db: Session) -> None:
        self.db = db

    def append(self, event: NewEvent) -> UUID:
        new_id = self.db.execute(
            insert(MemoryEvent)
            .values(
                tenant_id=event.tenant_id,
                asset_id=event.asset_id,
                wo_id=event.wo_id,
                type=event.type,
                stage=event.stage,
                payload=event.payload,
                actor_user_id=event.actor_user_id,
                at=event.at,
                idempotency_key=event.idempotency_key,
                corrects_event_id=event.corrects_event_id,
            )
            .returning(MemoryEvent.id)
        ).scalar_one()
        assert isinstance(new_id, UUID)  # noqa: S101
        return new_id

    def list(self, wo_id: UUID) -> list[StoredEvent]:
        rows = self.db.execute(
            select(MemoryEvent)
            .where(MemoryEvent.wo_id == wo_id)
            .order_by(MemoryEvent.at, MemoryEvent.id)
        ).scalars()
        return [
            StoredEvent(e.id, e.wo_id, e.type, e.stage, e.corrects_event_id, e.actor_user_id, e.at)
            for e in rows
        ]

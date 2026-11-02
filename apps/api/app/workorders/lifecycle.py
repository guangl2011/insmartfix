"""Lifecycle derivation by folding immutable memory events (FR-6.1, FR-6.3).

The current stage is the stage of the latest ADVANCE that no CORRECTION has voided. History is
never mutated; an undo is a new CORRECTION event naming the advance it voids.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class LifecycleEventRow:
    id: UUID
    type: str  # ADVANCE | CORRECTION | OUTCOME
    stage: str | None
    corrects_event_id: UUID | None
    at: datetime


@dataclass(frozen=True)
class LifecycleState:
    stage: str | None
    last_advanced_at: datetime | None
    latest_advance_id: UUID | None


def fold(events: Iterable[LifecycleEventRow]) -> LifecycleState:
    rows = sorted(events, key=lambda e: (e.at, str(e.id)))
    voided = {e.corrects_event_id for e in rows if e.type == "CORRECTION"}
    live = [e for e in rows if e.type == "ADVANCE" and e.id not in voided]
    if not live:
        return LifecycleState(None, None, None)
    last = live[-1]
    return LifecycleState(last.stage, last.at, last.id)

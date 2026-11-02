"""Lifecycle derivation by folding immutable memory events (FR-6.1, FR-6.3).

The current stage is the stage of the latest ADVANCE that no CORRECTION has voided. History is
never mutated; an undo is a new CORRECTION event naming the advance it voids.
"""

from collections.abc import Iterable, Sequence
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


# --- Transitions (FR-6.1, FR-6.3, FR-6.4; D10 H-4) ---------------------------------------------

NEXT_STAGE: dict[str | None, str] = {None: "EN_ROUTE", "EN_ROUTE": "ARRIVED"}


@dataclass(frozen=True)
class EventView:
    """What the transition rules need about each lifecycle event of one WO."""

    id: UUID
    type: str
    stage: str | None
    corrects_event_id: UUID | None
    actor_user_id: UUID
    at: datetime


class TransitionRefusedError(Exception):
    """→ 409 INVALID_TRANSITION."""


def check_advance(events: Sequence[EventView], stage: str | None, completed: bool) -> str:
    """Advance only to the next stage in order (no ARRIVED before EN_ROUTE, no repeats)."""
    if completed or stage is None:
        raise TransitionRefusedError
    current = fold(_rows(events)).stage
    if NEXT_STAGE.get(current) != stage:
        raise TransitionRefusedError
    return stage


def undo_target(
    events: Sequence[EventView], corrects_event_id: UUID | None, actor: UUID, completed: bool
) -> EventView:
    """D10 H-4. The target must be on this WO (only this WO's events are passed in), be an
    ADVANCE (never a CORRECTION or outcome), be the latest advance not yet corrected, have been
    authored by the same actor, and the WO must not be completed. With no id given, the server
    picks the latest uncorrected advance."""
    if completed:
        raise TransitionRefusedError
    state = fold(_rows(events))
    if state.latest_advance_id is None:
        raise TransitionRefusedError
    if corrects_event_id is not None and corrects_event_id != state.latest_advance_id:
        raise TransitionRefusedError  # another WO's event, a correction, a non-latest or voided one
    target = next(e for e in events if e.id == state.latest_advance_id)
    if target.actor_user_id != actor:
        raise TransitionRefusedError
    return target


def _rows(events: Sequence[EventView]) -> list[LifecycleEventRow]:
    return [LifecycleEventRow(e.id, e.type, e.stage, e.corrects_event_id, e.at) for e in events]

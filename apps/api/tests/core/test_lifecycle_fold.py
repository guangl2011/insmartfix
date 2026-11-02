"""Lifecycle derivation fold (FR-6.1, FR-6.3): corrections void advances; history untouched."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.workorders.lifecycle import (
    EventView,
    LifecycleEventRow,
    TransitionRefusedError,
    check_advance,
    fold,
    undo_target,
)

T = datetime(2026, 11, 2, 9, tzinfo=UTC)


def adv(stage: str, minutes: int) -> LifecycleEventRow:
    return LifecycleEventRow(uuid4(), "ADVANCE", stage, None, T + timedelta(minutes=minutes))


def corr(target: LifecycleEventRow, minutes: int) -> LifecycleEventRow:
    return LifecycleEventRow(uuid4(), "CORRECTION", None, target.id, T + timedelta(minutes=minutes))


def test_empty_history_has_no_stage() -> None:
    s = fold([])
    assert (s.stage, s.last_advanced_at, s.latest_advance_id) == (None, None, None)


def test_latest_live_advance_wins_regardless_of_input_order() -> None:
    a, b = adv("EN_ROUTE", 0), adv("ARRIVED", 5)
    s = fold([b, a])
    assert (s.stage, s.last_advanced_at, s.latest_advance_id) == ("ARRIVED", b.at, b.id)


def test_correction_voids_its_advance() -> None:
    a, b = adv("EN_ROUTE", 0), adv("ARRIVED", 5)
    s = fold([a, b, corr(b, 6)])
    assert (s.stage, s.latest_advance_id) == ("EN_ROUTE", a.id)
    assert fold([a, corr(a, 1)]).stage is None


def test_outcome_events_are_ignored() -> None:
    a = adv("EN_ROUTE", 0)
    outcome = LifecycleEventRow(uuid4(), "OUTCOME", None, None, T + timedelta(hours=1))
    assert fold([a, outcome]).stage == "EN_ROUTE"


def _view(row: LifecycleEventRow, actor: object) -> EventView:
    return EventView(row.id, row.type, row.stage, row.corrects_event_id, actor, row.at)  # type: ignore[arg-type]


def test_T_LIFE_5_undo_requires_the_same_actor_and_a_live_target() -> None:
    marco, ana = uuid4(), uuid4()
    a = adv("EN_ROUTE", 0)
    events = [_view(a, marco)]
    assert undo_target(events, None, marco, completed=False).id == a.id
    with pytest.raises(TransitionRefusedError):
        undo_target(events, None, ana, completed=False)  # another actor's event
    with pytest.raises(TransitionRefusedError):
        undo_target([], None, marco, completed=False)  # nothing to undo
    with pytest.raises(TransitionRefusedError):
        undo_target(events, None, marco, completed=True)


def test_T_LIFE_3_advance_order() -> None:
    a = adv("EN_ROUTE", 0)
    assert check_advance([], "EN_ROUTE", completed=False) == "EN_ROUTE"
    assert check_advance([_view(a, uuid4())], "ARRIVED", completed=False) == "ARRIVED"
    for events, stage in (([], "ARRIVED"), ([_view(a, uuid4())], "EN_ROUTE"), ([], None)):
        with pytest.raises(TransitionRefusedError):
            check_advance(events, stage, completed=False)

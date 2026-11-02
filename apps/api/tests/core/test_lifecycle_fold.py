"""Lifecycle derivation fold (FR-6.1, FR-6.3): corrections void advances; history untouched."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.workorders.lifecycle import LifecycleEventRow, fold

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

"""app.clock: injectable server clock (plan §0 rule 6, FR-2.4, D10 H-7)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from app.clock import FakeClockDisabledError, clock, now, wall_now

AT = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


@pytest.fixture
def fake() -> Iterator[None]:
    clock.enable_fake(True)
    yield
    clock.enable_fake(False)


def test_real_clock_is_utc_aware() -> None:
    clock.enable_fake(False)
    t = now()
    assert t.tzinfo is not None
    assert abs((t - wall_now()).total_seconds()) < 5


def test_moving_the_clock_is_refused_when_fake_mode_is_off() -> None:
    clock.enable_fake(False)
    with pytest.raises(FakeClockDisabledError):
        clock.set(AT)
    with pytest.raises(FakeClockDisabledError):
        clock.advance(timedelta(1))
    with pytest.raises(FakeClockDisabledError):
        clock.reset()


@pytest.mark.usefixtures("fake")
def test_set_freezes_and_advance_moves_frozen_time() -> None:
    clock.set(AT)
    assert clock.frozen
    assert now() == AT
    clock.advance(timedelta(minutes=12))
    assert now() == AT + timedelta(minutes=12)


@pytest.mark.usefixtures("fake")
def test_advance_without_freeze_offsets_real_time_and_reset_restores() -> None:
    clock.advance(timedelta(hours=2))
    assert not clock.frozen
    assert (now() - wall_now()) > timedelta(hours=1, minutes=59)
    clock.reset()
    assert abs((now() - wall_now()).total_seconds()) < 5


@pytest.mark.usefixtures("fake")
def test_wall_clock_is_never_moved() -> None:
    clock.set(AT - timedelta(days=3650))
    assert wall_now().year >= 2026


@pytest.mark.usefixtures("fake")
def test_naive_datetime_rejected_and_other_zones_normalised() -> None:
    with pytest.raises(ValueError, match="timezone"):
        clock.set(datetime(2026, 1, 1))
    clock.set(datetime(2026, 1, 1, 10, tzinfo=UTC).astimezone())
    assert now().tzinfo == UTC

"""Server clock (IMPLEMENTATION_PLAN §0 rule 6). Domain code reads time only through `now()`.

Every response carries `server_time` from this clock (spec §5, FR-2.4). In test environments
(`FAKE_CLOCK=1` and `ENV in {local,test,ci}`, D10 H-7) the app enables the fake mode and
`POST /__test/clock` (`app/testing/`) can freeze or move it. Security decisions that must not be
movable, such as JWT `exp`, use `wall_now()` instead (D10 H-7, M-5).
"""

import threading
from datetime import UTC, datetime, timedelta


class FakeClockDisabledError(RuntimeError):
    """Raised when something tries to move the clock while fake mode is off."""


class _Clock:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._enabled = False
        self._frozen: datetime | None = None
        self._offset = timedelta(0)

    def now(self) -> datetime:
        with self._lock:
            if self._frozen is not None:
                return self._frozen
            return datetime.now(UTC) + self._offset

    def enable_fake(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = enabled
            self._frozen = None
            self._offset = timedelta(0)

    @property
    def fake_enabled(self) -> bool:
        return self._enabled

    @property
    def frozen(self) -> bool:
        return self._frozen is not None

    def set(self, at: datetime) -> None:
        """Freeze the clock at `at` (must be timezone-aware)."""
        if at.tzinfo is None:
            raise ValueError("fake clock needs a timezone-aware datetime")
        with self._lock:
            self._require_enabled()
            self._frozen = at.astimezone(UTC)

    def advance(self, delta: timedelta) -> None:
        """Move the clock forward (or back); keeps it frozen if it was frozen."""
        with self._lock:
            self._require_enabled()
            if self._frozen is not None:
                self._frozen += delta
            else:
                self._offset += delta

    def reset(self) -> None:
        """Back to real time (fake mode stays enabled)."""
        with self._lock:
            self._require_enabled()
            self._frozen = None
            self._offset = timedelta(0)

    def _require_enabled(self) -> None:
        if not self._enabled:
            raise FakeClockDisabledError("FAKE_CLOCK is not enabled in this environment")


clock = _Clock()


def now() -> datetime:
    """Current server time (UTC, aware). Movable in test environments only."""
    return clock.now()


def wall_now() -> datetime:
    """Real wall-clock time; never affected by the fake clock."""
    return datetime.now(UTC)

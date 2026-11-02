"""Server clock. Every response carries `server_time` (spec §5).

M1 adds the FAKE_CLOCK-controlled offset behind `POST /__test/clock`.
"""

from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)

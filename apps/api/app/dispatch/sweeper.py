"""Background SLA sweeper (FR-5.2): every 15 s, single-flight across instances.

Each tick runs in one transaction that first takes `pg_try_advisory_xact_lock`; if another
instance holds it the tick is skipped. Time comes from `app.clock`, so tests can drive it.
"""

import logging
import threading

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.clock import now
from app.dispatch.expiry import expire_due

logger = logging.getLogger(__name__)

SWEEPER_LOCK_KEY = 0x1F5_0001  # arbitrary, fixed: "InsmartFix SLA sweeper"


def sweep_once(engine: Engine) -> int | None:
    """One tick. Returns the number of expired offers, or None if another sweeper had the lock."""
    with Session(engine) as db, db.begin():
        got = db.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": SWEEPER_LOCK_KEY})
        if not got.scalar_one():
            return None
        total = 0
        while True:
            n = expire_due(db, now())
            total += n
            if n == 0:
                return total


class Sweeper:
    def __init__(self, engine: Engine, interval_seconds: float) -> None:
        self.engine = engine
        self.interval = interval_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="sla-sweeper", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=self.interval + 5)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                expired = sweep_once(self.engine)
                if expired:
                    logger.info("sla sweep", extra={"expired": expired})
            except Exception as exc:  # keep sweeping; a DB blip must not kill the thread
                logger.warning("sla sweep failed: %s", type(exc).__name__)

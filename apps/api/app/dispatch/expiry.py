"""SLA expiry (FR-5.1, FR-5.2). M1-T7 adds the lazy hook point; M1-T9 fills in `expire_due`."""

from datetime import datetime

from sqlalchemy.orm import Session


def expire_lazily(db: Session, now: datetime) -> None:
    """Called before any read or write that touches offers, so state is correct without the
    sweeper. No-op until M1-T9."""

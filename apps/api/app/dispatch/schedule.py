"""Contractor schedule (spec §5; FR-2.1, FR-2.2, FR-2.8).

Offers: live offers to the contractor (PENDING, current, candidate OFFERED, deadline in the future),
soonest `sla_deadline` first. Active: ACCEPTED / IN_PROGRESS jobs held by the contractor, most
recently advanced first (a job not advanced yet counts from when it was accepted).
`voice_bookings` is always empty in v1.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.contract.schedule import ScheduleResponse
from app.dispatch.expiry import expire_lazily
from app.workorders.summary import (
    NullTeaserSource,
    SummaryRow,
    TeaserSource,
    summaries_for_contractor,
)

_EPOCH = datetime.min.replace(tzinfo=UTC)


def _active_key(row: SummaryRow) -> datetime:
    return row.summary.last_advanced_at or row.accepted_at or _EPOCH


def build_schedule(
    db: Session, contractor_id: UUID, now: datetime, teasers: TeaserSource | None = None
) -> ScheduleResponse:
    expire_lazily(db, now)
    source = teasers or NullTeaserSource()
    offers = [
        r
        for r in summaries_for_contractor(
            db, contractor_id, dispatch_states=["PENDING"], teasers=source
        )
        if r.candidate_state == "OFFERED"
        and r.summary.sla_deadline is not None
        and r.summary.sla_deadline > now
    ]
    offers.sort(key=lambda r: (r.summary.sla_deadline, str(r.summary.wo_id)))
    active = summaries_for_contractor(
        db, contractor_id, dispatch_states=["ACCEPTED", "IN_PROGRESS"], teasers=source
    )
    active.sort(key=lambda r: (_active_key(r), str(r.summary.wo_id)), reverse=True)
    return ScheduleResponse(
        offers=[r.summary for r in offers],
        active=[r.summary for r in active],
        voice_bookings=[],
        server_time=now,
    )

"""Idempotent loader for the TEST_PLAN §5 fixtures (FR-10.2).

Runs as the runtime role, which can't delete or truncate, so the loader only inserts what is
missing. Re-running it never duplicates rows; it re-hashes the test passwords and refreshes the
deadlines of seed offers nobody has touched yet (still PENDING with rank 1), so countdowns are
current after a re-seed. Jobs that were accepted, advanced or completed are left as they are.
"""

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import (
    Asset,
    Contractor,
    DecisionPacket,
    Dispatch,
    DispatchCandidate,
    FailureCode,
    MemoryEvent,
    Site,
    Tenant,
    User,
    WorkOrder,
)
from app.seed import fixtures as fx
from app.seed import packets
from app.seed.failure_codes import FAILURE_CODES

HashFn = Callable[[str], str]


def load(session: Session, *, now: datetime, password: str, hash_password: HashFn) -> None:
    """Load every fixture. The caller commits."""
    _reference_data(session, password=password, hash_password=hash_password)
    _catalog(session)
    _packets(session, now)
    for offer in fx.OFFERS:
        _offer(session, offer, now)
    _active_jobs(session, now)
    session.flush()


def _reference_data(session: Session, *, password: str, hash_password: HashFn) -> None:
    for tid, name in fx.TENANTS:
        _add_missing(session, Tenant(id=tid, name=name))
    session.flush()
    for cid, tid, name, company, rating in fx.CONTRACTORS:
        _add_missing(
            session,
            Contractor(
                id=cid, tenant_id=tid, name=name, company=company, avg_rating=Decimal(rating)
            ),
        )
    session.flush()
    for uid, tid, email, name, role, user_cid in fx.USERS:
        user = session.get(User, uid)
        if user is None:
            user = User(
                id=uid, tenant_id=tid, email=email, name=name, role=role, contractor_id=user_cid
            )
            session.add(user)
        user.password_hash = hash_password(password)  # one salt per user and per run
    for sid, tid, name, location in fx.SITES:
        _add_missing(session, Site(id=sid, tenant_id=tid, name=name, location=location))
    session.flush()
    for a in fx.ASSETS:
        _add_missing(
            session,
            Asset(
                id=a.id,
                tenant_id=a.tenant_id,
                site_id=a.site_id,
                name=a.name,
                subtype=a.subtype,
                make=a.make,
                model=a.model,
                install_year=a.install_year,
                location=a.location,
                duty=a.duty,
            ),
        )
    session.flush()


def _catalog(session: Session) -> None:
    for subtype, codes in FAILURE_CODES.items():
        for order, (code, group, label) in enumerate(codes):
            row = session.get(FailureCode, (subtype, code))
            if row is None:
                row = FailureCode(subtype=subtype, code=code)
                session.add(row)
            row.component_group, row.label, row.sort_order = group, label, order
    session.flush()


def _packets(session: Session, now: datetime) -> None:
    """RTU-04 gets a full packet; AHU-NEW-01 deliberately has none (FR-3.4)."""
    decision, packet = packets.rtu04(now)
    row = session.get(DecisionPacket, fx.A_RTU04)
    if row is None:
        row = DecisionPacket(asset_id=fx.A_RTU04, tenant_id=fx.TENANT_MIDTOWN)
        session.add(row)
    row.predicted_failure_code = packets.RTU04_PREDICTED
    row.likely_cause = packets.RTU04_LIKELY_CAUSE
    row.confidence = Decimal(str(packets.RTU04_CONFIDENCE))
    row.decision, row.packet, row.updated_at = decision, packet, now
    session.flush()


def _offer(session: Session, offer: fx.OfferFixture, now: datetime) -> None:
    deadline = now + offer.remaining
    offered_at = deadline - timedelta(minutes=offer.sla_minutes)
    first = offer.candidates[0][0]
    if session.get(WorkOrder, offer.wo_id) is None:
        _work_order(session, offer.wo_id, offer.tenant_id, offer.asset_id, offer.symptom, "OPEN")
        for rank, (cid, score, reason) in enumerate(offer.candidates, start=1):
            session.add(
                DispatchCandidate(
                    wo_id=offer.wo_id,
                    contractor_id=cid,
                    tenant_id=offer.tenant_id,
                    rank=rank,
                    match_score=Decimal(score),
                    match_reason=reason,
                    state="OFFERED" if rank == 1 else "QUEUED",
                    offered_at=offered_at if rank == 1 else None,
                    sla_deadline=deadline if rank == 1 else None,
                )
            )
        session.flush()
        session.add(
            Dispatch(
                wo_id=offer.wo_id,
                tenant_id=offer.tenant_id,
                state="PENDING",
                current_contractor_id=first,
                sla_minutes=offer.sla_minutes,
                sla_deadline=deadline,
                version=0,
                updated_at=now,
            )
        )
        session.flush()
        return

    # Already seeded: refresh the countdown only if the offer is untouched.
    dispatch = session.get(Dispatch, offer.wo_id)
    candidate = session.get(DispatchCandidate, (offer.wo_id, first))
    if (
        dispatch is not None
        and candidate is not None
        and dispatch.state == "PENDING"
        and dispatch.current_contractor_id == first
        and candidate.state == "OFFERED"
    ):
        dispatch.sla_deadline = deadline
        dispatch.version += 1
        dispatch.updated_at = now
        candidate.offered_at = offered_at
        candidate.sla_deadline = deadline


def _active_jobs(session: Session, now: datetime) -> None:
    for (wo_id, asset_id, symptom, accepted_ago), state in (
        (fx.ACTIVE_ACCEPTED, "ACCEPTED"),
        (fx.ACTIVE_ARRIVED, "IN_PROGRESS"),
    ):
        if session.get(WorkOrder, wo_id) is not None:
            continue
        accepted_at = now + accepted_ago
        _work_order(
            session,
            wo_id,
            fx.TENANT_MIDTOWN,
            asset_id,
            symptom,
            "IN_PROGRESS" if state == "IN_PROGRESS" else "OPEN",
        )
        session.add(
            DispatchCandidate(
                wo_id=wo_id,
                contractor_id=fx.C_MARCO,
                tenant_id=fx.TENANT_MIDTOWN,
                rank=1,
                match_score=Decimal("0.900"),
                match_reason="Closest certified RTU tech",
                state="ACCEPTED",
                offered_at=accepted_at - timedelta(minutes=3),
                sla_deadline=accepted_at + timedelta(minutes=27),
                responded_at=accepted_at,
            )
        )
        session.flush()
        session.add(
            Dispatch(
                wo_id=wo_id,
                tenant_id=fx.TENANT_MIDTOWN,
                state=state,
                current_contractor_id=fx.C_MARCO,
                sla_minutes=30,
                sla_deadline=accepted_at + timedelta(minutes=27),
                version=1,
                updated_at=accepted_at,
            )
        )
    session.flush()
    for event_id, stage, ago in fx.ARRIVED_EVENTS:
        if session.get(MemoryEvent, event_id) is None:
            session.add(
                MemoryEvent(
                    id=event_id,
                    tenant_id=fx.TENANT_MIDTOWN,
                    asset_id=fx.A_RTU04,
                    wo_id=fx.WO_ARRIVED,
                    type="ADVANCE",
                    stage=stage,
                    payload={},
                    actor_user_id=fx.U_MARCO,
                    at=now + ago,
                    idempotency_key=f"seed-{event_id}",
                )
            )
            session.flush()


def _work_order(
    session: Session,
    wo_id: uuid.UUID,
    tenant_id: uuid.UUID,
    asset_id: uuid.UUID,
    symptom: str,
    status: str,
) -> None:
    session.add(
        WorkOrder(
            id=wo_id,
            tenant_id=tenant_id,
            asset_id=asset_id,
            symptom=symptom,
            wo_source="dispatch",
            status=status,
            predicted_failure_code=packets.RTU04_PREDICTED if asset_id == fx.A_RTU04 else None,
        )
    )
    session.flush()


def _add_missing(session: Session, row: Tenant | Contractor | Site | Asset) -> None:
    if session.get(type(row), row.id) is None:
        session.add(row)

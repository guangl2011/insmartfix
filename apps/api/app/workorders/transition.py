"""`POST /workorders/{wo}/transition` service (FR-6.1, FR-6.3, FR-6.4; D10 H-3, H-4).

One transaction per request, serialised per WO by `SELECT … FOR UPDATE` on its dispatch row:
idempotency replay check → rule check → append through `MemorySeam` → dispatch
`ACCEPTED → IN_PROGRESS` on the first advance → store the idempotency record. A concurrent
second undo of the same event also trips the partial unique index on `corrects_event_id`.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contract.common import ErrorCode
from app.contract.schedule import LifecycleStage
from app.contract.workorders import (
    LifecycleEvent,
    TransitionAction,
    TransitionRequest,
    TransitionResponse,
)
from app.core.errors import ApiError
from app.core.idempotency import IdempotencyRequest
from app.core.idempotency_store import lookup, save, scoped_event_key
from app.db.models import Dispatch, WorkOrder
from app.memory.postgres import PostgresMemorySeam
from app.memory.seam import NewEvent
from app.workorders.detail import lifecycle_history
from app.workorders.lifecycle import (
    EventView,
    TransitionRefusedError,
    check_advance,
    fold,
    undo_target,
)
from app.workorders.lifecycle import _rows as as_rows

LIFECYCLE_TYPES = ("ADVANCE", "CORRECTION")


def _refused() -> ApiError:
    return ApiError(409, ErrorCode.INVALID_TRANSITION)


def transition(
    db: Session,
    *,
    wo_id: UUID,
    actor_user_id: UUID,
    body: TransitionRequest,
    idem: IdempotencyRequest | None,
    now: datetime,
) -> TransitionResponse | dict[str, Any]:
    """Returns the response model, or the stored body of an idempotent replay."""
    dispatch = db.execute(
        select(Dispatch).where(Dispatch.wo_id == wo_id).with_for_update()
    ).scalar_one()
    if idem is not None and (stored := lookup(db, idem)) is not None:
        return stored.body
    wo = db.get(WorkOrder, wo_id)
    assert wo is not None  # noqa: S101 — the gate loaded it
    seam = PostgresMemorySeam(db)
    events = [
        EventView(e.id, e.type, e.stage, e.corrects_event_id, e.actor_user_id, e.at)
        for e in seam.list(wo_id)
        if e.type in LIFECYCLE_TYPES
    ]
    completed = dispatch.state == "COMPLETED"
    try:
        if body.action is TransitionAction.ADVANCE:
            stage = check_advance(events, body.stage.value if body.stage else None, completed)
            new = NewEvent(wo.tenant_id, wo.asset_id, wo_id, "ADVANCE", actor_user_id, now, stage)
        else:
            target = undo_target(events, body.corrects_event_id, actor_user_id, completed)
            new = NewEvent(
                wo.tenant_id,
                wo.asset_id,
                wo_id,
                "CORRECTION",
                actor_user_id,
                now,
                corrects_event_id=target.id,
            )
    except TransitionRefusedError:
        raise _refused() from None
    if idem is not None:
        new = NewEvent(**{**new.__dict__, "idempotency_key": scoped_event_key(idem)})
    try:
        with db.begin_nested():
            event_id = seam.append(new)
    except IntegrityError:
        raise _refused() from None  # e.g. this advance was corrected concurrently
    if new.type == "ADVANCE" and dispatch.state == "ACCEPTED":
        dispatch.state = "IN_PROGRESS"
        dispatch.version += 1
        dispatch.updated_at = now
    db.flush()
    history = lifecycle_history(db, wo_id)
    stage_now = fold(as_rows([_view(h) for h in history])).stage
    response = TransitionResponse(
        lifecycle_stage=LifecycleStage(stage_now) if stage_now else None,
        event_id=event_id,
        history=history,
        server_time=now,
    )
    if idem is not None:
        save(db, idem, 200, response.model_dump(mode="json", exclude={"server_time"}))
    return response


def _view(h: LifecycleEvent) -> EventView:
    return EventView(h.event_id, h.type.value, h.stage, h.corrects_event_id, h.actor_user_id, h.at)

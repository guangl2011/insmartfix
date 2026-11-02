"""`POST /__test/clock`: move the server clock for deterministic SLA tests (TEST_PLAN §3)."""

from datetime import datetime, timedelta

from fastapi import APIRouter
from pydantic import Field

from app.clock import clock, now
from app.contract.common import RequestModel, ServerTimed

router = APIRouter(include_in_schema=False)


class ClockRequest(RequestModel):
    """Apply in order: `reset`, then `set`, then `advance_seconds`."""

    reset: bool = False
    set: datetime | None = None
    advance_seconds: float | None = Field(default=None, ge=-86_400 * 365, le=86_400 * 365)


class ClockResponse(ServerTimed):
    frozen: bool


@router.post("/__test/clock")
def move_clock(body: ClockRequest) -> ClockResponse:
    if body.reset:
        clock.reset()
    if body.set is not None:
        clock.set(body.set)
    if body.advance_seconds is not None:
        clock.advance(timedelta(seconds=body.advance_seconds))
    return ClockResponse(server_time=now(), frozen=clock.frozen)


@router.get("/__test/clock")
def read_clock() -> ClockResponse:
    return ClockResponse(server_time=now(), frozen=clock.frozen)

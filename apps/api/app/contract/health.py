"""Liveness / readiness bodies (spec §5, NFR-7)."""

from typing import Literal

from pydantic import BaseModel

from app.contract.common import ServerTimed


class HealthResponse(ServerTimed):
    status: Literal["ok"]


class ReadyChecks(BaseModel):
    database: Literal["ok"]


class ReadyResponse(ServerTimed):
    status: Literal["ready"]
    checks: ReadyChecks

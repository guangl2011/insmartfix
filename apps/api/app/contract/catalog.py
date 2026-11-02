"""Failure-code catalog bodies (spec §5 `GET /failure-codes`, FR-7.1)."""

from pydantic import BaseModel

from app.contract.common import ServerTimed


class FailureCode(BaseModel):
    code: str
    subtype: str
    component_group: str
    label: str


class FailureCodeList(ServerTimed):
    """`FailureCode[]` wrapped in an object so the body can carry `server_time` (spec §5)."""

    failure_codes: list[FailureCode]

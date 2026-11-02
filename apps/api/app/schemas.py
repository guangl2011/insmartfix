"""Shared response models (spec §5)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    """`{"error": {"code": "STRING", "message": "human text"}}` — every API error."""

    error: ErrorBody


class HealthResponse(BaseModel):
    status: Literal["ok"]
    server_time: datetime


class ReadyChecks(BaseModel):
    database: Literal["ok"]


class ReadyResponse(BaseModel):
    status: Literal["ready"]
    checks: ReadyChecks
    server_time: datetime

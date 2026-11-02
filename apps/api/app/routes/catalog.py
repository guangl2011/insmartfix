"""Failure-code catalog (spec §5 `GET /failure-codes`, FR-7.1). Any authenticated role."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.deps import get_principal
from app.catalog.service import list_codes
from app.clock import now
from app.contract.catalog import FailureCode, FailureCodeList
from app.contract.common import error_responses
from app.db.session import get_db
from app.routes import API_PREFIX

router = APIRouter(prefix=API_PREFIX, tags=["catalog"], dependencies=[Depends(get_principal)])


@router.get(
    "/failure-codes",
    operation_id="list_failure_codes",
    response_model=FailureCodeList,
    responses=error_responses(401, 422),
)
def list_failure_codes(
    db: Annotated[Session, Depends(get_db)],
    subtype: Annotated[str | None, Query(max_length=64)] = None,
) -> FailureCodeList:
    """Codes for an asset subtype, ordered and grouped by component (FR-7.1)."""
    return FailureCodeList(
        failure_codes=[
            FailureCode(
                code=c.code, subtype=c.subtype, component_group=c.component_group, label=c.label
            )
            for c in list_codes(db, subtype)
        ],
        server_time=now(),
    )

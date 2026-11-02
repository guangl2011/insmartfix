"""Catalog queries. Ordered and grouped by component: group, then `sort_order`, then code."""

from collections.abc import Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FailureCode


def list_codes(session: Session, subtype: str | None = None) -> Sequence[FailureCode]:
    """Every code, or only those for `subtype` (FR-7.1 pre-filter), in display order."""
    query = select(FailureCode)
    if subtype is not None:
        query = query.where(FailureCode.subtype == subtype)
    query = query.order_by(
        FailureCode.subtype, FailureCode.component_group, FailureCode.sort_order, FailureCode.code
    )
    return session.scalars(query).all()


def component_groups(session: Session, subtype: str) -> Mapping[str, str]:
    """`code -> component_group` for one subtype: the input the calibration labeler needs."""
    return {c.code: c.component_group for c in list_codes(session, subtype)}


def is_valid_code(session: Session, subtype: str, code: str) -> bool:
    return session.get(FailureCode, (subtype, code)) is not None

"""`calibration_records` writer. Append-only (the runtime role has INSERT, SELECT only).

The label is computed here, from the WO's dispatch-time prediction snapshot (D10 L-4), never
taken from a request (M-8). Runs inside the completion transaction (M2-T5), which commits.
"""

import uuid
from collections.abc import Mapping
from datetime import datetime

from sqlalchemy.orm import Session

from app.calibration.labeler import Label, label
from app.db.models import CalibrationRecord, WorkOrder


def record_calibration(
    session: Session,
    *,
    wo: WorkOrder,
    actual_code: str,
    actual_fault_matched: bool,
    actor_user_id: uuid.UUID,
    groups: Mapping[str, str],
    at: datetime,
) -> Label:
    result = label(wo.predicted_failure_code, actual_code, groups)
    session.add(
        CalibrationRecord(
            wo_id=wo.id,
            tenant_id=wo.tenant_id,
            asset_id=wo.asset_id,
            predicted_code=wo.predicted_failure_code,
            actual_code=actual_code,
            label=result.value,
            actual_fault_matched=actual_fault_matched,
            actor_user_id=actor_user_id,
            created_at=at,
        )
    )
    session.flush()
    return result

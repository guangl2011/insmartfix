"""T-CAL-1 (writer half): the stored label uses the WO's prediction snapshot (D10 L-4)."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, update
from sqlalchemy.orm import Session

from app.calibration.labeler import Label
from app.calibration.records import record_calibration
from app.db.models import CalibrationRecord, WorkOrder
from tests.integration.conftest import make_world

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
GROUPS = {"COMP-CONTACTOR": "COMPRESSOR", "COMP-CAPACITOR": "COMPRESSOR", "REF-LEAK": "REF"}


@pytest.fixture
def session(app_engine: Engine) -> Iterator[Session]:
    with Session(app_engine) as s:
        yield s
        s.rollback()


@pytest.mark.parametrize(
    ("snapshot", "actual", "expected"),
    [
        ("COMP-CONTACTOR", "COMP-CONTACTOR", Label.MATCH),
        ("COMP-CONTACTOR", "COMP-CAPACITOR", Label.PARTIAL),
        ("COMP-CONTACTOR", "REF-LEAK", Label.MISS),
        (None, "REF-LEAK", Label.NO_PREDICTION),
    ],
)
def test_T_CAL_1_record_uses_the_prediction_snapshot(
    session: Session, snapshot: str | None, actual: str, expected: Label
) -> None:
    w = make_world(session.connection())
    session.execute(
        update(WorkOrder).where(WorkOrder.id == w.wo_id).values(predicted_failure_code=snapshot)
    )
    wo = session.get_one(WorkOrder, w.wo_id)
    got = record_calibration(
        session,
        wo=wo,
        actual_code=actual,
        actual_fault_matched=expected is Label.MATCH,
        actor_user_id=w.contractor_user_id,
        groups=GROUPS,
        at=NOW,
    )
    assert got is expected
    row = session.get_one(CalibrationRecord, w.wo_id)
    assert (row.predicted_code, row.actual_code, row.label, row.actor_user_id, row.asset_id) == (
        snapshot,
        actual,
        expected.value,
        w.contractor_user_id,
        w.asset_id,
    )
    assert row.created_at == NOW

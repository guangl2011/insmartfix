"""v1 engine: reads the packets seeded into `decision_packets` (TEST_PLAN §5 RTU-04)."""

from sqlalchemy.orm import Session

from app.db.models import Asset, DecisionPacket
from app.decision_engine.port import EnginePacket


class StubDecisionEngine:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _row(self, asset: Asset) -> DecisionPacket | None:
        row = self._session.get(DecisionPacket, asset.id)
        # Defence in depth: a packet is only ever served for an asset in its own tenant.
        if row is None or row.tenant_id != asset.tenant_id:
            return None
        return row

    def get_packet(self, asset: Asset) -> EnginePacket | None:
        row = self._row(asset)
        if row is None:
            return None
        return EnginePacket(
            decision=dict(row.decision),
            packet=dict(row.packet),
            predicted_failure_code=row.predicted_failure_code,
            likely_cause=row.likely_cause,
            confidence=float(row.confidence) if row.confidence is not None else None,
        )

    def predicted_failure_code(self, asset: Asset) -> str | None:
        row = self._row(asset)
        return row.predicted_failure_code if row is not None else None

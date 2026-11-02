"""The Decision Engine port. A live Insmart engine replaces the stub behind this interface (D1).

`decision` and `packet` are JSON objects shaped like the contract's `Decision` and `Packet`
(`app/contract/workorders.py`); the work-order detail builder validates them into those models.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from app.db.models import Asset


@dataclass(frozen=True)
class EnginePacket:
    decision: dict[str, Any]
    packet: dict[str, Any]
    predicted_failure_code: str | None
    likely_cause: str | None  # the card teaser: "Likely: X · NN% match" (FR-2.3)
    confidence: float | None


class DecisionEngine(Protocol):
    def get_packet(self, asset: Asset) -> EnginePacket | None:
        """The pre-diagnostic packet, or None when the asset has no history (FR-3.4)."""
        ...

    def predicted_failure_code(self, asset: Asset) -> str | None:
        """The engine's predicted failure code (snapshotted on the WO, D10 L-4)."""
        ...


class NullDecisionEngine:
    """No engine at all: every asset is a no-packet asset."""

    def get_packet(self, asset: Asset) -> EnginePacket | None:
        return None

    def predicted_failure_code(self, asset: Asset) -> str | None:
        return None

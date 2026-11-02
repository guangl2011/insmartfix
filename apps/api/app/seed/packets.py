"""Stub Decision Engine packets (FR-3.2-3.4). RTU-04 has a full packet predicting COMP-CONTACTOR at
82 %; AHU-NEW-01 has none (`pre_diagnostic_available = false`). Times are relative to seed time.
"""

from datetime import datetime, timedelta
from typing import Any

from app.seed import fixtures as fx

RTU04_PREDICTED = "COMP-CONTACTOR"
RTU04_LIKELY_CAUSE = "Compressor contactor"
RTU04_CONFIDENCE = 0.82


def rtu04(now: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
    """(decision, packet) JSON for RTU-04, shaped like the contract's `Decision` and `Packet`."""

    def ago(days: int) -> str:
        return (now - timedelta(days=days)).isoformat()

    events = [
        {"at": ago(2), "kind": "alarm", "summary": "Compressor short-cycling: 9 starts in 1 h"},
        {"at": ago(6), "kind": "alarm", "summary": "High discharge temperature"},
        {"at": ago(13), "kind": "reading", "summary": "Contactor coil voltage dip to 19 V"},
    ]
    insights = [
        {"summary": "Start count 3x fleet median for this model", "confidence": 0.86},
        {"summary": "Contactor age past typical service life (6 y)", "confidence": 0.74},
    ]
    decision = {
        "health_score": 54,
        "failure_risk": "HIGH",
        "root_cause": "Pitted compressor contactor causing short-cycling",
        "recommended_action": "Replace the compressor contactor; check the run capacitor",
        "evidence_summary": "Based on 3 recent events + 2 active insights",
        "evidence": [{"kind": "event", "summary": e["summary"], "at": e["at"]} for e in events]
        + [{"kind": "insight", "summary": i["summary"]} for i in insights],
    }
    rtu = next(a for a in fx.ASSETS if a.id == fx.A_RTU04)
    packet = {
        "asset_identity": {
            "name": rtu.name,
            "subtype": rtu.subtype,
            "make": rtu.make,
            "model": rtu.model,
            "install_year": rtu.install_year,
            "location": rtu.location,
            "duty": rtu.duty,
        },
        "recent_events": events,
        "recent_maintenance": [
            {
                "at": ago(95),
                "summary": "Quarterly PM: belts, filters",
                "performed_by": "Rossi HVAC",
            },
            {"at": ago(280), "summary": "Condenser coil cleaned", "performed_by": "Rossi HVAC"},
        ],
        "active_insights": insights,
        "predicted_parts": [
            {
                "description": "Contactor 2-pole 40 A 24 V",
                "part_code": "CTR-2P40",
                "qty": 1,
                "likelihood": 0.82,
            },
            {
                "description": "Run capacitor 45/5 uF",
                "part_code": "CAP-455",
                "qty": 1,
                "likelihood": 0.35,
            },
        ],
    }
    return decision, packet

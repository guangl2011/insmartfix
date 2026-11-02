"""M2-T1: stub Decision Engine over seeded packets, and the failure-code catalog (FR-3.2-3.4,
FR-7.1). Supports T-WO-2/3, T-COMP-2 and T-CAL-1."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.catalog.service import component_groups, is_valid_code, list_codes
from app.db.models import Asset, DecisionPacket
from app.decision_engine.port import DecisionEngine, NullDecisionEngine
from app.decision_engine.stub import StubDecisionEngine
from app.seed import fixtures as fx
from app.seed.failure_codes import FAILURE_CODES
from app.seed.load import load
from tests.integration.conftest import make_world

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def seeded(app_engine: Engine) -> None:
    with Session(app_engine) as s, s.begin():
        load(s, now=NOW, password="not-a-real-password", hash_password=lambda p: "x")


@pytest.fixture
def session(app_engine: Engine, seeded: None) -> Iterator[Session]:
    with Session(app_engine) as s:
        yield s
        s.rollback()


def test_stub_engine_serves_the_rtu04_packet(session: Session) -> None:
    engine: DecisionEngine = StubDecisionEngine(session)
    rtu = session.get_one(Asset, fx.A_RTU04)
    got = engine.get_packet(rtu)
    assert got is not None
    assert (got.predicted_failure_code, got.likely_cause, got.confidence) == (
        "COMP-CONTACTOR",
        "Compressor contactor",
        0.82,
    )
    assert engine.predicted_failure_code(rtu) == "COMP-CONTACTOR"
    assert got.decision["failure_risk"] == "HIGH"
    assert got.decision["evidence_summary"] == "Based on 3 recent events + 2 active insights"
    assert set(got.packet) == {
        "asset_identity",
        "recent_events",
        "recent_maintenance",
        "active_insights",
        "predicted_parts",
    }
    assert all(got.packet[k] for k in got.packet)  # FR-3.3: every section populated for RTU-04
    assert got.packet["asset_identity"]["name"] == "RTU-04"


def test_stub_engine_has_no_packet_for_ahu_new_01(session: Session) -> None:
    engine = StubDecisionEngine(session)
    ahu = session.get_one(Asset, fx.A_AHUNEW01)
    assert engine.get_packet(ahu) is None
    assert engine.predicted_failure_code(ahu) is None


def test_stub_engine_never_serves_a_packet_across_tenants(session: Session) -> None:
    # A row whose tenant disagrees with the asset is ignored (the FK makes it unreachable anyway).
    rtu = session.get_one(Asset, fx.A_RTU04)
    impostor = Asset(
        id=rtu.id, tenant_id=fx.TENANT_OTHER, site_id=rtu.site_id, name="x", subtype="RTU"
    )
    session.expunge(rtu)
    assert StubDecisionEngine(session).get_packet(impostor) is None
    assert StubDecisionEngine(session).predicted_failure_code(impostor) is None


def test_stub_engine_handles_a_packet_without_confidence(app_engine: Engine) -> None:
    with Session(app_engine) as s:
        w = make_world(s.connection())
        s.add(DecisionPacket(asset_id=w.asset_id, tenant_id=w.tenant_id, decision={}, packet={}))
        s.flush()
        got = StubDecisionEngine(s).get_packet(s.get_one(Asset, w.asset_id))
        assert got is not None
        assert (got.confidence, got.predicted_failure_code) == (None, None)
        s.rollback()


def test_null_engine_has_nothing() -> None:
    engine: DecisionEngine = NullDecisionEngine()
    asset = Asset(name="x", subtype="RTU")
    assert engine.get_packet(asset) is None
    assert engine.predicted_failure_code(asset) is None


def test_catalog_filters_by_subtype_in_group_order(session: Session) -> None:
    rtu = list_codes(session, "RTU")
    assert {c.subtype for c in rtu} == {"RTU"}
    assert {c.code for c in rtu} >= {code for code, _, _ in FAILURE_CODES["RTU"]}
    keys = [(c.component_group, c.sort_order, c.code) for c in rtu]
    assert keys == sorted(keys)
    assert "COMP-CONTACTOR" in {c.code for c in rtu}
    assert list_codes(session, "NO-SUCH-SUBTYPE") == []
    everything = list_codes(session)
    assert {"RTU", "AHU"} <= {c.subtype for c in everything}


def test_component_groups_and_validity(session: Session) -> None:
    groups = component_groups(session, "RTU")
    assert groups["COMP-CONTACTOR"] == groups["COMP-CAPACITOR"] == "COMPRESSOR"
    assert groups["REF-LEAK"] == "REFRIGERANT"
    assert is_valid_code(session, "RTU", "COMP-CONTACTOR")
    assert not is_valid_code(session, "AHU", "COMP-CONTACTOR")  # filtered by asset subtype
    assert not is_valid_code(session, "RTU", "MADE-UP")


def test_seeded_packet_is_contract_valid(session: Session) -> None:
    """The stub engine's JSON validates as the contract's `Decision` and `Packet` (FR-3.2, 3.3)."""
    from app.contract.workorders import Decision, Packet

    got = StubDecisionEngine(session).get_packet(session.get_one(Asset, fx.A_RTU04))
    assert got is not None
    decision = Decision.model_validate(got.decision)
    packet = Packet.model_validate(got.packet)
    assert decision.health_score == 54
    assert len(decision.evidence) == 5
    assert len(packet.recent_events) == 3
    assert packet.predicted_parts[0].likelihood == 0.82

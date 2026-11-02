"""T-INBOX-1 (A): schedule ordering and grouping (FR-2.1, FR-2.2, FR-2.8; spec §5 OfferSummary)."""

import os
from collections.abc import Iterator
from datetime import timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.clock import wall_now
from app.contract.schedule import ScheduleResponse
from app.db.session import get_engine
from app.main import create_app
from app.settings import normalize_database_url
from tests.conftest import make_settings
from tests.integration.factories import Tenant, add_event, make_offer, make_tenant

pytestmark = pytest.mark.integration


@pytest.fixture
def api(migrated_db: None) -> Iterator[TestClient]:
    url = normalize_database_url(os.environ["DATABASE_URL"])
    with TestClient(create_app(make_settings(url, env="ci"))) as c:
        yield c
    get_engine.cache_clear()


class Inbox:
    def __init__(self, t: Tenant, ids: dict[str, UUID]) -> None:
        self.t = t
        self.ids = ids


@pytest.fixture
def inbox(app_engine: Engine) -> Inbox:
    """TEST_PLAN §5 shapes: offers at 12 m / 4 m / 45 s / past deadline, one ACCEPTED and one
    ARRIVED job for Marco, plus noise that must not appear."""
    now = wall_now()
    ids: dict[str, UUID] = {}
    with app_engine.begin() as conn:
        t = make_tenant(conn, ["marco", "ana"])
        m, a = t.contractors["marco"], t.contractors["ana"]

        def offer(name: str, minutes: float) -> None:
            ids[name] = make_offer(
                conn,
                t,
                [(m, "OFFERED"), (a, "QUEUED")],
                current=m,
                deadline=now + timedelta(minutes=minutes),
                symptom=name,
            )

        offer("12m", 12)
        offer("45s", 0.75)
        offer("4m", 4)
        offer("past_deadline", -1)  # unswept: never shown as a live offer
        ids["ana_offer"] = make_offer(conn, t, [(a, "OFFERED"), (m, "QUEUED")], current=a)
        ids["accepted"] = make_offer(
            conn,
            t,
            [(m, "ACCEPTED")],
            state="ACCEPTED",
            current=m,
            responded_at=now - timedelta(minutes=30),
            symptom="accepted",
        )
        ids["arrived"] = make_offer(
            conn,
            t,
            [(m, "ACCEPTED")],
            state="IN_PROGRESS",
            current=m,
            symptom="arrived",
            responded_at=now - timedelta(hours=2),
        )
        en_route = add_event(
            conn,
            t,
            ids["arrived"],
            m,
            type_="ADVANCE",
            stage="EN_ROUTE",
            at=now - timedelta(minutes=50),
        )
        arrived = add_event(
            conn,
            t,
            ids["arrived"],
            m,
            type_="ADVANCE",
            stage="ARRIVED",
            at=now - timedelta(minutes=10),
        )
        # An older job advanced long ago, then its last advance undone (CORRECTION).
        ids["undone"] = make_offer(
            conn,
            t,
            [(m, "ACCEPTED")],
            state="IN_PROGRESS",
            current=m,
            symptom="undone",
            responded_at=now - timedelta(hours=5),
        )
        first = add_event(
            conn,
            t,
            ids["undone"],
            m,
            type_="ADVANCE",
            stage="EN_ROUTE",
            at=now - timedelta(hours=4),
        )
        second = add_event(
            conn,
            t,
            ids["undone"],
            m,
            type_="ADVANCE",
            stage="ARRIVED",
            at=now - timedelta(minutes=1),
        )
        add_event(conn, t, ids["undone"], m, type_="CORRECTION", corrects=second, at=now)
        assert en_route
        assert arrived
        assert first
        ids["completed"] = make_offer(
            conn, t, [(m, "ACCEPTED")], state="COMPLETED", current=m, symptom="completed"
        )
    return Inbox(t, ids)


def _schedule(api: TestClient, path: str, auth: dict[str, str]) -> ScheduleResponse:
    res = api.get(path, headers=auth)
    assert res.status_code == 200, res.text
    return ScheduleResponse.model_validate(res.json())


def test_T_INBOX_1_offers_soonest_deadline_first_active_most_recently_advanced(
    api: TestClient, inbox: Inbox
) -> None:
    m = inbox.t.contractors["marco"]
    s = _schedule(api, "/v1/me/schedule", m.auth)
    assert [o.symptom for o in s.offers] == ["45s", "4m", "12m"]
    # arrived (advanced 10 min ago) > accepted (accepted 30 min ago, never advanced) >
    # undone (latest live advance 4 h ago after the correction).
    assert [o.symptom for o in s.active] == ["arrived", "accepted", "undone"]
    assert s.voice_bookings == []
    by = {o.symptom: o for o in s.active}
    assert by["arrived"].lifecycle_stage == "ARRIVED"
    assert by["undone"].lifecycle_stage == "EN_ROUTE"
    assert by["accepted"].lifecycle_stage is None
    assert by["arrived"].dispatch_state == "IN_PROGRESS"
    assert all(o.sla_deadline is None for o in s.active)
    first = s.offers[0]
    assert first.dispatch_state == "PENDING"
    assert first.match_score == pytest.approx(0.8)
    assert first.match_reason == "Nearby"
    assert first.site.name == "Tower"
    assert first.wo_source == "dispatch"
    assert "ranked_candidates" not in api.get("/v1/me/schedule", headers=m.auth).text


def test_T_INBOX_1_contractor_path_and_owner_view_match_the_me_alias(
    api: TestClient, inbox: Inbox
) -> None:
    m = inbox.t.contractors["marco"]
    me = _schedule(api, "/v1/me/schedule", m.auth)
    own = _schedule(api, f"/v1/contractor/{m.contractor_id}/schedule", m.auth)
    owner = _schedule(api, f"/v1/contractor/{m.contractor_id}/schedule", inbox.t.owner.auth)
    dumps = [s.model_dump(exclude={"server_time"}) for s in (me, own, owner)]
    assert dumps[0] == dumps[1] == dumps[2]


def test_T_INBOX_1_other_contractor_sees_only_their_own(api: TestClient, inbox: Inbox) -> None:
    a = inbox.t.contractors["ana"]
    s = _schedule(api, "/v1/me/schedule", a.auth)
    assert [o.wo_id for o in s.offers] == [inbox.ids["ana_offer"]]
    assert s.active == []

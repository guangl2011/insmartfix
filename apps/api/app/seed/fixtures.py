"""TEST_PLAN §5 fixture dataset. Fixed UUIDv4 ids so E2E specs and contract mocks can refer to them.

No secrets here: test-account passwords come from `SEED_PASSWORD` at load time.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta


def _id(value: str) -> uuid.UUID:
    return uuid.UUID(value)


TENANT_MIDTOWN = _id("635c1742-02e6-49ab-b54b-61f4289bcc82")
TENANT_OTHER = _id("fc1425ac-eb04-4242-9a24-7948e00ab418")

C_MARCO = _id("c7ae8737-3259-4110-81b3-efd6f15aaff3")
C_ANA = _id("6731fe6a-cb06-4557-8cd0-fe095da9a8e8")
C_ZED = _id("20bd03df-09fd-4856-8e6b-77aed0b11920")

U_OWNER = _id("645a2899-c7b3-4db4-95ba-6f645062ee87")
U_MARCO = _id("5787a2ce-46ba-4f09-95e2-e5e8d646a931")
U_ANA = _id("f459cce0-4da4-429c-8e31-72f878bccace")
U_ZED = _id("21b5223c-f84c-46b1-a57b-f6fc4bbb5ef8")

SITE_TOWER = _id("0772d7f5-7eec-4bc7-ba92-6e9c53cfb90c")
SITE_ANNEX = _id("07ea0199-eb78-4fc0-8c84-e94e68b31d9c")
SITE_OTHER = _id("d7f1d2e2-4aa2-4a2b-a1c6-8d3e53203cd2")

A_RTU04 = _id("a190819b-8405-42a2-9257-b336255c6e1f")
A_AHUNEW01 = _id("9aecfae3-cf17-4bf7-b1dc-fe6abc8fe239")
A_ZED = _id("55909fd0-562b-404e-9541-d9d1ae2ed224")

WO_OFFER_12M = _id("d63f4fe5-14e1-4c6b-956d-4355b083a65d")
WO_OFFER_4M = _id("b4a5faf4-b464-4398-ae3c-32a419e54041")
WO_OFFER_45S = _id("aa4cd539-50df-4e61-8d8a-13bd05b3ee31")
WO_OFFER_PAST = _id("b2a773ab-17a4-4117-9aeb-58ffe0b830e1")
WO_ACCEPTED = _id("7d159866-2434-4b68-8dda-deb4f30bf8e4")
WO_ARRIVED = _id("b56502ad-420e-4e76-ad52-993f4d941147")
WO_ZED = _id("1b5d8def-8f14-49ea-8057-6ce1e4849c66")

EV_ARRIVED_EN_ROUTE = _id("196e21aa-9b5b-46a3-8b23-ce64e5b2619f")
EV_ARRIVED_ARRIVED = _id("d1df06bb-6500-4c51-8bcc-ca9d2fb91c67")

TENANTS = ((TENANT_MIDTOWN, "Midtown Properties"), (TENANT_OTHER, "Other Holdings"))

# (id, tenant, name, company, avg_rating)
CONTRACTORS = (
    (C_MARCO, TENANT_MIDTOWN, "Marco Rossi", "Rossi HVAC", "4.80"),
    (C_ANA, TENANT_MIDTOWN, "Ana Lee", "Lee Mechanical", "4.60"),
    (C_ZED, TENANT_OTHER, "Zed", "Zed Air", "4.10"),
)

# (id, tenant, email, name, role, contractor_id)
USERS = (
    (U_OWNER, TENANT_MIDTOWN, "owner@test.insmart.ai", "Dana Owner", "owner", None),
    (U_MARCO, TENANT_MIDTOWN, "marco@test.insmart.ai", "Marco Rossi", "contractor", C_MARCO),
    (U_ANA, TENANT_MIDTOWN, "ana@test.insmart.ai", "Ana Lee", "contractor", C_ANA),
    (U_ZED, TENANT_OTHER, "zed@other.insmart.ai", "Zed", "contractor", C_ZED),
)

# (id, tenant, name, location)
SITES = (
    (SITE_TOWER, TENANT_MIDTOWN, "Midtown Tower", "350 W 42nd St, New York"),
    (SITE_ANNEX, TENANT_MIDTOWN, "Midtown Annex", "360 W 42nd St, New York"),
    (SITE_OTHER, TENANT_OTHER, "Other Plaza", "1 Other Way, Newark"),
)


@dataclass(frozen=True)
class AssetFixture:
    id: uuid.UUID
    tenant_id: uuid.UUID
    site_id: uuid.UUID
    name: str
    subtype: str
    make: str
    model: str
    install_year: int
    location: str
    duty: str


ASSETS = (
    AssetFixture(
        A_RTU04,
        TENANT_MIDTOWN,
        SITE_TOWER,
        "RTU-04",
        "RTU",
        "Carrier",
        "48TC",
        2014,
        "Roof",
        "Cooling + heating, 12.5 ton",
    ),
    AssetFixture(
        A_AHUNEW01,
        TENANT_MIDTOWN,
        SITE_ANNEX,
        "AHU-NEW-01",
        "AHU",
        "Trane",
        "Performance",
        2026,
        "Mechanical room B1",
        "Air handling",
    ),
    AssetFixture(
        A_ZED,
        TENANT_OTHER,
        SITE_OTHER,
        "RTU-Z1",
        "RTU",
        "Lennox",
        "Energence",
        2018,
        "Roof",
        "Cooling",
    ),
)

RTU_PREDICTED = "COMP-CONTACTOR"  # FR-3 happy path: RTU-04 predicts COMP-CONTACTOR at 82 %


@dataclass(frozen=True)
class OfferFixture:
    """A PENDING offer. `remaining` is relative to seed time; negative means already past."""

    wo_id: uuid.UUID
    tenant_id: uuid.UUID
    asset_id: uuid.UUID
    symptom: str
    sla_minutes: int
    remaining: timedelta
    # (contractor, match_score, reason), ranked best first; rank 1 holds the offer.
    candidates: tuple[tuple[uuid.UUID, str, str], ...]


OFFERS = (
    OfferFixture(
        WO_OFFER_12M,
        TENANT_MIDTOWN,
        A_RTU04,
        "Not cooling; compressor short-cycling",
        30,
        timedelta(minutes=12),
        ((C_MARCO, "0.920", "Closest certified RTU tech"), (C_ANA, "0.810", "Available today")),
    ),
    OfferFixture(
        WO_OFFER_4M,
        TENANT_MIDTOWN,
        A_AHUNEW01,
        "Supply fan noisy at start-up",
        30,
        timedelta(minutes=4),
        ((C_MARCO, "0.880", "AHU experience"), (C_ANA, "0.790", "Nearby")),
    ),
    OfferFixture(
        WO_OFFER_45S,
        TENANT_MIDTOWN,
        A_RTU04,
        "High head pressure alarm",
        15,
        timedelta(seconds=45),
        ((C_MARCO, "0.900", "Closest certified RTU tech"), (C_ANA, "0.800", "Available today")),
    ),
    OfferFixture(
        WO_OFFER_PAST,
        TENANT_MIDTOWN,
        A_AHUNEW01,
        "Filter differential pressure high",
        15,
        timedelta(minutes=-2),
        ((C_MARCO, "0.850", "AHU experience"), (C_ANA, "0.830", "Nearby")),
    ),
    OfferFixture(
        WO_ZED,
        TENANT_OTHER,
        A_ZED,
        "Unit tripping breaker",
        30,
        timedelta(minutes=20),
        ((C_ZED, "0.900", "Only contractor"),),
    ),
)

# Marco's active jobs: one ACCEPTED (no advance yet), one ARRIVED (EN_ROUTE then ARRIVED).
ACTIVE_ACCEPTED = (WO_ACCEPTED, A_RTU04, "Economizer stuck open", timedelta(minutes=-50))
ACTIVE_ARRIVED = (WO_ARRIVED, A_RTU04, "Refrigerant leak suspected", timedelta(minutes=-90))
ARRIVED_EVENTS = (
    (EV_ARRIVED_EN_ROUTE, "EN_ROUTE", timedelta(minutes=-40)),
    (EV_ARRIVED_ARRIVED, "ARRIVED", timedelta(minutes=-10)),
)

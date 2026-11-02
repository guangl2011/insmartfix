"""In-memory users for auth unit tests."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.auth.passwords import hash_password
from app.auth.service import UserRecord

PASSWORD = "correct horse battery staple"
_HASH = hash_password(PASSWORD)

TENANT = UUID("00000000-0000-4000-8000-0000000000a1")
MARCO_CID = UUID("00000000-0000-4000-8000-0000000000c1")

MARCO = UserRecord(
    id=uuid4(),
    tenant_id=TENANT,
    email="marco@test.insmart.ai",
    name="Marco Rossi",
    password_hash=_HASH,
    role="contractor",
    contractor_id=MARCO_CID,
    token_version=0,
    disabled_at=None,
    company="Rossi HVAC",
)
OWNER = replace(
    MARCO, id=uuid4(), email="owner@test.insmart.ai", name="Owner", role="owner", contractor_id=None
)
DISABLED = replace(
    MARCO,
    id=uuid4(),
    email="disabled@test.insmart.ai",
    disabled_at=datetime(2026, 1, 1, tzinfo=UTC),
)
NO_HASH = replace(MARCO, id=uuid4(), email="nohash@test.insmart.ai", password_hash=None)

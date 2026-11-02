"""Test data for gate/dispatch integration tests: two tenants, contractors, owners, offers.

Inserted as the runtime role (it can INSERT everywhere it needs). Tokens are minted directly
(`issue_token`) so tests don't spend login rate-limit budget.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Connection, text

from app.auth.tokens import issue_token
from app.clock import wall_now
from tests.conftest import TEST_JWT_SECRET


@dataclass(frozen=True)
class Person:
    user_id: uuid.UUID
    role: str
    tenant_id: uuid.UUID
    contractor_id: uuid.UUID | None

    @property
    def cid(self) -> uuid.UUID:
        """The contractor id (contractors only)."""
        assert self.contractor_id is not None
        return self.contractor_id

    @property
    def token(self) -> str:
        tok, _ = issue_token(
            user_id=self.user_id,
            role=self.role,
            tenant_id=self.tenant_id,
            contractor_id=self.contractor_id,
            token_version=0,
            secret=TEST_JWT_SECRET,
        )
        return tok

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@dataclass(frozen=True)
class Tenant:
    tenant_id: uuid.UUID
    asset_id: uuid.UUID
    owner: Person
    fm: Person
    contractors: dict[str, Person]


def _one(conn: Connection, sql: str, **params: object) -> uuid.UUID:
    value = conn.execute(text(sql), params).scalar_one()
    assert isinstance(value, uuid.UUID)
    return value


def make_tenant(conn: Connection, contractor_names: list[str]) -> Tenant:
    tag = uuid.uuid4().hex[:10]
    tenant = _one(conn, "INSERT INTO tenants (name) VALUES (:n) RETURNING id", n=f"T {tag}")
    site = _one(
        conn,
        "INSERT INTO sites (tenant_id, name, location) VALUES (:t, 'Tower', 'Roof') RETURNING id",
        t=tenant,
    )
    asset = _one(
        conn,
        "INSERT INTO assets (tenant_id, site_id, name, subtype) "
        "VALUES (:t, :s, :n, 'RTU') RETURNING id",
        t=tenant,
        s=site,
        n=f"RTU-{tag}",
    )
    user_sql = (
        "INSERT INTO users (tenant_id, email, name, role, contractor_id) "
        "VALUES (:t, :e, :n, :r, :c) RETURNING id"
    )

    def person(name: str, role: str, cid: uuid.UUID | None) -> Person:
        uid = _one(conn, user_sql, t=tenant, e=f"{name}-{tag}@test.example", n=name, r=role, c=cid)
        return Person(uid, role, tenant, cid)

    contractors = {}
    for name in contractor_names:
        cid = _one(
            conn,
            "INSERT INTO contractors (tenant_id, name, company) VALUES (:t, :n, 'Co') RETURNING id",
            t=tenant,
            n=name,
        )
        contractors[name] = person(name, "contractor", cid)
    return Tenant(
        tenant, asset, person("owner", "owner", None), person("fm", "fm", None), contractors
    )


def make_offer(
    conn: Connection,
    tenant: Tenant,
    candidates: list[tuple[Person, str]],
    *,
    state: str = "PENDING",
    current: Person | None = None,
    deadline: datetime | None = None,
    sla_minutes: int = 15,
    responded_at: datetime | None = None,
    symptom: str = "Discharge air too warm",
) -> uuid.UUID:
    """A WO with ranked candidates `[(person, candidate_state), ...]` and a dispatch row."""
    at = wall_now()
    deadline = deadline or at + timedelta(minutes=5)
    wo = _one(
        conn,
        "INSERT INTO workorders (tenant_id, asset_id, symptom) VALUES (:t, :a, :s) RETURNING id",
        t=tenant.tenant_id,
        a=tenant.asset_id,
        s=symptom,
    )
    for rank, (p, cstate) in enumerate(candidates, start=1):
        offered = cstate != "QUEUED"
        conn.execute(
            text(
                "INSERT INTO dispatch_candidates (wo_id, contractor_id, tenant_id, rank, "
                "match_score, match_reason, state, offered_at, sla_deadline, responded_at) "
                "VALUES (:w, :c, :t, :r, 0.8, 'Nearby', :s, :o, :d, :ra)"
            ),
            {
                "w": wo,
                "c": p.contractor_id,
                "t": tenant.tenant_id,
                "r": rank,
                "s": cstate,
                "o": at if offered else None,
                "d": deadline if offered else None,
                "ra": responded_at if cstate in ("ACCEPTED", "DECLINED") else None,
            },
        )
    conn.execute(
        text(
            "INSERT INTO dispatch (wo_id, tenant_id, state, current_contractor_id, sla_minutes, "
            "sla_deadline) VALUES (:w, :t, :s, :c, :m, :d)"
        ),
        {
            "w": wo,
            "t": tenant.tenant_id,
            "s": state,
            "c": current.contractor_id if current else None,
            "m": sla_minutes,
            "d": deadline,
        },
    )
    return wo


def add_event(
    conn: Connection,
    tenant: Tenant,
    wo: uuid.UUID,
    actor: Person,
    *,
    type_: str,
    at: datetime,
    stage: str | None = None,
    corrects: uuid.UUID | None = None,
) -> uuid.UUID:
    return _one(
        conn,
        "INSERT INTO memory_events (tenant_id, asset_id, wo_id, type, stage, actor_user_id, at, "
        "corrects_event_id) VALUES (:t, :a, :w, :ty, :st, :u, :at, :c) RETURNING id",
        t=tenant.tenant_id,
        a=tenant.asset_id,
        w=wo,
        ty=type_,
        st=stage,
        u=actor.user_id,
        at=at,
        c=corrects,
    )

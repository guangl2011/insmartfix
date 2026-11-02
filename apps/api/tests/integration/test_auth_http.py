"""Auth over HTTP against Postgres: T-AUTH-1 (A), T-AUTH-8, T-AUTH-10, T-AUTH-11, T-AUTH-12,
T-AUTH-13 (A). The shared `auth_attempts` store is exercised across two app instances.
"""

import os
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.auth.passwords import hash_password
from app.contract.auth import LoginResponse, MeResponse
from app.contract.common import ErrorEnvelope
from app.db.session import get_engine
from app.main import create_app
from app.settings import normalize_database_url
from tests.conftest import make_settings
from tests.integration.conftest import World, make_world

pytestmark = pytest.mark.integration

PASSWORD = "integration-password-1"
PROXY = ("127.0.0.1", 50000)  # trusted proxy (the "BFF") in these tests


@dataclass
class Accounts:
    world: World
    contractor_email: str
    owner_email: str


@pytest.fixture
def accounts(app_engine: Engine) -> Accounts:
    with app_engine.begin() as conn:
        world = make_world(conn)
        conn.execute(
            text("UPDATE users SET password_hash = :h WHERE tenant_id = :t"),
            {"h": hash_password(PASSWORD), "t": world.tenant_id},
        )
        emails: dict[str, str] = dict(
            conn.execute(
                text("SELECT role, email FROM users WHERE tenant_id = :t"), {"t": world.tenant_id}
            ).all()
        )
    return Accounts(world, emails["contractor"], emails["owner"])


def _client(peer: tuple[str, int] = PROXY) -> TestClient:
    url = normalize_database_url(os.environ["DATABASE_URL"])
    settings = make_settings(url, env="ci", trusted_proxies=["127.0.0.0/8"])
    return TestClient(create_app(settings), client=peer)


@pytest.fixture
def api(migrated_db: None) -> Iterator[TestClient]:
    with _client() as c:
        yield c
    get_engine.cache_clear()


def _ip() -> str:
    """A fresh client IP per test, so per-IP buckets never collide between tests."""
    n = uuid.uuid4().int
    return f"198.{18 + (n >> 16) % 2}.{(n >> 8) & 255}.{n & 255}"


def _login(c: TestClient, email: str, password: str, ip: str) -> Any:
    return c.post(
        "/v1/auth/login",
        json={"email": email, "password": password},
        headers={"X-Forwarded-For": ip},
    )


def test_T_AUTH_1_login_then_me(api: TestClient, accounts: Accounts) -> None:
    res = _login(api, accounts.contractor_email.upper(), PASSWORD, _ip())
    assert res.status_code == 200, res.text
    body = LoginResponse.model_validate(res.json())
    assert body.user.contractor_id == accounts.world.contractor_id
    me = api.get("/v1/me", headers={"Authorization": f"Bearer {body.access_token}"})
    assert me.status_code == 200
    profile = MeResponse.model_validate(me.json())
    assert profile.contractor_id == accounts.world.contractor_id
    assert profile.role == "contractor"


def _comparable(res: Any) -> tuple[int, dict[str, Any], dict[str, str]]:
    body = res.json()
    body.pop("server_time")
    headers = {k: v for k, v in res.headers.items() if k not in {"x-request-id", "date"}}
    return res.status_code, body, headers


def test_T_AUTH_10_identical_401s(api: TestClient, accounts: Accounts, app_engine: Engine) -> None:
    w = accounts.world
    with app_engine.begin() as conn:
        tag = uuid.uuid4().hex[:8]
        disabled = f"disabled-{tag}@test.example"
        nohash = f"nohash-{tag}@test.example"
        for email, h, dis in ((disabled, hash_password(PASSWORD), True), (nohash, None, False)):
            conn.execute(
                text(
                    "INSERT INTO users (tenant_id, email, name, role, password_hash, disabled_at) "
                    "VALUES (:t, :e, 'X', 'owner', :h, CASE WHEN :d THEN now() END)"
                ),
                {"t": w.tenant_id, "e": email, "h": h, "d": dis},
            )
    cases = [
        (f"nobody-{tag}@test.example", PASSWORD),
        (accounts.contractor_email, "wrong-password"),
        (disabled, PASSWORD),
        (nohash, PASSWORD),
    ]
    results = {_comparable_key(_login(api, e, p, _ip())) for e, p in cases}
    assert len(results) == 1
    status, body = next(iter(results))[:2]
    assert status == 401
    assert "'INVALID_CREDENTIALS'" in body


def _comparable_key(res: Any) -> tuple[int, str, str]:
    status, body, headers = _comparable(res)
    return status, repr(sorted(body.items())), repr(sorted(headers.items()))


def test_T_AUTH_8_rate_limit_after_five_attempts(api: TestClient, accounts: Accounts) -> None:
    ip = _ip()
    codes = [_login(api, accounts.contractor_email, "wrong", ip).status_code for _ in range(5)]
    assert codes == [401] * 5
    limited = _login(api, accounts.contractor_email, PASSWORD, ip)
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
    ErrorEnvelope.model_validate(limited.json())
    assert limited.json()["error"]["code"] == "RATE_LIMITED"


def test_T_AUTH_11_limit_holds_across_two_app_instances(accounts: Accounts) -> None:
    """Two independently built apps (two "workers"), with separate engines, share the store."""
    ip = _ip()
    with _client() as a:
        get_engine.cache_clear()
        with _client() as b:
            for i in range(5):
                assert (
                    _login(a if i % 2 else b, accounts.owner_email, "wrong", ip).status_code == 401
                )
            assert _login(a, accounts.owner_email, PASSWORD, ip).status_code == 429
            assert _login(b, accounts.owner_email, PASSWORD, ip).status_code == 429
    get_engine.cache_clear()


def test_T_AUTH_11_concurrent_attempts_never_exceed_the_limit(
    api: TestClient, accounts: Accounts
) -> None:
    ip = _ip()
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(
            pool.map(
                lambda _: _login(api, accounts.owner_email, "wrong", ip).status_code, range(12)
            )
        )
    assert sorted(codes) == [401] * 5 + [429] * 7


def test_T_AUTH_11_untrusted_peer_cannot_rotate_forwarded_for(accounts: Accounts) -> None:
    with _client(peer=("203.0.113.77", 40000)) as c:
        codes = [
            _login(c, accounts.contractor_email, "wrong", f"192.0.2.{i}").status_code
            for i in range(6)
        ]
    get_engine.cache_clear()
    # The socket peer is the key; the rotating header is ignored.
    assert codes[:5] == [401] * 5
    assert codes[5] == 429


def _token(api: TestClient, email: str) -> str:
    res = _login(api, email, PASSWORD, _ip())
    assert res.status_code == 200, res.text
    return str(res.json()["access_token"])


def test_T_AUTH_12_http_rejections(api: TestClient, accounts: Accounts, app_engine: Engine) -> None:
    for header in ({}, {"Authorization": "Bearer nope"}, {"Authorization": "Basic Zm9vOmJhcg=="}):
        res = api.get("/v1/me", headers=header)
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "UNAUTHENTICATED"
        assert res.headers["www-authenticate"] == "Bearer"
    token = _token(api, accounts.owner_email)
    with app_engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET disabled_at = now() WHERE email = :e"),
            {"e": accounts.owner_email},
        )
    assert api.get("/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_T_AUTH_13_logout_revokes_every_token(api: TestClient, accounts: Accounts) -> None:
    first = _token(api, accounts.contractor_email)
    second = _token(api, accounts.contractor_email)
    auth = {"Authorization": f"Bearer {first}"}
    assert api.get("/v1/me", headers=auth).status_code == 200
    out = api.post("/v1/auth/logout", headers=auth)
    assert out.status_code == 204
    assert out.content == b""
    for token in (first, second):
        h = {"Authorization": f"Bearer {token}"}
        assert api.get("/v1/me", headers=h).status_code == 401
        assert api.get("/v1/me/schedule", headers=h).status_code == 401
        assert api.post("/v1/auth/logout", headers=h).status_code == 401
    # A fresh login works again.
    fresh = _token(api, accounts.contractor_email)
    assert api.get("/v1/me", headers={"Authorization": f"Bearer {fresh}"}).status_code == 200

"""Login service: T-AUTH-1 (A, service half), T-AUTH-10, T-AUTH-11, T-AUTH-8 (unit, memory store).

The HTTP and shared-Postgres-store halves are in tests/integration/test_auth_http.py.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.auth import passwords, service
from app.auth.ratelimit import MemoryAttemptStore, client_ip, parse_trusted_proxies
from app.auth.service import MemoryUserRepo, login, logout, resolve_principal
from app.core.errors import ApiError
from tests.auth.fakes import DISABLED, MARCO, NO_HASH, OWNER, PASSWORD
from tests.conftest import TEST_JWT_SECRET

T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


def _login(
    email: str,
    password: str,
    *,
    ip: str = "203.0.113.7",
    store: MemoryAttemptStore | None = None,
    now: datetime = T0,
) -> Any:
    return login(
        users=MemoryUserRepo([MARCO, OWNER, DISABLED, NO_HASH]),
        attempts=store or MemoryAttemptStore(),
        email=email,
        password=password,
        client_ip=ip,
        secret=TEST_JWT_SECRET,
        now=now,
    )


def _error(**kw: Any) -> ApiError:
    with pytest.raises(ApiError) as exc:
        _login(**kw)
    return exc.value


def test_T_AUTH_1_valid_login_issues_12h_token_and_profile() -> None:
    res = _login("marco@test.insmart.ai", PASSWORD)
    assert res.user.contractor_id == MARCO.contractor_id
    assert res.expires_at == T0 + timedelta(hours=12)
    p = resolve_principal(MemoryUserRepo([MARCO]), res.access_token, TEST_JWT_SECRET)
    assert p.user_id == MARCO.id


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("nobody@test.insmart.ai", PASSWORD),  # unknown email
        ("marco@test.insmart.ai", "wrong"),  # wrong password
        ("disabled@test.insmart.ai", PASSWORD),  # disabled user, right password
        ("nohash@test.insmart.ai", PASSWORD),  # user without a password hash
    ],
)
def test_T_AUTH_10_every_failure_is_identical(email: str, password: str) -> None:
    err = _error(email=email, password=password)
    assert (err.status_code, err.code, err.message, err.headers, err.reason) == (
        401,
        "INVALID_CREDENTIALS",
        "Email or password is incorrect.",
        None,
        None,
    )


@pytest.mark.parametrize("email", ["nobody@test.insmart.ai", "nohash@test.insmart.ai"])
def test_T_AUTH_10_miss_path_runs_a_dummy_argon2_verify(
    email: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    real = passwords.dummy_verify

    def spy(pw: str) -> None:
        calls.append(pw)
        real(pw)

    monkeypatch.setattr(passwords, "dummy_verify", spy)
    _error(email=email, password=PASSWORD)
    assert calls == [PASSWORD]


def test_T_AUTH_10_rate_limit_identical_for_known_and_unknown_email() -> None:
    errs = []
    for email in ("marco@test.insmart.ai", "nobody@test.insmart.ai"):
        store = MemoryAttemptStore()
        for _ in range(5):
            _error(email=email, password="wrong", store=store)
        errs.append(_error(email=email, password="wrong", store=store))
    assert {(e.status_code, e.code, e.message, str(e.headers)) for e in errs} == {
        (429, "RATE_LIMITED", "Too many attempts. Try again in a minute.", "{'Retry-After': '60'}")
    }


def test_T_AUTH_8_sixth_attempt_in_a_minute_is_429_then_window_drains() -> None:
    store = MemoryAttemptStore()
    for i in range(5):
        _error(
            email="marco@test.insmart.ai",
            password="wrong",
            store=store,
            now=T0 + timedelta(seconds=i),
        )
    assert _error(email="marco@test.insmart.ai", password=PASSWORD, store=store).status_code == 429
    later = T0 + timedelta(seconds=61)
    assert _login("marco@test.insmart.ai", PASSWORD, store=store, now=later).access_token


def test_T_AUTH_11_email_variants_share_a_bucket() -> None:
    store = MemoryAttemptStore()
    variants = [
        "Marco@test.insmart.ai",
        " marco@TEST.insmart.ai ",
        "\uff4d\uff41\uff52\uff43\uff4f@test.insmart.ai",  # fullwidth "marco" (NFKC)
        "MARCO@test.insmart.ai",
        "marco@test.insmart.ai\t",
    ]
    for v in variants:
        _error(email=v, password="wrong", store=store)
    assert _error(email="marco@test.insmart.ai", password=PASSWORD, store=store).status_code == 429


def test_T_AUTH_11_per_email_cap_holds_across_ips() -> None:
    store = MemoryAttemptStore()
    n = 0
    for ip_n in range(10):
        for _ in range(2):
            _error(
                email="marco@test.insmart.ai",
                password="wrong",
                ip=f"198.51.100.{ip_n}",
                store=store,
                now=T0 + timedelta(minutes=n),
            )
            n += 1
    err = _error(
        email="marco@test.insmart.ai",
        password=PASSWORD,
        ip="198.51.100.99",
        store=store,
        now=T0 + timedelta(minutes=n),
    )
    assert err.status_code == 429


def test_T_AUTH_11_per_ip_cap_holds_across_emails() -> None:
    store = MemoryAttemptStore()
    for i in range(30):
        _error(email=f"user{i}@test.insmart.ai", password="wrong", store=store)
    assert _error(email="marco@test.insmart.ai", password=PASSWORD, store=store).status_code == 429
    # A different IP is unaffected.
    assert _login("marco@test.insmart.ai", PASSWORD, ip="192.0.2.1", store=store).access_token


def test_T_AUTH_11_untrusted_forwarded_for_is_ignored() -> None:
    trusted = parse_trusted_proxies(["10.0.0.0/8"])
    assert client_ip("203.0.113.5", "1.2.3.4", trusted) == "203.0.113.5"
    assert client_ip("10.1.2.3", "1.2.3.4", trusted) == "1.2.3.4"
    assert client_ip("10.1.2.3", "9.9.9.9, 1.2.3.4, 10.0.0.2", trusted) == "1.2.3.4"
    assert client_ip("10.1.2.3", "10.0.0.9", trusted) == "10.1.2.3"
    assert client_ip("10.1.2.3", "garbage", trusted) == "10.1.2.3"
    assert client_ip("10.1.2.3", None, trusted) == "10.1.2.3"
    assert client_ip(None, "1.2.3.4", trusted) == "unknown"
    assert client_ip("not-an-ip", "1.2.3.4", trusted) == "not-an-ip"


def test_D11_logout_revokes_every_token_of_the_user() -> None:
    repo = MemoryUserRepo([MARCO])
    store = MemoryAttemptStore()
    first = login(
        users=repo,
        attempts=store,
        email=MARCO.email,
        password=PASSWORD,
        client_ip="192.0.2.1",
        secret=TEST_JWT_SECRET,
        now=T0,
    ).access_token
    second = login(
        users=repo,
        attempts=store,
        email=MARCO.email,
        password=PASSWORD,
        client_ip="192.0.2.2",
        secret=TEST_JWT_SECRET,
        now=T0,
    ).access_token
    principal = resolve_principal(repo, first, TEST_JWT_SECRET)
    logout(repo, principal)
    for token in (first, second):
        with pytest.raises(ApiError):
            resolve_principal(repo, token, TEST_JWT_SECRET)
    assert service.profile(MARCO).company == "Rossi HVAC"

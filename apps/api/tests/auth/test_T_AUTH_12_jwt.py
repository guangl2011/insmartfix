"""T-AUTH-12 (A): JWT rejection (D10 M-5, H-7). Every case → 401 from `resolve_principal`."""

import base64
import json
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
import pytest

from app.auth.service import MemoryUserRepo, Principal, resolve_principal
from app.auth.tokens import AUDIENCE, ISSUER, decode_token, issue_token
from app.clock import clock
from app.core.errors import ApiError
from tests.auth.fakes import MARCO, OWNER, TENANT
from tests.conftest import TEST_JWT_SECRET

SECRET = TEST_JWT_SECRET


def _claims(**over: Any) -> dict[str, Any]:
    now = int(time.time())
    base: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(MARCO.id),
        "role": "contractor",
        "tenant_id": str(TENANT),
        "contractor_id": str(MARCO.contractor_id),
        "tv": 0,
        "iat": now,
        "nbf": now,
        "exp": now + 3600,
        "jti": uuid4().hex,
    }
    base.update(over)
    return {k: v for k, v in base.items() if v is not ...}


def _sign(claims: dict[str, Any], alg: str = "HS256", key: str = SECRET) -> str:
    return jwt.encode(claims, key, algorithm=alg)


def _b64(d: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


def _assert_401(token: str | None, repo: MemoryUserRepo | None = None) -> None:
    with pytest.raises(ApiError) as exc:
        resolve_principal(repo or MemoryUserRepo([MARCO, OWNER]), token, SECRET)
    assert exc.value.status_code == 401
    assert exc.value.code == "UNAUTHENTICATED"
    assert exc.value.headers == {"WWW-Authenticate": "Bearer"}


def test_valid_token_resolves_principal_from_db_row() -> None:
    token, _ = issue_token(
        user_id=MARCO.id,
        role="contractor",
        tenant_id=TENANT,
        contractor_id=MARCO.contractor_id,
        token_version=0,
        secret=SECRET,
    )
    p = resolve_principal(MemoryUserRepo([MARCO]), token, SECRET)
    assert p == Principal(
        user_id=MARCO.id,
        role=p.role,
        tenant_id=TENANT,
        contractor_id=MARCO.contractor_id,
        name="Marco Rossi",
        company="Rossi HVAC",
    )
    assert p.is_contractor
    assert decode_token(token, SECRET).token_version == 0


def test_T_AUTH_12_missing_token() -> None:
    _assert_401(None)
    _assert_401("")
    _assert_401("not-a-jwt")


def test_T_AUTH_12_alg_none() -> None:
    header = _b64({"alg": "none", "typ": "JWT"})
    _assert_401(f"{header}.{_b64(_claims())}.")


def test_T_AUTH_12_hs512_and_wrong_secret() -> None:
    _assert_401(_sign(_claims(), alg="HS512"))
    _assert_401(_sign(_claims(), key="another-secret-of-sufficient-length-0123"))


def test_T_AUTH_12_rs_hs_confusion_header() -> None:
    # An "RS256" header signed with the shared secret as an HMAC key must not verify.
    header = _b64({"alg": "RS256", "typ": "JWT"})
    body = _b64(_claims())
    import hashlib
    import hmac

    sig = hmac.new(SECRET.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    _assert_401(f"{header}.{body}.{base64.urlsafe_b64encode(sig).rstrip(b'=').decode()}")


@pytest.mark.parametrize("claim", ["exp", "sub", "jti", "iat", "nbf", "iss", "aud", "tv", "role"])
def test_T_AUTH_12_missing_required_claim(claim: str) -> None:
    _assert_401(_sign(_claims(**{claim: ...})))


@pytest.mark.parametrize(
    "over",
    [{"iss": "someone-else"}, {"aud": "other-api"}, {"aud": ["insmartfix-api", "x"]}],
)
def test_T_AUTH_12_wrong_issuer_or_audience(over: dict[str, Any]) -> None:
    _assert_401(_sign(_claims(**over)))


def test_T_AUTH_12_nbf_in_future_and_expired() -> None:
    now = int(time.time())
    _assert_401(_sign(_claims(nbf=now + 600)))
    _assert_401(_sign(_claims(exp=now - 600, iat=now - 4000, nbf=now - 4000)))


def test_T_AUTH_12_expiry_uses_wall_clock_not_app_clock() -> None:
    now = int(time.time())
    expired = _sign(_claims(exp=now - 600, iat=now - 4000, nbf=now - 4000))
    clock.enable_fake(True)
    try:
        clock.set(datetime.now(UTC) - timedelta(hours=2))
        _assert_401(expired)
    finally:
        clock.enable_fake(False)


def test_T_AUTH_12_disabled_user_and_unknown_user() -> None:
    disabled = replace(MARCO, disabled_at=datetime(2026, 1, 1, tzinfo=UTC))
    _assert_401(_sign(_claims()), MemoryUserRepo([disabled]))
    _assert_401(_sign(_claims(sub=str(uuid4()))))


def test_T_AUTH_12_stale_token_version() -> None:
    _assert_401(_sign(_claims(tv=0)), MemoryUserRepo([replace(MARCO, token_version=1)]))
    _assert_401(_sign(_claims(tv="0")))
    _assert_401(_sign(_claims(tv=True)))


@pytest.mark.parametrize(
    "over",
    [
        {"role": "owner"},
        {"tenant_id": str(uuid4())},
        {"contractor_id": str(uuid4())},
        {"contractor_id": None},
    ],
)
def test_T_AUTH_12_token_claims_differ_from_db_row(over: dict[str, Any]) -> None:
    _assert_401(_sign(_claims(**over)))

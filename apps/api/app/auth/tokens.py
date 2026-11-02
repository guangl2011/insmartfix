"""JWT issue + strict decode (spec §4.3 HS256 / 12 h; D10 M-5, H-7).

Decoding pins `algorithms=["HS256"]`, requires every registered claim, checks `iss`/`aud`, and
validates `exp`/`nbf` against the **wall clock** (PyJWT's own `time.time()`), never `app.clock`.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import jwt

from app.clock import wall_now

ALGORITHM = "HS256"
ISSUER = "insmartfix"
AUDIENCE = "insmartfix-api"
TOKEN_TTL = timedelta(hours=12)
LEEWAY_SECONDS = 10
REQUIRED_CLAIMS = ["exp", "iat", "nbf", "sub", "iss", "aud", "jti", "tv", "role", "tenant_id"]


class InvalidTokenError(Exception):
    """Any reason a bearer token is not acceptable. Callers answer 401 without detail."""


@dataclass(frozen=True)
class TokenClaims:
    user_id: UUID
    role: str
    tenant_id: UUID
    contractor_id: UUID | None
    token_version: int
    jti: str


def issue_token(
    *,
    user_id: UUID,
    role: str,
    tenant_id: UUID,
    contractor_id: UUID | None,
    token_version: int,
    secret: str,
    issued_at: datetime | None = None,
) -> tuple[str, datetime]:
    iat = issued_at or wall_now()
    exp = iat + TOKEN_TTL
    payload: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(user_id),
        "role": role,
        "tenant_id": str(tenant_id),
        "contractor_id": str(contractor_id) if contractor_id else None,
        "tv": token_version,
        "iat": int(iat.timestamp()),
        "nbf": int(iat.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM), exp.replace(microsecond=0)


def decode_token(token: str, secret: str) -> TokenClaims:
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != ALGORITHM:
            raise InvalidTokenError("algorithm")
        payload = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            issuer=ISSUER,
            leeway=LEEWAY_SECONDS,
            options={"require": REQUIRED_CLAIMS, "strict_aud": True},
        )
        cid = payload.get("contractor_id")
        tv = payload["tv"]
        if not isinstance(tv, int) or isinstance(tv, bool):
            raise InvalidTokenError("tv")
        return TokenClaims(
            user_id=UUID(str(payload["sub"])),
            role=str(payload["role"]),
            tenant_id=UUID(str(payload["tenant_id"])),
            contractor_id=UUID(str(cid)) if cid is not None else None,
            token_version=tv,
            jti=str(payload["jti"]),
        )
    except InvalidTokenError:
        raise
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
        raise InvalidTokenError(type(exc).__name__) from exc

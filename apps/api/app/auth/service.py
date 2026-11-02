"""Login, principal resolution and logout (FR-1.1, FR-1.4, D11; D10 M-5, L-3)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.auth.emails import normalize_email
from app.auth.passwords import verify_password
from app.auth.ratelimit import AttemptStore, enforce_login_limit
from app.auth.tokens import InvalidTokenError, decode_token, issue_token
from app.clock import wall_now
from app.contract.auth import LoginResponse, Role, UserProfile
from app.contract.common import ErrorCode
from app.core.errors import ApiError


@dataclass(frozen=True)
class UserRecord:
    id: UUID
    tenant_id: UUID
    email: str
    name: str
    password_hash: str | None
    role: str
    contractor_id: UUID | None
    token_version: int
    disabled_at: datetime | None
    company: str | None = None


class UserRepo(Protocol):
    def by_email(self, normalized_email: str) -> UserRecord | None: ...
    def by_id(self, user_id: UUID) -> UserRecord | None: ...
    def bump_token_version(self, user_id: UUID) -> None: ...


@dataclass(frozen=True)
class Principal:
    """The authenticated caller. Role, tenant and contractor come from the DB row (D10 M-5)."""

    user_id: UUID
    role: Role
    tenant_id: UUID
    contractor_id: UUID | None
    name: str
    company: str | None

    @property
    def is_contractor(self) -> bool:
        return self.role is Role.CONTRACTOR


# Every login failure is the same 401 INVALID_CREDENTIALS: unknown email, wrong password, disabled
# user, user with no password hash (D10 L-3). No header or message varies.
UNAUTHENTICATED_HEADERS = {"WWW-Authenticate": "Bearer"}


def _unauthenticated() -> ApiError:
    return ApiError(401, ErrorCode.UNAUTHENTICATED, headers=UNAUTHENTICATED_HEADERS)


def profile(user: UserRecord) -> UserProfile:
    return UserProfile(
        user_id=user.id,
        name=user.name,
        role=Role(user.role),
        tenant_id=user.tenant_id,
        contractor_id=user.contractor_id,
        company=user.company,
    )


def login(
    *,
    users: UserRepo,
    attempts: AttemptStore,
    email: str,
    password: str,
    client_ip: str,
    secret: str,
    now: datetime | None = None,
) -> LoginResponse:
    """Rate limit first (identically for any email), then exactly one argon2 verify."""
    at = now or wall_now()
    normalized = normalize_email(email)
    enforce_login_limit(attempts, normalized, client_ip, at)
    user = users.by_email(normalized)
    ok = verify_password(user.password_hash if user else None, password)
    if user is None or not ok or user.disabled_at is not None:
        raise ApiError(401, ErrorCode.INVALID_CREDENTIALS)
    token, expires_at = issue_token(
        user_id=user.id,
        role=user.role,
        tenant_id=user.tenant_id,
        contractor_id=user.contractor_id,
        token_version=user.token_version,
        secret=secret,
        issued_at=at,
    )
    return LoginResponse(
        access_token=token, expires_at=expires_at, user=profile(user), server_time=at
    )


def resolve_principal(users: UserRepo, token: str | None, secret: str) -> Principal:
    """401 on no token, any invalid token, a disabled user, a stale `token_version`, or token
    claims that no longer match the user row."""
    if not token:
        raise _unauthenticated()
    try:
        claims = decode_token(token, secret)
    except InvalidTokenError:
        raise _unauthenticated() from None
    user = users.by_id(claims.user_id)
    if (
        user is None
        or user.disabled_at is not None
        or user.token_version != claims.token_version
        or user.role != claims.role
        or user.tenant_id != claims.tenant_id
        or user.contractor_id != claims.contractor_id
    ):
        raise _unauthenticated()
    return Principal(
        user_id=user.id,
        role=Role(user.role),
        tenant_id=user.tenant_id,
        contractor_id=user.contractor_id,
        name=user.name,
        company=user.company,
    )


def logout(users: UserRepo, principal: Principal) -> None:
    """D11: bump `token_version`, revoking every outstanding token of this user."""
    users.bump_token_version(principal.user_id)


class MemoryUserRepo:
    """In-memory repo for unit tests."""

    def __init__(self, users: Sequence[UserRecord] = ()) -> None:
        self.users = {u.id: u for u in users}

    def by_email(self, normalized_email: str) -> UserRecord | None:
        return next((u for u in self.users.values() if u.email == normalized_email), None)

    def by_id(self, user_id: UUID) -> UserRecord | None:
        return self.users.get(user_id)

    def bump_token_version(self, user_id: UUID) -> None:
        from dataclasses import replace

        u = self.users[user_id]
        self.users[user_id] = replace(u, token_version=u.token_version + 1)

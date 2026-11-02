"""Auth + identity routes (spec §5; FR-1.1, FR-1.4; D11 logout; D10 M-5, M-7, L-3)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.deps import CurrentPrincipal
from app.auth.ratelimit import client_ip, parse_trusted_proxies
from app.auth.store import PgAttemptStore, SqlUserRepo
from app.clock import now
from app.contract.auth import LoginRequest, LoginResponse, MeResponse
from app.contract.common import error_responses
from app.db.session import get_db, get_engine
from app.routes import API_PREFIX
from app.settings import Settings, get_settings

router = APIRouter(prefix=API_PREFIX, tags=["auth"])


@router.post(
    "/auth/login",
    operation_id="login",
    response_model=LoginResponse,
    responses=error_responses(401, 422, 429),
)
def login(
    body: LoginRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginResponse:
    """Email + password login (FR-1.1). Every failure is an identical 401 (D10 L-3)."""
    ip = client_ip(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
        parse_trusted_proxies(settings.trusted_proxies),
    )
    result = service.login(
        users=SqlUserRepo(db),
        attempts=PgAttemptStore(get_engine(settings.database_url)),
        email=body.email,
        password=body.password,
        client_ip=ip,
        secret=settings.jwt_secret.get_secret_value(),
    )
    return result.model_copy(update={"server_time": now()})


@router.post(
    "/auth/logout",
    operation_id="logout",
    status_code=204,
    response_class=Response,
    responses=error_responses(401),
)
def logout(principal: CurrentPrincipal, db: Annotated[Session, Depends(get_db)]) -> Response:
    """Revoke every outstanding token of the caller by bumping `token_version` (D11)."""
    service.logout(SqlUserRepo(db), principal)
    return Response(status_code=204)


@router.get(
    "/me",
    operation_id="get_me",
    response_model=MeResponse,
    responses=error_responses(401),
)
def get_me(principal: CurrentPrincipal) -> MeResponse:
    """The signed-in user; contractors get their `contractor_id` here (FR-1.4)."""
    return MeResponse(
        user_id=principal.user_id,
        name=principal.name,
        role=principal.role,
        tenant_id=principal.tenant_id,
        contractor_id=principal.contractor_id,
        company=principal.company,
        server_time=now(),
    )

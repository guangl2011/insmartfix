"""Auth + identity routes (spec §5; FR-1.1, FR-1.4; D11). Stubs until M1-T4."""

from fastapi import APIRouter, Response, Security
from fastapi.responses import JSONResponse

from app.contract.auth import LoginRequest, LoginResponse, MeResponse
from app.contract.common import error_responses
from app.contract.security import bearer_scheme
from app.routes._stub import not_implemented

router = APIRouter(tags=["auth"])
authed = [Security(bearer_scheme)]


@router.post(
    "/auth/login",
    operation_id="login",
    response_model=LoginResponse,
    responses=error_responses(401, 422, 429, 501),
)
def login(body: LoginRequest) -> JSONResponse:
    """Email + password login (FR-1.1). Every failure is an identical 401 (D10 L-3)."""
    return not_implemented()


@router.post(
    "/auth/logout",
    operation_id="logout",
    status_code=204,
    response_class=Response,
    dependencies=authed,
    responses=error_responses(401, 501),
)
def logout() -> Response:
    """Revoke every outstanding token of the caller by bumping `token_version` (D11)."""
    return not_implemented()


@router.get(
    "/me",
    operation_id="get_me",
    response_model=MeResponse,
    dependencies=authed,
    responses=error_responses(401, 501),
)
def get_me() -> JSONResponse:
    """The signed-in user; contractors get their `contractor_id` here (FR-1.4)."""
    return not_implemented()

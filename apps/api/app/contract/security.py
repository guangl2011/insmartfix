"""OpenAPI security scheme for bearer-token routes (spec §5; FR-1.3 mobile, FR-1.2 via web BFF)."""

from fastapi.security import HTTPBearer

# auto_error=False: the auth dependency (M1-T4) owns the 401 envelope, not FastAPI's default 403.
bearer_scheme = HTTPBearer(
    scheme_name="bearerAuth",
    description="JWT from `POST /v1/auth/login`; revoked by `POST /v1/auth/logout` (D11).",
    auto_error=False,
)

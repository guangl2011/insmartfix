"""501 placeholder used by contract route stubs (M1-T1) until each route is implemented."""

from fastapi.responses import JSONResponse

from app.contract.common import ErrorCode
from app.core.errors import error_response


def not_implemented() -> JSONResponse:
    return error_response(501, ErrorCode.NOT_IMPLEMENTED)

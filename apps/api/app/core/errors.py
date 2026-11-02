"""Error envelope (spec §5): every error is `{"error": {"code", "message"}, "server_time"}`."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.clock import now
from app.contract.common import ErrorCode, ErrorEnvelope, OfferUnavailableReason

logger = logging.getLogger(__name__)

# Fixed, generic messages: identical bodies for identical codes (D10 M-1/M-2, T-AUTH-15).
DEFAULT_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.INVALID_CREDENTIALS: "Email or password is incorrect.",
    ErrorCode.RATE_LIMITED: "Too many attempts. Try again in a minute.",
    ErrorCode.UNAUTHENTICATED: "Sign in to continue.",
    ErrorCode.FORBIDDEN: "You don't have access to this.",
    ErrorCode.NOT_FOUND: "Not found.",
    ErrorCode.METHOD_NOT_ALLOWED: "Method not allowed.",
    ErrorCode.OFFER_UNAVAILABLE: "This offer is no longer available.",
    ErrorCode.INVALID_TRANSITION: "That step isn't allowed right now.",
    ErrorCode.ALREADY_COMPLETED: "This job has already been completed.",
    ErrorCode.VALIDATION_ERROR: "The request is invalid.",
    ErrorCode.IDEMPOTENCY_KEY_REUSED: "This Idempotency-Key was used with a different body.",
    ErrorCode.PAYLOAD_TOO_LARGE: "The upload is too large.",
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: "Unsupported file type.",
    ErrorCode.NOT_IMPLEMENTED: "Not implemented yet.",
    ErrorCode.NOT_READY: "Service is not ready.",
    ErrorCode.INTERNAL: "Something went wrong.",
}

STATUS_CODES: dict[int, ErrorCode] = {
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    415: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
    501: ErrorCode.NOT_IMPLEMENTED,
}


class ApiError(Exception):
    """Raise from anywhere in a request to return the envelope with this status and code."""

    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        message: str | None = None,
        *,
        reason: OfferUnavailableReason | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(code.value)
        self.status_code = status_code
        self.code = code
        self.message = message or DEFAULT_MESSAGES[code]
        self.reason = reason
        self.headers = headers


def error_response(
    status_code: int,
    code: ErrorCode,
    message: str | None = None,
    *,
    reason: OfferUnavailableReason | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorEnvelope.model_validate(
        {
            "error": {
                "code": code,
                "message": message or DEFAULT_MESSAGES[code],
                "reason": reason,
            },
            "server_time": now(),
        }
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json", exclude_none=True),
        headers=headers,
    )


async def _api_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)  # noqa: S101 — registered for ApiError only
    return error_response(
        exc.status_code, exc.code, exc.message, reason=exc.reason, headers=exc.headers
    )


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    # Never echo the rejected input back (it may hold credentials or PII; NFR-6).
    return error_response(422, ErrorCode.VALIDATION_ERROR)


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    headers = dict(exc.headers) if exc.headers else None
    if exc.status_code == 400:
        # Starlette's "error parsing the body" (malformed JSON/multipart): a validation error.
        return error_response(422, ErrorCode.VALIDATION_ERROR, headers=headers)
    code = STATUS_CODES.get(exc.status_code, ErrorCode.INTERNAL)
    return error_response(exc.status_code, code, headers=headers)


async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error: %s", type(exc).__name__)
    return error_response(500, ErrorCode.INTERNAL)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled)

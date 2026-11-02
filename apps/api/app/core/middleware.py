"""ASGI middleware: request id + access log (NFR-7), JSON body size limit (D10 M-8)."""

import logging
import re
import time
import uuid
from typing import Any

from fastapi import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.contract.common import ErrorCode
from app.core.errors import error_response
from app.core.logging import request_id_var

access_log = logging.getLogger("app.access")

REQUEST_ID_HEADER = "x-request-id"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

JSON_BODY_LIMIT = 64 * 1024  # D10 M-8
MULTIPART_BODY_LIMIT = 10 * 1024 * 1024 + 64 * 1024  # FR-7.7 10 MB file + form overhead


class RequestContextMiddleware:
    """Assigns a request id (honours a well-formed inbound `X-Request-ID`), echoes it back and
    writes one access-log line per request with the route template, never the raw path/query."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        inbound = _header(scope, REQUEST_ID_HEADER)
        rid = inbound if inbound and _REQUEST_ID_RE.match(inbound) else uuid.uuid4().hex
        token = request_id_var.set(rid)
        status = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", [])
                message["headers"] = [
                    *message["headers"],
                    (REQUEST_ID_HEADER.encode(), rid.encode()),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = scope.get("route")
            access_log.info(
                "request",
                extra={
                    "method": scope["method"],
                    "route": getattr(route, "path", "<unmatched>"),
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            request_id_var.reset(token)


class BodyTooLargeError(HTTPException):
    """An HTTPException, so FastAPI's body reader re-raises it instead of turning it into 400."""

    def __init__(self) -> None:
        super().__init__(status_code=413)


class BodySizeLimitMiddleware:
    """Rejects request bodies over the limit with 413: up front from `Content-Length`, and while
    streaming for chunked bodies. Multipart uploads get the photo limit, everything else 64 KB."""

    def __init__(
        self,
        app: ASGIApp,
        json_limit: int = JSON_BODY_LIMIT,
        multipart_limit: int = MULTIPART_BODY_LIMIT,
    ) -> None:
        self.app = app
        self.json_limit = json_limit
        self.multipart_limit = multipart_limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        ctype = (_header(scope, "content-type") or "").lower()
        limit = self.multipart_limit if ctype.startswith("multipart/") else self.json_limit
        declared = _header(scope, "content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > limit):
            await error_response(413, ErrorCode.PAYLOAD_TOO_LARGE)(scope, receive, send)
            return
        seen = 0

        async def limited_receive() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    raise BodyTooLargeError()
            return message

        await self.app(scope, limited_receive, send)


def _header(scope: Scope, name: str) -> str | None:
    raw: Any = name.encode()
    for k, v in scope.get("headers", []):
        if k == raw:
            return str(v.decode("latin-1"))
    return None

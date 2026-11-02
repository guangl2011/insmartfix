"""Stream a `multipart/form-data` body and return exactly one file part (D10 M-9).

The size limit is enforced while the body is read (never after buffering it all). A request with
no file part, or with more than one, is malformed. Only the `file` field is accepted; any other
field, file or not, is malformed too, so nothing unexpected is ever parsed into memory.
"""

from collections.abc import AsyncIterator

from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, parse_options_header

FIELD = "file"
# Headers, boundaries and the disposition line: generous, but small next to the file limit.
ENVELOPE_ALLOWANCE = 16 * 1024


class UploadTooLargeError(Exception):
    """The body or the file part exceeds the limit (→ 413)."""


class MalformedUploadError(Exception):
    """Not multipart, no file part, more than one part, or an unexpected field (→ 422)."""


class _Collector:
    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        self.parts = 0
        self.data = bytearray()
        self._header_name = b""
        self._header_value = b""
        self._disposition = b""

    def on_part_begin(self) -> None:
        self.parts += 1
        if self.parts > 1:
            raise MalformedUploadError("exactly one part is accepted")
        self._disposition = b""

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_name += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._header_value += data[start:end]

    def on_header_end(self) -> None:
        if self._header_name.strip().lower() == b"content-disposition":
            self._disposition = self._header_value
        self._header_name = self._header_value = b""

    def on_headers_finished(self) -> None:
        kind, params = parse_options_header(self._disposition)
        if (
            kind != b"form-data"
            or params.get(b"name") != FIELD.encode()
            or b"filename" not in params
        ):
            raise MalformedUploadError("expected a single file part named 'file'")

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if len(self.data) + (end - start) > self.max_bytes:
            raise UploadTooLargeError
        self.data += data[start:end]


async def read_single_file(
    content_type: str | None,
    content_length: str | None,
    stream: AsyncIterator[bytes],
    *,
    max_bytes: int,
) -> bytes:
    kind, params = parse_options_header(content_type or "")
    boundary = params.get(b"boundary")
    if kind != b"multipart/form-data" or not boundary:
        raise MalformedUploadError("expected multipart/form-data")

    body_cap = max_bytes + ENVELOPE_ALLOWANCE
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError as exc:
            raise MalformedUploadError("bad Content-Length") from exc
        if declared > body_cap:
            raise UploadTooLargeError

    collector = _Collector(max_bytes)
    parser = MultipartParser(
        boundary,
        callbacks={
            "on_part_begin": collector.on_part_begin,
            "on_header_field": collector.on_header_field,
            "on_header_value": collector.on_header_value,
            "on_header_end": collector.on_header_end,
            "on_headers_finished": collector.on_headers_finished,
            "on_part_data": collector.on_part_data,
        },
    )
    received = 0
    try:
        async for chunk in stream:
            received += len(chunk)
            if received > body_cap:
                raise UploadTooLargeError
            parser.write(chunk)
        parser.finalize()
    except MultipartParseError as exc:
        raise MalformedUploadError("unparseable multipart body") from exc
    if collector.parts != 1 or not collector.data:
        raise MalformedUploadError("no file")
    return bytes(collector.data)

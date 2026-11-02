"""T-PHOTO-1 / T-PHOTO-3 (module layer): one streamed file part, 10 MB enforced while reading."""

import asyncio
from collections.abc import AsyncIterator, Sequence

import pytest

from app.media.upload import MalformedUploadError, UploadTooLargeError, read_single_file

BOUNDARY = "xBoUnDaRyx"
CT = f"multipart/form-data; boundary={BOUNDARY}"


def part(name: str, content: bytes, filename: str | None = "photo.jpg") -> bytes:
    disposition = f'form-data; name="{name}"' + (f'; filename="{filename}"' if filename else "")
    return (
        (
            f"--{BOUNDARY}\r\nContent-Disposition: {disposition}\r\n"
            f"Content-Type: image/jpeg\r\n\r\n"
        ).encode()
        + content
        + b"\r\n"
    )


def body(*parts: bytes) -> bytes:
    return b"".join(parts) + f"--{BOUNDARY}--\r\n".encode()


async def _chunks(data: bytes, size: int = 7_000) -> AsyncIterator[bytes]:
    for i in range(0, len(data), size):
        yield data[i : i + size]


def read(
    data: bytes,
    *,
    content_type: str | None = CT,
    content_length: str | None = None,
    max_bytes: int = 1_000,
    chunks: Sequence[bytes] | None = None,
) -> bytes:
    async def stream() -> AsyncIterator[bytes]:
        if chunks is None:
            async for c in _chunks(data):
                yield c
        else:
            for c in chunks:
                yield c

    return asyncio.run(
        read_single_file(content_type, content_length, stream(), max_bytes=max_bytes)
    )


def test_T_PHOTO_1_reads_the_single_file_part() -> None:
    payload = bytes(range(256)) * 3
    assert read(body(part("file", payload))) == payload


def test_T_PHOTO_1_file_over_the_limit_is_rejected_while_streaming() -> None:
    with pytest.raises(UploadTooLargeError):
        read(body(part("file", b"x" * 1_001)), max_bytes=1_000)


def test_T_PHOTO_1_declared_length_over_the_cap_is_rejected_before_reading() -> None:
    with pytest.raises(UploadTooLargeError):
        read(b"", content_length=str(10_000_000), max_bytes=1_000, chunks=[b"never read"])


def test_T_PHOTO_1_body_over_the_cap_is_rejected_even_without_content_length() -> None:
    # A huge non-file preamble never reaches the parser's buffers.
    flood = [b"\r\n" * 20_000] * 5
    with pytest.raises(UploadTooLargeError):
        read(b"", chunks=flood, max_bytes=1_000)


def test_T_PHOTO_3_two_file_parts_are_rejected() -> None:
    with pytest.raises(MalformedUploadError):
        read(body(part("file", b"a"), part("file", b"b")))


@pytest.mark.parametrize(
    "data",
    [
        body(part("other", b"a")),  # wrong field name
        body(part("file", b"a", filename=None)),  # a plain field, not a file
        body(),  # no parts
        body(part("file", b"")),  # empty file
        b"not multipart at all",
    ],
)
def test_T_PHOTO_3_unexpected_shapes_are_malformed(data: bytes) -> None:
    with pytest.raises(MalformedUploadError):
        read(data)


@pytest.mark.parametrize(
    "content_type",
    [None, "application/json", "multipart/form-data", "multipart/mixed; boundary=x"],
)
def test_T_PHOTO_3_requires_multipart_form_data_with_a_boundary(content_type: str | None) -> None:
    with pytest.raises(MalformedUploadError):
        read(body(part("file", b"a")), content_type=content_type)


def test_bad_content_length_is_malformed() -> None:
    with pytest.raises(MalformedUploadError):
        read(body(part("file", b"a")), content_length="lots")

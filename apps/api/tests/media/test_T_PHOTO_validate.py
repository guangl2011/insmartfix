"""T-PHOTO-1 / T-PHOTO-3 (module layer): sniffing, bomb limits, re-encoding, metadata stripping."""

import hashlib
import io
import resource

import pytest
from PIL import Image

from app.media.validate import MAX_EDGE, UnsupportedImageError, clean, sniff
from tests.media import images

METADATA_MARKERS = (
    b"Exif",
    b"http://ns.adobe.com/xap",
    b"xmpmeta",
    b"Photoshop 3.0",
    b"8BIM",
    images.SECRET,
    b"ICC_PROFILE",
    b"GPS",
)


def _assert_no_metadata(data: bytes) -> None:
    for marker in METADATA_MARKERS:
        assert marker not in data, marker
    with Image.open(io.BytesIO(data)) as img:
        assert dict(img.getexif()) == {}
        for key in ("exif", "xmp", "XML:com.adobe.xmp", "icc_profile", "photoshop", "Comment"):
            assert key not in img.info, key


@pytest.mark.parametrize(
    ("head", "kind"),
    [
        (b"\xff\xd8\xff\xe0\x00\x10JFIF", "jpeg"),
        (b"\x89PNG\r\n\x1a\n\x00\x00", "png"),
        (b"\x00\x00\x00\x18ftypheic\x00\x00", "heic"),
        (b"\x00\x00\x00\x18ftypmif1\x00\x00", "heic"),
        (b"%PDF-1.7\n", None),
        (b"<html><body>", None),
        (b"GIF89a\x01\x00", None),
        (b"\x00\x00\x00\x18ftypmp42", None),
        (b"", None),
    ],
)
def test_T_PHOTO_1_sniffs_magic_bytes_not_names(head: bytes, kind: str | None) -> None:
    assert sniff(head) == kind


def test_T_PHOTO_1_jpeg_is_reencoded_and_gps_stripped() -> None:
    upload = images.jpeg()
    got = clean(upload)
    assert got.content_type == "image/jpeg"
    assert (got.width, got.height) == (40, 20)
    assert got.sha256 == hashlib.sha256(got.content).hexdigest()
    _assert_no_metadata(got.content)


def test_T_PHOTO_1_orientation_is_applied_before_stripping() -> None:
    got = clean(images.jpeg(size=(40, 20), orientation=6))  # rotate 90°
    assert (got.width, got.height) == (20, 40)
    _assert_no_metadata(got.content)


def test_T_PHOTO_3_png_text_exif_and_icc_chunks_are_gone() -> None:
    got = clean(images.png())
    assert got.content_type == "image/png"
    assert set(images.png_chunk_types(got.content)) <= {b"IHDR", b"IDAT", b"IEND"}
    _assert_no_metadata(got.content)
    with Image.open(io.BytesIO(got.content)) as img:
        assert img.mode == "RGBA"


def test_T_PHOTO_3_heic_is_stored_as_jpeg_without_metadata() -> None:
    got = clean(images.heic())
    assert got.content_type == "image/jpeg"
    assert (got.width, got.height) == (64, 48)
    _assert_no_metadata(got.content)


def test_T_PHOTO_3_polyglot_is_stored_only_as_reencoded_bytes() -> None:
    upload = images.jpeg() + b"<html><script>alert(1)</script></html>PK\x03\x04zipzipzip"
    got = clean(upload)
    assert hashlib.sha256(upload).hexdigest() != got.sha256
    assert b"<script>" not in got.content
    assert b"PK\x03\x04" not in got.content
    assert got.content.endswith(b"\xff\xd9")  # no trailing data after the JPEG end marker


@pytest.mark.parametrize(
    "bomb",
    [
        images.png_header_only(60_000, 60_000),  # far past Pillow's own 2x bomb error
        images.png_header_only(7_000, 7_000),  # 49 MP: over 40 MP, edges under 8192
        images.png_header_only(MAX_EDGE + 1, 10),  # long edge
    ],
)
def test_T_PHOTO_3_decompression_bombs_are_rejected_with_bounded_memory(bomb: bytes) -> None:
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # KiB on Linux
    with pytest.raises(UnsupportedImageError):
        clean(bomb)
    grew_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before
    assert grew_kib < 64 * 1024, f"RSS grew {grew_kib} KiB while rejecting a bomb"
    assert len(bomb) < 50_000


def test_T_PHOTO_3_oversized_heic_is_rejected() -> None:
    with pytest.raises(UnsupportedImageError, match="dimensions"):
        clean(images.heic(size=(MAX_EDGE + 8, 64)))


@pytest.mark.parametrize(
    "data",
    [
        b"%PDF-1.7\n" + b"x" * 100,
        b"<html>hello</html>",
        b"\xff\xd8\xff" + b"\x00" * 64,  # JPEG signature, garbage body
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 64,
        b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64,
    ],
)
def test_T_PHOTO_1_non_images_and_truncated_images_are_unsupported(data: bytes) -> None:
    with pytest.raises(UnsupportedImageError):
        clean(data)


def test_T_PHOTO_3_signature_must_match_the_decoded_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A PNG body behind a JPEG signature is not trusted.
    with pytest.raises(UnsupportedImageError):
        clean(b"\xff\xd8\xff" + images.png())
    # And if the sniff and the decoder ever disagree, the decoder's answer doesn't win.
    monkeypatch.setattr("app.media.validate.sniff", lambda _: "png")
    with pytest.raises(UnsupportedImageError, match="signature"):
        clean(images.jpeg())

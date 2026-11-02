"""Validate an uploaded photo and re-encode it from pixels only (FR-7.7, D10 M-9, C-4).

1. Sniff the magic bytes (JPEG, PNG, HEIC). The client's filename and Content-Type are ignored.
2. Read the header only and reject a long edge > 8192 px or more than 40 MP *before* decoding.
   `DecompressionBombWarning` is an error, so Pillow's own bomb check also rejects.
3. Decode, apply the EXIF orientation, then copy the raw pixels into a brand-new image. That image
   has no EXIF, XMP, IPTC, ICC, PNG text chunks or HEIC metadata boxes: nothing to strip, because
   nothing is carried over. Only these bytes are ever stored, so a polyglot tail never survives.
4. Encode as PNG for PNG input and as JPEG otherwise (HEIC is stored as JPEG). The server chooses
   the content type.
"""

import hashlib
import io
import warnings
from dataclasses import dataclass
from typing import Literal

import pillow_heif
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_EDGE = 8192
JPEG_QUALITY = 88

Kind = Literal["jpeg", "png", "heic"]

_HEIC_BRANDS = frozenset({b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"})
# Pillow format names accepted for each sniffed kind (MPO = multi-picture JPEG from phones).
_FORMATS: dict[Kind, frozenset[str]] = {
    "jpeg": frozenset({"JPEG", "MPO"}),
    "png": frozenset({"PNG"}),
    "heic": frozenset({"HEIF"}),
}

Image.MAX_IMAGE_PIXELS = MAX_PIXELS
pillow_heif.register_heif_opener(thumbnails=False)


class UnsupportedImageError(Exception):
    """Not a JPEG/PNG/HEIC we can safely decode (→ 415)."""


@dataclass(frozen=True)
class CleanImage:
    content: bytes
    content_type: Literal["image/jpeg", "image/png"]
    width: int
    height: int
    sha256: str


def sniff(head: bytes) -> Kind | None:
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(head) >= 12 and head[4:8] == b"ftyp" and head[8:12] in _HEIC_BRANDS:
        return "heic"
    return None


def clean(data: bytes) -> CleanImage:
    kind = sniff(data[:16])
    if kind is None:
        raise UnsupportedImageError("unrecognised file signature")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as img:
                if img.format not in _FORMATS[kind]:
                    raise UnsupportedImageError("content does not match its signature")
                width, height = img.size  # header only: nothing decoded yet
                if max(width, height) > MAX_EDGE or width * height > MAX_PIXELS:
                    raise UnsupportedImageError("image dimensions too large")
                img.load()
                return _reencode(ImageOps.exif_transpose(img), kind)
    except UnsupportedImageError:
        raise
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        ValueError,
        SyntaxError,
    ) as exc:
        raise UnsupportedImageError(type(exc).__name__) from exc


def _reencode(img: Image.Image, kind: Kind) -> CleanImage:
    if kind == "png":
        mode = img.mode if img.mode in {"RGB", "RGBA", "L", "LA"} else "RGBA"
    else:
        mode = "RGB"
    pixels = img.convert(mode) if img.mode != mode else img
    # A fresh image from raw pixels carries no `info` at all (no EXIF/XMP/ICC/text chunks).
    fresh = Image.frombytes(mode, pixels.size, pixels.tobytes())
    out = io.BytesIO()
    if kind == "png":
        fresh.save(out, format="PNG", optimize=True)
        content_type: Literal["image/jpeg", "image/png"] = "image/png"
    else:
        fresh.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        content_type = "image/jpeg"
    content = out.getvalue()
    return CleanImage(
        content=content,
        content_type=content_type,
        width=fresh.width,
        height=fresh.height,
        sha256=hashlib.sha256(content).hexdigest(),
    )

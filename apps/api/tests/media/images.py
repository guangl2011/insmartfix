"""Test images built in memory: metadata-laden photos, bombs and polyglots (no binary fixtures)."""

import io
import struct
import zlib

import pillow_heif
from PIL import Image, PngImagePlugin

GPS_IFD = 0x8825
ORIENTATION = 0x0112
XMP = (
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-'
    b'syntax-ns#"><rdf:Description xmlns:exif="http://ns.adobe.com/exif/1.0/" '
    b'exif:GPSLatitude="40,45.0N"/></rdf:RDF></x:xmpmeta>'
)
SECRET = b"OWNER-SERIAL-12345"


def exif_bytes(orientation: int = 1) -> bytes:
    exif = Image.Exif()
    exif[ORIENTATION] = orientation
    exif[0x013B] = SECRET.decode()  # Artist
    exif[0xA431] = SECRET.decode()  # BodySerialNumber
    exif.get_ifd(GPS_IFD).update({1: "N", 2: (40.0, 45.0, 0.0), 3: "W", 4: (73.0, 59.0, 0.0)})
    return exif.tobytes()


def _app_segment(marker: int, payload: bytes) -> bytes:
    return struct.pack(">BBH", 0xFF, marker, len(payload) + 2) + payload


def jpeg(size: tuple[int, int] = (40, 20), orientation: int = 1) -> bytes:
    """A JPEG with EXIF (GPS, serial, artist), XMP and IPTC segments."""
    out = io.BytesIO()
    Image.new("RGB", size, (200, 40, 40)).save(out, "JPEG", exif=exif_bytes(orientation))
    data = out.getvalue()
    xmp = _app_segment(0xE1, b"http://ns.adobe.com/xap/1.0/\x00" + XMP)
    iptc = _app_segment(0xED, b"Photoshop 3.0\x008BIM\x04\x04\x00\x00\x00\x00\x00\x0c" + SECRET)
    return data[:2] + xmp + iptc + data[2:]


def png() -> bytes:
    """A PNG with tEXt, iTXt and zTXt chunks, an eXIf chunk and an ICC profile."""
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", SECRET.decode())
    info.add_itxt("XML:com.adobe.xmp", XMP.decode())
    info.add_text("Location", "40.75,-73.98", zip=True)
    out = io.BytesIO()
    Image.new("RGBA", (30, 30), (0, 100, 200, 128)).save(
        out, "PNG", pnginfo=info, exif=exif_bytes(), icc_profile=b"\x00" * 128
    )
    return out.getvalue()


def heic(size: tuple[int, int] = (64, 48)) -> bytes:
    pillow_heif.register_heif_opener()
    out = io.BytesIO()
    Image.new("RGB", size, (10, 200, 10)).save(out, "HEIF", exif=exif_bytes(), xmp=XMP)
    return out.getvalue()


def png_header_only(width: int, height: int) -> bytes:
    """A tiny PNG whose IHDR declares a huge image: a decompression bomb."""

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    idat = zlib.compress(b"\x00" * 4096, 9)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def png_chunk_types(data: bytes) -> list[bytes]:
    pos, kinds = 8, []
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kinds.append(data[pos + 4 : pos + 8])
        pos += 12 + length
    return kinds

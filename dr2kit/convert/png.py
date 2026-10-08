"""A small PNG reader and writer in pure Python (zlib only).

Why our own: the core must import inside Blender's Python, which has no Pillow, and PNG
is the format modders edit textures in. Writing is simple (one IDAT, filter 0 or "up").
Reading covers what image editors save: 8- and 16-bit greyscale, grey+alpha, RGB, RGBA,
and palette images (1/2/4/8-bit), with all five row filters. Interlaced (Adam7) files
are read through Pillow when it is installed, and refused with a clear message otherwise.

Images travel through the toolkit as `Image`: width, height, and RGBA bytes (4 bytes per
pixel, rows top to bottom). That one layout keeps every converter simple.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from ..errors import FormatError

SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass
class Image:
    """An RGBA image: ``width`` × ``height`` pixels, 4 bytes each, rows top to bottom."""
    width: int
    height: int
    rgba: bytes

    def __post_init__(self):
        if len(self.rgba) != self.width * self.height * 4:
            raise ValueError(f"{self.width}x{self.height} needs {self.width * self.height * 4} "
                             f"bytes of RGBA, got {len(self.rgba)}")


def _chunk(kind: bytes, body: bytes) -> bytes:
    return (struct.pack(">I", len(body)) + kind + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))


def encode(img: Image, mode: str = "RGBA", level: int = 6) -> bytes:
    """PNG bytes for ``img``. ``mode`` is ``"RGBA"``, ``"RGB"`` or ``"L"`` (uses red)."""
    bpp = {"RGBA": 4, "RGB": 3, "L": 1}[mode]
    colour_type = {"RGBA": 6, "RGB": 2, "L": 0}[mode]
    src = img.rgba
    if mode == "RGBA":
        px = src
    else:
        try:
            import numpy as np
            a = np.frombuffer(src, dtype=np.uint8).reshape(-1, 4)
            px = a[:, :bpp].tobytes()
        except ImportError:
            px = b"".join(src[i:i + bpp] for i in range(0, len(src), 4))
    stride = img.width * bpp
    # "Up" filter (each row minus the one above): compresses textures noticeably better
    # than no filter, and is one subtraction per byte.
    try:
        import numpy as np
        a = np.frombuffer(px, dtype=np.uint8).reshape(img.height, stride)
        up = a.copy()
        up[1:] -= a[:-1]
        ft = np.full((img.height, 1), 2, dtype=np.uint8)
        ft[0] = 0
        raw = np.hstack([ft, up]).tobytes()
    except ImportError:
        raw = bytearray()
        prev = bytes(stride)
        for y in range(img.height):
            row = px[y * stride:(y + 1) * stride]
            up = bytes((a - b) & 0xFF for a, b in zip(row, prev)) if y else row
            raw += (b"\x02" if y else b"\x00") + up
            prev = row
    ihdr = struct.pack(">IIBBBBB", img.width, img.height, 8, colour_type, 0, 0, 0)
    return (SIGNATURE + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(bytes(raw), level))
            + _chunk(b"IEND", b""))


def write(path: str | Path, img: Image, mode: str = "RGBA") -> None:
    Path(path).write_bytes(encode(img, mode))


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _unfilter(raw: bytes, height: int, stride: int, bpp: int, source: str) -> bytes:
    out = bytearray(height * stride)
    prev = bytearray(stride)
    pos = 0
    for y in range(height):
        if pos + 1 + stride > len(raw):
            raise FormatError(f"{source}: image data ends early (row {y})")
        ft = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if ft == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                ul = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(left, prev[i], ul)) & 0xFF
        elif ft != 0:
            raise FormatError(f"{source}: unknown PNG row filter {ft}")
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return bytes(out)


def decode(data: bytes, source: str = "<png>") -> Image:
    """Read PNG bytes into an RGBA `Image`. Raises `FormatError` on anything unreadable.

    Uses Pillow when it is installed (much faster); the pure-Python path below gives
    the same pixels and is what runs inside Blender.
    """
    if data[:8] != SIGNATURE:
        raise FormatError(f"{source}: not a PNG file")
    try:
        import PIL  # noqa: F401
    except ImportError:
        return decode_pure(data, source)
    return _decode_with_pillow(data, source)


def decode_pure(data: bytes, source: str = "<png>") -> Image:
    """`decode` without Pillow (pure Python + zlib)."""
    if data[:8] != SIGNATURE:
        raise FormatError(f"{source}: not a PNG file")
    pos = 8
    ihdr = None
    idat = bytearray()
    palette = b""
    trns = b""
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            palette = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
    if ihdr is None:
        raise FormatError(f"{source}: no IHDR chunk")
    w, h, depth, ctype, _, _, interlace = ihdr
    if interlace:
        return _decode_with_pillow(data, source)
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype)
    if channels is None or depth not in (1, 2, 4, 8, 16):
        raise FormatError(f"{source}: unsupported PNG colour type {ctype} / depth {depth}")
    bits = channels * depth
    stride = (w * bits + 7) // 8
    raw = _unfilter(zlib.decompress(bytes(idat)), h, stride, max(1, bits // 8), source)

    def samples(row: bytes) -> list[int]:
        if depth == 8:
            return list(row)
        if depth == 16:
            return list(row[0::2])                      # keep the high byte
        per = 8 // depth
        mask = (1 << depth) - 1
        out = []
        for byte in row:
            for k in range(per):
                out.append((byte >> (8 - depth * (k + 1))) & mask)
        return out

    out = bytearray(w * h * 4)
    scale = 255 // ((1 << depth) - 1) if depth < 8 else 1
    for y in range(h):
        s = samples(raw[y * stride:(y + 1) * stride])
        o = y * w * 4
        for x in range(w):
            if ctype == 3:
                i = s[x]
                r, g, b = palette[i * 3:i * 3 + 3]
                a = trns[i] if i < len(trns) else 255
            elif ctype == 0:
                r = g = b = s[x] * scale
                a = 255
            elif ctype == 4:
                r = g = b = s[x * 2]
                a = s[x * 2 + 1]
            elif ctype == 2:
                r, g, b = s[x * 3:x * 3 + 3]
                a = 255
            else:
                r, g, b, a = s[x * 4:x * 4 + 4]
            out[o:o + 4] = bytes((r, g, b, a))
            o += 4
    return Image(w, h, bytes(out))


def _decode_with_pillow(data: bytes, source: str) -> Image:
    try:
        import io
        from PIL import Image as PILImage
    except ImportError:
        raise FormatError(f"{source}: interlaced PNG; save it without interlacing, or "
                          f"install Pillow (pip install pillow)") from None
    try:
        im = PILImage.open(io.BytesIO(data))
        im.load()
    except Exception as e:  # noqa: BLE001 - Pillow raises many types
        raise FormatError(f"{source}: {e}") from None
    if im.mode == "P" or im.mode.startswith("I") or im.mode == "F":
        im = im.convert("RGBA")
    im = im.convert("RGBA")
    return Image(im.width, im.height, im.tobytes())


def read(path: str | Path) -> Image:
    p = Path(path)
    return decode(p.read_bytes(), str(p))

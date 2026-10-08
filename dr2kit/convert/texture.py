"""Textures ⇄ images: `.bct` → PNG to look at or edit, PNG → `.bct` to put back.

This is the layer modders meet: it hides tiling, byte order, block compression and mip
levels. It joins `dr2kit.formats.bct` (where each level sits, tiling) and
`dr2kit.convert.dxt` (blocks ⇄ pixels).

Export (`to_image`): untile one level (or all six cube faces), swap to little-endian,
decode to RGBA. Cube maps become a horizontal strip of six faces in D3D order
(+X, −X, +Y, −Y, +Z, −Z).

Import (`replace_image`): same size and format as the original (v1 rule, see
docs/ARCHITECTURE.md §Textures). Level 0 is encoded with the original blocks as a
*reference*, so unchanged blocks keep their exact bytes. If level 0 comes out identical
to the original, the original mip levels are kept too: importing an unedited export
gives back the shipped file byte for byte (the phase 2 gate). Otherwise the mips are
rebuilt from the new image (2×2 box filter) and encoded the same way.
"""

from __future__ import annotations

from ..errors import FormatError
from ..formats.bct import Bct, Level, swap_to_big, swap_to_little
from . import dxt
from .png import Image

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

# Block formats this module can encode (all the block formats the games use).
_BLOCK = {"DXT1", "DXT5", "DXN"}


def decode_level(bct: Bct, lv: Level) -> bytes:
    """RGBA bytes (``lv.width * lv.height * 4``) of one level of one face."""
    fmt = bct.format
    rows = swap_to_little(bct.untile(lv), fmt)
    if fmt.name in _BLOCK:
        return dxt.decode(fmt.name, rows, lv.width, lv.height)
    if fmt.name == "A8R8G8B8":
        # After the 32-bit swap each texel is a little-endian ARGB word: bytes B, G, R, A.
        if np is not None:
            a = np.frombuffer(rows, np.uint8).reshape(-1, 4)[:, [2, 1, 0, 3]]
            return a.tobytes()
        out = bytearray(len(rows))
        out[0::4], out[1::4], out[2::4], out[3::4] = rows[2::4], rows[1::4], rows[0::4], rows[3::4]
        return bytes(out)
    if fmt.name == "L8":
        if np is not None:
            v = np.frombuffer(rows, np.uint8)
            return np.stack([v, v, v, np.full_like(v, 255)], -1).tobytes()
        return b"".join(bytes((v, v, v, 255)) for v in rows)
    raise FormatError(f"{bct.source}: no decoder for {fmt.name}")


def encode_level(bct: Bct, lv: Level, rgba: bytes, keep_unchanged: bool = True) -> bytes:
    """Rows of stored (big-endian) units for one level, from RGBA bytes."""
    fmt = bct.format
    ref = swap_to_little(bct.untile(lv), fmt) if keep_unchanged else None
    if fmt.name in _BLOCK:
        rows = dxt.encode(fmt.name, rgba, lv.width, lv.height, reference=ref)
    elif fmt.name == "A8R8G8B8":
        out = bytearray(len(rgba))
        out[0::4], out[1::4], out[2::4], out[3::4] = rgba[2::4], rgba[1::4], rgba[0::4], rgba[3::4]
        rows = bytes(out)
    elif fmt.name == "L8":
        rows = bytes(rgba[0::4])
    else:
        raise FormatError(f"{bct.source}: no encoder for {fmt.name}")
    return swap_to_big(rows, fmt)


def to_image(bct: Bct, level: int = 0) -> Image:
    """One mip level as an `Image`; a cube map's six faces side by side."""
    faces = [lv for lv in bct.levels() if lv.level == level]
    if not faces:
        raise FormatError(f"{bct.source}: no level {level} (it has {bct.header.levels})")
    w, h = faces[0].width, faces[0].height
    if len(faces) == 1:
        return Image(w, h, decode_level(bct, faces[0]))
    return Image(w * len(faces), h, _side_by_side([decode_level(bct, f) for f in faces], w, h))


def _side_by_side(parts: list[bytes], w: int, h: int) -> bytes:
    row = w * 4
    return b"".join(p[y * row:(y + 1) * row] for y in range(h) for p in parts)


def _split(img: Image, n: int) -> list[bytes]:
    w = img.width // n
    row = w * 4
    full = img.width * 4
    return [b"".join(img.rgba[y * full + i * row:y * full + (i + 1) * row]
                     for y in range(img.height)) for i in range(n)]


def downsample(rgba: bytes, w: int, h: int, nw: int, nh: int) -> bytes:
    """Box-filter an image to ``nw``×``nh`` (each output pixel averages its 2×2 parent)."""
    if np is not None:
        a = np.frombuffer(rgba, np.uint8).reshape(h, w, 4).astype(np.uint32)
        ys = np.minimum(np.arange(nh) * 2, h - 1)
        xs = np.minimum(np.arange(nw) * 2, w - 1)
        ys1 = np.minimum(ys + 1, h - 1)
        xs1 = np.minimum(xs + 1, w - 1)
        s = a[ys][:, xs] + a[ys][:, xs1] + a[ys1][:, xs] + a[ys1][:, xs1]
        return ((s + 2) // 4).astype(np.uint8).tobytes()
    out = bytearray(nw * nh * 4)
    for y in range(nh):
        for x in range(nw):
            for c in range(4):
                tot = 0
                for dy in (0, 1):
                    for dx in (0, 1):
                        sy, sx = min(2 * y + dy, h - 1), min(2 * x + dx, w - 1)
                        tot += rgba[(sy * w + sx) * 4 + c]
                out[(y * nw + x) * 4 + c] = (tot + 2) // 4
    return bytes(out)


def replace_image(bct: Bct, img: Image) -> Bct:
    """A copy of ``bct`` whose texels come from ``img`` (same size; v1 rule).

    Raises `FormatError` if the size does not match. See the module docstring for how
    unchanged blocks and mip levels are kept.
    """
    faces = bct.header.faces
    w0, h0 = bct.header.width, bct.header.height
    if (img.width, img.height) != (w0 * faces, h0):
        want = f"{w0 * faces}x{h0}" + (" (six cube faces side by side)" if faces > 1 else "")
        raise FormatError(f"{bct.source}: the image is {img.width}x{img.height}; this "
                          f"texture needs exactly {want}. Resizing comes in a later version.")
    out = Bct(bct.header, bytearray(bct.payload), bct.source)
    face_pixels = _split(img, faces) if faces > 1 else [img.rgba]
    levels = bct.levels()
    unchanged = all(decode_level(bct, lv) == face_pixels[lv.face]
                    for lv in levels if lv.level == 0)
    if unchanged:
        return out
    current = {f: face_pixels[f] for f in range(faces)}
    sizes = {f: (w0, h0) for f in range(faces)}
    for lv in levels:   # level order: 0 (all faces), 1 (all faces), ...
        pw, ph = sizes[lv.face]
        if (lv.width, lv.height) != (pw, ph):
            current[lv.face] = downsample(current[lv.face], pw, ph, lv.width, lv.height)
            sizes[lv.face] = (lv.width, lv.height)
        out.set_level(lv, encode_level(bct, lv, current[lv.face]))
    return out


def has_alpha(img: Image) -> bool:
    """True if any pixel is not fully opaque."""
    if np is not None:
        return bool((np.frombuffer(img.rgba, np.uint8)[3::4] != 255).any())
    return any(a != 255 for a in img.rgba[3::4])


def png_mode(bct: Bct, img: Image) -> str:
    """The PNG colour mode that loses nothing for this texture: L, RGB or RGBA."""
    if bct.format.name == "L8":
        return "L"
    return "RGBA" if has_alpha(img) else "RGB"

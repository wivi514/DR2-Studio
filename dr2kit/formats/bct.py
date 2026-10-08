"""`.bct` textures: the 48-byte header, the mip/face layout, and Xenos tiling.

Every texture of both games is a `.bct`: loose ones (``grid.bct``), ones named ``*.bct``
inside archives, and the extension-less entries of ``.tex`` packs. This module reads the
header, works out where each mip level (and each cube face) sits in the payload, and
moves texels between the GPU's **tiled** order and plain rows (untile / tile). Turning
blocks into pixels (DXT decode, PNG) is `dr2kit.convert.texture`'s job.

Key facts (docs/formats.md, "Textures: `.tex` and `.bct`"; all measured over every
texture of Case Zero and Case West, 12,224 + 23,126, by ``dr2 census``):

* The header is **48 bytes, big-endian**, and is *not* a GPU fetch constant: it is the
  engine's own compact description (format code, mip count, bits per pixel, flags).
  The payload follows at 0x30 and the file ends exactly where the header says.
* **Format codes** (header byte 8) are the engine's own, not Xenos ``k_*`` numbers:
  ``0x08`` DXT1, ``0x0A`` DXT5, ``0x1B`` DXN (normal maps), ``0x00`` A8R8G8B8,
  ``0x21`` 8-bit single channel. Byte 11 is the bits per pixel and always agrees.
* Every texture is **tiled** (``Tiled2DOffset``, the XDK's ``XGAddress2DTiledOffset``),
  with the row pitch rounded up to 32 units (a unit is a texel, or a 4×4 block for DXT).
* **Mip levels** follow the base level, each starting on a 4 KB boundary. Level *L* ≥ 1
  is sized from the next power of two of the base size, shifted right by *L*.
* **Packed mips**: once a level's shorter side is ≤ 16 texels, it and all smaller levels
  share one 32×32-unit tile, each at a fixed offset inside it. For a small texture this
  includes level 0 (a 16×8 texture's base sits at block row 4, not 0). The offset rule
  is Xenia's ``GetPackedMipOffset``, as transcribed and verified against hardware bytes by
  the CZ recomp (``runtime/gpu/vk_renderer.cpp``, ``PackedLevelOffset``), and verified
  here against where the non-zero blocks of real textures actually sit.
* **Cube maps** (flag bit 0x08, header word 0x24 = 5 = faces - 1): each level holds its six
  faces one after the other, each face a whole 4 KB-aligned tile region.

Origin: ``Tiled2DOffset`` and the packed-mip rule come from the CZ recomp's
``tools/tex_decode.py`` and ``runtime/gpu/vk_renderer.cpp`` (same author); the header
layout was decoded for this toolkit in phase 2.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, replace

from ..errors import FormatError

try:  # numpy is optional (Blender bundles it; plain installs may not have it)
    import numpy as _np
except ImportError:  # pragma: no cover - exercised by the no-numpy CI job
    _np = None

MAGIC = b"\x05\x01\x01"        # bytes 0-2; byte 3 is the flags byte (formats.md retraction)
HEADER_SIZE = 0x30
PAGE = 4096                    # every level / face region starts on a 4 KB boundary
TILE = 32                      # tiles are 32×32 units; pitch and height round up to this
PACKED_MAX = 16                # levels whose shorter side is <= 16 texels are packed

# Header byte 3. 0x02 is set on every texture of both games; the rest are listed in
# formats.md with their counts. Only CUBE is understood (size and word 0x24 agree).
FLAG_ALWAYS = 0x02
FLAG_ALPHA = 0x04      # hypothesis: set on every DXT5 and on DXT1s with 1-bit alpha
FLAG_CUBE = 0x08       # verified: exactly the textures with six faces (word 0x24 == 5)

# Byte 9: 0x23 on every CZ texture, 0x24 on all but 4 CW ones. A writer version, probably.
KNOWN_VERSIONS = (0x23, 0x24)


@dataclass(frozen=True)
class TextureFormat:
    """One texture format: how texels are grouped and stored.

    ``block`` is 4 for the DXT family (a unit is a 4×4 block) and 1 for plain formats
    (a unit is one texel). ``unit_bytes`` is the size of one unit. ``endian`` says how
    the GPU swaps bytes on load: ``"8in16"`` swaps each 16-bit word (DXT payloads are
    big-endian 16-bit words), ``"8in32"`` reverses each 32-bit word, ``"none"`` keeps them.
    """
    code: int
    name: str
    block: int
    unit_bytes: int
    endian: str
    channels: str          # what the decoded image holds, for people ("RGB", "RGBA", ...)

    @property
    def bpp(self) -> int:
        """Bits per pixel, as header byte 11 stores it."""
        return self.unit_bytes * 8 // (self.block * self.block)

    @property
    def log2_unit(self) -> int:
        return self.unit_bytes.bit_length() - 1


# The engine's format codes (header byte 8). Counts per game: formats.md.
FORMATS: dict[int, TextureFormat] = {f.code: f for f in (
    TextureFormat(0x08, "DXT1", 4, 8, "8in16", "RGB(A1)"),
    TextureFormat(0x0A, "DXT5", 4, 16, "8in16", "RGBA"),
    TextureFormat(0x1B, "DXN", 4, 16, "8in16", "RG (normal XY)"),
    TextureFormat(0x00, "A8R8G8B8", 1, 4, "8in32", "RGBA"),
    TextureFormat(0x21, "L8", 1, 1, "none", "L"),
)}

_HEADER = struct.Struct(">3sB HH BBBB I I I I I I I I I")


@dataclass
class BctHeader:
    """The 48-byte header, every field kept so the writer reproduces it exactly.

    Fields whose meaning is unknown are named after their offset and preserved.
    """
    flags: int                 # byte 3 (FLAG_*)
    width: int
    height: int
    format_code: int           # byte 8 (FORMATS)
    version: int               # byte 9: 0x23 (CZ) / 0x24 (CW)
    levels: int                # byte 10: mip levels stored, base included
    bpp: int                   # byte 11: bits per pixel
    word_0c: int               # differs per texture, low 5 bits always 0; meaning unknown
    word_10: int = 0x18        # 0x18 in every texture; meaning unknown
    word_14: int = 0
    data_offset: int = HEADER_SIZE   # word 0x18: always 0x30
    data_size: int = 0               # word 0x1C: payload length
    data_end: int = 0                # word 0x20: data_offset + data_size = file length
    depth_minus_1: int = 0           # word 0x24: 5 on cube maps, else 0
    word_28: int = 0
    word_2c: int = 0

    @classmethod
    def parse(cls, data: bytes, source: str = "<memory>") -> "BctHeader":
        if len(data) < HEADER_SIZE:
            raise FormatError(f"{source}: {len(data)} bytes, shorter than a .bct header")
        (magic, flags, w, h, fmt, ver, levels, bpp, w0c, w10, w14, doff, dsize, dend,
         depth, w28, w2c) = _HEADER.unpack_from(data)
        if magic != MAGIC:
            raise FormatError(f"{source}: magic {data[:3].hex(' ')}, not 05 01 01")
        return cls(flags, w, h, fmt, ver, levels, bpp, w0c, w10, w14, doff, dsize, dend,
                   depth, w28, w2c)

    def to_bytes(self) -> bytes:
        return _HEADER.pack(MAGIC, self.flags, self.width, self.height, self.format_code,
                            self.version, self.levels, self.bpp, self.word_0c, self.word_10,
                            self.word_14, self.data_offset, self.data_size, self.data_end,
                            self.depth_minus_1, self.word_28, self.word_2c)

    @property
    def format(self) -> TextureFormat | None:
        """The `TextureFormat`, or None for a code nobody has identified."""
        return FORMATS.get(self.format_code)

    @property
    def is_cube(self) -> bool:
        return bool(self.flags & FLAG_CUBE)

    @property
    def faces(self) -> int:
        return 6 if self.is_cube else 1


@dataclass(frozen=True)
class Level:
    """Where one mip level of one face sits in the payload.

    ``width``/``height`` are the image size in texels; ``units_w``/``units_h`` the same in
    units (blocks for DXT). ``offset`` is the byte offset of the level's tile region inside
    the payload, ``pitch`` its row pitch in units, and ``tile_x``/``tile_y`` the unit
    offset of the level inside that region (non-zero only for packed levels).
    """
    level: int
    face: int
    width: int
    height: int
    units_w: int
    units_h: int
    offset: int
    pitch: int
    tile_x: int
    tile_y: int
    packed: bool

    @property
    def linear_size(self) -> int:
        """Bytes of this level once untiled (rows of units, no padding)."""
        return self.units_w * self.units_h


# ---- the tiling math -------------------------------------------------------------------

def tiled_offset(x: int, y: int, pitch: int, log2_unit: int) -> int:
    """Unit index of unit (x, y) in a tiled surface ``pitch`` units wide.

    The XDK's ``XGAddress2DTiledOffset``, as the CZ recomp transcribed it
    (``Tiled2DOffset``). ``log2_unit`` is log2 of the unit size in bytes. Multiply the
    result by the unit size to get a byte offset.
    """
    macro = ((x >> 5) + (y >> 5) * (pitch >> 5)) << (log2_unit + 7)
    micro = ((x & 7) + ((y & 6) << 2)) << log2_unit
    off = (macro + ((micro & ~15) << 1) + (micro & 15)
           + ((y & 8) << (3 + log2_unit)) + ((y & 1) << 4))
    return ((((off & ~511) << 3) + ((off & 448) << 2) + (off & 63)
             + ((y & 16) << 7) + (((((y & 8) >> 2) + (x >> 3)) & 3) << 6)) >> log2_unit)


def _tiled_offsets_np(xs, ys, pitch: int, log2_unit: int):
    """`tiled_offset` over numpy arrays (same formula, elementwise)."""
    macro = ((xs >> 5) + (ys >> 5) * (pitch >> 5)) << (log2_unit + 7)
    micro = ((xs & 7) + ((ys & 6) << 2)) << log2_unit
    off = (macro + ((micro & ~15) << 1) + (micro & 15)
           + ((ys & 8) << (3 + log2_unit)) + ((ys & 1) << 4))
    return ((((off & ~511) << 3) + ((off & 448) << 2) + (off & 63)
             + ((ys & 16) << 7) + (((((ys & 8) >> 2) + (xs >> 3)) & 3) << 6)) >> log2_unit)


def _log2ceil(v: int) -> int:
    return max(0, (v - 1).bit_length())


def _align(n: int, a: int) -> int:
    return (n + a - 1) // a * a


def packed_level_offset(width: int, height: int, level: int) -> tuple[int, int] | None:
    """Texel offset of a packed mip level inside the shared tile, or None if not packed.

    Wider-than-tall textures stack the packed levels downwards (offsets in y), others
    across (offsets in x): 16, 8, 4 texels for the first three packed levels, then the
    long side's size shifted down. Xenia's ``GetPackedMipOffset`` (BSD-3-Clause), via the
    CZ recomp; verified on real textures (formats.md).
    """
    log2w, log2h = _log2ceil(width), _log2ceil(height)
    log2size = min(log2w, log2h)
    if log2size > 4 + level:
        return None
    packed_base = log2size - 4 if log2size > 4 else 0
    packed_mip = level - packed_base
    x = y = 0
    if packed_mip < 3:
        if log2w > log2h:
            y = 16 >> packed_mip
        else:
            x = 16 >> packed_mip
    else:
        off = (1 << (max(log2w, log2h) - packed_base)) >> (packed_mip - 2)
        if log2w > log2h:
            x = off
        else:
            y = off
    return x, y


def level_size(header: BctHeader, level: int) -> tuple[int, int]:
    """The image size of mip ``level`` in texels (never below 1)."""
    return max(1, header.width >> level), max(1, header.height >> level)


def _storage_size(header: BctHeader, level: int) -> tuple[int, int]:
    """Size used for the level's *storage*: level 0 as is, later levels from the next
    power of two of the base (Xenia's ``GetGuestTextureLayout`` rule)."""
    if level == 0:
        return header.width, header.height
    return (max(1, (1 << _log2ceil(header.width)) >> level),
            max(1, (1 << _log2ceil(header.height)) >> level))


def layout(header: BctHeader) -> list[Level]:
    """Every (level, face) of the texture and where it sits in the payload.

    Order: level 0 faces 0..5, level 1 faces 0..5, and so on (one face for a 2D texture).
    Raises `FormatError` for an unknown format code.
    """
    fmt = header.format
    if fmt is None:
        raise FormatError(f"unknown texture format code {header.format_code:#04x}")
    b = fmt.block
    out = []
    pos = 0
    tail_offset = None          # where the packed tile of each face starts, once reached
    for lv in range(header.levels):
        w, h = level_size(header, lv)
        sw, sh = _storage_size(header, lv)
        uw, uh = (w + b - 1) // b, (h + b - 1) // b
        suw, suh = (sw + b - 1) // b, (sh + b - 1) // b
        packed = packed_level_offset(header.width, header.height, lv)
        if packed is None:
            pitch = _align(suw, TILE)
            stride = _align(pitch * _align(suh, TILE) * fmt.unit_bytes, PAGE)
            for face in range(header.faces):
                out.append(Level(lv, face, w, h, uw, uh, pos + face * stride, pitch,
                                 0, 0, False))
            pos += stride * header.faces
            continue
        # The packed tail: one tile per face, holding this level and all smaller ones.
        if tail_offset is None:
            tail_offset = pos
            pitch = _align(suw, TILE)
            tail_stride = _align(pitch * _align(suh, TILE) * fmt.unit_bytes, PAGE)
            tail_pitch = pitch
        px, py = packed
        for face in range(header.faces):
            out.append(Level(lv, face, w, h, uw, uh, tail_offset + face * tail_stride,
                             tail_pitch, px // b, py // b, True))
    return out


def required_size(header: BctHeader, levels: list[Level] | None = None) -> int:
    """The smallest payload that holds every unit of every level (bytes)."""
    fmt = header.format
    levels = layout(header) if levels is None else levels
    end = 0
    for lv in levels:
        offs = _unit_offsets(lv, fmt)
        if len(offs):
            end = max(end, int(max(offs)) + fmt.unit_bytes)
    return end


def _region_stride(header: BctHeader, lv: Level) -> int:
    """Bytes from the start of ``lv``'s region to the next region (whole tiles, 4 KB)."""
    fmt = header.format
    if lv.packed:
        rows = TILE
    else:
        sh = _storage_size(header, lv.level)[1]
        rows = _align((sh + fmt.block - 1) // fmt.block, TILE)
    return _align(lv.pitch * rows * fmt.unit_bytes, PAGE)


def model_data_size(header: BctHeader) -> int:
    """The payload size this module's layout model predicts (``data_size``).

    Every region is its whole 4 KB-aligned tile footprint, except the last region of a 2D
    texture, which is cut to the 4 KB page holding its last used unit. Matches 99.6% of
    the textures of both games; the rest (odd sizes such as 40x40, tall narrow textures)
    carry more padding than predicted, never less (formats.md). Informational: readers
    rely on `required_size`, not on this.
    """
    levels = layout(header)
    last = levels[-1]
    if header.is_cube:
        return last.offset + _region_stride(header, last)
    region = [lv for lv in levels if lv.offset == last.offset]
    return last.offset + _align(required_size(header, region) - last.offset, PAGE)


# ---- the texture ----------------------------------------------------------------------

@dataclass
class Bct:
    """A parsed texture: header plus payload (still tiled, still big-endian).

    `untile` gives one level's units as plain rows; `set_level` writes rows back.
    `to_bytes` writes the file; unedited it gives back the original bytes.
    """
    header: BctHeader
    payload: bytearray
    source: str = "<memory>"

    @classmethod
    def parse(cls, data: bytes, source: str = "<memory>") -> "Bct":
        """Parse a texture, checking every size before trusting it.

        Raises `FormatError` naming ``source`` and the failed check: unknown format,
        sizes that don't add up, or a payload too small for its own layout.
        """
        hdr = BctHeader.parse(data, source)
        if hdr.data_offset != HEADER_SIZE:
            raise FormatError(f"{source}: data offset {hdr.data_offset:#x}, expected 0x30")
        if hdr.data_end != hdr.data_offset + hdr.data_size or hdr.data_end != len(data):
            raise FormatError(f"{source}: header says data {hdr.data_offset:#x}+"
                              f"{hdr.data_size:#x} ends at {hdr.data_end:#x}, file is "
                              f"{len(data):#x} bytes")
        fmt = hdr.format
        if fmt is None:
            raise FormatError(f"{source}: unknown texture format code {hdr.format_code:#04x}")
        if hdr.bpp != fmt.bpp:
            raise FormatError(f"{source}: {fmt.name} is {fmt.bpp} bits per pixel, header "
                              f"says {hdr.bpp}")
        if not 1 <= hdr.levels <= 13 or not hdr.width or not hdr.height:
            raise FormatError(f"{source}: {hdr.width}x{hdr.height} with {hdr.levels} levels")
        if hdr.depth_minus_1 != (5 if hdr.is_cube else 0):
            raise FormatError(f"{source}: depth word {hdr.depth_minus_1} does not match "
                              f"the cube flag ({hdr.is_cube})")
        need = required_size(hdr)
        if need > hdr.data_size:
            raise FormatError(f"{source}: layout needs {need:#x} bytes, payload is "
                              f"{hdr.data_size:#x}")
        return cls(hdr, bytearray(data[HEADER_SIZE:]), source)

    def to_bytes(self) -> bytes:
        self.header.data_size = len(self.payload)
        self.header.data_end = HEADER_SIZE + len(self.payload)
        return self.header.to_bytes() + bytes(self.payload)

    @property
    def format(self) -> TextureFormat:
        return self.header.format

    def levels(self) -> list[Level]:
        return layout(self.header)

    def level(self, level: int = 0, face: int = 0) -> Level:
        for lv in self.levels():
            if lv.level == level and lv.face == face:
                return lv
        raise IndexError(f"{self.source}: no level {level} face {face}")

    def untile(self, lv: Level) -> bytes:
        """The units of one level as rows (``units_w`` per row), in stored byte order."""
        return untile(self.payload, lv, self.format)

    def set_level(self, lv: Level, rows: bytes) -> None:
        """Write a level's units (rows, stored byte order) back into the tiled payload."""
        tile(self.payload, lv, self.format, rows)


def _unit_offsets(lv: Level, fmt: TextureFormat):
    """Byte offsets in the payload of every unit of ``lv``, row by row."""
    if _np is not None:
        ys, xs = _np.mgrid[0:lv.units_h, 0:lv.units_w].astype(_np.int64)
        offs = _tiled_offsets_np(xs + lv.tile_x, ys + lv.tile_y, lv.pitch, fmt.log2_unit)
        return (offs * fmt.unit_bytes + lv.offset).ravel()
    return [lv.offset + tiled_offset(lv.tile_x + x, lv.tile_y + y, lv.pitch,
                                     fmt.log2_unit) * fmt.unit_bytes
            for y in range(lv.units_h) for x in range(lv.units_w)]


def untile(payload: bytes, lv: Level, fmt: TextureFormat) -> bytes:
    """Gather one level's units from tiled order into rows. Bytes are not swapped."""
    n = fmt.unit_bytes
    offs = _unit_offsets(lv, fmt)
    if _np is not None:
        if len(offs) and int(offs.max()) + n > len(payload):
            raise FormatError(f"level {lv.level} reads past the payload")
        src = _np.frombuffer(bytes(payload), dtype=_np.uint8)
        idx = offs[:, None] + _np.arange(n)
        return src[idx].tobytes()
    out = bytearray(len(offs) * n)
    mv = memoryview(payload)
    for i, o in enumerate(offs):
        if o + n > len(payload):
            raise FormatError(f"level {lv.level} reads past the payload")
        out[i * n:(i + 1) * n] = mv[o:o + n]
    return bytes(out)


def tile(payload: bytearray, lv: Level, fmt: TextureFormat, rows: bytes) -> None:
    """Scatter one level's rows of units into the tiled payload (in place)."""
    n = fmt.unit_bytes
    if len(rows) != lv.units_w * lv.units_h * n:
        raise ValueError(f"level {lv.level}: got {len(rows)} bytes, expected "
                         f"{lv.units_w * lv.units_h * n}")
    offs = _unit_offsets(lv, fmt)
    if _np is not None:
        if len(offs) and int(offs.max()) + n > len(payload):
            raise FormatError(f"level {lv.level} writes past the payload")
        dst = _np.frombuffer(payload, dtype=_np.uint8)   # a view: writes go to payload
        idx = offs[:, None] + _np.arange(n)
        dst[idx] = _np.frombuffer(rows, dtype=_np.uint8).reshape(-1, n)
        return
    for i, o in enumerate(offs):
        payload[o:o + n] = rows[i * n:(i + 1) * n]


def swap_to_little(rows: bytes, fmt: TextureFormat) -> bytes:
    """Undo the format's big-endian storage, so standard decoders can read the units."""
    if fmt.endian == "none":
        return rows
    if _np is not None:
        dt = ">u2" if fmt.endian == "8in16" else ">u4"
        return _np.frombuffer(rows, dtype=dt).astype(dt[1:].replace("u", "<u")).tobytes()
    b = bytearray(rows)
    if fmt.endian == "8in16":
        b[0::2], b[1::2] = rows[1::2], rows[0::2]
    else:
        b[0::4], b[1::4], b[2::4], b[3::4] = rows[3::4], rows[2::4], rows[1::4], rows[0::4]
    return bytes(b)


swap_to_big = swap_to_little    # the swap is its own inverse


def is_bct(data: bytes) -> bool:
    """True if ``data`` starts like a texture (05 01 01)."""
    return data[:3] == MAGIC


__all__ = ["Bct", "BctHeader", "Level", "TextureFormat", "FORMATS", "layout",
           "required_size", "model_data_size", "tiled_offset", "packed_level_offset",
           "untile", "tile", "swap_to_little", "swap_to_big", "is_bct", "FLAG_CUBE",
           "FLAG_ALPHA", "HEADER_SIZE"]

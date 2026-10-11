"""Vertex declarations and vertex streams: the Xbox 360 D3D formats the games use.

A mesh's vertices are raw GPU streams. What each byte means is written in the mesh's
**vertex declaration** (`D3DVertexDesc N` in the model's ``persistent.big``): a list of
12-byte ``D3DVERTEXELEMENT9`` records, exactly as the Xbox 360 D3D runtime takes them::

    u16 stream | u16 offset | u32 type | u8 method | u8 usage | u8 usage_index | u8 pad
    ... terminated by stream 0xFF, type 0xFFFFFFFF (D3DDECL_END)

Key facts (docs/formats.md §"Vertex declarations"; counts from ``dr2 census --models``):

* The ``type`` is the 360's own ``D3DDECLTYPE`` value, not the PC one. Its low 6 bits
  are the Xenos vertex fetch format (0x39 = 32_32_32_FLOAT, 0x06 = 8_8_8_8,
  0x10 = 10_11_11, 0x07 = 2_10_10_10, 0x19 = 16_16 …); bit 8 = signed, bit 9 = integer
  (not normalised). `TYPES` lists the ones the games use; anything else is reported by
  the census instead of being guessed.
* **Byte order.** Streams are big-endian. Every element is read as big-endian 32-bit
  words, and component *x* sits in the **low** bits of its word (so for 8_8_8_8, x is the
  last byte in memory). This is how the CZ recomp's renderer fetches vertices, and it
  draws both games correctly; the 8_8_8_8 rule was also measured on skinning weights
  (they sum to 255 only this way round). **16-bit pairs are the exception:** x is the
  **high** half, the first 16 bits in memory (phase 10). The Xbox's vertex fetch hands
  a shader a 16-bit pair transposed, and the game's shaders swap it back with a ``yx``
  destination swizzle, so the value the game uses has x first (the CZ recomp's
  ``vk_renderer.cpp``, g_SwappedTexcoords). Only ``SHORT2N`` occurs (level lightmap
  UVs); read the other way, every lightmap landed transposed (docs/formats.md
  §Vertex declarations, retraction).
* Packed normals are ``HEND3N`` (10_11_11 signed normalised: x = bits 0-10, y = 11-21,
  z = 22-31); tangents are ``DEC4N`` (2_10_10_10: x, y, z 10 bits each, w 2 bits = the
  bitangent sign).
* **Skinning** (``BLENDWEIGHT`` + ``BLENDINDICES``, both 8_8_8_8): weight component *k*
  goes with index component *k* (x with x … w with w), read from the game's own
  vertex shader (``ProtoSkinnedClothRGB``, translated with XenosRecomp). An index is a
  **row** of the bone palette, i.e. 3 × the palette slot, because each bone is a 3×4
  matrix (three shader constants). See `dr2kit.formats.scene` for how a palette slot
  becomes a skeleton node.

Decoding is pure Python and returns plain lists, so it also runs in Blender's Python.
Encoding (`encode_element`, `encode_value`, phase 4) is the exact inverse: decode then
encode gives back the stored bytes of every element of both games (census).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from ..errors import FormatError

ELEMENT_SIZE = 12
END_STREAM = 0xFF

# D3DDECLUSAGE (same numbers on PC and 360).
USAGE_NAMES = {
    0: "POSITION", 1: "BLENDWEIGHT", 2: "BLENDINDICES", 3: "NORMAL", 4: "PSIZE",
    5: "TEXCOORD", 6: "TANGENT", 7: "BINORMAL", 8: "TESSFACTOR", 9: "POSITIONT",
    10: "COLOR", 11: "FOG", 12: "DEPTH", 13: "SAMPLE",
}
POSITION, BLENDWEIGHT, BLENDINDICES, NORMAL, TEXCOORD, TANGENT, COLOR = 0, 1, 2, 3, 5, 6, 10


@dataclass(frozen=True)
class VertexType:
    """One 360 ``D3DDECLTYPE``: its name, byte size, component count and decoder kind."""
    name: str
    size: int
    components: int
    kind: str          # see `_decode_one`


# 360 D3DDECLTYPE values (xbox d3d9types.h). Only types that occur in the games (census)
# are listed; each one's decoding is checked by the census (unit normals, weight sums,
# finite floats). An unknown type is a FormatError, never a guess (rule 6).
TYPES: dict[int, VertexType] = {
    0x2C83A4: VertexType("FLOAT1", 4, 1, "f32"),
    0x2C23A5: VertexType("FLOAT2", 8, 2, "f32"),
    0x2A23B9: VertexType("FLOAT3", 12, 3, "f32"),
    0x1A23A6: VertexType("FLOAT4", 16, 4, "f32"),
    0x1A2086: VertexType("UBYTE4N", 4, 4, "u8n"),
    0x1A2286: VertexType("UBYTE4", 4, 4, "u8"),
    0x1A2186: VertexType("BYTE4N", 4, 4, "s8n"),
    0x182886: VertexType("D3DCOLOR", 4, 4, "color"),
    0x2C2159: VertexType("SHORT2N", 4, 2, "s16n"),
    0x1A215A: VertexType("SHORT4N", 8, 4, "s16n"),
    0x2C2359: VertexType("SHORT2", 4, 2, "s16"),
    0x2C2059: VertexType("USHORT2N", 4, 2, "u16n"),
    0x2C235F: VertexType("FLOAT16_2", 4, 2, "f16"),
    0x1A2360: VertexType("FLOAT16_4", 8, 4, "f16"),
    0x1A2187: VertexType("DEC4N", 4, 4, "dec4n"),
    0x2A2187: VertexType("DEC3N", 4, 3, "dec4n"),
    0x2A2190: VertexType("HEND3N", 4, 3, "hend3n"),
}


@dataclass(frozen=True)
class VertexElement:
    """One ``D3DVERTEXELEMENT9`` record, every field kept."""
    stream: int
    offset: int
    type: int
    method: int
    usage: int
    usage_index: int
    pad: int = 0

    @property
    def vtype(self) -> VertexType | None:
        return TYPES.get(self.type)

    @property
    def usage_name(self) -> str:
        return f"{USAGE_NAMES.get(self.usage, f'USAGE{self.usage}')}{self.usage_index}"

    def describe(self) -> str:
        t = self.vtype
        tn = t.name if t else f"type 0x{self.type:06X}"
        return f"s{self.stream}+{self.offset} {self.usage_name} {tn}"


def parse_declaration(data: bytes, source: str = "<memory>") -> list[VertexElement]:
    """Parse a ``D3DVertexDesc`` chunk into its elements (the END record is dropped).

    Raises `FormatError` if the chunk is not a whole number of records, has no END
    record, or carries bytes after it.
    """
    if len(data) % ELEMENT_SIZE:
        raise FormatError(f"{source}: vertex declaration is {len(data)} bytes, "
                          f"not a multiple of {ELEMENT_SIZE}")
    out = []
    for off in range(0, len(data), ELEMENT_SIZE):
        s, o, t, m, u, ui, pad = struct.unpack_from(">HHIBBBB", data, off)
        if s == END_STREAM:
            if t != 0xFFFFFFFF or off + ELEMENT_SIZE != len(data):
                raise FormatError(f"{source}: malformed end of vertex declaration at +{off}")
            return out
        out.append(VertexElement(s, o, t, m, u, ui, pad))
    raise FormatError(f"{source}: vertex declaration has no END record")


def declaration_bytes(elements: list[VertexElement]) -> bytes:
    """The chunk bytes for a list of elements (the inverse of `parse_declaration`)."""
    out = b"".join(struct.pack(">HHIBBBB", e.stream, e.offset, e.type, e.method, e.usage,
                               e.usage_index, e.pad) for e in elements)
    return out + struct.pack(">HHIBBBB", END_STREAM, 0, 0xFFFFFFFF, 0, 0, 0, 0)


# --- decoding ---------------------------------------------------------------------------

def _s(v: int, bits: int) -> int:
    """Two's complement of a ``bits``-wide field."""
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def _snorm(v: int, bits: int) -> float:
    """Signed normalised: q / (2^(bits-1) - 1), **not** clamped.

    The lowest code, -2^(bits-1), decodes to slightly below -1 (-1.002 for 10 bits). The
    GPU clamps it to -1, but the games store -1.0 that way on most fields (and the
    2-bit tangent w never), so clamping here would make two codes decode to the same
    value and the encoder could not give the stored bits back (census, phase 4)."""
    return _s(v, bits) / ((1 << (bits - 1)) - 1)


def _f16(h: int) -> float:
    return struct.unpack("<e", struct.pack("<H", h))[0]


def _decode_one(kind: str, comps: int, raw: bytes, off: int) -> tuple:
    """Decode one element at ``raw[off:]`` into a tuple of numbers."""
    if kind == "f32":
        return struct.unpack_from(f">{comps}f", raw, off)
    if kind in ("u8n", "u8", "s8n", "color"):
        w = struct.unpack_from(">I", raw, off)[0]
        b = (w & 0xFF, (w >> 8) & 0xFF, (w >> 16) & 0xFF, w >> 24)   # x = low byte
        if kind == "u8":
            return b
        if kind == "u8n":
            return tuple(x / 255.0 for x in b)
        if kind == "s8n":
            return tuple(_snorm(x, 8) for x in b)
        # D3DCOLOR: the word is 0xAARRGGBB; give (r, g, b, a)
        return (b[2] / 255.0, b[1] / 255.0, b[0] / 255.0, b[3] / 255.0)
    if kind in ("s16n", "s16", "u16n", "f16"):
        words = struct.unpack_from(f">{(comps + 1) // 2}I", raw, off)
        h = []
        for w in words:
            h += [w >> 16, w & 0xFFFF]                    # x = HIGH half (module docstring)
        h = h[:comps]
        if kind == "s16n":
            return tuple(_snorm(x, 16) for x in h)
        if kind == "s16":
            return tuple(_s(x, 16) for x in h)
        if kind == "u16n":
            return tuple(x / 65535.0 for x in h)
        return tuple(_f16(x) for x in h)
    if kind == "dec4n":
        w = struct.unpack_from(">I", raw, off)[0]
        v = (_snorm(w & 0x3FF, 10), _snorm((w >> 10) & 0x3FF, 10),
             _snorm((w >> 20) & 0x3FF, 10), _snorm(w >> 30, 2))
        return v[:comps]
    if kind == "hend3n":
        w = struct.unpack_from(">I", raw, off)[0]
        return (_snorm(w & 0x7FF, 11), _snorm((w >> 11) & 0x7FF, 11), _snorm(w >> 22, 10))
    raise FormatError(f"no decoder for vertex kind {kind!r}")


def decode_element(el: VertexElement, data: bytes, stride: int, first: int, count: int,
                   source: str = "<memory>") -> list[tuple]:
    """Decode one element for vertices ``first … first+count-1`` of a stream.

    ``data`` is the whole stream, ``stride`` its bytes per vertex. Raises `FormatError`
    for an unknown type or when the vertices run past the end of the stream.
    """
    t = el.vtype
    if t is None:
        raise FormatError(f"{source}: unknown vertex type 0x{el.type:06X} ({el.usage_name})")
    if el.offset + t.size > stride:
        raise FormatError(f"{source}: element {el.describe()} does not fit a "
                          f"{stride}-byte vertex")
    end = (first + count - 1) * stride + el.offset + t.size if count else 0
    if count and (first < 0 or end > len(data)):
        raise FormatError(f"{source}: vertices {first}..{first + count - 1} run past the "
                          f"stream ({len(data)} bytes, stride {stride})")
    base = first * stride + el.offset
    return [_decode_one(t.kind, t.components, data, base + i * stride) for i in range(count)]


# --- encoding (phase 4) -----------------------------------------------------------------
#
# Each encoder is the exact inverse of `_decode_one`: decode → encode gives back the
# stored bytes for every element of every draw of both games (``dr2 census --models``,
# check "vertex re-encode"). Values out of range are clamped, never wrapped.

def _q_snorm(v: float, bits: int) -> int:
    """A float → a ``bits``-wide two's complement field: round(v × m), m = 2^(bits-1) - 1,
    clamped to [-m - 1, m]. The inverse of `_snorm` (which does not clamp either)."""
    m = (1 << (bits - 1)) - 1
    q = max(-m - 1, min(m, int(round(float(v) * m))))
    return q & ((1 << bits) - 1)


def _q_unorm(v: float, bits: int) -> int:
    m = (1 << bits) - 1
    return int(round(max(0.0, min(1.0, float(v))) * m))


def _q_int(v: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(float(v)))))


def _encode_one(kind: str, comps: int, vals) -> bytes:
    """Encode one element (a sequence of ``comps`` numbers) to its bytes."""
    v = list(vals)[:comps]
    if len(v) < comps:
        raise FormatError(f"{kind}: {len(v)} values for {comps} components")
    if kind == "f32":
        return struct.pack(f">{comps}f", *v)
    if kind in ("u8n", "u8", "s8n", "color"):
        if kind == "u8":
            b = [_q_int(x, 0, 255) for x in v]
        elif kind == "u8n":
            b = [_q_unorm(x, 8) for x in v]
        elif kind == "s8n":
            b = [_q_snorm(x, 8) for x in v]
        else:   # (r, g, b, a) → 0xAARRGGBB
            r, g, bl, a = (_q_unorm(x, 8) for x in v)
            b = [bl, g, r, a]
        return struct.pack(">I", b[0] | b[1] << 8 | b[2] << 16 | b[3] << 24)
    if kind in ("s16n", "s16", "u16n", "f16"):
        if kind == "s16n":
            h = [_q_snorm(x, 16) for x in v]
        elif kind == "s16":
            h = [_q_int(x, -32768, 32767) & 0xFFFF for x in v]
        elif kind == "u16n":
            h = [_q_unorm(x, 16) for x in v]
        else:
            h = [struct.unpack("<H", struct.pack("<e", float(x)))[0] for x in v]
        h += [0] * (len(h) % 2)
        return struct.pack(f">{len(h) // 2}I",
                           *(h[i] << 16 | h[i + 1] for i in range(0, len(h), 2)))
    if kind == "dec4n":
        w = v[3] if comps > 3 else 0.0
        return struct.pack(">I", _q_snorm(v[0], 10) | _q_snorm(v[1], 10) << 10
                           | _q_snorm(v[2], 10) << 20 | _q_snorm(w, 2) << 30)
    if kind == "hend3n":
        return struct.pack(">I", _q_snorm(v[0], 11) | _q_snorm(v[1], 11) << 11
                           | _q_snorm(v[2], 10) << 22)
    raise FormatError(f"no encoder for vertex kind {kind!r}")


def encode_value(el: VertexElement, value) -> bytes:
    """The bytes of one element for one vertex (inverse of `decode_element`)."""
    t = el.vtype
    if t is None:
        raise FormatError(f"unknown vertex type 0x{el.type:06X} ({el.usage_name})")
    return _encode_one(t.kind, t.components, value)


def encode_element(el: VertexElement, values: list, out: bytearray, stride: int,
                   first: int = 0) -> None:
    """Write one element for vertices ``first …`` into the stream ``out`` (in place).

    ``out`` must already be long enough (``(first + len(values)) * stride`` bytes).
    """
    t = el.vtype
    if t is None:
        raise FormatError(f"unknown vertex type 0x{el.type:06X} ({el.usage_name})")
    if el.offset + t.size > stride:
        raise FormatError(f"element {el.describe()} does not fit a {stride}-byte vertex")
    if (first + len(values)) * stride > len(out):
        raise FormatError(f"element {el.describe()}: {len(values)} vertices from {first} "
                          f"run past the stream ({len(out)} bytes)")
    base = first * stride + el.offset
    for i, v in enumerate(values):
        o = base + i * stride
        out[o:o + t.size] = _encode_one(t.kind, t.components, v)

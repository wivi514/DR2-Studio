"""Shared test helpers.

Two kinds of tests (docs/dev/testing.md):

* **Unit tests** build tiny synthetic archives in code. They run everywhere, CI included.
  Never put real game files (or anything extracted from them) in tests: the data is
  copyrighted (CLAUDE.md).
* **Game-data tests** (marker ``gamedata``) read a real install found through the game
  profiles, and **skip with a message saying why** when the game isn't there.
"""

from __future__ import annotations

import pytest

from dr2kit.container.big import BigArchive, BigEntry, LZX, STORED
from dr2kit.errors import GameNotFoundError


@pytest.fixture(autouse=True)
def _isolated_user_folders(tmp_path_factory, monkeypatch):
    """Every test gets its own config, cache and data folders (`dr2kit.userdirs`), so
    no test reads or writes the developer's real config, index or mod library."""
    from dr2kit import userdirs
    base = tmp_path_factory.mktemp("userdirs")
    monkeypatch.setattr(userdirs, "_dir", lambda kind: base / kind)
    monkeypatch.setenv("DR2_STUDIO_NO_DIALOGS", "1")     # Studio: errors go to the log
    monkeypatch.setenv("DR2_STUDIO_NO_SETUP", "1")       # Studio: no welcome window
    monkeypatch.setenv("DR2_STUDIO_NO_LAYOUT", "1")      # Studio: the default window layout


def make_archive(*entries, alignment: int = 4) -> BigArchive:
    """Build an archive from ``(name, data)`` or ``(name, data, compression)`` tuples,
    every entry declared ``alignment`` (its ``flags``, where the writer puts it)."""
    arc = BigArchive(source="<test>")
    for spec in entries:
        name, data, *rest = spec
        arc.add(name, data, compression=rest[0] if rest else STORED, flags=alignment,
                alignment=alignment)
    return arc


def make_bct(fmt_name: str = "DXT1", width: int = 64, height: int = 64, levels: int = 1,
             cube: bool = False, fill=None) -> bytes:
    """A synthetic `.bct` texture: header built field by field, payload sized by the
    layout model and filled by ``fill(i) -> byte`` (default: a repeating pattern)."""
    from dr2kit.formats.bct import FORMATS, FLAG_ALWAYS, FLAG_CUBE, BctHeader, model_data_size
    fmt = next(f for f in FORMATS.values() if f.name == fmt_name)
    hdr = BctHeader(flags=0xE0 | FLAG_ALWAYS | (FLAG_CUBE if cube else 0), width=width,
                    height=height, format_code=fmt.code, version=0x23, levels=levels,
                    bpp=fmt.bpp, word_0c=0x12345660, depth_minus_1=5 if cube else 0)
    size = model_data_size(hdr)
    hdr.data_size, hdr.data_end = size, 0x30 + size
    fill = fill or (lambda i: (i * 37 + 11) & 0xFF)
    return hdr.to_bytes() + bytes(fill(i) for i in range(size))


# --- synthetic scenes (docs/formats.md §Scene container), packed by hand ----------------

def node_record(index, parent, t=(0.0, 0.0, 0.0), q=(0.0, 0.0, 0.0, 1.0), s=(1.0, 1.0, 1.0),
                flag=1) -> bytes:
    import struct
    return struct.pack(">IiI3f3f4f", index, parent, flag, *s, *t, *q)


def buffer_record(name: str, count: int, stride: int) -> bytes:
    import struct
    return name.encode().ljust(0x24, b"\0") + struct.pack(">iIIII", -1, count, stride, 0, 0)


def decl_bytes(*elements) -> bytes:
    """``(stream, offset, type, usage, usage_index)`` tuples + the END record."""
    import struct
    out = b"".join(struct.pack(">HHIBBBB", s, o, t, 0, u, ui, 0) for s, o, t, u, ui in elements)
    return out + struct.pack(">HHIBBBB", 0xFF, 0, 0xFFFFFFFF, 0, 0, 0, 0)


def u8x4(x, y, z, w) -> bytes:
    """An 8_8_8_8 element: component x in the low byte of a big-endian word."""
    import struct
    return struct.pack(">I", x | y << 8 | z << 16 | w << 24)


def hend3n(x, y, z) -> bytes:
    """10_11_11 signed normalised: x bits 0-10, y 11-21, z 22-31."""
    import struct
    def f(v, bits):
        return round(v * ((1 << (bits - 1)) - 1)) & ((1 << bits) - 1)
    return struct.pack(">I", f(x, 11) | f(y, 11) << 11 | f(z, 10) << 22)


SKIN_DECL = [(0, 0, 0x2A23B9, 0, 0), (0, 12, 0x2C23A5, 5, 0), (0, 20, 0x1A2086, 1, 0),
             (0, 24, 0x1A2286, 2, 0), (0, 28, 0x1A2187, 6, 0), (0, 32, 0x2A2190, 3, 0)]


def make_scene(*, combined: bool = False) -> bytes:
    """A tiny model: 3 bones, one material, one shape drawn as a 4-index strip (2
    triangles).

    ``combined=False``: a skinned character-style shape with its own buffers.
    ``combined=True``: a static prop-style shape with two draws reading shared
    ``Combined Vertices 12/8`` + ``Combined Indices 2`` buffers and sharing one
    declaration (the 0x0A word picks it).
    """
    import math
    import struct
    names = ["dummy01", "dummy01.spine", "dummy01.l_arm"]
    h = math.sqrt(0.5)
    recs = [node_record(0, -1), node_record(1, 0, t=(0.0, 1.0, 0.0)),
            node_record(2, 1, t=(0.5, 0.0, 0.0), q=(0.0, 0.0, h, h))]
    quad = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0)]
    shape = "geo_boxShape"
    entries = [(n, r) for n, r in zip(names, recs)]
    entries.append(("_BONEHIERARCHY_", b"".join(struct.pack(">Ii", i, p)
                                                for i, p in [(0, -1), (1, 0), (2, 1)])))
    pers = []
    if not combined:
        vb = b""
        slots = [(0, 0, 0, 0), (1, 0, 0, 0), (1, 2, 0, 0), (2, 0, 0, 0)]
        weights = [(255, 0, 0, 0), (255, 0, 0, 0), (128, 127, 0, 0), (255, 0, 0, 0)]
        for (x, y, z), (s0, s1, s2, s3), wt in zip(quad, slots, weights):
            vb += struct.pack(">3f2f", x, y, z, x, 1 - y)
            vb += u8x4(*wt) + u8x4(s0 * 3, s1 * 3, s2 * 3, s3 * 3)
            vb += struct.pack(">I", 511 | 1 << 30)              # tangent (1, 0, 0, w 1)
            vb += hend3n(0.0, 0.0, 1.0)
        entries += [(f"{shape} Vertices 0", vb),
                    (f"{shape} Indices 0", struct.pack(">4H", 0, 1, 2, 3))]
        pers += [(f"{shape} D3DVertexDesc 0", decl_bytes(*SKIN_DECL)),
                 # word 5 = packet byte offset, word 6 = packet words up to the draw's end
                 (f"{shape} RenderStrip", struct.pack(">7I", 0, 0x3F, 0, 0, 3, 0, 13)),
                 (f"{shape} CommandBuffer", struct.pack(">13I", 0x0D, 0x0001013C, 0x5CEF4D20,
                                                        0x0A, 0x0B, 0x0C, 0x408, 0, 0, 4, 0, 4, 1)
                  + struct.pack(">3I", 0x71, 0x3F, 0x5CEF4D20) + struct.pack(">I", 0xFFFFF604)),
                 (f"{shape} VBHeader", buffer_record(f"{shape} 0", 4, 36)),
                 (f"{shape} VDHeader", struct.pack(">Ii", 0, -1)),
                 (f"{shape} IBHeader", buffer_record(f"{shape} 0", 4, 2))]
        words = (4, 0, 1, 1, 1, 1, 0, 3)
        shaders = "0x5CEF4D20 : ProtoSkinnedClothRGB\r\n"
    else:
        # two copies of the quad, the second shifted up by 2: one per draw
        pos = b"".join(struct.pack(">3f", x, y + 2 * k, z) for k in range(2) for x, y, z in quad)
        uv = b"".join(struct.pack(">2f", x, y) for _ in range(2) for x, y, _z in quad)
        entries += [("Combined Vertices 12", pos), ("Combined Vertices 8", uv),
                    ("Combined Indices 2", struct.pack(">8H", 0, 1, 2, 3, 0, 1, 2, 3))]
        def packet(k):
            return struct.pack(">17I", 0x0001013C, 0xE9EA5720, 0x0A, 0x800C0028, 4 * k,
                               0x80080128, 4 * k, 0x00800247, 4 * k,
                               0x408, 0, 0, 4, 0, 4, 1, 0xFFFFF004)
        pers += [(f"{shape} D3DVertexDesc 0", decl_bytes((0, 0, 0x2A23B9, 0, 0),
                                                         (1, 0, 0x2C23A5, 5, 0))),
                 (f"{shape} RenderStrip", struct.pack(">7I", 0, 0x3F, 0, 0, 1, 0, 16)
                  + struct.pack(">7I", 0, 0x3F, 0, 0, 1, 68, 16)),
                 (f"{shape} CommandBuffer", packet(0) + packet(1)),
                 (f"{shape} VDHeader", struct.pack(">Ii", 0, -1)),
                 ("Combined_VBHeader", buffer_record("Combined Vertices 8", 8, 8)
                  + buffer_record("Combined Vertices 12", 8, 12)),
                 ("Combined_IBHeader", buffer_record("Combined Indices 2", 8, 2))]
        words = (0, 0, 0, 1, 0, 2, 0, 1)
        shaders = "0xE9EA5720 : LIT_CM\r\n"
    pers.append((shape, struct.pack(">8I", *words) + struct.pack(">7f", 1.5, 0, 0, 0, 1, 3, 0)
                 + bytes(12)))
    pers.append(("_BOUNDINGBOX_", struct.pack(">6f", 0, 0, 0, 1, 3, 0)))
    slot = lambda name: struct.pack(">I", 1) + name.encode().ljust(52, b"\0") + bytes(44)
    entries += [("UsedShaders.txt", shaders.encode()),
                ("MatArray", struct.pack(">4I4fI", 1, 0xE06D61E0, 2, 0, 909.1, 0.7, 0.5, 1.0,
                                         0x251350C0)),
                ("MatTextureInfoArray", slot("box_cm") + slot("gExposureTexture")),
                ("_BONENAMES_", b"".join(n.encode().ljust(31, b"\0") for n in names)),
                ("persistent.big", make_archive(*pers).to_bytes()),
                ("SceneDescription", b"".join(n.encode().ljust(32, b"\0") + struct.pack(">I", 2)
                                              for n in names)
                 + shape.encode().ljust(32, b"\0") + struct.pack(">I", 0)),
                ("SceneHeader", struct.pack(">5I", 1, 2, 2, 4, 1))]
    return make_archive(*entries).to_bytes()


@pytest.fixture
def game_root():
    """Return a function: ``game_root("cz")`` -> the data root, or skip saying why."""
    from dr2kit.profiles import locate

    def get(game: str):
        try:
            return locate(game).root
        except GameNotFoundError as e:
            pytest.skip(f"{game} game data not available: {e}")
    return get


__all__ = ["make_archive", "make_bct", "make_scene", "node_record", "BigArchive", "BigEntry",
           "LZX", "STORED"]

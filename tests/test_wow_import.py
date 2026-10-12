"""tools/wow_import.py on a small synthetic WoW 3.3.5 model (no WoW data: phase 13 step
6.5 and 8): the .m2 / .skin reader, the .glb, and one emitter's DR2 fields."""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import wow_import as wi  # noqa: E402


def _m2() -> bytes:
    """A 2-triangle blade along +x (0 → 2), one texture, one particle emitter."""
    head = bytearray(0x130)
    body = bytearray()

    def put(data: bytes) -> int:
        at = len(head) + len(body)
        body.extend(data)
        while len(body) % 4:
            body.append(0)
        return at

    def arr(off: int, count: int, at: int) -> None:
        struct.pack_into("<II", head, off, count, at)

    head[:4] = b"MD20"
    struct.pack_into("<I", head, 4, 264)
    arr(0x08, 5, put(b"Test\0"))
    verts = b""
    for x, y in ((0, 0), (2, 0), (2, 0.2), (0, 0.2)):
        verts += struct.pack("<3f4B4B3f2f2f", x, y, 0, 255, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1,
                             x / 2, y, 0, 0)
    arr(0x3C, 4, put(verts))
    name = put(b"Item\\Weapon\\Glow.blp\0")
    arr(0x50, 1, put(struct.pack("<IIII", 0, 0, 20, name)))
    arr(0x80, 1, put(struct.pack("<H", 0)))

    def track(value: float) -> bytes:              # M2Track<float> with one key
        ts = put(struct.pack("<I", 0))
        vs = put(struct.pack("<f", value))
        tsa = put(struct.pack("<II", 1, ts))
        vsa = put(struct.pack("<II", 1, vs))
        return struct.pack("<HhIIII", 0, -1, 1, tsa, 1, vsa)

    def fblock(fmt: str, values) -> bytes:
        times = [0, 16384, 32767][:len(values)]
        t = put(struct.pack(f"<{len(times)}h", *times))
        v = put(b"".join(struct.pack(fmt, *x) for x in values))
        return struct.pack("<IIII", len(times), t, len(values), v)

    p = bytearray()
    p += struct.pack("<iI3fHH", -1, 0, 1.0, 0.0, 0.1, 0, 0)
    p += bytes(16)                                     # two model file names
    p += struct.pack("<BBHBBHHH", 4, 1, 0, 0, 0, 0, 1, 1)
    for v in (0.5, 0.0, 0.0, 6.28, 0.25, 2.0):         # speed … gravity, life
        p += track(v)
    p += struct.pack("<f", 0)
    p += track(5.0) + struct.pack("<f", 0)             # rate
    p += track(0.2) + track(0.1) + track(0.0)          # area length, width, z source
    p += fblock("<3f", [(255, 0, 0), (0, 255, 0), (0, 0, 255)])
    p += fblock("<h", [(0,), (32767,), (0,)])
    p += fblock("<2f", [(0.1, 0.1), (0.3, 0.3), (0.1, 0.1)])
    p += bytes(8 + 32)                                 # scale vary, head / tail cells
    p += struct.pack("<3f2f6f", 0.1, 10, 1, 1, 1, 1, 0.5, 0, 0, 0, 0)
    p += bytes(24 + 12 + 4 + 16 + 8) + track(1.0)[:0] + bytes(20)
    assert len(p) == wi.PARTICLE_SIZE, hex(len(p))
    arr(0x128, 1, put(bytes(p)))
    return bytes(head + body)


def _skin() -> bytes:
    head = bytearray(48)
    body = bytearray()

    def put(data: bytes) -> int:
        at = len(head) + len(body)
        body.extend(data)
        while len(body) % 4:
            body.append(0)
        return at
    head[:4] = b"SKIN"
    struct.pack_into("<II", head, 4, 4, put(struct.pack("<4H", 0, 1, 2, 3)))
    struct.pack_into("<II", head, 12, 6, put(struct.pack("<6H", 0, 1, 2, 0, 2, 3)))
    struct.pack_into("<II", head, 28, 1, put(struct.pack("<6H", 0, 0, 0, 4, 0, 6) + bytes(36)))
    struct.pack_into("<II", head, 36, 1, put(struct.pack("<BbHHHhHHHHHHH",
                                                         0, 0, 0, 0, 0, -1, 0, 0, 1, 0, 0, 0, 0)))
    return bytes(head + body)


def test_read_m2_and_skin():
    m2 = wi.read_m2(_m2())
    assert m2.name == "Test" and len(m2.vertices) == 4
    assert m2.textures == [(0, "Item\\Weapon\\Glow.blp")]
    (p,) = m2.particles
    assert p.texture == "Item\\Weapon\\Glow.blp" and p.blend == 4
    assert (p.speed, p.gravity, p.lifespan, p.rate) == (0.5, 0.25, 2.0, 5.0)
    assert (p.area_length, p.area_width) == pytest.approx((0.2, 0.1))
    assert p.alphas == pytest.approx([0, 1, 0]) and p.scales == pytest.approx([0.1, 0.3, 0.1])
    tris, subs, units = wi.read_skin(_skin())
    assert tris == [0, 1, 2, 0, 2, 3] and len(subs) == 1 and units == [(0, 0)]
    with pytest.raises(wi.WowError):
        wi.read_m2(b"MD21" + bytes(400))


def test_model_glb_without_texture(tmp_path):
    m2 = wi.read_m2(_m2())
    glb = wi.model_glb(m2, _skin(), wi.Source(tmp_path))  # no .blp next to it: no material
    n = struct.unpack_from("<I", glb, 12)[0]
    g = json.loads(glb[20:20 + n])
    assert len(g["meshes"]) == 1 and "materials" not in g
    pos = g["accessors"][g["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    assert pos["count"] == 4 and pos["max"][2] == pytest.approx(2.0)   # x → glTF z


def test_emitter_changes():
    m2 = wi.read_m2(_m2())
    axis, start, scale = wi.model_frame(m2, 1.0)
    assert (axis, start, scale) == (0, 0.0, 0.5)
    ch = wi.emitter_changes(m2.particles[0], axis, start, scale, "wow_glow")
    assert ch["texture"] == "wow_glow"
    assert ch["colour_times"] == pytest.approx([0.5, 1.0, 1.5, 2.0])
    assert ch["colours"][:4] == pytest.approx([1, 0, 0, 0])            # red, clear
    assert ch["colours"][8:12] == pytest.approx([0, 1, 0, 1], abs=1e-3)          # green at mid-life
    assert ch["sizes"][2] == pytest.approx(0.15, abs=1e-4)
    assert ch["offset"] == pytest.approx([0.0, 0.5, 0.05])             # 1 of 2 along → y
    assert ch["gravity"] == pytest.approx([0, -0.125, 0])              # WoW down → DR2 −y
    assert ch["count_20"] == 5                                          # its rate
    assert ch["shape_values"] == pytest.approx([0.05, 0.025, 0.025, -0.05, -0.025, -0.025])

"""Unit tests for dr2kit.formats.scene_write and the vertex encoders (synthetic data only)."""

import random
import struct

import pytest

from dr2kit.errors import FormatError
from dr2kit.formats import vertex as vx
from dr2kit.formats.scene import Scene, strip_to_triangles
from dr2kit.formats.scene_write import (DrawGeometry, SceneEditor, quantize_weights,
                                        rewrite_problems, split_by_palette,
                                        triangles_to_strip)

from conftest import make_scene


def _canon(t):
    i = t.index(min(t))
    return t[i:] + t[:i]


@pytest.mark.parametrize("type_,values", [
    (0x2A23B9, [(1.5, -2.25, 1e-3)]),                               # FLOAT3
    (0x1A2086, [(1.0, 0.0, 128 / 255, 127 / 255)]),                 # UBYTE4N
    (0x1A2286, [(0, 3, 6, 180)]),                                    # UBYTE4
    (0x2C2159, [(0.5, -1.0), (-32768 / 32767, 1.0)]),                # SHORT2N, both -1 codes
    (0x2A2190, [(-1024 / 1023, 0.0, 1.0), (0.25, -0.5, -512 / 511)]),  # HEND3N, lowest codes
    (0x1A2187, [(-512 / 511, 0.0, 1.0, -1.0), (0.1, 0.2, 0.3, 1.0)]),  # DEC4N
    (0x182886, [(1.0, 0.5, 0.0, 1.0)]),                              # D3DCOLOR
    (0x2C235F, [(0.5, -2.0)]),                                       # FLOAT16_2
])
def test_encode_is_the_inverse_of_decode(type_, values):
    el = vx.VertexElement(0, 0, type_, 0, 0, 0)
    size = el.vtype.size
    buf = bytearray(len(values) * size)
    vx.encode_element(el, values, buf, size)
    back = vx.decode_element(el, bytes(buf), size, 0, len(values))
    again = bytearray(len(buf))
    vx.encode_element(el, back, again, size)
    assert again == buf                                   # bits survive decode → encode
    for v, b in zip(values, back):
        assert all(abs(x - y) < 2e-3 for x, y in zip(v, b))


def test_lowest_snorm_code_is_kept():
    """The games store -1.0 as -2^(bits-1) on most fields; it must not become -m."""
    el = vx.VertexElement(0, 0, 0x1A2187, 0, 6, 0)        # DEC4N
    raw = struct.pack(">I", 0x200 | 0x200 << 10 | 0x200 << 20 | 3 << 30)
    v = vx.decode_element(el, raw, 4, 0, 1)[0]
    assert v[0] < -1.0 and v[3] == -1.0
    assert vx.encode_value(el, v) == raw


@pytest.mark.parametrize("combined", [False, True])
def test_rewrite_is_exact(combined):
    assert rewrite_problems(Scene.parse(make_scene(combined=combined))) == []


def test_strip_round_trip_keeps_every_triangle_and_its_winding():
    rnd = random.Random(4)
    for trial in range(40):
        n = rnd.randint(3, 30)
        tris = []
        for _ in range(rnd.randint(1, 60)):
            a, b, c = rnd.sample(range(n), 3)
            tris.append((a, b, c))
        strip = triangles_to_strip(tris)
        back, _ = strip_to_triangles(strip)
        assert sorted(map(_canon, back)) == sorted(map(_canon, tris)), trial


def test_strip_of_a_grid_is_compact():
    # a 4×4 quad grid, triangulated consistently: one strip run per row at most
    tris = []
    for y in range(4):
        for x in range(4):
            a, b, c, d = y * 5 + x, y * 5 + x + 1, (y + 1) * 5 + x, (y + 1) * 5 + x + 1
            tris += [(a, b, c), (c, b, d)]
    strip = triangles_to_strip(tris)
    assert len(strip) < 3 * len(tris)


def test_quantize_weights_sums_to_255():
    rnd = random.Random(1)
    for _ in range(200):
        ws = [rnd.random() for _ in range(rnd.randint(1, 4))]
        q = quantize_weights(ws)
        assert sum(q) == 255 and len(q) == 4 and all(0 <= x <= 255 for x in q)
    assert quantize_weights([1, 1, 1]) == [85, 85, 85, 0]
    with pytest.raises(FormatError):
        quantize_weights([0, 0])


def test_split_by_palette():
    # 3 triangles: nodes 0-2, nodes 50-60, nodes 100-102 → no 61-run holds all of them
    pos = [(float(i), 0.0, 0.0) for i in range(9)]
    joints = [(0,), (1,), (2,), (50,), (55,), (60,), (100,), (101,), (102,)]
    g = DrawGeometry(0, pos, [(0, 1, 2), (3, 4, 5), (6, 7, 8)], joints=joints,
                     weights=[(1.0,)] * 9)
    groups = split_by_palette(g)
    assert [(s, c) for _, s, c in groups] == [(0, 61), (100, 3)]
    wide = DrawGeometry(0, pos[:3], [(0, 1, 2)], joints=[(0,), (1,), (70,)],
                        weights=[(1.0,)] * 3)
    with pytest.raises(FormatError, match="no palette can hold it"):
        split_by_palette(wide)


def _geometry(sc, mesh):
    out = []
    for d in mesh.draws:
        dd = sc.draw_data(d, mesh.name)
        out.append((dd, DrawGeometry(d.material, dd.positions, dd.triangles, dd.normals,
                                     dd.uvs, dd.colors, dd.joints, dd.weights, dd.tangents)))
    return out


@pytest.mark.parametrize("combined", [False, True])
def test_replace_mesh_with_its_own_geometry_decodes_the_same(combined):
    sc = Scene.parse(make_scene(combined=combined))
    mesh = sc.meshes[0]
    parts = _geometry(sc, mesh)
    ed = SceneEditor(sc)
    ed.replace_mesh(mesh.name, [g for _, g in parts])
    sc2 = Scene.parse(ed.to_bytes())
    assert rewrite_problems(sc2) == []
    m2 = sc2.meshes[0]
    assert len(m2.draws) == len(parts)
    for d2, (dd, _) in zip(m2.draws, parts):
        dd2 = sc2.draw_data(d2, m2.name)
        assert sorted(dd2.positions) == sorted(dd.positions)
        key = lambda d, t: _canon(tuple(d.positions[v] for v in t))  # noqa: E731
        assert sorted(key(dd2, t) for t in dd2.triangles) == sorted(key(dd, t) for t in dd.triangles)
        if dd.weights:
            assert sorted(dd2.weights) == sorted(dd.weights)


def test_replace_mesh_new_geometry_bigger_and_moved():
    sc = Scene.parse(make_scene())
    mesh = sc.meshes[0]
    # a 3×3 grid of vertices weighted between the spine (1) and the arm (2)
    pos = [(x * 0.5, y * 0.5 + 3.0, 0.25) for y in range(3) for x in range(3)]
    tris = [(0, 1, 3), (3, 1, 4), (1, 2, 4), (4, 2, 5), (3, 4, 6), (6, 4, 7), (4, 5, 7),
            (7, 5, 8)]
    g = DrawGeometry(0, pos, tris, [(0.0, 0.0, 1.0)] * 9,
                     [[(p[0], p[1]) for p in pos]], None,
                     [(1, 2)] * 9, [(0.7, 0.3)] * 9)
    ed = SceneEditor(sc)
    assert ed.replace_mesh(mesh.name, [g]) == [(1, 2)]
    sc2 = Scene.parse(ed.to_bytes())
    m2 = sc2.meshes[0]
    d2 = m2.draws[0]
    dd = sc2.draw_data(d2, m2.name)
    assert len(dd.positions) == 9 and len(dd.triangles) == 8
    assert (d2.palette_start, d2.palette_count) == (1, 2)
    assert all(abs(sum(w) - 1.0) < 1e-9 for w in dd.weights)
    assert {j[:2] for j in dd.joints} == {(1, 2)}
    assert m2.bounds_max[1] == pytest.approx(4.0) and m2.bounds_min[1] == pytest.approx(3.0)
    assert m2.radius == pytest.approx((1.0 ** 2 + 4.0 ** 2 + 0.25 ** 2) ** 0.5, rel=1e-6)
    assert m2.words[5] == 1 and (m2.words[6], m2.words[7]) == (1, 2)


def test_rigid_shader_refuses_two_bones():
    sc = Scene.parse(make_scene(combined=True))
    mesh = sc.meshes[0]
    g = DrawGeometry(0, [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)], [(0, 1, 2)],
                     joints=[(0,), (1,), (1,)], weights=[(1.0,)] * 3)
    with pytest.raises(FormatError, match="rigid"):
        SceneEditor(sc).replace_mesh(mesh.name, [g])

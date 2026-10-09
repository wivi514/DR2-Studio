"""Unit tests for dr2kit.formats.scene and dr2kit.formats.vertex (synthetic scenes only)."""

import math
import struct

import pytest

from dr2kit.errors import FormatError
from dr2kit.formats import vertex as vx
from dr2kit.formats.scene import (Node, Scene, parse_command_buffer, strip_to_triangles)

from conftest import make_archive, make_scene, node_record


def test_node_record_round_trip():
    raw = node_record(7, 3, t=(1.0, 2.0, 3.0), q=(0.0, 0.0, 0.6, 0.8), flag=0)
    n = Node.parse("dummy01.x", raw)
    assert (n.index, n.parent, n.flag) == (7, 3, 0)
    assert n.translation == (1.0, 2.0, 3.0)
    assert n.to_bytes() == raw


def test_split_rig_root_points_at_itself():
    assert Node.parse("r", node_record(0, 0)).is_root
    assert Node.parse("r", node_record(0, -1)).is_root
    assert not Node.parse("c", node_record(1, 0)).is_root


def test_skeleton_world_positions():
    sc = Scene.parse(make_scene())
    pos = sc.skeleton.world_positions()
    assert pos[1] == pytest.approx((0.0, 1.0, 0.0))
    assert pos[2] == pytest.approx((0.5, 1.0, 0.0))      # parent's rotation applies to children only
    assert [n.name for n in sc.skeleton.nodes] == ["dummy01", "dummy01.spine", "dummy01.l_arm"]


def test_scene_header_materials_shaders():
    sc = Scene.parse(make_scene(), "t")
    assert sc.kind == "model" and sc.header[3] == len(sc.description) == 4
    assert sc.description[3] == ("geo_boxShape", 0)
    m = sc.materials[0]
    assert [s.name for s in m.slots] == ["box_cm", "gExposureTexture"]
    assert m.texture("colour") == "box_cm" and m.slots[1].engine
    assert sc.shaders == {0x5CEF4D20: "ProtoSkinnedClothRGB"}
    assert sorted(sc.unknown) == []


def test_own_buffers_skinned_draw():
    sc = Scene.parse(make_scene(), "t")
    (mesh,) = sc.meshes
    (d,) = mesh.draws
    assert d.skinned and (d.palette_start, d.palette_count) == (0, 3)
    assert d.streams[0].buffer == "geo_boxShape Vertices 0" and d.index_buffer == "geo_boxShape Indices 0"
    dd = sc.draw_data(d, mesh.name)
    assert dd.positions[3] == (1.0, 1.0, 0.0)
    assert dd.uvs[0][1] == (1.0, 1.0)
    assert dd.normals[0] == pytest.approx((0.0, 0.0, 1.0))
    assert dd.tangents[0] == pytest.approx((1.0, 0.0, 0.0, 1.0))
    # weight component k pairs with index component k; index = 3 * palette slot
    assert dd.joints[2][:2] == (1, 2)
    assert dd.weights[2][:2] == pytest.approx((128 / 255, 127 / 255))
    assert all(sum(w) == pytest.approx(1.0) for w in dd.weights)
    assert dd.triangles == [(0, 1, 2), (2, 1, 3)]


def test_combined_buffers_and_shared_declaration():
    sc = Scene.parse(make_scene(combined=True), "t")
    (mesh,) = sc.meshes
    assert len(mesh.draws) == 2
    d0, d1 = mesh.draws
    assert d0.declaration_number == d1.declaration_number == 0
    assert d1.streams[0].buffer == "Combined Vertices 12" and d1.streams[0].first == 4
    assert d1.streams[1].stride == 8 and d1.index_bind == 4
    assert not d0.skinned
    assert sc.draw_data(d1).positions[0] == (0.0, 2.0, 0.0)     # the second copy


def test_strip_to_triangles_drops_degenerates_and_keeps_winding():
    # the join pattern the games use: ... 2 2 3 3 3 ... (two strips, five degenerates)
    tris, dropped = strip_to_triangles([0, 1, 2, 2, 3, 3, 3, 4, 5])
    assert (tris, dropped) == ([(0, 1, 2), (3, 4, 5)], 5)
    # odd triangles swap their first two indices so every face keeps the same winding
    assert strip_to_triangles([0, 1, 2, 3]) == ([(0, 1, 2), (2, 1, 3)], 0)


def test_command_buffer_unknown_opcode_is_named():
    with pytest.raises(FormatError, match="unknown command 0x000000EE"):
        parse_command_buffer(struct.pack(">2I", 0x0A, 0xEE))
    cmds = parse_command_buffer(struct.pack(">4I", 0x0001013C, 0x12345678, 0x0A, 0xFFFFF604))
    assert [c.op for c in cmds] == [0x3C, 0x0A, 0x04] and cmds[0].args == (0x12345678,)


def test_declaration_parse_and_bytes():
    from conftest import SKIN_DECL, decl_bytes
    raw = decl_bytes(*SKIN_DECL)
    els = vx.parse_declaration(raw)
    assert [e.usage_name for e in els] == ["POSITION0", "TEXCOORD0", "BLENDWEIGHT0",
                                           "BLENDINDICES0", "TANGENT0", "NORMAL0"]
    assert vx.declaration_bytes(els) == raw
    with pytest.raises(FormatError, match="no END"):
        vx.parse_declaration(raw[:-12])


def test_vertex_decoders():
    from conftest import hend3n, u8x4
    el = lambda t: vx.VertexElement(0, 0, t, 0, 0, 0)
    assert vx.decode_element(el(0x1A2286), u8x4(1, 2, 3, 4), 4, 0, 1) == [(1, 2, 3, 4)]
    (n,) = vx.decode_element(el(0x2A2190), hend3n(0.6, -0.8, 0.0), 4, 0, 1)
    assert n == pytest.approx((0.6, -0.8, 0.0), abs=2e-3)
    # SHORT2N: x is the low half of the big-endian word
    (uv,) = vx.decode_element(el(0x2C2159), struct.pack(">hh", -32767, 16384), 4, 0, 1)
    assert uv == pytest.approx((16384 / 32767, -1.0))
    with pytest.raises(FormatError, match="unknown vertex type"):
        vx.decode_element(el(0x123456), bytes(4), 4, 0, 1)
    with pytest.raises(FormatError, match="run past"):
        vx.decode_element(el(0x2A23B9), bytes(12), 12, 0, 2)


def test_truncated_bone_names_resolve_by_prefix_and_index():
    # _BONENAMES_ keeps 30 characters; two records share that prefix
    long_a, long_b = "geo_body.geo_carrier_long_name", "geo_body.geo_carrier_long_name1"
    assert len(long_a) == 30
    arc = make_archive(
        ("root", node_record(0, -1)), (long_a, node_record(1, 0)), (long_b, node_record(2, 0)),
        ("_BONENAMES_", b"".join(n[:30].encode().ljust(31, b"\0")
                                 for n in ("root", long_a, long_b))),
        ("SceneHeader", struct.pack(">5I", 1, 2, 2, 3, 0)))
    sc = Scene.from_archive(arc, "t")
    assert [n.name for n in sc.skeleton.nodes] == ["root", long_a, long_b]
    assert sc.kind == "skeleton"


def test_not_a_scene():
    with pytest.raises(FormatError, match="no SceneHeader"):
        Scene.from_archive(make_archive(("a", b"x")), "t")


def test_world_matrix_inverse():
    from dr2kit.formats.scene import mat_inverse_affine, mat_mul, trs_matrix
    m = trs_matrix((1, 2, 3), (0, math.sqrt(0.5), 0, math.sqrt(0.5)), (2, 2, 2))
    i = mat_mul(m, mat_inverse_affine(m))
    for r in range(4):
        assert i[r] == pytest.approx([1.0 if c == r else 0.0 for c in range(4)], abs=1e-12)


@pytest.mark.parametrize("name, role", [
    ("zc_head_cm", "colour"), ("mech_eye_cm1", "colour"), ("glass_cmda77", "colour"),
    ("Metal_oldred_02_CM4c73", "colour"), ("boss_commander_epi_upper_dm", "colour"),
    ("common_nm", "normal"), ("z_eye_mask", "mask"), ("decal_letters_large_om1202", "opacity"),
    ("reflection_sharp", "other"), ("swatch_black", "other"), ("s400_BM-28", "other")])
def test_texture_roles(name, role):
    """Names measured over every material slot of both games (formats.md §Materials)."""
    from dr2kit.formats.scene import texture_role
    assert texture_role(name) == role


def test_colour_falls_back_to_a_plain_texture():
    from dr2kit.formats.scene import Material, TextureSlot
    slot = lambda n: TextureSlot(1, n, bytes(100))
    m = Material(1, 0, 3, 0, (0, 0, 0, 0), 0xFFFFFFFF,
                 [slot("LM_z01_wall"), slot("reflection_basic"), slot("Raw_flesh"),
                  slot("armcap_nm")])
    assert m.texture("colour") == "Raw_flesh"          # lightmaps / reflections skipped
    m.slots.insert(0, slot("x_dm"))
    assert m.texture("colour") == "x_dm"

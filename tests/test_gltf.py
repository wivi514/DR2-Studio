"""Unit tests for dr2kit.convert.gltf (synthetic scenes only)."""

import json
import struct

import pytest

from dr2kit.convert import gltf
from dr2kit.errors import FormatError
from dr2kit.formats.scene import Scene

from conftest import make_scene


def test_glb_container_round_trip():
    b = gltf.GlbBuilder()
    acc = b.accessor([(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)], "VEC3", minmax=True)
    data = b.to_bytes()
    assert data[:4] == b"glTF" and struct.unpack_from("<I", data, 8)[0] == len(data)
    g = gltf.Glb.parse(data)
    assert g.accessor(acc) == [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)]
    assert g.gltf["accessors"][acc]["min"] == [1.0, 2.0, 3.0]
    with pytest.raises(FormatError, match="not a .glb"):
        gltf.Glb.parse(b"nope" * 8)


def test_skeleton_glb_has_armature_skin_and_extras():
    sc = Scene.parse(make_scene())
    g = gltf.Glb.parse(gltf.skeleton_to_glb(sc))
    names = [n["name"] for n in g.gltf["nodes"]]
    assert names == ["dummy01", "dummy01.spine", "dummy01.l_arm"]
    assert g.gltf["nodes"][0]["children"] == [1] and g.gltf["scenes"][0]["nodes"] == [0]
    assert g.gltf["skins"][0]["joints"] == [0, 1, 2]
    ex = g.gltf["nodes"][2]["extras"]["dr2"]
    assert ex["index"] == 2 and ex["parent"] == 1
    assert bytes.fromhex(ex["record"]) == sc.skeleton.nodes[2].to_bytes()


def test_skeleton_from_glb_is_bit_exact_and_snaps_noise():
    sc = Scene.parse(make_scene())
    g = gltf.Glb.parse(gltf.skeleton_to_glb(sc))
    # Simulate Blender: float noise below the tolerance, plus a JSON-string property
    for node in g.gltf["nodes"]:
        node["translation"] = [c + 3e-7 for c in node.get("translation", [0, 0, 0])]
        node["extras"]["dr2"] = json.dumps(node["extras"]["dr2"])
    noisy = _rebuild(g)
    back = gltf.skeleton_from_glb(noisy)
    assert [n.to_bytes() for n in back] == [n.to_bytes() for n in sc.skeleton.nodes]


def test_skeleton_from_glb_keeps_real_edits():
    sc = Scene.parse(make_scene())
    g = gltf.Glb.parse(gltf.skeleton_to_glb(sc))
    g.gltf["nodes"][1]["translation"] = [0.0, 1.25, 0.0]       # the spine moved 25 cm
    back = gltf.skeleton_from_glb(_rebuild(g))
    assert back[1].translation == (0.0, 1.25, 0.0)
    assert back[2].to_bytes() == sc.skeleton.nodes[2].to_bytes()


def test_model_glb_meshes_skin_materials():
    sc = Scene.parse(make_scene(), "t")
    st = gltf.ExportStats()
    pngs = []
    data = gltf.model_to_glb(sc, lambda name: pngs.append(name) or _tiny_png(), stats=st)
    g = gltf.Glb.parse(data)
    assert (st.meshes, st.primitives, st.vertices, st.triangles) == (1, 1, 4, 2)
    assert pngs == ["box_cm"] and st.textures == 1 and st.missing_textures == []
    (mesh,) = g.gltf["meshes"]
    prim = mesh["primitives"][0]
    assert g.accessor(prim["indices"]) == [0, 1, 2, 2, 1, 3]
    assert g.accessor(prim["attributes"]["JOINTS_0"])[2][:2] == (1, 2)
    w = g.accessor(prim["attributes"]["WEIGHTS_0"])
    assert all(sum(r) == pytest.approx(1.0) for r in w)
    assert "TANGENT" not in prim["attributes"]
    assert prim["extras"]["dr2"]["shader_name"] == "ProtoSkinnedClothRGB"
    mesh_node = next(n for n in g.gltf["nodes"] if n.get("mesh") == 0)
    assert mesh_node["skin"] == 0
    mat = g.gltf["materials"][0]
    assert mat["name"] == "00_box_cm" and "baseColorTexture" in mat["pbrMetallicRoughness"]
    # inverse bind matrix of the arm: undoes its rest pose (0.5, 1, 0)
    ibm = g.accessor(g.gltf["skins"][0]["inverseBindMatrices"])[2]
    assert ibm[12:15] == pytest.approx((-1.0, 0.5, 0.0))    # rotated 90° about Z, then moved


def test_model_glb_without_textures_and_unskinned():
    sc = Scene.parse(make_scene(combined=True))
    g = gltf.Glb.parse(gltf.model_to_glb(sc))
    assert len(g.gltf["meshes"][0]["primitives"]) == 2
    assert "skins" not in g.gltf
    assert "images" not in g.gltf


def _rebuild(g: gltf.Glb) -> bytes:
    """Write a parsed glb back (after editing its JSON)."""
    b = gltf.GlbBuilder()
    b.gltf, b.bin = g.gltf, bytearray(g.bin)
    return b.to_bytes()


def _tiny_png() -> bytes:
    from dr2kit.convert import png
    return png.encode(png.Image(1, 1, b"\xff\x00\x00\xff"), "RGBA")


def test_texture_finder_reads_packs_next_to_a_loose_model(tmp_path):
    """Loose models (data/dynamicprops/special/x.big) keep their .tex pack as a file in
    the same folder; the finder looks there (the Case West commander/prop report)."""
    from conftest import make_archive, make_bct, make_scene
    from dr2kit.container.vpath import AssetTree
    from dr2kit.convert.model import TextureFinder
    folder = tmp_path / "data" / "dynamicprops"
    folder.mkdir(parents=True)
    (folder / "box.big").write_bytes(make_scene())
    (folder / "box.tex").write_bytes(make_archive(("box_cm", make_bct("DXT1", 8, 8))).to_bytes())
    f = TextureFinder(AssetTree(tmp_path), "data/dynamicprops/box.big")
    assert f("box_cm") is not None
    assert f.found["box_cm"] == "data/dynamicprops/box.tex/box_cm"

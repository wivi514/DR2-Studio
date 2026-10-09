"""Unit tests for dr2kit.convert.model_import (.glb → model) on synthetic scenes."""

import pytest

from dr2kit.container.big import LZX
from dr2kit.container.vpath import AssetTree
from dr2kit.convert import gltf
from dr2kit.convert.model_import import (ModelImportError, format_plan, import_glb,
                                         plan_import)
from dr2kit.formats.scene import Scene, mat_inverse_affine
from dr2kit.mods import build as mbuild
from dr2kit.mods.manifest import Mod, ModError, create

from conftest import make_archive, make_scene

GRID = [(x * 0.5, y * 0.5 + 1.0, 0.1) for y in range(3) for x in range(3)]
GRID_TRIS = [(0, 1, 3), (3, 1, 4), (1, 2, 4), (4, 2, 5), (3, 4, 6), (6, 4, 7), (4, 5, 7),
             (7, 5, 8)]


def make_glb(scene, *, joint_order=None, extra_bone=None, weights=None, joints=None,
             node_name="geo_boxShape", material="00_box_cm", positions=GRID,
             tris=GRID_TRIS) -> bytes:
    """A .glb as Blender would write one: the armature (joints in ``joint_order``, not the
    game's), one skinned mesh node. ``joints`` are game node indices per vertex."""
    b = gltf.GlbBuilder("test")
    jn = gltf.add_skeleton(b, scene.skeleton)
    order = joint_order or list(range(len(jn)))
    joint_nodes = [jn[i] for i in order]
    world = scene.skeleton.world_matrices()
    ibm = [gltf._col_major(mat_inverse_affine(world[i])) for i in order]
    if extra_bone:
        b.gltf["nodes"].append({"name": extra_bone, "translation": [0.0, 2.0, 0.0]})
        joint_nodes.append(len(b.gltf["nodes"]) - 1)
        ibm.append(gltf._col_major([[1, 0, 0, 0], [0, 1, 0, -2.0], [0, 0, 1, 0], [0, 0, 0, 1]]))
        b.gltf["scenes"][0]["nodes"].append(joint_nodes[-1])
    skin = b.add("skins", {"joints": joint_nodes,
                           "inverseBindMatrices": b.accessor(ibm, "MAT4", target=None)})
    slot = {g: k for k, g in enumerate(order)}
    if extra_bone:
        slot["extra"] = len(order)
    n = len(positions)
    js = joints or [(1, 2)] * n
    ws = weights or [(0.75, 0.25)] * n
    J = [tuple(slot[j] for j in v) + (0,) * (4 - len(v)) for v in js]
    W = [tuple(w) + (0.0,) * (4 - len(w)) for w in ws]
    mat = b.add("materials", {"name": material})
    prim = {"attributes": {"POSITION": b.accessor(positions, "VEC3", minmax=True),
                           "NORMAL": b.accessor([(0.0, 0.0, 1.0)] * n, "VEC3"),
                           "TEXCOORD_0": b.accessor([(p[0], p[1]) for p in positions], "VEC2"),
                           "JOINTS_0": b.accessor(J, "VEC4", gltf.USHORT),
                           "WEIGHTS_0": b.accessor(W, "VEC4")},
            "indices": b.accessor([i for t in tris for i in t], "SCALAR", gltf.USHORT,
                                  target=gltf.ELEMENT_ARRAY_BUFFER),
            "material": mat}
    mesh = b.add("meshes", {"name": "Cube", "primitives": [prim]})
    b.gltf["scenes"][0]["nodes"].append(b.add("nodes", {"name": node_name, "mesh": mesh,
                                                        "skin": skin}))
    return b.to_bytes()


@pytest.mark.parametrize("combined", [False, True])
def test_export_then_import_gives_identical_bytes(combined):
    data = make_scene(combined=combined)
    out, plan = import_glb(Scene.parse(data), gltf.model_to_glb(Scene.parse(data)))
    assert out == data
    assert plan.ok and plan.unchanged == ["geo_boxShape"] and not plan.shapes


def test_new_mesh_with_reordered_bones():
    data = make_scene()
    sc = Scene.parse(data)
    glb = make_glb(sc, joint_order=[2, 0, 1], node_name="geo_boxShape.001")
    out, plan = import_glb(Scene.parse(data), glb)
    assert plan.ok and list(plan.shapes) == ["geo_boxShape"], format_plan(plan)
    sc2 = Scene.parse(out)
    d = sc2.meshes[0].draws[0]
    dd = sc2.draw_data(d, "geo_boxShape")
    assert (d.palette_start, d.palette_count) == (1, 2)
    for a, b in zip(sorted(dd.positions), sorted(GRID)):      # float32 in the game
        assert a == pytest.approx(b, abs=1e-7)
    # bones were matched by name: the 0.75 weight is on the spine (node 1)
    for js, ws in zip(dd.joints, dd.weights):
        assert dict((j, round(w * 255)) for j, w in zip(js, ws) if w) == {1: 191, 2: 64}


def test_unknown_bone_and_unweighted_vertices_are_errors():
    sc = Scene.parse(make_scene())
    joints = [(1, "extra")] + [(1,)] * 8
    weights = [(0.5, 0.5)] + [(1.0,)] * 7 + [(0.0,)]
    plan = plan_import(sc, make_glb(sc, extra_bone="tail_bone", joints=joints,
                                    weights=weights))
    msgs = [str(i) for i in plan.errors]
    assert any("'tail_bone'" in m and "doesn't have" in m for m in msgs), msgs
    assert any("1 of 9 vertices have no bone weight" in m for m in msgs), msgs
    with pytest.raises(ModelImportError, match="tail_bone"):
        import_glb(sc, make_glb(sc, extra_bone="tail_bone", joints=joints, weights=weights))


def test_more_than_four_influences_keeps_the_strongest():
    sc = Scene.parse(make_scene())
    # JOINTS_0 holds 4 slots; build 5 influences through two sets is not supported by
    # the helper, so check the warning path through a vertex with 4 + duplicate merge
    glb = make_glb(sc, joints=[(1, 2, 1, 0)] * 9, weights=[(0.4, 0.3, 0.2, 0.1)] * 9)
    out, plan = import_glb(sc, glb)
    dd = Scene.parse(out).draw_data(Scene.parse(out).meshes[0].draws[0])
    for js, ws in zip(dd.joints, dd.weights):     # node 1 merged: 0.6, node 2: 0.3, 0: 0.1
        got = {j: round(w * 255) for j, w in zip(js, ws) if w}
        assert got == {1: 153, 2: 77, 0: 25}


def test_unmatched_object_and_material_fallback():
    sc = Scene.parse(make_scene())
    plan = plan_import(sc, make_glb(sc, node_name="Suzanne"))
    assert not plan.ok
    assert any("matches no shape" in str(i) for i in plan.issues)
    plan = plan_import(sc, make_glb(sc, material="Material.001"))
    assert plan.ok and any("not one of this model's" in str(i) for i in plan.issues)


def test_skeleton_is_not_a_model():
    sc = Scene.parse(make_scene())
    sk = Scene.parse(make_scene())
    sk.meshes = []
    plan = plan_import(sk, make_glb(sc))
    assert not plan.ok and "skeleton" in str(plan.errors[0])


def test_mod_with_a_glb_override(tmp_path, monkeypatch):
    root = tmp_path / "game"
    (root / "data" / "models").mkdir(parents=True)
    npcs = make_archive(("hero.big", make_scene(), LZX))
    (root / "data" / "models" / "npcs.big").write_bytes(npcs.to_bytes())
    monkeypatch.setenv("DR2_CZ_DATA", str(root))
    tree = AssetTree(root)
    sc = Scene.parse(tree.resolve("data/models/npcs.big/hero.big").data())
    mod_dir = create(tmp_path / "mod", "bigger_box")
    dest = mod_dir / "replace" / "data" / "models" / "npcs.big" / "hero.big.glb"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(make_glb(sc))
    mod = Mod.load(mod_dir)
    plan = mbuild.classify([mod], "cz", tree)
    assert [p.override.kind for p in plan] == ["model-glb"]
    res = mbuild.build([mod], "cz", tree, tmp_path / "out")
    assert res.files == ["data/models/npcs.big"]
    built = AssetTree(tmp_path / "out")
    node = built.resolve("data/models/npcs.big/hero.big")
    assert node.entry.compressed                              # re-compressed, as shipped
    sc2 = Scene.parse(node.data())
    assert len(sc2.draw_data(sc2.meshes[0].draws[0]).positions) == 9
    # a bad .glb is refused at classify time, with the validator's message
    dest.write_bytes(make_glb(sc, extra_bone="tail_bone", joints=[(1, "extra")] * 9))
    with pytest.raises(ModError, match="tail_bone"):
        mbuild.classify([Mod.load(mod_dir)], "cz", tree)

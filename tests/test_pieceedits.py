"""Building edits (phase 11 step 4): ``.pieces.json`` read and written, applied to a
zone's placement table, merged across mods, built into a mod set, and edited through the
Maps tab's editor (synthetic level, no game data)."""

import json
import math
import struct

import pytest

from dr2kit.container.vpath import AssetTree
from dr2kit.errors import Dr2Error, FormatError
from dr2kit.formats import level as lvl
from dr2kit.formats import pieceedits as pe
from dr2kit.mods import build
from dr2kit.mods.manifest import Mod, create
from dr2kit.mods.pieceedit import PieceEdits, pieces_path, read_organization

from test_level import make_level, organization, placement_record

ZV = "data/models/environment/town/town_z01.big"


def test_json_round_trip_and_errors():
    e = pe.Edits({"Box": {"hidden": True}, "shed": {"position": [1, 2, 3],
                                                    "rotation": [0, 0, 0, 1],
                                                    "scale": [2, 2, 2]}},
                 [{"piece": "box", "position": [4, 5, 6]}])
    text = pe.to_json(e, "town_z01")
    back = pe.from_json(text)
    assert back.pieces == e.pieces and back.copies == e.copies
    assert text.count("\n") == 10                  # one line per piece and copy
    for bad in ('{"format": "x"}', '{"format": "%s", "pieces": {"a": {"size": 1}}}' % pe.FORMAT,
                '{"format": "%s", "pieces": {"a": {"position": [1, 2]}}}' % pe.FORMAT,
                '{"format": "%s", "copies": [{"position": [1, 2, 3]}]}' % pe.FORMAT,
                '{"format": "%s", "pieces": {"a": {"rotation": [0, 0, 0, 0]}}}' % pe.FORMAT):
        with pytest.raises(FormatError):
            pe.from_json(bad)


def test_apply_moves_hides_and_copies():
    h = math.sqrt(0.5)
    org = lvl.ZoneOrganization.from_entries(_entries(organization(
        placement_record("box", 0, (0, 0, 0), lo=(-1, 0, -2), hi=(1, 1, 2)),
        placement_record("shed", 1, (10, 0, 0), lo=(9, -1, -1), hi=(11, 1, 1)))))
    e = pe.Edits({"BOX": {"position": [5, 0, 0], "rotation": [0, h, 0, h], "scale": [2, 2, 2]},
                  "shed": {"hidden": True}},
                 [{"piece": "box", "position": [0, 0, 20]}])
    out = pe.apply(org, e)
    box, shed, copy = out.placements
    assert box.position == (5, 0, 0) and box.scale == (2, 2, 2)
    # the 2 × 1 × 4 box, turned a quarter and doubled: 8 along x, 4 along z
    assert [round(c, 3) for c in box.bounds_min] == [1, 0, -2]
    assert [round(c, 3) for c in box.bounds_max] == [9, 2, 2]
    assert shed.position == (10, -pe.PARK_DROP, 0) and shed.bounds_min[1] == -1 - pe.PARK_DROP
    assert copy.piece == "box" and copy.index == 0 and copy.position == (0, 0, 20)
    assert copy.to_bytes()[:64] == org.placements[0].to_bytes()[:64]
    assert org.placements[0].position == (0, 0, 0)            # the original is untouched
    with pytest.raises(FormatError, match="ghost"):
        pe.apply(org, pe.Edits({"ghost": {"hidden": True}}))


def test_merge_by_piece():
    a = pe.Layer("a", 0, pe.Edits({"box": {"hidden": True}}, [{"piece": "box"}]))
    b = pe.Layer("b", 1, pe.Edits({"box": {"position": [1, 2, 3]}}, [{"piece": "shed"}]))
    m, shadowed, problems = pe.merge([b, a])
    assert m.pieces == {"box": {"position": [1, 2, 3]}} and len(m.copies) == 2
    assert shadowed == [("piece box", "a", "b")] and not problems
    _m, _s, problems = pe.merge([a, pe.Layer("c", 0, pe.Edits({"Box": {"hidden": True}}))])
    assert problems and "same priority" in problems[0]


def test_session_build_and_conflicts(tmp_path):
    root = tmp_path / "game"
    root.mkdir()
    tree = make_level(root, pieces=("box", "shed"))
    mod = create(tmp_path / "m", "m")
    z = PieceEdits.open(mod, tree, ZV)
    z.checkpoint()
    z.place("box", position=[1, 2, 3])
    z.checkpoint()
    z.hide("shed")
    z.checkpoint()
    name = z.copy("box", position=[9, 0, 9])
    assert name == "box#1" and z.count() == 3
    z.save()
    f = pieces_path(mod, ZV)
    assert f.name == "ZONE_ORGANIZATION.big.pieces.json" and f.is_file()
    z.place("box", position=z.shipped("box").position)       # back where the game has it
    assert "position" not in z.edits.pieces.get("box", {})
    assert z.undo() and z.edits.pieces["box"]["position"] == [1, 2, 3]
    with pytest.raises(Dr2Error):
        z.place("box", scale=[0, 1, 1])
    out = tmp_path / "out"
    res = build.build([Mod.load(mod)], "cz", tree, out)        # verify() runs inside
    assert any(p.override.kind == "pieces" for p in res.overrides)
    org = read_organization(AssetTree(out), ZV)
    assert [p.piece for p in org.placements] == ["box", "shed", "box"]
    assert org.placements[0].position == (1, 2, 3)
    assert org.placements[1].position == (5.0, -pe.PARK_DROP, 0.0)
    n, = struct.unpack(">I", AssetTree(out).resolve(ZV + "/ZONE_ORGANIZATION.big/"
                                                         "NumModelInstance").data())
    assert n == 3
    # a second mod replacing the zone's table as a whole can't be built with it
    other = create(tmp_path / "o", "o")
    raw = other / "replace" / ZV / "ZONE_ORGANIZATION.big" / "ModelInstanceArray"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(tree.resolve(ZV + "/ZONE_ORGANIZATION.big/ModelInstanceArray").data())
    with pytest.raises(Dr2Error, match="moves buildings"):
        build.plan_mods([Mod.load(mod), Mod.load(other)], "cz", tree)
    # a .pieces.json anywhere else is refused
    wrong = other / "replace" / ZV / "box.big.pieces.json"
    raw.unlink()
    wrong.write_text(f.read_text())
    with pytest.raises(Dr2Error, match="goes next to"):
        build.plan_mods([Mod.load(other)], "cz", tree)


def test_editor_undo_spans_buildings_and_items(tmp_path):
    from dr2kit.studio.maps_edit import LevelEditor
    from test_level import make_datafile
    root = tmp_path / "game"
    root.mkdir()
    make_datafile(root)
    tree = make_level(root, pieces=("box", "shed"))
    mod = create(tmp_path / "m", "m")
    ed = LevelEditor(AssetTree(root), mod)
    states = ed.piece_move(ZV, "box", position=[3, 0, 0], scale=[2, 2, 2])
    moved = [s for s in states if s.name == "box"]
    assert moved and moved[0].position == (3, 0, 0) and moved[0].scale == (2, 2, 2)
    assert states[-1].name == "" and states[-1].copy           # the end of the copies
    ed.move("town.txt", "HotDog3", (5, 2, 3))
    name, states = ed.piece_copy(ZV, "shed", position=[0, 0, 7])
    assert name == "shed#1" and any(s.name == "shed#1" for s in states)
    ed.piece_hide(ZV, "box")
    assert ed.zone(ZV).hidden("box") and ed.count() == 3       # box, the copy, the item
    ed.undo()                                                   # the hide
    assert not ed.zone(ZV).hidden("box")
    ed.undo()                                                   # the copy
    assert not ed.zone(ZV).edits.copies
    ed.undo()                                                   # the item
    ed.undo()                                                   # the move
    assert not pieces_path(mod, ZV).exists()
    states = ed.redo()
    assert any(s.name == "box" and s.position == (3, 0, 0) for s in states)
    assert json.loads(pieces_path(mod, ZV).read_text())["pieces"]["box"]["scale"] == [2, 2, 2]


def _entries(archive_bytes: bytes) -> dict:
    from dr2kit.container.big import BigArchive
    return {e.name: e.data() for e in BigArchive.parse(archive_bytes).entries}


def _mopp(origin, extent=1.0, code=b"\x01\x02\x03"):
    return struct.pack("<4fI", *origin, 2 ** 24 / extent, len(code)) + b"\0" + code


def _zone_with_collision(root, shapes):
    """The town level of test_level with a MERGED_COLLISION.big holding ``shapes``
    (``[(name, vertices, triangles)]``, each with a search tree at its lowest corner)."""
    from dr2kit.container.big import BigArchive
    from conftest import make_archive
    from test_level import collision_shape
    entries = []
    for name, verts, tris in shapes:
        for k, v in collision_shape(name, verts, tris):
            if k.endswith("hkpMoppCode"):
                v = _mopp([min(p[i] for p in verts) for i in range(3)])
            entries.append((k, v))
    path = root / "data/models/environment/town/town_z01.big"
    zone = BigArchive.parse(path.read_bytes())
    zone.add("MERGED_COLLISION.big", make_archive(
        ("persistent.big", make_archive(*entries).to_bytes())).to_bytes())
    path.write_bytes(zone.to_bytes())
    return AssetTree(root)


WALLS = [(-1.0, 0.0, -1.0), (1.0, 0.0, -1.0), (-1.0, 1.0, 1.0), (1.0, 1.0, 1.0)]


def test_move_shapes_moves_vertices_tree_and_bounds(tmp_path):
    from dr2kit.formats.collision import move_shapes, read_collision
    root = tmp_path / "game"
    root.mkdir()
    make_level(root)
    tree = _zone_with_collision(root, [("COL_pro_1", WALLS, [(0, 1, 2), (2, 1, 3)])])
    vp = ZV + "/MERGED_COLLISION.big"
    data = move_shapes(tree.resolve(vp).data(), {"meshcol_pro_1": (10, 0, -2)}, vp)
    from dr2kit.container.big import BigArchive
    (s,) = read_collision(BigArchive.parse(data))
    assert s.vertices[0] == (9.0, 0.0, -3.0) and s.mesh == "meshCOL_pro_1"
    pers = BigArchive.parse(BigArchive.parse(data).get("persistent.big").data())
    origin = struct.unpack_from("<3f", pers.get("meshCOL_pro_1 hkpMoppCode").data())
    assert origin == (9.0, 0.0, -3.0)                  # the tree moved with the vertices
    head = struct.unpack_from(">7f", pers.get("meshCOL_pro_1").data(), 32)
    assert head[1:4] == (9.0, 0.0, -3.0) and head[4:7] == (11.0, 1.0, -1.0)
    assert pers.get("meshCOL_pro_1 hkpMoppCode").data()[12:] == _mopp((0, 0, 0))[12:]
    with pytest.raises(FormatError, match="nope"):
        move_shapes(tree.resolve(vp).data(), {"meshnope": (1, 0, 0)}, vp)


def test_buildings_group_parts_and_collision_and_move_together(tmp_path):
    from dr2kit.convert import buildings as cb
    from dr2kit.convert import level as cl
    from dr2kit.formats.collision import read_collision
    root = tmp_path / "game"
    root.mkdir()
    make_level(root, pieces=("store", "boards", "car", "lot"), placements=[
        placement_record("store", 0, (0, 0.5, 0), lo=(-1, 0, -1), hi=(1, 1, 1)),
        placement_record("boards", 1, (1, 0.5, 0), lo=(0.95, 0.2, -0.8), hi=(1.05, 0.8, 0.8)),
        placement_record("lot", 3, (20, 1, 0), lo=(10, 0, -10), hi=(30, 2, 10)),
        placement_record("car", 2, (20, 0.5, 0), lo=(19, 0, -1), hi=(21, 1, 1))])
    fence = [(10.0, 0.0, -10.0), (30.0, 0.0, -10.0), (10.0, 2.0, -10.0), (30.0, 2.0, -10.0)]
    tree = _zone_with_collision(root, [("pro_1", WALLS, [(0, 1, 2), (2, 1, 3)]),
                                       ("pro_2", fence, [(0, 1, 2), (2, 1, 3)])])
    zd = cl.Level.open(tree, "town").zone("z01")
    bs = {b.name: b for b in cb.zone_buildings(zd, cl.zone_shapes(tree, zd))}
    assert bs["store"].parts == ["store", "boards"] and bs["store"].shapes == ["meshpro_1"]
    # the car stands inside the lot's box but doesn't touch its fence: a building alone
    assert bs["lot"].parts == ["lot"] and bs["car"].parts == ["car"]
    mod = create(tmp_path / "m", "m")
    z = PieceEdits.open(mod, tree, ZV)
    assert z.place_building("boards", [5, 0.5, 0]) == []          # by any part
    assert z.placement("boards").position == (6, 0.5, 0)
    h = math.sqrt(0.5)
    warn = z.place_building("store", [5, 0.5, 0], [0, h, 0, h])
    assert warn and "turned" in warn[0]
    assert [round(c, 4) for c in z.placement("boards").position] == [5, 0.5, -1]
    z.save()
    col = pieces_path(mod, ZV, pe.COLLISION)
    assert json.loads(col.read_text())["collision"] == {"meshpro_1": {"move": [5, 0, 0]}}
    out = tmp_path / "out"
    build.build([Mod.load(mod)], "cz", tree, out)
    (s, _f) = read_collision(AssetTree(out).open_archive(ZV + "/MERGED_COLLISION.big"))
    assert s.vertices[0] == (4.0, 0.0, -1.0)
    z.hide_building("store")
    assert z.building_hidden("boards")
    assert z.edits.collision["meshpro_1"] == {"move": [5, 0, 0], "hidden": True}
    names = z.copy_building("store", [0, 0, 9])
    assert names == ["store#1", "boards#2"]
    z.restore_building("store")
    assert not z.edits.pieces and not z.edits.collision and len(z.edits.copies) == 2
    # the modder's corrections: the boards on their own, then back as guessed
    cb.set_correction("cz", "town_z01", "boards", "")
    moves = cb.corrections("cz", "town_z01")
    assert moves == {"boards": ""}
    bs = {b.name: b for b in cb.zone_buildings(zd, cl.zone_shapes(tree, zd), moves)}
    assert bs["store"].parts == ["store"] and bs["boards"].parts == ["boards"]
    bs = {b.name: b for b in cb.zone_buildings(zd, cl.zone_shapes(tree, zd), {"car": "store"})}
    assert bs["store"].parts == ["store", "boards", "car"] and "car" not in bs
    cb.set_correction("cz", "town_z01", "boards", None)
    assert cb.corrections("cz", "town_z01") == {}


@pytest.mark.gamedata
def test_case_zero_store_is_one_building_with_its_collision(game_root):
    """The store in front of the safehouse (hidden in game 2026-10-11: its boards, writing
    and collision stayed; then, grouped, its roof unit stayed floating): one building of
    four parts (the unit rests on its roof) and two collision shapes; the next building's
    roof vent goes with it, not with a wide vent piece above both."""
    from dr2kit.convert import buildings as cb
    from dr2kit.convert import level as cl
    tree = AssetTree(game_root("cz"))
    zd = cl.Level.open(tree, "prologue").zone("z04")
    b = cb.building_of(cb.zone_buildings(zd, cl.zone_shapes(tree, zd)), "z04_gen_e_details")
    bs = cb.zone_buildings(zd, cl.zone_shapes(tree, zd))
    assert b.parts == ["z04_gen_e_structure", "z04_gen_e_details", "z04_gen_e_decals",
                       "z04_roof_vent_3"]
    assert b.shapes == ["meshCOL_pro_351", "meshCOL_z04_camera"]
    f = cb.building_of(bs, "z04_roof_vent_04")
    assert f.name == "z04_gen_f_detail" and "z04_gen_f_decal_2" in f.parts

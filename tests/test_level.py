"""Levels (phase 10): zone list and placement records, a synthetic level assembled into
one .glb, the texture finder's own-pack and _LOD rules; and on the real games, the
bowling alley zone and the level census (skipped without the games)."""

from __future__ import annotations

import math
import struct

import pytest

from conftest import make_archive, make_bct, make_scene
from dr2kit.container.vpath import AssetTree
from dr2kit.convert import gltf
from dr2kit.convert import level as clevel
from dr2kit.formats import level as lvl


def zone_record(name, lo, hi, flag=-1) -> bytes:
    c = tuple((a + b) / 2 for a, b in zip(lo, hi))
    r = math.dist(lo, hi) / 2
    return (name.encode().ljust(64, b"\0") + struct.pack(">10f", *lo, *hi, *c, r)
            + struct.pack(">i", flag) + bytes(24))


def placement_record(piece, index, pos, rot=(0.0, 0.0, 0.0, 1.0), lo=(-1, -1, -1),
                     hi=(1, 1, 1), flags=0) -> bytes:
    rec = bytearray(piece.encode().ljust(32, b"\0") * 2)
    rec += struct.pack(">20f", 1, 1, 1, *rot, *pos, *lo, *hi, *pos, 2.0)
    rec += bytes(64)
    struct.pack_into(">I", rec, 144, flags)
    struct.pack_into(">f", rec, 148, 80.0)
    struct.pack_into(">I", rec, 160, 0xFFFFFFFF)
    struct.pack_into(">f", rec, 168, 10.0)
    struct.pack_into(">I", rec, 196, index)
    return bytes(rec)


def organization(*records) -> bytes:
    return make_archive(("NumModelInstance", struct.pack(">I", len(records))),
                        ("ModelInstanceArray", b"".join(records)),
                        ("ModelInstanceArray_Dynamic", b""),
                        ("NumModelInstance_Dynamic", struct.pack(">I", 0)),
                        ("_ZONEINFO_", struct.pack(">10f", *range(10)))).to_bytes()


def make_level(root, pieces=("box",), placements=None, lod=True):
    """data/models/environment/town: zonelist.big + town_z01.big with the pieces."""
    folder = root / "data" / "models" / "environment" / "town"
    folder.mkdir(parents=True)
    zl = make_archive(("NumZones", struct.pack(">I", 1)),
                      ("ZoneList", zone_record("town\\town_z01", (-10, 0, -10), (10, 5, 10))))
    (folder / "zonelist.big").write_bytes(zl.to_bytes())
    entries = []
    for name in pieces:
        if lod:
            entries.append((f"{name}_LOD.tex", make_archive(
                ("box_cm.bct", make_bct("DXT1", 4, 4))).to_bytes()))
        entries.append((f"{name}.big", make_archive((f"_COMP_{name}.big",
                                                     make_scene(combined=True))).to_bytes()))
        entries.append((f"{name}.tex", make_archive(("box_cm", make_bct("DXT1", 8, 8))).to_bytes()))
    if placements is None:
        placements = [placement_record(p, i, (5.0 * i, 0.0, 0.0)) for i, p in enumerate(pieces)]
    entries.append(("ZONE_ORGANIZATION.big", organization(*placements)))
    (folder / "town_z01.big").write_bytes(make_archive(*entries).to_bytes())
    return AssetTree(root)


def test_placement_record_round_trip_and_fields():
    h = math.sqrt(0.5)
    raw = placement_record("z05_glass08", 24, (-172.4, 6.3, -27.0), (0.0, h, 0.0, -h), flags=0x20)
    p = lvl.Placement.parse(raw)
    assert p.piece == p.name2 == "z05_glass08"
    assert p.index == 24 and p.flags == 0x20
    assert p.draw_distance == 80.0 and p.lod_distance == 10.0
    assert p.tail == lvl.EXPECTED_TAIL
    assert p.to_bytes() == raw
    # a quarter turn about Y: local +X goes to world +Z (x, y, z, w as glTF)
    x, y, z = p.to_world((1.0, 0.0, 0.0))
    assert (round(x - p.position[0], 5), round(y - p.position[1], 5),
            round(z - p.position[2], 5)) == (0.0, 0.0, 1.0)
    with pytest.raises(Exception):
        lvl.Placement.parse(raw[:-1])


def test_zone_list():
    raw = zone_record("living_research\\living_research_z01", (0, 0, 0), (2, 2, 2))
    (z,) = lvl.read_zone_list(struct.pack(">I", 1), raw)
    assert z.zone == "living_research_z01" and z.flag == -1
    assert z.to_bytes() == raw
    with pytest.raises(Exception):
        lvl.read_zone_list(struct.pack(">I", 2), raw)


def test_level_reads_zones_and_names_mismatches(tmp_path):
    tree = make_level(tmp_path, pieces=("box", "lonely"),
                      placements=[placement_record("box", 0, (1, 2, 3)),
                                  placement_record("ghost", 1, (0, 0, 0))])
    (L,) = clevel.list_levels(tree)
    assert L.name == "town" and L.zone_names() == ["town_z01"]
    z = L.zone("z01")
    assert sorted(z.pieces) == ["box", "lonely"]
    assert z.unplaced == ["lonely"] and z.missing == ["ghost"]
    st = clevel.ZoneStats()
    clevel.zone_glb(tree, z, game="cz", stats=st)
    assert st.placements == 1
    assert [f[0] for f in st.failed] == ["ghost"]           # named, never silently dropped


def test_zone_glb_places_pieces_and_shares_textures(tmp_path):
    tree = make_level(tmp_path, pieces=("box", "crate"))
    z = clevel.Level.open(tree, "town").zone("town_z01")
    g = gltf.Glb.parse(clevel.zone_glb(tree, z, game="cz"))
    nodes = g.gltf["nodes"]
    placed = [n for n in nodes if "dr2_piece" in n.get("extras", {})]
    assert [n["translation"] for n in placed] == [[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]]
    (top,) = g.gltf["scenes"][0]["nodes"]
    assert nodes[top]["name"] == "town_z01"                 # one group per zone
    # both pieces use the same texture bytes: stored once
    assert len(g.gltf["images"]) == 1
    # the full-size texture, not the _LOD copy listed before it in the zone
    assert g.gltf["scenes"][0]["extras"]["dr2"]["zone"] == "town_z01"


def test_texture_finder_prefers_full_size_over_lod(tmp_path):
    from dr2kit.convert.model import TextureFinder
    tree = make_level(tmp_path)
    vp = "data/models/environment/town/town_z01.big/box.big/_COMP_box.big"
    f = TextureFinder(tree, vp)
    assert f.bct("box_cm")[0].endswith("/box.tex/box_cm")
    f = TextureFinder(tree, vp, lod=True)
    assert f.bct("box_cm")[0].endswith("/box_LOD.tex/box_cm.bct")


def test_assembler_instances_one_mesh_many_times():
    from dr2kit.formats.scene import Scene
    data = gltf.model_to_glb(Scene.parse(make_scene(combined=True)))
    asm = gltf.Assembler()
    grp = asm.group("zone")
    asm.add(data, [{"name": "a", "translation": (1, 0, 0)},
                   {"name": "b", "translation": (2, 0, 0)}], grp)
    g = gltf.Glb.parse(asm.to_bytes())
    src = gltf.Glb.parse(data)
    assert len(g.gltf["meshes"]) == len(src.gltf["meshes"])     # meshes stored once
    mesh_nodes = [n for n in g.gltf["nodes"] if "mesh" in n]
    assert len(mesh_nodes) == 2 * sum(1 for n in src.gltf["nodes"] if "mesh" in n)
    assert g.accessor(g.gltf["meshes"][0]["primitives"][0]["attributes"]["POSITION"]) == \
        src.accessor(src.gltf["meshes"][0]["primitives"][0]["attributes"]["POSITION"])


# --- the real games --------------------------------------------------------------------

@pytest.mark.gamedata
def test_bowling_alley_zone(game_root):
    tree = AssetTree(game_root("cz"))
    L = clevel.Level.open(tree, "prologue")
    assert len(L.zones) == 11
    z = L.zone("z05")
    assert len(z.pieces) == len(z.placements) == 19 and not z.unplaced and not z.missing
    org = z.organization
    stored = tree.resolve(f"{z.vpath}/ZONE_ORGANIZATION.big/ModelInstanceArray").data()
    assert org.placements_bytes() == stored
    glass = next(p for p in z.placements if p.piece == "z05_glass08")
    assert abs(glass.rotation[1] - math.sqrt(0.5)) < 1e-4


@pytest.mark.gamedata
@pytest.mark.slow
@pytest.mark.parametrize("game", ["cz", "cw"])
def test_level_census(game, game_root):
    from dr2kit.census import CensusReport, check_levels
    tree = AssetTree(game_root(game))
    rep = CensusReport(game, str(tree.root))
    check_levels(rep, tree, game)
    assert rep.problems == []
    assert rep.level_counts["items and doors with their model"] == {"cz": 1060, "cw": 1835}[game]
    placements = {"cz": 922, "cw": 972}[game]
    assert rep.level_counts["placements"] == placements
    assert rep.level_counts["pieces read"] == placements
    explained = (rep.level_counts["placed bounds = stored bounds"]
                 + rep.level_counts["placed vertices inside the stored bounds (loose shape bounds)"])
    assert placements - explained == {"cz": 1, "cw": 2}[game]   # named in docs/formats.md


# --- step 2: level text files ------------------------------------------------------------

LEVEL_TXT = (
    'cItemPlacement HotDog3\r\n{\r\n\tItemName = "HotDog"\r\n'
    '\tLocation = "1.0,2.0,3.0"\r\n\tRotation = "0,0,0,1"\r\n'
    '\tcItemPlacement Soda\r\n\t{\r\n\t\tItemName = "Soda"\r\n'
    '\t\tLocation = "4,5,6"\r\n\t\tRotation = "0,0,0,1"\r\n\t}\r\n\r\n}\r\n\r\n'
    'cSpawnPoint Start\r\n{\r\n\tLocation0 = "1,0,1"\r\n\tRotation0 = "3.14159"\r\n}\r\n\r\n'
    'cZombieWarehouse Roof\r\n{\r\n\tcPolygonLarge Ground\r\n\t{\r\n\t\tHeight = "2.0"\r\n'
    '\t\tNumVertex = "3"\r\n\t\tVertex0 = "0,0,0"\r\n\t\tVertex1 = "1,0,0"\r\n'
    '\t\tVertex10 = "9,9,9"\r\n\t\tVertex2 = "0,0,1"\r\n\t}\r\n}\r\n\r\n'
    'cPolygonSmall PR102\r\n{\r\n\tText = "7"\r\n\tVertex0 = "0,0,0"\r\n}\r\n'
    'cLightContextVolume LC\r\n{\r\n\tQuadName = "L_out"\r\n}\r\n'
    'cPolygonLarge L_out\r\n{\r\n\tVertex0 = "0,0,0"\r\n}\r\n'
    'cMysteryThing X\r\n{\r\n\tA = "1" // a comment\r\n}\r\n')
NAVMESH = ('Vertices\r\n{\r\n\t"0,0,0"\r\n\t"1,0,0"\r\n\t"1,0,1"\r\n\t"0,0,1"\r\n}\r\n'
           'Polyhedrons\r\n{\r\n\tPolyhedronEdges\r\n\t{\r\n\t\tmask = "3"\r\n'
           '\t\t"0"\r\n\t\t"1"\r\n\t\t"2"\r\n\t\t"3"\r\n\t}\r\n}\r\n\r\nConnections\r\n{\r\n}\r\n')
ITEMS = ('cFoodItem HotDog\r\n{\r\n\tAssetFilename = "data/models/food/hotdog"\r\n}\r\n'
         'cFoodItem Soda\r\n{\r\n\tMergedFilename = "data/dynamicprops/soda"\r\n'
         '\tAssetFilename = "bigsoda"\r\n}\r\n')
MAP_CSV = ('# wid_name,\tname string\r\npr101,\t1709,\t1710,\t1711,\t1700,\r\n'
           'savepoint,\t-85.4,\t0.0,\t109.3,\tLEVEL_TOWN,\r\n')


def make_datafile(root):
    data = root / "data"
    data.mkdir(exist_ok=True)
    df = make_archive(("town.txt", LEVEL_TXT.encode()), ("waypoint_town.txt", b"\r\n"),
                      ("nm_town.txt", NAVMESH.encode()), ("items.txt", ITEMS.encode()),
                      ("fe_map_f1.csv", MAP_CSV.encode()))
    (data / "datafile.big").write_bytes(df.to_bytes())
    scene = make_scene(combined=True)
    sa = make_archive(("HotDog.big", make_archive(("hotdog.big", scene)).to_bytes()),
                      ("soda.big", make_archive(("bigsoda.big", scene),
                                                ("bigsoda_cherry.big", b"")).to_bytes()))
    (data / "streamedassets.big").write_bytes(sa.to_bytes())
    return AssetTree(root)


def test_levelscript_keeps_every_byte_and_edits_one_line():
    from dr2kit.formats.levelscript import Document
    doc = Document.parse(LEVEL_TXT.encode(), "town.txt")
    assert doc.to_bytes() == LEVEL_TXT.encode()
    hot = doc.blocks[0]
    assert hot.children[0].name == "Soda"
    roof = doc.blocks[2].children[0]
    assert roof.numbered("Vertex") == ["0,0,0", "1,0,0", "0,0,1", "9,9,9"]   # by number
    doc.set(hot, "Location", "7,8,9")
    doc.set(hot, "PropState", "-1")                       # a new key, before the brace
    out = doc.to_bytes().decode("latin-1")
    assert '\tLocation = "7,8,9"\r\n' in out and '\tPropState = "-1"\r\n' in out
    again = Document.parse(out, "town.txt")
    assert again.blocks[0].get("PropState") == "-1"
    assert again.blocks[0].children[0].get("Location") == "4,5,6"
    # only the changed line and the added one differ
    assert len(out.splitlines()) == len(LEVEL_TXT.splitlines()) + 1


def test_levelscript_reports_what_it_cannot_read():
    from dr2kit.errors import FormatError
    from dr2kit.formats.levelscript import Document
    with pytest.raises(FormatError, match="town.txt:2"):
        Document.parse('cA B\r\n= "x"\r\n', "town.txt")
    with pytest.raises(FormatError, match="ends inside a block"):
        Document.parse('cA B\r\n{\r\n', "town.txt")


def test_placed_things_and_item_models(tmp_path):
    from dr2kit.convert import placed
    tree = make_datafile(tmp_path)
    assert placed.script_names(tree) == ["town"]
    assert placed.geometry_of("town_safehouse", ["town", "other"]) == "town"
    ls = placed.read_script(tree, "town", placed.ItemModels(tree), {7: "Main Street"})
    items = ls.of_kind("item")
    assert [(t.name, t.parent) for t in items] == [("HotDog3", None), ("Soda", "HotDog3")]
    # CZ style: the pack named after the item; CW style: after MergedFilename, the empty
    # texture-variant placeholder ignored
    assert items[0].model == "data/streamedassets.big/HotDog.big/hotdog.big"
    assert items[1].model == "data/streamedassets.big/soda.big/bigsoda.big"
    (spawn,) = ls.of_kind("spawn")
    assert abs(spawn.rotation[1] - 1.0) < 1e-4            # half a turn about Y
    area, zone = ls.of_kind("zombie_area")               # the area, then each polygon
    assert area.name == "Roof" and not area.polygon
    assert zone.name == "Roof/Ground" and len(zone.polygon) == 4
    assert [t.label for t in ls.of_kind("map_area")] == ["Main Street"]
    assert [t.name for t in ls.of_kind("light_area") if t.polygon] == ["L_out"]
    assert ls.unknown == {"cMysteryThing": 1}             # named, not dropped
    assert ls.navmesh.triangles() == [(0, 1, 2), (0, 2, 3)]
    (point,) = ls.of_kind("map_point")
    assert point.label == "Save point" and point.position == (-85.4, 0.0, 109.3)


@pytest.mark.gamedata
def test_every_placed_item_finds_its_model(game_root):
    from dr2kit.convert import placed
    for game in ("cz", "cw"):
        tree = AssetTree(game_root(game))
        models = placed.ItemModels(tree)
        n = 0
        for s in placed.script_names(tree):
            for t in placed.read_script(tree, s, models).things:
                if t.item:
                    assert t.model, (game, s, t.name, models.why.get(t.item.lower()))
                    n += 1
        assert n == {"cz": 1060, "cw": 1835}[game]


# --- step 3: the Maps tab's data, level materials -------------------------------------------

def test_lightmaps_have_their_own_role():
    from dr2kit.formats.scene import texture_role
    # the endings used to make these normal / self-illumination / detail maps
    for name in ("LM_z01_ash_tree_NE", "AO_z01_sheriff_si", "LM_z04_machine_05_det",
                 "AO_z05_bowling_struc"):
        assert texture_role(name) == "lightmap"
    assert texture_role("wall_concrete_badirty_red_cm") == "colour"


def test_assembler_keeps_blend_textures():
    """A blend's textures are named by number in the material's extras: the assembler
    must renumber them like the standard slots."""
    b = gltf.GlbBuilder()
    img = b.add("images", {"mimeType": "image/png", "bufferView": b.view(b"\x89PNG-a")})
    img2 = b.add("images", {"mimeType": "image/png", "bufferView": b.view(b"\x89PNG-b")})
    t0 = b.add("textures", {"source": img})
    t1 = b.add("textures", {"source": img2})
    b.add("materials", {"pbrMetallicRoughness": {"baseColorTexture": {"index": t0}},
                        "extras": {"dr2": {"blend": {"overlay": t1, "mask": None}}}})
    b.gltf["scenes"][0]["nodes"].append(b.add("nodes", {"name": "n"}))
    data = b.to_bytes()
    other = gltf.GlbBuilder()                 # something else first, so numbers shift
    other.add("images", {"mimeType": "image/png", "bufferView": other.view(b"\x89PNG-c")})
    other.add("textures", {"source": 0})
    other.gltf["scenes"][0]["nodes"].append(other.add("nodes", {"name": "x"}))
    asm = gltf.Assembler()
    asm.add(other.to_bytes(), [{"name": "x"}])
    asm.add(data, [{"name": "n"}])
    g = gltf.Glb.parse(asm.to_bytes())
    mat = g.gltf["materials"][-1]
    base = mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]
    over = mat["extras"]["dr2"]["blend"]["overlay"]
    assert (base, over) == (1, 2)
    src = g.gltf["images"][g.gltf["textures"][over]["source"]]
    view = g.gltf["bufferViews"][src["bufferView"]]
    assert g.bin[view["byteOffset"]:view["byteOffset"] + view["byteLength"]] == b"\x89PNG-b"


def test_map_cache_builds_once_and_rebuilds_when_the_game_changes(tmp_path):
    import os
    import time
    from dr2kit.convert import mapdata
    root = tmp_path / "game"
    root.mkdir()
    tree = make_level(root)
    cache = mapdata.MapCache(tree, "cz", root=tmp_path / "cache")
    p1 = cache.pieces("town", "z01")
    assert p1.is_file() and gltf.Glb.parse(p1.read_bytes()).gltf["nodes"]
    stamp = p1.stat().st_mtime_ns
    assert cache.pieces("town", "z01") == p1 and p1.stat().st_mtime_ns == stamp   # cached
    zone_file = root / "data/models/environment/town/town_z01.big"
    os.utime(zone_file, ns=(time.time_ns(), time.time_ns() + 10**9))
    p2 = mapdata.MapCache(AssetTree(root), "cz", root=tmp_path / "cache").pieces("town", "z01")
    assert p2 != p1 and p2.is_file() and not p1.exists()       # the old build is gone
    assert mapdata.MapCache(tree, "cz", root=tmp_path / "cache").pieces(
        "town", "z01", mapdata.LOD).name.startswith("town_z01-lod-")


def test_map_overview(tmp_path):
    from dr2kit.convert import mapdata
    tree = make_datafile(tmp_path)
    make_level(tmp_path)
    cache = mapdata.MapCache(tree, "cz", root=tmp_path / "cache")
    ov = mapdata.overview(cache, "town")
    assert ov["scripts"] == ["town"] and ov["script"] == "town"
    assert [z["name"] for z in ov["zones"]] == ["town_z01"]
    assert ov["start"]["name"] == "Start"                     # the Start spawn point
    kinds = {m["kind"] for m in ov["markers"]}
    assert {"spawn", "zombie_area", "map_area", "map_point"} <= kinds
    assert "item" not in kinds and len(ov["items"]) == 2      # items come as zone files
    assert len(ov["navmesh"]["triangles"]) == 6
    things = cache.zone_things("town", "z01", "town")
    assert {t.name for t in things} == {"HotDog3", "Soda"}
    assert cache.items("town", "z01", "town").is_file()
    json_doc = mapdata.overview_json(cache, "town")
    assert json_doc.startswith(b"{")


@pytest.mark.gamedata
def test_level_materials_in_the_glb(game_root):
    """The bowling alley's outside: lightmaps on the occlusion slot of the 2nd UV set,
    and the ground's two colour maps blended by a mask (CM2DDU_LM)."""
    from dr2kit.convert.model import export_glb
    tree = AssetTree(game_root("cz"))
    vp = ("data/models/environment/prologue/prologue_z05.big/z05_bowling_struc.big/"
          "_COMP_z05_bowling_struc.big")
    g = gltf.Glb.parse(export_glb(tree, vp, game="cz"))
    mats = {m["name"]: m for m in g.gltf["materials"]}
    wall = next(m for n, m in mats.items() if "wall_concrete_badirty_red_cm" in n)
    assert wall["occlusionTexture"]["texCoord"] == 1
    assert wall["extras"]["dr2"]["lightmap"] == "AO_z05_bowling_struc"
    ground = next(m for n, m in mats.items() if "sand_pebbles_brown_cm" in n)
    blend = ground["extras"]["dr2"]["blend"]
    assert blend["textures"] == ["gravel_dirty_gray_cm", "page_grass_patch_mask_cm"]
    assert (blend["overlay_uv"], blend["mask_uv"], blend["by"]) == (1, 2, "mask.g²")
    assert ground["occlusionTexture"]["texCoord"] == 3


# --- step 4: exporting a level ---------------------------------------------------------------

def test_export_level_groups_zone_layers_and_markers(tmp_path):
    from dr2kit.catalog.level_export import export_level
    root = tmp_path / "game"
    root.mkdir()
    tree = make_datafile(root)
    make_level(root)
    res = export_level(tree, "cz", "town", tmp_path / "out", markers=("spawn", "zombie_area",
                                                                      "map_point", "navmesh"))
    folder = tmp_path / "out" / "cz" / "town"
    assert res.folder == folder and not res.failed
    assert {p.name for p in res.files} >= {"town_z01.glb", "town.txt", "nm_town.txt",
                                           "fe_map_f1.csv", "info.txt"}
    g = gltf.Glb.parse((folder / "town_z01.glb").read_bytes())
    nodes = g.gltf["nodes"]
    layers = {n["name"]: n["extras"]["dr2_layer"] for n in nodes
              if "dr2_layer" in n.get("extras", {})}
    assert layers["town_z01"] == "zone" and layers["Buildings"] == "pieces"
    assert layers["Items and doors"] == "items" and layers["Markers"] == "markers"
    assert layers["Spawn points"] == "spawn" and layers["Navigation mesh"] == "navmesh"
    start = next(n for n in nodes if n["name"] == "Start")
    assert "mesh" not in start and start["translation"] == [1.0, 0.0, 1.0]   # an Empty
    roof = next(n for n in nodes if n["name"] == "Roof/Ground")
    prim = g.gltf["meshes"][roof["mesh"]]["primitives"][0]
    assert prim["mode"] == 2                                                # an outline
    assert res.items == 2 and res.markers >= 4
    # a second run skips what is there (resumable)
    again = export_level(tree, "cz", "town", tmp_path / "out")
    assert folder / "town_z01.glb" in again.skipped


def test_dr2_export_a_level(tmp_path, monkeypatch, capsys):
    from dr2kit.cli.main import main
    root = tmp_path / "game"
    root.mkdir()
    make_datafile(root)
    make_level(root)
    monkeypatch.setenv("DR2_CZ_DATA", str(root))
    out = tmp_path / "out"
    assert main(["export", "town", "--whole", "--markers", "none", "-g", "cz", "-o",
                 str(out), "-q"]) == 0
    assert (out / "cz" / "town" / "town.glb").is_file()
    assert main(["export", "town", "--zone", "z99", "-g", "cz", "-o", str(out)]) == 1


def test_a_level_texture_mod_reaches_every_copy_in_the_zone(tmp_path):
    """The game takes a level texture from the first pack of the zone that has it, so a
    PNG on any copy goes to every identical copy; the finder picks the first (phase 10,
    checked in game)."""
    from dr2kit.convert import png
    from dr2kit.convert.model import TextureFinder
    from dr2kit.mods.build import plan_mods
    from dr2kit.mods.manifest import Mod, create
    root = tmp_path / "game"
    root.mkdir()
    tree = make_level(root, pieces=("box", "crate"), lod=False)
    zone = "data/models/environment/town/town_z01.big"
    f = TextureFinder(tree, f"{zone}/crate.big/_COMP_crate.big")
    assert f.bct("box_cm")[0] == f"{zone}/box.tex/box_cm"          # first in the zone
    mod = create(tmp_path / "m", "m")
    out = mod / "replace" / zone / "crate.tex" / "box_cm.png"
    out.parent.mkdir(parents=True)
    png.write(out, png.Image(8, 8, bytes((0, 0, 255, 255)) * 64))
    plan = plan_mods([Mod.load(mod)], "cz", tree)
    assert {p.vpath for p in plan.planned} == {f"{zone}/crate.tex/box_cm",
                                                f"{zone}/box.tex/box_cm"}
    assert any("box.tex" in n for n in plan.notes)


# --- stretch: zombies in their areas -------------------------------------------------------

MISSIONS = ('cMissionDefinition Opening\r\n{\r\n\tcMissionLevelReady Town\r\n\t{\r\n'
            '\t\tLevelName = "LEVEL_TOWN"\r\n\t\tcMissionZombieFactory Crowd\r\n\t\t{\r\n'
            '\t\t\tAmount0 = "30"\r\n\t\t\tType0 = "zombie_test"\r\n'
            '\t\t\tZombieWarehouseName = "Roof"\r\n\t\t}\r\n\t}\r\n}\r\n'
            'cMissionDefinition Elsewhere\r\n{\r\n\tcMissionLevelReady X\r\n\t{\r\n'
            '\t\tLevelName = "LEVEL_OTHER"\r\n\t\tcMissionZombieFactory C2\r\n\t\t{\r\n'
            '\t\t\tAmount0 = "5"\r\n\t\t\tType0 = "zombie_test"\r\n'
            '\t\t\tZombieWarehouseName = "Roof"\r\n\t\t}\r\n\t}\r\n}\r\n')


def test_zombie_crowds_stand_in_their_area(tmp_path):
    from dr2kit.container.big import BigArchive
    from dr2kit.convert import placed, zombies
    tree = make_datafile(tmp_path)
    df = tmp_path / "data" / "datafile.big"
    arc = BigArchive.parse(df.read_bytes())
    arc.add("missions.txt", MISSIONS.encode())
    df.write_bytes(arc.to_bytes())
    tree = AssetTree(tmp_path)
    crowds = zombies.crowds(tree, "town")
    assert [(c.mission, c.area, c.amounts) for c in crowds] == [
        ("Opening", "Roof", {"zombie_test": 30})]            # LEVEL_OTHER's isn't here
    ls = placed.read_script(tree, "town")
    spots = zombies.spots(ls, crowds, per_area=8)
    assert len(spots) == 8 and {s.type for s in spots} == {"zombie_test"}
    for s in spots:                                       # inside the floor (0..1 square)
        x, y, z = s.position
        assert -1e-6 <= x <= 9.0001 and -1e-6 <= z <= 9.0001 and abs(y) < 9.0001
    assert zombies.spots(ls, crowds, per_area=8) == spots      # seeded: the same each time


def test_floor_polygons_triangulate():
    from dr2kit.convert.zombies import _triangulate_xz
    square = [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]
    assert len(_triangulate_xz(square)) == 2
    l_shape = [(0, 0, 0), (2, 0, 0), (2, 0, 1), (1, 0, 1), (1, 0, 2), (0, 0, 2)]
    tris = _triangulate_xz(l_shape)
    area = sum(abs((l_shape[b][0] - l_shape[a][0]) * (l_shape[c][2] - l_shape[a][2])
                   - (l_shape[b][2] - l_shape[a][2]) * (l_shape[c][0] - l_shape[a][0])) / 2
               for a, b, c in tris)
    assert len(tris) == 4 and abs(area - 3.0) < 1e-9


def test_light_table_by_hour(tmp_path):
    from dr2kit.container.big import BigArchive
    from dr2kit.convert import mapdata
    tree = make_datafile(tmp_path)
    hours = ",".join(str(h) for h in range(24))
    rows = ["name," + hours]
    for c in "xyz":
        rows.append(f"mSkyColor1.{c}," + ",".join(str(h / 10) for h in range(24)))
    rows.append("mSHRenderMatrixRed.33," + ",".join("0.5" for _ in range(24)))
    rows.append("mSHRenderMatrixRed.13," + ",".join("0.1" for _ in range(24)))
    rows.append("mFogEnd," + ",".join("200" for _ in range(24)))
    df = tmp_path / "data" / "datafile.big"
    arc = BigArchive.parse(df.read_bytes())
    arc.add("town.csv", "\r\n".join(rows).encode())
    df.write_bytes(arc.to_bytes())
    table = mapdata.light_table(AssetTree(tmp_path), "/town.csv")
    assert len(table) == 24
    assert table[12]["sky"][0] == [1.2, 1.2, 1.2] and table[12]["fog_end"] == 200
    # irradiance n^T M n, n = (0, ±1, 0, 1): up = M11 + M13 + M31 + M33
    assert abs(table[0]["ambient"]["up"][0] - 0.6) < 1e-9
    assert abs(table[0]["ambient"]["down"][0] - 0.4) < 1e-9
    assert mapdata.light_table(AssetTree(tmp_path), "nope.csv") is None


# --- stretch: the collision mesh ---------------------------------------------------------

def collision_shape(name, verts, tris, words=(0, 0, 0, 0, 0, 0, 0, 1)):
    """The entries of one ``mesh<name>`` group (docs/formats.md §Levels, "Collision")."""
    lo = [min(v[i] for v in verts) for i in range(3)]
    hi = [max(v[i] for v in verts) for i in range(3)]
    small = len(verts) <= 256
    flat = [i for t in tris for i in t]
    return [(f"mesh{name}", struct.pack(">8I7f", *words, 1.0, *lo, *hi)),
            (f"mesh{name} hkCollisionShapeMesh",
             struct.pack(">2I", len(verts), len(tris)) + bytes(36)),
            (f"mesh{name} CollisionVertices", b"".join(struct.pack(">3f", *v) for v in verts)),
            (f"mesh{name} CollisionIndices",
             struct.pack(f">{len(flat)}{'B' if small else 'H'}", *flat)),
            (f"mesh{name} CollisionMaterials", bytes(4 * len(tris))),
            (f"mesh{name} hkpMoppCode", b"")]


def test_zone_collision_places_shapes_and_names_the_lost(tmp_path):
    from dr2kit.formats.collision import read_collision
    tree = make_level(tmp_path, pieces=("box",),
                      placements=[placement_record("box", 0, (3.0, 0.0, 0.0))])
    quad = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0)]
    floor = [(-8.0, 0.0, -8.0), (8.0, 0.0, -8.0), (-8.0, 0.0, 8.0)]
    lost = [(100.0, 0.0, 100.0), (101.0, 0.0, 100.0), (100.0, 0.0, 101.0)]
    pers = make_archive(*collision_shape("COL_dummy01", quad, [(0, 1, 2), (2, 1, 3)]),
                        *collision_shape("floor", floor, [(0, 1, 2)]),
                        *collision_shape("COL_lost", lost, [(0, 1, 2)]))
    path = tmp_path / "data/models/environment/town/town_z01.big"
    from dr2kit.container.big import BigArchive
    zone = BigArchive.parse(path.read_bytes())
    zone.add("MERGED_COLLISION.big", make_archive(("persistent.big", pers.to_bytes())).to_bytes())
    path.write_bytes(zone.to_bytes())
    tree = AssetTree(tmp_path)
    vp = "data/models/environment/town/town_z01.big/MERGED_COLLISION.big"
    shapes = read_collision(tree.open_archive(vp), vp)
    assert [s.name for s in shapes] == ["dummy01", "floor", "lost"]   # "mesh", "COL_" off
    assert shapes[0].triangles == [(0, 1, 2), (2, 1, 3)] and shapes[0].index_size == 1
    z = clevel.Level.open(tree, "town").zone("z01")
    col = clevel.zone_collision(tree, z)
    assert col.shapes == {"piece": 1, "world": 1} and col.unplaced == ["lost"]
    assert col.vertices[:4] == [(3.0, 0.0, 0.0), (4.0, 0.0, 0.0), (3.0, 1.0, 0.0),
                                (4.0, 1.0, 0.0)]                       # placed like box
    assert col.vertices[4:] == floor                                   # world as stored
    assert col.triangles[2] == (4, 5, 6)
    g = gltf.Glb.parse(clevel.collision_glb(tree, z))
    (node,) = [n for n in g.gltf["nodes"] if "mesh" in n]
    assert node["extras"]["dr2_kind"] == "collision" and node["extras"]["dr2_unplaced"] == 1


@pytest.mark.gamedata
def test_collision_under_the_prologue_start(game_root):
    """Every shape of CZ's prologue is read; the ground under Start (a shape stored in its
    piece's space, found by the collision node number) is in place."""
    from dr2kit.convert import placed
    tree = AssetTree(game_root("cz"))
    L = clevel.Level.open(tree, "prologue")
    from dr2kit.formats.collision import read_collision
    cols, read = [], 0
    for zd in L.zone_data():
        cols.append(clevel.zone_collision(tree, zd))
        vp = f"{zd.vpath}/MERGED_COLLISION.big"
        read += sum(1 for s in read_collision(tree.open_archive(vp), vp) if s.vertices)
    assert read == 402                       # every shape drawn or named, none dropped
    assert sum(sum(c.shapes.values()) + len(c.unplaced) for c in cols) == read
    start = next(t for t in placed.read_script(tree, "prologue", None, None).things
                 if t.kind == "spawn" and t.name == "Start")
    px, py, pz = start.position

    def ground(c):
        for a, b, d in c.triangles:
            A, B, C = c.vertices[a], c.vertices[b], c.vertices[d]
            det = (B[2] - C[2]) * (A[0] - C[0]) + (C[0] - B[0]) * (A[2] - C[2])
            if abs(det) < 1e-9:
                continue
            l1 = ((B[2] - C[2]) * (px - C[0]) + (C[0] - B[0]) * (pz - C[2])) / det
            l2 = ((C[2] - A[2]) * (px - C[0]) + (A[0] - C[0]) * (pz - C[2])) / det
            if min(l1, l2, 1 - l1 - l2) >= 0 and \
                    abs(l1 * A[1] + l2 * B[1] + (1 - l1 - l2) * C[1] - py) < 1.5:
                return True
        return False
    assert any(ground(c) for c in cols)

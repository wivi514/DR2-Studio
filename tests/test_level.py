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

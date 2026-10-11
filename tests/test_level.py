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
    placements = {"cz": 922, "cw": 972}[game]
    assert rep.level_counts["placements"] == placements
    assert rep.level_counts["pieces read"] == placements
    explained = (rep.level_counts["placed bounds = stored bounds"]
                 + rep.level_counts["placed vertices inside the stored bounds (loose shape bounds)"])
    assert placements - explained == {"cz": 1, "cw": 2}[game]   # named in docs/formats.md

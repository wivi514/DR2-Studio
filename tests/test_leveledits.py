"""Level text edits (phase 11): block add / remove in the tool's style, ``.edits.json``
apply / diff / merge, the build merging several mods over the recomp's copy, and the
meaning checks. Synthetic files only (no game data)."""

import json

import pytest

from dr2kit.container.big import LZX
from dr2kit.errors import FormatError
from dr2kit.formats import leveledits as le
from dr2kit.formats.levelscript import Document, render_block
from dr2kit.mods import build as mbuild
from dr2kit.mods.manifest import Mod, ModError, create

from conftest import make_archive

LEVEL = (
    "cItemPlacement Scissors\r\n{\r\n"
    '\tIsStatic = ""\r\n\tItemName = "Scissors"\r\n'
    '\tLocation = "-139.048,3.399,-85.070"\r\n\tRotation = "0,0,0,1"\r\n}\r\n\r\n'
    "cItemPlacement Shampoo\r\n{\r\n"
    '\tItemName = "Shampoo"\r\n\tLocation = "-145.900,3.415,-89.782"\r\n'
    '\tRotation = "0,0,0,1"\r\n}\r\n\r\n\r\n')

MISSIONS = (
    "cMissionDefinition Zeds\r\n{\r\n\tDuration = \"10\"\r\n"
    "\tcMissionLevelReady Ready\r\n\t{\r\n\t\tLevelName = \"LEVEL_PROLOGUE\"\r\n"
    "\t\tcMissionZombieFactory x2009\r\n\t\t{\r\n\t\t\tAmount0 = \"40\"\r\n"
    "\t\t\tType0 = \"zombie_skinny\"\r\n\t\t\tZombieWarehouseName = \"street\"\r\n"
    "\t\t}\r\n\r\n\t}\r\n\r\n}\r\n\r\n\r\n"
    "cMissionDefinition Other\r\n{\r\n\tDuration = \"5\"\r\n"
    "\tcMissionLevelReady Ready\r\n\t{\r\n\t\tLevelName = \"LEVEL_PROLOGUE\"\r\n"
    "\t\tcMissionZombieFactory x2009\r\n\t\t{\r\n\t\t\tAmount0 = \"3\"\r\n"
    "\t\t}\r\n\r\n\t}\r\n\r\n}\r\n\r\n\r\n"
    "cMissionDefinition Third\r\n{\r\n\tDuration = \"1\"\r\n}\r\n\r\n\r\n")


def test_render_matches_the_tool_style():
    doc = Document.parse(MISSIONS)
    for b in doc.walk():
        depth = len(doc.lines[b.line]) - len(doc.lines[b.line].lstrip("\t"))
        assert "".join(render_block(b, depth)) == doc.text(b)


def test_find_by_path_and_ambiguity():
    doc = Document.parse(MISSIONS)
    b = doc.find("cMissionDefinition Other/cMissionLevelReady Ready/cMissionZombieFactory x2009")
    assert b.get("Amount0") == "3"
    assert doc.path(b) == "cMissionDefinition Other/cMissionLevelReady Ready/" \
                          "cMissionZombieFactory x2009"
    with pytest.raises(FormatError, match="no block"):
        doc.find("cMissionDefinition Nope")


def test_set_new_key_sorted_and_comment_kept():
    doc = Document.parse(LEVEL)
    b = doc.find("cItemPlacement Shampoo")
    doc.set(b, "PropState", "-1")
    assert [p.key for p in b.props] == ["ItemName", "Location", "PropState", "Rotation"]
    assert '\tPropState = "-1"\r\n\tRotation' in doc.to_bytes().decode()
    z = Document.parse('cSet a\r\n{\r\n\tstart = "0" //Day 1 at 0:0\r\n}\r\n')
    z.set(z.blocks[0], "start", "25200")
    assert z.to_bytes() == b'cSet a\r\n{\r\n\tstart = "25200" //Day 1 at 0:0\r\n}\r\n'


@pytest.mark.parametrize("text", [LEVEL, MISSIONS])
def test_remove_and_add_back_is_identical(text):
    for i in range(len(list(Document.parse(text).walk()))):
        doc = Document.parse(text)
        b = list(doc.walk())[i]
        parent = doc.parent(b)
        sibs = parent.children if parent else doc.blocks
        at = next(k for k, s in enumerate(sibs) if s is b)
        spec = le.spec_of(b)
        doc.remove(b)
        cls, _, name = (b.cls + " " + b.name).partition(" ")
        tup = le._tuple_of(f"{b.cls} {b.name}".strip(), spec)
        doc.add(parent, *tup[:4], index=at, values=tup[4])
        assert doc.to_bytes() == text.encode(), f"block {i}"


def test_edits_apply_diff_reverse():
    text = MISSIONS
    e = le.from_json(json.dumps({
        "set": {"cMissionDefinition Zeds/cMissionLevelReady Ready/cMissionZombieFactory x2009":
                {"Amount0": "80", "Type1": "zombie_fat", "Amount1": "5"}},
        "add": {"cMissionDefinition Zeds/cMissionLevelReady Ready/cMissionSpawnZombie Mine":
                {"ZombieType": "zombie_fat", "SpawnPoint": "1,2,3", "Rotation": "1.5"}},
        "remove": ["cMissionDefinition Other"]}))
    doc = Document.parse(text)
    le.apply(doc, e)
    out = doc.to_bytes().decode()
    assert "cMissionDefinition Other" not in out
    assert '\t\tcMissionSpawnZombie Mine\r\n\t\t{\r\n\t\t\tRotation = "1.5"\r\n' in out
    assert '\t\t\tAmount0 = "80"\r\n\t\t\tAmount1 = "5"\r\n' in out
    back = le.diff(Document.parse(out), Document.parse(text))
    d2 = Document.parse(out)
    le.apply(d2, back)
    assert d2.to_bytes() == text.encode()
    # the diff of the edit is the edit
    again = le.diff(Document.parse(text), Document.parse(out))
    assert again.remove == e.remove and set(again.add) == set(e.add)


def test_apply_names_every_missing_path():
    e = le.Edits(set={"cItemPlacement Nope": {"Location": "0,0,0"}}, remove=["cX Y"])
    with pytest.raises(FormatError) as ex:
        le.apply(Document.parse(LEVEL), e)
    assert "cItemPlacement Nope" in str(ex.value) and "cX Y" in str(ex.value)


def test_bad_json_is_explained():
    with pytest.raises(FormatError, match="text in quotes"):
        le.from_json('{"set": {"cItemPlacement A": {"Location": 3}}}')
    with pytest.raises(FormatError, match="unknown part"):
        le.from_json('{"move": {}}')


def test_merge_conflicts_and_priority():
    a = le.Layer("a", 0, le.Edits(set={"cItemPlacement Shampoo": {"Location": "1,1,1"}}))
    b = le.Layer("b", 0, le.Edits(set={"cItemPlacement Shampoo": {"Location": "2,2,2"}}))
    c = le.Layer("c", 5, le.Edits(set={"cItemPlacement Shampoo": {"Location": "3,3,3"}}))
    d = le.Layer("d", 0, le.Edits(set={"cItemPlacement Scissors": {"Location": "4,4,4"}}))
    assert le.merge([a, b])[1]                         # same key, same priority
    shadowed, problems = le.merge([a, c, d])
    assert not problems and shadowed == [("cItemPlacement Shampoo Location", "a", "c")]
    out, _ = le.apply_all(LEVEL.encode(), [c, a, d])
    assert b'"3,3,3"' in out and b'"4,4,4"' in out and b'"1,1,1"' not in out
    r = le.Layer("r", 0, le.Edits(remove=["cItemPlacement Shampoo"]))
    assert le.merge([a, r])[1]                          # one changes what another removes


# ---- the build ------------------------------------------------------------------------

@pytest.fixture
def game(tmp_path, monkeypatch):
    """A synthetic game with datafile.big holding a level file and missions.txt
    (compressed), laid out like a recomp with a game_patched copy that changed
    missions.txt (like the CZ recomp's co-op edits)."""
    items = ('cWeaponItem Scissors\r\n{\r\n\tDisplayName = "1"\r\n}\r\n\r\n'
             'cWeaponItem Shampoo\r\n{\r\n\tDisplayName = "2"\r\n}\r\n\r\n'
             'cWeaponItem Katana\r\n{\r\n\tDisplayName = "3"\r\n}\r\n\r\n')
    files = [("prologue.txt", LEVEL.encode(), LZX), ("missions.txt", MISSIONS.encode(), LZX),
             ("items.txt", items.encode()),
             ("waypoint_prologue.txt", b"cWaypoint W\r\n{\r\n}\r\n")]
    root = tmp_path / "assets" / "game"
    (root / "data").mkdir(parents=True)
    (root / "data" / "datafile.big").write_bytes(make_archive(*files).to_bytes())
    (root / "data" / "models").mkdir()
    zeds = make_archive(("zombie_skinny.big", b"z"), ("zombie_fat.big", b"z"))
    (root / "data" / "models" / "zombies.big").write_bytes(zeds.to_bytes())
    patched = tmp_path / "assets" / "game_patched"
    (patched / "data").mkdir(parents=True)
    coop = MISSIONS.replace('Duration = "5"', 'Duration = "6"')   # the "recomp's" change
    files[1] = ("missions.txt", coop.encode(), LZX)
    (patched / "data" / "datafile.big").write_bytes(make_archive(*files).to_bytes())
    monkeypatch.setenv("DR2_CZ_DATA", str(root))
    return root


def edits_mod(tmp_path, name, file, edits, priority=0):
    root = create(tmp_path / name, name)
    if priority:
        t = (root / "mod.toml").read_text().replace("priority = 0", f"priority = {priority}")
        (root / "mod.toml").write_text(t)
    dest = root / "replace" / "data" / "datafile.big" / f"{file}.edits.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(edits))
    return Mod.load(root)


def test_build_merges_mods_over_the_recomp_copy(game, tmp_path):
    from dr2kit.container.vpath import AssetTree
    tree = AssetTree(game)
    path = "cMissionDefinition Zeds/cMissionLevelReady Ready/cMissionZombieFactory x2009"
    m1 = edits_mod(tmp_path, "more", "missions.txt", {"set": {path: {"Amount0": "80"}}})
    m2 = edits_mod(tmp_path, "move", "prologue.txt",
                   {"set": {"cItemPlacement Shampoo": {"Location": "0,3.4,0"}},
                    "add": {"cItemPlacement MyKatana": {"ItemName": "Katana",
                                                       "Location": "1,3.4,1",
                                                       "Rotation": "0,0,0,1"}}})
    m3 = edits_mod(tmp_path, "type", "missions.txt",
                   {"set": {path: {"Type1": "zombie_fat", "Amount1": "4"}}})
    base = game.parent / "game_patched"
    res = mbuild.build([m1, m2, m3], "cz", tree, tmp_path / "out", [base])
    built = AssetTree(tmp_path / "out")
    missions = built.resolve("data/datafile.big/missions.txt").data().decode()
    assert 'Amount0 = "80"' in missions and 'Type1 = "zombie_fat"' in missions
    assert 'Duration = "6"' in missions                  # the recomp's change is kept
    level = built.resolve("data/datafile.big/prologue.txt").data().decode()
    assert "cItemPlacement MyKatana" in level and '"0,3.4,0"' in level
    arc = built.open_archive("data/datafile.big")
    assert all(e.compression == LZX for e in arc.entries if e.name in ("missions.txt", "prologue.txt"))
    assert res.base_used


def test_build_refuses_bad_edits(game, tmp_path):
    from dr2kit.container.vpath import AssetTree
    m = edits_mod(tmp_path, "bad", "prologue.txt",
                  {"set": {"cItemPlacement Nope": {"Location": "0,0,0"}},
                   "add": {"cItemPlacement New": {"ItemName": "NoSuchItem",
                                                  "Location": "0,0,0"}}})
    with pytest.raises(ModError) as ex:
        mbuild.plan_mods([m], "cz", AssetTree(game))
    assert "cItemPlacement Nope" in str(ex.value)
    m = edits_mod(tmp_path, "bad2", "prologue.txt",
                  {"add": {"cItemPlacement New": {"ItemName": "NoSuchItem",
                                                  "Location": "0,0,0",
                                                  "Rotation": "0,0,0,0"}}})
    with pytest.raises(ModError) as ex:
        mbuild.plan_mods([m], "cz", AssetTree(game))
    assert "NoSuchItem" in str(ex.value) and "all zeros" in str(ex.value)


def test_same_key_same_priority_is_a_conflict(game, tmp_path):
    from dr2kit.container.vpath import AssetTree
    a = edits_mod(tmp_path, "a", "prologue.txt",
                  {"set": {"cItemPlacement Shampoo": {"Location": "1,1,1"}}})
    b = edits_mod(tmp_path, "b", "prologue.txt",
                  {"set": {"cItemPlacement Shampoo": {"Location": "2,2,2"}}})
    with pytest.raises(ModError, match="same priority"):
        mbuild.plan_mods([a, b], "cz", AssetTree(game))
    c = edits_mod(tmp_path, "c", "prologue.txt",
                  {"set": {"cItemPlacement Shampoo": {"Location": "3,3,3"}}}, priority=2)
    plan = mbuild.plan_mods([a, c], "cz", AssetTree(game))
    assert plan.shadowed and plan.shadowed[0][1:] == ("a", "c")


def test_unknown_zombie_type_is_refused(game, tmp_path):
    from dr2kit.container.vpath import AssetTree
    path = "cMissionDefinition Zeds/cMissionLevelReady Ready"
    m = edits_mod(tmp_path, "z", "missions.txt",
                  {"add": {f"{path}/cMissionSpawnZombie One":
                           {"ZombieType": "zombie_dragon", "SpawnPoint": "1,2,3",
                            "SpawnWithItem": "Katana"}}})
    with pytest.raises(ModError, match="zombie_dragon"):
        mbuild.plan_mods([m], "cz", AssetTree(game))


def test_blocks_inside_game_missions_are_refused_own_missions_allowed(game, tmp_path):
    """In game (CZ, 2026-10-11): a block added inside one of the game's missions breaks
    saves and stalls a new game; a mission of the mod's own is fine."""
    from dr2kit.container.vpath import AssetTree
    inside = "cMissionDefinition Zeds/cMissionLevelReady Ready/cMissionSpawnZombie One"
    spawn = {"ZombieType": "zombie_fat", "SpawnPoint": "1,2,3", "NumberOfZombies": "1"}
    m = edits_mod(tmp_path, "inside", "missions.txt", {"add": {inside: spawn}})
    with pytest.raises(ModError, match="can't load saves"):
        mbuild.plan_mods([m], "cz", AssetTree(game))
    own = {"cMissionDefinition MyZombies": {
        "Duration": "100", "cMissionLevelReady MyReady": {
            "LevelName": "LEVEL_PROLOGUE", "cMissionSpawnZombie One": spawn}}}
    m = edits_mod(tmp_path, "own", "missions.txt", {"add": own})
    plan = mbuild.plan_mods([m], "cz", AssetTree(game))
    assert plan.planned and not any("can't load saves" in n for n in plan.notes)
    # a second mod adding into the first mod's mission is not inside a game mission
    m2 = edits_mod(tmp_path, "more", "missions.txt", {"add": {
        "cMissionDefinition MyZombies/cMissionLevelReady MyReady/cMissionSpawnZombie Two":
            spawn}}, priority=1)
    assert mbuild.plan_mods([m, m2], "cz", AssetTree(game)).planned


def test_zombie_editing_keeps_the_games_missions_whole(game, tmp_path):
    """Phase 11 step 3 (studio.maps_edit): the game's zombies change by value only, new
    ones go into the mod's own mission (cloned from the level's main zombie mission),
    and the build accepts the result."""
    from dr2kit.container.vpath import AssetTree
    from dr2kit.studio.maps_edit import LevelEditor
    mod = create(tmp_path / "zeds", "zeds")
    ed = LevelEditor(AssetTree(game), mod)
    z = ed.zombies("prologue")
    crowd = z["crowds"][0]
    assert crowd["area"] == "street" and crowd["amounts"] == {"zombie_skinny": 40}
    ed.crowd_amounts(crowd["path"], [("zombie_fat", 12), ("zombie_skinny", 3)])
    new = ed.add_zombie("prologue", "zombie_fat", (1, 2, 3), 0.5, 4)
    assert new.startswith("cMissionDefinition zeds_Zombies/") and ed.is_own(new)
    singles = [s for s in ed.zombies("prologue")["zombie_spawns"] if s["kind"] == "single"]
    assert [s["path"] for s in singles] == [new]
    ed.zombie_move(new, (5, 2, 5), 1.0)
    e = le.from_json(ed.session("missions.txt").save().read_text())
    assert e.set[crowd["path"]] == {"Amount0": "12", "Type0": "zombie_fat",
                                    "Amount1": "3", "Type1": "zombie_skinny"}
    own = e.add["cMissionDefinition zeds_Zombies"]
    assert own["Duration"] == "10"                       # Zeds' keys (the main mission)
    ready = own["cMissionLevelReady zeds_prologue"]
    assert ready["cMissionSpawnZombie Zombie1"]["SpawnPoint"] == "5.000,2.000,5.000"
    assert mbuild.plan_mods([Mod.load(mod)], "cz", AssetTree(game)).planned
    ed.remove_zombie(new)                                # the mod's own: removed
    assert all(s["kind"] != "single" for s in ed.zombies("prologue")["zombie_spawns"])


def test_prefabs_move_together_and_own_prefabs(game, tmp_path):
    """Phase 11 step 5 (catalog.prefabs): a clone keeps its parts together (positions
    near the anchor move with it, far ones and the trigger's own corners don't), turns its
    facings, gets a new name; own prefabs are saved and placed again."""
    import math
    from dr2kit.catalog import prefabs as pf
    from dr2kit.container.vpath import AssetTree
    from dr2kit.studio.maps_edit import LevelEditor
    out = pf.moved({"Location": "100,1,100", "ActionPoint": "100,0,101", "Vertex1": "-1,0,1",
                    "Vertex2": "101,0,102", "Far": "500,0,500", "ActionActorRotation": "0.5",
                    "Rotation": "0,0,0,1"}, (100, 0, 101), (0, 0, 0), 90)
    assert out["ActionPoint"] == "0.000,0.000,0.000"
    assert out["Location"] == "-1.000,1.000,0.000"           # 1 m back, turned 90°
    assert out["Vertex2"] == "1.000,0.000,-1.000"            # a corner in world space
    assert out["Vertex1"] == "-1,0,1" and out["Far"] == "500,0,500"
    assert out["ActionActorRotation"] == f"{0.5 + math.pi / 2:.3f}"
    assert out["Rotation"] == "0.000,0.707,0.000,0.707"
    toml = tmp_path / "p.toml"
    toml.write_text('[[prefab]]\nid = "bench"\nname = "Bench"\ngroup = "Stations"\n'
                    'file = "level"\nchecked = "yes"\n'
                    'source.cz = ["prologue.txt", "cItemPlacement Scissors"]\n')
    (p,) = pf.load(toml)
    ed = LevelEditor(AssetTree(game), create(tmp_path / "pm", "pm"))
    names, states = pf.place(ed, p, "cz", "prologue", (1, 2, 3))
    assert names == ["bench_Scissors"] and states[0].position == (1.0, 2.0, 3.0)
    assert states[0].new_model
    b = ed.placement("prologue.txt", names[0])
    f = pf.save_own(tmp_path / "own" / "My scissors", "My scissors", "level",
                    [{"cls": b.cls, "name": "MyScissors",
                      "props": {k.key: k.value for k in b.props}}], (1, 2, 3))
    (own,) = pf.load_own(tmp_path / "own")
    assert own.name == "My scissors" and own.path == f
    names, _ = pf.place(ed, own, "cz", "prologue", (5, 2, 3))
    assert ed.placement("prologue.txt", names[0]).get("Location") == "5.000,2.000,3.000"
    names, _ = pf.place(ed, own, "cz", "prologue", (6, 2, 3))     # a second one: new name
    assert names == ["MyScissors_1"]


def test_shipped_prefabs_are_complete():
    """Every shipped prefab names its file kind, a source for each game it has, and an
    item swap only with a source."""
    from dr2kit.catalog import prefabs as pf
    ps = pf.load()
    assert {p.id for p in ps} >= {"save_point", "workbench", "door_to_level", "spawn_point",
                                 "wall"}
    for p in ps:
        assert p.file in ("level", "waypoint") and p.name and p.group
        assert set(p.item) <= set(p.source)
        for g, (f, path) in p.source.items():
            assert f.endswith(".txt") and " " in path


def test_new_item_and_added_entries(game, tmp_path):
    """Phase 11 (own models): a new item from a template (its pack renamed, its items.txt
    block), added to streamedassets.big as a NEW entry: in name order, compressed like its
    neighbours, declaring their alignment (flags: the game hangs on 0, CZ 2026-10-11)."""
    from dr2kit.container.big import LZX, BigArchive
    from dr2kit.container.vpath import AssetTree
    from dr2kit.mods.newitem import new_item
    from dr2kit.studio.maps_edit import LevelEditor
    inner = make_archive(("Scissors.big", b"scene" * 10), ("Scissors.tex", b"tex" * 10),
                         ("Scissors_LOD.tex", b"lod"), ("w_scissors.bct", b"icon"))
    sa = make_archive(("Katana.big", b"k" * 50, LZX), ("Scissors.big", inner.to_bytes(), LZX),
                      ("Zebra.big", b"z" * 50, LZX))
    for e in sa.entries:
        e.flags = e.alignment = 2048
    (game / "data" / "streamedassets.big").write_bytes(sa.to_bytes())
    mod = create(tmp_path / "ni", "ni")
    new_item(AssetTree(game), mod, "MyScissors", "Scissors")
    recipe = mod / "add" / "data" / "streamedassets.big" / "MyScissors.big.copy.json"
    assert json.loads(recipe.read_text())["copy"] == "data/streamedassets.big/Scissors.big"
    assert not any(p.is_file() and p.suffix == ".big" for p in (mod / "add").rglob("*"))
    ed = LevelEditor(AssetTree(game), mod, game="cz")
    assert ed.models.resolve("MyScissors").endswith("MyScissors.big/MyScissors.big")
    ed.add("prologue.txt", "MyScissors", (1, 2, 3))
    res = mbuild.build([Mod.load(mod)], "cz", AssetTree(game), tmp_path / "out")
    arc = AssetTree(tmp_path / "out").open_archive("data/streamedassets.big")
    names = [e.name for e in arc.entries]
    assert names == ["Katana.big", "MyScissors.big", "Scissors.big", "Zebra.big"]
    new = arc.entries[1]
    assert new.compression == LZX and new.flags == 2048 and new.data_offset % 2048 == 0
    assert [e.name for e in BigArchive.parse(new.data()).entries] == [
        "MyScissors.big", "MyScissors.tex", "MyScissors_LOD.tex", "w_scissors.bct"]
    assert any(p.override.kind == "add" for p in res.overrides)
    with pytest.raises(Exception, match="already an item"):
        new_item(AssetTree(game), mod, "Scissors", "Scissors")

"""Level slots and a whole level of the other game (phase 15 maps: `dr2kit.convert.crossgame`
level slots, `dr2kit.mods.importlevel`). The slot tests read only the toolkit's own
`crossgame.toml`; the import tests use the real games and SKIP, saying why, when a game
isn't installed. Nothing of the games is copied into the repository."""

import json

import pytest

from dr2kit.container.vpath import AssetTree
from dr2kit.convert import crossgame
from dr2kit.errors import Dr2Error


def test_level_names_are_not_always_the_script_name():
    s = crossgame.level_slot("cz", "lighting")
    assert s.level == "LEVEL_LIGHTINGTEST" and s.name == "LIGHTINGTEST"
    assert crossgame.level_slot("cz", "LEVEL_MADHATTER").script == "gs_hattrick"
    assert crossgame.level_slot("cz", "x_prologue").zonelist == "x_prologue/zonelist.big"
    with pytest.raises(Dr2Error):
        crossgame.level_slot("cz", "testlevel")          # 16 slots share it: ambiguous


def test_which_empty_slots_take_a_level():
    # measured 2026-10-13: Default / MainMenu need no file, Prologue ships; FoodBarn stalls
    assert crossgame.level_slot("cz", "x_prologue").loads
    assert crossgame.level_slot("cz", "main_menu").loads
    assert crossgame.level_slot("cz", "prologue_bowling").loads
    fb = crossgame.level_slot("cz", "food_barn")
    assert not fb.loads and "FoodBarn.txt" in fb.why_not
    assert not crossgame.level_slot("cz", "prologue").loads       # the game's own
    assert len(crossgame.free_level_slots("cz")) == 42
    assert [s.level for s in crossgame.free_level_slots("cw")] == ["LEVEL_W_MALL"]


def test_free_slots_leave_out_taken_scripts_and_zone_lists():
    first = crossgame.free_level_slots("cz")[0]
    rest = crossgame.free_level_slots("cz", [first.level])
    assert first not in rest and len(rest) == 41
    z = crossgame.free_level_slots("cz", ["LEVEL_Z_FRANK"])     # testlevel.txt is shared
    assert not any(s.script == "testlevel" for s in z)
    assert crossgame.free_level_slots("cw", ["w_mall"]) == []


@pytest.fixture
def both(game_root):
    return {g: AssetTree(game_root(g)) for g in ("cz", "cw")}


@pytest.mark.gamedata
def test_storage_pens_plans_into_case_zero(both):
    from dr2kit.mods import importlevel
    p = importlevel.plan(both["cw"], both["cz"], "cw", "cz", "storage_pens")
    assert p.unresolved == []
    assert p.slot.loads and p.folder == "storage_pens" and len(p.zones) == 10
    assert f"data/models/environment/{p.slot.zonelist}.copy.json" in p.recipes
    zone = p.recipes["data/models/environment/storage_pens/storage_pens_z00.big.copy.json"]
    assert zone["from"] == "cw" and zone["shaders"]
    assert p.arrive == "Start" and p.door["props"]["Level"] == p.slot.level
    assert p.mission is not None
    props = dict(p.mission[2])
    assert props["LevelRequiredToStartName"] == p.slot.name
    # doors to Case West's other levels lead back to the street's safehouse exit
    script = p.recipes[f"data/datafile.big/{p.slot.script}.txt.copy.json"]
    sets = script["edits"]["set"]
    door = next(v for k, v in sets.items() if k.endswith("cDoorPlacement LowerLiving1"))
    assert door["Level"] == "PROLOGUE" and door["LevelSpawnPoint"] == "AlternateExit"
    assert door.get("KeyItem", "x") is None                       # the key is taken off
    # no armed enemy left in a crowd (a crowd spawning one crashed Case Zero)
    armed = {"mercenary", "mercenary_pheno", "mercenary_tk"} | {
        zp.slot for zp in p.zombie_plans if zp.armed}
    for c in p.mission[3][0][3]:
        if c[0] == "cMissionZombieFactory":
            assert not {v for k, v in c[2] if k.startswith("Type")} & armed


@pytest.mark.gamedata
def test_a_slot_the_mod_uses_is_not_offered_again(both, tmp_path):
    from dr2kit.mods import importlevel
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources" / "levels.json").write_text(json.dumps(
        {"LEVEL_PROLOGUE_BOWLING": {"level": "LEVEL_STORAGE_PENS"}}))
    taken = tuple(importlevel.mod_levels(tmp_path))
    p = importlevel.plan(both["cw"], both["cz"], "cw", "cz", "storage_pens",
                         taken_slots=taken)
    assert p.slot.level != "LEVEL_PROLOGUE_BOWLING"
    with pytest.raises(Dr2Error, match="already puts a level"):
        importlevel.plan(both["cw"], both["cz"], "cw", "cz", "living_research",
                         slot="prologue_bowling", taken_slots=taken)

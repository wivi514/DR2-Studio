"""The other game's zombie types (phase 15 step 4: `dr2kit.mods.importzombie`) on the real
games. Each test SKIPS, saying why, when a game isn't installed. Nothing of the games is
copied into the repository: mods are written to a temporary folder."""

import json

import pytest

from dr2kit.container.vpath import AssetTree
from dr2kit.errors import Dr2Error
from dr2kit.mods import importzombie as iz
from dr2kit.mods.build import plan_mods
from dr2kit.mods.manifest import Mod, create

pytestmark = pytest.mark.gamedata


@pytest.fixture
def both(game_root):
    return {g: AssetTree(game_root(g)) for g in ("cz", "cw")}


def test_every_case_west_type_has_a_slot_in_case_zero(both):
    r = iz.census(both["cw"], both["cz"], "cw", "cz")
    assert r["refused"] == [] and r["planned"] == r["types"] == 7
    assert r["slots"]["zombie_gas"] == "zombie_gas"              # its own name, empty in CZ
    assert r["slots"]["zombie_fat_female"] == "zombie_fat_female"
    assert len(set(r["slots"].values())) == 7                     # one slot each
    assert not set(r["slots"].values()) & iz.shipped_types(both["cz"])


def test_case_zero_into_case_west_waits_for_the_recomp(both):
    with pytest.raises(Dr2Error, match="TODO.md #1"):
        iz.plan(both["cz"], both["cw"], "cz", "cw", "zombie_cop")


def test_security_brings_its_behaviour_and_load_set(both):
    p = iz.plan(both["cw"], both["cz"], "cw", "cz", "security_light", levels=("prologue",))
    assert p.slot not in ("zombie_fat_female", "zombie_gas")      # left for CW's own
    assert [b[1] for b in p.behaviours] == ["EnemyRanged"]
    assert p.cost == 3904 and p.load_sets["LEVEL_PROLOGUE"] > iz.budget(both["cz"])
    assert p.warnings                                             # over the street's budget
    recipe = p.recipes[f"data/models/zombies.big/{p.slot}.big.copy.json"]
    assert recipe["from"] == "cw" and recipe["rename"] == {"security_light": p.slot}


def test_import_writes_a_mod_that_builds_the_slot(both, tmp_path):
    root = create(tmp_path / "zomb", "zomb")
    p, _ = iz.import_zombie(root, "zombie_gas", "cw", "cz", both["cz"], levels=("prologue",))
    m = Mod.load(root)
    assert m.games == ("cz",) and set(m.requires["games"]) == {"cz", "cw"}
    plan = plan_mods([m], "cz", both["cz"])
    targets = {x.vpath.lower() for x in plan.planned}
    assert "data/models/zombies.big/zombie_gas.big" in targets
    assert "data/datafile/persistent_filecache.big/zombiesets.txt" in targets
    cache = json.loads((root / "replace/data/datafile/persistent_filecache.big/"
                        "zombiesets.txt.edits.json").read_text("utf-8"))
    assert cache["file"].endswith("persistent_filecache.big/zombiesets.txt")
    assert iz.mod_slots(root) == {"zombie_gas": "zombie_gas"}
    with pytest.raises(Dr2Error):                                # the slot is the mod's now
        iz.import_zombie(root, "security_light", "cw", "cz", both["cz"], slot="zombie_gas")


def test_built_model_takes_the_slots_name(both, tmp_path):
    from dr2kit.container.big import BigArchive
    from dr2kit.mods.newitem import build_copy
    p = iz.plan(both["cw"], both["cz"], "cw", "cz", "security_light", slot="zombie_dealer")
    data = build_copy(both["cz"], p.recipes["data/models/zombies.big/zombie_dealer.big.copy.json"],
                      tmp_path)
    names = [e.name.lower() for e in BigArchive.parse(data).entries]
    assert "zombie_dealer_2.big" in names and "zombie_dealer_4.tex" in names
    assert not any("security_light" in n for n in names)


def test_build_knows_a_filled_slot(both, tmp_path):
    """A crowd retyped to a slot the mod fills passes the build's level check (the slot's
    model is an add/ of zombies.big, not in the game yet)."""
    from dr2kit.mods.build import build
    from dr2kit.mods.leveledit import TextEdits
    root = create(tmp_path / "zomb", "zomb")
    p, _ = iz.import_zombie(root, "security_heavy", "cw", "cz", both["cz"])
    ed = TextEdits(root, "missions.txt", both["cz"])
    blk = next(b for b in ed.doc.walk() if b.cls == "cMissionZombieFactory")
    ed.doc.set(blk, "Type0", p.slot)
    ed.save()
    res = build([Mod.load(root)], "cz", both["cz"], tmp_path / "out")
    assert any(f.endswith("zombies.big") for f in map(str, res.files))


def test_gas_zombies_bring_their_voices(both):
    """Case Zero's sound list names the gas zombies' voices but ships none of their banks."""
    banks = [b for b, _ in iz.voice_banks(both["cw"], both["cz"])]
    assert "data/streamedassets.big/fx_gzombieakalem2.big" in banks
    assert not any("fx_zombieakalema" in b for b in banks)       # Case Zero has these

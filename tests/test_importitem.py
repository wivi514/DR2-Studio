"""The other game's items (phase 15: `dr2kit.mods.importitem`, `dr2kit.convert.shadercarry`)
on the real games. Each test SKIPS, saying why, when a game isn't installed. Nothing of the
games is copied into the repository: mods are written to a temporary folder."""

import json

import pytest

from dr2kit.container.vpath import AssetTree
from dr2kit.convert import shadercarry
from dr2kit.formats import shaderbank as sb
from dr2kit.mods import importitem
from dr2kit.mods.build import plan_mods
from dr2kit.mods.manifest import Mod, create

pytestmark = pytest.mark.gamedata


@pytest.fixture
def both(game_root):
    return {g: AssetTree(game_root(g)) for g in ("cz", "cw")}


def test_laser_sword_plans_into_case_zero(both):
    p = importitem.plan(both["cw"], both["cz"], "cw", "cz", "LaserLightSword")
    assert p.unresolved == []
    brought = " ".join(r.what for r in p.log if r.how == "brought")
    assert "anm_Laser_Sword" in brought and "fx_laserlight" in brought
    assert "combo_lightsaber" in brought and "CW shaders" in brought
    assert any(k.endswith(".sdo.copy.json") for k in p.recipes)
    assert len(p.strings) == 6                    # the name and the combo card's texts


def test_converted_pack_names_only_brought_shaders(both):
    data = both["cw"].resolve("data/streamedassets.big/combo_lightsaber.big").data()
    sd, ps = shadercarry.used_shaders(data)
    c = shadercarry.plan(both["cw"], both["cz"], "cw", "cz", sd, ps)
    out = shadercarry.convert_pack(data, c.to_json())
    sd2, ps2 = shadercarry.used_shaders(out)
    assert sd2 == {c.sd.get(h, h) for h in sd} and ps2 == {c.ps.get(h, h) for h in ps}


def test_brought_description_and_parameters(both):
    c = shadercarry.plan(both["cw"], both["cz"], "cw", "cz", {0x48C6E780})   # ZombieGlow
    new = c.sd[0x48C6E780]
    raw = shadercarry.build_entry(both["cw"], both["cz"], {
        "kind": "sd", "old": "48c6e780", "new": f"{new:08x}",
        "rename": {f"{o:08x}": f"{n:08x}" for o, n in {**c.vs, **c.ps}.items()}})
    d = sb.Description.parse(raw)
    assert d.hash == new and d.name == "ZombieGlow"
    vs, ps = d.programs()
    assert ps <= set(c.ps.values()) | {p for p in ps if p not in c.ps}
    old_pd = next(iter(c.ps))
    pdo = sb.ParamFile.parse_pdo(shadercarry.build_entry(both["cw"], both["cz"], {
        "kind": "pd", "old": f"{old_pd:08x}", "new": f"{c.ps[old_pd]:08x}"}))
    reg = sb.registry(both["cz"], "pd")
    for prm in pdo.params:                        # the target's numbers, or a free one
        assert prm.number == reg.get(prm.name, prm.number)


def test_import_writes_a_mod_that_plans(both, tmp_path):
    root = create(tmp_path / "laser", "laser")
    p, files = importitem.import_item(root, "LaserLightSword", "cw", "cz", both["cz"])
    m = Mod.load(root)
    assert m.games == ("cz",) and set(m.requires["games"]) == {"cz", "cw"}
    plan = plan_mods([m], "cz", both["cz"])
    kinds = {x.override.kind for x in plan.planned}
    assert {"add", "edits", "strings"} <= kinds
    copy = json.loads((root / "replace/data/frontend/str_fr.bcs.json").read_text("utf-8"))
    assert len(copy["copy"]) == 6 and not copy["strings"]


def test_every_item_resolves_both_ways(both):
    for src, dst in (("cw", "cz"), ("cz", "cw")):
        r = importitem.census(both[src], both[dst], src, dst)
        assert r["refused"] == [] and r["unresolved"] == [], (src, dst, r["unresolved"][:5])
        assert r["planned"] == r["items"]


def test_case_west_scenes_get_case_zeros_hierarchy(both):
    """Case Zero's program hangs placing an item whose scene lacks _BONEHIERARCHY_ (U1,
    2026-10-12): a Case West pack built for Case Zero gets it, right after the nodes, the
    same pairs as the node records; for Case West nothing changes."""
    from dr2kit.container.big import BigArchive
    from dr2kit.convert.crossgame import fit_scenes
    from dr2kit.formats.scene import Scene
    data = both["cw"].resolve("data/streamedassets.big/combo_lightsaber.big").data()
    assert fit_scenes(data, "cw") is data
    scene = BigArchive.parse(fit_scenes(data, "cz")).get("combo_lightsaber.big").data()
    arc = BigArchive.parse(scene)
    names = [e.name for e in arc.entries]
    at = names.index("_BONEHIERARCHY_")
    assert all(e.size == 52 for e in arc.entries[:at]) and arc.entries[at + 1].size != 52
    s = Scene.parse(scene)
    assert sorted(s.hierarchy) == sorted((n.index, n.parent) for n in s.skeleton.nodes)


def test_hierarchy_order_is_case_zeros(both):
    """`Skeleton.hierarchy_pairs` writes what Case Zero's own tools wrote (Broadsword)."""
    from dr2kit.formats.scene import Scene
    s = Scene.parse(both["cz"].resolve(
        "data/streamedassets.big/broadsword.big/broadsword.big").data())
    assert s.skeleton.hierarchy_pairs() == [tuple(p) for p in s.hierarchy]


def test_missing_effects_brought_into_free_slots(both, tmp_path):
    """Case West's Impact Hammer uses two effects Case Zero lacks: each gets a free slot of
    the table (a recipe reading Case West, in Case Zero's layout at build time), the
    particle picture Case Zero lacks comes too, and a second import reuses the slots."""
    root = create(tmp_path / "hammer", "hammer")
    p, _ = importitem.import_item(root, "ImpactHammer", "cw", "cz", both["cz"])
    assert set(p.effects) == {"impact_wpn_bs_1", "groundblast_wpn_dbs_1"}
    free = {n for n, _ in importitem._game("cz", both["cz"]).free_slots}
    assert set(p.effects.values()) <= free
    assert "data/models/effects.tex/fire_ring.copy.json" in p.recipes
    brought, used = importitem.mod_effects(root)
    assert brought == p.effects and used == set(p.effects.values())
    again = importitem.plan(both["cw"], both["cz"], "cw", "cz", "ImpactHammer",
                            taken_effects=brought, used_slots=used)
    assert again.effects == p.effects


def test_audio_type_keeps_the_targets_bits(both):
    """Case West's Impact Hammer has PropAudioType bit 17, which only Case West's items use;
    placed in Case Zero with it, the load faulted (key bisect, 2026-10-13)."""
    p = importitem.plan(both["cw"], both["cz"], "cw", "cz", "ImpactHammer")
    props = dict(p.blocks[0][2])
    assert props["PropAudioType"] == "1024"
    assert any(r.how == "renumbered" and "audio type 132096 -> 1024" in r.what for r in p.log)
    assert "AttachmentItemName" not in props          # it named a block left out

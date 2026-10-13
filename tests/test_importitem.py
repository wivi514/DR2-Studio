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

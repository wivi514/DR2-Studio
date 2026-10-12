"""Phase 13: the weapon wizard, its catalogue, the model fitter, icons and cards."""

from __future__ import annotations

import json

import pytest

np = pytest.importorskip("numpy")

from dr2kit.catalog import weapons  # noqa: E402
from dr2kit.catalog.sample_sword import sample_sword_glb  # noqa: E402
from dr2kit.convert import icon, render, weapon_fit as wf  # noqa: E402
from dr2kit.errors import Dr2Error  # noqa: E402


# --- the catalogue ----------------------------------------------------------------------

def test_effect_tables():
    cz, cw = weapons.names("cz"), weapons.names("cw")
    assert len(cz) == 371 and len(cw) == 414
    assert cz[:370] == cw[:370]                    # shared, then each game's own
    assert cz[370] == "roadflare_env_c_1" and cw[370] == "groundblast_wpn_dbs_1"
    assert cz[140] == "fireextinguisher_wpn_dc_2"  # PyroEffect 141 of the Fire Extinguisher
    assert weapons.effect_number("cz", "snowtrail_wpn_bs_1") == 215
    assert weapons.effect_number("cz", "215") == 215
    assert weapons.effect_number("cz", "none") == 0
    with pytest.raises(Dr2Error):
        weapons.effect_number("cz", 400)          # CZ has 371
    with pytest.raises(Dr2Error):
        weapons.effect_number("cz", "no_such_effect")


def test_effect_groups_and_reading():
    by = {e.name: e for e in weapons.effects("cw")}
    assert by["snowtrail_wpn_bs_1"].group == "ice"
    assert by["flamingsword_wpn_c_3_unq"].group == "fire"
    assert by["victim_bld_dbm_3"].group == "blood"
    assert by["elecrake_wpn_dbs_3_unq"].group == "electric"
    assert by["tikitorch_wpn_c_2"].loops is True and by["impact_bld_dbs_2"].loops is False
    assert by[weapons.names("cw")[214]].tested       # 215 was checked in game
    assert {g for g, _ in weapons.groups()} >= {e.group for e in by.values()}


def test_effect_usage():
    from dr2kit.formats.levelscript import Document
    doc = Document.parse('cPlayerWeaponItem Rake\r\n{\r\n\tEffectOnVictim0 = "249"\r\n'
                         '\tEffectOnVictim1 = "249"\r\n\tPyroEffect0 = "123"\r\n}\r\n')
    use = weapons.usage(doc)
    assert use[249] == ["Rake (EffectOnVictim)"] and use[123] == ["Rake (PyroEffect)"]


def test_kinds_and_elements():
    ids = [k.id for k in weapons.kinds()]
    assert len(ids) == len(set(ids)) and "sword" in ids
    assert weapons.kind("sword").template("cz") == "Broadsword"
    assert weapons.kind("sword").template("cw") == "Katana"
    assert all(k.source for k in weapons.kinds())
    with pytest.raises(Dr2Error):
        weapons.kind("scythe").template("cz")     # Case West only
    el = weapons.elements()
    assert el["shock"]["keys"] == {"Can_Electrocute": "true"}
    assert el["freeze"]["child"]["keys"]["PropHitZombieEffect"] == "1"
    assert el["fire"]["child"]["keys"]["PropHitZombieEffect"] == "0"
    assert weapons.slots()["held"]["condition"] == 30
    assert weapons.slots()["swinging"]["condition"] == 31


# --- the fitter -------------------------------------------------------------------------

def _frame(axis=(0, 0, 1), side=(1, 0, 0), handle=(0, 0, -0.3), length=1.2):
    axis, side = np.array(axis, float), np.array(side, float)
    return wf.Frame(np.array(handle, float), axis, side, np.cross(axis, side), length)


def test_sample_sword_reads():
    g = wf.read_glb(sample_sword_glb())
    assert len(g.images) == 3                       # steel (a picture), gold, leather
    assert g.images[0].shape[:2] == (256, 64)
    assert len(g.triangles) == 4 * 12 and set(g.material.tolist()) == {0, 1, 2}
    span = g.positions.max(axis=0) - g.positions.min(axis=0)
    assert abs(span[1] - 1.05) < 1e-6               # upright, 1.05 m


def test_fit_lays_the_model_on_the_line():
    g = wf.read_glb(sample_sword_glb())
    fr = _frame()
    out = wf.fit(g, fr)                               # auto: the origin is at the grip
    t = (out.positions - fr.handle) @ fr.axis
    assert abs(t.min()) < 1e-9 and abs(t.max() - fr.length) < 1e-9
    # the pommel (gold, near the origin) is at the handle end, the blade's tip at the other
    tip = out.positions[np.argmax(t)]
    assert abs(tip @ fr.side) < 0.01
    # the flat of the blade lies across the frame's side axis
    blade = out.positions[np.unique(g.triangles[g.material == 0])]
    across = blade - fr.handle
    assert np.ptp(across @ fr.side) > 5 * np.ptp(across @ fr.thin)
    flipped = wf.fit(g, fr, handle="max", length=0.5, slide=0.1)
    t2 = (flipped.positions - fr.handle) @ fr.axis
    assert abs(t2.min() - 0.1) < 1e-9 and abs(t2.max() - 0.6) < 1e-9
    with pytest.raises(Dr2Error):
        wf.fit(g, fr, handle="middle")


def test_atlas_packs_materials():
    g = wf.read_glb(sample_sword_glb())
    notes = []
    img, uv = wf.atlas(g, 128, 128, notes)
    assert img.shape == (128, 128, 4) and uv.shape == g.uvs.shape
    assert (uv >= 0).all() and (uv <= 1).all() and not notes
    # each material's UVs land in its own cell (2 × 2 grid for three materials)
    cells = set()
    for m in range(3):
        v = np.unique(g.triangles[g.material == m])
        c = (uv[v] * 2).astype(int).clip(0, 1)
        assert len({tuple(x) for x in c}) == 1
        cells.add(tuple(c[0]))
    assert len(cells) == 3
    one = wf.Geometry(g.positions, g.normals, g.uvs, g.triangles, np.zeros_like(g.material),
                      g.images)
    img1, uv1 = wf.atlas(one, 64, 32)
    assert img1.shape == (32, 64, 4) and np.array_equal(uv1, g.uvs)


# --- pictures ---------------------------------------------------------------------------

def _parts():
    g = wf.fit(wf.read_glb(sample_sword_glb()), _frame())
    img, uv = wf.atlas(g, 64, 64)
    return [render.Part(g.positions.astype(np.float32), g.triangles.astype(np.int32),
                        g.normals.astype(np.float32), uv.astype(np.float32),
                        img.astype(np.float32) / 255)]


def test_effect_locator_runs_along_the_blade():
    import numpy as np
    from dr2kit.formats.scene import quat_rotate
    frame = wf.Frame(np.array([0, 0, -0.3]), np.array([0.0, 0, 1]), np.array([0.0, 1, 0]),
                     np.array([-1.0, 0, 0]), 1.2, grip=np.array([0.01, 0, -0.11]))
    pos, rot = wf.effect_locator(frame, 0.1)
    assert pos == pytest.approx([0.01, 0, -0.01])
    assert quat_rotate(rot, (0, 1, 0)) == pytest.approx((0, 0, 1), abs=1e-6)  # +y → the tip
    assert sum(v * v for v in rot) == pytest.approx(1.0)


def test_weapon_icon():
    pic = icon.weapon_icon(_parts(), _frame())
    assert pic.shape == (64, 128, 4)
    a = pic[..., 3]
    assert set(np.unique(a)) <= {0, 255} and a.any()           # DXT1: on or off
    ys, xs = np.nonzero(a)
    assert xs.max() - xs.min() > 100                           # the length across
    # handle at the left, higher than the tip at the right
    left = ys[xs < xs.min() + 10].mean()
    right = ys[xs > xs.max() - 10].mean()
    assert left < right
    edge = pic[a > 0]
    assert (edge[..., :3] == icon.OUTLINE).all(axis=1).any()   # the dark outline


def test_card_pictures():
    w, h = icon.portrait_size()
    p = icon.card_portrait(_parts(), _frame(), "freeze")
    assert p.shape == (h, w, 4) and (p[..., 3] == 255).all()
    clear = icon.card_portrait(_parts(), _frame(), glow=False)
    assert (clear[..., 3] == 0).any() and (clear[..., 3] == 255).any()
    cards = [np.full((512, 364, 4), v, np.uint8) for v in (10, 20, 30)]
    empty = icon.card_template(cards)
    assert (empty == 20).all()
    drawing = icon.item_drawing(_parts())
    card = icon.compose_card(empty, p, [drawing, drawing])
    assert card.shape == (512, 364, 4)
    m = icon.window_mask()
    assert not np.array_equal(card[m], empty[m])               # the portrait went in
    assert np.array_equal(card[:10, :, :3], empty[:10, :, :3])  # above the window: unchanged
    x0, y0, x1, y1 = icon.CARD["left"]
    assert (card[y0:y1, x0:x1, :3] < 20).any()                 # black lines
    faded = icon.faded(p)
    assert faded.shape == p.shape and (faded[..., 0] >= faded[..., 2]).all()
    with pytest.raises(Dr2Error):
        icon.compose_card(np.zeros((10, 10, 4), np.uint8))


# --- the wizard on the real games -------------------------------------------------------

@pytest.mark.gamedata
@pytest.mark.parametrize("game", ["cz", "cw"])
def test_make_weapon_builds(game, game_root, tmp_path):
    from dr2kit.container.big import BigArchive
    from dr2kit.container.vpath import AssetTree
    from dr2kit.formats.bcs import StringBank
    from dr2kit.formats.levelscript import Document
    from dr2kit.mods import build as mbuild
    from dr2kit.mods import manifest, newweapon as nw
    tree = AssetTree(game_root(game))
    mod = tmp_path / "mod"
    manifest.create(mod, "wiztest", "Wizard test")
    spec = nw.WeaponSpec(name="TestBlade", kind="sword",
                         names={"en": "Test Blade", "fr": "Lame d'essai"}, model="sample",
                         damage=150, element="freeze",
                         effects={"impact": 181, "held": "snowtrail_wpn_bs_1"},
                         combo=nw.Combo(["BowieKnife", "FireExtinguisher"]),
                         shine="little", effect_start=0.12)
    made = nw.make_weapon(tree, game, mod, spec)
    assert manifest.Mod.load(mod).games == (game,)
    assert nw.weapons_of(mod) == ["TestBlade"]
    assert nw.load_spec(mod, "TestBlade") == spec
    res = mbuild.build([manifest.Mod.load(mod)], game, tree, tmp_path / "out")
    out = AssetTree(tmp_path / "out")
    pack = out.resolve("data/streamedassets.big/TestBlade.big")
    names = {e.name.lower() for e in BigArchive.parse(pack.data(), pack.vpath).entries}
    assert {"testblade.big", "testblade.tex", "w_testblade.bct"} <= names
    doc = Document.parse(out.resolve("data/datafile.big/items.txt").data())
    b = doc.get("cPlayerWeaponItem TestBlade")
    assert b.get("IconFilename") == "w_testblade" and b.get("Can_Freeze") == "true"
    assert b.get("AttackDamage0") == "150" and b.get("EffectOnImpact0") == "181"
    assert b.get("DisplayName") == str(made.string_ids["name"])
    kids = {c.cls: c for c in b.children}
    assert kids["cPropHitZombieInfoItem"].get("PropHitZombieEffect") == "1"
    card = kids["cComboCardItem"]
    assert card.get("Weapon_1") == "BowieKnife" and card.get("IconAsset") == "comboc_testblade"
    assert card.get("CardIndexNumber") == str(made.card_number)
    conds = dict(zip(b.numbered("PropEffectsOnCondition"), b.numbered("PyroEffect")))
    assert conds.get("30") == "215"
    for lang, want in (("en", "Test Blade"), ("fr", "Lame d'essai"), ("it", "Test Blade")):
        bank = StringBank.parse(out.resolve(f"data/frontend/str_{lang}.bcs").data())
        assert bank.strings[made.string_ids["name"]] == want
    assert bank.strings[made.string_ids["card"]] == "TEST BLADE"
    # the effect point (locator 16) along the blade in both copies, and the shine
    import struct
    from dr2kit.formats.scene import Scene
    scene_e = next(e for e in BigArchive.parse(pack.data(), pack.vpath).entries
                   if e.name.lower() == "testblade.big")
    sc = BigArchive.parse(scene_e.data(), "s")
    inner = BigArchive.parse(next(e for e in sc.entries if e.name == "persistent.big").data(),
                             "p")
    want = json.loads((mod / "add/data/streamedassets.big/TestBlade.big.copy.json")
                      .read_text())["locators"]["16"]
    for arc in (sc, inner):
        data = next(e for e in arc.entries if e.name == "LocatorArray").data()
        recs = [struct.unpack_from(">I3f4f", data, i) for i in range(0, len(data), 52)]
        (r16,) = [r for r in recs if r[0] == 16]
        assert r16[1:4] == pytest.approx(want["position"], abs=1e-5)
        assert r16[4:8] == pytest.approx(want["rotation"], abs=1e-5)
    assert [m.params for m in Scene.parse(scene_e.data(), "s").materials if m.slots] == \
        [pytest.approx(nw.SHINES["little"][1])]
    cards = out.resolve("data/frontend/combocards.tex")
    cnames = {e.name for e in BigArchive.parse(cards.data(), cards.vpath).entries}
    assert {"comboc_testblade.bct", "comboc_testblade_no.bct"} <= cnames
    assert not any("TestBlade" in w and "id(s)" not in w for w in res.warnings)
    # run again without the combo: the card and its texts go
    spec.combo = None
    again = nw.make_weapon(tree, game, mod, spec)
    assert again.string_ids == {"name": made.string_ids["name"]}
    assert not (mod / "add/data/frontend").exists()
    en = json.loads((mod / "replace/data/frontend/str_en.bcs.json").read_text("utf-8"))
    assert list(en["strings"]) == [str(made.string_ids["name"])]
    nw.remove_weapon(tree, mod, "TestBlade")
    assert nw.weapons_of(mod) == [] and not (mod / "add").exists()

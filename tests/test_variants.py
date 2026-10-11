"""Variants (phase 9): the game's shape classifier, looks, colour choices, the .glb."""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from dr2kit.convert import gltf
from dr2kit.convert import variants as cv
from dr2kit.errors import Dr2Error
from dr2kit.formats.scene import Scene
from dr2kit.profiles import load_profile

from conftest import make_scene

SKINNY = ["head1_headShape", "chestupper_neck1Shape", "cap_neckchest1Shape", "head2_headShape",
          "chestupper_neck2Shape", "head_eyesShape", "headwear2Shape", "headwear3Shape",
          "chest_shirt1Shape", "larm_shirt1Shape", "chest_shirt2Shape", "pants_pants1Shape",
          "pants_pants2Shape", "lleg_lfoot1Shape", "rleg_rfoot1Shape", "larm_armShape",
          "head_blackShape", "pants_blackShape", "cap_lleghipShape"]


def scene(names, source="data/models/zombies.big/zombie_x.big/zombie_x_2.big"):
    return SimpleNamespace(meshes=[SimpleNamespace(name=n) for n in names], source=source,
                           materials=[])


@pytest.mark.parametrize("game", ["cz", "cw"])
def test_profile_table_matches_the_slots(game):
    """The bits SLOTS and TOGGLES use are the profile's (copied from the executable)."""
    groups = {p.split(",")[0]: int(m, 16) for m, p in load_profile(game).variants["groups"]}
    assert len(load_profile(game).variants["groups"]) == 53
    for slot in cv.SLOTS:
        if slot.key == "tumour":
            assert groups["head1_head_tumour1*"] == slot.bit(1)
            continue
        first = {"head": "head1_*", "headwear": "headwear1*", "shirt": "chest_shirt1*",
                 "pants": "pants_pants1*", "skirt": "skirt_skirt1*", "feet": "lleg_lfoot1*",
                 "tallboots": "lleg_tallboot1*"}[slot.key]
        assert groups[first] == slot.bit(1), slot.key
        if slot.count > 1:
            last = re.sub(r"1", str(slot.count), first, count=1)
            assert groups[last] == slot.bit(slot.count), slot.key
    for t, pattern in (("caps", "cap_*"), ("burnt", "head_black*"), ("gas", "head_gas*"),
                       ("bare_arms", "larm_arm*"), ("glasses", "eyewear_acc*"),
                       ("chest_acc", "chest_acc*"), ("backpack", "chest_acc_bkpc"),
                       ("shirt_tumour", "chest_shirt1_tumour1*")):
        assert groups[pattern] == cv.TOGGLE[t].bit, t
    assert groups["*"] == cv.DEFAULT_BIT


def test_classifier_is_the_games_prefix_rule():
    c = cv.Classifier.for_game("cz")
    assert cv.pattern_matches("head1_*,chestupper_neck1*", "chestupper_neck1Shape")
    assert not cv.pattern_matches("head1_*", "head11")       # '_' needed
    assert cv.pattern_matches("cap_neckchest1", "cap_neckchest1Shape")   # a prefix too
    assert not cv.pattern_matches("Head*", "head1_headShape")            # case-sensitive
    assert c.bits("head1_headShape") == 0x10001                  # head region + head 1
    assert c.bits("headwear2Shape") == 0x4000101                 # as the CZ recomp measured
    assert c.bits("geo_boxShape") == cv.DEFAULT_BIT              # matched nothing else
    assert cv.corrected_name("headwearShape2DeformedDeformed") == "headwear2ShapeDeformedDeformed"
    assert cv.corrected_name("geo_window_Shape1") is None


def test_skinny_like_model_slots_default_and_mask():
    mv = cv.model_variants(scene(SKINNY), "cz")
    assert mv.zombie
    assert mv.slots == {"head": [1, 2], "headwear": [2, 3], "shirt": [1, 2], "pants": [1, 2],
                        "feet": [1]}
    assert mv.toggles == ["caps", "burnt", "bare_arms"]
    d = mv.default()
    shown = {p.name for p, s in zip(mv.parts, mv.shown(d)) if s}
    assert shown == {"head1_headShape", "chestupper_neck1Shape", "head_eyesShape",
                     "headwear2Shape", "chest_shirt1Shape", "larm_shirt1Shape",
                     "pants_pants1Shape", "lleg_lfoot1Shape", "rleg_rfoot1Shape",
                     "larm_armShape"}
    # the game's rule: hidden when bits & mask; the mask converts back to the choice
    mask = mv.hide_mask(d)
    assert mv.shown_by_mask(mask) == mv.shown(d)
    assert mv.choice_from_mask(mask).slots == d.slots
    every = mv.shown(mv.everything())
    assert all(every)
    groups = {p.name: p.group for p in mv.parts}
    assert groups["head2_headShape"] == "Head 2" and groups["head_blackShape"] == "Burnt"
    assert groups["cap_neckchest1Shape"] == "Wound caps"
    assert groups["head_eyesShape"] == "Always shown"


def test_recomp_measured_mask_draws_a_bare_head_1_soldier():
    """CZ recomp, 2026-10-08: live mask 0x001FFFCF767EC602 drew head 1, no helmet."""
    names = ["head1_headShape", "head2_headShape", "head2_head_balaclavaShape",
             "head3_headShape", "headwear2Shape", "head_eyesShape", "cap_neckchest1Shape"]
    mv = cv.model_variants(scene(names), "cz")
    drawn = {p.name for p, s in zip(mv.parts, mv.shown_by_mask(0x001FFFCF767EC602)) if s}
    assert drawn == {"head1_headShape", "head_eyesShape"}


def test_choice_text_round_trip_and_errors():
    mv = cv.model_variants(scene(SKINNY), "cz")
    c = mv.parse("head=2,shirt=none burnt=on")
    assert (c.slots["head"], c.slots["shirt"], c.toggles["burnt"]) == (2, None, True)
    assert mv.parse(c.text()) == c
    assert mv.parse("everything").everything
    with pytest.raises(Dr2Error, match="head 1, 2"):
        mv.parse("head=5")
    with pytest.raises(Dr2Error, match="no such choice"):
        mv.parse("hat=1")
    r = mv.random(__import__("random").Random(4))
    assert set(r.slots) == set(mv.slots)


def test_misplaced_digit_read_as_meant():
    mv = cv.model_variants(scene(["headwearShape2DeformedDeformed", "head1_headShape",
                                  "head2_headShape"]), "cz")
    p = mv.parts[0]
    assert p.misplaced and p.group == "Headwear 2"
    assert any("after 'Shape'" in line for line in mv.describe())


def test_non_zombies_are_not_classified_and_prop_states_work():
    props = scene(["slot_machineShape", "slot_logoShape", "slot_logo_dmgShape",
                   "LOD_slot_machineShape", "slot_screen_staticShape",
                   "slot_screen_staticWinShape", "cap_bottleShape"],
                  source="data/streamedassets.big/slot.big/slot.big")
    mv = cv.model_variants(props, "cz")
    assert not mv.zombie and mv.toggles == [] and mv.slots == {}
    assert mv.states == ["far", "damaged", "screen_win"]
    shown = lambda c: {p.name for p, s in zip(mv.parts, mv.shown(c)) if s}   # noqa: E731
    base = shown(mv.default())
    assert "slot_logo_dmgShape" not in base and "LOD_slot_machineShape" not in base
    assert "cap_bottleShape" in base                    # a prop's cap is not a wound cap
    dmg = shown(mv.parse("damaged=on"))
    assert "slot_logo_dmgShape" in dmg and "slot_logoShape" not in dmg
    # a person: no table, nothing to choose
    assert not cv.model_variants(scene(["head_hairShape", "cap_neckShape"],
                                       "data/models/npcs.big/bob.big"), "cz").has_choices


def test_colour_rule_and_list():
    bank = ["zombie_a_mtl_jersey1.pdv", "zombie_a_mtl_jersey2.pdv", "zombie_a_mtl_jersey10.pdv",
            "zombie_a_4_mtl_1_var2.pdv", "zombie_a_4_mtl_1_var1.pdv", "zombie_a_mtl_jersey.pdv",
            "zombie_a_mtl_jerseyx1.pdv"]
    assert cv.colour_rule("zombie_a_mtl_jersey.pdv", bank) == [
        "zombie_a_mtl_jersey1.pdv", "zombie_a_mtl_jersey2.pdv", "zombie_a_mtl_jersey10.pdv"]
    assert cv.colour_rule("zombie_a_4_mtl_1.pdv", bank) == [
        "zombie_a_4_mtl_1_var1.pdv", "zombie_a_4_mtl_1_var2.pdv"]
    assert cv.colour_key("zombie_skinny_mtl_jersey.pdv") == "jersey"
    lst = cv.parse_colour_list("[zombie_a_2]\nZombie_a_mtl_jersey.pdv=a1.pdv,a2.pdv,\n")
    assert lst == {"zombie_a_2": {"zombie_a_mtl_jersey.pdv": ["a1.pdv", "a2.pdv"]}}


def test_glb_parts_include_and_colour_variants():
    sc = Scene.parse(make_scene())
    tiny = (b"\x89PNG\r\n\x1a\n" + b"\0" * 8)
    data = gltf.model_to_glb(sc, lambda n: tiny,
                             parts=[{"dr2_group": "Head 2", "dr2_shown": False, "dr2_part": 0}],
                             colour_variants=[("jersey 1", {0: ("box_cm_baked_jersey1", tiny,
                                                               "pattern")})],
                             extras={"dr2_variant": "head=2"})
    g = gltf.Glb.parse(data).gltf
    node = next(n for n in g["nodes"] if n.get("mesh") is not None)
    assert (node["extras"]["dr2_group"], node["extras"]["dr2_shown"]) == ("Head 2", False)
    assert g["extensions"]["KHR_materials_variants"]["variants"] == [{"name": "jersey 1"}]
    assert "KHR_materials_variants" in g["extensionsUsed"]
    prim = g["meshes"][0]["primitives"][0]
    m = prim["extensions"]["KHR_materials_variants"]["mappings"][0]
    assert m["variants"] == [0] and g["materials"][m["material"]]["name"].endswith("(jersey 1)")
    assert g["scenes"][0]["extras"]["dr2_variant"] == "head=2"
    # "as shown": a left-out part is not written, nor its textures
    g2 = gltf.Glb.parse(gltf.model_to_glb(sc, lambda n: tiny, include=set())).gltf
    assert "meshes" not in g2 and "images" not in g2


def test_library_folds_detail_levels(tmp_path, monkeypatch):
    """zombie_x_2/_3/_4 are one Library item (high detail shown); exports keep all."""
    from conftest import make_archive
    from dr2kit.catalog.export import group_rows
    from dr2kit.container.big import BigArchive
    from dr2kit.container.vpath import AssetTree
    from dr2kit.index import query
    from dr2kit.index.build import build_index, connect
    base = BigArchive.parse(make_scene())

    def level(n):          # different bytes per level, so they aren't folded as copies
        return make_archive(*[(e.name, e.data()) for e in base.entries],
                            ("note", str(n).encode())).to_bytes()
    zombie = make_archive(*[(f"zombie_x_{n}.big", level(n)) for n in (2, 3, 4)])
    root = tmp_path / "game"
    (root / "data" / "models").mkdir(parents=True)
    (root / "data" / "models" / "zombies.big").write_bytes(
        make_archive(("zombie_x.big", zombie.to_bytes())).to_bytes())
    monkeypatch.setenv("DR2_CZ_DATA", str(root))
    db = tmp_path / "i.sqlite"
    build_index("cz", AssetTree(root), db, thumbs=False)
    con = connect(db)
    shown = query.library_items(con, "cz", "zombies")
    assert [(r["name"], r["label"], r["detail"]) for r in shown] == [
        ("zombie_x_2.big", "Zombie X", "high")]
    levels = query.detail_levels(con, shown[0]["id"])
    assert [(r["name"], r["detail"]) for r in levels] == [
        ("zombie_x_2.big", "high"), ("zombie_x_3.big", "medium"), ("zombie_x_4.big", "low")]
    assert [r["detail"] for r in query.detail_levels(con, levels[2]["id"])] == \
        ["high", "medium", "low"]
    assert len(group_rows(con, "cz", "zombies")) == 3
    assert {r["n"] for r in query.library_counts(con, "cz")} == {1}
    low = query.library_item(con, levels[2]["id"])
    assert low["label"] == "Zombie X (low detail)" and low["detail_of"] == shown[0]["id"]


# ---- the games' own data (skip when absent) --------------------------------------------

ZOMBIES = {"cz": ["zombie_skinny", "zombie_soldier", "zombie_fat", "zombie_cop"],
           "cw": ["zombie_gas", "zombie_fat_female", "zombie_security"]}


@pytest.mark.parametrize("game", ["cz", "cw"])
def test_game_zombies_have_one_choice_per_slot(game, game_root):
    from dr2kit.container.vpath import AssetTree
    from dr2kit.convert.model import read_scene
    tree = AssetTree(game_root(game))
    for z in ZOMBIES[game]:
        vp = f"data/models/zombies.big/{z}.big/{z}_2.big"
        mv = cv.read_variants(tree, read_scene(tree, vp), game)
        assert mv.zombie and "head" in mv.slots, vp
        d = mv.default()
        shown = [p for p, s in zip(mv.parts, mv.shown(d)) if s]
        for slot in mv.slots:
            nums = {cv.SLOT[slot].number(p.bits) for p in shown} - {None}
            assert len(nums) <= 1, (vp, slot, nums)
        assert not any(p.bits & cv.TOGGLE["caps"].bit for p in shown), vp


def test_cz_colour_list_is_the_name_rule(game_root):
    """The name rule gives every choice CZ's zombie_pdv_variations.txt lists."""
    from dr2kit.container.vpath import AssetTree
    tree = AssetTree(game_root("cz"))
    bank = cv.ColourBank(tree, "cz")
    listed = bank.listed()
    assert sum(len(v) for m in listed.values() for v in m.values()) == 129
    names = list(bank.names())
    for model in listed.values():
        for own, alts in model.items():
            assert cv.colour_rule(own, names) == alts, own


@pytest.mark.parametrize("mode", ["all", "shown"])
def test_variant_exports_import_back_identical(mode, game_root):
    """An organised (or one-look) export, imported unedited, gives the model's own bytes:
    tagged nodes still match their shapes, left-out parts are kept as they are."""
    from dr2kit.container.vpath import AssetTree
    from dr2kit.convert.model import model_glb, read_scene
    from dr2kit.convert.model_import import import_glb, plan_import
    tree = AssetTree(game_root("cz"))
    vp = "data/models/zombies.big/zombie_skinny.big/zombie_skinny_2.big"
    data = tree.resolve(vp).data()
    sc = read_scene(tree, vp)
    glb = model_glb(tree, sc, game="cz", textures=False, variant="head=2 shirt=3", mode=mode)
    out, _plan = import_glb(Scene.parse(data, vp), glb)
    assert out == data
    plan = plan_import(Scene.parse(data, vp), glb)
    if mode == "shown":
        assert any("exported as one look" in str(i) for i in plan.issues)
        assert len(plan.untouched) == len(sc.meshes) - len(plan.unchanged)

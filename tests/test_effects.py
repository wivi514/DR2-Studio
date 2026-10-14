"""Phase 13 step 6: particle effects (formats.effect), changes (convert.effects), effect
mods (mods.neweffect) and what the build does for them (eviction, scene list, layout.bin)."""

from __future__ import annotations

import json
import struct

import pytest

from dr2kit.convert.effects import apply_changes, describe, main_colour
from dr2kit.errors import Dr2Error, FormatError
from dr2kit.formats import effect as fx


def make_emitter(shape: int = 0, texture: str = "fire_flame",
                 colours=((1.0, 0.5, 0.1, 1.0),) * 5) -> bytes:
    raw = bytearray(fx.FIXED)
    struct.pack_into(">I", raw, 0x30, shape)
    struct.pack_into(">4f", raw, 0x54, 0.1, 0.2, 0.3, 0.4)
    struct.pack_into(">20f", raw, 0x64, *[v for c in colours for v in c])
    struct.pack_into(">5f", raw, 0xF0, 0.1, 0.2, 0.3, 0.2, 0.0)
    raw += texture.encode().ljust(fx.TEXTURE_SIZE, b"\0") + bytes(8)
    raw += struct.pack(f">{fx.SHAPE_TAIL[shape] // 4}f",
                       *([0.03, 0.7, 0, -0.03, 0, 0][:fx.SHAPE_TAIL[shape] // 4]))
    return bytes(raw)


def make_effect(name: str = "test_wpn_c_1", shapes=(0, 1, 3), version: int = 0x1D) -> bytes:
    out = struct.pack(">I", version) + name.encode().ljust(fx.NAME_SIZE, b"\0")
    out += struct.pack(">I", len(shapes))
    out += struct.pack(f">{fx.VERSIONS[version]}I", *([0] * (fx.VERSIONS[version] - 1) + [30]))
    for s in shapes:
        out += make_emitter(s)
    return out


@pytest.mark.parametrize("version", [0x1D, 0x20])
def test_effect_round_trip(version):
    data = make_effect(version=version)
    e = fx.Effect.parse(data)
    assert e.name == "test_wpn_c_1" and len(e.emitters) == 3
    assert [len(m.raw) for m in e.emitters] == [440, 464, 460]
    assert e.emitters[1].shape_values[:2] == pytest.approx([0.03, 0.7])
    assert e.emitters[0].texture == "fire_flame"
    assert e.to_bytes() == data
    assert fx.is_effect(data) and not fx.is_effect(b"\0\0\0\x01")
    with pytest.raises(FormatError):
        fx.Effect.parse(data + b"\0\0\0\0")            # leftover bytes are named
    with pytest.raises(FormatError):
        fx.Effect.parse(b"\0\0\0\x07" + data[4:])     # unknown version


def test_emitter_fields():
    e = fx.Effect.parse(make_effect())
    m = e.emitters[0]
    assert m.get("colour_times") == pytest.approx([0.1, 0.2, 0.3, 0.4])
    assert m.colour_keys()[0] == pytest.approx((1.0, 0.5, 0.1, 1.0))
    m.set("gravity", [0, -2, 0])
    assert m.get("gravity") == pytest.approx([0, -2, 0])
    m.texture = "glow"
    assert m.texture == "glow"
    with pytest.raises(FormatError):
        m.set("shape", 1)                                # changes the size: refused
    with pytest.raises(FormatError):
        m.set("sizes", [1, 2])
    with pytest.raises(FormatError):
        m.texture = "x" * 40
    assert fx.Effect.parse(e.to_bytes()).emitters[0].texture == "glow"
    d = m.to_dict()
    assert d["texture"] == "glow" and len(d["colours"]) == 20


def test_changes():
    e = fx.Effect.parse(make_effect())
    apply_changes(e, {"hue": 210, "saturation": 1.2, "size": 2, "time": 0.5,
                      "texture": {"fire_flame": "glow"}, "emitters": {"1": {"gravity": [0, 1, 0]}},
                      "remove": [2]})
    assert len(e.emitters) == 2
    r, g, b, a = e.emitters[0].colour_keys()[0]
    assert b > r and b > g and a == pytest.approx(1.0)       # orange turned blue
    assert e.emitters[0].get("sizes")[1] == pytest.approx(0.4)
    assert e.emitters[0].get("colour_times")[3] == pytest.approx(0.2)
    assert {m.texture for m in e.emitters} == {"glow"}
    assert e.emitters[1].get("gravity") == pytest.approx([0, 1, 0])
    assert len(describe(e)) == 2 and main_colour(e)[2] > 0.5
    grey = fx.Effect.parse(make_effect(shapes=(0,)))
    grey.emitters[0].set_colour_keys([(0.5, 0.5, 0.5, 1.0)] * 5)
    apply_changes(grey, {"hue": 120})
    assert grey.emitters[0].colour_keys()[0][:3] == pytest.approx((0.5, 0.5, 0.5))  # grey stays
    for bad in ({"colour": 1}, {"texture": {"nope": "x"}}, {"emitters": {"9": {}}},
                {"emitters": {"0": {"no_field": 1}}}, {"remove": [0, 1, 2]}):
        with pytest.raises(Dr2Error):
            apply_changes(fx.Effect.parse(make_effect()), bad)


def test_layout_change():
    e = fx.Effect.parse(make_effect())                   # shapes 0, 1, 3
    apply_changes(e, {"layout": [1, 1, 0, 1], "emitters": {"3": {"gravity": [0, 5, 0]}}})
    assert [m.get("shape") for m in e.emitters] == [1, 1, 0, 1]
    assert e.emitters[3].get("gravity") == pytest.approx([0, 5, 0])
    assert e.emitters[0].get("gravity") == pytest.approx([0, 0, 0])   # copies, not shared
    assert fx.Effect.parse(e.to_bytes()).to_bytes() == e.to_bytes()
    for bad in ({"layout": []}, {"layout": [7]}, {"layout": "x"}):
        with pytest.raises(Dr2Error):
            apply_changes(fx.Effect.parse(make_effect()), bad)


# --- the real games ---------------------------------------------------------------------

def test_effect_between_the_games_layouts():
    """Case West's 3 header words ↔ Case Zero's 4 (a 0 third), emitters unchanged."""
    cw = fx.Effect.parse(make_effect(version=0x20))
    assert cw.as_version(0x1D).to_bytes() == make_effect(version=0x1D)
    cz = fx.Effect.parse(make_effect(version=0x1D))
    assert cz.as_version(0x20).to_bytes() == make_effect(version=0x20)
    assert cz.as_version(0x1D) is cz
    with pytest.raises(FormatError):
        cz.as_version(7)


@pytest.mark.gamedata
def test_case_west_effects_in_case_zeros_layout(game_root):
    """Every effect both games have with the same emitters converts to Case Zero's bytes,
    except Case Zero's 7 with the third word set (census, 2026-10-13)."""
    from dr2kit.container.vpath import AssetTree
    cz = fx.read_all(AssetTree(game_root("cz")))
    cw = fx.read_all(AssetTree(game_root("cw")))
    same = differ = 0
    for name, (_, e) in cz.items():
        if name in cw and [m.raw for m in e.emitters] == [m.raw for m in cw[name][1].emitters]:
            if cw[name][1].as_version(0x1D).to_bytes() == e.to_bytes():
                same += 1
            else:
                differ += 1
    assert same >= 390 and differ <= 10, (same, differ)


@pytest.mark.gamedata
@pytest.mark.parametrize("game", ["cz", "cw"])
def test_effects_census(game, game_root):
    from dr2kit.container.vpath import AssetTree
    r = fx.census_effects(AssetTree(game_root(game)))
    assert not r["problems"]
    assert r["effects"] == {"cz": 448, "cw": 506}[game]
    assert r["emitters"] == {"cz": 2221, "cw": 2516}[game]


@pytest.mark.gamedata
@pytest.mark.parametrize("game", ["cz", "cw"])
def test_effect_mod_builds(game, game_root, tmp_path):
    from dr2kit.container.big import BigArchive
    from dr2kit.container.vpath import AssetTree
    from dr2kit.mods import build as mbuild
    from dr2kit.mods import manifest, neweffect
    root = game_root(game)
    tree = AssetTree(root)
    mod = tmp_path / "mod"
    manifest.create(mod, "fx")
    free = neweffect.free_slots(tree, game)
    assert (69, "wip_1") in free and len(free) == 36
    neweffect.change_effect(tree, mod, "flamingsword_wpn_c_3_unq", {"hue": 120})
    num, recipe = neweffect.new_effect(tree, game, mod, "flamingsword_wpn_c_3_unq",
                                       {"hue": 210, "size": 1.5}, "wip_1")
    assert num == 69 and recipe.name == "EFFECT_Common1069.copy.json"
    assert neweffect.own_effects(mod)[0][0] == 69
    assert neweffect.changed_effects(mod)[0][0] == "flamingsword_wpn_c_3_unq"
    with pytest.raises(Dr2Error):
        neweffect.new_effect(tree, game, mod, "flamingsword_wpn_c_3_unq", {}, 178)  # not free
    res = mbuild.build([manifest.Mod.load(mod)], game, tree, tmp_path / "out")
    out = AssetTree(tmp_path / "out")
    assert "layout.bin" in res.files                   # effects.big grew: re-pinned
    lay = (tmp_path / "out" / "layout.bin").read_bytes()
    size = (tmp_path / "out" / "data/models/effects.big").stat().st_size
    pins = [int.from_bytes(lay[i + 132:i + 136], "big") for i in range(0, len(lay), 152)
            if lay[i:i + 128].split(b"\0")[0] == b"data/models/effects.big"]
    assert pins and all(p == size for p in pins)
    effects = fx.read_all(out)
    assert effects["wip_1"][0] == "EFFECT_Common1069"
    assert effects["wip_1"][1].emitters[0].get("sizes")[0] > \
        effects["flamingsword_wpn_c_3_unq"][1].emitters[0].get("sizes")[0]
    desc = out.resolve("data/models/effects.big/SceneDescription").data()
    assert b"EFFECT_Common1069".ljust(32, b"\0") + struct.pack(">I", 13) in desc
    head = out.resolve("data/models/effects.big/SceneHeader").data()
    assert struct.unpack_from(">I", head, 12)[0] == len(desc) // 36
    pre_new = (tmp_path / "out" / "data/preload4.big").read_bytes()
    pre_old = (root / "data/preload4.big").read_bytes()
    assert len(pre_new) == len(pre_old)
    assert sum(a != b for a, b in zip(pre_new, pre_old)) <= 4   # one hash word: evicted
    arc = BigArchive.parse(pre_new, "preload4.big")
    e = next(x for x in arc.entries if x.name == "effects.big")
    assert e.hash != e.computed_hash()
    # an .effect.json made for another effect is refused, by name
    bad = mod / "replace/data/models/effects.big/EFFECT_Common0.effect.json"
    bad.write_text(json.dumps({"format": "dr2kit-effect/1", "effect": "not_this_one",
                               "changes": {}}))
    with pytest.raises(Dr2Error):
        mbuild.plan_mods([manifest.Mod.load(mod)], game, tree)


@pytest.mark.gamedata
def test_new_effect_refuses_a_slot_used_by_another_mod(game_root, tmp_path, monkeypatch):
    """An explicit slot choice cannot collide with another mod in the library."""
    from types import SimpleNamespace

    from dr2kit.container.vpath import AssetTree
    from dr2kit.mods import library, manifest, neweffect

    tree = AssetTree(game_root("cz"))
    free_slot = neweffect.free_slots(tree, "cz")[0][0]
    current = tmp_path / "current"
    manifest.create(current, "current")
    other = tmp_path / "other"
    folder = other / "add/data/models/effects.big"
    folder.mkdir(parents=True)
    (folder / f"EFFECT_Common{neweffect.OWN_ENTRY + free_slot}.copy.json").write_text("{}")

    entry = SimpleNamespace(mod=SimpleNamespace(root=other, games=("cz",)))
    monkeypatch.setattr(library, "ModLibrary", lambda: SimpleNamespace(entries=lambda: [entry]))
    with pytest.raises(Dr2Error, match=f"effect slot {free_slot} is already used"):
        neweffect.new_effect(tree, "cz", current, "flamingsword_wpn_c_3_unq", {}, free_slot)


@pytest.mark.gamedata
def test_particle_picture_of_ones_own(game_root, tmp_path):
    from dr2kit.container.vpath import AssetTree
    from dr2kit.convert import png
    from dr2kit.convert.texture import to_image
    from dr2kit.formats.bct import Bct
    from dr2kit.mods import build as mbuild
    from dr2kit.mods import manifest, neweffect
    tree = AssetTree(game_root("cz"))
    mod = tmp_path / "mod"
    manifest.create(mod, "pic")
    pic = tmp_path / "flake.png"
    png.write(pic, png.Image(60, 60, bytes((200, 230, 255, 255)) * 3600))
    f = neweffect.new_particle_texture(tree, mod, "my_flake", pic)
    assert f.name == "my_flake.copy.json"                   # no .bct, like its neighbours
    with pytest.raises(Dr2Error):
        neweffect.new_particle_texture(tree, mod, "fire_flame", pic)   # the game's name
    num, _ = neweffect.new_effect(tree, "cz", mod, "snowtrail_wpn_bs_1",
                                  {"texture": {"snow": "my_flake"}})
    mbuild.build([manifest.Mod.load(mod)], "cz", tree, tmp_path / "out")
    out = AssetTree(tmp_path / "out")
    t = to_image(Bct.parse(out.resolve("data/models/effects.tex/my_flake").data()))
    assert (t.width, t.height) == (64, 64)                 # the nearest game size
    assert t.rgba[:3] == bytes((200, 230, 255)) or abs(t.rgba[0] - 200) < 12
    from dr2kit.catalog.weapons import names
    e = fx.read_all(out)[names("cz")[num - 1]][1]
    assert "my_flake" in {m.texture for m in e.emitters}
    assert neweffect.remove(mod, num) and not neweffect.own_effects(mod)

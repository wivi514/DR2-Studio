"""Seeing mods without the game (phase 10 step 5): `mods.preview` gives the bytes Play
deploys, through every way a reader reaches an asset; a failing mod is left out."""

import os
import time

import pytest

from dr2kit.container.big import BigArchive
from dr2kit.container.vpath import AssetTree
from dr2kit.formats.bct import Bct
from dr2kit.mods import build as mbuild
from dr2kit.mods.manifest import Mod
from dr2kit.mods.preview import Preview

from test_mods import TEX_VP, game, make_mod, red_png  # noqa: F401 - the fixture


def test_preview_gives_the_built_bytes(game, tmp_path):
    mod_dir = make_mod(tmp_path)
    red_png(mod_dir / "replace" / (TEX_VP + ".png"))
    (mod_dir / "replace" / "data" / "notes.txt").write_bytes(b"modded notes")
    mods = [Mod.load(mod_dir)]
    pv = Preview("cz", game, mods, cache_dir=tmp_path / "pcache")
    assert pv.problems == [] and pv.active
    assert pv.changed("data/models/npcs.big") == ["red"]
    tree = pv.tree()
    res = mbuild.build(mods, "cz", AssetTree(game), tmp_path / "built")
    built = AssetTree(tmp_path / "built")
    for vp in (TEX_VP, "data/notes.txt"):
        assert tree.resolve(vp).data() == built.resolve(vp).data()       # exact bytes
    assert AssetTree(game).resolve(TEX_VP).data() != tree.resolve(TEX_VP).data()
    # a reader that parses the nested pack from its entry's raw bytes sees it too
    npcs = tree.open_archive("data/models/npcs.big")
    pack = BigArchive.parse(npcs.find("hero.tex")[0].data())
    assert pack.find("hero_cm")[0].data() == built.resolve(TEX_VP).data()
    # untouched assets are the game's own
    assert tree.resolve("data/models/npcs.big/hero.big").data() == \
        AssetTree(game).resolve("data/models/npcs.big/hero.big").data()
    assert Bct.parse(tree.resolve(TEX_VP).data()).header.width == 32
    assert any(f.suffix == ".bin" for f in (tmp_path / "pcache").iterdir())   # cached
    assert res.files


def test_a_failing_mod_is_left_out(game, tmp_path):
    good = make_mod(tmp_path, "good")
    red_png(good / "replace" / (TEX_VP + ".png"))
    bad = make_mod(tmp_path, "bad", priority=5)
    red_png(bad / "replace" / "data" / "models" / "npcs.big" / "nothing.tex" / "x.png")
    pv = Preview("cz", game, [Mod.load(good), Mod.load(bad)], cache_dir=tmp_path / "c")
    assert [m.id for m in pv.mods] == ["good"]
    assert len(pv.problems) == 1 and "bad" in pv.problems[0]
    assert pv.tree().resolve(TEX_VP).data() != AssetTree(game).resolve(TEX_VP).data()


def test_stamp_follows_the_mod_files(game, tmp_path):
    mod_dir = make_mod(tmp_path)
    png = mod_dir / "replace" / (TEX_VP + ".png")
    red_png(png)
    pv = Preview("cz", game, [Mod.load(mod_dir)], cache_dir=tmp_path / "c")
    s1 = pv.stamp(["data/models/npcs.big"])
    assert s1 and pv.stamp(["data/datafile.big"]) == ""          # only what it touches
    os.utime(png, ns=(time.time_ns(), time.time_ns() + 10**9))
    assert pv.stamp(["data/models/npcs.big"]) != s1


def test_preview_of_a_real_texture_mod_matches_the_build(game_root, tmp_path):
    """On the real game: Chuck's shirt recoloured (compressed .tex inside npcs.big)."""
    from dr2kit.convert import png
    from dr2kit.convert.texture import to_image
    root = game_root("cz")
    vp = "data/models/npcs.big/chest_young_chuck.tex/young_cr_shirt_cm"
    tree = AssetTree(root)
    img = to_image(Bct.parse(tree.resolve(vp).data()), 0)
    rgba = bytearray(img.rgba)
    rgba[0::4] = bytes(255 - b for b in rgba[0::4])                 # invert red
    mod_dir = make_mod(tmp_path, "shirt")
    out = mod_dir / "replace" / (vp + ".png")
    out.parent.mkdir(parents=True)
    png.write(out, png.Image(img.width, img.height, bytes(rgba)))
    mods = [Mod.load(mod_dir)]
    pv = Preview("cz", root, mods, cache_dir=tmp_path / "c")
    mbuild.build(mods, "cz", tree, tmp_path / "built")
    assert pv.tree().resolve(vp).data() == AssetTree(tmp_path / "built").resolve(vp).data()


test_preview_of_a_real_texture_mod_matches_the_build = pytest.mark.gamedata(
    test_preview_of_a_real_texture_mod_matches_the_build)


@pytest.mark.gamedata
def test_preview_of_a_real_model_mod_matches_the_build(game_root, tmp_path):
    """A .glb replacing a model (the scissors, inside its streamedassets pack)."""
    from dr2kit.convert.model import export_glb
    root = game_root("cz")
    vp = "data/streamedassets.big/Scissors.big/scissors.big"
    tree = AssetTree(root)
    mod_dir = make_mod(tmp_path, "scissors")
    out = mod_dir / "replace" / (vp + ".glb")
    out.parent.mkdir(parents=True)
    out.write_bytes(export_glb(tree, vp, game="cz"))
    mods = [Mod.load(mod_dir)]
    pv = Preview("cz", root, mods, cache_dir=tmp_path / "c")
    assert pv.problems == []
    mbuild.build(mods, "cz", tree, tmp_path / "built")
    assert pv.tree().resolve(vp).data() == AssetTree(tmp_path / "built").resolve(vp).data()

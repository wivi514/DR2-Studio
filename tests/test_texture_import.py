"""Textures from texturing programs → the model's game textures (`mods.texture_import`),
on a synthetic game: one model (`box.big`, material 0 with `box_cm`) and its pack."""

import math

import pytest

from dr2kit.container.vpath import AssetTree
from dr2kit.convert import png
from dr2kit.mods import texture_import as ti

from conftest import make_archive, make_bct, make_scene

np = pytest.importorskip("numpy")
MODEL = "data/pack.big/box.big"


@pytest.fixture
def game(tmp_path):
    root = tmp_path / "game"
    (root / "data").mkdir(parents=True)
    pack = make_archive(("box.big", make_scene()),
                        ("box.tex", make_archive(("box_cm", make_bct("DXT1", 32, 32, 1))).to_bytes()))
    (root / "data" / "pack.big").write_bytes(pack.to_bytes())
    return AssetTree(root)


def solid(path, w, h, rgba):
    png.write(path, png.Image(w, h, bytes(rgba) * (w * h)))


def test_painter_names_sizes_and_skips(game, tmp_path):
    out = tmp_path / "painter"
    out.mkdir()
    solid(out / "00_box_cm_BaseColor.png", 64, 64, (255, 0, 0, 255))
    solid(out / "00_box_cm_Roughness.png", 64, 64, (9, 9, 9, 255))
    solid(out / "00_box_cm_Normal.png", 64, 64, (128, 128, 255, 255))
    solid(out / "mystery.png", 8, 8, (0, 0, 0, 255))
    tp = ti.plan(game, MODEL, [out])
    assert [(i.texture, i.role) for i in tp.items] == [("box_cm", "colour")]
    assert "resized 64×64 → 32×32" in tp.items[0].notes
    why = dict(tp.skipped)
    assert "no map for this channel" in why["00_box_cm_Roughness.png"]
    assert "no normal map" in why["00_box_cm_Normal.png"]
    assert "neither" in why["mystery.png"]
    mod = tmp_path / "mod"
    (written,) = ti.apply(tp, mod)
    assert written == mod / "replace" / "data/pack.big/box.tex/box_cm.png"
    img = png.read(written)
    assert (img.width, img.height) == (32, 32) and img.rgba[:4] == bytes((255, 0, 0, 255))


def test_painter_default_names_with_the_mesh_first(game, tmp_path):
    out = tmp_path / "p"
    out.mkdir()
    solid(out / "box_00_box_cm_BaseColor.png", 32, 32, (1, 2, 3, 255))
    assert [i.texture for i in ti.plan(game, MODEL, [out]).items] == ["box_cm"]


def test_exact_texture_name_and_wrong_shape(game, tmp_path):
    out = tmp_path / "x"
    out.mkdir()
    solid(out / "box_cm.png", 32, 32, (0, 255, 0, 255))
    assert [i.texture for i in ti.plan(game, MODEL, [out]).items] == ["box_cm"]
    solid(out / "box_cm.png", 64, 32, (0, 255, 0, 255))
    tp = ti.plan(game, MODEL, [out])
    assert not tp.items and "shape" in tp.skipped[0][1]


def test_metal_roughness_becomes_diffuse(game, tmp_path):
    out = tmp_path / "mr"
    out.mkdir()
    solid(out / "00_box_cm_BaseColor.png", 32, 32, (200, 100, 50, 255))
    solid(out / "00_box_cm_Metallic.png", 32, 32, (255, 255, 255, 255))   # all metal
    tp = ti.plan(game, MODEL, [out])
    (item,) = tp.items                      # no specular slot here: colour only
    assert item.derived.startswith("from BaseColor + Metallic")
    assert item.image.rgba[:3] == bytes((0, 0, 0))   # metal has no diffuse colour


def test_green_convention_is_measured():
    w = h = 64
    px = bytearray()
    for y in range(h):
        for x in range(w):
            # a bump h = exp(-r²); OpenGL normal: (-dh/dx, +dh/drow ... green up)
            dx, dy = x - 32, y - 32
            hgt = math.exp(-(dx * dx + dy * dy) / 120)
            gx, grow = -2 * dx / 120 * hgt, -2 * dy / 120 * hgt
            n = (-gx * 4, grow * 4, 1)
            ln = math.sqrt(sum(c * c for c in n))
            px += bytes(int((c / ln * 0.5 + 0.5) * 255) for c in n) + b"\xff"
    gl = png.Image(w, h, bytes(px))
    assert ti.green_convention(gl) < -0.5
    flipped = bytearray(px)
    flipped[1::4] = bytes(255 - v for v in flipped[1::4])
    assert ti.green_convention(png.Image(w, h, bytes(flipped))) > 0.5


def test_textures_from_a_glb(game, tmp_path):
    from dr2kit.convert.gltf import model_to_glb
    from dr2kit.formats.scene import Scene
    red = png.encode(png.Image(32, 32, bytes((250, 0, 0, 255)) * 1024))
    glb = model_to_glb(Scene.parse(make_scene()), lambda name: red)
    f = tmp_path / "from_blender.glb"
    f.write_bytes(glb)
    tp = ti.plan(game, MODEL, [f])
    assert [(i.texture, i.source) for i in tp.items] == [("box_cm", "from_blender.glb: 00_box_cm_BaseColor")]

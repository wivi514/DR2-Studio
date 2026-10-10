"""Materials whose colour comes from shader constants: value sets, constant tables, bakes.

Synthetic data only. The formulas are the ones read from the game's pixel shaders
(docs/formats.md §Materials: value sets); every material of both games bakes
(checked by hand over both games, see docs/devlog.md).
"""

import struct

import pytest

from dr2kit.errors import FormatError
from dr2kit.formats.shader import REG_FLOAT4, ValueSet, constant_table


def shader_container(constants) -> bytes:
    """A minimal shader container: magic, constant-table offset, the table."""
    names = b"".join(n.encode() + b"\0" for n, _ in constants)
    info_off = 28
    name_off = info_off + 20 * len(constants)
    table = struct.pack(">7I", 0, 0, 0, len(constants), info_off, 0, 0)
    o = name_off
    for n, reg in constants:
        table += struct.pack(">IHHHHII", o, REG_FLOAT4, reg, 1, 0, 0, 0)
        o += len(n) + 1
    table += names
    head = b"\x10\x2a\x11\x01" + bytes(12) + struct.pack(">I", 0x24) + bytes(0x24 - 0x14)
    return head + struct.pack(">I", len(table)) + table


def value_set(name: str, shader: int, values) -> bytes:
    raw = name.encode() + b"\0"
    out = struct.pack(">I", len(raw)) + raw.ljust((len(raw) + 3) & ~3, b"\0")
    out = out[:4 + len(raw)] + bytes((-(4 + len(raw))) % 4)
    out += struct.pack(">4I", 0x1234, 0xFFFFFFFF, shader, len(values))
    for reg, floats in values:
        out += struct.pack(">6I", 2, 0, len(floats), 1, reg, 0xABCD) + \
            struct.pack(f">{len(floats)}f", *floats)
    return out


def test_constant_table_and_value_set():
    po = shader_container([("gBaseTextureColour", 141), ("gPattern1Colour", 143)])
    table = constant_table(po)
    assert table["gBaseTextureColour"].register == 141
    vs = ValueSet.parse(value_set("x_mtl_shirt.pdv", 0x21B5AF40,
                                  [(141, (0.5, 0.25, 0.125, 1.0)), (143, (1, 1, 1, 0.5)),
                                   (200, (9.0,))]))
    assert vs.name == "x_mtl_shirt.pdv" and vs.pixel_shader == 0x21B5AF40
    named = vs.named(table)
    assert named == {"gBaseTextureColour": (0.5, 0.25, 0.125, 1.0),
                     "gPattern1Colour": (1.0, 1.0, 1.0, 0.5)}          # 200: not a constant
    with pytest.raises(FormatError):
        ValueSet.parse(value_set("x.pdv", 1, [(141, (1.0,))]) + b"junk")
    with pytest.raises(FormatError):
        constant_table(b"nope" * 10)


np = pytest.importorskip("numpy")


def image(pixels):
    from dr2kit.convert.png import Image
    a = np.asarray(pixels, np.uint8)
    return Image(a.shape[1], a.shape[0], a.tobytes())


def baked(rec, textures):
    from dr2kit.convert.material import bake
    img = bake(rec, lambda n: textures.get(n))
    return np.frombuffer(img.rgba, np.uint8).reshape(img.height, img.width, 4)


def test_pattern_bake_weights_and_blood():
    from dr2kit.convert.material import Recipe
    d = image([[[255, 0, 0, 0], [0, 255, 0, 0]]])            # base here, pattern 1 there
    values = {"gBaseTextureColour": (0.25, 0.5, 1.0, 1.0), "gPattern1Colour": (1, 1, 1, 0.25)}
    out = baked(Recipe("pattern", values, "d", None), {"d": d})
    # linear = colour x weight x channel^2; shown as sqrt(linear)
    assert out[0, 0, :3].tolist() == [128, 180, 255]
    assert out[0, 1, :3].tolist() == [128, 128, 128]
    m = image([[[0, 0, 255, 255], [0, 0, 0, 0]]])            # blood where mask B and A
    values = dict(values, gBloodColour=(0.5, 0.0, 0.0, 1.0), gPackedBumpAmbBloodvis=(1, 0, 1))
    out = baked(Recipe("pattern", values, "d", "m"), {"d": d, "m": m})
    lin = np.array([0.25, 0.5, 1.0])
    want = np.sqrt(lin + 1.0 * (np.array([0.5, 0, 0]) * lin - lin)) * 255
    assert np.allclose(out[0, 0, :3], want, atol=1) and out[0, 1, :3].tolist() == [128] * 3


def test_pattern_uv_transform_tiles_the_weights():
    from dr2kit.convert.material import Recipe
    d = image([[[255, 0, 0, 0], [0, 0, 0, 0]]])
    values = {"gBaseTextureColour": (1, 1, 1, 1), "gUVScaleOffset": (2.0, 1.0, 0.0, 0.0)}
    m = image([[[0, 0, 0, 0]] * 4])
    out = baked(Recipe("pattern", values, "d", "m"), {"d": d, "m": m})
    assert out.shape[1] == 4 and out[0, :, 0].tolist() == [255, 0, 255, 0]


def test_bodypart_and_channel_bakes():
    from dr2kit.convert.material import Recipe
    d = image([[[255, 255, 255, 210], [255, 255, 255, 100], [255, 255, 255, 255]]])
    values = {f"gBodyPart{i}Colour": c for i, c in
              ((1, (1, 0, 0, 1)), (2, (0, 1, 0, 1)), (3, (0, 0, 1, 1)), (4, (0.25, 0.25, 0.25, 1)))}
    out = baked(Recipe("bodypart", values, "d", None), {"d": d})
    assert out[0, 0, :3].tolist() == [255, 0, 0]               # alpha 0.82: part 1
    assert out[0, 1, :3].tolist() == [128, 128, 128]           # alpha 0.39: part 4
    assert out[0, 2, :3].tolist() == [255, 255, 255]           # above 0.875: untinted
    d = image([[[0, 0, 0, 255], [255, 0, 0, 255]]])
    values = {"gDiffuseTint": (0.25, 0.25, 0.25, 1), "gRedChannelColour": (1, 0, 0, 1),
              "gRedChannelSaturation": (1.0,), "gGreenChannelColour": (0, 0, 0, 0),
              "gBlueChannelColour": (0, 0, 0, 0)}
    out = baked(Recipe("channel", values, "d", None), {"d": d})
    assert out[0, 0, :3].tolist() == [128, 128, 128]           # tint only
    assert out[0, 1, :3].tolist() == [255, 0, 0]               # red layer fully on


def test_lens_and_hair_bakes_keep_their_opacity():
    """Glasses (gLensColour, ProtoSkinnedLens) and eyelashes/hair
    (gDiffuseColourControl, ProtoSkinnedHair, ZombieHair): the texture is channels, not
    a colour (formulas from 1595db80.po and ca7f0160.po)."""
    from dr2kit.convert.material import LENS_GAIN, Recipe
    t = image([[[0, 255, 255, 255], [0, 0, 128, 255]]])       # frame (cyan) | lens (blue)
    out = baked(Recipe("lens", {"gLensColour": (0.25, 0.25, 0.25, 0.5)}, "t", None), {"t": t})
    assert np.allclose(out[0, 0, :3], np.sqrt(LENS_GAIN * 0.25) * 255, atol=1)   # 1.4 b² c
    assert out[0, 0, 3] == 128 and out[0, 1, 3] == 0                             # g² × a
    lash = image([[[255, 4, 1, 255], [255, 0, 0, 0]]])        # Katey's red lash weights
    values = {"gDiffuseColourControl": (0.09, 0.04, 0.01), "gHairTransparencyScale": (0.5,)}
    out = baked(Recipe("hair", values, "t", None), {"t": lash})
    assert out[0, 0, :3].tolist() == [77, 51, 26]             # sqrt(r² × colour): brown, not red
    assert out[0, 0, 3] == 128 and out[0, 1, 3] == 0          # a × scale


def test_alpha_mode_by_shader():
    from dr2kit.convert.material import alpha_mode
    for name in ("CM_OM_LM", "LIT_CM_OM_RMX", "ProtoSkinnedHair", "ProtoSkinnedHairRGB",
                 "ZombieHair"):
        assert alpha_mode(name) == "MASK", name
    for name in ("ProtoSkinnedCloth", "ZombieCloth", "ZombieDiffuse", "CM_LM", "ZombieHairLOD2",
                 "LIT_CM_NM_RMX_SPEC", ""):
        assert alpha_mode(name) == "OPAQUE", name


def test_glb_marks_hair_and_lens_materials():
    from conftest import make_scene
    from dr2kit.convert.gltf import Glb, model_to_glb
    from dr2kit.formats.scene import Scene
    sc = Scene.parse(make_scene())
    png1 = __import__("dr2kit.convert.png", fromlist=["png"]).encode(
        __import__("dr2kit.convert.png", fromlist=["png"]).Image(1, 1, bytes(4)))
    sc.shaders = {k: "ProtoSkinnedHairRGB" for k in sc.shaders}
    mat = Glb.parse(model_to_glb(sc, lambda n: png1)).gltf["materials"][0]
    assert mat["alphaMode"] == "MASK" and mat["alphaCutoff"] == 0.5
    sc.shaders = {k: "ProtoSkinnedClothRGB" for k in sc.shaders}
    assert "alphaMode" not in Glb.parse(model_to_glb(sc, lambda n: png1)).gltf["materials"][0]
    mat = Glb.parse(model_to_glb(sc, lambda n: png1,
                                 base_colour=lambda m: ("x_baked", png1, "lens"))).gltf["materials"][0]
    assert mat["alphaMode"] == "BLEND"

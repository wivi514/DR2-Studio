"""Animations (`formats.anim`) and Chuck holding an item (`convert.holding`), phase 13.2.

The unit tests build ``.anm`` bytes field by field (docs/formats.md §Animations); the
game-data tests read the real idles and skip, saying why, without a game.
"""

from __future__ import annotations

import math
import struct

import pytest

from dr2kit.errors import FormatError
from dr2kit.formats import anim


def make_anm(tracks, keys: bytes, frames: int = 2, rate: float = 30.0,
             offset0: bool = False) -> bytes:
    """An ``.anm``: ``tracks`` = [(node, kind)], ``keys`` = the first keys in order."""
    n = len(tracks)
    mask_off = 0x14 + 2 * n + 2
    width = (n + 7) // 8
    data_off = (mask_off + frames * width + 3) // 4 * 4
    head = struct.pack(">IffHHHH", 0x24F628C0, (frames - 1) / rate, rate, mask_off,
                       0 if offset0 else data_off, frames, n)
    table = b"".join(bytes((node, kind)) for node, kind in tracks) + b"\xff\x00"
    mask = bytes([0xFF] * width) * frames
    pad = b"\0" * (data_off - mask_off - len(mask))
    return head + table + mask + pad + keys


def packed(q) -> bytes:
    """An animated rotation's first key: x, y as 15 bits (/16384), z, w as 16 (/32767)."""
    x, y, z, w = q
    return struct.pack(">HHhh", round(x * 16384) & 0x7FFF, (round(y * 16384) & 0x7FFF) | 0x8000,
                       round(z * 32767), round(w * 32767))


def test_first_pose_reads_every_kind():
    a = 0.3
    q = (math.sin(a) * 0.6, -math.sin(a) * 0.8, 0.0, math.cos(a))
    keys = (packed(q) + struct.pack(">3f", 0.0, 0.87, 0.1)      # 0x01, 0x02
            + struct.pack(">3f", 0.034, 0.175, -0.003)            # 0x12
            + struct.pack(">4h", -16384, -16384, -16384, 16384))  # 0x31
    data = make_anm([(3, anim.ROT), (2, anim.TRANS), (16, anim.FIXED_TRANS),
                     (16, anim.FIXED_ROT)], keys)
    an = anim.Animation.parse(data, "t.anm")
    assert an.frames == 2 and an.rate == 30.0 and len(an.tracks) == 4
    assert an.keys(0) == [0, 1]
    pose = an.first_pose()
    assert all(abs(u - v) < 2e-4 for u, v in zip(pose.rotations[3], q))
    assert pose.rotations[16] == pytest.approx((-0.5, -0.5, -0.5, 0.5), abs=1e-4)
    assert pose.translations[2] == pytest.approx((0.0, 0.87, 0.1))
    assert pose.translations[16] == pytest.approx((0.034, 0.175, -0.003), abs=1e-6)


def test_data_offset_zero_when_too_far():
    """Long cutscenes store 0 when the first keys sit past 0xFFFF: computed from the mask."""
    keys = struct.pack(">4h", 0, 0, 0, 32767)
    data = make_anm([(1, anim.FIXED_ROT)], keys, offset0=True)
    assert anim.Animation.parse(data).first_pose().rotations[1] == pytest.approx((0, 0, 0, 1))


def test_bad_files_are_named():
    with pytest.raises(FormatError, match="too short"):
        anim.Animation.parse(b"\0" * 8)
    data = bytearray(make_anm([(1, anim.FIXED_ROT)], struct.pack(">4h", 0, 0, 0, 32767)))
    data[0x14 + 3] = 0x77                       # FF 00 broken
    with pytest.raises(FormatError, match="FF 00"):
        anim.Animation.parse(bytes(data))
    data = make_anm([(1, 0x44)], b"\0" * 8)
    with pytest.raises(FormatError, match="unknown track kind"):
        anim.Animation.parse(data)
    data = make_anm([(1, anim.FIXED_ROT)], struct.pack(">4h", 9000, 9000, 9000, 9000))
    with pytest.raises(FormatError, match="unit quaternion"):
        anim.Animation.parse(data).first_pose()


def test_part_of():
    assert anim.part_of("data/anim/default.big/hand.big/male_hand_fist_pose.anm") == "hand"
    assert anim.part_of("data/streamedassets.big/anm_Sword.big/fullbody.big/x.anm") == "fullbody"
    assert anim.part_of("data/x.anm") is None


def test_decompose_and_placement():
    from dr2kit.convert import holding
    from dr2kit.formats.scene import mat_mul, trs_matrix
    q = (0.0, math.sin(0.4), 0.0, math.cos(0.4))
    hand = trs_matrix((0.3, 0.9, 0.1), q, (1, 1, 1))
    grip = trs_matrix((0.0, 0.0, -0.11), (0, 0, 0, 1), (1, 1, 1))
    place = holding.item_placement(hand, grip)
    at_grip = mat_mul(place, grip)              # the grip node lands on the hand
    assert [round(at_grip[r][3], 6) for r in range(3)] == [0.3, 0.9, 0.1]
    t, rot, s = holding.decompose(place)
    assert s == pytest.approx([1, 1, 1]) and rot == pytest.approx(list(q), abs=1e-9)
    assert holding.flat(place)[12:15] == pytest.approx(t)


def test_assembler_poses_nodes():
    from dr2kit.convert.gltf import Assembler, Glb, GlbBuilder
    b = GlbBuilder()
    b.add("nodes", {"name": "dummy01.Bone", "rotation": [0, 0, 0, 1]})
    b.gltf["scenes"][0]["nodes"].append(0)
    asm = Assembler()
    asm.add(b.to_bytes(), [{"name": "part"}], pose={"dummy01.bone": {"rotation": (0, 1, 0, 0)}})
    nodes = Glb.parse(asm.to_bytes()).gltf["nodes"]
    assert next(n for n in nodes if n["name"] == "dummy01.Bone")["rotation"] == [0, 1, 0, 0]


def test_glb_with_picture():
    from dr2kit.convert import png
    from dr2kit.convert.gltf import Glb, GlbBuilder, glb_with_picture
    b = GlbBuilder()
    b.add("materials", {"name": "m"})
    pic = png.encode(png.Image(1, 1, b"\xff\0\0\xff"))
    g = Glb.parse(glb_with_picture(b.to_bytes(), pic))
    assert g.gltf["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"] == {"index": 0}
    v = g.gltf["bufferViews"][g.gltf["images"][0]["bufferView"]]
    assert g.bin[v["byteOffset"]:v["byteOffset"] + v["byteLength"]] == pic


# --- the real games --------------------------------------------------------------------

@pytest.mark.gamedata
@pytest.mark.parametrize("game", ["cz", "cw"])
def test_idles_from_the_game_graph(game, game_root):
    """Each kind of item gets its idle from sgraph.txt (docs/formats.md §Animations)."""
    from dr2kit.container.vpath import AssetTree
    from dr2kit.convert import holding
    tree = AssetTree(game_root(game))
    expect = {0: "male_idle_combat.anm", 4: "male_lgbox_idle.anm", 13: "male_idle_smallbox.anm",
              14: "male_idle_thrust.anm", 15: "male_idle_samurai_sword.anm",
              -1: "male_idle_combat.anm"}
    for value, name in expect.items():
        idle = holding.item_idle(tree, idle_value=value, hand_value=8)
        assert idle.fullbody.endswith("fullbody.big/" + name), (value, idle)
        assert idle.root and idle.root.endswith("root.big/" + name)
        assert idle.hand.endswith("male_hand_hold_pole_pose.anm")
    parts = holding.outfit_parts(tree)
    assert any("/chest_" in p for p in parts) and any("/feet_" in p for p in parts)


@pytest.mark.gamedata
@pytest.mark.parametrize("game,item", [("cz", "Broadsword"), ("cw", "Katana")])
def test_chuck_holds_the_sword(game, item, game_root):
    """Posed: hips lowered by the idle; the sword's grip node on his right-hand prop node,
    which hangs at his side (below the chest, right of the middle)."""
    from dr2kit.container.vpath import AssetTree
    from dr2kit.convert import holding, placed
    from dr2kit.formats.scene import Scene, mat_mul
    tree = AssetTree(game_root(game))
    models = placed.ItemModels(tree)
    chuck = holding.posed_chuck(tree, models.blocks[item.lower()])
    assert chuck.idle.fullbody.endswith("male_idle_combat.anm")
    assert len(chuck.pose) == len(chuck.rest.nodes) == 98
    root = chuck.posed.by_name("dummy01.root")
    assert root.translation[1] < chuck.rest.by_name("dummy01.root").translation[1]
    vp = models.resolve(item)
    scene = Scene.parse(tree.resolve(vp).data(), vp)
    place = holding.item_placement(chuck.hand, holding.grip_matrix(scene))
    grip = mat_mul(place, holding.grip_matrix(scene))
    x, y, z = (grip[r][3] for r in range(3))
    assert -0.45 < x < -0.15 and 0.6 < y < 1.1 and abs(z) < 0.4, (x, y, z)


@pytest.mark.gamedata
def test_every_gameplay_animation_reads(game_root):
    from dr2kit.container.vpath import AssetTree
    tree = AssetTree(game_root("cz"))
    arc = tree.open_archive("data/anim/default.big/hand.big")
    for e in arc.entries:
        anim.Animation.parse(e.data(), e.name).first_pose()

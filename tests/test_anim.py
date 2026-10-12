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
    """An 8-byte rotation key: x 16 bits (/32767) across the two first words, y 15 bits
    (/16383), z, w 16 bits (/32767)."""
    x, y, z, w = q
    v = ((round(x * 32767) & 0xFFFF) << 47 | (round(y * 16383) & 0x7FFF) << 32
         | (round(z * 32767) & 0xFFFF) << 16 | (round(w * 32767) & 0xFFFF))
    return v.to_bytes(8, "big")


def delta(dx: int, dy: int, dz: int, dw: int) -> bytes:
    """A 4-byte rotation key: the change from the previous key (x, z, w /12700, y /6300)."""
    return (1 << 31 | (dx & 0xFF) << 23 | (dy & 0x7F) << 16 | (dz & 0xFF) << 8
            | (dw & 0xFF)).to_bytes(4, "big")


def packed_trans(p) -> bytes:
    """An 8-byte translation key: three 21-bit numbers × 300 / (2²⁰ − 1), top bit set."""
    v = 1 << 63
    for sh, c in zip((42, 21, 0), p):
        v |= (round(c / anim.TRANS_SCALE) & 0x1FFFFF) << sh
    return v.to_bytes(8, "big")


def make_keyed(tracks, first: bytes, keyrows, later: bytes, rate: float = 30.0) -> bytes:
    """An ``.anm`` with a key mask: ``keyrows`` = per frame, the set of track numbers with
    a key; ``later`` = the later keys in the game's order."""
    n, frames = len(tracks), len(keyrows)
    mask_off = 0x14 + 2 * n + 2
    width = (n + 7) // 8
    data_off = (mask_off + frames * width + 3) // 4 * 4
    head = struct.pack(">IffHHHH", 0x24F628C0, (frames - 1) / rate, rate, mask_off,
                       data_off, frames, n)
    table = b"".join(bytes((node, kind)) for node, kind in tracks) + b"\xff\x00"
    mask = b""
    for row in keyrows:
        bits = bytearray(width)
        for t in row:
            bits[t >> 3] |= 1 << (t & 7)
        mask += bytes(bits)
    pad = b"\0" * (data_off - mask_off - len(mask))
    return head + table + mask + pad + first + later


def test_first_pose_reads_every_kind():
    a = 0.3
    q = (math.sin(a) * 0.6, -math.sin(a) * 0.8, 0.0, math.cos(a))
    keys = (struct.pack(">3f", 0.0, 0.87, 0.1) + packed(q)      # 0x02, 0x01
            + struct.pack(">3f", 0.034, 0.175, -0.003)            # 0x12
            + struct.pack(">4h", -16384, -16384, -16384, 16384))  # 0x31
    data = make_anm([(2, anim.TRANS), (3, anim.ROT), (16, anim.FIXED_TRANS),
                     (16, anim.FIXED_ROT)], keys)
    an = anim.Animation.parse(data, "t.anm")
    assert an.frames == 2 and an.rate == 30.0 and len(an.tracks) == 4
    assert an.keys(1) == [0, 1]
    pose = an.first_pose()
    assert all(abs(u - v) < 2e-4 for u, v in zip(pose.rotations[3], q))
    assert pose.rotations[16] == pytest.approx((-0.5, -0.5, -0.5, 0.5), abs=1e-4)
    assert pose.translations[2] == pytest.approx((0.0, 0.87, 0.1))
    assert pose.translations[16] == pytest.approx((0.034, 0.175, -0.003), abs=1e-6)


def test_decode_reads_every_key_in_the_games_order():
    """Two animated tracks; the later keys are stored as each is needed: at frame f, for
    every track with a key at f, its next key (4-aligned); a 4-byte rotation key is a
    change from the previous key, a packed translation key the position itself."""
    q0 = (0.0, 0.0, 0.0, 1.0)
    first = struct.pack(">3f", 0.0, 1.0, 0.0) + packed(q0)
    # keys: translation (track 0) at frames 0, 1, 3; rotation (track 1) at 0, 1, 2, 3
    rows = [{0, 1}, {0, 1}, {1}, {0, 1}]
    q2 = (0.0, math.sin(0.2), 0.0, math.cos(0.2))
    later = (packed_trans((0.0, 1.0, 0.5))      # frame 0: track 0's next key (frame 1)
             + delta(0, 6, 0, 0)                # frame 0: track 1's next key (frame 1)
             + struct.pack(">3f", 0.0, 1.0, 2.0)   # frame 1: track 0's next (frame 3), floats
             + packed(q2)                       # frame 1: track 1's next (frame 2)
             + delta(0, 0, 0, 0))               # frame 2: track 1's next (frame 3)
    data = make_keyed([(5, anim.TRANS), (7, anim.ROT)], first, rows, later)
    clip = anim.Animation.parse(data, "k.anm").decode()
    tr, rot = clip.channels
    assert tr.frames == [0, 1, 3] and rot.frames == [0, 1, 2, 3]
    assert tr.values[1] == pytest.approx((0.0, 1.0, 0.5), abs=3e-4)
    assert tr.values[2] == pytest.approx((0.0, 1.0, 2.0))
    assert rot.values[1][1] == pytest.approx(6 / 6300, abs=1e-6)
    assert rot.values[2] == pytest.approx(q2, abs=1e-4)
    assert rot.values[3] == pytest.approx(q2, abs=1e-4)
    # between keys: interpolated
    assert clip.pose(2).translations[5] == pytest.approx((0.0, 1.0, 1.25), abs=3e-4)
    assert clip.pose(1.5).rotations[7][1] == pytest.approx(
        anim.nlerp(rot.values[1], rot.values[2], 0.5)[1], abs=1e-9)
    with pytest.raises(FormatError, match="the keys end"):
        anim.Animation.parse(data + b"\0\0\0\0", "k.anm").decode()


def test_tracks_out_of_order_are_named():
    data = make_anm([(3, anim.ROT), (2, anim.TRANS)], packed((0, 0, 0, 1)) + b"\0" * 12)
    with pytest.raises(FormatError, match="kind order"):
        anim.Animation.parse(data)


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


def test_add_animation_moves_every_copy_of_a_node():
    """Chuck's parts each carry the rig: a clip moves every node of that name."""
    from dr2kit.convert import holding
    from dr2kit.convert.gltf import Assembler, Glb
    asm = Assembler()
    for part in ("chest", "feet"):
        g = asm.group(part)
        asm.b.gltf["nodes"][g]["children"] = [asm.b.add("nodes", {"name": "dummy01.Root"})]
    clp = {"length": 1.0, "nodes": {"dummy01.root": {
        "r": {"t": [0.0, 1.0], "v": [[0, 0, 0, 1], [0, 1, 0, 0]]},
        "p": {"t": [0.0], "v": [[0, 1, 0]]}}}}
    assert holding.add_animation(asm, "swing", clp) == 4
    js = Glb.parse(asm.to_bytes()).gltf
    an = js["animations"][0]
    assert an["name"] == "swing" and len(an["samplers"]) == 2
    roots = {i for i, n in enumerate(js["nodes"]) if n["name"] == "dummy01.Root"}
    assert {c["target"]["node"] for c in an["channels"]} == roots
    one_key = js["accessors"][an["samplers"][1]["input"]]
    assert one_key["count"] == 2 and one_key["max"] == [1.0]      # held over the clip


def test_companions_pair_fullbody_and_root():
    from dr2kit.convert import holding

    class Tree:
        def resolve(self, vp):
            if "missing" in vp:
                from dr2kit.errors import Dr2Error
                raise Dr2Error(vp)
            return type("N", (), {"vpath": vp})()
    t = Tree()
    assert holding.companions(t, "a/fullbody.big/x.anm") == ["a/fullbody.big/x.anm",
                                                             "a/root.big/x.anm"]
    assert holding.companions(t, "a/root.big/x.anm") == ["a/fullbody.big/x.anm",
                                                         "a/root.big/x.anm"]
    assert holding.companions(t, "missing/fullbody.big/x.anm") == ["missing/fullbody.big/x.anm"]


@pytest.mark.gamedata
@pytest.mark.parametrize("game", ["cz", "cw"])
def test_animations_play_on_their_rig(game, game_root):
    """Every key read (phase 14): a sword attack plays on Chuck (the weapon's bank, with its
    root partner), a zombie animation on the zombie rig (its id in _ANIMCHANNELINFO_)."""
    from dr2kit.container.vpath import AssetTree
    from dr2kit.convert import holding, placed
    tree = AssetTree(game_root(game))
    ids = holding.skeleton_ids(tree)
    assert ids[0x24F628C0].endswith("playerfullbody.big")
    assert ids[0x45E6F8E0].endswith("zombiefullbody.big")
    block = placed.ItemModels(tree).blocks["broadsword" if game == "cz" else "katana"]
    moves = holding.item_moves(tree, block)
    assert moves and all(len(m.files) == 2 for m in moves)
    clp = holding.clip(tree, moves[0].files, rig=holding.RIG)
    assert len(clp["nodes"]) == 98 and clp["length"] > 0.5
    travel = clp["nodes"]["dummy01.root"]["p"]["v"]
    assert len(travel) > 2
    zombie = next(e.name for e in tree.open_archive("data/anim/zombies.big/fullbody.big").entries)
    assert holding.body_for(tree, f"data/anim/zombies.big/fullbody.big/{zombie}") \
        .endswith("zombiefullbody.big")


@pytest.mark.gamedata
def test_every_key_of_the_sword_bank_reads(game_root):
    from dr2kit.container.vpath import AssetTree
    tree = AssetTree(game_root("cz"))
    for part in ("fullbody", "root"):
        arc = tree.open_archive(f"data/streamedassets.big/anm_Sword.big/{part}.big")
        for e in arc.entries:
            c = anim.Animation.parse(e.data(), e.name).decode()
            assert all(ch.frames[-1] == c.frames - 1 for ch in c.channels
                       if ch.track.animated)

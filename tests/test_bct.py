"""Unit tests for dr2kit.formats.bct (synthetic textures only)."""

import struct

import pytest

from dr2kit.errors import FormatError
from dr2kit.formats import bct
from dr2kit.formats.bct import Bct, BctHeader, layout, model_data_size, packed_level_offset

from conftest import make_bct


def hand_header(**kw) -> bytes:
    """A 48-byte header packed by hand from docs/formats.md, not by BctHeader."""
    f = dict(flags=0xE2, w=256, h=256, fmt=0x08, ver=0x23, levels=7, bpp=4, w0c=0xBC3DCE20,
             size=0xF000, depth=0)
    f.update(kw)
    return (b"\x05\x01\x01" + bytes([f["flags"]]) + struct.pack(">HH", f["w"], f["h"])
            + bytes([f["fmt"], f["ver"], f["levels"], f["bpp"]])
            + struct.pack(">9I", f["w0c"], 0x18, 0, 0x30, f["size"], 0x30 + f["size"],
                          f["depth"], 0, 0))


def test_parse_hand_built_header():
    h = BctHeader.parse(hand_header())
    assert (h.width, h.height, h.levels, h.bpp) == (256, 256, 7, 4)
    assert h.format.name == "DXT1" and not h.is_cube and h.faces == 1
    assert h.data_offset == 0x30 and h.data_size == 0xF000 and h.data_end == 0xF030
    assert h.to_bytes() == hand_header()


def test_full_texture_round_trip():
    raw = hand_header() + bytes(range(256)) * (0xF000 // 256)
    tex = Bct.parse(raw, "hand")
    assert tex.to_bytes() == raw


@pytest.mark.parametrize("fmt,w,h,levels,size", [
    # (format, size, levels, payload size): the shapes most textures of both games have,
    # with their shipped payload sizes (formats.md, "Textures").
    ("DXT1", 256, 256, 7, 0xF000),
    ("DXT1", 512, 512, 8, 0x2F000),
    ("DXT1", 1024, 1024, 9, 0xAF000),
    ("DXT1", 16, 16, 3, 0x1000),
    ("DXT1", 64, 32, 4, 0x3000),
    ("DXT1", 128, 64, 1, 0x2000),
    ("DXT5", 80, 80, 1, 0x4000),
    ("DXT5", 32, 32, 1, 0x2000),
    ("DXN", 16, 8, 2, 0x2000),
    ("L8", 960, 956, 1, 921600),
])
def test_model_size_matches_shipped_shapes(fmt, w, h, levels, size):
    f = next(x for x in bct.FORMATS.values() if x.name == fmt)
    hdr = BctHeader(0xE2, w, h, f.code, 0x23, levels, f.bpp, 0)
    assert model_data_size(hdr) == size


def test_cube_layout():
    f = bct.FORMATS[0x08]
    hdr = BctHeader(0xEA, 128, 128, f.code, 0x23, 6, 4, 0, depth_minus_1=5)
    assert hdr.is_cube and hdr.faces == 6
    lv = layout(hdr)
    assert len(lv) == 6 * 6
    # Level 0: six faces of 8 KB each, one after the other; then level 1 starts.
    assert [x.offset for x in lv if x.level == 0] == [i * 0x2000 for i in range(6)]
    assert min(x.offset for x in lv if x.level == 1) == 6 * 0x2000
    assert model_data_size(hdr) == 196608     # shipped size of the 128x128 cube maps


def test_packed_offsets():
    # Square: across (x); wide: down (y); tall: across. Verified on real data (formats.md).
    assert [packed_level_offset(16, 16, m) for m in range(3)] == [(16, 0), (8, 0), (4, 0)]
    assert packed_level_offset(16, 8, 0) == (0, 16)
    assert packed_level_offset(4, 16, 0) == (16, 0)
    assert packed_level_offset(256, 256, 3) is None
    assert packed_level_offset(256, 256, 4) == (16, 0)


def test_tiled_offset_is_a_permutation_of_one_tile():
    # For 4-, 8- and 16-byte units a 32x32-unit tile fills exactly 1024 slots; for 1- and
    # 2-byte units it is spread wider but still never maps two units to one slot.
    for l2 in (0, 1, 2, 3, 4):
        offs = {bct.tiled_offset(x, y, 32, l2) for x in range(32) for y in range(32)}
        assert len(offs) == 1024
        if l2 >= 2:
            assert offs == set(range(1024))


def test_mip_offsets_256_dxt1():
    tex = Bct.parse(make_bct("DXT1", 256, 256, 7))
    levels = tex.levels()
    assert [lv.offset for lv in levels][:5] == [0, 0x8000, 0xA000, 0xC000, 0xE000]
    assert all(lv.packed for lv in levels[4:]) and not levels[3].packed
    assert [(lv.tile_x, lv.tile_y) for lv in levels[4:]] == [(4, 0), (2, 0), (1, 0)]


@pytest.mark.parametrize("use_numpy", [True, False])
def test_untile_then_tile_gives_back_the_payload(monkeypatch, use_numpy):
    if not use_numpy:
        monkeypatch.setattr(bct, "_np", None)
    raw = make_bct("DXT5", 64, 32, 4)
    tex = Bct.parse(raw)
    copy = Bct(tex.header, bytearray(len(tex.payload)))
    for lv in tex.levels():
        rows = tex.untile(lv)
        assert len(rows) == lv.units_w * lv.units_h * 16
        copy.set_level(lv, rows)
    # Every byte the layout uses is restored (the rest was zero in the copy).
    used = bytearray(len(tex.payload))
    for lv in tex.levels():
        Bct(tex.header, used).set_level(lv, b"\xff" * (lv.units_w * lv.units_h * 16))
    for i, u in enumerate(used):
        if u:
            assert copy.payload[i] == tex.payload[i]


def test_numpy_and_pure_untile_agree(monkeypatch):
    tex = Bct.parse(make_bct("DXT1", 128, 64, 6))
    fast = [tex.untile(lv) for lv in tex.levels()]
    monkeypatch.setattr(bct, "_np", None)
    assert [tex.untile(lv) for lv in tex.levels()] == fast


def test_swap_is_its_own_inverse():
    data = bytes(range(64))
    for f in bct.FORMATS.values():
        assert bct.swap_to_big(bct.swap_to_little(data, f), f) == data
    assert bct.swap_to_little(b"\x01\x02\x03\x04", bct.FORMATS[0x08]) == b"\x02\x01\x04\x03"
    assert bct.swap_to_little(b"\x01\x02\x03\x04", bct.FORMATS[0x00]) == b"\x04\x03\x02\x01"


@pytest.mark.parametrize("damage,match", [
    (lambda r: b"\x05\x01\x02" + r[3:], "magic"),
    (lambda r: r[:-1], "ends at"),
    (lambda r: r[:8] + b"\x77" + r[9:], "unknown texture format"),
    (lambda r: r[:11] + b"\x08" + r[12:], "bits per pixel"),
    (lambda r: r[:3] + b"\xea" + r[4:], "cube"),
    (lambda r: r[:10], "shorter"),
])
def test_damaged_textures_are_refused(damage, match):
    raw = hand_header() + bytes(0xF000)
    with pytest.raises(FormatError, match=match):
        Bct.parse(damage(raw), "bad")


def test_payload_too_small_for_its_layout():
    raw = hand_header(size=0x1000) + bytes(0x1000)
    with pytest.raises(FormatError, match="layout needs"):
        Bct.parse(raw, "small")

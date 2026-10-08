"""Unit tests for dr2kit.convert (dxt, png, texture) on synthetic images."""

import struct
import sys
import zlib

import pytest

from dr2kit.convert import dxt, png, texture
from dr2kit.convert.png import Image
from dr2kit.formats import bct
from dr2kit.formats.bct import Bct

from conftest import make_bct


def gradient(w: int, h: int, alpha: bool = False) -> bytes:
    out = bytearray()
    for y in range(h):
        for x in range(w):
            out += bytes((x * 255 // max(1, w - 1), y * 255 // max(1, h - 1),
                          (x + y) * 127 // max(1, w + h - 2),
                          (x * 255 // max(1, w - 1)) if alpha else 255))
    return bytes(out)


# ---- dxt -----------------------------------------------------------------------------------

def test_dxt1_block_by_hand():
    # c0 = pure red (0xF800), c1 = pure blue (0x001F), c0 > c1: four colours.
    # Indices: texel 0 -> 0 (red), texel 1 -> 1 (blue), texel 2 -> 2 (2/3 red), rest 3.
    bits = 0 | (1 << 2) | (2 << 4) | sum(3 << (2 * t) for t in range(3, 16))
    block = struct.pack("<HHI", 0xF800, 0x001F, bits)
    px = dxt.decode("DXT1", block, 4, 4)
    assert px[0:4] == bytes((255, 0, 0, 255))
    assert px[4:8] == bytes((0, 0, 255, 255))
    assert px[8:12] == bytes((170, 0, 85, 255))
    assert px[12:16] == bytes((85, 0, 170, 255))


def test_dxt1_three_colour_mode_is_transparent_black():
    block = struct.pack("<HHI", 0x001F, 0xF800, 0xFFFFFFFF)   # c0 <= c1, all index 3
    assert dxt.decode("DXT1", block, 4, 4)[:4] == bytes((0, 0, 0, 0))


@pytest.mark.parametrize("fmt", ["DXT1", "DXT5", "DXN"])
def test_numpy_and_pure_decoders_agree(monkeypatch, fmt):
    data = bytes((i * 131 + 7) & 0xFF for i in range(dxt.BLOCK_BYTES[fmt] * 6))
    fast = dxt.decode(fmt, data, 12, 8)
    monkeypatch.setattr(dxt, "np", None)
    assert dxt.decode(fmt, data, 12, 8) == fast


@pytest.mark.parametrize("use_numpy", [True, False])
@pytest.mark.parametrize("fmt", ["DXT1", "DXT5", "DXN"])
def test_encode_solid_colour_is_exact(monkeypatch, fmt, use_numpy):
    if not use_numpy:
        monkeypatch.setattr(dxt, "np", None)
    # A colour exactly representable in RGB565 once expanded by bit replication
    # (31 -> 255, 62 -> 251, 1 -> 8), and any alpha / channel value for BC4.
    img = bytes((255, 251, 8, 200)) * 64
    out = dxt.decode(fmt, dxt.encode(fmt, img, 8, 8), 8, 8)
    if fmt == "DXN":
        assert out[0::4] == img[0::4] and out[1::4] == img[1::4]
    elif fmt == "DXT1":
        assert out[0::4] == img[0::4] and out[1::4] == img[1::4] and out[2::4] == img[2::4]
    else:
        assert out == img


@pytest.mark.parametrize("fmt,limit", [("DXT1", 6), ("DXT5", 6), ("DXN", 3)])
def test_encode_gradient_error_is_small(fmt, limit):
    img = gradient(64, 64, alpha=(fmt == "DXT5"))
    out = dxt.decode(fmt, dxt.encode(fmt, img, 64, 64), 64, 64)
    chans = [0, 1] if fmt == "DXN" else [0, 1, 2, 3]
    err = [abs(a - b) for i, (a, b) in enumerate(zip(img, out)) if i % 4 in chans]
    assert sum(err) / len(err) < limit


def test_dxt1_alpha_becomes_transparent_texels():
    img = bytearray(bytes((200, 100, 50, 255)) * 16)
    img[3] = 0                                   # first pixel transparent
    out = dxt.decode("DXT1", dxt.encode("DXT1", bytes(img), 4, 4), 4, 4)
    assert out[3] == 0 and all(a == 255 for a in out[7::4])


@pytest.mark.parametrize("use_numpy", [True, False])
@pytest.mark.parametrize("fmt", ["DXT1", "DXT5", "DXN"])
def test_reference_blocks_are_kept_when_pixels_match(monkeypatch, fmt, use_numpy):
    if not use_numpy:
        monkeypatch.setattr(dxt, "np", None)
    # Arbitrary blocks (not what our encoder would produce), decoded then re-encoded.
    ref = bytes((i * 89 + 3) & 0xFF for i in range(dxt.BLOCK_BYTES[fmt] * 4))
    px = dxt.decode(fmt, ref, 8, 8)
    assert dxt.encode(fmt, px, 8, 8, reference=ref) == ref
    # Change one pixel: only that block may differ.
    edited = bytearray(px)
    edited[0:3] = bytes((0, 255, 0)) if px[0:3] != bytes((0, 255, 0)) else bytes((255, 0, 0))
    out = dxt.encode(fmt, bytes(edited), 8, 8, reference=ref)
    n = dxt.BLOCK_BYTES[fmt]
    assert out[n:] == ref[n:]


# ---- png ------------------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["RGBA", "RGB", "L"])
def test_png_round_trip_pure(mode):
    img = Image(7, 5, gradient(7, 5, alpha=True))
    back = png.decode_pure(png.encode(img, mode))
    if mode == "RGBA":
        assert back.rgba == img.rgba
    elif mode == "RGB":
        assert back.rgba[0::4] == img.rgba[0::4] and back.rgba[3::4] == b"\xff" * 35
    else:
        assert back.rgba[0::4] == img.rgba[0::4] == back.rgba[2::4]


def test_png_encode_without_numpy(monkeypatch):
    img = Image(5, 3, gradient(5, 3, alpha=True))
    expected = png.encode(img)
    monkeypatch.setitem(sys.modules, "numpy", None)
    assert png.encode(img) == expected


def test_png_palette_and_filters_by_hand():
    # A 2x2 palette image, 8-bit, with a tRNS entry, rows filtered "sub" and "paeth".
    pal = bytes((10, 20, 30, 200, 100, 0))
    rows = b"\x01" + bytes((0, 1)) + b"\x04" + bytes((1, 255))   # sub: 0,1 ; paeth: 1,0
    def chunk(k, b):
        return struct.pack(">I", len(b)) + k + b + struct.pack(">I", zlib.crc32(k + b))
    data = (png.SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 3, 0, 0, 0))
            + chunk(b"PLTE", pal) + chunk(b"tRNS", b"\x80")
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    img = png.decode_pure(data)
    assert img.rgba == bytes((10, 20, 30, 128, 200, 100, 0, 255,
                              200, 100, 0, 255, 10, 20, 30, 128))


def test_png_refuses_garbage():
    from dr2kit.errors import FormatError
    with pytest.raises(FormatError):
        png.decode(b"not a png at all")


# ---- texture (bct <-> image) -------------------------------------------------------------

@pytest.mark.parametrize("fmt,w,h,levels,cube", [
    ("DXT1", 64, 64, 5, False), ("DXT5", 32, 16, 3, False), ("DXN", 16, 16, 3, False),
    ("A8R8G8B8", 8, 8, 4, False), ("L8", 40, 24, 1, False), ("DXT1", 16, 16, 3, True),
])
def test_unchanged_export_imports_to_identical_bytes(fmt, w, h, levels, cube):
    raw = make_bct(fmt, w, h, levels, cube=cube)
    tex = Bct.parse(raw)
    img = texture.to_image(tex)
    assert (img.width, img.height) == (w * (6 if cube else 1), h)
    assert texture.replace_image(tex, img).to_bytes() == raw
    # Every level, decoded then encoded, gives back the stored units (the census gate).
    for lv in tex.levels():
        assert texture.encode_level(tex, lv, texture.decode_level(tex, lv)) == tex.untile(lv)


def test_edited_image_changes_pixels_and_rebuilds_mips():
    tex = Bct.parse(make_bct("DXT1", 64, 64, 5))
    red = Image(64, 64, bytes((255, 0, 0, 255)) * 64 * 64)
    new = texture.replace_image(tex, red)
    assert texture.to_image(new).rgba == red.rgba
    for lv in new.levels():
        px = texture.decode_level(new, lv)
        assert px[0:4] == bytes((255, 0, 0, 255))
    assert len(new.to_bytes()) == len(tex.to_bytes())


def test_wrong_size_is_refused():
    from dr2kit.errors import FormatError
    tex = Bct.parse(make_bct("DXT1", 64, 64, 1))
    with pytest.raises(FormatError, match="needs exactly 64x64"):
        texture.replace_image(tex, Image(32, 32, bytes(32 * 32 * 4)))


def test_downsample_box_filter():
    img = bytes((0, 0, 0, 255, 255, 255, 255, 255) * 2)    # 2x2: black, white / black, white
    assert texture.downsample(img, 2, 2, 1, 1) == bytes((128, 128, 128, 255))

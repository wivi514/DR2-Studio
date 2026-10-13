"""Shader bank descriptions (`dr2kit.formats.shaderbank`, phase 15), on hand-made bytes."""

import struct

import pytest

from dr2kit.errors import FormatError
from dr2kit.formats import shaderbank as sb


def text(s: str) -> bytes:                      # .sdo / .pdo text: length counts the NUL
    raw = s.encode() + b"\0"
    return struct.pack(">I", len(raw)) + raw.ljust((len(raw) + 3) & ~3, b"\0")


def sdo() -> bytes:
    recs = struct.pack(">6I", 0, 0x200, 0x651BA6C0, 0, 0xE776BB80, 0) + \
        struct.pack(">6I", 0, 0x800, 0x5E69BC40, 0, sb.NONE, 0)
    return struct.pack(">3I", 0x48C6E780, sb.NONE, 2) + recs + text("ZombieGlow") + \
        struct.pack(">I", 3) + text("Default")


def param(name, h, number, typ=4, regs=1, slider=False) -> bytes:
    flags = b"\x00\x01\x00\x00" if slider else b"\x01\x00\x00\x00"
    out = text(name) + struct.pack(">5I", h, number, 0, typ, regs) + flags
    if slider:
        out += struct.pack(f">{1 + 3 * typ}I", *range(1 + 3 * typ)) + text(name[1:] + " label")
    return out


def pdo() -> bytes:
    return struct.pack(">II", 0xE776BB80, 2) + param("gGlowScale", 0xC1A23FC0, 187, 1, 1, True) \
        + param("gMiscParameters", 0x6C51E580, 16) + struct.pack(">II", 0, 0xE776BB80)


def test_description_round_trip_and_programs():
    d = sdo()
    s = sb.Description.parse(d)
    assert s.name == "ZombieGlow" and s.to_bytes() == d
    assert s.programs() == ({0x651BA6C0, 0x5E69BC40}, {0xE776BB80})
    s.passes[0].ps = 0x12345660
    assert sb.Description.parse(s.to_bytes()).passes[0].ps == 0x12345660


def test_pixel_parameters_round_trip_with_slider():
    d = pdo()
    pf = sb.ParamFile.parse_pdo(d)
    assert [(p.name, p.number) for p in pf.params] == [("gGlowScale", 187),
                                                       ("gMiscParameters", 16)]
    assert pf.params[0].label == "GlowScale label" and len(pf.params[0].slider) == 4
    assert pf.to_bytes() == d
    pf.params[0].number = 177
    assert sb.ParamFile.parse_pdo(pf.to_bytes()).params[0].number == 177


def test_vertex_parameters_keep_their_header():
    own = 0xA07A5E80
    d = b"HEAD" * 3 + struct.pack(">II", own, 1) + param("gEyeSpaceDepth", 0x3D835D00, 195) + \
        struct.pack(">I", 0)
    pf = sb.ParamFile.parse_vdo(d, own)
    assert pf.head == b"HEAD" * 3 and pf.params[0].number == 195 and pf.to_bytes() == d


def test_bad_files_say_why():
    with pytest.raises(FormatError, match="left after"):
        sb.ParamFile.parse_pdo(pdo() + b"\0\0\0\0")
    with pytest.raises(FormatError, match="not its hash"):
        sb.ParamFile.parse_pdo(pdo()[:-4] + b"\0\0\0\1")


def test_string_table_and_add():
    st = sb.StringTable(["", "PosUVFullScreen.bvd", "Blur.bpd"])
    raw = st.to_bytes()
    assert raw[:12] == struct.pack(">3I", 3, 0, 0)     # the empty first entry
    assert sb.StringTable.parse(raw).strings == st.strings
    assert st.add(["Blur.bpd", "gGlowScale", "gGlowScale"]) == ["gGlowScale"]
    assert sb.StringTable.parse(st.to_bytes()).strings[-1] == "gGlowScale"

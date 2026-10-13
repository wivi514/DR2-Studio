"""360 shader programs' constants (`dr2kit.formats.xenos`, phase 15), on hand-made bytes."""

import struct

import pytest

from dr2kit.errors import FormatError
from dr2kit.formats import xenos


def program(src1: int, src3: int, scalar_op: int = 0, literal: int = 252) -> bytes:
    """A pixel shader: a constant table naming gFog (c19, 2 registers) and gDebug (c21),
    a literal at ``literal``, one exec of one ALU instruction reading c``src1`` and
    c``src3`` (src2 a temp)."""
    names = b"gFog\0gDebug\0\0\0"
    head = 0x24
    ct = head                                      # u32 size, then the D3DX table
    table_at = ct + 4
    info = 28                                      # after the 7-word table header
    consts = struct.pack(">IHHHHII", info + 40, 2, 19, 2, 0, 0, 0) + \
        struct.pack(">IHHHHII", info + 45, 2, 21, 1, 0, 0, 0)
    table = struct.pack(">7I", 0, 0, 0, 2, info, 0, 0) + consts + names
    dt = table_at + len(table)
    defs = struct.pack(">5I", 0, 0, 0, 0, 12) + struct.pack(">HHI", 256 + literal, 4, 0) + b"\0" * 4
    sh = dt + len(defs)
    virtual = sh + 8
    # microcode: one CF pair (exec at address 1, 1 instruction, ALU), then the ALU word
    exec_lo = 1 | (1 << 12)                        # address 1, count 1, sequence 0 (ALU)
    exec_hi = 2 << 12                              # exec end
    cf = struct.pack(">3I", exec_lo, exec_hi, 0)
    w0 = scalar_op << 26
    w2 = (src1 << 16) | (5 << 8) | src3 | (1 << 30)    # src2 is temp r5 (select 1)
    alu = struct.pack(">3I", w0, 0, w2)
    code = cf + alu
    shader = struct.pack(">II", 0, len(code))
    container = struct.pack(">9I", 0x102A1100, virtual, len(code), 0, ct, dt, sh, 0, 0)
    return container + struct.pack(">I", len(table)) + table + defs + shader + code


def alu_word2(d: bytes) -> int:
    return struct.unpack_from(">I", d, len(d) - 4)[0]


def test_constants_and_literals():
    d = program(19, 21)
    cs = xenos.constants(d)
    assert [(c.name, c.set, c.register, c.count) for c in cs] == \
        [("gFog", "float4", 19, 2), ("gDebug", "float4", 21, 1)]
    assert xenos.literals(d) == [252]
    assert len(xenos.alu_instructions(d)) == 1


def test_remap_moves_operands_and_table():
    d = program(20, 21)                            # gFog[1] and gDebug
    out, unknown = xenos.remap_constants(d, {19: 18, 20: 19, 21: 20})
    assert unknown == []
    w2 = alu_word2(out)
    assert (w2 >> 16) & 0xFF == 19 and w2 & 0xFF == 20
    assert (w2 >> 8) & 0xFF == 5                   # the temp register is not a constant
    assert [c.register for c in xenos.constants(out)] == [18, 20]
    assert len(out) == len(d)


def test_scalar_constant_ops_read_src3_as_a_constant():
    d = program(19, 21, scalar_op=42)              # mulsc: src3 is a constant either way
    w2 = struct.unpack_from(">I", d, len(d) - 4)[0] | (1 << 29)
    d = d[:-4] + struct.pack(">I", w2)
    out, _ = xenos.remap_constants(d, {21: 30})
    assert alu_word2(out) & 0xFF == 30


def test_unnamed_registers_are_reported():
    _, unknown = xenos.remap_constants(program(19, 40), {})
    assert unknown == [40]
    _, unknown = xenos.remap_constants(program(19, 252), {})
    assert unknown == []                           # a literal


def test_not_a_shader():
    with pytest.raises(FormatError):
        xenos.constants(b"\0" * 64)

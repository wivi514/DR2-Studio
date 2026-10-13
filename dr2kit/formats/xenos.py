"""Xbox 360 shader programs (``.vo`` / ``.po``): the constant table, and moving constants
to other registers (phase 15, docs/formats.md §"Across the games: constant registers").

Why: a program brought from the other game reads its constants from **the registers its
own game's engine fills**. The two games number their shader parameters differently
(Case West inserted ``gPowerOffParameter`` at pixel register 17, so its
``gBumpLightParameters``, ``gFogParameters``, ``gShaderDebugParameters``… sit one higher
than Case Zero's), and each engine writes every parameter at its own number. A Case West
pixel shader in Case Zero then read Case Zero's point light where it expects
``gShaderDebugParameters`` (c21), took its debug branch and drew flat white (the user's
U1, 2026-10-13). So a brought program gets **its constant operands renumbered** to the
target's registers, the same way its ``.pdo`` is (`convert.shadercarry.number_map`).

Layout (big-endian; the field names follow the sibling XenosRecomp's ``shader.h`` /
``constant_table.h`` / ``shader_code.h``, whose decoder this mirrors):

* the container: ``u32 flags`` (``0x102A11xx``; bit 0 set = vertex shader), virtual
  size, physical size, ``u32``, the constant table's offset, the definition table's
  offset, the shader header's offset, two ``u32``;
* the constant table (D3DX ``CONSTANTTABLE`` behind a ``u32`` size): constants, each
  ``{u32 name offset, u16 register set (0 bool, 1 int4, 2 float4, 3 sampler), u16
  register index, u16 count, u16, u32 type info, u32 default}``, offsets from the table's
  start;
* the shader header: ``u32 physical offset, u32 size …``: the microcode sits at
  ``virtual size + physical offset``, 3 words per instruction; control-flow instructions
  (two per 3 words) first, then the exec blocks they point at. An exec's ``sequence``
  bits (2 per instruction) say fetch (bit set) or ALU;
* an ALU instruction (3 words, bit fields from the low bit up): word 1 holds
  ``const0Relative`` / ``const1Relative`` and the swizzles; word 2 the three source
  registers (8 bits each, ``src3`` lowest), the vector opcode and the three ``select``
  bits (bit 29 ``src3``, 30 ``src2``, 31 ``src1``): **a source whose select bit is 0
  is a constant**, its 8 bits the register. The scalar opcodes 42-47 (``mulsc``,
  ``addsc``, ``subsc``) read ``src3`` as a constant whatever its select bit.

A parameter the target's engine never writes can be pointed at one of the program's own
literals instead (`read_literal`: Case West's ``gPowerOffParameter`` read 0 in Case Zero and
switched off the Laser Sword's self-lit blade).

Literal constants (the definition table, ``c252``-``c255`` style) are the program's own
and are never moved.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from ..errors import FormatError

MAGIC = 0x102A1100
SETS = ("bool", "int4", "float4", "sampler")
SCALAR_CONST_OPS = range(42, 48)               # mulsc0/1, addsc0/1, subsc0/1
EXEC_OPS = {1, 2, 3, 4, 5, 6, 13, 14}          # exec, cond exec (pred) [end], pred clean


@dataclass
class Constant:
    """One entry of the constant table (``at``: its record's offset in the file)."""
    name: str
    set: str
    register: int
    count: int
    at: int


def _u32(d: bytes, o: int) -> int:
    return struct.unpack_from(">I", d, o)[0]


def _cstr(d: bytes, o: int) -> str:
    end = d.index(b"\0", o)
    return d[o:end].decode("latin-1")


def constants(d: bytes, where: str = "<shader>") -> list[Constant]:
    """The program's constant table."""
    if len(d) < 0x24 or (_u32(d, 0) & 0xFFFFFF00) != MAGIC:
        raise FormatError(f"{where}: not a 360 shader container")
    ct = _u32(d, 0x10)
    if not ct:
        return []
    base = ct + 4                                   # the table follows its u32 size
    n, info = _u32(d, base + 12), _u32(d, base + 16)
    out = []
    for i in range(n):
        at = base + info + i * 20
        name_off, rset, reg, count = struct.unpack_from(">IHHH", d, at)
        if rset > 3:
            raise FormatError(f"{where}: constant {i} has register set {rset}")
        out.append(Constant(_cstr(d, base + name_off), SETS[rset], reg, count, at))
    return out


def is_vertex(d: bytes) -> bool:
    return bool(_u32(d, 0) & 1)


def _code(d: bytes) -> tuple[int, int]:
    """(offset of the microcode, its size in bytes)."""
    sh = _u32(d, 0x18)
    return _u32(d, 4) + _u32(d, sh), _u32(d, sh + 4)


def alu_instructions(d: bytes) -> list[int]:
    """The file offsets of every ALU instruction, found the way the hardware does: the
    control-flow instructions' exec blocks and their sequence bits."""
    code, size = _code(d)
    words = lambda o: struct.unpack_from(">3I", d, code + o)          # noqa: E731
    end = size
    cfs = []
    o = 0
    while o < end and o + 12 <= size:
        w0, w1, w2 = words(o)
        for lo, hi in ((w0, w1 & 0xFFFF), ((w1 >> 16) | ((w2 << 16) & 0xFFFF0000), w2 >> 16)):
            op = (hi >> 12) & 0xF
            if op in EXEC_OPS:
                addr, count, seq = lo & 0xFFF, (lo >> 12) & 7, (lo >> 16) & 0xFFF
                cfs.append((addr, count, seq))
                if addr:
                    end = min(end, addr * 12)
        o += 12
    out = set()
    for addr, count, seq in cfs:
        for i in range(count):
            if not seq & (1 << (i * 2)):
                out.add(code + (addr + i) * 12)
    return sorted(out)


def constant_operands(d: bytes, at: int) -> list[tuple[int, int, int]]:
    """``(word offset, bit shift, register)`` of each constant source of the ALU
    instruction at ``at``."""
    w0, w1, w2 = struct.unpack_from(">3I", d, at)
    scalar_op = (w0 >> 26) & 0x3F
    out = []
    for shift, sel_bit in ((16, 31), (8, 30), (0, 29)):          # src1, src2, src3
        const = not (w2 >> sel_bit) & 1
        if shift == 0 and scalar_op in SCALAR_CONST_OPS:
            const = True
        if const:
            out.append((at + 8, shift, (w2 >> shift) & 0xFF))
    return out


def remap_constants(d: bytes, moves: dict[int, int], where: str = "<shader>") -> tuple[bytes, list[int]]:
    """``d`` with every float4 constant operand ``r`` read from ``moves[r]`` instead
    (registers not in ``moves`` stay), and the constant table's float4 entries moved
    with them. Returns the new bytes and the registers read that no table entry or
    literal names (``unknown``: reported by the caller)."""
    out = bytearray(d)
    table = [c for c in constants(d, where) if c.set == "float4"]
    named = {c.register + k for c in table for k in range(c.count)}
    unknown = set()
    for at in alu_instructions(d):
        for word_at, shift, reg in constant_operands(d, at):
            if reg not in named:
                unknown.add(reg)
            new = moves.get(reg, reg)
            if new != reg:
                if not 0 <= new < 256:
                    raise FormatError(f"{where}: constant register {new} out of range")
                w = struct.unpack_from(">I", out, word_at)[0]
                w = (w & ~(0xFF << shift)) | (new << shift)
                struct.pack_into(">I", out, word_at, w)
    for c in table:
        if c.register in moves:
            struct.pack_into(">H", out, c.at + 6, moves[c.register])
    return bytes(out), sorted(unknown - set(literals(d)))


def literals(d: bytes) -> list[int]:
    """Registers the program defines itself: the float4 literals of the definition table
    (``{u16 register, u16 count of floats, u32 physical offset}`` up to a 0 word; a pixel
    shader's registers are stored 256 higher, as XenosRecomp reads them)."""
    dt = _u32(d, 0x14)
    if not dt:
        return []
    base = 256 if not is_vertex(d) else 0
    out = []
    o = dt + 20
    while o + 8 <= len(d):
        w = _u32(d, o)
        if w == 0:
            break
        reg, count = w >> 16, w & 0xFFFF
        out += range(reg - base, reg - base + (count + 3) // 4)
        o += 8
    return out


def literal_values(d: bytes) -> dict[int, tuple[float, float, float, float]]:
    """The program's own float4 literals: register -> its four values (stored at the
    container's virtual size + each definition's physical offset)."""
    dt = _u32(d, 0x14)
    if not dt:
        return {}
    base = 256 if not is_vertex(d) else 0
    virtual = _u32(d, 4)
    out = {}
    o = dt + 20
    while o + 8 <= len(d):
        w = _u32(d, o)
        if w == 0:
            break
        reg, count = w >> 16, w & 0xFFFF
        phys = _u32(d, o + 4)
        for i in range((count + 3) // 4):
            out[reg - base + i] = struct.unpack_from(">4f", d, virtual + phys + 16 * i)
        o += 8
    return out


def read_literal(d: bytes, register: int, value: float, where: str = "<shader>") -> bytes:
    """``d`` with every constant operand reading ``register`` reading ``value`` instead:
    pointed at a component of one of the program's own literals that holds exactly that
    value, its swizzle set so every lane reads that component (the swizzle of lane ``i``
    is stored as ``(component - i) & 3``, 2 bits per lane, as XenosRecomp decodes it).
    For a parameter the target's engine never writes (Case West's
    ``gPowerOffParameter``: 0 there switched off every self-lit part). Raises
    `FormatError` when no literal holds the value."""
    spot = next(((r, c) for r, v in sorted(literal_values(d).items())
                 for c in range(4) if v[c] == value), None)
    if spot is None:
        raise FormatError(f"{where}: no literal holds {value}")
    reg, comp = spot
    swz = sum(((comp - i) & 3) << (2 * i) for i in range(4))
    out = bytearray(d)
    for at in alu_instructions(d):
        for word_at, shift, r in constant_operands(d, at):
            if r != register:
                continue
            w2 = struct.unpack_from(">I", out, word_at)[0]
            struct.pack_into(">I", out, word_at, (w2 & ~(0xFF << shift)) | (reg << shift))
            # the operand's swizzle sits in word 1 at the same shift (src1 16, src2 8, src3 0)
            w1 = struct.unpack_from(">I", out, at + 4)[0]
            struct.pack_into(">I", out, at + 4, (w1 & ~(0xFF << shift)) | (swz << shift))
    return bytes(out)

"""Shader constants: the `.po`/`.vo` constant table and the `.scv` value sets.

Why this exists: some materials don't keep their colour in a texture. Zombie clothing
(`ZombieCloth`) stores a *weight map* in its ``_cm1`` texture and gets its colours
from shader constants (``gBaseTextureColour``, ``gPattern1Colour``…) that the material's
**value set** supplies; a preview that shows ``_cm1`` as a colour map shows red and
purple zombies. To bake the real colour (`dr2kit.convert.material`), the toolkit needs
the value set's numbers *and* their names, and only the shader knows the names.

* **Shader container** (`.po` pixel / `.vo` vertex shaders in ``shaders/*-ps.big`` /
  ``-vs.big``, magic ``10 2A 11 xx``): the standard Xbox 360 D3D container. Its
  **constant table** (``D3DXSHADER_CONSTANTTABLE``, big-endian) lists every constant
  with its register set and register index (`constant_table`). Layout as read by
  XenosRecomp (``constant_table.h``, ``shader.h``): container word 4 = offset of a
  ``{u32 size; CONSTANTTABLE}`` block; name and info offsets are relative to the
  ``CONSTANTTABLE`` start.
* **Value set** (`.scv`, in each model's ``valuesets.big``, named by the hash a
  `MatArray` record stores, `scene.Material.valueset`): big-endian; ``u32 name length,
  name`` (``pro_zombie_cop_mtl_shirt.pdv``, NUL included, padded to 4 bytes),
  ``u32 own hash``, ``u32 0xFFFFFFFF``,
  ``u32 pixel shader`` (the `.po` entry name in hex), ``u32 count``, then ``count``
  records ``u32 2, u32 0, u32 n, u32 1, u32 register, u32 name hash, n × f32``. The
  register is the pixel-shader float4 register the values go to; its name comes from
  that shader's constant table. (Checked: all 7 registers of the cop shirt's value set
  name constants of its shader ``21b5af40.po``; the name hash is not the engine string
  hash, CRC-32 or FNV of the name.)

Facts and census: docs/formats.md §Materials: value sets.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from ..errors import FormatError

SHADER_MAGIC = b"\x10\x2a\x11"
REG_FLOAT4 = 2


@dataclass(frozen=True)
class Constant:
    name: str
    register_set: int        # 0 bool, 1 int4, 2 float4, 3 sampler
    register: int
    count: int


def constant_table(po: bytes, source: str = "<memory>") -> dict[str, Constant]:
    """``{name: Constant}`` from a shader container's constant table."""
    if po[:3] != SHADER_MAGIC or len(po) < 0x24:
        raise FormatError(f"{source}: not an Xbox 360 shader container")
    ct_off = struct.unpack_from(">I", po, 0x10)[0]
    base = ct_off + 4                       # CONSTANTTABLE, after its u32 size
    if base + 28 > len(po):
        raise FormatError(f"{source}: constant table offset {ct_off:#x} out of range")
    _size, _creator, _ver, n, info_off, _flags, _target = struct.unpack_from(">7I", po, base)
    out = {}
    for i in range(n):
        o = base + info_off + i * 20
        if o + 20 > len(po):
            raise FormatError(f"{source}: constant {i} of {n} runs past the end")
        name_off, rset, reg, cnt = struct.unpack_from(">IHHH", po, o)
        s = base + name_off
        name = po[s:po.index(b"\0", s)].decode("latin-1")
        out[name] = Constant(name, rset, reg, cnt)
    return out


@dataclass
class ValueSet:
    """A material's shader constants: ``values[register] = (name hash, floats)``."""
    name: str
    hash: int
    pixel_shader: int
    values: dict[int, tuple[int, tuple[float, ...]]] = field(default_factory=dict)

    @classmethod
    def parse(cls, data: bytes, source: str = "<memory>") -> "ValueSet":
        try:
            n = struct.unpack_from(">I", data, 0)[0]
            name = data[4:4 + n].split(b"\0", 1)[0].decode("latin-1")
            o = (4 + n + 3) & ~3                 # the name is padded to 4 bytes
            own, _ff, ps, count = struct.unpack_from(">4I", data, o)
            o += 16
            vs = cls(name, own, ps)
            for _ in range(count):
                kind, _z, k, _one, reg, h = struct.unpack_from(">6I", data, o)
                if kind != 2 or not 0 < k <= 16:
                    raise FormatError(f"{source}: value record at {o:#x} is type {kind}, "
                                      f"{k} values (expected type 2, 1-16)")
                vs.values[reg] = (h, struct.unpack_from(f">{k}f", data, o + 24))
                o += 24 + 4 * k
        except struct.error as ex:
            raise FormatError(f"{source}: value set ends early ({ex})") from None
        if o != len(data):
            raise FormatError(f"{source}: {len(data) - o} bytes left after {count} values")
        return vs

    def named(self, table: dict[str, Constant]) -> dict[str, tuple[float, ...]]:
        """The values by constant name, using the pixel shader's constant table."""
        by_reg = {c.register: c.name for c in table.values() if c.register_set == REG_FLOAT4}
        return {by_reg[r]: v for r, (_, v) in self.values.items() if r in by_reg}

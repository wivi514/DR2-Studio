"""Particle effects: the ``EFFECT_Common<k>`` entries of ``data/models/effects.big`` (phase 13).

Why: a weapon's effect numbers (``EffectOnImpact``, ``PyroEffect``…) pick an effect by
name from a table in the executable (`catalog.weapons`); the effect itself, how many
particles, what colour, how big, with which picture, is one entry of ``effects.big``.
Reading it lets a modder recolour or resize a game effect, and make effects of their own
(docs/formats.md §Particle effects, docs/modding/21-effects.md).

Layout (big-endian; every entry of both games, census: `census_effects`):

```
u32   version            0x1D (Case Zero) / 0x20 (Case West)
char  name[0x80]         the effect's name, NUL-padded ("flamingsword_wpn_c_3_unq")
u32   count              emitters
u32   head[4 | 3]        CZ 4 words, CW 3 (the last: 10…50, the first ones 0/1) ❓
count × emitter:
  0x190 bytes           fields (`FIELDS`: colours, sizes, times, speeds…)
  char  texture[0x20]   the particle picture, by name ("cloud_smoke2", "fire_flame")
  u32   zero[2]
  shape tail            by the shape word at +0x30: 0 none, 1 / 2 six floats, 3 five floats
```

So an emitter is 440, 464 or 460 bytes. The shape's floats sit at the end: the
Flaming Sword's flame emitters have shape 1 with (0.03, 0.7, 0, -0.03, 0, 0), a box from
(-0.03, 0, 0) to (0.03, 0.7, 0) along the blade ❓.

What each field means is named in `FIELDS` with how sure it is: the texture, the colour
keys (five RGBA, all 0-1, at +0x64), their times (+0x54, increasing) and the size keys
(+0xF0) read as such in every emitter; the rest are guesses from their values across all
4,737 emitters, to be checked in game one value at a time (`status` "?").

`Effect.parse` / `to_bytes` give every entry back byte for byte (`census_effects`). The
fields are read and written in place (`Emitter.get` / `set`), so a field whose meaning is
unknown is still kept.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from ..errors import FormatError

VERSIONS = {0x1D: 4, 0x20: 3}          # version -> header words after the count
NAME_SIZE = 0x80
FIXED = 0x190                           # an emitter's fields before its texture name
TEXTURE_SIZE = 0x20
SHAPE_TAIL = {0: 0, 1: 24, 2: 24, 3: 20}
SHAPE_NAMES = {0: "point", 1: "box", 2: "box (2)", 3: "sphere"}   # names ❓ (1/2 differ)
EMITTER_BASE = FIXED + TEXTURE_SIZE + 8


@dataclass(frozen=True)
class Field:
    """One field of an emitter: ``offset``, ``kind`` (``f`` float, ``i`` int, or ``fN``
    / ``iN`` for N in a row), a name, what it seems to be, and how sure (``ok`` read the
    same way in every emitter of both games; ``?`` a guess from the values)."""
    offset: int
    kind: str
    name: str
    meaning: str
    status: str = "?"

    @property
    def count(self) -> int:
        return int(self.kind[1:] or 1)

    @property
    def size(self) -> int:
        return 4 * self.count


FIELDS = [
    Field(0x00, "f3", "offset", "where it starts, from the effect's place (metres)"),
    Field(0x0C, "i", "flag_0c", "0 / 1 / 2"),
    Field(0x10, "f", "f_10", "-222 … 22"),
    Field(0x14, "f", "f_14", "0 … 90, often 1 or 2"),
    Field(0x18, "f", "f_18", "-77 … 700; ×10 changed nothing seen in game"),
    Field(0x1C, "i", "count_1c", "1 … 20+; ×10 changed nothing seen in game"),
    Field(0x20, "i", "count_20", "how many particles: ×10 made a flame ten times as dense "
                                 "(measured in game, CZ)", "ok"),
    Field(0x24, "f3", "speed", "starting speed, x y z (metres per second)"),
    Field(0x30, "i", "shape", "where particles start: 0 a point, 1 / 2 a box, 3 a sphere "
                              "(the tail's size follows it in every emitter)", "ok"),
    Field(0x34, "f3", "spread", "spread of the start, x y z"),
    Field(0x40, "f", "f_40", "0.005 … 10, mostly 0.7-1 (drag?)"),
    Field(0x44, "f3", "gravity", "a pull on the particles, x y z (y mostly below 0)"),
    Field(0x50, "f", "f_50", "-10 … 6"),
    Field(0x54, "f4", "colour_times", "when the colour reaches keys 2-5 (seconds, "
                                      "increasing); the last is the particles' life: ×4 "
                                      "made a flame live and rise four times as long "
                                      "(measured in game, CZ)", "ok"),
    Field(0x64, "f20", "colours", "five colour keys, red green blue alpha, 0 … 1", "ok"),
    Field(0xB4, "f15", "angles", "turning (radians): five keys of three"),
    Field(0xF0, "f5", "sizes", "five size keys (metres)", "ok"),
    Field(0x104, "f5", "f_104", "five keys: 0 … 215"),
    Field(0x118, "i", "blend", "0 … 5 (how it is drawn: add, mix…?)"),
    Field(0x11C, "i", "i_11c", "0 … 4, mostly equal to blend"),
    Field(0x120, "f3", "spin", "-44 … 44, x y z"),
    Field(0x12C, "i", "flag_12c", "0 / 1"),
    Field(0x130, "i", "flag_130", "0 / 1"),
    Field(0x134, "i", "zero_134", "always 0", "ok"),
    Field(0x138, "f6", "f_138", "six floats, mostly 0 (the 4th 0 … 22: ×10 changed nothing "
                                "seen in game)"),
    Field(0x150, "f", "f_150", "0 … 1"),
    Field(0x154, "i", "flag_154", "0 / 1"),
    Field(0x158, "i", "flag_158", "0 / 1"),
    Field(0x15C, "i", "flag_15c", "0 / 1"),
    Field(0x160, "i", "i_160", "-1 or a small number (another effect, a locator?)"),
    Field(0x164, "i", "i_164", "1 … 20, mostly 3; 30 hid the emitter in game ❓"),
    Field(0x168, "f", "f_168", "0 … 4"),
    Field(0x16C, "f", "f_16c", "0 … 10, mostly 10"),
    Field(0x170, "i", "i_170", "0 … 3"),
    Field(0x174, "f", "f_174", "0 … 1"),
    Field(0x178, "i", "flag_178", "0 / 1"),
    Field(0x17C, "i", "flag_17c", "0 / 1"),
    Field(0x180, "f", "f_180", "0 … 9"),
    Field(0x184, "f", "f_184", "-2 … 400, mostly 1"),
    Field(0x188, "i", "flag_188", "0 / 1"),
    Field(0x18C, "i", "flag_18c", "0 / 1"),
]
BY_NAME = {f.name: f for f in FIELDS}


@dataclass
class Emitter:
    """One emitter, kept as its bytes (`FIELDS` read and written in place)."""
    raw: bytearray

    @classmethod
    def parse(cls, data: bytes, at: int, source: str = "<effect>") -> "Emitter":
        if at + EMITTER_BASE > len(data):
            raise FormatError(f"{source}: an emitter at {at:#x} runs past the end")
        shape = struct.unpack_from(">I", data, at + 0x30)[0]
        if shape not in SHAPE_TAIL:
            raise FormatError(f"{source}: emitter at {at:#x}: unknown shape {shape}")
        size = EMITTER_BASE + SHAPE_TAIL[shape]
        if at + size > len(data):
            raise FormatError(f"{source}: an emitter at {at:#x} runs past the end")
        return cls(bytearray(data[at:at + size]))

    def get(self, name: str):
        """A field's value: a number, or a list for ``fN`` / ``iN``."""
        f = BY_NAME[name]
        vals = struct.unpack_from(f">{f.count}{f.kind[0]}", self.raw, f.offset)
        return list(vals) if f.count > 1 else vals[0]

    def set(self, name: str, value) -> None:
        f = BY_NAME[name]
        if name == "shape" and value != self.get("shape"):
            raise FormatError("changing an emitter's shape changes its size: not supported")
        vals = value if isinstance(value, (list, tuple)) else [value]
        if len(vals) != f.count:
            raise FormatError(f"{name}: {f.count} value(s), got {len(vals)}")
        conv = float if f.kind[0] == "f" else int
        struct.pack_into(f">{f.count}{f.kind[0]}", self.raw, f.offset, *(conv(v) for v in vals))

    @property
    def texture(self) -> str:
        return self.raw[FIXED:FIXED + TEXTURE_SIZE].split(b"\0")[0].decode("ascii")

    @texture.setter
    def texture(self, name: str) -> None:
        b = name.encode("ascii")
        if not b or len(b) >= TEXTURE_SIZE:
            raise FormatError(f"texture name {name!r}: 1 to {TEXTURE_SIZE - 1} characters")
        self.raw[FIXED:FIXED + TEXTURE_SIZE] = b.ljust(TEXTURE_SIZE, b"\0")

    @property
    def shape_values(self) -> list[float]:
        n = SHAPE_TAIL[self.get("shape")] // 4
        return list(struct.unpack_from(f">{n}f", self.raw, EMITTER_BASE))

    @shape_values.setter
    def shape_values(self, values) -> None:
        n = SHAPE_TAIL[self.get("shape")] // 4
        if len(values) != n:
            raise FormatError(f"this emitter's shape has {n} values")
        struct.pack_into(f">{n}f", self.raw, EMITTER_BASE, *map(float, values))

    def colour_keys(self) -> list[tuple[float, float, float, float]]:
        c = self.get("colours")
        return [tuple(c[i:i + 4]) for i in range(0, 20, 4)]

    def set_colour_keys(self, keys) -> None:
        self.set("colours", [float(v) for k in keys for v in k])

    def to_dict(self) -> dict:
        d = {f.name: self.get(f.name) for f in FIELDS}
        d["texture"] = self.texture
        d["shape_values"] = self.shape_values
        return d


@dataclass
class Effect:
    """One ``EFFECT_Common<k>`` entry (module docstring)."""
    version: int
    name: str
    name_field: bytes                   # the 0x80 bytes as stored (padding kept)
    head: list[int]
    emitters: list[Emitter] = field(default_factory=list)

    @classmethod
    def parse(cls, data: bytes, source: str = "<effect>") -> "Effect":
        if len(data) < 4 + NAME_SIZE + 4:
            raise FormatError(f"{source}: {len(data)} bytes, too short for an effect")
        version = struct.unpack_from(">I", data)[0]
        if version not in VERSIONS:
            raise FormatError(f"{source}: version {version:#x}, expected 0x1D or 0x20")
        name_field = data[4:4 + NAME_SIZE]
        name = name_field.split(b"\0")[0].decode("ascii", "replace")
        count = struct.unpack_from(">I", data, 4 + NAME_SIZE)[0]
        nh = VERSIONS[version]
        at = 8 + NAME_SIZE
        head = list(struct.unpack_from(f">{nh}I", data, at))
        at += 4 * nh
        emitters = []
        for _ in range(count):
            e = Emitter.parse(data, at, source)
            emitters.append(e)
            at += len(e.raw)
        if at != len(data):
            raise FormatError(f"{source}: {len(data) - at} byte(s) left after {count} "
                              f"emitter(s)")
        return cls(version, name, name_field, head, emitters)

    def to_bytes(self) -> bytes:
        out = bytearray(struct.pack(">I", self.version))
        out += self.name_field
        out += struct.pack(">I", len(self.emitters))
        out += struct.pack(f">{len(self.head)}I", *self.head)
        for e in self.emitters:
            out += e.raw
        return bytes(out)

    def rename(self, name: str) -> None:
        b = name.encode("ascii")
        if not b or len(b) >= NAME_SIZE:
            raise FormatError(f"effect name {name!r}: 1 to {NAME_SIZE - 1} characters")
        self.name = name
        self.name_field = b.ljust(NAME_SIZE, b"\0")


def is_effect(data: bytes) -> bool:
    return len(data) >= 4 and struct.unpack_from(">I", data)[0] in VERSIONS


EFFECTS_BIG = "data/models/effects.big"


def read_all(tree) -> dict[str, tuple[str, Effect]]:
    """effect name → (its entry's name, `Effect`) for every effect of a game."""
    arc = tree.open_archive(tree.resolve(EFFECTS_BIG).vpath)
    out = {}
    for e in arc.entries:
        if e.name.startswith("EFFECT_"):
            fx = Effect.parse(e.data(), f"{EFFECTS_BIG}/{e.name}")
            out.setdefault(fx.name, (e.name, fx))
    return out


def census_effects(tree) -> dict:
    """Every effect parsed and written back: counts and any difference (a gate)."""
    arc = tree.open_archive(tree.resolve(EFFECTS_BIG).vpath)
    effects = emitters = 0
    shapes: dict[int, int] = {}
    problems = []
    for e in arc.entries:
        if not e.name.startswith("EFFECT_"):
            continue
        data = e.data()
        try:
            fx = Effect.parse(data, e.name)
        except FormatError as ex:
            problems.append(str(ex))
            continue
        if fx.to_bytes() != data:
            problems.append(f"{e.name}: written back differently")
        effects += 1
        emitters += len(fx.emitters)
        for m in fx.emitters:
            shapes[m.get("shape")] = shapes.get(m.get("shape"), 0) + 1
    return {"effects": effects, "emitters": emitters, "shapes": shapes,
            "problems": problems}

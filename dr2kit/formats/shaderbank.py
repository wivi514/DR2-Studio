"""The shader banks' descriptions: ``.sdo``, ``.pdo``, ``.vdo`` and ``strings.bin`` (phase 15).

Why: a model brought from the other game draws with **its own game's shaders** (decision
2 of phase 15, user 2026-10-12), copied into the target's banks. The programs (``.vo``,
``.po``) are copied as they are; the files that *name* them must be rewritten: a
description lists its programs by hash, and a pixel shader's parameter list numbers its
parameters with a registry that differs between the games. This module reads and writes
those files byte for byte (`census` checks every one of both games).

The banks are ``data/shaders/deadrising{prologue,epilogue}-<kind>.big`` (also inside
``data/preload4.big``), all big-endian:

* **``-sd``: descriptions** ``<hash>.sdo`` (`Description`): ``u32 hash, u32 link``
  (``0xFFFFFFFF``, or another description's hash ❓: `census` counts what it names),
  ``u32 n``, then ``n`` pass records of 6 words ``{0, flags, vertex shader hash, 0, pixel
  shader hash, 0}`` (``0xFFFFFFFF``: no pixel shader), then the rest: the
  shader's name (``u32 length, text``: ``ZombieGlow``), ``Default`` and lists of numbers
  (kept as bytes). A model names a description by its hash (``UsedShaders.txt``, draw
  commands ``0x3C`` / ``0x3F``).
* **``-pd``: a pixel shader's parameters** ``<hash>.pdo`` (`ParamFile`): ``u32 hash, u32
  n``, ``n`` × `Param`, ``u32 word`` (0 or a hash ❓), ``u32 hash`` again.
* **``-vd``: a vertex shader's** ``<hash>.vdo``: a vertex-input header (kept as bytes),
  then ``u32 hash, u32 n``, ``n`` × `Param`, ``u32 word``.
* `Param`: ``u32 length, name`` (NUL included, padded to 4), ``u32 hash`` (the same in
  both games; value sets name constants by it), ``u32 number`` (**a registry per game**:
  CW's ``gGlowScale`` 187 is CZ's ``gBodyPart4Colour``), ``u32 0, u32 type`` (1-4: float
  to float4), ``u32 registers``, 4 flag bytes; when flag byte 1 is set a slider follows:
  ``1 + 3 × type`` words (a word, then min, default and max per component) and a label
  (``u32 length, text``: ``Glow Scale``).
* **``-ss``: ``strings.bin``** (`StringTable`): ``u32 count``, then ``count`` entries
  ``{u32 length, text, NUL, padded to 4}``, the first one empty: shader file and parameter
  names. ❓ who reads it.

Facts and the census: docs/formats.md §"Across the games: shader banks".
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from ..errors import FormatError

NONE = 0xFFFFFFFF
KINDS = ("vs", "ps", "vd", "pd", "sc", "sd", "ss")


def bank_prefix(game_or_tree) -> str:
    """``deadrisingprologue`` (CZ) or ``deadrisingepilogue`` (CW): read from the tree's
    ``data/shaders`` folder, or by game id."""
    if isinstance(game_or_tree, str):
        return {"cz": "deadrisingprologue", "cw": "deadrisingepilogue"}[game_or_tree]
    for p in (game_or_tree.root / "data" / "shaders").iterdir():
        if p.name.lower().endswith("-sd.big"):
            return p.name[:-len("-sd.big")]
    raise FormatError(f"{game_or_tree.root}: no shader bank (data/shaders/*-sd.big)")


def _text(d: bytes, o: int, where: str) -> tuple[str, int]:
    if o + 4 > len(d):
        raise FormatError(f"{where}: text cut short at {o}")
    n = struct.unpack_from(">I", d, o)[0]
    end = o + 4 + ((n + 3) & ~3)
    if end > len(d):
        raise FormatError(f"{where}: text of {n} bytes at {o} runs past the end")
    return d[o + 4:o + 4 + n].split(b"\0", 1)[0].decode("latin-1"), end


def _put_text(s: str, n: int | None = None) -> bytes:
    raw = s.encode("latin-1")
    n = len(raw) + 1 if n is None else n
    return struct.pack(">I", n) + raw.ljust((n + 3) & ~3, b"\0")


@dataclass
class Pass:
    """One pass record of a description: its programs by hash."""
    flags: int
    vs: int
    ps: int                    # NONE: no pixel shader
    words: tuple[int, int, int] = (0, 0, 0)    # the record's 1st, 4th and 6th words


@dataclass
class Description:
    """A ``.sdo`` (module docstring)."""
    hash: int
    passes: list[Pass]
    rest: bytes                # the name, ``Default`` and the lists after the records
    link: int = NONE           # word 1 (module docstring)

    @property
    def name(self) -> str:
        return _text(self.rest, 0, "sdo")[0]

    @classmethod
    def parse(cls, d: bytes, where: str = "<sdo>") -> "Description":
        if len(d) < 12:
            raise FormatError(f"{where}: {len(d)} bytes, too short for a description")
        h, link, n = struct.unpack_from(">3I", d, 0)
        if n > 4096 or 12 + 24 * n + 4 > len(d):
            raise FormatError(f"{where}: not a shader description ({n} passes)")
        passes = []
        for i in range(n):
            a, f, vs, b, ps, c = struct.unpack_from(">6I", d, 12 + 24 * i)
            passes.append(Pass(f, vs, ps, (a, b, c)))
        out = cls(h, passes, d[12 + 24 * n:], link)
        out.name                                     # the name must follow the records
        return out

    def to_bytes(self) -> bytes:
        out = [struct.pack(">3I", self.hash, self.link, len(self.passes))]
        out += [struct.pack(">6I", p.words[0], p.flags, p.vs, p.words[1], p.ps, p.words[2])
                for p in self.passes]
        return b"".join(out) + self.rest

    def programs(self) -> tuple[set[int], set[int]]:
        """(vertex shader hashes, pixel shader hashes) its passes name."""
        return ({p.vs for p in self.passes if p.vs != NONE},
                {p.ps for p in self.passes if p.ps != NONE})


@dataclass
class Param:
    """One parameter of a ``.pdo`` / ``.vdo`` (module docstring)."""
    name: str
    hash: int
    number: int
    type: int
    registers: int
    flags: bytes
    zero: int = 0
    slider: tuple[int, ...] | None = None     # 1 + 3 × type words
    label: str | None = None
    name_len: int = 0                          # the stored length (NUL included)
    label_len: int = 0

    def to_bytes(self) -> bytes:
        out = _put_text(self.name, self.name_len or None) + struct.pack(
            ">5I", self.hash, self.number, self.zero, self.type, self.registers) + self.flags
        if self.flags[1]:
            out += struct.pack(f">{len(self.slider)}I", *self.slider)
            out += _put_text(self.label or "", self.label_len or None)
        return out


def _params(d: bytes, o: int, n: int, where: str) -> tuple[list[Param], int]:
    out = []
    for i in range(n):
        start = o
        name, o = _text(d, o, where)
        name_len = struct.unpack_from(">I", d, start)[0]
        if o + 24 > len(d):
            raise FormatError(f"{where}: parameter {i} ({name}) cut short")
        h, num, z, typ, regs = struct.unpack_from(">5I", d, o)
        flags = d[o + 20:o + 24]
        o += 24
        slider = label = None
        label_len = 0
        if flags[1]:
            if not 1 <= typ <= 4:
                raise FormatError(f"{where}: parameter {name} has a slider of type {typ}")
            k = 1 + 3 * typ
            slider = struct.unpack_from(f">{k}I", d, o)
            o += 4 * k
            label_len = struct.unpack_from(">I", d, o)[0]
            label, o = _text(d, o, where)
        out.append(Param(name, h, num, typ, regs, flags, z, slider, label, name_len, label_len))
    return out, o


@dataclass
class ParamFile:
    """A ``.pdo`` (``head`` empty, ``trailer`` True) or ``.vdo`` (``head`` = the vertex
    input header before the hash, no trailing hash)."""
    hash: int
    params: list[Param]
    word: int
    head: bytes = b""
    trailer: bool = True

    @classmethod
    def parse_pdo(cls, d: bytes, where: str = "<pdo>") -> "ParamFile":
        h, n = struct.unpack_from(">II", d, 0)
        params, o = _params(d, 8, n, where)
        if o + 8 != len(d):
            raise FormatError(f"{where}: {len(d) - o - 8} bytes left after the parameters")
        w, own = struct.unpack_from(">II", d, o)
        if own != h:
            raise FormatError(f"{where}: ends with {own:08x}, not its hash {h:08x}")
        return cls(h, params, w)

    @classmethod
    def parse_vdo(cls, d: bytes, own: int, where: str = "<vdo>") -> "ParamFile":
        at = d.find(struct.pack(">I", own))
        while at >= 0 and at % 4:
            at = d.find(struct.pack(">I", own), at + 1)
        if at < 0:
            raise FormatError(f"{where}: its hash {own:08x} is not inside")
        n = struct.unpack_from(">I", d, at + 4)[0]
        params, o = _params(d, at + 8, n, where)
        if o + 4 != len(d):
            raise FormatError(f"{where}: {len(d) - o - 4} bytes left after the parameters")
        return cls(own, params, struct.unpack_from(">I", d, o)[0], d[:at], False)

    def to_bytes(self) -> bytes:
        out = self.head + struct.pack(">II", self.hash, len(self.params))
        out += b"".join(p.to_bytes() for p in self.params) + struct.pack(">I", self.word)
        return out + (struct.pack(">I", self.hash) if self.trailer else b"")


@dataclass
class StringTable:
    """``strings.bin`` (module docstring): ``strings[0]`` is the empty first entry."""
    strings: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, d: bytes, where: str = "<strings.bin>") -> "StringTable":
        n = struct.unpack_from(">I", d, 0)[0]
        o, out = 4, []
        for _ in range(n):
            s, o = _text_nul(d, o, where)
            out.append(s)
        if o != len(d):
            raise FormatError(f"{where}: {len(d) - o} bytes left after {n} strings")
        return cls(out)

    def to_bytes(self) -> bytes:
        out = [struct.pack(">I", len(self.strings))]
        for s in self.strings:
            raw = s.encode("latin-1")
            out.append(struct.pack(">I", len(raw)) + (raw + b"\0").ljust((len(raw) + 4) & ~3,
                                                                          b"\0"))
        return b"".join(out)

    def add(self, names) -> list[str]:
        """Append the names it lacks (order kept, existing numbers unchanged); returns
        the ones added."""
        have = set(self.strings)
        new = [s for s in dict.fromkeys(names) if s not in have]
        self.strings += new
        return new


def _text_nul(d: bytes, o: int, where: str) -> tuple[str, int]:
    if o + 4 > len(d):
        raise FormatError(f"{where}: string cut short at {o}")
    n = struct.unpack_from(">I", d, o)[0]
    end = o + 4 + ((n + 4) & ~3)
    if end > len(d):
        raise FormatError(f"{where}: string of {n} bytes at {o} runs past the end")
    return d[o + 4:o + 4 + n].decode("latin-1"), end


def census(tree, game: str = "") -> dict:
    """Every description, parameter file and string table of the game's banks parses and
    writes back byte for byte; every program a description names is in the banks; the
    parameter numbers of each stage are counted (``{"problems": [...], ...}``)."""
    pre = bank_prefix(tree)
    banks = {k: tree.open_archive(f"data/shaders/{pre}-{k}.big") for k in KINDS}
    names = {k: {e.name.lower() for e in a.entries} for k, a in banks.items()}
    problems: list[str] = []
    counts = {"descriptions": 0, "pdo": 0, "vdo": 0, "strings": 0, "missing programs": 0}
    numbers: dict[str, dict[int, set[str]]] = {"pd": {}, "vd": {}}
    for e in banks["sd"].entries:
        where = f"{pre}-sd.big/{e.name}"
        try:
            sd = Description.parse(e.data(), where)
            if sd.to_bytes() != e.data():
                problems.append(f"{where}: writes back different")
            vs, ps = sd.programs()
            for h in vs:
                if f"{h:08x}.vo" not in names["vs"]:
                    counts["missing programs"] += 1
            for h in ps:
                if f"{h:08x}.po" not in names["ps"]:
                    counts["missing programs"] += 1
            counts["descriptions"] += 1
        except FormatError as ex:
            problems.append(str(ex))
    for kind, ext in (("pd", "pdo"), ("vd", "vdo")):
        for e in banks[kind].entries:
            where = f"{pre}-{kind}.big/{e.name}"
            try:
                own = int(e.name[:8], 16)
                pf = ParamFile.parse_pdo(e.data(), where) if kind == "pd" else \
                    ParamFile.parse_vdo(e.data(), own, where)
                if pf.to_bytes() != e.data():
                    problems.append(f"{where}: writes back different")
                for p in pf.params:
                    numbers[kind].setdefault(p.number, set()).add(p.name)
                counts[ext] += 1
            except (FormatError, ValueError, struct.error) as ex:
                problems.append(f"{where}: {ex}")
    for e in banks["ss"].entries:
        st = StringTable.parse(e.data(), f"{pre}-ss.big/{e.name}")
        if st.to_bytes() != e.data():
            problems.append(f"{pre}-ss.big/{e.name}: writes back different")
        counts["strings"] += len(st.strings)
    clash = {k: sorted(n for n, s in v.items() if len(s) > 1) for k, v in numbers.items()}
    return {"problems": problems, **counts,
            "pixel parameter numbers": len(numbers["pd"]),
            "vertex parameter numbers": len(numbers["vd"]),
            "numbers with two names": clash}


def registry(tree, kind: str = "pd") -> dict[str, int]:
    """name -> parameter number over every ``.pdo`` (``kind="pd"``) or ``.vdo`` of a game."""
    pre = bank_prefix(tree)
    out: dict[str, int] = {}
    for e in tree.open_archive(f"data/shaders/{pre}-{kind}.big").entries:
        pf = ParamFile.parse_pdo(e.data(), e.name) if kind == "pd" else \
            ParamFile.parse_vdo(e.data(), int(e.name[:8], 16), e.name)
        for p in pf.params:
            out.setdefault(p.name, p.number)
    return out

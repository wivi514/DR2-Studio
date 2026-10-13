"""Bring a model's shaders from the other game (phase 15, decision 2: "the proper Case West
shader", user 2026-10-12).

Why: a model draws with the shader descriptions its ``UsedShaders.txt`` names and the
pixel shaders its materials' value sets name. The other game's banks hold descriptions
of the same names whose programs were compiled differently (no vertex shader and only 45
pixel shader names are shared byte for byte), and its pixel shaders number their
parameters with another registry (docs/formats.md §"Across the games: shader banks"). So
a Case West model in Case Zero gets **Case West's own shaders**, copied into Case Zero's
banks:

* `plan` decides, for each description the model names and each program it lists, whether
  the target already has the very same bytes (then it is used as is) or it is **brought**
  under a new name (`new_name`: a hash no entry of the target uses, the low 5 bits clear
  like the games' own). A brought description lists brought programs; a vertex shader
  brings its ``.vdo`` along, a pixel shader its ``.pdo``.
* The bank entries are **recipes** (``add/data/shaders/<bank>/<new>.<ext>.copy.json``,
  ``"from"`` the source game), so the mod holds no game data: `build_entry` makes each
  entry when the mod is built, its own hash and the hashes it names renamed, and a
  ``.pdo``'s parameter numbers turned into the target's (`number_map`: a name the target
  has keeps the target's number; a name it lacks gets a number no shader of the target
  uses ❓ in game: U3). **The number is the constant register** the program reads the
  parameter from, and the games' registers differ (Case West's ``gShaderDebugParameters``
  is c21, Case Zero's c20: a brought program read Case Zero's point light there and drew
  flat white, U1 2026-10-13), so a brought pixel shader's constant operands are moved to
  the same numbers (`move_registers`, `formats.xenos`; formats.md §"Across the games:
  constant registers"). Vertex shaders' registers are the same in both games.
* `convert_pack` rewrites the model itself: ``UsedShaders.txt``, the draws' ``0x3C`` /
  ``0x3F`` shader commands, and each value set's pixel shader.

The recomps translate a shader the first time a draw binds it (both have a first-sight
translator), so brought shaders draw without a recomp change; adding the mods' banks to
the first-run shader build only avoids that first moment without them.
"""

from __future__ import annotations

import re
import struct
import zlib
from dataclasses import dataclass, field
from functools import lru_cache

from ..container.big import BigArchive, is_big
from ..container.vpath import AssetTree
from ..errors import Dr2Error
from ..formats import shaderbank as sb
from ..formats import xenos
from ..formats.scene import Command, parse_command_buffer

USED = "usedshaders.txt"
# Parameters only one game's engine writes (globals, no slider), and the value a brought
# program reads instead in the other game: Case West's power switch (1: the power is on;
# 0 switched off every self-lit part: the Laser Sword had no glow, U1 2026-10-13) and its
# self-lit glow multiplier ❓ (1: neutral).
ENGINE_ONLY = {"gPowerOffParameter": 1.0, "gMultiplierGlowSI": 1.0}
LITERAL_FLOOR = 248          # the lowest literal register a game's pixel shader defines
EXT = {"sd": "sdo", "vs": "vo", "vd": "vdo", "ps": "po", "pd": "pdo"}


@dataclass
class Carry:
    """What `plan` decided: old hash -> new hash per kind (only what is brought), and the
    bank entries to add (``{"sd": {new: old}, "vs": …}``)."""
    src: str
    dst: str
    sd: dict[int, int] = field(default_factory=dict)
    vs: dict[int, int] = field(default_factory=dict)
    ps: dict[int, int] = field(default_factory=dict)
    shared: list[str] = field(default_factory=list)      # names used as the target has them

    def entries(self) -> list[tuple[str, int, int]]:
        """``(bank kind, old, new)`` of every entry to add (a program brings its
        description file: ``vs`` -> ``vd``, ``ps`` -> ``pd``)."""
        out = [("sd", o, n) for o, n in self.sd.items()]
        for kind, desc in (("vs", "vd"), ("ps", "pd")):
            for o, n in getattr(self, kind).items():
                out += [(kind, o, n), (desc, o, n)]
        return sorted(out)

    def to_json(self) -> dict:
        return {k: {f"{o:08x}": f"{n:08x}" for o, n in getattr(self, k).items()}
                for k in ("sd", "vs", "ps") if getattr(self, k)}


class Banks:
    """One game's shader banks, read once."""

    def __init__(self, tree: AssetTree):
        self.tree = tree
        self.prefix = sb.bank_prefix(tree)
        self.arcs = {k: tree.open_archive(f"data/shaders/{self.prefix}-{k}.big")
                     for k in EXT}
        self.data = {k: {e.name.lower(): e for e in a.entries} for k, a in self.arcs.items()}

    def vpath(self, kind: str, h: int) -> str:
        return f"data/shaders/{self.prefix}-{kind}.big/{h:08x}.{EXT[kind]}"

    def get(self, kind: str, h: int) -> bytes | None:
        e = self.data[kind].get(f"{h:08x}.{EXT[kind]}")
        return e.data() if e is not None else None

    def names(self) -> set[int]:
        out = set()
        for d in self.data.values():
            out |= {int(n[:8], 16) for n in d if re.match(r"^[0-9a-f]{8}\.", n)}
        return out


@lru_cache(maxsize=4)
def _banks(root: str) -> Banks:
    from pathlib import Path
    return Banks(AssetTree(Path(root)))


def banks(tree: AssetTree) -> Banks:
    return _banks(str(tree.root))


def new_name(src: str, kind: str, old: int, taken: set[int]) -> int:
    """A hash for a brought entry: from the source game, bank and old hash (so every mod
    that brings the same shader gives it the same name), low 5 bits clear, not ``taken``."""
    salt = 0
    while True:
        h = zlib.crc32(f"dr2kit:{src}:{kind}:{old:08x}:{salt}".encode()) & ~0x1F
        if h and h not in taken and h != sb.NONE:
            return h
        salt += 1


def plan(src_tree: AssetTree, dst_tree: AssetTree, src: str, dst: str,
         descriptions: set[int], pixel_shaders: set[int] = frozenset()) -> Carry:
    """Which of these descriptions (a model's ``UsedShaders.txt`` hashes) and pixel shaders
    (its value sets') the target can use as they are, and which are brought (module
    docstring). Raises `Dr2Error` naming a description the source game lacks."""
    a, b = banks(src_tree), banks(dst_tree)
    taken = b.names() | a.names()
    c = Carry(src, dst)

    def program(kind: str, desc: str, h: int) -> int:
        mine, theirs = a.get(kind, h), b.get(kind, h)
        if mine is None:
            raise Dr2Error(f"{a.prefix}-{kind}.big has no {h:08x}.{EXT[kind]}")
        if mine == theirs and a.get(desc, h) == b.get(desc, h):
            return h
        table = getattr(c, kind)
        if h not in table:
            table[h] = new_name(src, kind, h, taken)
            taken.add(table[h])
        return table[h]

    for h in sorted(descriptions):
        raw = a.get("sd", h)
        if raw is None:
            raise Dr2Error(f"the model names shader {h:08x}, which {a.prefix}-sd.big lacks")
        d = sb.Description.parse(raw, a.vpath("sd", h))
        vs, ps = d.programs()
        moved = [program("vs", "vd", v) != v for v in sorted(vs)] + \
            [program("ps", "pd", p) != p for p in sorted(ps)]
        if any(moved) or raw != b.get("sd", h):
            c.sd[h] = new_name(src, "sd", h, taken)
            taken.add(c.sd[h])
        else:
            c.shared.append(d.name)
    for p in sorted(pixel_shaders):
        program("ps", "pd", p)
    return c


def _pixel_extents(tree: AssetTree) -> dict[str, tuple[int, int]]:
    """Pixel parameter name -> (register, the most registers any program reads of it),
    from every pixel shader's constant table (the register is the ``.pdo`` number: the
    same in every program and ``.pdo`` of a game, census in formats.md)."""
    out: dict[str, tuple[int, int]] = {}
    for name, e in banks(tree).data["ps"].items():
        if not name.endswith(".po"):
            continue
        for c in xenos.constants(e.data(), name):
            if c.set == "float4":
                reg, n = out.get(c.name, (c.register, 0))
                out[c.name] = (reg, max(n, c.count))
    return out


@lru_cache(maxsize=4)
def number_map(src_root: str, dst_root: str) -> dict[str, int]:
    """Pixel parameter name -> its register (= ``.pdo`` number) in the target.

    A name the target has keeps the target's register: the target's engine writes it
    there. A name only the source has (Case West's ``gGlowScale``, ``gPowerOffParameter``
    …) gets registers no program of the target reads, in the gaps below the target's
    highest one first (so the number stays inside the range the target's engine knows),
    then above it, never into the literal registers (248 and up)."""
    from pathlib import Path
    src = _pixel_extents(AssetTree(Path(src_root)))
    dst = _pixel_extents(AssetTree(Path(dst_root)))
    taken = {r + k for r, n in dst.values() for k in range(n)}
    out = {name: reg for name, (reg, _) in dst.items()}
    for name, (_, n) in sorted(src.items(), key=lambda kv: kv[1][0]):
        if name in out:
            continue
        reg = next((r for r in range(1, LITERAL_FLOOR - n + 1)
                    if all(r + k not in taken for k in range(n))), None)
        if reg is None:
            raise Dr2Error(f"no free pixel shader registers left for {name}")
        out[name] = reg
        taken |= {reg + k for k in range(n)}
    return out


@lru_cache(maxsize=4)
def register_moves(src_root: str, dst_root: str) -> dict[int, int]:
    """Source pixel register -> target register, for every register of every parameter
    (`number_map`): what a brought material's value set must be renumbered by."""
    from pathlib import Path
    numbers = number_map(src_root, dst_root)
    out = {}
    for name, (reg, n) in _pixel_extents(AssetTree(Path(src_root))).items():
        for k in range(n):
            out[reg + k] = numbers[name] + k
    return out


@lru_cache(maxsize=4)
def fixed_values(src_root: str, dst_root: str) -> dict[str, float]:
    """`ENGINE_ONLY` parameters the target's engine doesn't write (its programs never
    read them): a brought program reads the fixed value instead."""
    from pathlib import Path
    dst = _pixel_extents(AssetTree(Path(dst_root)))
    return {n: v for n, v in ENGINE_ONLY.items() if n not in dst}


def move_registers(raw: bytes, numbers: dict[str, int], where: str = "",
                   fixed: dict[str, float] | None = None) -> bytes:
    """A brought pixel shader reading each parameter at the target's register
    (`number_map`; formats/xenos.py says why). Raises `Dr2Error` when a parameter has no
    register in the map or would land on one of the program's own literals."""
    moves = {}
    for c in xenos.constants(raw, where):
        if c.set != "float4":
            continue
        if c.name not in numbers:
            raise Dr2Error(f"{where}: pixel parameter {c.name} has no register in the target")
        for k in range(c.count):
            moves[c.register + k] = numbers[c.name] + k
    clash = set(moves.values()) & set(xenos.literals(raw))
    if clash:
        raise Dr2Error(f"{where}: registers {sorted(clash)} are the program's own literals")
    out, unknown = xenos.remap_constants(raw, moves, where)
    if unknown:
        raise Dr2Error(f"{where}: reads constant registers {unknown} no parameter names")
    for c in xenos.constants(out, where):
        if c.set == "float4" and c.name in (fixed or {}):
            try:
                out = xenos.read_literal(out, c.register, fixed[c.name], where)
            except Exception as ex:                             # noqa: BLE001
                raise Dr2Error(f"{where}: {c.name}: {ex}") from None
    return out


def build_entry(src_tree: AssetTree, dst_tree: AssetTree, spec: dict, where: str = "") -> bytes:
    """A brought bank entry from a recipe's ``"shader"`` (``{"kind": "sd", "old": "…",
    "new": "…", "rename": {old: new for every program}}``, module docstring)."""
    pre = f"{where}: " if where else ""
    kind = spec.get("kind")
    if kind not in EXT:
        raise Dr2Error(f"{pre}shader kind {kind!r} (one of {', '.join(EXT)})")
    old, new = int(spec["old"], 16), int(spec["new"], 16)
    rename = {int(k, 16): int(v, 16) for k, v in (spec.get("rename") or {}).items()}
    raw = banks(src_tree).get(kind, old)
    if raw is None:
        raise Dr2Error(f"{pre}the source game has no {old:08x}.{EXT[kind]}")
    if kind == "sd":
        d = sb.Description.parse(raw, where)
        d.hash = new
        for p in d.passes:
            p.vs, p.ps = rename.get(p.vs, p.vs), rename.get(p.ps, p.ps)
        return d.to_bytes()
    if kind == "pd":
        pf = sb.ParamFile.parse_pdo(raw, where)
        numbers = number_map(str(src_tree.root), str(dst_tree.root))
        pf.hash = new
        for p in pf.params:
            p.number = numbers[p.name]
        return pf.to_bytes()
    if kind == "vd":
        pf = sb.ParamFile.parse_vdo(raw, old, where)
        pf.hash = new
        return pf.to_bytes()
    if kind == "ps":                               # read at the target's registers
        roots = (str(src_tree.root), str(dst_tree.root))
        return move_registers(raw, number_map(*roots), where, fixed_values(*roots))
    return raw                                     # a vertex shader: the same bytes


def recipes(c: Carry, dst_tree: AssetTree) -> dict[str, dict]:
    """The ``add/`` recipe files for a `Carry`: path under ``add/`` -> recipe."""
    src_b = banks(_src_tree(c))
    dst_b = banks(dst_tree)
    rename = {**c.vs, **c.ps}
    out = {}
    for kind, old, new in c.entries():
        vp = dst_b.vpath(kind, new)
        out[vp + ".copy.json"] = {
            "format": "dr2kit-copy/1", "from": c.src, "copy": src_b.vpath(kind, old),
            "shader": {"kind": kind, "old": f"{old:08x}", "new": f"{new:08x}",
                       **({"rename": {f"{o:08x}": f"{n:08x}" for o, n in rename.items()}}
                          if kind == "sd" else {})}}
    return out


def _src_tree(c: Carry) -> AssetTree:
    from .crossgame import source_tree
    return source_tree(c.src)


# --- the model -----------------------------------------------------------------------

def scenes_of(data: bytes, name: str = "") -> list[tuple[BigArchive, str]]:
    """Every scene archive (one with ``UsedShaders.txt``) in a pack, nested ones too."""
    arc = BigArchive.parse(data, name)
    out = []
    _walk_scenes(arc, name, out)
    return out


def _walk_scenes(arc: BigArchive, vp: str, out: list) -> None:
    if any(e.name.lower() == USED for e in arc.entries):
        out.append((arc, vp))
    for e in arc.entries:
        if e.name.lower().endswith((".big", ".tex")) and is_big(e.data()):
            try:
                _walk_scenes(BigArchive.parse(e.data(), e.name), f"{vp}/{e.name}", out)
            except Exception:                                   # noqa: BLE001
                pass


def used_shaders(data: bytes) -> tuple[set[int], set[int]]:
    """(descriptions, value sets' pixel shaders) a pack's models use."""
    from ..formats.shader import ValueSet
    sd, ps = set(), set()
    for arc, _ in scenes_of(data):
        for e in arc.entries:
            low = e.name.lower()
            if low == USED:
                sd |= _used_hashes(e.data())
            elif low == "valuesets.big":
                for v in BigArchive.parse(e.data(), e.name).entries:
                    ps.add(ValueSet.parse(v.data(), v.name).pixel_shader)
    return sd, ps - {sb.NONE}


def _used_hashes(text: bytes) -> set[int]:
    return {int(m.group(1), 16) for m in
            re.finditer(rb"0x([0-9A-Fa-f]{1,8})\s*:", text)}


def convert_pack(data: bytes, maps: dict, name: str = "pack",
                 regs: dict[int, int] | None = None) -> bytes:
    """``data`` (a pack or scene archive) drawing with the brought shaders: ``maps`` is
    `Carry.to_json` (``{"sd": {old: new}, "ps": {old: new}}``). ``regs``
    (`register_moves`): a value set whose pixel shader is brought gets its values'
    registers renumbered too: a value set record names the **register** it fills (the
    Laser Sword's blade glowed in Case West, was pale in Case Zero while its glow values
    went to Case West's registers, U1 2026-10-13)."""
    sd = {int(k, 16): int(v, 16) for k, v in (maps.get("sd") or {}).items()}
    ps = {int(k, 16): int(v, 16) for k, v in (maps.get("ps") or {}).items()}
    arc = BigArchive.parse(data, name)
    _convert(arc, sd, ps, regs or {})
    return arc.to_bytes()


def _convert(arc: BigArchive, sd: dict, ps: dict, regs: dict) -> bool:
    changed = False
    for e in arc.entries:
        low = e.name.lower()
        if low == USED and sd:
            text = e.data().decode("latin-1")
            new = re.sub(r"0x([0-9A-Fa-f]{1,8})(\s*:)",
                         lambda m: (f"0x{sd[int(m.group(1), 16)]:08X}{m.group(2)}"
                                    if int(m.group(1), 16) in sd else m.group(0)), text)
            if new != text:
                e.set_data(new.encode("latin-1"))
                changed = True
        elif low.endswith(" commandbuffer") and sd:
            out = _commands(e.data(), sd)
            if out is not None:
                e.set_data(out)
                changed = True
        elif low.endswith(".scv") and ps:
            out = _value_set(e.data(), ps, regs)
            if out is not None:
                e.set_data(out)
                changed = True
        elif low.endswith((".big", ".tex")) and is_big(e.data()):
            try:
                inner = BigArchive.parse(e.data(), e.name)
            except Exception:                                   # noqa: BLE001
                continue
            if _convert(inner, sd, ps, regs):
                e.set_data(inner.to_bytes())
                changed = True
    return changed


def _commands(data: bytes, sd: dict) -> bytes | None:
    cmds = parse_command_buffer(data)
    hit = False
    out = []
    for c in cmds:
        args = c.args
        if c.op in (0x3C, 0x3F) and args and args[0] in sd:
            args = (sd[args[0]],) + args[1:]
            hit = True
        out.append(Command(c.word, args))
    if not hit:
        return None
    return b"".join(struct.pack(f">{1 + len(c.args)}I", c.word, *c.args) for c in out)


def _value_set(data: bytes, ps: dict, regs: dict | None = None) -> bytes | None:
    """A value set naming its brought pixel shader, its records' registers moved
    (``{u32 kind, 0, count, 1, register, name hash}`` + floats; formats/shader.py)."""
    n = struct.unpack_from(">I", data, 0)[0]
    at = ((4 + n + 3) & ~3) + 8
    old = struct.unpack_from(">I", data, at)[0]
    if old not in ps:
        return None
    out = bytearray(data)
    struct.pack_into(">I", out, at, ps[old])
    count = struct.unpack_from(">I", data, at + 4)[0]
    o = at + 8
    for _ in range(count):
        k, reg = struct.unpack_from(">I", data, o + 8)[0], struct.unpack_from(">I", data, o + 16)[0]
        if regs and reg in regs:
            struct.pack_into(">I", out, o + 16, regs[reg])
        o += 24 + 4 * k
    return bytes(out)

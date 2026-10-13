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
  uses ❓ in game: U3).
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
from ..formats.scene import Command, parse_command_buffer

USED = "usedshaders.txt"
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


@lru_cache(maxsize=4)
def number_map(src_root: str, dst_root: str) -> dict[str, int]:
    """Pixel parameter name -> the number it gets in the target (module docstring)."""
    from pathlib import Path
    src, dst = AssetTree(Path(src_root)), AssetTree(Path(dst_root))
    theirs = sb.registry(dst, "pd")
    used = set(theirs.values()) | set(sb.registry(dst, "vd").values())
    out = dict(theirs)
    mine = sb.registry(src, "pd")
    free = (n for n in range(1, 4096) if n not in used)
    for name, _ in sorted(mine.items(), key=lambda kv: kv[1]):
        if name not in out:
            out[name] = next(free)
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
    return raw                                     # a program: the same bytes, a new name


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


def convert_pack(data: bytes, maps: dict, name: str = "pack") -> bytes:
    """``data`` (a pack or scene archive) drawing with the brought shaders: ``maps`` is
    `Carry.to_json` (``{"sd": {old: new}, "ps": {old: new}}``)."""
    sd = {int(k, 16): int(v, 16) for k, v in (maps.get("sd") or {}).items()}
    ps = {int(k, 16): int(v, 16) for k, v in (maps.get("ps") or {}).items()}
    arc = BigArchive.parse(data, name)
    _convert(arc, sd, ps)
    return arc.to_bytes()


def _convert(arc: BigArchive, sd: dict, ps: dict) -> bool:
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
            out = _value_set(e.data(), ps)
            if out is not None:
                e.set_data(out)
                changed = True
        elif low.endswith((".big", ".tex")) and is_big(e.data()):
            try:
                inner = BigArchive.parse(e.data(), e.name)
            except Exception:                                   # noqa: BLE001
                continue
            if _convert(inner, sd, ps):
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


def _value_set(data: bytes, ps: dict) -> bytes | None:
    n = struct.unpack_from(">I", data, 0)[0]
    at = ((4 + n + 3) & ~3) + 8
    old = struct.unpack_from(">I", data, at)[0]
    if old not in ps:
        return None
    return data[:at] + struct.pack(">I", ps[old]) + data[at + 4:]

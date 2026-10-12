"""Building edits as a mod: ``ZONE_ORGANIZATION.big.pieces.json``, the level pieces of one
zone a mod hides, moves, turns, resizes or copies (phase 11 step 4, docs/formats.md
§Levels "Piece edits").

A level's buildings, floors and signs are **pieces** placed by the zone's binary table
``ZONE_ORGANIZATION.big/ModelInstanceArray`` (`dr2kit.formats.level`: 208-byte records,
scale, rotation, position, world bounds). Like the level text files' ``.edits.json``
(`dr2kit.formats.leveledits`), a mod doesn't ship the changed table: it ships **what it
changes, by piece name**, and the build applies that to the zone's own table, so two mods
that each move a different building of one zone merge (`merge`).

The file (``replace/data/models/environment/prologue/prologue_z05.big/ZONE_ORGANIZATION.big.pieces.json``)::

    {"format": "dr2kit-piece-edits/1",
     "pieces": {"z05_bowling_sign": {"position": [-172.4, 9.1, -27.0],
                                     "rotation": [0, 0.7071, 0, 0.7071],
                                     "scale": [1.5, 1.5, 1.5]},
                "z05_dumpster01":   {"hidden": true}},
     "copies": [{"piece": "z05_bench02", "position": [-160, 3.4, -30],
                 "rotation": [0, 0, 0, 1], "scale": [1, 1, 1]}]}

* ``pieces``: per piece name (every piece is placed once in its zone, in both games), any
  of ``position`` / ``rotation`` (quaternion x, y, z, w) / ``scale``, or ``hidden``.
* **Hidden** pieces keep their record and are moved `PARK_DROP` metres under the level,
  so no other record moves (the records' order and count stay as shipped). Whether the
  game also drops the piece's collision with it is measured in game (formats.md).
* ``copies``: new records of a piece of the same zone, appended after the shipped ones
  (``NumModelInstance`` grows). A copy is drawn from the same piece archive; it is named
  ``<piece>#<n>`` (n from 1, in list order) in Studio. **A copy has no collision** (in
  game, 2026-10-11: the copied van could be walked through).
* ``new`` (phase 14, buildings of one's own): records for **pieces the game doesn't
  have**, whose archives a mod adds to the zone (``add/…/<zone>.big/<piece>.big`` and its
  ``.tex`` / ``_LOD.tex``)::

      "new": [{"piece": "mod_box01", "like": "z02_hardware",
               "bounds": [[-2, 0, -2], [2, 3, 2]], "draw_distance": 200,
               "position": [-277, 3.26, -40.5], "rotation": [0, 0, 0, 1], "scale": [1, 1, 1]}]

  The record is the ``like`` piece's (the bytes nobody understands, its flags) with the
  new name, a piece number no record of the zone uses (``index``: past the zone's
  highest), the box of the new piece's shape in its own space (``bounds``, which gives
  the world bounds, centre and radius), its ``draw_distance`` (metres; the ``like``
  piece's when left out) and where it goes. Whether the game draws such a piece is the
  test T4a (docs/phase14-kickoff.md).
* ``collision``: the zone's collision shapes (``MERGED_COLLISION.big``, by group name
  ``meshCOL_pro_351``) a building edit moves (``move``: an offset in the shape's own
  space) or sends away (``hidden``: `PARK_DROP` metres down), `formats.collision.move_shapes`.
  **Collision is not tied to a piece's placement** (in game, 2026-10-11: a hidden store
  left its walls standing), so Studio moves a building's collision with it. These edits
  live in a second file next to the zone's ``MERGED_COLLISION.big``
  (``MERGED_COLLISION.big.pieces.json``, the same format; `collision_bytes`).

The world bounds of a changed record are worked out again from the shipped record (its
world box taken back to the piece's own space, then placed the new way): a little larger
than the tightest box when the piece is turned, never smaller.
"""

from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass, field, replace

from ..errors import FormatError
from .level import Placement, ZoneOrganization, quat_matrix

FORMAT = "dr2kit-piece-edits/1"
EXT = ".pieces.json"
TARGET = "ZONE_ORGANIZATION.big"   # the nested archives an edit file sits next to
COLLISION = "MERGED_COLLISION.big"
TARGETS = (TARGET, COLLISION)
PARK_DROP = 1000.0                 # metres a hidden piece goes down
KEYS = ("position", "rotation", "scale", "hidden")


@dataclass
class Edits:
    """One mod's changes to one zone's pieces (module docstring)."""
    pieces: dict[str, dict] = field(default_factory=dict)
    copies: list[dict] = field(default_factory=list)
    collision: dict[str, dict] = field(default_factory=dict)
    new: list[dict] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.pieces or self.copies or self.collision or self.new)

    def count(self) -> int:
        return len(self.pieces) + len(self.copies) + len(self.collision) + len(self.new)

    def placements_part(self) -> "Edits":
        return Edits(self.pieces, self.copies, new=self.new)

    def collision_part(self) -> "Edits":
        return Edits(collision=self.collision)


def _vec(v, n: int, where: str) -> list[float]:
    if not isinstance(v, (list, tuple)) or len(v) != n:
        raise FormatError(f"{where}: needs {n} numbers, has {v!r}")
    try:
        out = [float(c) for c in v]
    except (TypeError, ValueError):
        raise FormatError(f"{where}: needs {n} numbers, has {v!r}") from None
    if not all(math.isfinite(c) for c in out):
        raise FormatError(f"{where}: {v!r} is not a finite number")
    return out


def _spec(d, where: str, copy: bool = False) -> dict:
    if not isinstance(d, dict):
        raise FormatError(f"{where}: must be an object")
    out = {}
    for k, v in d.items():
        if copy and k == "piece":
            if not isinstance(v, str) or not v:
                raise FormatError(f"{where}: piece must be a name")
            out[k] = v
        elif k == "hidden" and not copy:
            out[k] = bool(v)
        elif k in ("position", "scale"):
            out[k] = _vec(v, 3, f"{where}.{k}")
        elif k == "rotation":
            q = _vec(v, 4, f"{where}.{k}")
            if sum(c * c for c in q) < 1e-6:
                raise FormatError(f"{where}.rotation: a zero quaternion")
            out[k] = q
        else:
            raise FormatError(f"{where}: unknown key {k!r} (allowed: "
                              f"{', '.join(('piece',) * copy + KEYS[:3 + (not copy)])})")
    if copy and "piece" not in out:
        raise FormatError(f"{where}: a copy names its piece")
    return out


def from_json(text: str, where: str = "<pieces>") -> Edits:
    """Read a ``.pieces.json`` (raises `FormatError` naming what is wrong)."""
    try:
        d = json.loads(text)
    except json.JSONDecodeError as e:
        raise FormatError(f"{where}: not JSON ({e})") from None
    if not isinstance(d, dict) or d.get("format") != FORMAT:
        raise FormatError(f"{where}: not a piece edit file (format must be {FORMAT!r})")
    extra = set(d) - {"format", "pieces", "copies", "zone", "collision", "new"}
    if extra:
        raise FormatError(f"{where}: unknown keys {sorted(extra)}")
    pieces = {str(k): _spec(v, f"{where}: {k}") for k, v in (d.get("pieces") or {}).items()}
    copies = d.get("copies") or []
    if not isinstance(copies, list):
        raise FormatError(f"{where}: copies must be a list")
    collision = {}
    for k, v in (d.get("collision") or {}).items():
        w = f"{where}: collision {k}"
        if not isinstance(v, dict) or set(v) - {"move", "hidden"}:
            raise FormatError(f"{w}: allowed: move (3 numbers), hidden")
        c = {}
        if "move" in v:
            c["move"] = _vec(v["move"], 3, f"{w}.move")
        if v.get("hidden"):
            c["hidden"] = True
        if c:
            collision[str(k)] = c
    new = d.get("new") or []
    if not isinstance(new, list):
        raise FormatError(f"{where}: new must be a list")
    return Edits(pieces, [_spec(c, f"{where}: copy {i + 1}", copy=True)
                          for i, c in enumerate(copies)], collision,
                 [_new_spec(c, f"{where}: new {i + 1}") for i, c in enumerate(new)])


def _new_spec(d, where: str) -> dict:
    """A ``new`` piece's record (module docstring), checked."""
    if not isinstance(d, dict):
        raise FormatError(f"{where}: must be an object")
    for k in ("piece", "like", "bounds"):
        if k not in d:
            raise FormatError(f"{where}: needs {k!r}")
    out = {}
    for k in ("piece", "like"):
        v = d[k]
        if not isinstance(v, str) or not v or len(v.encode("latin-1", "replace")) > 31:
            raise FormatError(f"{where}: {k} must be a name of at most 31 letters")
        out[k] = v
    b = d["bounds"]
    if not isinstance(b, (list, tuple)) or len(b) != 2:
        raise FormatError(f"{where}: bounds is [[min x, y, z], [max x, y, z]]")
    lo, hi = _vec(b[0], 3, f"{where}.bounds"), _vec(b[1], 3, f"{where}.bounds")
    if any(a > c for a, c in zip(lo, hi)):
        raise FormatError(f"{where}: bounds min is above max")
    out["bounds"] = [lo, hi]
    if "draw_distance" in d:
        out["draw_distance"] = _vec([d["draw_distance"]], 1, f"{where}.draw_distance")[0]
    rest = {k: v for k, v in d.items() if k not in ("piece", "like", "bounds", "draw_distance")}
    out.update(_spec(rest, where))
    if out.pop("hidden", None) is not None:
        raise FormatError(f"{where}: a new piece can't be hidden (leave it out)")
    return out


def _round(v) -> list[float]:
    return [round(c, 4) + 0.0 for c in v]          # + 0.0: never "-0.0"


def to_json(e: Edits, zone: str = "") -> str:
    """The ``.pieces.json`` text (pieces sorted by name; numbers to 0.1 mm)."""
    def clean(s):
        return {k: ([_round(x) for x in v] if k == "bounds" else
                    _round(v) if isinstance(v, list) else v) for k, v in s.items()}
    one = json.dumps                       # one line per piece: easy to read and diff
    lines = ['{"format": ' + one(FORMAT) + ","]
    if zone:
        lines.append(' "zone": ' + one(zone) + ",")
    names = sorted(e.pieces, key=str.lower)
    lines.append(' "pieces": {' + ("" if names else "}" + ("," if e.copies else "")))
    for i, k in enumerate(names):
        lines.append(f"  {one(k)}: {one(clean(e.pieces[k]))}" + ("," if i < len(names) - 1 else ""))
    if names:
        lines.append(" }" + ("," if e.copies else ""))
    if e.copies:
        lines.append(' "copies": [')
        lines += [f"  {one(clean(c))}" + ("," if i < len(e.copies) - 1 else "")
                  for i, c in enumerate(e.copies)]
        lines.append(" ]" + ("," if e.collision else ""))
    if e.new:
        if lines[-1].endswith(("}", "]")) and not lines[-1].endswith(","):
            lines[-1] += ","
        lines.append(' "new": [')
        lines += [f"  {one(clean(c))}" + ("," if i < len(e.new) - 1 else "")
                  for i, c in enumerate(e.new)]
        lines.append(" ]" + ("," if e.collision else ""))
    if e.collision:
        if not e.copies and not e.new and lines[-1].endswith("}"):
            lines[-1] += ","
        names = sorted(e.collision, key=str.lower)
        lines.append(' "collision": {')
        lines += [f"  {one(k)}: {one(clean(e.collision[k]))}" + ("," if i < len(names) - 1 else "")
                  for i, k in enumerate(names)]
        lines.append(" }")
    return "\n".join(lines) + "\n}\n"


# ---- the maths --------------------------------------------------------------------------

def _mat(p_scale, q):
    r = quat_matrix(q)
    return [[r[i][j] * p_scale[j] for j in range(3)] for i in range(3)]


def _inverse3(m):
    a, b, c = m
    det = (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
           + a[2] * (b[0] * c[1] - b[1] * c[0]))
    if abs(det) < 1e-12:
        raise FormatError("a piece with a zero scale can't be placed")
    inv = [[(b[1] * c[2] - b[2] * c[1]), -(a[1] * c[2] - a[2] * c[1]), (a[1] * b[2] - a[2] * b[1])],
           [-(b[0] * c[2] - b[2] * c[0]), (a[0] * c[2] - a[2] * c[0]), -(a[0] * b[2] - a[2] * b[0])],
           [(b[0] * c[1] - b[1] * c[0]), -(a[0] * c[1] - a[1] * c[0]), (a[0] * b[1] - a[1] * b[0])]]
    return [[v / det for v in row] for row in inv]


def _corners(lo, hi):
    return [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]


def _box(points):
    return (tuple(min(p[i] for p in points) for i in range(3)),
            tuple(max(p[i] for p in points) for i in range(3)))


def placed(p: Placement, position=None, rotation=None, scale=None) -> Placement:
    """``p`` put another way (any of the three left out stays), with world bounds,
    centre and radius worked out again (module docstring)."""
    pos = tuple(position) if position is not None else tuple(p.position)
    rot = tuple(rotation) if rotation is not None else tuple(p.rotation)
    n = math.sqrt(sum(c * c for c in rot)) or 1.0
    rot = tuple(c / n for c in rot)
    scl = tuple(scale) if scale is not None else tuple(p.scale)
    inv = _inverse3(_mat(p.scale, p.rotation))
    local = [tuple(sum(inv[i][j] * (c[j] - p.position[j]) for j in range(3)) for i in range(3))
             for c in _corners(p.bounds_min, p.bounds_max)]
    m = _mat(scl, rot)
    world = [tuple(sum(m[i][j] * c[j] for j in range(3)) + pos[i] for i in range(3))
             for c in local]
    lo, hi = _box(world)
    old = max(abs(s) for s in p.scale) or 1.0
    radius = p.radius * max(abs(s) for s in scl) / old
    centre = tuple((a + b) / 2 for a, b in zip(lo, hi))
    return replace(p, position=pos, rotation=rot, scale=scl, bounds_min=lo, bounds_max=hi,
                   centre=centre, radius=radius)


def parked(p: Placement) -> Placement:
    """``p`` moved `PARK_DROP` metres down (a hidden piece)."""
    d = (0.0, -PARK_DROP, 0.0)
    add = lambda v: tuple(a + b for a, b in zip(v, d))  # noqa: E731
    return replace(p, position=add(p.position), bounds_min=add(p.bounds_min),
                   bounds_max=add(p.bounds_max), centre=add(p.centre))


# ---- applying ---------------------------------------------------------------------------

def apply(org: ZoneOrganization, e: Edits, where: str = "") -> ZoneOrganization:
    """``org`` with ``e`` applied (a new object). Raises `FormatError` naming every piece
    the zone doesn't place."""
    by = {}
    for i, p in enumerate(org.placements):
        by.setdefault(p.piece.lower(), i)
    missing = [k for k in e.pieces if k.lower() not in by]
    missing += [c["piece"] for c in e.copies if c["piece"].lower() not in by]
    if missing:
        raise FormatError(f"{where}: the zone places no piece named "
                          f"{', '.join(sorted(set(missing)))}")
    out = list(org.placements)
    for name, spec in e.pieces.items():
        i = by[name.lower()]
        p = placed(out[i], spec.get("position"), spec.get("rotation"), spec.get("scale"))
        out[i] = parked(p) if spec.get("hidden") else p
    for c in e.copies:
        src = org.placements[by[c["piece"].lower()]]
        out.append(placed(src, c.get("position"), c.get("rotation"), c.get("scale")))
    next_index = max((p.index for p in org.placements), default=-1) + 1
    for c in e.new:
        if c["like"].lower() not in by:
            raise FormatError(f"{where}: the zone places no piece named {c['like']} "
                              f"(a new piece's like)")
        if c["piece"].lower() in by:
            raise FormatError(f"{where}: the zone already has a piece {c['piece']}: "
                              f"give the new one another name")
        out.append(new_placement(org.placements[by[c["like"].lower()]], c, next_index))
        next_index += 1
    return ZoneOrganization(out, org.dynamic, org.info)


def new_placement(like: Placement, spec: dict, index: int) -> Placement:
    """A record for a new piece (module docstring, ``new``): ``like``'s record renamed,
    numbered ``index``, its box ``spec["bounds"]`` placed as asked."""
    lo, hi = (tuple(v) for v in spec["bounds"])
    radius = math.dist(lo, hi) / 2
    base = replace(like, piece=spec["piece"], name2=spec["piece"], raw_names=b"",
                   scale=(1.0, 1.0, 1.0), rotation=(0.0, 0.0, 0.0, 1.0),
                   position=(0.0, 0.0, 0.0), bounds_min=lo, bounds_max=hi,
                   centre=tuple((a + b) / 2 for a, b in zip(lo, hi)), radius=radius,
                   index=index, draw_distance=spec.get("draw_distance", like.draw_distance))
    return placed(base, spec.get("position", (0.0, 0.0, 0.0)), spec.get("rotation"),
                  spec.get("scale"))


def collision_bytes(archive: bytes, e: Edits, where: str = "") -> bytes:
    """``MERGED_COLLISION.big`` with the collision edits of ``e`` applied."""
    from .collision import move_shapes
    moves = {}
    for mesh, spec in e.collision.items():
        d = list(spec.get("move") or (0.0, 0.0, 0.0))
        if spec.get("hidden"):
            d[1] -= PARK_DROP
        moves[mesh] = d
    return move_shapes(archive, moves, where or COLLISION) if moves else archive


def target_bytes(archive: bytes, e: Edits, where: str) -> bytes:
    """The archive an edit file sits next to (`TARGETS`, by the end of ``where``) with
    the edits applied."""
    if where.lower().endswith(COLLISION.lower()):
        return collision_bytes(archive, e, where)
    return zone_bytes(archive, e, where)


def zone_bytes(archive: bytes, e: Edits, where: str = "") -> bytes:
    """``ZONE_ORGANIZATION.big`` (the archive's bytes) with ``e`` applied: its
    ``ModelInstanceArray`` and, for copies, ``NumModelInstance`` written again, each
    compressed as before."""
    from ..container.big import BigArchive
    arc = BigArchive.parse(archive, where or TARGET)
    entries = {x.name.lower(): x for x in arc.entries}
    org = ZoneOrganization.from_entries({x.name: x.data() for x in arc.entries}, where)
    new = apply(org, e, where)
    entries["modelinstancearray"].set_data(new.placements_bytes())
    if len(new.placements) != len(org.placements):
        entries["nummodelinstance"].set_data(struct.pack(">I", len(new.placements)))
    return arc.to_bytes()


@dataclass
class Layer:
    """One mod's edits of one zone, for `merge`."""
    mod: str
    priority: int
    edits: Edits


def merge(layers: list[Layer]) -> tuple[Edits, list[tuple[str, str, str]], list[str]]:
    """Several mods' edits of one zone as one: per piece, the highest priority wins
    (``shadowed``: ``(what, losing mod, winning mod)``); the same piece changed by two
    mods of the same priority is a problem. Copies of every mod are kept."""
    out = Edits()
    owner: dict[str, Layer] = {}
    shadowed, problems = [], []
    for L in sorted(layers, key=lambda L: L.priority):
        for name, spec in L.edits.pieces.items():
            key = name.lower()
            if key in owner:
                if owner[key].priority == L.priority:
                    problems.append(f"piece {name}: changed by both {owner[key].mod} and "
                                    f"{L.mod} at the same priority; raise one mod's priority")
                    continue
                shadowed.append((f"piece {name}", owner[key].mod, L.mod))
            owner[key] = L
            out.pieces[name] = spec
        for name, spec in L.edits.collision.items():
            key = "collision:" + name.lower()
            if key in owner:
                if owner[key].priority == L.priority:
                    problems.append(f"collision {name}: changed by both {owner[key].mod} and "
                                    f"{L.mod} at the same priority; raise one mod's priority")
                    continue
                shadowed.append((f"collision {name}", owner[key].mod, L.mod))
            owner[key] = L
            out.collision[name] = spec
        out.copies += L.edits.copies
        out.new += L.edits.new
    return out, shadowed, problems


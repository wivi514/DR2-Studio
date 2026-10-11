"""Zombies standing in their areas: the crowds a level's missions put there (phase 10,
stretch).

A level's zombie crowds are not in the level files but in ``missions.txt``
(docs/formats.md §Levels, "Zombie spawns"): each ``cMissionZombieFactory`` inside a
mission's ``cMissionLevelReady`` (``LevelName = "LEVEL_PROLOGUE"``) fills a **zombie
area** (``ZombieWarehouseName``: a ``cZombieWarehouse`` of the level file, a set of floor
polygons) with ``Amount<n>`` zombies of ``Type<n>`` (``zombie_skinny``). A type is a
model folder ``data/models/zombies.big/<type>.big`` holding three detail levels
(``<type>_2.big`` high, ``_3`` medium, ``_4`` low; phase 9).

`crowds` lists, for a level script, every factory of every mission for that level;
`spots` spreads them over their area's polygons the way a viewer can show them: points
picked at random inside the triangles (by area), on the floor, each turned at random,
each with one of a few looks per type (`convert.variants`: random choices, seeded), so a
crowd looks like a crowd. The game places and dresses its zombies itself while playing;
this is a picture of *where* and *what*, not of the exact spots (which aren't stored).

Which missions run when is the game's business: by default every factory of the level
counts, each crowd capped (``per_area``) so the view stays light.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from ..container.vpath import AssetTree, join
from ..errors import VPathError
from ..formats.levelscript import Document
from . import placed

ZOMBIES = "data/models/zombies.big"
DETAIL = {"high": 2, "medium": 3, "low": 4}


@dataclass
class Crowd:
    """One factory: ``amounts`` of each zombie type into the area ``area``."""
    mission: str
    area: str
    amounts: dict[str, int] = field(default_factory=dict)
    line: int = 0


@dataclass
class Spot:
    """One zombie to draw."""
    type: str
    position: tuple[float, float, float]
    yaw: float                       # radians about Y
    look: int                        # which of the type's looks (0: the default)
    crowd: Crowd | None = None


def crowds(tree: AssetTree, script: str) -> list[Crowd]:
    """Every zombie factory that ``missions.txt`` runs on the level of ``script``."""
    try:
        doc = Document.parse(tree.resolve(join(placed.DATAFILE, "missions.txt")).data(),
                             "missions.txt")
    except VPathError:
        return []
    want = f"level_{script}".lower()
    out: list[Crowd] = []

    def go(b, mission, level):
        if b.cls == "cMissionDefinition":
            mission = b.name
        if b.cls == "cMissionLevelReady":
            level = (b.get("LevelName") or "").lower()
        if b.cls == "cMissionZombieFactory" and level == want:
            c = Crowd(mission or "", b.get("ZombieWarehouseName") or "", line=b.line + 1)
            for p in b.props:
                if p.key.startswith("Type") and p.key[4:].isdigit():
                    try:
                        n = int(b.get(f"Amount{p.key[4:]}") or 0)
                    except ValueError:
                        n = 0
                    if p.value and n > 0:
                        c.amounts[p.value] = c.amounts.get(p.value, 0) + n
            if c.area and c.amounts:
                out.append(c)
        for ch in b.children:
            go(ch, mission, level)
    for b in doc.blocks:
        go(b, None, None)
    return out


def model_vpath(tree: AssetTree, ztype: str, detail: str = "medium") -> str | None:
    """The model of a zombie type at a detail level (falling back to the others)."""
    order = [DETAIL[detail]] + [d for d in (2, 3, 4) if d != DETAIL[detail]]
    for d in order:
        vp = f"{ZOMBIES}/{ztype}.big/{ztype}_{d}.big"
        try:
            tree.resolve(vp)
            return vp
        except VPathError:
            continue
    return None


def _triangles(polygon):
    pts = list(polygon)
    if len(pts) < 3:
        return []
    return [(pts[a], pts[b], pts[c]) for a, b, c in _triangulate_xz(pts)]


def spots(ls: placed.LevelScript, crowd_list: list[Crowd], *, per_area: int = 12,
          looks: int = 3, seed: int = 1) -> list[Spot]:
    """Zombies to draw for ``crowd_list`` in the areas of ``ls`` (module docstring).
    Each crowd gets at most ``per_area`` zombies, shared out over its types by amount."""
    rng = random.Random(seed)
    areas: dict[str, list] = {}
    for t in ls.things:
        if t.kind == "zombie_area" and t.polygon and t.parent:
            areas.setdefault(t.parent.lower(), []).extend(_triangles(t.polygon))
    out: list[Spot] = []
    for c in crowd_list:
        tris = areas.get(c.area.lower())
        if not tris:
            continue
        weights = [_area(t) for t in tris]
        total = sum(c.amounts.values())
        n = min(per_area, total)
        types = []
        for ztype, amount in sorted(c.amounts.items()):
            types += [ztype] * max(1, round(n * amount / total))
        for ztype in types[:n]:
            a, b, d = rng.choices(tris, weights)[0]
            r1, r2 = rng.random(), rng.random()
            if r1 + r2 > 1:
                r1, r2 = 1 - r1, 1 - r2
            p = tuple(a[i] + r1 * (b[i] - a[i]) + r2 * (d[i] - a[i]) for i in range(3))
            out.append(Spot(ztype, p, rng.uniform(-math.pi, math.pi), rng.randrange(looks), c))
    return out


def _triangulate_xz(pts) -> list[tuple[int, int, int]]:
    """A floor polygon (any winding, seen from above) as triangles: ear clipping in the
    XZ plane; falls back to a fan when the polygon isn't simple."""
    idx = list(range(len(pts)))
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][2] - pts[(i + 1) % len(pts)][0] * pts[i][2]
               for i in idx)
    sign = 1 if area > 0 else -1

    def cross(o, a, b):
        return ((pts[a][0] - pts[o][0]) * (pts[b][2] - pts[o][2])
                - (pts[a][2] - pts[o][2]) * (pts[b][0] - pts[o][0])) * sign

    def inside(p, a, b, c):
        return cross(a, b, p) >= 0 and cross(b, c, p) >= 0 and cross(c, a, p) >= 0
    out = []
    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        for k in range(len(idx)):
            a, b, c = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            if cross(a, b, c) <= 0:
                continue
            if any(inside(p, a, b, c) for p in idx if p not in (a, b, c)):
                continue
            out.append((a, b, c))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        out.append(tuple(idx))
    elif len(idx) > 3:                       # not simple: a fan over what is left
        out += [(idx[0], idx[i], idx[i + 1]) for i in range(1, len(idx) - 1)]
    return out


def _area(tri) -> float:
    a, b, c = tri
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    return 0.5 * abs(u[0] * v[2] - u[2] * v[0]) + 1e-6

"""Buildings: a zone's level pieces grouped into the buildings a player sees, each with
its collision shapes (phase 11 step 4; user request 2026-10-11: "should see building as a
whole and everything from it as child of it in hierarchy including its collision").

Why it is needed: the game has no "building" object. A building is several **pieces**
(`formats.level` placements: ``z04_gen_e_structure`` the walls, ``z04_gen_e_details`` the
boarded windows, ``z04_gen_e_decals`` the writing, ``z04_roof_vent_3`` on its roof), and
its collision is a separate **shape** of the zone's ``MERGED_COLLISION.big``
(`convert.level.zone_shapes`) that often has no name in common with it (the store's walls
are ``pro_351``). Hiding one piece in game (2026-10-11) left the boards, the writing and
the collision standing; so the editor works on whole buildings.

How a zone's pieces are grouped (`zone_buildings`), measured to give the buildings of
CZ's street (docs/formats.md §Levels "Buildings"):

1. Pieces are taken biggest first. A piece joins the smallest building found so far whose
   box (1 m larger) holds most of its own box (`INSIDE`), or whose first piece shares its
   name stem (``z04_sheriff_ext`` / ``z04_sheriff_detail``) and overlaps it (`NEAR`);
   otherwise it starts a building.
   **And it must touch the building**: when the building's first piece has collision,
   the piece's box (`TOUCH` metres larger) must meet one of its collision triangles. A
   box is not a wall: a fence around a car park holds the cars in its box, but its thin
   collision doesn't reach them, while a roof vent sits on the store's roof.
   A piece **resting on top** of a building joins it too: its footprint (seen from above)
   within the building's (`INSIDE`) and its bottom within `TOUCH` of the building's top
   (the store's air conditioner: in game 2026-10-11 it was left floating when the store
   was hidden, because only its bottom 35 cm lies inside the store's box). When several
   buildings would take a piece, one whose collision it touches comes first, then the
   smallest.
2. Pieces wider than `HUGE` metres (roads, ground, the hills), and flat ones (less than
   `SLAB` high and more than `SLAB_WIDE` wide: concrete slabs, car parks) are never a
   building's first piece, so they don't swallow what stands on them: each stays a
   building of its own.
3. A collision shape goes to the building of its piece (a shape placed by its piece),
   else to the smallest building whose box holds most of the shape's box (a shape in
   world space, like ``pro_351``). Shapes no building holds (the zone's ground, long
   fences) stay with no building.

It is a guess from shapes and names, not a fact of the file: the Inspector can edit one
piece alone, and the census counts what the grouping gives.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .level import PlacedShape, ZoneData, piece_name

HUGE = 60.0         # metres: a piece this wide is ground, a road or scenery
INSIDE = 0.8        # a piece joins a building whose box holds this much of its box
NEAR = 0.3          # ... or this much, when their names share a stem
FLAT = 0.05         # metres: the least thickness counted (decals and floors are flat)
TOUCH = 0.5         # metres: how near a part must come to its building's collision
SLAB = 2.5          # metres: a piece lower than this …
SLAB_WIDE = 8.0     # … and wider than this is ground, not a building


@dataclass
class Building:
    """One building of a zone: its first (biggest) piece names it."""
    zone: str
    name: str                                     # the first piece's name
    parts: list[str] = field(default_factory=list)          # piece names, the first first
    shapes: list[str] = field(default_factory=list)         # collision groups (meshCOL_…)
    bounds_min: tuple = (0.0, 0.0, 0.0)
    bounds_max: tuple = (0.0, 0.0, 0.0)

    @property
    def centre(self) -> tuple:
        return tuple((a + b) / 2 for a, b in zip(self.bounds_min, self.bounds_max))

    def to_dict(self) -> dict:
        return {"zone": self.zone, "name": self.name, "parts": self.parts,
                "shapes": self.shapes, "min": list(self.bounds_min),
                "max": list(self.bounds_max)}


def _box(lo, hi):
    return tuple(lo), tuple(hi)


def _volume(lo, hi) -> float:
    v = 1.0
    for a, b in zip(lo, hi):
        v *= max(b - a, FLAT)
    return v


def _held(outer, inner, grow: float = 1.0) -> float:
    """How much of box ``inner`` lies in box ``outer`` made ``grow`` metres larger (0…1;
    a flat side counts as `FLAT` thick)."""
    (olo, ohi), (ilo, ihi) = outer, inner
    part = whole = 1.0
    for i in range(3):
        lo, hi = olo[i] - grow, ohi[i] + grow
        size = ihi[i] - ilo[i]
        if size < FLAT:
            o = FLAT if lo <= ilo[i] <= hi else 0.0
        else:
            o = max(0.0, min(hi, ihi[i]) - max(lo, ilo[i]))
        part *= o
        whole *= max(size, FLAT)
    return part / whole


def _held_from_above(outer, inner) -> float:
    """How much of ``inner``'s footprint (x and z) lies in ``outer``'s, 1 m larger."""
    (olo, ohi), (ilo, ihi) = outer, inner
    part = whole = 1.0
    for i in (0, 2):
        size = max(ihi[i] - ilo[i], FLAT)
        part *= max(0.0, min(ohi[i] + 1.0, ihi[i]) - max(olo[i] - 1.0, ilo[i])) if \
            ihi[i] - ilo[i] >= FLAT else (FLAT if olo[i] - 1 <= ilo[i] <= ohi[i] + 1 else 0.0)
        whole *= size
    return part / whole


def stem(name: str) -> str:
    """``z04_sheriff_ext`` → ``z04_sheriff``, ``z04_gen_f_decal_2`` → ``z04_gen_f``: the
    name without its numbers and last word, if that leaves more than the zone's prefix."""
    words = name.lower().split("_")
    while len(words) > 2 and words[-1].isdigit():
        words.pop()
    return "_".join(words[:-1]) if len(words) > 2 else ""


def related(a: str, b: str) -> bool:
    """Two piece names of one building: one's stem begins the other's (``z04_pawn_int``
    and ``z04_pawn``; never ``z04_gen_e`` and ``z04_gen_f``)."""
    sa, sb = stem(a), stem(b)
    if not sa or not sb:
        return False
    return sa == sb or sa.startswith(sb + "_") or sb.startswith(sa + "_")


def _tri_boxes(shape: PlacedShape) -> list:
    w = shape.world
    return [(tuple(min(w[a][i], w[b][i], w[c][i]) for i in range(3)),
             tuple(max(w[a][i], w[b][i], w[c][i]) for i in range(3)))
            for a, b, c in shape.shape.triangles]


def _touches(box, tris) -> bool:
    lo, hi = box
    return any(all(tlo[i] <= hi[i] + TOUCH and lo[i] - TOUCH <= thi[i] for i in range(3))
               for tlo, thi in tris)


def zone_buildings(zone: ZoneData, shapes: list[PlacedShape] | None = None,
                   moves: dict[str, str] | None = None) -> list[Building]:
    """The zone's buildings (module docstring), biggest first. ``moves``: the modder's own
    corrections, piece name → the building it belongs to (its first piece), or ``""``
    for a building of its own (`corrections`)."""
    shapes = shapes or []
    own: dict[str, list] = {}               # piece -> its collision (placed by it, or held)

    def collision_of(name: str, box) -> list:
        key = name.lower()
        if key not in own:
            tris = []
            for sh in shapes:
                if (sh.rule == "piece" and sh.piece is not None and
                        sh.piece.piece.lower() == key) or \
                        (sh.rule == "world" and _held(box, sh.bounds, TOUCH) >= INSIDE):
                    tris += _tri_boxes(sh)
            own[key] = tris
        return own[key]
    pieces = []
    for p in zone.placements:
        name = piece_name(p, zone)
        if name is not None:
            pieces.append((name, _box(p.bounds_min, p.bounds_max)))
    pieces.sort(key=lambda t: -_volume(*t[1]))
    out: list[Building] = []
    boxes: list = []
    of_piece: dict[str, Building] = {}
    huge: set[str] = set()                    # buildings that are ground, roads, scenery
    firsts: dict[str, tuple] = {}             # a building's first piece's box
    for name, box in pieces:
        width = max(b - a for a, b in zip(*box))
        best = None
        if width <= HUGE:
            found = []                    # (touches its collision, box volume, building)
            for b, bb in zip(out, boxes):
                if b.name.lower() in huge:
                    continue
                held = _held(bb, box)
                same = related(name, b.name)
                on_top = (_held_from_above(bb, box) >= INSIDE and
                          bb[0][1] <= box[0][1] <= bb[1][1] + TOUCH)
                if held >= INSIDE or (same and held >= NEAR) or on_top:
                    tris = collision_of(b.name, firsts[b.name.lower()])
                    touch = bool(tris) and _touches(box, tris)
                    if same or not tris or touch:
                        found.append((not touch, _volume(*bb), out.index(b)))
            if found:                     # the one it touches first, then the smallest
                best = out[min(found)[2]]
        if best is None:
            best = Building(zone.name, name)
            firsts[name.lower()] = box
            if width > HUGE or (box[1][1] - box[0][1] < SLAB and width > SLAB_WIDE):
                huge.add(name.lower())
            out.append(best)
            boxes.append(box)
        else:
            i = out.index(best)
            lo, hi = boxes[i]
            boxes[i] = (tuple(min(a, b) for a, b in zip(lo, box[0])),
                        tuple(max(a, b) for a, b in zip(hi, box[1])))
        best.parts.append(name)
        of_piece[name.lower()] = best
    for piece, target in (moves or {}).items():
        out, boxes = _move(out, boxes, piece, target, dict(pieces), of_piece)
    for b, (lo, hi) in zip(out, boxes):
        b.bounds_min, b.bounds_max = lo, hi
    for s in shapes:
        b = None
        if s.rule == "piece" and s.piece is not None:
            b = of_piece.get(s.piece.piece.lower())
        else:
            sb = s.bounds
            for c, bb in zip(out, boxes):
                if c.name.lower() in huge:
                    continue
                if _held(bb, sb, 0.5) >= INSIDE and (b is None or _volume(*bb) <
                                                     _volume(b.bounds_min, b.bounds_max)):
                    b = c
        if b is not None:
            b.shapes.append(s.shape.mesh)
    return out


def _move(out, boxes, piece, target, box_of, of_piece):
    """One correction: ``piece`` out of its building, into ``target``'s (or alone)."""
    key = piece.lower()
    src = of_piece.get(key)
    if src is None:
        return out, boxes
    name = next(p for p in src.parts if p.lower() == key)
    dst = next((b for b in out if any(p.lower() == target.lower() for p in b.parts)), None) \
        if target else None
    if dst is src:
        return out, boxes
    src.parts.remove(name)
    if dst is None:
        dst = Building(src.zone, name)
        out.append(dst)
        boxes.append(box_of[name])
    dst.parts.append(name)
    of_piece[key] = dst
    keep = [(b, bb) for b, bb in zip(out, boxes) if b.parts]
    out = [b for b, _ in keep]
    boxes = []
    for b in out:                           # boxes made again from the parts
        bs = [box_of[p] for p in b.parts]
        boxes.append((tuple(min(x[0][i] for x in bs) for i in range(3)),
                      tuple(max(x[1][i] for x in bs) for i in range(3))))
        if b.name not in b.parts:           # its first piece moved out: the biggest leads
            b.parts.sort(key=lambda p: -_volume(*box_of[p]))
            b.name = b.parts[0]
    return out, boxes


CORRECTIONS = "buildings.json"


def corrections(game: str, zone: str) -> dict[str, str]:
    """The modder's own building corrections of one zone (saved in the config folder,
    `set_correction`): piece → building (``""``: alone)."""
    import json
    from ..userdirs import config_dir
    f = config_dir() / CORRECTIONS
    try:
        return json.loads(f.read_text("utf-8")).get(f"{game}/{zone}".lower(), {})
    except (OSError, ValueError):
        return {}


def set_correction(game: str, zone: str, piece: str, building: str | None) -> None:
    """Keep ``piece`` in ``building`` (``""``: alone; None: as Studio guesses)."""
    import json
    from ..userdirs import config_dir
    f = config_dir() / CORRECTIONS
    try:
        data = json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        data = {}
    z = data.setdefault(f"{game}/{zone}".lower(), {})
    if building is None:
        z.pop(piece, None)
    else:
        z[piece] = building
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", "utf-8")


def building_of(buildings: list[Building], piece: str) -> Building | None:
    """The building a piece (or a copy, ``<piece>#<n>``) is part of."""
    key = piece.split("#", 1)[0].lower()
    return next((b for b in buildings if any(p.lower() == key for p in b.parts)), None)

"""Levels in 3D: find a game's levels, read their zones, put the pieces in their places.

A **level** (Case Zero's Fortune City street ``prologue``, Case West's
``living_research``…) is a folder under ``data/models/environment/`` with a
``zonelist.big``; each **zone** is an archive of **pieces** (ordinary scenes) plus a
placement table (`dr2kit.formats.level`). This module:

* lists levels and zones (`list_levels`, `Level`), and a zone's pieces, placements, and
  what doesn't match: placements naming no piece, pieces never placed (`ZoneData`);
* builds a zone as one ``.glb`` (`zone_glb`): each piece exported by
  `convert.model.model_glb` exactly as the Library shows it, then placed by its record
  (world = rotation × (scale × local) + position, checked by ``dr2 census --levels``),
  one mesh shared by every placement of a piece (`convert.gltf.Assembler`). ``lod=True``
  uses the game's small ``_LOD`` textures (the Maps tab's far zones).

Why one ``.glb`` per zone: a whole level is ~1.2 million triangles and ~200 MB of
archives. The game itself streams zone by zone; so do the Maps tab (near the camera
first) and the export (one file per zone by default, docs/phase10-kickoff.md §Decisions).

Every piece is read through the tree it is given, so a `mods.preview.ModdedTree` shows
a level with the switched-on mods (phase 10 step 5) without anything here knowing.
Formats and how they were checked: docs/formats.md §Levels.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..container.vpath import AssetTree, join
from ..errors import Dr2Error, VPathError
from ..formats import level as lvl

LEVELS_DIR = "data/models/environment"
ORGANIZATION = "ZONE_ORGANIZATION.big"
NOT_PIECES = {"zone_organization", "merged_collision"}      # zone entries that aren't pieces


@dataclass
class ZoneData:
    """What one zone holds: its pieces (name → scene vpath), placements, and mismatches."""
    level: str
    zone: lvl.Zone
    vpath: str                                   # the zone's archive
    pieces: dict[str, str] = field(default_factory=dict)
    organization: lvl.ZoneOrganization | None = None
    unplaced: list[str] = field(default_factory=list)       # pieces with no placement
    missing: list[str] = field(default_factory=list)        # placements naming no piece

    @property
    def name(self) -> str:
        return self.zone.zone

    @property
    def placements(self) -> list[lvl.Placement]:
        return self.organization.placements if self.organization else []


@dataclass
class Level:
    """One level folder: its zones (from ``zonelist.big``), read on demand."""
    tree: AssetTree
    name: str
    vpath: str
    zones: list[lvl.Zone]

    @classmethod
    def open(cls, tree: AssetTree, name: str) -> "Level":
        """The level called ``name`` (``prologue``), or its folder's vpath."""
        vp = name if "/" in name else join(LEVELS_DIR, name)
        try:
            node = tree.resolve(vp)
            num = tree.resolve(join(node.vpath, "zonelist.big", "NumZones")).data()
            zl = tree.resolve(join(node.vpath, "zonelist.big", "ZoneList")).data()
        except VPathError as e:
            raise Dr2Error(f"{name}: not a level (no zonelist.big: {e})") from None
        zones = lvl.read_zone_list(num, zl, join(node.vpath, "zonelist.big"))
        return cls(tree, node.vpath.rsplit("/", 1)[-1], node.vpath, zones)

    def zone_names(self) -> list[str]:
        return [z.zone for z in self.zones]

    def find_zone(self, zone: str) -> lvl.Zone:
        """A zone by name (``prologue_z05``) or short name (``z05``), any case."""
        key = zone.lower()
        for z in self.zones:
            if z.zone.lower() in (key, f"{self.name.lower()}_{key}"):
                return z
        raise Dr2Error(f"{self.name} has no zone {zone!r} (it has "
                       f"{', '.join(self.zone_names())})")

    def zone(self, zone: str | lvl.Zone) -> ZoneData:
        """Read one zone: its pieces, placement table and mismatches."""
        z = zone if isinstance(zone, lvl.Zone) else self.find_zone(zone)
        zvp = join(self.vpath, f"{z.zone}.big")
        try:
            arc = self.tree.open_archive(zvp)
        except VPathError as e:
            raise Dr2Error(f"{zvp}: the zone's archive is missing ({e})") from None
        zvp = arc.source
        out = ZoneData(self.name, z, zvp)
        org = None
        for e in arc.entries:
            low = e.name.lower()
            if not low.endswith(".big"):
                continue
            stem = e.name[:-4]
            if low == ORGANIZATION.lower():
                sub = self.tree.open_archive(join(zvp, e.name))
                org = lvl.ZoneOrganization.from_entries({x.name: x.data() for x in sub.entries},
                                                        join(zvp, e.name))
            elif stem.lower() not in NOT_PIECES:
                out.pieces[stem] = join(zvp, e.name, f"_COMP_{stem}.big")
        if org is None:
            raise Dr2Error(f"{zvp}: no {ORGANIZATION}")
        out.organization = org
        placed = {p.piece.lower() for p in org.placements}
        have = {k.lower(): k for k in out.pieces}
        out.unplaced = sorted(k for k in out.pieces if k.lower() not in placed)
        out.missing = sorted({p.piece for p in org.placements if p.piece.lower() not in have})
        return out

    def zone_data(self) -> list[ZoneData]:
        return [self.zone(z) for z in self.zones]


def list_levels(tree: AssetTree) -> list[Level]:
    """Every level folder of the game (folders under ``environment/`` with a zone list),
    sorted by name. Level-less folders and loose ``.big`` files (the sky) are skipped."""
    try:
        node = tree.resolve(LEVELS_DIR)
    except VPathError:
        return []
    out = []
    for p in sorted(node.path.iterdir(), key=lambda p: p.name.lower()):
        if p.is_dir() and any(c.name.lower() == "zonelist.big" for c in p.iterdir()):
            out.append(Level.open(tree, join(node.vpath, p.name)))
    return out


def piece_name(placement: lvl.Placement, zone: ZoneData) -> str | None:
    """The piece a placement puts down, with the archive's letter case (None: missing)."""
    key = placement.piece.lower()
    return next((k for k in zone.pieces if k.lower() == key), None)


def unit(q) -> tuple[float, float, float, float]:
    """A quaternion scaled to length 1 (glTF requires it; one placement of Case West's
    safehouse stores a length of 1.017)."""
    n = sum(c * c for c in q) ** 0.5 or 1.0
    return tuple(c / n for c in q)


def placement_node(p: lvl.Placement, extras: dict | None = None) -> dict:
    """A placement as `gltf.Assembler.add` takes it."""
    out = {"name": p.piece, "translation": p.position, "rotation": unit(p.rotation),
           "extras": {"dr2_piece": p.piece, "dr2_index": p.index, **(extras or {})}}
    if any(abs(s - 1.0) > 1e-7 for s in p.scale):
        out["scale"] = p.scale
    return out


@dataclass
class ZoneStats:
    pieces: int = 0
    placements: int = 0
    triangles: int = 0
    textures: int = 0
    failed: list = field(default_factory=list)              # (piece, why)
    missing_textures: set = field(default_factory=set)


def zone_glb(tree: AssetTree, zone: ZoneData, *, game: str, textures: bool = True,
             lod: bool = False, db_path=None, stats: ZoneStats | None = None,
             assembler=None, parent: int | None = None, progress=None,
             png_level: int = 6) -> bytes | None:
    """The zone as one ``.glb``: every placed piece in its place, under one group node
    named after the zone. ``lod``: the small ``_LOD`` textures. With ``assembler`` (a
    `gltf.Assembler`), the zone goes into it under ``parent`` and None is returned
    (several zones in one file). A piece that fails to read is skipped and named in
    ``stats.failed``, never silently. ``png_level`` 1 makes the textures 3× faster and
    a little bigger (the Maps tab's cache)."""
    from . import gltf
    from .model import TextureFinder, model_glb, read_scene
    st = stats if stats is not None else ZoneStats()
    own = assembler is None
    asm = assembler or gltf.Assembler()
    group = asm.group(zone.name, parent, {"dr2_zone": zone.name, "dr2_level": zone.level})
    shared: dict = {"png_level": png_level}   # the zone's pieces share textures: decode once
    by_piece: dict[str, list[lvl.Placement]] = {}
    for p in zone.placements:
        name = piece_name(p, zone)
        if name is None:
            st.failed.append((p.piece, "placed, but the zone has no such piece"))
            continue
        by_piece.setdefault(name, []).append(p)
    for i, (name, places) in enumerate(by_piece.items()):
        if progress:
            progress(i, len(by_piece), name)
        vp = zone.pieces[name]
        try:
            sc = read_scene(tree, vp)
            es = gltf.ExportStats()
            finder = TextureFinder(tree, vp, game, db_path, lod=lod, shared=shared) \
                if textures else None
            data = model_glb(tree, sc, game=game, finder=finder, textures=textures,
                             db_path=db_path, stats=es, mode="shown", colour_variants=False)
        except Exception as e:  # noqa: BLE001 - named in stats.failed, the zone goes on
            st.failed.append((name, str(e)))
            continue
        asm.add(data, [placement_node(p, {"dr2_vpath": vp}) for p in places], group, vp)
        st.pieces += 1
        st.placements += len(places)
        st.triangles += es.triangles * len(places)
        st.textures += es.textures
        st.missing_textures.update(es.missing_textures or ())
    if not own:
        return None
    asm.extras = {"level": zone.level, "zone": zone.name, "source": zone.vpath,
                  "lod": lod}
    return asm.to_bytes()


def zone_of(position, zones: list[lvl.Zone]) -> lvl.Zone | None:
    """The smallest zone whose bounds hold ``position`` (Case Zero's z01 is the whole
    backdrop, 886 m across, so "smallest" matters), or None."""
    best = None
    for z in zones:
        if all(lo - 0.5 <= c <= hi + 0.5 for c, lo, hi in zip(position, z.bounds_min, z.bounds_max)):
            if best is None or z.radius < best.radius:
                best = z
    return best


def things_glb(tree: AssetTree, things, *, game: str, textures: bool = True,
               lod: bool = False, db_path=None, stats: ZoneStats | None = None,
               assembler=None, parent: int | None = None, progress=None,
               png_level: int = 6) -> bytes | None:
    """Placed items and doors (`dr2kit.convert.placed.Thing` with a ``model``) as one
    ``.glb``, each model exported once in its default look and placed at every spot.
    With ``assembler``, they go into it under ``parent`` (None returned)."""
    from . import gltf
    from .model import TextureFinder, model_glb, read_scene
    st = stats if stats is not None else ZoneStats()
    own = assembler is None
    asm = assembler or gltf.Assembler()
    by_model: dict[str, list] = {}
    shared: dict = {"png_level": png_level}
    for t in things:
        if t.model and t.position:
            by_model.setdefault(t.model, []).append(t)
    for i, (vp, places) in enumerate(by_model.items()):
        if progress:
            progress(i, len(by_model), vp)
        try:
            sc = read_scene(tree, vp)
            es = gltf.ExportStats()
            finder = TextureFinder(tree, vp, game, db_path, lod=lod, shared=shared) \
                if textures else None
            data = model_glb(tree, sc, game=game, finder=finder, textures=textures,
                             db_path=db_path, stats=es, mode="shown", colour_variants=False)
        except Exception as e:  # noqa: BLE001 - named in stats.failed
            st.failed.append((vp, str(e)))
            continue
        nodes = [{"name": t.name, "translation": t.position,
                  "rotation": unit(t.rotation or (0.0, 0.0, 0.0, 1.0)),
                  "extras": {"dr2_item": t.item, "dr2_name": t.name, "dr2_kind": t.kind,
                             "dr2_vpath": vp, "dr2_line": t.line, "dr2_file": t.file}}
                 for t in places]
        asm.add(data, nodes, parent, vp)
        st.pieces += 1
        st.placements += len(places)
        st.triangles += es.triangles * len(places)
        st.textures += es.textures
        st.missing_textures.update(es.missing_textures or ())
    if not own:
        return None
    return asm.to_bytes()


def zombies_glb(tree: AssetTree, spots, *, game: str, detail: str = "medium",
                textures: bool = True, lod: bool = False, db_path=None,
                stats: ZoneStats | None = None, assembler=None, parent: int | None = None,
                png_level: int = 6, looks: int = 3) -> bytes | None:
    """Zombies standing where the missions put crowds (`convert.zombies.spots`): each
    type's model (``detail``: high / medium / low) in a few looks (look 0 the default,
    the others random choices of `convert.variants`, seeded), each made once and placed
    at every spot, in the rest pose without bones (`gltf.Assembler.add` ``static``)."""
    import random as _random
    import zlib
    from . import gltf
    from . import variants as cvar
    from . import zombies as czomb
    from .model import TextureFinder, model_glb, read_scene
    st = stats if stats is not None else ZoneStats()
    own = assembler is None
    asm = assembler or gltf.Assembler()
    shared: dict = {"png_level": png_level}
    groups: dict[tuple, list] = {}
    for sp in spots:
        groups.setdefault((sp.type, sp.look % max(1, looks)), []).append(sp)
    for (ztype, look), places in sorted(groups.items()):
        vp = czomb.model_vpath(tree, ztype, detail)
        if vp is None:
            st.failed.append((ztype, "no model for this zombie type"))
            continue
        try:
            sc = read_scene(tree, vp)
            mv = cvar.read_variants(tree, sc, game)
            choice = mv.default() if look == 0 else mv.random(_random.Random(zlib.crc32(f"{ztype}/{look}".encode())))
            es = gltf.ExportStats()
            finder = TextureFinder(tree, vp, game, db_path, lod=lod, shared=shared) \
                if textures else None
            data = model_glb(tree, sc, game=game, finder=finder, textures=textures,
                             db_path=db_path, stats=es, variant=choice, mode="shown",
                             colour_variants=False, variants=mv)
        except Exception as e:  # noqa: BLE001 - named in stats.failed
            st.failed.append((vp, str(e)))
            continue
        nodes = [{"name": f"{ztype} ({sp.crowd.area if sp.crowd else ''})",
                  "translation": sp.position,
                  "rotation": (0.0, math.sin(sp.yaw / 2), 0.0, math.cos(sp.yaw / 2)),
                  "extras": {"dr2_zombie": ztype, "dr2_vpath": vp, "dr2_kind": "zombie",
                             "dr2_name": ztype, "dr2_area": sp.crowd.area if sp.crowd else "",
                             "dr2_mission": sp.crowd.mission if sp.crowd else "",
                             "dr2_line": sp.crowd.line if sp.crowd else 0,
                             "dr2_path": sp.crowd.path if sp.crowd else "",
                             "dr2_file": "missions.txt"}}
                 for sp in places]
        asm.add(data, nodes, parent, vp, static=True)
        st.pieces += 1
        st.placements += len(places)
        st.triangles += es.triangles * len(places)
    if not own:
        return None
    return asm.to_bytes()


COLLISION_COLOUR = (1.0, 0.45, 0.1)


@dataclass
class ZoneCollision:
    """A zone's collision in world space: shapes placed by the rule of
    `zone_collision`, and the ones whose placement isn't known (named, not drawn)."""
    vertices: list = field(default_factory=list)
    triangles: list = field(default_factory=list)
    shapes: dict = field(default_factory=dict)        # how many by rule
    unplaced: list = field(default_factory=list)      # shape names


def zone_collision(tree: AssetTree, zone: ZoneData) -> ZoneCollision:
    """The zone's ``MERGED_COLLISION.big`` (`formats.collision`) in world space.

    A shape belongs to a piece: the one with a node of the shape's name (``<name>``, or a
    part ``piece.<name>``), else of its name without a trailing ``_a`` / ``_b`` (CZ splits
    a shape that way), else the piece the collision file's node number ``words[1]``
    names (0: none). Its vertices are in that **piece's** space (node offsets included)
    or already in world space, and nothing in the file says which ❓: the one that lands
    inside the zone's placed pieces (their bounds, 1 m around) is taken, the piece's
    placement first. A shape with no piece is in world space, unless its box lies far
    from the zone (more than 1.5 radii from its centre): those few look local but their
    piece is unknown ❓, so they are left out and named (docs/formats.md §Levels,
    "Collision")."""
    import re
    from ..formats.collision import read_collision
    from ..formats.scene import Scene
    from .model import read_scene
    out = ZoneCollision()
    vp = join(zone.vpath, "MERGED_COLLISION.big")
    try:
        arc = tree.open_archive(vp)
    except VPathError:
        return out
    try:
        col_nodes = [n.name.lower() for n in Scene.from_archive(arc, vp).skeleton.nodes]
    except Dr2Error:                      # no scene around the shapes: no node numbers
        col_nodes = []
    by_node: dict = {}
    by_piece: dict = {}
    boxes = []
    for p in zone.placements:
        name = piece_name(p, zone)
        if name is None:
            continue
        by_piece.setdefault(name.lower(), p)
        try:
            ps = read_scene(tree, zone.pieces[name])
        except Exception:  # noqa: BLE001 - the census names a piece that fails
            continue
        for nd in ps.skeleton.nodes:
            for key in (nd.name.lower(), nd.name.lower().rsplit(".", 1)[-1]):
                by_node.setdefault(key, p)
        pts = [p.to_world(c) for c in piece_corners(ps)]
        if pts:
            boxes.append(([min(q[i] for q in pts) - 1 for i in range(3)],
                          [max(q[i] for q in pts) + 1 for i in range(3)]))

    def inside(verts) -> bool:
        n = sum(1 for v in verts
                if any(all(lo[i] <= v[i] <= hi[i] for i in range(3)) for lo, hi in boxes))
        return n * 2 > len(verts)
    for s in read_collision(arc, vp):
        if not s.vertices:
            continue
        key = s.name.lower()
        piece = by_node.get(key) or by_node.get(re.sub(r"_[a-z]$", "", key))
        if piece is None and 0 < s.words[1] < len(col_nodes):
            piece = by_piece.get(col_nodes[s.words[1]])
        if piece is not None:
            placed = [piece.to_world(v) for v in s.vertices]
            if inside(placed) or not inside(s.vertices):
                verts, rule = placed, "piece"
            else:
                verts, rule = list(s.vertices), "world"
        else:
            verts, rule = list(s.vertices), "world"
            lo = [min(v[i] for v in verts) for i in range(3)]
            hi = [max(v[i] for v in verts) for i in range(3)]
            near = [min(max(zone.zone.centre[i], lo[i]), hi[i]) for i in range(3)]
            if math.dist(near, zone.zone.centre) > zone.zone.radius * 1.5 + 5:
                out.unplaced.append(s.name)
                continue
        base = len(out.vertices)
        out.vertices += verts
        out.triangles += [(a + base, b + base, d + base) for a, b, d in s.triangles]
        out.shapes[rule] = out.shapes.get(rule, 0) + 1
    return out


def piece_corners(sc) -> list:
    """The 8 corners of every shape's stored bounds, in the piece's own space (a rigid
    shape's bounds are relative to its node, `Scene.rigid_node`)."""
    import itertools
    world = sc.skeleton.world_matrices() if sc.skeleton.nodes else []
    pts = []
    for m in sc.meshes:
        n = sc.rigid_node(m)
        for c in itertools.product(*zip(m.bounds_min, m.bounds_max)):
            if n is None:
                pts.append(c)
            else:
                w = world[n]
                pts.append(tuple(sum(w[i][j] * c[j] for j in range(3)) + w[i][3]
                                 for i in range(3)))
    return pts


def collision_glb(tree: AssetTree, zone: ZoneData, assembler=None,
                  parent: int | None = None) -> bytes | None:
    """The zone's collision as one see-through orange mesh (`zone_collision`); None
    when the zone has none."""
    from . import gltf
    col = zone_collision(tree, zone)
    if not col.triangles:
        return None
    own = assembler is None
    asm = assembler or gltf.Assembler()
    asm.mesh(f"{zone.name} collision", col.vertices, col.triangles, parent,
             COLLISION_COLOUR, 0.35, {"dr2_kind": "collision", "dr2_zone": zone.name,
                                      "dr2_unplaced": len(col.unplaced)})
    return asm.to_bytes() if own else None


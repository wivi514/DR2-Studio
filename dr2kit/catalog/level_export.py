"""Export a level: its zones as ``.glb`` for Blender, with items and markers (phase 10 step 4).

What a modder gets for ``dr2 export prologue -g cz -o out`` (or *Export zone… / Export
level…* in DR2 Studio's Maps tab)::

    out/cz/prologue/
        prologue_z01.glb … prologue_z11.glb   one file per zone (decision 2026-10-11:
                                              a whole level is ~1.5 M triangles, fine for
                                              Blender but too much for some programs)
        prologue.glb                          instead, with --whole: every zone in one file
        text/prologue.txt, waypoint_…, nm_…   the level's own files, as the game has them
        text/fe_map_*.csv, prologue.csv       the in-game map's points, the light by hour
        info.txt                              what is where, the counts, how to open it

Inside a zone's ``.glb``, nodes are grouped the way the Blender add-on turns into
collections (``extras.dr2_layer``): the zone, then **Buildings** (the pieces, placed as
the game places them: `convert.level.zone_glb`), **Items and doors** (each item's model at
its spot: `convert.level.things_glb`), and **Markers**, one group per kind: spawn
points and map points as empties (an Empty's arrow is the way the player faces), areas
and triggers as outlines, the navigation mesh as a see-through mesh. Every marker keeps
its settings from the level file in its custom properties.

With ``zombies``, a **Zombies** group holds the crowds the missions put in the zone's
zombie areas (`convert.zombies`, `level.zombies_glb`: high-detail models in their rest
pose, a few looks per type; example spots, the game spreads them itself).

Level materials carry their lightmap (the occlusion texture on the lightmap's UV set)
and two-texture blends in their extras (`convert.gltf.lightmap_slots`, `blend_slots`):
Blender's importer shows the colour map; the add-on's *Level materials* option wires the
lightmap in.

Resumable like the Library export: each file is written under a temporary name and
renamed when complete, and a file that already exists is skipped.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from ..container.vpath import AssetTree
from ..convert import gltf
from ..convert import level as clevel
from ..convert import mapdata, placed
from ..errors import Dr2Error

MARKER_COLOURS = {"spawn": (0.19, 0.88, 0.38), "zombie_area": (0.88, 0.25, 0.25),
                  "map_area": (0.25, 0.56, 1.0), "light_area": (1.0, 0.82, 0.25),
                  "trigger": (1.0, 0.25, 1.0), "sound_area": (0.25, 0.88, 0.88),
                  "map_point": (1.0, 0.63, 0.13), "acoustics": (0.63, 0.63, 0.63),
                  "waypoint": (1.0, 1.0, 1.0), "navmesh": (0.25, 1.0, 0.5)}
DEFAULT_MARKERS = ("spawn", "zombie_area", "map_area", "map_point", "trigger", "navmesh")


@dataclass
class LevelExport:
    """What was written (or would be, with ``dry_run``)."""
    folder: Path
    files: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    triangles: int = 0
    pieces: int = 0
    items: int = 0
    markers: int = 0
    zombies: int = 0


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _box(t: placed.Thing) -> list[list]:
    """A sound area's box (half sizes ❓) as two outlines and four uprights, world space."""
    from ..formats.level import quat_matrix
    sx, sy, sz = t.scale
    r = quat_matrix(t.rotation or (0.0, 0.0, 0.0, 1.0))

    def w(x, y, z):
        return tuple(t.position[i] + r[i][0] * x + r[i][1] * y + r[i][2] * z for i in range(3))
    bottom = [w(x, -sy, z) for x, z in ((-sx, -sz), (sx, -sz), (sx, sz), (-sx, sz))]
    top = [w(x, sy, z) for x, z in ((-sx, -sz), (sx, -sz), (sx, sz), (-sx, sz))]
    return [bottom, top] + [[b, u] for b, u in zip(bottom, top)]


def _trigger(t: placed.Thing) -> list[list]:
    """A trigger's quad (its Vertex1…4, scaled by its Radius ❓), placed."""
    from ..formats.level import quat_matrix
    try:
        radius = float(t.props.get("Radius", "1") or 1)
    except ValueError:
        radius = 1.0
    r = quat_matrix(t.rotation or (0.0, 0.0, 0.0, 1.0))
    pts = []
    for p in t.polygon:
        q = [c * radius for c in p]
        pts.append(tuple(t.position[i] + r[i][0] * q[0] + r[i][1] * q[1] + r[i][2] * q[2]
                         for i in range(3)))
    return [pts] if pts else []


def _prism(t: placed.Thing) -> list[list]:
    loops = [list(t.polygon)]
    if t.height:
        loops.append([(x, y + t.height, z) for x, y, z in t.polygon])
    return loops


def _where(t: placed.Thing):
    if t.position:
        return t.position
    if t.polygon:
        return tuple(sum(p[i] for p in t.polygon) / len(t.polygon) for i in range(3))
    return None


def add_markers(asm: gltf.Assembler, things: list[placed.Thing], parent: int,
                kinds=DEFAULT_MARKERS, navmesh: placed.NavMesh | None = None,
                nav_filter=None) -> int:
    """Markers into ``asm`` under ``parent``, one group per kind; returns how many."""
    groups: dict[str, int] = {}
    n = 0

    def group(kind: str) -> int:
        if kind not in groups:
            groups[kind] = asm.group(placed.LAYERS.get(kind, kind), parent,
                                     {"dr2_layer": kind})
        return groups[kind]
    for t in things:
        if t.kind not in kinds or t.kind in ("item", "door"):
            continue
        extras = {"dr2_kind": t.kind, "dr2_file": t.file, "dr2_line": t.line,
                  **{f"dr2_{k}": v for k, v in t.props.items() if not k.startswith("Vertex")}}
        if t.label:
            extras["dr2_label"] = t.label
        title = f"{t.name}" + (f" ({t.label})" if t.label and t.label != t.name else "")
        colour = MARKER_COLOURS.get(t.kind, (1.0, 1.0, 1.0))
        if t.kind == "trigger" and t.polygon and t.position:
            asm.lines(title, _trigger(t), group(t.kind), colour, extras)
        elif t.polygon:
            asm.lines(title, _prism(t), group(t.kind), colour, extras)
        elif t.kind == "sound_area" and t.scale and t.position:
            asm.lines(title, _box(t), group(t.kind), colour, extras)
        elif t.position:
            asm.empty(title, group(t.kind), t.position, t.rotation, extras)
        else:
            continue
        n += 1
    if navmesh is not None and "navmesh" in kinds and navmesh.polygons:
        tris = [tr for tr in navmesh.triangles()
                if nav_filter is None or nav_filter(navmesh.vertices[tr[0]])]
        if tris:
            used = sorted({i for tr in tris for i in tr})
            remap = {v: k for k, v in enumerate(used)}
            asm.mesh("Navigation mesh", [navmesh.vertices[i] for i in used],
                     [tuple(remap[i] for i in tr) for tr in tris], group("navmesh"),
                     MARKER_COLOURS["navmesh"], 0.35, {"dr2_kind": "navmesh"})
            n += 1
    return n


def export_level(tree: AssetTree, game: str, level: str, out: str | Path, *,
                 zones: list[str] | None = None, script: str | None = None,
                 items: bool = True, markers=DEFAULT_MARKERS, whole: bool = False,
                 lod: bool = False, text: bool = True, db_path=None, progress=None,
                 cancel=None, dry_run: bool = False, zombies: bool = False) -> LevelExport:
    """Write ``out/<game>/<level>/`` (module docstring). ``zones`` (names or ``z05``)
    limits it; ``script`` picks the item set (default: the level's own); ``markers`` the
    marker kinds (empty: none); ``whole``: one ``.glb`` for every zone chosen.
    ``progress(done, total, what)`` is called between files; ``cancel()`` True stops."""
    L = clevel.Level.open(tree, level)
    chosen = [L.find_zone(z) for z in zones] if zones else list(L.zones)
    scripts = mapdata.scripts_of(tree, L.name)
    if script is None:
        script = scripts[0] if scripts else None
    elif script not in scripts:
        raise Dr2Error(f"{L.name} has no item set {script!r} (it has {', '.join(scripts) or 'none'})")
    folder = Path(out) / game / L.name
    res = LevelExport(folder)
    ls = None
    if script and (items or markers or zombies):
        ls = placed.read_script(tree, script, placed.ItemModels(tree), mapdata._strings(tree))
    targets = [(f"{L.name}.glb", chosen)] if whole else \
        [(f"{z.zone}.glb", [z]) for z in chosen]
    total = len(targets) + (1 if text else 0)
    for k, (name, zs) in enumerate(targets):
        if cancel and cancel():
            break
        path = folder / name
        if progress:
            progress(k, total, name)
        if path.exists():
            res.skipped.append(path)
            continue
        if dry_run:
            res.files.append(path)
            continue
        data = level_glb(tree, game, L, zs, ls, items=items, markers=markers, lod=lod,
                         db_path=db_path, result=res, zombies=zombies)
        _write(path, data)
        res.files.append(path)
    if text and not (cancel and cancel()):
        if progress:
            progress(len(targets), total, "text files and info.txt")
        if not dry_run:
            _write_text(tree, L, scripts, ls, folder, res)
        _write_info(L, game, script, scripts, res, whole, lod, dry_run)
    return res


def level_glb(tree: AssetTree, game: str, L: clevel.Level, zones: list, ls, *,
              items: bool = True, markers=DEFAULT_MARKERS, lod: bool = False,
              db_path=None, result: LevelExport | None = None,
              zombies: bool = False) -> bytes:
    """One ``.glb`` of ``zones`` (`formats.level.Zone` records of ``L``): pieces, the
    items of the level script ``ls`` (a `placed.LevelScript`, or None) and its markers,
    grouped by zone and layer (module docstring). Counts go into ``result``."""
    res = result if result is not None else LevelExport(Path("."))
    asm = gltf.Assembler()
    for z in zones:
        zd = L.zone(z)
        top = asm.group(z.zone, None, {"dr2_zone": z.zone, "dr2_level": L.name,
                                       "dr2_layer": "zone"})
        st = clevel.ZoneStats()
        build = asm.group("Buildings", top, {"dr2_layer": "pieces"})
        clevel.zone_glb(tree, zd, game=game, lod=lod, db_path=db_path, stats=st,
                        assembler=asm, parent=build)
        res.pieces += st.pieces
        res.triangles += st.triangles
        res.failed += [(f"{z.zone}/{a}", b) for a, b in st.failed]
        if ls is None:
            continue
        mine = [t for t in ls.things
                if _where(t) is not None and mapdata._home(_where(t), L.zones) is z]
        its = [t for t in mine if t.kind in ("item", "door") and t.model]
        if items and its:
            st2 = clevel.ZoneStats()
            grp = asm.group("Items and doors", top, {"dr2_layer": "items"})
            clevel.things_glb(tree, its, game=game, lod=lod, db_path=db_path, stats=st2,
                              assembler=asm, parent=grp)
            res.items += st2.placements
            res.triangles += st2.triangles
            res.failed += [(f"{z.zone}/{a}", b) for a, b in st2.failed]
        if zombies:
            from ..convert import zombies as czomb
            spots = [s for s in czomb.spots(ls, czomb.crowds(tree, ls.name))
                     if mapdata._home(s.position, L.zones) is z]
            if spots:
                st3 = clevel.ZoneStats()
                grp = asm.group("Zombies", top, {"dr2_layer": "zombies"})
                clevel.zombies_glb(tree, spots, game=game, detail="high", lod=lod,
                                   db_path=db_path, stats=st3, assembler=asm, parent=grp)
                res.zombies += st3.placements
                res.triangles += st3.triangles
                res.failed += [(f"{z.zone}/{a}", b) for a, b in st3.failed]
        if markers:
            grp = asm.group("Markers", top, {"dr2_layer": "markers"})
            res.markers += add_markers(asm, mine, grp, markers, ls.navmesh,
                                       lambda p, z=z: mapdata._home(p, L.zones) is z)
    asm.extras = {"game": game, "level": L.name, "zones": [z.zone for z in zones],
                  "script": ls.name if ls is not None else None}
    return asm.to_bytes()


def _write_text(tree, L, scripts, ls, folder: Path, res: LevelExport) -> None:
    """The level's own text files (every item set's), the map files, its lighting."""
    try:
        arc = tree.open_archive(placed.DATAFILE)
    except Dr2Error:
        return
    want = set()
    for s in scripts:
        want |= {f"{s}.txt", f"waypoint_{s}.txt", f"nm_{s}.txt"}
    if ls is not None:
        for t in ls.things:
            ctx = t.props.get("ContextFileName") or ""
            if ctx:
                want.add(ctx.strip("/\\").lower())
    for e in arc.entries:
        low = e.name.lower()
        if low in want or low.startswith("fe_map"):
            path = folder / "text" / e.name
            if path.exists():
                res.skipped.append(path)
                continue
            _write(path, e.data())
            res.files.append(path)


def _write_info(L, game, script, scripts, res: LevelExport, whole, lod, dry_run) -> None:
    path = res.folder / "info.txt"
    lines = [f"{L.name} ({'Case Zero' if game == 'cz' else 'Case West'}): {L.vpath}",
             f"{len(L.zones)} zones: {', '.join(L.zone_names())}",
             f"items and markers from: {script or 'none'}"
             + (f" (other item sets: {', '.join(s for s in scripts if s != script)})"
                if len(scripts) > 1 else ""),
             "",
             f"files: {len(res.files) + 1} written (this one included), "
             f"{len(res.skipped)} already there",
             f"pieces placed: {res.pieces}; items and doors: {res.items}; markers: {res.markers}; "
             f"triangles: {res.triangles:,}",
             "textures: " + ("the game's small (_LOD) copies" if lod else "full size"),
             "",
             "Open in Blender: File > Import > glTF 2.0 (.glb/.gltf), one zone at a time"
             + (" (one file: every zone)" if whole else "") + ".",
             "Each zone is a parent object with Buildings, Items and doors and Markers under",
             "it; the DR2 add-on's Import level puts them in collections and wires in the",
             "lightmaps (docs/modding/18-maps.md). Positions are the game's, in metres,",
             "Y up (Blender turns them to Z up on import).",
             "Lightmaps (baked light) are each level material's occlusion texture; Blender",
             "shows the colour map only unless the add-on wires them in.",
             "Markers keep the level file's settings as custom properties (dr2_…).",
             "The text/ folder holds the level's own files: changing them is a mod",
             "(a whole-file text replacement, docs/modding/11-text.md)."]
    if res.failed:
        lines += ["", "not exported:"] + [f"  {a}: {b}" for a, b in res.failed]
    if not dry_run:
        _write(path, ("\n".join(lines) + "\n").encode())
        res.files.append(path)

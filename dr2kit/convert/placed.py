"""What a level's text files put in it: items, doors, spawn points, areas, triggers, the
navigation mesh (phase 10 step 2).

The pieces (buildings, floors) come from the zone archives (`dr2kit.convert.level`);
everything else a level holds is plain text in ``data/datafile.big``, read losslessly by
`dr2kit.formats.levelscript`:

=========================== ==================================================================
``<script>.txt``             items (``cItemPlacement``, nested ones too: a hot dog stand's
                             sodas), doors, items with props on them, spawn points, zombie
                             areas (``cZombieWarehouse`` → floor polygons), map areas
                             (``cPolygonSmall`` / ``Large`` with a string id), lighting areas
``waypoint_<script>.txt``    triggers (doors to other levels, interactions), sound areas
                             (boxes), acoustics, waypoints
``nm_<script>.txt``          the navigation mesh: vertices, then polygons of vertex numbers
``fe_map*.csv``              the in-game map's points: workbenches, save points, the
                             safehouse (rows ``name, x, y, z, LEVEL_<SCRIPT>``)
=========================== ==================================================================

A **script** is one set of these files (``prologue``, ``prologue_safehouse``…); several
scripts can share one level's geometry (Case Zero's safehouse script is the street with
the safehouse's items: `geometry_of`).

**Items find their model** (`ItemModels`) through ``items.txt``: the block named by
``ItemName`` gives ``MergedFilename`` and ``AssetFilename``; the model is a pack
``data/streamedassets.big/<X>.big`` where X is, first found, the ``MergedFilename``'s
name (CW ``gascanister``), the item's own name (CZ ``Chair_3``) or the
``AssetFilename``'s name; the pack is the scene itself (CZ ``HotDog.big``), or inside it
the scene is ``<AssetFilename's name>.big`` (or the
pack's only scene; empty ``.big`` entries beside it are placeholders of texture variants,
``adboard_cafe.big``). Measured: every placed item and door of both games resolves
(`dr2 census --levels`).

Classes the toolkit doesn't draw are still counted and named (`LevelScript.unknown`),
never dropped (CLAUDE.md rule 6). Facts and how they were found: docs/formats.md §Levels.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ..container.vpath import AssetTree, join
from ..errors import Dr2Error, VPathError
from ..formats.levelscript import Block, Document

DATAFILE = "data/datafile.big"
STREAMED = "data/streamedassets.big"

# What each class is, for the Maps tab's layers (kind) — and the classes that are known
# but not drawn (kept, counted, listed in the info panel).
KINDS = {
    "cItemPlacement": "item",
    "cItemWithAttachedPropsPlacement": "item",
    "cDoorPlacement": "door",
    "cSpawnPoint": "spawn",
    "cZombieWarehouse": "zombie_area",
    "cPolygonSmall": "map_area",
    "cPolygonLarge": "map_area",
    "cLightContextVolume": "light_area",
    "cTriggerVolume": "trigger",
    "cEnvironmentVolume": "sound_area",
    "cEnvironmentAcoustics": "acoustics",
    "cAudioMaterial": "acoustics",
    "cWaypoint": "waypoint",
}
LAYERS = {   # kind -> what the Maps tab calls the layer
    "item": "Items", "door": "Doors", "spawn": "Spawn points", "zombie_area": "Zombie areas",
    "map_area": "Map areas", "light_area": "Lighting areas", "trigger": "Triggers",
    "sound_area": "Sound areas", "acoustics": "Acoustics", "waypoint": "Waypoints",
    "navmesh": "Navigation mesh", "map_point": "Map points",
}
MAP_POINT_LABELS = {"workbench": "Workbench", "savepoint": "Save point",
                    "safehouse": "Safehouse"}


@dataclass
class Thing:
    """One placed thing or marker. Positions are world space (metres, Y up)."""
    kind: str                                   # KINDS value
    cls: str
    name: str
    file: str                                   # the text file's name
    line: int                                   # its header line (1-based)
    position: tuple[float, float, float] | None = None
    rotation: tuple[float, float, float, float] | None = None   # quaternion x, y, z, w
    scale: tuple[float, float, float] | None = None             # sound areas: box size
    polygon: list[tuple[float, float, float]] = field(default_factory=list)
    height: float | None = None                 # a polygon's prism height
    props: dict[str, str] = field(default_factory=dict)
    item: str | None = None                     # items and doors: ItemName
    model: str | None = None                    # its scene's vpath, once resolved
    label: str | None = None                    # map areas: their name in the game's text
    parent: str | None = None                   # nested: the enclosing block's name

    def to_dict(self) -> dict:
        """JSON-ready (the Maps page gets markers this way)."""
        out = {"kind": self.kind, "cls": self.cls, "name": self.name, "file": self.file,
               "line": self.line}
        for k in ("position", "rotation", "scale", "height", "item", "model", "label",
                  "parent"):
            v = getattr(self, k)
            if v is not None:
                out[k] = v
        if self.polygon:
            out["polygon"] = self.polygon
        out["props"] = self.props
        return out


@dataclass
class NavMesh:
    """``nm_<script>.txt``: vertices and the polygons (vertex numbers) zombies and
    survivors walk on. ``Connections`` is empty in every file of both games."""
    vertices: list[tuple[float, float, float]] = field(default_factory=list)
    polygons: list[list[int]] = field(default_factory=list)
    masks: list[int | None] = field(default_factory=list)       # a polygon's mask value

    def triangles(self) -> list[tuple[int, int, int]]:
        """Every polygon as a fan of triangles."""
        out = []
        for p in self.polygons:
            for i in range(1, len(p) - 1):
                out.append((p[0], p[i], p[i + 1]))
        return out


@dataclass
class LevelScript:
    """One script's placed things, read from its text files."""
    name: str
    files: list[str] = field(default_factory=list)            # vpaths read
    things: list[Thing] = field(default_factory=list)
    navmesh: NavMesh | None = None
    unknown: Counter = field(default_factory=Counter)          # classes not in KINDS
    documents: dict[str, Document] = field(default_factory=dict)

    def of_kind(self, kind: str) -> list[Thing]:
        return [t for t in self.things if t.kind == kind]

    def counts(self) -> Counter:
        c = Counter(t.kind for t in self.things)
        if self.navmesh:
            c["navmesh"] = len(self.navmesh.polygons)
        return c


def _floats(text: str | None):
    if text is None:
        return None
    try:
        return tuple(float(c) for c in text.split(","))
    except ValueError:
        return None


def _vec(text: str | None, n: int):
    v = _floats(text)
    return v if v is not None and len(v) == n else None


def script_names(tree: AssetTree) -> list[str]:
    """The level scripts of a game: ``<x>.txt`` files of ``datafile.big`` that have a
    ``waypoint_<x>.txt`` or ``nm_<x>.txt`` beside them."""
    try:
        arc = tree.open_archive(DATAFILE)
    except VPathError:
        return []
    names = {e.name.lower() for e in arc.entries}
    out = []
    for n in sorted(names):
        if not n.endswith(".txt") or n.startswith(("waypoint_", "nm_")):
            continue
        stem = n[:-4]
        if f"waypoint_{stem}.txt" in names or f"nm_{stem}.txt" in names:
            out.append(stem)
    return out


def geometry_of(script: str, levels: list[str]) -> str | None:
    """The level folder whose pieces a script's things sit in: the folder of the same
    name, else the longest folder name the script starts with (CZ ``prologue_safehouse``
    → ``prologue``)."""
    low = {lv.lower(): lv for lv in levels}
    if script.lower() in low:
        return low[script.lower()]
    best = [lv for k, lv in low.items() if script.lower().startswith(k + "_")]
    return max(best, key=len) if best else None


def scripts_for_level(level: str, scripts: list[str], levels: list[str]) -> list[str]:
    """The scripts drawn in ``level``: its own first, then those that borrow it."""
    own = [s for s in scripts if s.lower() == level.lower()]
    return own + [s for s in scripts if s.lower() != level.lower()
                  and (geometry_of(s, levels) or "").lower() == level.lower()]


def read_script(tree: AssetTree, name: str, models: "ItemModels | None" = None,
                strings: dict[int, str] | None = None) -> LevelScript:
    """Read a script's files (those it has). ``models`` resolves items to scenes;
    ``strings`` (id → text) names the map areas."""
    out = LevelScript(name)
    for fname in (f"{name}.txt", f"waypoint_{name}.txt"):
        try:
            node = tree.resolve(join(DATAFILE, fname))
        except VPathError:
            continue
        doc = Document.parse(node.data(), node.vpath)
        out.files.append(node.vpath)
        out.documents[fname.lower()] = doc
        for b in doc.blocks:
            _things(b, fname, out, None)
    try:
        node = tree.resolve(join(DATAFILE, f"nm_{name}.txt"))
    except VPathError:
        node = None
    if node is not None:
        doc = Document.parse(node.data(), node.vpath)
        out.files.append(node.vpath)
        out.documents[f"nm_{name}.txt"] = doc
        out.navmesh = read_navmesh(doc)
    if not out.files:
        raise Dr2Error(f"no level script {name!r} in {DATAFILE}")
    out.things += map_points(tree, name)
    # a polygon named by a lighting volume's QuadName is that volume's area, not a map
    # area (CZ L_exterior, CW L_QueenHarvest…)
    quads = {t.props.get("QuadName", "").lower() for t in out.things
             if t.cls == "cLightContextVolume"}
    for t in out.things:
        if t.kind == "map_area" and t.name.lower() in quads:
            t.kind = "light_area"
    if models is not None:
        for t in out.things:
            if t.item:
                t.model = models.resolve(t.item)
    if strings:
        for t in out.things:
            text = t.props.get("Text") or t.props.get("LevelRegionText")
            if text and text.isdigit():
                t.label = strings.get(int(text))
    return out


def _things(b: Block, fname: str, out: LevelScript, parent: str | None) -> None:
    kind = KINDS.get(b.cls)
    if kind is None:
        out.unknown[b.cls] += 1
        for c in b.children:
            _things(c, fname, out, b.name)
        return
    t = Thing(kind, b.cls, b.name, fname, b.line + 1, parent=parent,
              props={p.key: p.value for p in b.props})
    if kind in ("item", "door"):
        t.item = b.get("ItemName")
        t.position = _vec(b.get("Location"), 3)
        t.rotation = _vec(b.get("Rotation"), 4)
    elif kind == "spawn":
        t.position = _vec(b.get("Location0"), 3) or _vec(b.get("Location"), 3)
        heading = _floats(b.get("Rotation0") or b.get("Rotation"))
        if heading and len(heading) == 1:          # an angle about Y, in radians
            import math
            h = heading[0] / 2
            t.rotation = (0.0, math.sin(h), 0.0, math.cos(h))
    elif kind in ("map_area", "light_area") and b.cls.startswith("cPolygon"):
        t.polygon = [v for v in (_vec(x, 3) for x in b.numbered("Vertex")) if v]
        t.height = (_floats(b.get("Height")) or (None,))[0]
    elif kind == "trigger":
        t.position = _vec(b.get("Location"), 3)
        t.rotation = _vec(b.get("Rotation"), 4) or (0.0, 0.0, 0.0, 1.0)
        t.polygon = [v for v in (_vec(x, 3) for x in b.numbered("Vertex")) if v]
        t.height = (_floats(b.get("Height")) or (None,))[0]
    elif kind == "sound_area":
        t.position = _vec(b.get("Translation"), 3)
        t.rotation = _vec(b.get("Rotation"), 4)
        t.scale = _vec(b.get("Scale"), 3)
    elif kind in ("acoustics", "waypoint"):
        t.position = _vec(b.get("Location"), 3)
    out.things.append(t)
    if kind == "zombie_area":
        # a zombie area is a set of floor polygons: one thing per polygon, named
        # "<area>/<polygon>", so the Maps tab draws each and can say whose it is
        for c in b.children:
            if c.cls.startswith("cPolygon"):
                poly = Thing("zombie_area", c.cls, f"{b.name}/{c.name}", fname, c.line + 1,
                             parent=b.name, props={p.key: p.value for p in c.props})
                poly.polygon = [v for v in (_vec(x, 3) for x in c.numbered("Vertex")) if v]
                poly.height = (_floats(c.get("Height")) or (None,))[0]
                out.things.append(poly)
            else:
                _things(c, fname, out, b.name)
        return
    for c in b.children:
        _things(c, fname, out, b.name)


def map_points(tree: AssetTree, script: str) -> list[Thing]:
    """The in-game map's points that belong to ``script`` (``LEVEL_<SCRIPT>`` in the
    ``fe_map*.csv`` files): workbenches, save points, the safehouse."""
    try:
        arc = tree.open_archive(DATAFILE)
    except VPathError:
        return []
    want = f"level_{script}".lower()
    out = []
    for e in arc.entries:
        if not (e.name.lower().startswith("fe_map") and e.name.lower().endswith(".csv")):
            continue
        for no, line in enumerate(e.data().decode("latin-1").splitlines(), 1):
            cells = [c.strip() for c in line.split(",")]
            cells = [c for c in cells if c] if not line.lstrip().startswith("#") else []
            if len(cells) != 5 or cells[4].lower() != want:
                continue
            pos = _floats(",".join(cells[1:4]))
            if pos is None:
                continue
            base = cells[0].rstrip("_0123456789").lower()
            out.append(Thing("map_point", "map point", cells[0], e.name, no, position=pos,
                             label=MAP_POINT_LABELS.get(base, cells[0])))
    return out


def read_navmesh(doc: Document) -> NavMesh:
    """``Vertices { "x,y,z" … }``, ``Polyhedrons { PolyhedronEdges { mask = "3"
    "12" … } … }``, ``Connections { }``."""
    nm = NavMesh()
    for b in doc.blocks:
        if b.cls == "Vertices":
            for v, line in b.values:
                p = _vec(v, 3)
                if p is None:
                    raise Dr2Error(f"{doc.source}:{line + 1}: not a vertex: {v!r}")
                nm.vertices.append(p)
        elif b.cls == "Polyhedrons":
            for c in b.children:
                idx = [int(v) for v, _ in c.values]
                if any(i >= len(nm.vertices) for i in idx):
                    raise Dr2Error(f"{doc.source}:{c.line + 1}: a polygon names a vertex "
                                   f"past the {len(nm.vertices)} there are")
                nm.polygons.append(idx)
                m = c.get("mask")
                nm.masks.append(int(m) if m and m.isdigit() else None)
    return nm


class ItemModels:
    """Item name → the scene of its model (`resolve`), through ``items.txt`` and the
    packs of ``streamedassets.big`` (module docstring)."""

    def __init__(self, tree: AssetTree):
        self.tree = tree
        self.blocks: dict[str, Block] = {}
        try:
            doc = Document.parse(tree.resolve(join(DATAFILE, "items.txt")).data(), "items.txt")
            for b in doc.blocks:
                self.blocks.setdefault(b.name.lower(), b)
        except VPathError:
            pass
        try:
            arc = tree.open_archive(STREAMED)
            self.packs = {e.name.lower(): e.name for e in arc.entries}
        except VPathError:
            self.packs = {}
        self._cache: dict[str, str | None] = {}
        self.why: dict[str, str] = {}             # item -> why it has no model

    def resolve(self, item: str) -> str | None:
        """The vpath of the scene ``item`` shows, or None (`why` says why)."""
        key = item.lower()
        if key in self._cache:
            return self._cache[key]
        self._cache[key] = found = self._resolve(item)
        return found

    def _resolve(self, item: str) -> str | None:
        b = self.blocks.get(item.lower())
        if b is None:
            self.why[item.lower()] = "no block of that name in items.txt"
        merged = _base(b.get("MergedFilename")) if b is not None else None
        asset = _base(b.get("AssetFilename")) if b is not None else None
        for cand in (merged, item, asset):
            if not cand:
                continue
            outer = self.packs.get(cand.lower() + ".big")
            if outer is None:
                continue
            pack = self.tree.open_archive(join(STREAMED, outer))
            if any(e.name.lower() == "sceneheader" for e in pack.entries):
                return join(STREAMED, outer)            # the pack is the scene itself
            # empty .big entries are a texture variant's placeholder (adboard_cafe.big
            # beside adboard.big): the scene is the one with bytes
            scenes = [e.name for e in pack.entries
                      if e.name.lower().endswith(".big") and e.size2]
            for want in (asset, outer[:-4]):
                inner = [s for s in scenes if want and s.lower() == want.lower() + ".big"]
                if inner:
                    return join(STREAMED, outer, inner[0])
            if len(scenes) == 1:
                return join(STREAMED, outer, scenes[0])
            self.why[item.lower()] = (f"{STREAMED}/{outer} holds {len(scenes)} scenes, none "
                                      f"named after the item")
            return None
        self.why.setdefault(item.lower(), f"no pack named {merged or item}.big or "
                                          f"{asset or item}.big in {STREAMED}")
        return None


def _base(path: str | None) -> str | None:
    if not path:
        return None
    return path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or None

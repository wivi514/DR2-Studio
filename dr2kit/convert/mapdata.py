"""What DR2 Studio's Maps tab draws, ready to send: zone files on disk and the level's
markers as JSON (phase 10 step 3).

The Maps page (``studio/web/maps.js``, `dr2kit.studio.maps_view`) asks for zones one by
one, nearest the camera first, each as **pieces** (`level.zone_glb`) or **items**
(`level.things_glb`: the items and doors of one level script that stand in that zone),
in full size or with the small ``_LOD`` textures. Building one takes a few seconds, so
`MapCache` keeps every built file on disk (``<cache>/maps/<game>/<level>/``), named by
what it was built from: the toolkit's `MAP_VERSION`, the stamps (size, date) of the
files it read, and, when a view shows mods (phase 10 step 5), the tree's own stamp. A
changed game file or mod gives a new name, so a stale file is never shown.

`overview` is everything else the page needs in one JSON document: the zones (bounds,
centres), the level scripts that sit on this level, and for the chosen script every
marker (spawn points, zombie / map / lighting areas, triggers, sound areas, map points,
the navigation mesh) and where to start the camera (the ``Start`` spawn point when
there is one).

Pure Python, no Qt: tested without a window (tests/test_maps.py).
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from ..container.vpath import AssetTree, split
from . import level as clevel
from . import placed

MAP_VERSION = 5            # bump when what goes into a zone file changes (5: collision)
FULL, LOD = "full", "lod"
PNG_LEVEL = 1              # fast PNGs for the cache (exports keep level 6)
BACKDROP_RADIUS = 300.0    # zones larger than this are backdrops (CZ z01): always small textures


def _file_stamp(tree: AssetTree, vpath: str) -> str:
    """Size and date of the file on disk that holds ``vpath`` ("" if none)."""
    parts = split(vpath)
    here = tree.root
    for p in parts:
        nxt = next((c for c in here.iterdir() if c.name.lower() == p.lower()), None) \
            if here.is_dir() else None
        if nxt is None:
            break
        here = nxt
        if here.is_file():
            st = here.stat()
            return f"{here.name}:{st.st_size}:{st.st_mtime_ns}"
    return ""


def stamp(tree: AssetTree, vpaths: list[str]) -> str:
    """A short key for the state of ``vpaths``: their files' sizes and dates, plus the
    tree's own ``stamp(vpaths)`` when it has one (a view with mods, step 5)."""
    parts = [str(MAP_VERSION)] + [_file_stamp(tree, v) for v in vpaths]
    extra = getattr(tree, "stamp", None)
    if callable(extra):
        parts.append(extra(vpaths))
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def default_root() -> Path:
    from ..userdirs import cache_dir
    return cache_dir() / "maps"


class MapCache:
    """Built zone files on disk, built on first use (`pieces`, `items`)."""

    def __init__(self, tree: AssetTree, game: str, root: Path | None = None, db_path=None):
        self.tree, self.game, self.db_path = tree, game, db_path
        self.root = Path(root) if root else default_root()
        self._levels: dict[str, clevel.Level] = {}
        self._scripts: dict[str, placed.LevelScript] = {}
        self._models: placed.ItemModels | None = None

    def level(self, name: str) -> clevel.Level:
        if name not in self._levels:
            self._levels[name] = clevel.Level.open(self.tree, name)
        return self._levels[name]

    def script(self, name: str) -> placed.LevelScript:
        if name not in self._scripts:
            if self._models is None:
                self._models = placed.ItemModels(self.tree)
            self._scripts[name] = placed.read_script(self.tree, name, self._models,
                                                     _strings(self.tree))
        return self._scripts[name]

    def _path(self, level: str, name: str, key: str) -> Path:
        folder = self.root / self.game / level
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob(f"{name}-*.glb"):          # an older build of the same file
            if old.name != f"{name}-{key}.glb":
                try:
                    old.unlink()
                except OSError:
                    pass
        return folder / f"{name}-{key}.glb"

    def pieces(self, level: str, zone: str, detail: str = FULL) -> Path:
        """The zone's pieces, placed (built if not on disk)."""
        L = self.level(level)
        z = L.find_zone(zone)
        zvp = f"{L.vpath}/{z.zone}.big"
        path = self._path(level, f"{z.zone}-{detail}", stamp(self.tree, [zvp]))
        if not path.is_file():
            data = clevel.zone_glb(self.tree, L.zone(z), game=self.game, lod=detail == LOD,
                                   db_path=self.db_path, png_level=PNG_LEVEL)
            _write(path, data)
        return path

    def zone_things(self, level: str, zone: str, script: str) -> list[placed.Thing]:
        """The items and doors of ``script`` that stand in ``zone`` (each thing goes to
        the smallest zone holding it, or the nearest zone centre)."""
        L = self.level(level)
        z = L.find_zone(zone)
        out = []
        for t in self.script(script).things:
            if t.kind in ("item", "door") and t.model and t.position:
                if _home(t.position, L.zones) is z:
                    out.append(t)
        return out

    def items(self, level: str, zone: str, script: str, detail: str = FULL) -> Path | None:
        """The zone's items and doors of ``script`` (None when it has none)."""
        things = self.zone_things(level, zone, script)
        if not things:
            return None
        z = self.level(level).find_zone(zone)
        key = stamp(self.tree, [f"{placed.DATAFILE}/{script}.txt", placed.STREAMED]
                    + sorted({t.model for t in things}))
        path = self._path(level, f"{z.zone}-items-{script}-{detail}", key)
        if not path.is_file():
            data = clevel.things_glb(self.tree, things, game=self.game, lod=detail == LOD,
                                     db_path=self.db_path, png_level=PNG_LEVEL)
            _write(path, data)
        return path

    def zombie_spots(self, script: str):
        """Where the missions put zombie crowds on the level of ``script``."""
        key = f"zombies:{script}"
        if key not in self._scripts:
            from . import zombies as czomb
            self._scripts[key] = czomb.spots(self.script(script),
                                             czomb.crowds(self.tree, script))
        return self._scripts[key]

    def zombies(self, level: str, zone: str, script: str, detail: str = FULL) -> Path | None:
        """The zone's zombies (`level.zombies_glb`; None when it has none). Medium detail
        models, small textures far away."""
        L = self.level(level)
        z = L.find_zone(zone)
        spots = [s for s in self.zombie_spots(script) if _home(s.position, L.zones) is z]
        if not spots:
            return None
        key = stamp(self.tree, [f"{placed.DATAFILE}/missions.txt",
                                f"{placed.DATAFILE}/{script}.txt", "data/models/zombies.big"])
        path = self._path(level, f"{z.zone}-zombies-{script}-{detail}", key)
        if not path.is_file():
            data = clevel.zombies_glb(self.tree, spots, game=self.game, lod=detail == LOD,
                                      db_path=self.db_path, png_level=PNG_LEVEL)
            _write(path, data)
        return path

    def collision(self, level: str, zone: str) -> Path | None:
        """The zone's collision mesh (`level.collision_glb`; None when it has none)."""
        L = self.level(level)
        z = L.find_zone(zone)
        zvp = f"{L.vpath}/{z.zone}.big"
        path = self._path(level, f"{z.zone}-collision", stamp(self.tree, [zvp]))
        if not path.is_file():
            data = clevel.collision_glb(self.tree, L.zone(z))
            if data is None:
                return None
            _write(path, data)
        return path


def _write(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(path)                     # never a half-written file under the real name


def _home(position, zones):
    z = clevel.zone_of(position, zones)
    if z is not None:
        return z
    return min(zones, key=lambda z: math.dist(position, z.centre)) if zones else None


def _strings(tree: AssetTree) -> dict[int, str] | None:
    try:
        from .strings import load_bank
        return load_bank(tree, "en").strings
    except Exception:  # noqa: BLE001 - names are a nicety; the map works without them
        return None


def scripts_of(tree: AssetTree, level: str) -> list[str]:
    """The level scripts drawn on ``level`` (its own first)."""
    levels = [L.name for L in clevel.list_levels(tree)]
    return placed.scripts_for_level(level, placed.script_names(tree), levels)


MAP_PICTURES = "data/frontend/map.tex"
_NOT_MAPS = ("blur", "2f", "b1", "infobrochure", "pegboard", "tile", "icon", "hud", "colourize")


def map_rects(tree: AssetTree) -> dict[str, tuple[float, ...]]:
    """``LEVEL_<NAME>`` → (min x, max x, min z, max z, basement y, second floor y): the
    world rectangle the in-game map picture covers, and the heights below / above which
    the map shows the basement / the upper floor (``fe_map_points*.csv``)."""
    out = {}
    try:
        arc = tree.open_archive(placed.DATAFILE)
    except Exception:  # noqa: BLE001 - no map then
        return out
    for e in arc.entries:
        if not (e.name.lower().startswith("fe_map_points") and e.name.lower().endswith(".csv")):
            continue
        for line in e.data().decode("latin-1").splitlines():
            if line.lstrip().startswith("#"):
                continue
            cells = [c.strip() for c in line.split(",") if c.strip()]
            if len(cells) >= 7 and cells[0].upper().startswith("LEVEL_"):
                try:
                    out[cells[0].upper()] = tuple(float(c) for c in cells[3:9])
                except ValueError:
                    continue
    return out


def map_picture(tree: AssetTree, script: str | None, game: str | None = None) -> dict | None:
    """The in-game map for a level script: the game's main map picture
    (``frontend/map.tex``: CZ ``map_prologue``, CW ``map_all``) and the world rectangle it
    covers, ``{"vpath", "rect": [min x, max x, min z, max z]}``, or None. Checked on CZ:
    the picture spans the rectangle exactly, x to the right, z downwards (the bowling
    alley, the department store and the theatre land within 20 px of 1,480)."""
    rects = map_rects(tree)
    if not rects:
        return None
    rect = rects.get(f"LEVEL_{(script or '').upper()}") or next(iter(rects.values()))
    try:
        arc = tree.open_archive(MAP_PICTURES)
    except Exception:  # noqa: BLE001
        return None
    best = None
    for e in arc.entries:
        low = e.name.lower()
        if not low.startswith("map_") or any(k in low for k in _NOT_MAPS):
            continue
        if best is None or e.size2 > best.size2:
            best = e
    if best is None:
        return None
    out = {"vpath": f"{MAP_PICTURES}/{best.name}", "rect": list(rect[:4]), "floors": []}
    if game is None:
        return out
    from ..profiles import load_profile
    names = {e.name.lower().removesuffix(".bct"): e.name for e in arc.entries}
    for f in load_profile(game).map_floors:
        name = names.get(str(f.get("picture", "")).lower())
        if name is None:
            continue
        when = f.get("when", "above")
        k = 5 if when == "above" else 4
        out["floors"].append({"vpath": f"{MAP_PICTURES}/{name}", "x": f["x"], "y": f["y"],
                              "scale": f.get("scale", 1.0), "when": when,
                              "height": rect[k] if len(rect) > k else None})
    return out


LIGHT_KEYS = {          # what the Maps page uses of a lighting table, per hour
    "sky": ("mSkyColor1", "mSkyColor2", "mSkyColor3"), "sky_mid": "mSkyMidPoint",
    "fog": "mFogColour", "fog_start": "mFogStart", "fog_end": "mFogEnd", "fog_max": "mFogMax",
    "key": "mKeyLightColour", "key_dir": "mKeyLightDirection", "tint": "mTintColour",
}


def light_table(tree: AssetTree, name: str) -> list[dict] | None:
    """A lighting table (``datafile.big/<name>.csv``: rows of 24 hourly values) as 24
    dicts the Maps page reads: the sky's three colours and midpoint, fog colour and
    distances, the key light's colour and direction, the tint, and the ambient light
    from above and below (the spherical-harmonic matrices ``mSHRenderMatrix<C>.ij``:
    irradiance = nᵀ M n with n = (x, y, z, 1); up and down are n = (0, ±1, 0, 1))."""
    try:
        text = tree.resolve(f"{placed.DATAFILE}/{name.strip('/')}").data().decode("latin-1")
    except Exception:  # noqa: BLE001 - no table: the page keeps its own light
        return None
    rows = {}
    for line in text.splitlines():
        cells = line.split(",")
        if len(cells) >= 25:
            try:
                rows[cells[0].strip()] = [float(c) for c in cells[1:25]]
            except ValueError:
                continue

    def vec(key, h, n=3):
        return [rows.get(f"{key}.{c}", [0.0] * 24)[h] for c in "xyzw"[:n]]
    hours = []
    for h in range(24):
        d = {"sky": [vec(k, h) for k in LIGHT_KEYS["sky"]],
             "sky_mid": rows.get("mSkyMidPoint", [0.2] * 24)[h],
             "fog": vec("mFogColour", h), "fog_start": rows.get("mFogStart", [0] * 24)[h],
             "fog_end": rows.get("mFogEnd", [1000] * 24)[h],
             "fog_max": rows.get("mFogMax", [0] * 24)[h],
             "key": vec("mKeyLightColour", h), "key_dir": vec("mKeyLightDirection", h),
             "tint": vec("mTintColour", h)}
        amb = {}
        for side, s in (("up", 1), ("down", -1)):
            col = []
            for ch in ("Red", "Green", "Blue"):
                m = lambda i, j: rows.get(f"mSHRenderMatrix{ch}.{i}{j}", [0.0] * 24)[h]
                col.append(m(1, 1) + s * (m(1, 3) + m(3, 1)) + m(3, 3))
            amb[side] = col
        d["ambient"] = amb
        hours.append(d)
    return hours


def lighting(cache: MapCache, script: str | None) -> list[dict]:
    """The lighting contexts of a level script: each ``cLightContextVolume``'s table
    (`light_table`) and the area it covers (its ``QuadName`` polygon and height). The
    game lights a place with the context whose area holds it."""
    if not script:
        return []
    ls = cache.script(script)
    polys = {t.name.lower(): t for t in ls.things if t.polygon}
    tables: dict[str, list | None] = {}
    out = []
    for t in ls.things:
        if t.cls != "cLightContextVolume":
            continue
        f = (t.props.get("ContextFileName") or "").strip("/")
        if f and f not in tables:
            tables[f] = light_table(cache.tree, f)
        quad = polys.get((t.props.get("QuadName") or "").lower())
        if f and tables.get(f):
            out.append({"name": t.name, "file": f, "hours": tables[f],
                        "polygon": [[p[0], p[2]] for p in quad.polygon] if quad else [],
                        "y": [min(p[1] for p in quad.polygon),
                              min(p[1] for p in quad.polygon) + (quad.height or 1000)]
                        if quad else None})
    return out


def overview(cache: MapCache, level: str, script: str | None = None) -> dict:
    """The JSON document the Maps page opens a level with (module docstring)."""
    L = cache.level(level)
    scripts = scripts_of(cache.tree, L.name)
    if script is None and scripts:
        script = scripts[0]
    zones = [{"name": z.zone, "min": z.bounds_min, "max": z.bounds_max, "centre": z.centre,
              "radius": z.radius, "backdrop": z.radius > BACKDROP_RADIUS} for z in L.zones]
    out = {"game": cache.game, "level": L.name, "zones": zones, "scripts": scripts,
           "script": script, "markers": [], "navmesh": None, "start": None,
           "layers": placed.LAYERS}
    if script:
        ls = cache.script(script)
        out["markers"] = [t.to_dict() for t in ls.things if t.kind not in ("item", "door")]
        out["items"] = [{"name": t.name, "item": t.item, "kind": t.kind,
                         "position": t.position} for t in ls.things
                        if t.kind in ("item", "door") and t.position]
        if ls.navmesh and ls.navmesh.polygons:
            out["navmesh"] = {"vertices": [c for v in ls.navmesh.vertices for c in v],
                              "triangles": [i for t in ls.navmesh.triangles() for i in t]}
        spawns = ls.of_kind("spawn")
        start = next((s for s in spawns if s.name.lower() == "start"), None) or \
            (spawns[0] if spawns else None)
        if start is not None and start.position:
            out["start"] = {"position": start.position, "rotation": start.rotation,
                            "name": start.name}
    out["map"] = map_picture(cache.tree, script, cache.game)
    out["lighting"] = lighting(cache, script)
    if out["start"] is None:
        main = [z for z in L.zones if z.radius <= BACKDROP_RADIUS] or L.zones
        z = min(main, key=lambda z: z.radius) if len(main) == 1 else main[0]
        out["start"] = {"position": z.centre, "rotation": None, "name": z.zone}
    return out


def overview_json(cache: MapCache, level: str, script: str | None = None) -> bytes:
    return json.dumps(overview(cache, level, script), separators=(",", ":")).encode()

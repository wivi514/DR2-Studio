"""What level edits *mean*: checks a modder needs before the game sees them (phase 11).

`dr2kit.formats.leveledits` applies an ``.edits.json`` (it fails only on a block or key
that isn't there); this module looks at the blocks the edits add or change and says what
the game would do wrong with them, in plain words:

* **Items and doors** (``cItemPlacement`` …): the ``ItemName`` must name a block of
  ``items.txt`` (error), and its model should ship in this game (warning: an item can
  exist in ``items.txt`` with no model in Case Zero, a demo); ``Location`` three numbers,
  ``Rotation`` a unit quaternion (four numbers, length 1).
* **Zombies** (``missions.txt``): a ``ZombieType`` / ``Type<n>`` must be a zombie model
  of ``data/models/zombies.big`` (error); one the level doesn't load in
  ``zombiesets.txt`` gets a warning (likely skipped by the game, docs/phase11-kickoff.md;
  allowed, decision 2026-10-11); ``SpawnWithItem`` must be an item; a factory's
  ``ZombieWarehouseName`` must be an area (``cZombieWarehouse``) of the level's file;
  ``SpawnPoint`` three numbers, ``Rotation`` one angle (radians), amounts whole numbers.
* **Triggers** (``cTriggerVolume``): a save point (``ActionType 4``) or a door to
  another level (``3``) needs its ``ActionPoint`` (where Chuck stands) inside its box;
  a door's ``Level`` must be a level of the game.

`check` returns `Finding` s, only about the keys a mod sets and the blocks it adds; `dr2kit.mods.build.plan_mods` turns errors into problems
(nothing is built) and warnings into notes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..container.vpath import AssetTree, join
from ..errors import Dr2Error
from ..formats.leveledits import Edits
from ..formats.levelscript import Block, Document, split_path
from . import placed

ITEM_CLASSES = ("cItemPlacement", "cDoorPlacement", "cItemWithAttachedPropsPlacement")
ZOMBIES = "data/models/zombies.big"


@dataclass
class Finding:
    """One problem: ``error`` stops the build, a warning is told to the modder."""
    error: bool
    path: str
    text: str

    def __str__(self) -> str:
        return f"{self.path}: {self.text}"


class GameFacts:
    """What the checks look things up in, read once per game tree (cached by callers)."""

    def __init__(self, tree: AssetTree):
        self.tree = tree
        self.models = placed.ItemModels(tree)
        self.items = {k for k in self.models.blocks}
        try:
            arc = tree.open_archive(ZOMBIES)
            self.zombie_types = {e.name.lower()[:-4] for e in arc.entries
                                 if e.name.lower().endswith(".big")}
        except Dr2Error:
            self.zombie_types = set()
        self.load_sets = load_sets(tree)
        self._areas: dict[str, set[str] | None] = {}
        self.scripts = {s.lower() for s in placed.script_names(tree)}

    def areas(self, level: str) -> set[str] | None:
        """The zombie areas of ``LEVEL_<SCRIPT>`` (None: no such level script)."""
        script = level.lower().removeprefix("level_")
        if script not in self._areas:
            if script not in self.scripts:
                self._areas[script] = None
            else:
                try:
                    doc = Document.parse(self.tree.resolve(
                        join(placed.DATAFILE, f"{script}.txt")).data(), f"{script}.txt")
                    self._areas[script] = {b.name.lower() for b in doc.walk()
                                           if b.cls == "cZombieWarehouse"}
                except Dr2Error:
                    self._areas[script] = set()
        return self._areas[script]


def load_sets(tree: AssetTree) -> dict[str, list[dict]]:
    """``zombiesets.txt``: level (``LEVEL_PROLOGUE``, upper case) → its entries, each
    ``{"name", "start", "end", "types": [type…], "costs": {type: cost}, "total_cost"}``
    (times in seconds from Day 1 0:00; costs as the file's comments give them)."""
    try:
        node = tree.resolve(join(placed.DATAFILE, "zombiesets.txt"))
    except Dr2Error:
        return {}
    doc = Document.parse(node.data(), node.vpath)
    out: dict[str, list[dict]] = {}
    for b in doc.blocks:
        if b.cls != "cZombieLoadSet":
            continue
        entries = out.setdefault(b.name.upper(), [])
        for e in b.children:
            types = e.numbered("type")
            costs = {}
            for p in e.props:
                if p.key.lower().startswith("type"):
                    tail = doc.lines[p.line].split("//", 1)
                    if len(tail) == 2 and tail[1].strip().isdigit():
                        costs[p.value.lower()] = int(tail[1].strip())
            entries.append({"name": e.name, "start": _int(e.get("start")),
                            "end": _int(e.get("end")), "types": [t.lower() for t in types],
                            "costs": costs, "total_cost": _int(e.get("total_cost"))})
    return out


def _int(v: str | None) -> int | None:
    try:
        return int(v) if v is not None else None
    except ValueError:
        return None


def _floats(v: str | None) -> tuple[float, ...] | None:
    if v is None:
        return None
    try:
        return tuple(float(x) for x in v.split(","))
    except ValueError:
        return None


def changed(e: Edits) -> dict[str, set[str] | None]:
    """Block path → the keys the edits give it (lower case), or None for a block they add
    (every key is theirs, with every block inside it)."""
    out: dict[str, set[str] | None] = {}
    for p, keys in e.set.items():
        out.setdefault(p, set())
        if out[p] is not None:
            out[p] |= {k.lower() for k, v in keys.items() if v is not None}
    for p, spec in e.add.items():
        stack = [(p, spec)]
        while stack:
            base, s = stack.pop()
            out[base] = None
            stack += [(f"{base}/{k}", v) for k, v in s.items() if isinstance(v, dict)]
    return out


def check(facts: GameFacts, file_vpath: str, doc: Document, e: Edits) -> list[Finding]:
    """Check what ``e`` adds or sets in ``doc`` (already applied): a mod answers only for
    the keys it sets and the blocks it adds, not for the game's own values around them."""
    out: list[Finding] = []
    fname = file_vpath.rsplit("/", 1)[-1].lower()
    for path, keys in changed(e).items():
        b = doc.get(path)
        if b is None:
            continue
        level = _level_of(doc, path) if fname == "missions.txt" else None
        out += _check_block(facts, path, b, level, keys)
    return out


def _level_of(doc: Document, path: str) -> str | None:
    """The ``LevelName`` of the ``cMissionLevelReady`` a mission block is in."""
    parts = split_path(path)
    for i in range(len(parts), 0, -1):
        b = doc.get("/".join(parts[:i]))
        if b is not None and b.cls == "cMissionLevelReady":
            return (b.get("LevelName") or "").upper() or None
    return None


def _check_block(facts: GameFacts, path: str, b: Block, level: str | None,
                 keys: set[str] | None = None) -> list[Finding]:
    """The checks of one block; ``keys``: only findings about these keys count (None:
    all, a block the mod adds)."""
    out: list[Finding] = []

    def mine(key: str) -> bool:
        return keys is None or key.lower() in keys

    def err(text, key):
        if mine(key):
            out.append(Finding(True, path, text))

    def warn(text, key):
        if mine(key):
            out.append(Finding(False, path, text))

    def vec(key, n, required=False):
        v = b.get(key)
        if v is None:
            if required:
                err(f"needs {key} ({n} numbers)", key)
            return None
        f = _floats(v)
        if f is None or len(f) != n:
            err(f"{key} = {v!r}: needs {n} numbers separated by commas", key)
            return None
        return f

    def zombie(t, key):
        if t.lower() not in facts.zombie_types:
            err(f"{key} {t!r} is not a zombie type of this game (one of "
                f"{', '.join(sorted(facts.zombie_types)[:6])}…)", key)
        elif level and level in facts.load_sets and not any(
                t.lower() in en["types"] for en in facts.load_sets[level]):
            warn(f"{key} {t!r} is not in {level}'s load set (zombiesets.txt), so the "
                 f"game may not show it; add it to the load set", key)

    if b.cls in ITEM_CLASSES:
        item = b.get("ItemName")
        if not item:
            err("needs an ItemName (an item of items.txt)", "ItemName")
        elif item.lower() not in facts.items:
            err(f"ItemName {item!r} is not an item of this game's items.txt", "ItemName")
        elif facts.models.resolve(item) is None:
            warn(f"{item}'s model doesn't ship in this game "
                 f"({facts.models.why.get(item.lower(), 'not found')}): nothing will show", "ItemName")
        vec("Location", 3, required=True)
        q = vec("Rotation", 4)
        if q and abs(math.sqrt(sum(c * c for c in q)) - 1) > 0.01:
            err(f"Rotation {b.get('Rotation')} is not a turn (a quaternion of length 1)",
                "Rotation")
    elif b.cls == "cMissionSpawnZombie":
        t = b.get("ZombieType")
        if t:
            zombie(t, "ZombieType")
        vec("SpawnPoint", 3)
        vec("Rotation", 1)
        if b.get("NumberOfZombies") is not None and _int(b.get("NumberOfZombies")) is None:
            err(f"NumberOfZombies {b.get('NumberOfZombies')!r} is not a whole number",
                "NumberOfZombies")
        held = b.get("SpawnWithItem")
        if held and held.lower() not in facts.items:
            err(f"SpawnWithItem {held!r} is not an item of this game's items.txt",
                "SpawnWithItem")
    elif b.cls == "cMissionZombieFactory":
        for p in b.props:
            if p.key.lower().startswith("type") and p.key[4:].isdigit() and p.value:
                zombie(p.value, p.key)
            if p.key.lower().startswith("amount") and p.key[6:].isdigit() and \
                    _int(p.value) is None:
                err(f"{p.key} {p.value!r} is not a whole number", p.key)
        area = b.get("ZombieWarehouseName")
        areas = facts.areas(level) if level else None
        if area and areas is not None and area.lower() not in areas:
            err(f"ZombieWarehouseName {area!r} is not a zombie area of "
                f"{level.lower().removeprefix('level_')}.txt", "ZombieWarehouseName")
    elif b.cls == "cMissionSpawnZombieCrate":
        pass
    elif b.cls == "cTriggerVolume":
        kind = b.get("ActionType")
        loc = vec("Location", 3, required=kind in ("3", "4"))
        if kind in ("3", "4"):
            ap = vec("ActionPoint", 3, required=True)
            if loc and ap and not trigger_contains(b, ap):
                warn("ActionPoint (where Chuck stands to use it) is outside the trigger's "
                     "box: the prompt may never show", "ActionPoint")
        if kind == "3":
            lv = (b.get("Level") or "").lower().removeprefix("level_")
            if lv and lv not in facts.scripts:
                err(f"Level {b.get('Level')!r} is not a level of this game", "Level")
    elif b.cls == "cSpawnPoint":
        if b.get("Location0") is None:
            vec("Location", 3, required=True)
    return out


def trigger_contains(b: Block, point: tuple[float, ...]) -> bool:
    """Is ``point`` inside a ``cTriggerVolume``'s box (``Location``, ``Rotation`` and
    the corner ``Vertex1…4`` in its own space, ``Height`` up), or its ``Radius``?"""
    loc = _floats(b.get("Location"))
    if not loc:
        return False
    q = _floats(b.get("Rotation")) or (0.0, 0.0, 0.0, 1.0)
    d = [point[i] - loc[i] for i in range(3)]
    x, y, z, w = (-q[0], -q[1], -q[2], q[3])           # rotate by the inverse turn
    tx = 2 * (y * d[2] - z * d[1])
    ty = 2 * (z * d[0] - x * d[2])
    tz = 2 * (x * d[1] - y * d[0])
    local = (d[0] + w * tx + y * tz - z * ty, d[1] + w * ty + z * tx - x * tz,
             d[2] + w * tz + x * ty - y * tx)
    corners = [c for c in (_floats(v) for v in b.numbered("Vertex")) if c and len(c) == 3]
    h = (_floats(b.get("Height")) or (2.0,))[0]
    radius = (_floats(b.get("Radius")) or (0.0,))[0]
    if math.dist((0, 0, 0), local) <= radius:
        return True
    if len(corners) < 3 or not (-0.5 <= local[1] <= h + 0.5):
        return False
    xs = [c[0] for c in corners]
    zs = [c[2] for c in corners]
    return min(xs) <= local[0] <= max(xs) and min(zs) <= local[2] <= max(zs)

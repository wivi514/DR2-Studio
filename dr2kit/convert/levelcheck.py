"""What level edits *mean*: checks a modder needs before the game sees them (phase 11).

`dr2kit.formats.leveledits` applies an ``.edits.json`` (it fails only on a block or key
that isn't there); this module looks at the blocks the edits add or change and says what
the game would do wrong with them, in plain words:

* **Items and doors** (``cItemPlacement`` …): the ``ItemName`` must name a block of
  ``items.txt`` (error), and its model should ship in this game (warning: an item can
  exist in ``items.txt`` with no model in Case Zero, a demo); ``Location`` three numbers,
  ``Rotation`` four numbers, not all zero (length 1 expected, but the game itself ships
  CZ 12 / CW 18 placements whose quaternion isn't: a warning only).
* **Missions and saves** (in game, CZ, 2026-10-11): a block added *inside* one of the
  game's missions makes the game unable to load saves and stalls a new game, so it is an
  error (`SAVE_BREAK`); values and keys of the game's blocks change freely, and a
  mission of the mod's own loads fine (it runs in a new game only). Warning
  `SAVE_NEEDS`: a save made while such a mission runs crashes without it.
* **Zombies** (``missions.txt``): a ``ZombieType`` / ``Type<n>`` must be a zombie model
  of ``data/models/zombies.big`` (error); one the level doesn't load in
  ``zombiesets.txt`` gets a warning (allowed, decision 2026-10-11: CZ's street showed 8
  ``pro_zombie_cop``, a type it doesn't load, in game; the load set's memory budget is
  not measured); ``SpawnWithItem`` must be an item; a factory's
  ``ZombieWarehouseName`` must be an area (``cZombieWarehouse``) of the level's file;
  ``SpawnPoint`` three numbers, ``Rotation`` one angle (radians), amounts whole numbers.
* **Triggers** (``cTriggerVolume``): a save point (``ActionType 4``) needs its
  ``ActionPoint`` (where Chuck stands) just below the trigger's ``Location``, as all the
  game's own are (`action_point_fits`); a door's (``3``) ``Level`` must be a level of the
  game.

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
SAVE_BREAK = ("adds a block inside one of the game's own missions: the game then can't load "
              "saves and a new game stalls (measured in Case Zero, 2026-10-11). Change the "
              "game's blocks' values instead, or put new things in a mission of your own "
              "(they then appear in a new game only)")
SAVE_NEEDS = ("a mission of your own: it runs in a new game, and a save made while it runs "
              "crashes the game if it is loaded without this mod (measured in Case Zero, "
              "2026-10-11); tell players to keep the mod on for those saves")
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

    def __init__(self, tree: AssetTree, game: str | None = None):
        self.tree = tree
        self.game = game
        self.models = placed.ItemModels(tree)
        self.items = {k for k in self.models.blocks}
        try:
            arc = tree.open_archive(ZOMBIES)
            self.zombie_types = {e.name.lower()[:-4] for e in arc.entries
                                 if e.name.lower().endswith(".big")}
        except Dr2Error:
            self.zombie_types = set()
        self.load_sets = load_sets(tree)
        self.added_items: set[str] = set()       # items (lower) mods add, with their pack
        self._areas: dict[str, set[str] | None] = {}
        self.scripts = {s.lower() for s in placed.script_names(tree)}
        self.levels: dict[str, str] = {}       # level name (no LEVEL_) -> script (lower)
        for s in self.scripts:
            self.add_script(s)
        self.armed_types = _armed_types(tree)

    def add_script(self, script: str, doc: Document | None = None) -> None:
        """``<script>.txt`` is a level (the game's, or one a mod adds: ``doc``, its text,
        gives its spawn points and zombie areas): every slot of the program's level table
        that loads it now names a level (formats.md §Level slots: ``LEVEL_LIGHTINGTEST`` is
        ``lighting.txt``)."""
        script = script.lower()
        self.scripts.add(script)
        if doc is not None:
            self.spawn_points(script).update(b.name.lower() for b in doc.blocks
                                             if b.cls == "cSpawnPoint")
            self._areas[script] = {b.name.lower() for b in doc.walk()
                                   if b.cls == "cZombieWarehouse"}
        if self.game:
            from . import crossgame
            for s in crossgame.level_slot_list(self.game):
                if s.script.lower() == script:
                    self.levels[s.name] = script
        else:
            self.levels[script.upper()] = script

    def script_of(self, level: str) -> str | None:
        """The script of a level name (``LEVEL_PROLOGUE``, ``PROLOGUE``), None when no
        script of this game (or of a mod's added ones) is that level."""
        return self.levels.get(level.strip().upper().removeprefix("LEVEL_"))

    def spawn_points(self, script: str) -> set[str]:
        """The names of the ``cSpawnPoint`` blocks of ``<script>.txt`` (lower case)."""
        key = "spawns:" + script.lower()
        if key not in self.__dict__.setdefault("_spawns", {}):
            try:
                doc = Document.parse(self.tree.resolve(
                    join(placed.DATAFILE, f"{script}.txt")).data(), f"{script}.txt")
                self._spawns[key] = {b.name.lower() for b in doc.blocks
                                     if b.cls == "cSpawnPoint"}
            except Dr2Error:
                self._spawns[key] = set()
        return self._spawns[key]

    def areas(self, level: str) -> set[str] | None:
        """The zombie areas of a level (``LEVEL_PROLOGUE``; None: no such level)."""
        script = self.script_of(level) or level.lower().removeprefix("level_")
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


def _armed_types(tree: AssetTree) -> set[str]:
    """Zombie types whose behaviour shoots (``Range_Shoot``: Case Zero's soldiers, the
    mercenary slots Case West's guards take). Their AI needs a single spawn: a crowd
    spawning one faulted Case Zero (phase 15, 2026-10-13)."""
    try:
        doc = Document.parse(tree.resolve(join(placed.DATAFILE, "items.txt")).data(),
                             "items.txt")
    except Dr2Error:
        return set()
    shoots = {b.name.lower() for b in doc.blocks
              if b.cls == "cZombieBehaviourItem" and b.get("Range_Shoot") is not None}
    return {b.name.lower() for b in doc.blocks if b.cls == "cZombieClassItem" and
            any(v.lower() in shoots for v in b.numbered("BehaviourNames"))}


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


def check(facts: GameFacts, file_vpath: str, doc: Document, e: Edits,
          added_tops: set[str] | None = None) -> list[Finding]:
    """Check what ``e`` adds or sets in ``doc`` (already applied): a mod answers only for
    the keys it sets and the blocks it adds, not for the game's own values around them.
    ``added_tops``: top-level blocks (lower-case paths) that mods add to this file, so a
    block added inside one of them is not inside a mission of the game."""
    out: list[Finding] = []
    fname = file_vpath.rsplit("/", 1)[-1].lower()
    if fname == "missions.txt":
        tops = {p.lower() for p in (added_tops or set())} | \
            {p.lower() for p in e.add if len(split_path(p)) == 1}
        for p in e.add:
            parts = split_path(p)
            if len(parts) > 1 and parts[0].lower() not in tops:
                out.append(Finding(True, p, SAVE_BREAK))
            elif len(parts) == 1 and parts[0].lower().startswith("cmissiondefinition "):
                out.append(Finding(False, p, SAVE_NEEDS))
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
            warn(f"{key} {t!r} is not in {level}'s load set (zombiesets.txt): it showed in a "
                 f"Case Zero test, but it costs memory the level didn't plan for; keep the "
                 f"numbers small, or add it to the load set", key)

    if b.cls in ITEM_CLASSES:
        item = b.get("ItemName")
        if not item:
            err("needs an ItemName (an item of items.txt)", "ItemName")
        elif item.lower() not in facts.items and item.lower() not in facts.added_items:
            err(f"ItemName {item!r} is not an item of this game's items.txt", "ItemName")
        elif item.lower() not in facts.added_items and facts.models.resolve(item) is None:
            warn(f"{item}'s model doesn't ship in this game "
                 f"({facts.models.why.get(item.lower(), 'not found')}): nothing will show", "ItemName")
        vec("Location", 3, required=True)
        q = vec("Rotation", 4)
        n = math.sqrt(sum(c * c for c in q)) if q else 1.0
        if n < 1e-6:
            err(f"Rotation {b.get('Rotation')} is all zeros: not a turn", "Rotation")
        elif abs(n - 1) > 0.01:
            warn(f"Rotation {b.get('Rotation')} is a quaternion of length {n:.2f}, not 1 "
                 f"(the game ships 30 such, so it seems to cope; copy a rotation from "
                 f"another block to be safe)", "Rotation")
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
        if held and held.lower() not in facts.items and held.lower() not in facts.added_items:
            err(f"SpawnWithItem {held!r} is not an item of this game's items.txt",
                "SpawnWithItem")
    elif b.cls == "cMissionZombieFactory":
        for p in b.props:
            if p.key.lower().startswith("type") and p.key[4:].isdigit() and p.value:
                zombie(p.value, p.key)
                if p.value.lower() in facts.armed_types:
                    warn(f"{p.key} {p.value!r} is an armed enemy: a crowd spawning one "
                         f"crashed the game; spawn it one at a time (cMissionSpawnZombie, "
                         f"or retype a single zombie in the Maps tab)", p.key)
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
        if kind == "4" or (kind == "3" and b.get("ActionPoint")):
            ap = vec("ActionPoint", 3, required=kind == "4")
            if loc and ap and not action_point_fits(b, ap):
                warn("ActionPoint (where Chuck stands to use it) is not just below the "
                     "trigger's Location as in the game's own (0-1.5 m below, at most 1.5 m "
                     "across): the prompt may not show", "ActionPoint")
        if kind == "3":
            name = b.get("Level") or ""
            lv = facts.script_of(name) if name else None
            if name and lv is None:
                err(f"Level {name!r} is not a level of this game", "Level")
            arrive = b.get("LevelSpawnPoint")
            spawns = facts.spawn_points(lv) if lv else None
            if arrive and spawns is not None and arrive.lower() not in spawns:
                warn(f"LevelSpawnPoint {arrive!r} is not a spawn point of {lv}.txt (unless "
                     f"your mod adds it there)", "LevelSpawnPoint")
    elif b.cls == "cSpawnPoint":
        if b.get("Location0") is None:
            vec("Location", 3, required=True)
    return out


def action_point_fits(b: Block, point: tuple[float, ...]) -> bool:
    """Is ``point`` where the game's own save points and doors keep theirs: at most
    1.5 m across from the trigger's ``Location`` and 0-1.5 m below it? (Every shipped
    one: 0-1.3 m below, at most 1.2 m across, CZ 4 + CW 34, measured 2026-10-11. The
    corner ``Vertex<n>`` keys can't say more: some are in the trigger's own space, some
    in world space.)"""
    loc = _floats(b.get("Location"))
    if not loc or len(loc) != 3:
        return False
    across = math.hypot(point[0] - loc[0], point[2] - loc[2])
    return across <= 1.5 and -1.5 <= point[1] - loc[1] <= 0.2

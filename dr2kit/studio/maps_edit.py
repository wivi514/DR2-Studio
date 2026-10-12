"""The Maps tab's level editor (phase 11 step 2): move, turn, add, delete and change
placed items and doors, saved into the **mod being edited** as ``.edits.json``.

`LevelEditor` holds no Qt: one `dr2kit.mods.leveledit.TextEdits` per text file of the mod
(``prologue.txt``…), and every change goes through it, so the mod always holds exactly the
difference from the game's file (saved after each change). Undo and redo are a stack
across files (each file keeps its own text snapshots).

After a change the editor says what the page must show (`ItemState`): for every placed
item whose block changed, appeared or went away, its new place, its turn, what it is,
or that it is gone. The page (``web/maps.js``, ``dr2.itemState``) moves the item's node,
hides it, or, for an item that is new or became another item, loads its model from a
small ``.glb`` (`item_glb`). So nothing is rebuilt while editing; a level opened again
later is built from the game with the mods (``mods.preview``) as before.

Numbers are written like the game's tool writes them: three decimals
(``"-140.911,3.399,-89.938"``).

**Zombies** (step 3) live in ``missions.txt``, and the in-game tests of 2026-10-11 decide
how they are edited (docs/formats.md §Levels, "Level edits in game"): the game's own
zombies only by **value** (`zombie_set`, `zombie_move`, `crowd_amounts`; deleting one sets
its ``NumberOfZombies`` to 0), because a block added inside a game mission breaks saves;
new zombies go into the mod's **own mission** (`add_zombie`: a ``cMissionDefinition`` named
after the mod, with the keys of the level's main zombie mission and a
``cMissionLevelReady`` for the level), which runs in a new game. `zombies` gives the page
the crowds and spawns as the mod has them now.

**Buildings** (level pieces, step 4) are edited through `dr2kit.mods.pieceedit` (one
`PieceEdits` per zone, saved as the zone's ``.pieces.json``): `piece_move`, `piece_hide`,
`piece_copy`, `piece_restore`. They share the undo stack with the text files (its
entries are ``pieces:<zone vpath>``), and answer with `PieceState` lists the page applies
(``dr2.pieceState``).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..container.vpath import AssetTree
from ..convert import placed
from ..errors import Dr2Error
from ..formats.levelscript import Block, Document
from ..mods.leveledit import TextEdits
from ..mods.pieceedit import PieceEdits, PieceState

ITEM_CLASSES = ("cItemPlacement", "cDoorPlacement", "cItemWithAttachedPropsPlacement")


def fmt(values) -> str:
    """``(1, 2.5, -3)`` → ``"1.000,2.500,-3.000"`` (the game's three decimals; a value
    that rounds to zero is written ``0.000``, not ``-0.000``)."""
    return ",".join(f"{(float(v) if abs(float(v)) >= 0.0005 else 0.0):.3f}" for v in values)


def yaw_quaternion(degrees: float) -> tuple[float, float, float, float]:
    """A turn of ``degrees`` about the up axis (Y) as a quaternion ``x, y, z, w``."""
    h = math.radians(degrees) / 2
    return (0.0, math.sin(h), 0.0, math.cos(h))


def qmul(a, b):
    """The quaternion ``a × b`` (turn by ``b``, then by ``a``), ``x, y, z, w``."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def euler_of(q) -> tuple[float, float, float]:
    """A quaternion ``x, y, z, w`` as turns about X, Y and Z in degrees, applied Y first,
    then X, then Z (three.js's ``'YXZ'`` order: the heading first, as the panel shows)."""
    x, y, z, w = _unit(q)
    m13, m23, m33 = 2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)
    m21, m22 = 2 * (x * y + w * z), 1 - 2 * (x * x + z * z)
    m11, m31 = 1 - 2 * (y * y + z * z), 2 * (x * z - w * y)
    ax = math.asin(-max(-1.0, min(1.0, m23)))
    if abs(m23) < 0.9999999:
        ay, az = math.atan2(m13, m33), math.atan2(m21, m22)
    else:
        ay, az = math.atan2(-m31, m11), 0.0
    return tuple(math.degrees(a) for a in (ax, ay, az))


def quat_of_euler(x: float, y: float, z: float) -> tuple[float, float, float, float]:
    """`euler_of` reversed: degrees about X, Y, Z (``'YXZ'``) → quaternion ``x, y, z, w``."""
    c1, c2, c3 = (math.cos(math.radians(a) / 2) for a in (x, y, z))
    s1, s2, s3 = (math.sin(math.radians(a) / 2) for a in (x, y, z))
    return (s1 * c2 * c3 + c1 * s2 * s3, c1 * s2 * c3 - s1 * c2 * s3,
            c1 * c2 * s3 - s1 * s2 * c3, c1 * c2 * c3 + s1 * s2 * s3)


def yaw_of(q) -> float:
    """The turn about Y, in degrees, of a quaternion (its heading)."""
    x, y, z, w = q
    return math.degrees(math.atan2(2 * (w * y + x * z), 1 - 2 * (y * y + x * x)))


@dataclass
class ItemState:
    """What the page shows for one placed item after a change."""
    name: str
    file: str
    removed: bool = False
    item: str | None = None
    position: tuple[float, ...] | None = None
    rotation: tuple[float, ...] | None = None
    props: dict = field(default_factory=dict)
    model: str | None = None            # its scene, when the page must load a new one
    new_model: bool = False
    snap: bool = False                  # just placed: the page drops it onto the floor

    def to_dict(self) -> dict:
        d = {"name": self.name, "file": self.file, "removed": self.removed}
        if not self.removed:
            d.update(item=self.item, position=self.position, rotation=self.rotation,
                     props=self.props, model=self.model, new_model=self.new_model,
                     snap=self.snap)
        return d


def _snapshot(doc: Document) -> dict[str, tuple]:
    out = {}
    for b in doc.blocks:
        if b.cls in ITEM_CLASSES:
            out[b.name.lower()] = (b.cls, b.name, tuple((p.key, p.value) for p in b.props))
    return out


MISSIONS = "missions.txt"


class ZombieEdits:
    """The zombie half of `LevelEditor` (module docstring); mixed into it."""

    def zombies(self, script: str) -> dict:
        """``{"crowds": […], "zombie_spawns": […]}`` of the level of ``script``, as
        ``missions.txt`` is with the mod's changes (what the page draws)."""
        from ..convert import zombies as czomb
        try:
            doc = self.session(MISSIONS).doc
        except Dr2Error:                          # a game (or test data) without missions
            return {"crowds": [], "zombie_spawns": []}
        crowds, spawns = czomb.spawns_in(doc, script)
        return {"crowds": [czomb.crowd_dict(c) for c in crowds],
                "zombie_spawns": [z.to_dict() for z in spawns
                                  if z.position or z.kind == "crate"]}

    def is_own(self, path: str) -> bool:
        """Is ``path`` inside a mission the mod adds (not one of the game's)?"""
        from ..formats.levelscript import split_path
        top = split_path(path)[0].lower()
        original = self.session(MISSIONS).original
        return not any(f"{b.cls} {b.name}".lower() == top for b in original.blocks)

    def zombie_set(self, path: str, keys: dict) -> None:
        """Change keys of a zombie block (``None`` removes a key the mod added)."""
        def fn(doc):
            b = doc.find(path)
            for k, v in keys.items():
                if v is None:
                    doc.unset(b, k)
                else:
                    doc.set(b, k, str(v))
        self._change(MISSIONS, fn)

    def zombie_move(self, path: str, position, yaw: float | None = None) -> None:
        """Put a single zombie (``SpawnPoint``) or a clearing (``Location``) elsewhere;
        ``yaw``: its facing, radians, as the game's ``Rotation``."""
        def fn(doc):
            b = doc.find(path)
            key = "SpawnPoint" if b.cls == "cMissionSpawnZombie" else "Location"
            doc.set(b, key, fmt(position))
            if yaw is not None and b.cls == "cMissionSpawnZombie":
                doc.set(b, "Rotation", f"{yaw:.3f}")
        self._change(MISSIONS, fn)

    def crowd_amounts(self, path: str, amounts: list[tuple[str, int]]) -> None:
        """A crowd's types and amounts (``Type<n>`` / ``Amount<n>`` in order). Types it
        no longer has keep their keys with ``Amount<n> = 0``: removing keys from the
        game's blocks is avoided (only values are known to keep saves)."""
        def fn(doc):
            b = doc.find(path)
            old = [p.key for p in b.props if p.key.lower().startswith("amount")
                   and p.key[6:].isdigit()]
            for i, (t, n) in enumerate(amounts):
                doc.set(b, f"Type{i}", t)
                doc.set(b, f"Amount{i}", str(int(n)))
            for k in old:
                if int(k[6:]) >= len(amounts):
                    doc.set(b, k, "0")
        self._change(MISSIONS, fn)

    def own_mission(self, script: str) -> str:
        """The path of the mod's own ``cMissionLevelReady`` for ``script``'s level,
        made (cloned from the level's main zombie mission) when it isn't there yet."""
        mod_id = _mod_id(self.mod_dir)
        mission = f"cMissionDefinition {mod_id}_Zombies"
        ready = f"{mission}/cMissionLevelReady {mod_id}_{re.sub(r'\W', '_', script)}"
        doc = self.session(MISSIONS).doc
        if doc.get(ready) is not None:
            return ready
        template = _main_zombie_mission(self.session(MISSIONS).original, script)
        level = f"LEVEL_{script.upper()}"

        def fn(doc):
            m = doc.get(mission)
            if m is None:
                props = {p.key: p.value for p in template.props} if template else \
                    {"Duration": "518400", "MissionType": "12", "Module": "1",
                     "StartTime": "0"}
                m = doc.add(None, "cMissionDefinition", f"{mod_id}_Zombies", props)
            doc.add(m, "cMissionLevelReady", ready.rsplit(" ", 1)[1],
                    {"IgnoreWarning": "true", "LevelName": level})
        self._change(MISSIONS, fn)
        return ready

    def add_zombie(self, script: str, ztype: str, position, yaw: float = 0.0,
                   count: int = 1) -> str:
        """New zombies (``count`` of ``ztype``) in the mod's own mission; returns the
        new block's path. They appear in a new game (module docstring)."""
        ready = self.own_mission(script)
        doc = self.session(MISSIONS).doc
        taken = {b.name.lower() for b in doc.find(ready).children}
        n = 1
        while f"zombie{n}" in taken:
            n += 1
        name = f"Zombie{n}"
        props = {"NumberOfZombies": str(int(count)), "Rotation": f"{yaw:.3f}",
                 "SpawnPoint": fmt(position), "ZombieType": ztype}
        self._change(MISSIONS, lambda doc: doc.add(doc.find(ready), "cMissionSpawnZombie",
                                                   name, props))
        return f"{ready}/cMissionSpawnZombie {name}"

    def remove_zombie(self, path: str) -> None:
        """Take a single zombie out: the mod's own are removed, the game's get
        ``NumberOfZombies = 0`` (a value: saves keep working)."""
        if self.is_own(path):
            self._change(MISSIONS, lambda doc: doc.remove(doc.find(path)))
        else:
            self.zombie_set(path, {"NumberOfZombies": "0"})


MARKER_CLASSES = ("cTriggerVolume", "cSpawnPoint")


def added_markers(editor, script: str) -> list[dict]:
    """Triggers and spawn points the mod adds to the level of ``script`` (save points,
    doors… placed from prefabs), as the page's marker dicts (`placed.Thing.to_dict`)."""
    out = []
    for fname in (f"{script}.txt", f"waypoint_{script}.txt"):
        try:
            s = editor.session(fname)
        except Dr2Error:
            continue
        game = {(b.cls, b.name.lower()) for b in s.original.blocks}
        tmp = placed.LevelScript(script)
        for b in s.doc.blocks:
            if b.cls in MARKER_CLASSES and (b.cls, b.name.lower()) not in game:
                placed._things(b, fname, tmp, None)
        out += [dict(t.to_dict(), added=True) for t in tmp.things]
    return out


def _mod_id(mod_dir: Path) -> str:
    from ..mods.manifest import Mod
    try:
        mid = Mod.load(mod_dir).id
    except Dr2Error:
        mid = Path(mod_dir).name
    return re.sub(r"\W", "_", mid) or "Mod"


def _main_zombie_mission(doc: Document, script: str) -> Block | None:
    """The game's mission that puts the most crowds on ``script``'s level (CZ's street:
    ``PrologueZombies``): new zombie missions copy its keys (start time, duration…)."""
    want = f"level_{script}".lower()
    best, most = None, 0
    for m in doc.blocks:
        if m.cls != "cMissionDefinition":
            continue
        n = sum(1 for r in m.children if r.cls == "cMissionLevelReady"
                and (r.get("LevelName") or "").lower() == want
                for c in r.walk() if c.cls == "cMissionZombieFactory")
        if n > most:
            best, most = m, n
    return best


class LevelEditor(ZombieEdits):
    """Edits of placed things in one mod (module docstring)."""

    def __init__(self, tree: AssetTree, mod_dir: str | Path, base_dirs=(),
                 game: str | None = None):
        self.tree = tree
        self.mod_dir = Path(mod_dir)
        self.base_dirs = list(base_dirs)
        self.game = game
        self.sessions: dict[str, TextEdits] = {}
        self.zones: dict[str, PieceEdits] = {}   # zone vpath (lower) -> its building edits
        self._undo: list[str] = []              # file names, newest last
        self._redo: list[str] = []
        self.reload_models()

    def reload_models(self) -> None:
        """Items and their models as the game has them **with this mod** (its own items:
        ``items.txt`` additions and new packs, `mods.newitem`), read again after the mod
        gained an item."""
        self.mod_tree = self.tree
        if self.game:
            from ..mods.manifest import Mod
            from ..mods.preview import Preview
            try:
                pv = Preview(self.game, self.tree.root, [Mod.load(self.mod_dir)],
                             base_dirs=self.base_dirs)
                if pv.mods:
                    self.mod_tree = pv.tree()
            except Dr2Error:
                pass
        self.models = placed.ItemModels(self.mod_tree)

    # ---- files -------------------------------------------------------------------------

    def session(self, file: str) -> TextEdits:
        key = file.lower()
        if key not in self.sessions:
            self.sessions[key] = TextEdits(self.mod_dir, file, self.tree, self.base_dirs)
        return self.sessions[key]

    def forget(self, file: str) -> None:
        """Drop the open copy of ``file`` (the mod's file was written elsewhere, by
        `mods.newitem`): the next use reads it again. Its undo steps go with it."""
        self.sessions.pop(file.lower(), None)
        self._undo = [f for f in self._undo if f.lower() != file.lower()]
        self._redo = [f for f in self._redo if f.lower() != file.lower()]

    def placement(self, file: str, name: str) -> Block:
        """The item or door placed as ``name`` in ``file``."""
        doc = self.session(file).doc
        for b in doc.blocks:
            if b.cls in ITEM_CLASSES and b.name.lower() == name.lower():
                return b
        raise Dr2Error(f"{file}: nothing is placed as {name!r}")

    def count(self) -> int:
        """How many changes the mod holds in the files and zones opened here."""
        return (sum(s.edits().count() for s in self.sessions.values())
                + sum(z.count() for z in self.zones.values()))

    # ---- buildings (level pieces) -------------------------------------------------------

    def zone(self, zone_vpath: str) -> PieceEdits:
        """The building edits of one zone (``data/models/environment/<level>/<zone>.big``)."""
        key = zone_vpath.lower()
        if key not in self.zones:
            self.zones[key] = PieceEdits.open(self.mod_dir, self.tree, zone_vpath)
            self.zones[key].game = self.game
        return self.zones[key]

    def _piece_change(self, zone_vpath: str, fn) -> list[PieceState]:
        z = self.zone(zone_vpath)
        before = z.snapshot()
        z.checkpoint()
        try:
            out = fn(z)
            z.save()
        except Exception:
            z.undo()
            z._redo.clear()
            raise
        self._undo.append("pieces:" + zone_vpath.lower())
        self._redo.clear()
        self.last_result = out
        return self._piece_states(z, before)

    def _piece_states(self, z: PieceEdits, before: dict) -> list[PieceState]:
        """What the page must change: every piece whose state moved, pieces back as
        shipped, then the zone's copies, all of them (numbered anew), ended by a state
        with no name (the page drops the copies it had for the zone first)."""
        after = z.snapshot()
        out = []
        for key in sorted(set(before) | set(after)):
            if "#" in key or before.get(key) == after.get(key):
                continue
            if key in after:
                out.append(z.state(after[key]["name"]))
            else:                               # back as the game has it
                p = z.shipped(before[key]["piece"])
                out.append(PieceState(z.zone, p.piece, p.piece, tuple(p.position),
                                      tuple(p.rotation), tuple(p.scale)))
        out += [s for s in z.states() if s.copy]
        out.append(PieceState(z.zone, "", "", removed=True, copy=True))   # end of copies
        return out

    def piece_move(self, zone_vpath: str, name: str, position=None, rotation=None,
                   scale=None) -> list[PieceState]:
        return self._piece_change(zone_vpath, lambda z: z.place(name, position, rotation,
                                                                scale))

    def piece_hide(self, zone_vpath: str, name: str, hidden: bool = True) -> list[PieceState]:
        return self._piece_change(zone_vpath, lambda z: z.hide(name, hidden))

    def piece_restore(self, zone_vpath: str, name: str) -> list[PieceState]:
        return self._piece_change(zone_vpath, lambda z: z.restore(name))

    def piece_copy(self, zone_vpath: str, name: str, position=None, rotation=None,
                   scale=None) -> tuple[str, list[PieceState]]:
        """A copy of a building; returns its name (``<piece>#<n>``) and the states."""
        states = self._piece_change(zone_vpath, lambda z: z.copy(name, position, rotation,
                                                                 scale))
        return self.last_result, states

    def building_move(self, zone_vpath: str, name: str, position, rotation=None,
                      scale=None) -> tuple[list[PieceState], list[str]]:
        """Move a whole building (`PieceEdits.place_building`): the states, and warnings."""
        states = self._piece_change(zone_vpath, lambda z: z.place_building(
            name, position, rotation, scale))
        return states, self.last_result

    def building_hide(self, zone_vpath: str, name: str, hidden: bool = True) -> list[PieceState]:
        return self._piece_change(zone_vpath, lambda z: z.hide_building(name, hidden))

    def building_restore(self, zone_vpath: str, name: str) -> list[PieceState]:
        return self._piece_change(zone_vpath, lambda z: z.restore_building(name))

    def building_copy(self, zone_vpath: str, name: str, position) -> tuple[list[str], list[PieceState]]:
        states = self._piece_change(zone_vpath, lambda z: z.copy_building(name, position))
        return self.last_result, states

    def piece_state(self, zone_vpath: str, name: str) -> PieceState | None:
        try:
            return self.zone(zone_vpath).state(name)
        except Dr2Error:
            return None

    # ---- changes -------------------------------------------------------------------------

    def _change(self, file: str, fn) -> list[ItemState]:
        s = self.session(file)
        before = _snapshot(s.doc)
        s.checkpoint()
        try:
            fn(s.doc)
        except Exception:
            s.undo()                             # put the text back, drop the snapshot
            s._redo.clear()
            raise
        s.save()
        self._undo.append(file)
        self._redo.clear()
        return self._states(file, before, _snapshot(s.doc))

    def _states(self, file: str, before: dict, after: dict) -> list[ItemState]:
        out = []
        for key in sorted(set(before) | set(after)):
            a, b = before.get(key), after.get(key)
            if a == b:
                continue
            if b is None:
                out.append(ItemState(a[1], file, removed=True))
                continue
            blk = self.placement(file, b[1])
            props = dict(b[2])
            item = props.get("ItemName")
            st = ItemState(b[1], file, item=item, position=blk.floats("Location"),
                           rotation=blk.floats("Rotation") or (0.0, 0.0, 0.0, 1.0),
                           props=props)
            was_item = dict(a[2]).get("ItemName") if a else None
            if a is None or (was_item or "").lower() != (item or "").lower():
                st.model = self.models.resolve(item) if item else None
                st.new_model = True
            out.append(st)
        return out

    def move(self, file: str, name: str, position, rotation=None) -> list[ItemState]:
        """Put ``name`` at ``position`` (x, y, z), turned by ``rotation`` (a quaternion)."""
        def fn(doc):
            b = self.placement(file, name)
            doc.set(b, "Location", fmt(position))
            if rotation is not None:
                doc.set(b, "Rotation", fmt(_unit(rotation)))
        return self._change(file, fn)

    def set_item(self, file: str, name: str, item: str) -> list[ItemState]:
        """Make ``name`` another item (a bench → a chair)."""
        if item.lower() not in self.models.blocks:
            raise Dr2Error(f"{item!r} is not an item of this game's items.txt")
        return self._change(file, lambda doc: doc.set(self.placement(file, name),
                                                      "ItemName", self.models.blocks[
                                                          item.lower()].name))

    def set_key(self, file: str, name: str, key: str, value: str | None) -> list[ItemState]:
        """Change (``None``: remove) one key of a placement (``PropState``, ``IsStatic``…)."""
        def fn(doc):
            b = self.placement(file, name)
            if value is None:
                doc.unset(b, key)
            else:
                doc.set(b, key, value)
        return self._change(file, fn)

    def set_keys(self, file: str, path: str, keys: dict) -> list[ItemState]:
        """Change keys of any block of a level file (``None`` removes one): a door's
        ``Level``, an item's flags (*Settings…*)."""
        def fn(doc):
            b = doc.find(path)
            for k, v in keys.items():
                if v is None:
                    doc.unset(b, k)
                else:
                    doc.set(b, k, v)
        return self._change(file, fn)

    def remove_block(self, file: str, path: str) -> list[ItemState]:
        """Take a block the mod added out again (a save point placed from a prefab)."""
        s = self.session(file)
        top = path.split("/")[0].lower()
        if any(f"{b.cls} {b.name}".lower() == top for b in s.original.blocks):
            raise Dr2Error(f"{path} is the game's own: it can only be changed, not taken "
                           f"out here")
        return self._change(file, lambda doc: doc.remove(doc.find(path)))

    def delete(self, file: str, name: str) -> list[ItemState]:
        return self._change(file, lambda doc: doc.remove(self.placement(file, name)))

    def unique_name(self, file: str, base: str) -> str:
        """``base`` made unique among the file's top-level names (``Katana`` →
        ``Katana_1``), letters, digits and ``_`` only."""
        base = re.sub(r"\W", "_", base) or "Item"
        taken = {b.name.lower() for b in self.session(file).doc.blocks}
        if base.lower() not in taken:
            return base
        stem = re.sub(r"_\d+$", "", base)
        n = 1
        while f"{stem}_{n}".lower() in taken:
            n += 1
        return f"{stem}_{n}"

    def add(self, file: str, item: str, position, rotation=(0.0, 0.0, 0.0, 1.0),
            like: str | None = None) -> tuple[str, list[ItemState]]:
        """Place a new ``item`` (the keys of the placement ``like`` copied first when
        given: a duplicate). Returns its name and the states."""
        if item.lower() not in self.models.blocks:
            raise Dr2Error(f"{item!r} is not an item of this game's items.txt")
        real = self.models.blocks[item.lower()].name
        name = self.unique_name(file, f"{real}")
        cls = "cItemPlacement"
        props: dict[str, str] = {}
        if like:
            src = self.placement(file, like)
            cls = src.cls
            props = {p.key: p.value for p in src.props}
        props.update({"ItemName": real, "Location": fmt(position),
                      "Rotation": fmt(_unit(rotation))})
        states = self._change(file, lambda doc: doc.add(None, cls, name, props))
        return name, states

    def duplicate(self, file: str, name: str, offset=(1.0, 0.0, 0.0)) -> tuple[str, list[ItemState]]:
        """A copy of ``name`` beside it."""
        b = self.placement(file, name)
        pos = b.floats("Location") or (0.0, 0.0, 0.0)
        return self.add(file, b.get("ItemName") or "", tuple(p + o for p, o in zip(pos, offset)),
                        b.floats("Rotation") or (0.0, 0.0, 0.0, 1.0), like=name)

    # ---- undo ----------------------------------------------------------------------------

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> list[ItemState]:
        return self._step(self._undo, self._redo, "undo")

    def redo(self) -> list[ItemState]:
        return self._step(self._redo, self._undo, "redo")

    def _step(self, src: list, dst: list, how: str) -> list[ItemState]:
        if not src:
            return []
        file = src.pop()
        if file.startswith("pieces:"):
            z = self.zone(file[len("pieces:"):])
            before = z.snapshot()
            getattr(z, how)()
            z.save()
            dst.append(file)
            return self._piece_states(z, before)
        s = self.session(file)
        before = _snapshot(s.doc)
        getattr(s, how)()
        s.save()
        dst.append(file)
        return self._states(file, before, _snapshot(s.doc))

    def state(self, file: str, name: str) -> ItemState | None:
        """What ``name`` is now (None: not placed in this file)."""
        try:
            b = self.placement(file, name)
        except Dr2Error:
            return None
        props = {p.key: p.value for p in b.props}
        return ItemState(b.name, file, item=props.get("ItemName"),
                         position=b.floats("Location"),
                         rotation=b.floats("Rotation") or (0.0, 0.0, 0.0, 1.0), props=props)


def _unit(q) -> tuple[float, ...]:
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return tuple(c / n for c in q)


def item_glb(tree: AssetTree, game: str, state: ItemState, db_path=None) -> bytes | None:
    """One item's model placed where ``state`` says, as a small ``.glb`` for the page
    (the same node extras as the zones' items, so clicking it works the same)."""
    from ..convert.level import things_glb
    if not state.model or not state.position:
        return None
    t = placed.Thing("item", "cItemPlacement", state.name, state.file, 0,
                     position=tuple(state.position), rotation=tuple(state.rotation),
                     item=state.item, model=state.model)
    return things_glb(tree, [t], game=game, db_path=db_path, png_level=1)

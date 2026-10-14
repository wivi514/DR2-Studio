"""Bring a whole level of the other game: Case West's Storage Pens in Case Zero, or Case
Zero's street in Case West (phase 15 step 5, docs/phase15-kickoff.md §Maps).

Why: the user's phase 15 ("import a map from one to the other with all the items, zombie
placement and all the building environment, all properly done so they can talk to each
other and work normally… automatically assigned properly so it doesn't crash").

A level is (docs/formats.md §Levels, §Level slots):

* a **slot** of the program's level table (`crossgame.LevelSlot`): its level name
  (``LEVEL_X_PROLOGUE``), its script name and its zone list. A brought level goes into an
  **empty slot** of the target whose audio scene needs no file (`LevelSlot.loads`;
  measured 2026-10-13: Case Zero has 42 such slots, Case West one, ``w_mall``);
* its **zones**: ``data/models/environment/<folder>/<zone>.big``, archives of pieces,
  textures, lightmaps and collision, listed by the zone list (``folder/zone``). They are
  copied from the source game into a folder of the same name (a new folder in the
  target), drawn with their own game's shaders (`convert.shadercarry`; Storage Pens brings
  30 descriptions, 17 vertex and 272 pixel shaders) and fitted to the target's program
  (`crossgame.fit_scenes`). The slot's zone list is a copy of the source's;
* its **text files** (``<script>.txt``, ``waypoint_<script>.txt``, ``nm_<script>.txt``),
  copied under the slot's names with every name resolved in the target, the way
  `importitem` does for an item:

  - an item the target lacks is **brought** (`importitem.import_item`: its pack, shaders,
    moves, effects, text); one that can't be is **dropped** with its placements;
  - a block of a class the target's program doesn't name is dropped;
  - a door (``cDoorPlacement``, or a trigger with ``ActionType 3``) to a level the target
    doesn't have leads **back** to the target's level the entry door stands in (profile
    ``level_door``: ``return_spawn``), its key and locked messages taken off; a door to
    the level itself names the slot; another trigger naming a level the target lacks (a
    save point) names the slot;
  - text (a door's prompt, its messages) is copied under new string ids;
  - a light setting file (``cLightContextVolume ContextFileName``) the target lacks is
    brought;
* its **zombies**: they come from the source's zombie missions (``cMissionZombieFactory``
  crowds, single spawns, crates naming the level's zombie areas). The level's part of the
  source mission that spawns most is brought as **a mission of the mod's own**, set up as
  the target's own zombie mission is (phase 11: it runs in a **new game**, and saves made
  with it need the mod); every zombie type it or the level's load set uses is the target's
  own or brought (`importzombie`, decision 1), or left out when it can't be (Case Zero →
  Case West, docs/TODO.md #1); an armed enemy is left out of crowds (a crowd spawning one
  crashed Case Zero) and kept in single spawns;
* its **load set** (``zombiesets.txt``, ``cZombieLoadSet LEVEL_<SLOT>``, with the copy in
  ``persistent_filecache.big`` the game reads): the source's, types renamed;
* an **entry door** into it, in the target's level named by the profile (``level_door``),
  and every spawn point the target's own doors to that slot ask for.

Not brought (listed in the report): the source's story missions, the in-game map's points
and pictures, the level's ambient sound (a slot plays the audio scene it has: none for
``Default``).

The mod gets recipes and edits only, never game data (LICENSE): the zones are built from
the player's own copy of the source game (and cached, `newitem.build_copy`), so the mod
needs both games (`dr2kit.mods.requires`).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..container.vpath import AssetTree, split
from ..convert import crossgame, placed
from ..errors import Dr2Error
from ..formats import leveledits as le
from ..formats.levelscript import Block, Document, to_spec
from ..profiles import load_profile
from .importitem import ITEM_KEYS, Resolution, _IdPool
from .manifest import ADD_DIR
from .newitem import COPY_EXT, COPY_FORMAT

ENV = "data/models/environment"
DATAFILE = placed.DATAFILE
LEVEL_ITEM_KEYS = re.compile(r"^(AttachedProp\d+|SpawnWithItem)$")
LEVEL_STRING_KEYS = re.compile(r"^(CustomInteractionText|LockedMessage|UnlockedMessage|"
                               r"DisplayName|InteractionText)$")
DOOR_KEYS_OFF = ("KeyItem", "LockedMessage", "UnlockedMessage", "SiblingDoorName")
ZOMBIE_CLASSES = {"cMissionZombieFactory", "cMissionSpawnZombie", "cMissionSpawnZombieCrate",
                  "cMissionAdjustZombieTuning", "cMissionZombieRemoval"}
MISSION_PROPS = ("DescriptionSummary", "DisplayName", "DontAutoCompleteOnDebugJump",
                 "Duration", "MissionType", "Module", "REMOVE_BEFORE_SHIP",
                 "ShowInDebugMenu", "ShowInHUD", "StartTime", "WaitUntilEnd")
SETS = "zombiesets.txt"
CACHE = "data/datafile/persistent_filecache.big"


@dataclass
class LevelPlan:
    """Everything a level import does (module docstring); nothing written yet."""
    src: str
    dst: str
    level: crossgame.LevelSlot                     # the source level
    slot: crossgame.LevelSlot                      # where it goes
    folder: str = ""                               # the zones' folder (under ENV)
    zones: list[str] = field(default_factory=list)
    recipes: dict[str, dict] = field(default_factory=dict)        # path under add/ -> recipe
    items: list[str] = field(default_factory=list)                # items to bring
    zombies: dict[str, str] = field(default_factory=dict)         # source type -> target type
    zombie_plans: list = field(default_factory=list)
    strings: dict[int, int] = field(default_factory=dict)         # new id -> source id
    door_text: tuple[int, str] | None = None                      # the entry door's prompt
    mission: tuple | None = None                                  # (cls, name, props, children)
    load_set: tuple | None = None                                 # its block spec
    arrive: str = ""                                              # the spawn point doors reach
    door: dict = field(default_factory=dict)                      # file, block name, props
    spawns: list[tuple[str, str]] = field(default_factory=list)   # (name, copy of) to add
    log: list[Resolution] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    def report(self) -> str:
        names = {"cz": "Case Zero", "cw": "Case West"}
        lines = [f"{self.level.script}: from {names[self.src]} into {names[self.dst]}'s "
                 f"slot {self.slot.level} ({self.slot.script}.txt, "
                 f"{self.slot.zonelist})",
                 f"  zones: {len(self.zones)} in {ENV}/{self.folder}/",
                 f"  items brought: {len(self.items)}"
                 + (f" ({', '.join(self.items[:12])}{'…' if len(self.items) > 12 else ''})"
                    if self.items else ""),
                 "  zombie types: " + (", ".join(f"{a} as {b}" if a != b else a
                                                for a, b in sorted(self.zombies.items()))
                                       or "none")]
        if self.door:
            lines.append(f"  entry door: {self.door['file']} {self.door['name']} at "
                         f"{self.door['props']['Location']} -> {self.slot.level} / "
                         f"{self.arrive}")
        for how in ("brought", "renumbered", "dropped"):
            hits = [r for r in self.log if r.how == how]
            if hits:
                lines.append(f"  {how} ({len(hits)}):")
                lines += [f"    {r.where}: {r.what}" for r in hits[:60]]
                if len(hits) > 60:
                    lines.append(f"    … and {len(hits) - 60} more")
        lines += [f"  WARNING: {w}" for w in self.warnings]
        if self.unresolved:
            lines.append("  UNRESOLVED:")
            lines += [f"    {u}" for u in self.unresolved]
        return "\n".join(lines)


# --- what the mod already uses -----------------------------------------------------------

def mod_levels(mod_dir: str | Path) -> dict[str, dict]:
    """Levels the mod brought already (``sources/levels.json``): slot level name → entry."""
    f = Path(mod_dir) / "sources" / "levels.json"
    return json.loads(f.read_text("utf-8")) if f.is_file() else {}


# --- the plan --------------------------------------------------------------------------

def plan(src_tree: AssetTree, dst_tree: AssetTree, src: str, dst: str, level: str,
         slot: str | None = None, door: str | None = None, mod_id: str = "import",
         taken_slots=(), taken_ids: set[int] | None = None,
         taken_zombies: dict[str, str] | None = None, sets_text: str | None = None
         ) -> LevelPlan:
    """What bringing the level ``level`` (a level or script name of ``src``) into ``dst``
    does (module docstring). ``slot``: the target's slot (default: the first free one,
    `crossgame.free_level_slots`, not in ``taken_slots``); ``door``: the entry door's
    place ``x,y,z`` (default: the profile's ``level_door``). Raises `Dr2Error` when it
    can't be done at all."""
    from . import importzombie
    from ..convert.level import Level
    lv = crossgame.level_slot(src, level)
    if not lv.shipped:
        raise Dr2Error(f"{lv.level} is an empty slot of {src.upper()}: no level to bring")
    if slot:
        sl = crossgame.level_slot(dst, slot)
        if not sl.loads:
            raise Dr2Error(sl.why_not)
        if any(crossgame.level_slot(dst, t).level == sl.level for t in taken_slots):
            raise Dr2Error(f"the mod already puts a level in {sl.level}")
    else:
        free = crossgame.free_level_slots(dst, taken_slots)
        if not free:
            raise Dr2Error(f"{dst.upper()} has no free level slot left (Case West has one, "
                           f"w_mall; growing its level table is docs/TODO.md #1's kind of "
                           f"recomp change)")
        sl = free[0]
    p = LevelPlan(src, dst, lv, sl)
    prof = load_profile(dst)
    global _ITEMS_SRC, _ITEMS_DST
    _ITEMS_SRC = placed.ItemModels(src_tree).blocks
    _ITEMS_DST = placed.ItemModels(dst_tree).blocks
    _TREES[:] = [src_tree, dst_tree]
    _REFUSED.clear()

    # 1. the zones and the zone list
    L = Level.open(src_tree, lv.zonelist.rsplit("/", 1)[0])
    folders = {_folder(z).lower() for z in L.zones}
    if len(folders) != 1:
        raise Dr2Error(f"{lv.zonelist} names zones of several folders ({sorted(folders)}): "
                       f"not supported yet")
    p.folder = _folder(L.zones[0])
    if (dst_tree.root / ENV / p.folder).exists() or _has_dir(dst_tree, f"{ENV}/{p.folder}"):
        raise Dr2Error(f"{dst.upper()} already has a level folder {p.folder!r}: bringing a "
                       f"level whose zones share a folder name with the target's is not "
                       f"supported yet")
    _zones(src_tree, dst_tree, p, L)

    # 2. the zombies: types, the mission, the load set
    sets = sets_text if sets_text is not None else dst_tree.resolve(
        f"{DATAFILE}/{SETS}").data().decode("latin-1")
    taken_z = dict(taken_zombies or {})
    src_set = _load_set(src_tree, lv.level)
    mission = _zombie_mission(src_tree, lv)
    wanted = _types_in(src_set, mission)
    shipped_dst = importzombie.shipped_types(dst_tree)
    armed: set[str] = set()
    for ty in sorted(wanted):
        t = ty.lower()
        if t in shipped_dst:
            p.zombies[ty] = ty
            continue
        prev = next((s for s, x in taken_z.items() if x.lower() == t), None)
        if prev:
            p.zombies[ty] = prev
            continue
        try:
            zp = importzombie.plan(src_tree, dst_tree, src, dst, ty, taken=taken_z,
                                   sets_text=sets)
        except Dr2Error as e:
            p.log.append(Resolution(f"zombie type {ty}", "dropped", str(e)))
            continue
        taken_z[zp.slot] = ty
        p.zombies[ty] = zp.slot
        p.zombie_plans.append(zp)
        if zp.armed:
            armed.add(zp.slot.lower())
        p.log.append(Resolution(f"zombie type {ty}", "brought", f"as {zp.slot}"))
    armed |= {t.lower() for t in _armed_slots(dst)}
    if src_set is not None:
        p.load_set = _new_load_set(src_set, sl, p, importzombie.costs(src_tree))
    ids = _IdPool(mod_id, set(_strings(dst_tree)), set(taken_ids or ()))
    if mission is not None:
        p.mission = _mission(dst_tree, sl, mission, p, armed)

    # 3. the text files
    items_dst = placed.ItemModels(dst_tree).blocks
    items_src = placed.ItemModels(src_tree).blocks
    p.arrive = _arrive(src_tree, lv)
    door_prof = prof.level_door
    ret_level = crossgame.level_slot(dst, door_prof["level"]) if door_prof else None
    _asked_spawns(dst_tree, p)            # spawn points the target's own doors ask for
    for kind in ("", "waypoint_", "nm_"):
        _script(src_tree, dst_tree, p, kind, items_src, items_dst, ids, ret_level,
                door_prof.get("return_spawn", "") if door_prof else "")

    # 4. the entry door
    if ret_level is not None:
        _entry_door(dst_tree, p, ret_level, door or door_prof["location"], ids)

    p.warnings.append(
        f"its zombies come from a mission of the mod's own ({p.mission[1] if p.mission else 'none'}): "
        f"they show in a NEW game, and a save made with this mod needs it "
        f"(docs/modding/19-edit-a-level.md)" if p.mission else
        f"{lv.level} has no zombie mission in {src.upper()}: the level has no zombies")
    p.warnings.append("the in-game map shows nothing for this level, and it plays without "
                      "its own ambient sound (its slot's audio scene is "
                      f"{sl.audio})")
    return p


def _folder(z) -> str:
    """A zone record's folder (Case West writes ``storage_pens\\storage_pens_z00``)."""
    return z.name.replace("\\", "/").split("/")[0]


def _has_dir(tree: AssetTree, vp: str) -> bool:
    try:
        tree.resolve(vp)
        return True
    except Dr2Error:
        return False


_STRINGS: dict[str, dict[int, str]] = {}


def _strings(tree: AssetTree) -> dict[int, str]:
    key = str(tree.root)
    if key not in _STRINGS:
        from ..convert.strings import load_bank
        _STRINGS[key] = load_bank(tree, "en").strings
    return _STRINGS[key]


def _zones(src_tree: AssetTree, dst_tree: AssetTree, p: LevelPlan, L) -> None:
    """Recipes for every zone archive (with the source's shaders) and the zone list."""
    from ..convert import shadercarry
    sd, ps = set(), set()
    datas = {}
    for z in L.zones:
        vp = f"{ENV}/{_folder(z)}/{z.zone}.big"
        try:
            data = src_tree.resolve(vp).data()
        except Dr2Error:
            p.unresolved.append(f"zone {z.name}: {vp} is not in {p.src.upper()}")
            continue
        datas[vp] = data
        a, b = shadercarry.used_shaders(data)
        sd |= a
        ps |= b
    c = shadercarry.plan(src_tree, dst_tree, p.src, p.dst, sd, ps)
    for k, r in shadercarry.recipes(c, dst_tree).items():
        p.recipes.setdefault(k, r)
    maps = c.to_json()
    for vp in datas:
        recipe = {"format": COPY_FORMAT, "from": p.src, "copy": vp}
        if maps:
            recipe["shaders"] = maps
        p.recipes[f"{vp}{COPY_EXT}"] = recipe
        p.zones.append(vp.rsplit("/", 1)[-1][:-4])
    p.recipes[f"{ENV}/{p.slot.zonelist}{COPY_EXT}"] = {
        "format": COPY_FORMAT, "from": p.src, "copy": f"{ENV}/{p.level.zonelist}"}
    p.log.append(Resolution("zones", "brought",
                            f"{len(datas)} zones with their {p.src.upper()} shaders "
                            f"({len(c.sd)} descriptions, {len(c.vs)} vertex and "
                            f"{len(c.ps)} pixel shaders), {sum(map(len, datas.values())) / 1e6:.0f} MB"))


# --- zombies ---------------------------------------------------------------------------

def _load_set(tree: AssetTree, level: str) -> Block | None:
    doc = Document.parse(tree.resolve(f"{DATAFILE}/{SETS}").data(), SETS)
    return doc.get(f"cZombieLoadSet {level}")


def _zombie_mission(tree: AssetTree, lv: crossgame.LevelSlot) -> Block | None:
    """The ``cMissionLevelReady`` of the level in the source's mission that spawns most
    crowds there (Case West's Storage Pens: ``Case1Zombies``)."""
    doc = Document.parse(tree.resolve(f"{DATAFILE}/missions.txt").data(), "missions.txt")
    best, n = None, 0
    for m in doc.blocks:
        for r in m.children:
            if r.cls != "cMissionLevelReady" or \
                    (r.get("LevelName") or "").upper() != lv.level.upper():
                continue
            k = sum(1 for x in r.walk() if x.cls == "cMissionZombieFactory")
            if k > n:
                best, n = r, k
    return best


def zombie_mission_of(tree: AssetTree, level: str) -> Block | None:
    """The target's own mission that spawns most crowds in ``level`` (Case Zero's street:
    ``PrologueZombies``): a brought mission is set up as it is."""
    doc = Document.parse(tree.resolve(f"{DATAFILE}/missions.txt").data(), "missions.txt")
    best, n = None, -1
    for m in doc.blocks:
        k = sum(1 for r in m.children if r.cls == "cMissionLevelReady"
                and (r.get("LevelName") or "").upper() == level.upper()
                for x in r.walk() if x.cls == "cMissionZombieFactory")
        if k > n:
            best, n = m, k
    return best


def _types_in(load_set: Block | None, mission: Block | None) -> set[str]:
    out: set[str] = set()
    if load_set is not None:
        for e in load_set.children:
            out |= set(e.numbered("type"))
    if mission is not None:
        for x in mission.walk():
            if x.cls == "cMissionZombieFactory":
                out |= {pr.value for pr in x.props if re.fullmatch(r"Type\d+", pr.key)
                        and pr.value}
            elif x.cls == "cMissionSpawnZombie" and x.get("ZombieType"):
                out.add(x.get("ZombieType"))
    return out


def _armed_slots(game: str) -> list[str]:
    return list(load_profile(game).armed_enemies.get("slots", ()))


def _new_load_set(src_set: Block, sl: crossgame.LevelSlot, p: LevelPlan,
                  cost: dict[str, int]) -> tuple:
    """The source's load set under the slot's level name, types renamed, dropped types
    left out, ``number`` and ``total_cost`` recounted (``cost``: each source type's cost,
    `importzombie.costs` of the source game)."""
    from .importzombie import LOAD_SET_MAX
    children = []
    for e in src_set.children:
        kept: list[tuple[str, str]] = []                  # (target type, source type)
        for pr in e.props:
            if not re.fullmatch(r"type\d+", pr.key):
                continue
            new = p.zombies.get(pr.value)
            if new is None:
                continue
            if len(kept) >= LOAD_SET_MAX:
                p.log.append(Resolution(f"load set {e.name}", "dropped",
                                        f"{pr.value}: {LOAD_SET_MAX} types at most"))
                continue
            kept.append((new, pr.value))
        total = sum(cost.get(s.lower(), 0) for _, s in kept)
        rest = [(pr.key, pr.value) for pr in e.props
                if not re.fullmatch(r"type\d+", pr.key) and pr.key not in ("number",
                                                                          "total_cost")]
        props = [kv for kv in rest if kv[0] in ("start", "end")] + \
            [(f"type{i}", t) for i, (t, _) in enumerate(kept)] + \
            [("number", str(len(kept))), ("total_cost", str(total))] + \
            [kv for kv in rest if kv[0] not in ("start", "end")]
        children.append(("cZombieLoadSetEntry", e.name, props, []))
    p.log.append(Resolution(f"cZombieLoadSet {sl.level}", "brought",
                            f"{len(children)} time-of-day entries"))
    return ("cZombieLoadSet", sl.level, [], children)


def _mission(dst_tree: AssetTree, sl: crossgame.LevelSlot, ready: Block, p: LevelPlan,
             armed: set[str]) -> tuple:
    """The mod's own zombie mission (module docstring): the target's own zombie mission's
    settings, ``LevelRequiredToStartName`` the slot, and the source level's zombie
    blocks with their types resolved."""
    ref = zombie_mission_of(dst_tree, crossgame.level_slot(
        p.dst, load_profile(p.dst).level_door.get("level", sl.script)).level)
    props = [(k, ref.get(k)) for k in MISSION_PROPS if ref is not None and ref.get(k)]
    props.append(("LevelRequiredToStartName", sl.name))
    props.sort(key=lambda kv: kv[0].lower())
    unknown = crossgame.unknown_classes(p.dst)
    children = []
    for x in ready.children:
        if x.cls not in ZOMBIE_CLASSES or x.cls in unknown:
            p.log.append(Resolution(f"mission: {x.cls} {x.name}", "dropped",
                                    "not a zombie block" if x.cls not in ZOMBIE_CLASSES else
                                    f"{p.dst.upper()}'s program doesn't know {x.cls}"))
            continue
        spec = _zombie_block(x, p, armed)
        if spec is not None:
            children.append(spec)
    name = f"Dr2kit{_camel(sl.name)}Zombies"
    ready_props = [(pr.key, pr.value) for pr in ready.props if pr.key != "LevelName"] + \
        [("LevelName", sl.level)]
    ready_props.sort(key=lambda kv: kv[0].lower())
    p.log.append(Resolution(f"mission {name}", "brought",
                            f"{len(children)} zombie blocks of {p.level.level}'s mission"))
    return ("cMissionDefinition", name, props,
            [("cMissionLevelReady", f"{_camel(sl.name)}Ready", ready_props, children)])


def _camel(name: str) -> str:
    return "".join(w.capitalize() for w in name.lower().split("_"))


def _zombie_block(x: Block, p: LevelPlan, armed: set[str]) -> tuple | None:
    """One zombie block with its types resolved; None when nothing is left of it."""
    props = []
    where = f"mission: {x.cls} {x.name}"
    if x.cls == "cMissionZombieFactory":
        pairs = []
        for pr in x.props:
            m = re.fullmatch(r"Type(\d+)", pr.key)
            if m:
                pairs.append((m.group(1), pr.value, x.get(f"Amount{m.group(1)}")))
        kept = []
        for _, ty, amount in pairs:
            new = p.zombies.get(ty)
            if new is None:
                p.log.append(Resolution(where, "dropped", f"{amount} × {ty} (type left out)"))
                continue
            if new.lower() in armed:
                p.log.append(Resolution(where, "dropped",
                                        f"{amount} × {ty}: an armed enemy in a crowd "
                                        f"crashes the game (single spawns only)"))
                continue
            kept.append((new, amount))
        if not kept:
            return None
        for pr in x.props:
            if not re.fullmatch(r"(Type|Amount)\d+", pr.key):
                props.append((pr.key, pr.value))
        for i, (ty, amount) in enumerate(kept):
            props += [(f"Amount{i}", amount or "1"), (f"Type{i}", ty)]
    elif x.cls == "cMissionSpawnZombie":
        ty = x.get("ZombieType")
        new = p.zombies.get(ty) if ty else None
        if ty and new is None:
            p.log.append(Resolution(where, "dropped", f"{ty} (type left out)"))
            return None
        for pr in x.props:
            v = pr.value
            if pr.key == "ZombieType":
                v = new
            elif pr.key == "SpawnWithItem" and v:
                v = _item(p, v, where)
                if v is None:
                    continue
            props.append((pr.key, v))
    else:
        props = [(pr.key, pr.value) for pr in x.props]
    props.sort(key=lambda kv: kv[0].lower())
    return (x.cls, x.name, props, [to_spec(c) for c in x.children])


# --- the text files ---------------------------------------------------------------------

_ITEMS_SRC: dict = {}
_ITEMS_DST: dict = {}
_REFUSED: dict[str, str] = {}                    # item (lower) -> why it can't be brought
_TREES: list = [None, None]


def _item(p: LevelPlan, name: str, where: str) -> str | None:
    """An item name as the target has it: kept, brought (queued for `importitem`), or
    None (dropped, logged)."""
    low = name.lower()
    if low in _ITEMS_DST:
        return name
    if low in _ITEMS_SRC:
        why = _REFUSED.get(low)
        if why is None and all(i.lower() != low for i in p.items):
            from . import importitem
            try:
                importitem.plan(_TREES[0], _TREES[1], p.src, p.dst, _ITEMS_SRC[low].name)
                p.items.append(_ITEMS_SRC[low].name)
            except Dr2Error as e:
                why = _REFUSED[low] = str(e)
        if why is not None:
            p.log.append(Resolution(where, "dropped", f"{name}: {why}"))
            return None
        return name
    p.log.append(Resolution(where, "dropped", f"{name} is an item of neither game"))
    return None


def _script(src_tree: AssetTree, dst_tree: AssetTree, p: LevelPlan, kind: str, items_src,
            items_dst, ids: _IdPool, ret: crossgame.LevelSlot | None, ret_spawn: str) -> None:
    """The recipe for one text file: a copy of the source's with edits (module
    docstring)."""
    global _ITEMS_SRC, _ITEMS_DST
    _ITEMS_SRC, _ITEMS_DST = items_src, items_dst
    _TREES[:] = [src_tree, dst_tree]
    name = f"{kind}{p.level.script}.txt"
    try:
        raw = src_tree.resolve(f"{DATAFILE}/{name}").data()
    except Dr2Error:
        if kind:
            p.warnings.append(f"{p.src.upper()} has no {name}")
            return
        raise
    before = Document.parse(raw, name)
    doc = Document.parse(raw, name)
    if kind != "nm_":
        _rewrite(doc, p, ids, ret, ret_spawn, src_tree, dst_tree)
    if not kind:
        for new, like in p.spawns:
            src_b = doc.get(f"cSpawnPoint {like}")
            if src_b is not None and doc.get(f"cSpawnPoint {new}") is None:
                doc.add(None, "cSpawnPoint", new, [(pr.key, pr.value) for pr in src_b.props])
    e = le.diff(before, doc)
    recipe = {"format": COPY_FORMAT, "from": p.src, "copy": f"{DATAFILE}/{name}"}
    if e:
        recipe["edits"] = json.loads(le.to_json(e))
        del recipe["edits"]["format"]
    p.recipes[f"{DATAFILE}/{kind}{p.slot.script}.txt{COPY_EXT}"] = recipe


def _rewrite(doc: Document, p: LevelPlan, ids: _IdPool, ret, ret_spawn: str,
             src_tree: AssetTree, dst_tree: AssetTree) -> None:
    unknown = crossgame.unknown_classes(p.dst)
    src_strings = _strings(src_tree)
    dst_files = {e.name.lower() for e in dst_tree.open_archive(DATAFILE).entries}
    own = {s.level.upper() for s in crossgame.level_slot_list(p.dst) if s.shipped}

    def visit(blocks: list[Block]) -> None:
        for b in list(blocks):
            if _visit(b):
                visit(b.children)

    def _visit(b: Block) -> bool:
        where = f"{doc.source}: {b.cls} {b.name}".rstrip()
        if b.cls in unknown:
            doc.remove(b)
            p.log.append(Resolution(where, "dropped",
                                    f"{p.dst.upper()}'s program doesn't know {b.cls}"))
            return False
        for pr in list(b.props):
            k, v = pr.key, pr.value
            if (ITEM_KEYS.match(k) or LEVEL_ITEM_KEYS.match(k)) and v:
                if _item(p, v, where) is None:
                    if k == "ItemName":
                        doc.remove(b)
                        return False
                    doc.unset(b, k)
            elif k == "Level" and v:
                _door(doc, b, p, ret, ret_spawn, own, where)
            elif LEVEL_STRING_KEYS.match(k) and v.isdigit() and int(v) in src_strings \
                    and int(v) > 0:
                n = ids.take()
                p.strings[n] = int(v)
                doc.set(b, k, str(n))
            elif k == "ContextFileName" and v:
                f = v.strip("/\\")
                if f.lower() not in dst_files:
                    path = f"{DATAFILE}/{f}{COPY_EXT}"
                    if path not in p.recipes:
                        p.recipes[path] = {"format": COPY_FORMAT, "from": p.src,
                                           "copy": f"{DATAFILE}/{f}"}
                        p.log.append(Resolution(where, "brought", f"light settings {f}"))
        return True

    visit(doc.blocks)


def _door(doc: Document, b: Block, p: LevelPlan, ret, ret_spawn: str, own: set[str],
          where: str) -> None:
    """A door or trigger's ``Level`` in the target (module docstring)."""
    v = b.get("Level") or ""
    prefixed = v.upper().startswith("LEVEL_")
    name = v.upper().removeprefix("LEVEL_")
    if f"LEVEL_{name}" == p.level.level.upper():
        doc.set(b, "Level", p.slot.level if prefixed else p.slot.name)
        return
    if f"LEVEL_{name}" in own:
        return                                   # a level the target has (rare)
    if b.cls == "cTriggerVolume" and b.get("ActionType") != "3":
        # not a door (a save point, ActionType 4: Case Zero's diner names
        # LEVEL_AMERICANA_CASINO): the brought level's own slot, a level the target has
        doc.set(b, "Level", p.slot.level if prefixed else p.slot.name)
        p.log.append(Resolution(where, "renumbered", f"Level {v} -> {p.slot.level} (not a "
                                                     f"door; {v} is not a level of "
                                                     f"{p.dst.upper()})"))
        return
    if ret is None:
        p.unresolved.append(f"{where}: Level {v}: no level of {p.dst.upper()} to lead back to")
        return
    doc.set(b, "Level", ret.level if prefixed else ret.name)
    if ret_spawn:
        doc.set(b, "LevelSpawnPoint", ret_spawn)
    for k in DOOR_KEYS_OFF:
        doc.unset(b, k)
    p.log.append(Resolution(where, "renumbered", f"door to {v} -> back to {ret.level} "
                                                 f"({ret_spawn})"))


def _arrive(src_tree: AssetTree, lv: crossgame.LevelSlot) -> str:
    """The spawn point an entry door leads to: ``Start``, else the first one."""
    doc = Document.parse(src_tree.resolve(f"{DATAFILE}/{lv.script}.txt").data(), "")
    spawns = [b.name for b in doc.blocks if b.cls == "cSpawnPoint"]
    if not spawns:
        raise Dr2Error(f"{lv.script}.txt has no spawn point to arrive at")
    return next((s for s in spawns if s.lower() == "start"), spawns[0])


def _entry_door(dst_tree: AssetTree, p: LevelPlan, ret: crossgame.LevelSlot, where: str,
                ids: _IdPool) -> None:
    """A door (``cTriggerVolume``, ``ActionType 3``) into the brought level, in the
    target's level ``ret``: a copy of that level's first door with the slot, the arrival
    spawn point, ``where`` and a prompt of its own (the level's name)."""
    file = f"waypoint_{ret.script}.txt"
    doc = Document.parse(dst_tree.resolve(f"{DATAFILE}/{file}").data(), file)
    like = next((b for b in doc.walk() if b.cls == "cTriggerVolume" and
                 b.get("ActionType") == "3" and b.get("Level")), None)
    if like is None:
        p.unresolved.append(f"{file} has no door to copy for the entry door")
        return
    try:
        loc = [float(x) for x in where.split(",")]
        assert len(loc) == 3
    except (ValueError, AssertionError):
        raise Dr2Error(f"the door's place {where!r}: write x,y,z") from None
    props = {pr.key: pr.value for pr in like.props}
    text = " ".join(w.capitalize() for w in p.level.script.split("_"))
    n = ids.take()
    p.door_text = (n, text)
    props.update({"Level": p.slot.level, "LevelSpawnPoint": p.arrive,
                  "Location": ",".join(f"{x:g}" for x in loc), "DisplayName": str(n)})
    p.door = {"file": file, "name": f"Dr2kitTo{_camel(p.slot.name)}", "props": props}


def _asked_spawns(dst_tree: AssetTree, p: LevelPlan) -> None:
    """Spawn points the target's own doors to the slot ask for (Case Zero's street has a
    door to ``PROLOGUE_BOWLING`` / ``BowlingStart``): copies of the arrival one."""
    for s in crossgame.level_slot_list(p.dst):
        if not s.shipped:
            continue
        for kind in ("", "waypoint_"):
            try:
                doc = Document.parse(dst_tree.resolve(
                    f"{DATAFILE}/{kind}{s.script}.txt").data(), "")
            except Dr2Error:
                continue
            for b in doc.walk():
                lv = (b.get("Level") or "").upper().removeprefix("LEVEL_")
                sp = b.get("LevelSpawnPoint")
                if lv == p.slot.name and sp and sp.lower() != p.arrive.lower() and \
                        all(sp.lower() != x.lower() for x, _ in p.spawns):
                    p.spawns.append((sp, p.arrive))


# --- writing ---------------------------------------------------------------------------

def write(p: LevelPlan, mod_dir: str | Path, dst_tree: AssetTree, base_dirs=()) -> list[Path]:
    """Write a `LevelPlan` into a mod (module docstring). Items and zombie types are
    brought first (`importitem`, `importzombie`), then the recipes, the mission, the load
    set, the entry door, the text, ``[requires]`` and ``sources/levels.json``."""
    from ..convert import strings as cstr
    from . import importitem, importzombie
    from .leveledit import TextEdits
    from .manifest import Mod, REPLACE_DIR
    if p.unresolved:
        raise Dr2Error("can't bring the level: " + "; ".join(p.unresolved))
    root = Path(mod_dir)
    out: list[Path] = []
    # the level's text first: the items' imports then see its ids as taken
    if p.strings:
        for lang in cstr.languages(dst_tree):
            if lang == "id":
                continue
            out.append(cstr.set_mod_copies(root, lang, {k: (p.src, v)
                                                        for k, v in p.strings.items()}))
    if p.door_text:
        n, text = p.door_text
        for lang in cstr.languages(dst_tree):
            if lang == "id":
                continue
            out.append(cstr.set_mod_strings(root, lang, {n: text}))
    for item in p.items:
        try:
            _, files = importitem.import_item(mod_dir, item, p.src, p.dst, dst_tree, base_dirs)
            out += files
        except Dr2Error as e:
            p.log.append(Resolution(f"item {item}", "dropped", str(e)))
    for zp in p.zombie_plans:
        out += importzombie.write(zp, mod_dir, dst_tree, base_dirs)
    for rel, recipe in p.recipes.items():
        f = root.joinpath(ADD_DIR, *split(rel))
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(recipe, indent=1) + "\n", "utf-8")
        out.append(f)
    if p.mission is not None:
        m = TextEdits(mod_dir, "missions.txt", dst_tree, base_dirs)
        cls, name, props, children = p.mission
        old = m.doc.get(f"{cls} {name}")
        if old is not None:
            m.doc.remove(old)
        m.doc.add(None, cls, name, props, children)
        out.append(m.save())
    if p.load_set is not None:
        s = TextEdits(mod_dir, SETS, dst_tree, base_dirs)
        cls, name, props, children = p.load_set
        old = s.doc.get(f"{cls} {name}")
        if old is not None:
            s.doc.remove(old)
        s.doc.add(None, cls, name, props, children)
        saved = s.save()
        out.append(saved)
        mirror = root.joinpath(REPLACE_DIR, *split(CACHE), saved.name)  # the copy the game reads
        mirror.parent.mkdir(parents=True, exist_ok=True)
        doc = json.loads(saved.read_text("utf-8"))
        doc["file"] = f"{CACHE}/{SETS}"
        mirror.write_text(json.dumps(doc, indent=1) + "\n", "utf-8")
        out.append(mirror)
    if p.door:
        w = TextEdits(mod_dir, p.door["file"], dst_tree, base_dirs)
        old = w.doc.get(f"cTriggerVolume {p.door['name']}")
        if old is not None:
            w.doc.remove(old)
        w.doc.add(None, "cTriggerVolume", p.door["name"], sorted(p.door["props"].items(),
                                                                 key=lambda kv: kv[0].lower()))
        out.append(w.save())
    m = Mod.load(root)
    games = sorted(set(m.requires.get("games", [])) | {p.src, p.dst})
    if games != sorted(m.requires.get("games", [])):
        m.requires["games"] = games
        m.save()
    log = root / "sources" / "levels.json"
    log.parent.mkdir(parents=True, exist_ok=True)
    old = json.loads(log.read_text("utf-8")) if log.is_file() else {}
    old[p.slot.level] = {"level": p.level.level, "from": p.src, "into": p.dst,
                         "folder": p.folder, "zones": p.zones, "items": p.items,
                         "zombies": p.zombies, "arrive": p.arrive,
                         "mission": p.mission[1] if p.mission else None,
                         "log": [r.__dict__ for r in p.log if r.how != "kept"],
                         "warnings": p.warnings}
    log.write_text(json.dumps(old, indent=1) + "\n", "utf-8")
    return out + [log]


def import_level(mod_dir: str | Path, level: str, src: str, dst: str, dst_tree: AssetTree,
                 slot: str | None = None, door: str | None = None,
                 base_dirs=()) -> tuple[LevelPlan, list[Path]]:
    """Plan and write (module docstring). The mod becomes a mod for ``dst``."""
    from . import importitem, importzombie
    from .leveledit import TextEdits
    from .manifest import Mod
    m = Mod.load(mod_dir)
    sets = TextEdits(mod_dir, SETS, dst_tree, base_dirs).doc.to_bytes().decode("latin-1")
    p = plan(crossgame.source_tree(src), dst_tree, src, dst, level, slot, door, m.id,
             taken_slots=tuple(mod_levels(mod_dir)), taken_ids=importitem.taken_ids(mod_dir),
             taken_zombies=importzombie.mod_slots(mod_dir), sets_text=sets)
    files = write(p, mod_dir, dst_tree, base_dirs)
    m = Mod.load(mod_dir)
    if tuple(m.games) != (dst,):
        m.games = (dst,)
        m.save()
    return p, files


def prebuild(mod_dir: str | Path, dst_tree: AssetTree, workers: int = 0,
             progress=None) -> int:
    """Build (and so cache, `newitem.build_copy`) the mod's zone recipes now, several at
    once (``workers``: processes, default one per CPU but one; 1 builds in this process):
    the first build of a brought level takes minutes in one process (the LZX encoder).
    Returns how many were built. ``progress(done, total, name)``. A script calling it with
    several workers needs an ``if __name__ == "__main__"`` guard (forkserver, CLAUDE.md)."""
    import os
    from concurrent.futures import ProcessPoolExecutor
    recipes = []
    for f in Path(mod_dir).joinpath(ADD_DIR, *split(ENV)).rglob(f"*.big{COPY_EXT}"):
        r = json.loads(f.read_text("utf-8"))
        if r.get("from") and not f.name.lower().startswith("zonelist"):
            recipes.append((str(f), r))
    if not recipes:
        return 0
    n = workers or max(1, min(len(recipes), (os.cpu_count() or 2) - 1))
    done = 0
    if n == 1:                         # in this process (Studio's background thread)
        for f, r in recipes:
            _prebuild_one(str(dst_tree.root), r, str(mod_dir), f)
            done += 1
            if progress:
                progress(done, len(recipes), Path(f).name)
        return done
    with ProcessPoolExecutor(n) as ex:
        futs = {ex.submit(_prebuild_one, str(dst_tree.root), r, str(mod_dir), f): f
                for f, r in recipes}
        for fut in futs:
            fut.result()
            done += 1
            if progress:
                progress(done, len(recipes), Path(futs[fut]).name)
    return done


def _prebuild_one(root: str, recipe: dict, mod_dir: str, where: str) -> None:
    from .newitem import build_copy
    build_copy(AssetTree(Path(root)), recipe, Path(mod_dir), where)

"""Use a zombie type of the other game: Case West's in Case Zero (phase 15 step 4,
docs/phase15-kickoff.md §Zombies, decision 1).

Why: the user's phase 15 ("mutant zombies… automatically assigned properly so it doesn't
crash"; decision 1: "foreign zombies are added how it would natively and work with their
zombie spawn area"). A zombie type is, in the data (docs/formats.md §Zombie types):

* a **name in the program's type table** (Case Zero: 32 names, 12 shipped; Case West: 10,
  all shipped; `crossgame.zombie_types`). A program only spawns names of its own table,
  so a Case West type takes one of Case Zero's **empty slots** (a name of the table whose
  model the game doesn't ship): its own name when Case Zero's table has it
  (``zombie_gas``, ``zombie_fat_female``), else a free one (``zombie_dealer``…);
* its **model pack** ``data/models/zombies.big/<type>.big`` (detail levels
  ``<type>_2/_3/_4`` with their texture packs): copied from the other game under the
  slot's name, drawn with its own game's shaders (`convert.shadercarry`), its scenes made
  right for the target (`crossgame.fit_scenes`);
* its **class** ``cZombieClassItem <type>`` of ``items.txt`` (health, damage, the
  behaviours it picks from): Case Zero has one for every slot; it gets the other game's
  keys;
* the **behaviours** it names (``cZombieBehaviourItem`` blocks of ``items.txt``): kept
  when the target has one of that name, brought when not (Case West's ``EnemyRanged``,
  ``EnemyHazardUnit``, ``EnemyZombieController``);
* its place in a level's **load set** (``zombiesets.txt``: ``cZombieLoadSet
  LEVEL_<SCRIPT>`` → each time-of-day entry's ``type<n>``, ``number``, ``total_cost``)
  with its memory cost read from the other game's load sets. The importer adds it to the
  levels asked for (``total_cost`` kept in step). The same edits go to the copy in
  ``data/datafile/persistent_filecache.big`` (the build evicts ``preload4.big``'s copy of
  that archive, profile ``preload_evict``): **that copy is the one the game reads**
  (measured 2026-10-13: a load set edited in ``datafile.big`` only changed nothing);
* its **memory**: the ``total_cost`` numbers don't measure it (formats.md §Engine memory).
  A loaded type takes its pack unpacked in the program's fixed **Zombie heap** (30.2 MB in
  both games), the loaded types sharing ~5.5 MB more; Case Zero's street leaves 1.6 MB of
  it unmodded (profile ``zombie_heap``); both recomps grow it by 16 MiB since 2026-10-13
  (``recomp_growth``). The plan says how much the type takes and warns when it fits only in
  the grown heap, or not even there unless it replaces one of the level's types (the test
  mod with gas zombies, a guard and two brought weapons ran out of the title's size);
* **guards whose fighting is program code** (Case West's ``security_heavy`` /
  ``security_lab``: ``HazardUnit`` / ``ZombieController``, profile ``armed_enemies``
  ``as_soldiers``) become the target's soldiers with a gun, like the armed guards.

Spawning it is then the same as for a native type: the Maps editor's zombie retype /
spawns (phase 11, guide 19) name the slot.

Case Zero → Case West needs Case West's table grown from 10 to the engine's 32 (a recomp
change, deferred and written up for a contributor: docs/TODO.md #1): until then `plan`
refuses it, saying so.

The mod gets recipes and edits only, never game data (LICENSE).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..container.vpath import AssetTree, split
from ..convert import crossgame
from ..errors import Dr2Error
from ..formats.levelscript import Document
from .importitem import Resolution
from .manifest import ADD_DIR, REPLACE_DIR
from .newitem import COPY_EXT, COPY_FORMAT
from ..profiles import load_profile

ZOMBIES = "data/models/zombies.big"
ITEMS = "data/datafile.big/items.txt"
SETS = "data/datafile.big/zombiesets.txt"
CACHE = "data/datafile/persistent_filecache.big"     # holds a copy of zombiesets.txt
COST = re.compile(r'type\d+ = "(\w+)" // (\d+)')
# A load-set entry holds at most 13 types (type0..type12): with a 14th Case Zero faulted
# at boot reading index 13 (measured 2026-10-13, formats.md §Zombie types). A type left out
# still loads where something spawns it.
LOAD_SET_MAX = 13


@dataclass
class ZombiePlan:
    """Everything a zombie import does (module docstring); nothing written yet."""
    src: str
    dst: str
    type: str                        # the other game's type name
    slot: str                        # the target's type name it becomes
    recipes: dict[str, dict] = field(default_factory=dict)       # path under add/ -> recipe
    class_keys: list[tuple[str, str]] = field(default_factory=list)
    behaviours: list = field(default_factory=list)               # blocks to add (spec)
    load_sets: dict[str, int] = field(default_factory=dict)      # level set -> its new cost
    cost: int = 0
    heap_bytes: int = 0              # the type's pack unpacked: what it takes in the Zombie heap
    log: list[Resolution] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    armed: bool = False              # an armed enemy (a behaviour that shoots)
    gun: tuple[str, str] | None = None   # (the source game's gun, the item name the
                                         #  target's program gives this slot)

    def report(self) -> str:
        names = {"cz": "Case Zero", "cw": "Case West"}
        lines = [f"{self.type}: from {names[self.src]} into {names[self.dst]} as "
                 f"{self.slot}"]
        for how in ("brought", "kept", "renumbered", "dropped"):
            hits = [r for r in self.log if r.how == how]
            if hits:
                lines.append(f"  {how} ({len(hits)}):")
                lines += [f"    {r.where}: {r.what}" for r in hits]
        lines += [f"  WARNING: {w}" for w in self.warnings]
        return "\n".join(lines)


def _items(tree: AssetTree) -> Document:
    return Document.parse(tree.resolve(ITEMS).data(), ITEMS)


def _sets(tree: AssetTree) -> str:
    return tree.resolve(SETS).data().decode("latin-1")


def shipped_types(tree: AssetTree) -> set[str]:
    """Type names whose model the game ships (``zombies.big/<type>.big``)."""
    return {e.name.lower()[:-4] for e in tree.open_archive(ZOMBIES).entries
            if e.name.lower().endswith(".big")}


def costs(tree: AssetTree) -> dict[str, int]:
    """Each type's load-set cost (the largest the game's ``zombiesets.txt`` gives it)."""
    out: dict[str, int] = {}
    for ty, c in COST.findall(_sets(tree)):
        out[ty.lower()] = max(out.get(ty.lower(), 0), int(c))
    return out


def budget(tree: AssetTree) -> int:
    """The most a level of the game's own costs (its load sets' ``total_cost``). Not a
    memory measure (formats.md §Engine memory): `pack_bytes` is."""
    return max((int(c) for c in re.findall(r'total_cost = "(\d+)"', _sets(tree))), default=0)


def empty_slots(tree: AssetTree, game: str, taken: set[str] = frozenset()) -> list[str]:
    """The game's type names with no model shipped (and not ``taken`` by the mod)."""
    have = shipped_types(tree) | {t.lower() for t in taken}
    return [t for t in crossgame.zombie_types(game) if t.lower() not in have]


def mod_slots(mod_dir: str | Path) -> dict[str, str]:
    """Slots a mod fills already: slot → the other game's type (``sources/zombies.json``)."""
    f = Path(mod_dir) / "sources" / "zombies.json"
    if not f.is_file():
        return {}
    return {k: v["type"] for k, v in json.loads(f.read_text("utf-8")).items()}


def plan(src_tree: AssetTree, dst_tree: AssetTree, src: str, dst: str, zombie: str,
         slot: str | None = None, levels: tuple[str, ...] = (),
         taken: dict[str, str] | None = None, sets_text: str | None = None) -> ZombiePlan:
    """What importing the type ``zombie`` of ``src`` into ``dst`` does (module docstring).
    ``slot``: the target's type name to use (default: the same name if empty, else the
    first empty one the mod doesn't use, ``taken``, and the source game doesn't name);
    ``sets_text``: the mod's ``zombiesets.txt`` as edited so far (default: the game's); ``levels``: script names whose load
    sets get it (``prologue``)."""
    from ..convert import shadercarry
    taken = {k.lower(): v for k, v in (taken or {}).items()}
    zl = zombie.lower()
    if zl not in shipped_types(src_tree) or \
            zl not in {t.lower() for t in crossgame.zombie_types(src)}:
        raise Dr2Error(f"{zombie!r} is not a zombie type of {src.upper()} "
                       f"({', '.join(sorted(shipped_types(src_tree)))})")
    table = [t.lower() for t in crossgame.zombie_types(dst)]
    if len(table) < 32 and dst == "cw":
        raise Dr2Error("Case West's program has room for its own 10 zombie types only; "
                       "growing that table is a change to the Case West recomp that is "
                       "not done yet (docs/TODO.md #1)")
    free = empty_slots(dst_tree, dst, set(taken))
    a_items = _items(src_tree)
    # guards whose fighting is their own program's code (Case West's HazardUnit and
    # ZombieController: no data brings it) become the target's soldiers, armed (user's
    # choice 2026-10-13; docs/formats.md §Zombie types)
    as_soldier = zl in [t.lower() for t in load_profile(src).armed_enemies.get("as_soldiers", ())]
    armed = as_soldier or _is_armed(a_items, zombie)
    rules = load_profile(dst).armed_enemies if armed else {}
    if slot is None and rules.get("slots"):
        slot = next((s for s in rules["slots"] if s in free), None)
    if slot is None:
        prev = next((s for s, t in taken.items() if t.lower() == zl), None)
        # the same name when empty; else the first empty slot that is not one of the
        # source game's own names (CW's zombie_fat_female waits for CW's own)
        theirs = {t.lower() for t in crossgame.zombie_types(src)}
        other = [f for f in free if f not in theirs]
        slot = prev or (zl if zl in free else (other[0] if other else None))
        if slot is None:
            raise Dr2Error(f"{dst.upper()}'s zombie type table has no empty slot left")
    slot = slot.lower()
    if slot not in table:
        raise Dr2Error(f"{slot!r} is not a type name of {dst.upper()}'s program "
                       f"(empty ones: {', '.join(free)})")
    if slot in shipped_types(dst_tree):
        raise Dr2Error(f"{slot!r} is one of {dst.upper()}'s own types (empty ones: "
                       f"{', '.join(free)})")
    if slot in taken and taken[slot].lower() != zl:
        raise Dr2Error(f"the mod already puts {taken[slot]} in {slot!r}")
    p = ZombiePlan(src, dst, zombie, slot, armed=armed)
    if as_soldier:
        p.log.append(Resolution(f"{slot}: fighting", "kept",
                                f"{dst.upper()}'s soldier program with a gun: {zombie}'s own "
                                f"fighting is {src.upper()} program code, which "
                                f"{dst.upper()}'s program lacks"))

    # 1. the model pack under the slot's name, with its own game's shaders
    data = src_tree.resolve(f"{ZOMBIES}/{zombie}.big").data()
    sd, ps = shadercarry.used_shaders(data)
    c = shadercarry.plan(src_tree, dst_tree, src, dst, sd, ps)
    recipe = {"format": COPY_FORMAT, "from": src, "copy": f"{ZOMBIES}/{zombie}.big",
              "rename": {zombie: slot}}
    what = f"model {zombie} as {slot}"
    if c.sd or c.ps:
        recipe["shaders"] = c.to_json()
        for k, r in shadercarry.recipes(c, dst_tree).items():
            p.recipes.setdefault(k, r)
        what += (f" with its {src.upper()} shaders ({len(c.sd)} descriptions, "
                 f"{len(c.vs)} vertex and {len(c.ps)} pixel shaders)")
    p.recipes[f"{ZOMBIES}/{slot}.big{COPY_EXT}"] = recipe
    p.log.append(Resolution(f"{slot}: model", "brought", what))

    # 2. its class and the behaviours it names
    a, b = a_items, _items(dst_tree)
    src_cls = a.get(f"cZombieClassItem {zombie}")
    if src_cls is None:
        raise Dr2Error(f"{src.upper()}'s items.txt has no cZombieClassItem {zombie}")
    have = {blk.name.lower() for blk in b.blocks if blk.cls == "cZombieBehaviourItem"}
    src_beh = {blk.name.lower(): blk for blk in a.blocks if blk.cls == "cZombieBehaviourItem"}
    from ..formats.levelscript import to_spec
    own = rules.get("behaviour")
    for pr in src_cls.props:
        if own and pr.key.startswith(("BehaviourNames", "ChanceOfBehaviour")):
            # an armed enemy fights with the target's own soldier behaviour: the other
            # game's (Case West's EnemyRanged) has moves the target's animation graph
            # lacks, and its guards aimed once then fell like zombies (user, 2026-10-13)
            if pr.key == "BehaviourNames0":
                p.class_keys += [("BehaviourNames0", own), ("ChanceOfBehaviour0", "100")]
                p.log.append(Resolution(f"{slot}: {pr.key}", "kept",
                                        f"behaviour {own} ({dst.upper()}'s own soldiers', in "
                                        f"place of {pr.value}: its moves are in this game's "
                                        f"animation graph)"))
            continue
        p.class_keys.append((pr.key, pr.value))
        if pr.key.startswith("BehaviourNames") and pr.value:
            v = pr.value.lower()
            if v in have:
                p.log.append(Resolution(f"{slot}: {pr.key}", "kept",
                                        f"behaviour {pr.value} ({dst.upper()}'s own)"))
            elif v in src_beh:
                if all(s[1].lower() != v for s in p.behaviours):
                    p.behaviours.append(to_spec(src_beh[v]))
                p.log.append(Resolution(f"{slot}: {pr.key}", "brought",
                                        f"behaviour {pr.value}"))
            else:
                p.log.append(Resolution(f"{slot}: {pr.key}", "kept",
                                        f"behaviour {pr.value} (in neither game)"))
    p.log.append(Resolution(f"{slot}: class", "brought",
                            f"cZombieClassItem {zombie}'s {len(p.class_keys)} keys"))

    # 2b. animation banks the target lacks but its own animation graph names: Case Zero's
    # graph has all 69 of the gas zombies' moves and asks for data/anim/gaszombies.big,
    # which only Case West ships (U2, 2026-10-13: the gas crowds stayed empty without it)
    for bank, why in anim_banks(src_tree, dst_tree, zombie):
        p.recipes.setdefault(f"{bank}{COPY_EXT}", {"format": COPY_FORMAT, "from": src,
                                                  "copy": bank})
        p.log.append(Resolution(f"{slot}: animations", "brought", f"{bank} ({why})"))
    # 2c. voice banks likewise: Case Zero's sound list (scenegraph.txt) names the gas
    # zombies' voices (fx_gzombieakalem…) but ships none of their banks; the street's load
    # faulted (guest 0x1C) right after asking for data/audio/fx_gzombieakalem2.big
    for bank, why in voice_banks(src_tree, dst_tree, zombie):
        p.recipes.setdefault(f"{bank}{COPY_EXT}", {"format": COPY_FORMAT, "from": src,
                                                  "copy": bank})
        p.log.append(Resolution(f"{slot}: voices", "brought", f"{bank} ({why})"))
    if armed:
        gun = load_profile(src).armed_enemies.get("gun")
        weapon = rules.get("weapon")
        if gun and weapon and slot in rules.get("slots", ()):
            p.gun = (gun, weapon)
            p.log.append(Resolution(f"{slot}: gun", "brought",
                                    f"{gun} as {weapon} (the item {dst.upper()}'s program "
                                    f"gives a soldier of this slot)"))
        p.warnings.append(
            "an armed enemy: spawn it one at a time (a mission's single spawn, "
            "cMissionSpawnZombie, or the Maps tab's zombie retype), never in a crowd "
            "(cMissionZombieFactory): the soldier AI faults the game when a crowd spawns it")
    if p.behaviours:
        p.warnings.append(
            f"its behaviours ({', '.join(b[1] for b in p.behaviours)}) are "
            f"{src.upper()}'s own: {dst.upper()}'s animation graph has no states for their "
            f"moves yet, so it may not spawn or move (docs/formats.md §Zombie types)")

    # 3. memory and the load sets
    p.cost = costs(src_tree).get(zl, 0)
    p.heap_bytes = pack_bytes(src_tree, zombie)
    heap = load_profile(dst).zombie_heap
    if heap.get("size"):
        p.log.append(Resolution(f"{slot}: memory", "brought",
                                f"{_mb(p.heap_bytes)} of the {_mb(heap['size'])} Zombie heap "
                                f"when loaded (its pack unpacked)"))
    text = sets_text if sets_text is not None else _sets(dst_tree)
    for level in levels:
        name = f"LEVEL_{level.upper()}"
        m = re.search(rf"cZombieLoadSet {re.escape(name)}\b", text)
        if m is None:
            raise Dr2Error(f"{dst.upper()}'s zombiesets.txt has no load set {name}")
        totals = [int(x) for x in re.findall(r'total_cost = "(\d+)"',
                                              text[m.end():_next_block(text, m.end())])]
        new = max(totals, default=0) + p.cost
        p.load_sets[name] = new
        p.log.append(Resolution(f"{slot}: {name}", "brought",
                                f"in the load set (cost {p.cost}, the level then {new})"))
        body = text[m.end():_next_block(text, m.end())]
        full = [e for e in re.split(r"cZombieLoadSetEntry ", body)[1:]
                if slot not in [v.lower() for v in re.findall(r'type\d+ = "(\w+)"', e)]
                and len(re.findall(r'type\d+ = "', e)) >= LOAD_SET_MAX]
        if full:
            p.warnings.append(
                f"{name}: {len(full)} of its time-of-day entries already list {LOAD_SET_MAX} "
                f"types, the most the game takes (a 14th crashes it at boot): {slot} is left "
                f"out of those and loads where something spawns it")
        spare = heap.get("spare", {}).get(name)
        grown = spare + heap.get("recomp_growth", 0) if spare is not None else None
        if spare is not None and p.heap_bytes > grown:
            p.warnings.append(
                f"{name}: {dst.upper()}'s own zombies leave {_mb(grown)} of the Zombie heap "
                f"free there (with the recomp's grown heap) and {slot} takes "
                f"{_mb(p.heap_bytes)}: where it spawns, it must replace a type at least "
                f"{_mb(p.heap_bytes - grown)} big among the types loaded "
                f"({_heaviest(dst_tree)}), or the game runs out of memory and crashes")
        elif spare is not None and p.heap_bytes > spare:
            p.warnings.append(
                f"{name}: {slot} ({_mb(p.heap_bytes)}) fits beside {dst.upper()}'s own zombies "
                f"only in the recomp's grown Zombie heap ({_mb(grown)} free there; recomps "
                f"from 2026-10-13 on); in an older recomp it must replace a type at least "
                f"{_mb(p.heap_bytes - spare)} big, or the game crashes while the level loads")
    return p


def pack_bytes(tree: AssetTree, zombie: str) -> int:
    """What a zombie type takes in the program's Zombie heap when loaded: its pack
    ``zombies.big/<type>.big`` unpacked (measured over nine Case Zero types, formats.md
    §Engine memory; brought shaders live in the shader banks, not here)."""
    sub = tree.open_archive(f"{ZOMBIES}/{zombie}.big")
    return sum(e.size2 or e.size for e in sub.entries)


def _mb(n: int) -> str:
    return f"{n / 1e6:.1f} MB"


def _heaviest(tree: AssetTree, n: int = 3) -> str:
    """The game's heaviest shipped types, for the warning."""
    sizes = sorted(((pack_bytes(tree, t), t) for t in shipped_types(tree)), reverse=True)
    return ", ".join(f"{t} {_mb(b)}" for b, t in sizes[:n])


def _is_armed(items: Document, zombie: str) -> bool:
    """Whether a type is an armed enemy: a behaviour its class names shoots
    (``Range_Shoot``: Case West's guards' ``EnemyRanged``, Case Zero's ``ArmyMerc`` and
    ``DefaultMerc``). Not ``NPC = true``: every behaviour of both games has it."""
    cls = items.get(f"cZombieClassItem {zombie}")
    if cls is None:
        return False
    for v in cls.numbered("BehaviourNames"):
        b = items.get(f"cZombieBehaviourItem {v}")
        if b is not None and b.get("Range_Shoot") is not None:
            return True
    return False


def anim_banks(src_tree: AssetTree, dst_tree: AssetTree,
               zombie: str = "") -> list[tuple[str, str]]:
    """``data/anim/*.big`` banks the source game has and the target lacks, whose moves the
    target's own animation graph (``sgraph.txt``) names (most of them): the target's
    program asks for these files. With ``zombie``, only banks whose name holds a word of
    the type's name (``zombie_gas`` → ``gaszombies.big``)."""
    words = [w for w in zombie.lower().split("_") if w and w != "zombie"]
    from ..container.big import BigArchive
    have = {n.lower() for n, _ in _anim_files(dst_tree)}
    graph = dst_tree.resolve("data/datafile.big/sgraph.txt").data().decode("latin-1").lower()
    out = []
    for name, vp in _anim_files(src_tree):
        if name.lower() in have or (zombie and not any(w in name.lower() for w in words)):
            continue
        moves = set()
        for e in BigArchive.parse(src_tree.resolve(vp).data(), vp).entries:
            if e.name.lower().endswith(".big"):
                inner = src_tree.open_archive(f"{vp}/{e.name}")
                moves |= {x.name.lower().removesuffix(".anm") for x in inner.entries}
        named = sum(m in graph for m in moves)
        if moves and named >= 0.9 * len(moves):
            out.append((vp, f"{named} of its {len(moves)} moves are in this game's "
                            f"animation graph"))
    return out


SCENEGRAPH = "data/datafile.big/scenegraph.txt"
STREAMED = "data/streamedassets.big"


def voice_banks(src_tree: AssetTree, dst_tree: AssetTree,
                zombie: str = "") -> list[tuple[str, str]]:
    """``data/streamedassets.big/<voice><n>.big`` banks of the voices the target's sound
    list names (``cVoiceTalentEntry <talent>`` ``Source``) whose banks the target lacks
    and the source has: the target's program asks for them when a zombie of that voice
    loads. With ``zombie``, only voices whose talent name holds a word of the type's name
    (``zombie_gas`` → ``AKalemAGas``…, ``looter`` → ``Looter``)."""
    try:
        text = dst_tree.resolve(SCENEGRAPH).data().decode("latin-1")
    except Exception:                                           # noqa: BLE001
        return []
    words = [w for w in zombie.lower().split("_") if w and w != "zombie"]
    voices = {v.lower() for t, v in re.findall(
        r'cVoiceTalentEntry (\w+)\s*\{[^}]*?Source = "(\w+)"', text)
        if not zombie or any(w in t.lower() for w in words)}
    have = {e.name.lower() for e in dst_tree.open_archive(STREAMED).entries}
    theirs = [e.name for e in src_tree.open_archive(STREAMED).entries]
    out = []
    for v in sorted(voices):
        if any(re.fullmatch(rf"{v}\d*\.big", n) for n in have):
            continue
        for n in theirs:
            if re.fullmatch(rf"{v}\d*\.big", n.lower()):
                out.append((f"{STREAMED}/{n}", f"voice {v}, named by this game's sound list"))
    return out


def _anim_files(tree: AssetTree) -> list[tuple[str, str]]:
    return [(path.rsplit("/", 1)[-1], path) for path, _ in tree.files()
            if path.lower().startswith("data/anim/") and path.count("/") == 2
            and path.lower().endswith(".big")]


def _next_block(text: str, at: int) -> int:
    m = re.search(r"\ncZombieLoadSet ", text[at:])
    return at + m.start() if m else len(text)


def write(p: ZombiePlan, mod_dir: str | Path, dst_tree: AssetTree, base_dirs=()) -> list[Path]:
    """Write a `ZombiePlan` into a mod: the recipes (``add/``), the class and behaviours
    (``items.txt.edits.json``), the load sets (``zombiesets.txt.edits.json``),
    ``[requires]``'s games and ``sources/zombies.json``."""
    from .leveledit import TextEdits
    from .manifest import Mod
    root = Path(mod_dir)
    out = []
    for rel, recipe in p.recipes.items():
        f = root.joinpath(ADD_DIR, *split(rel))
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(recipe, indent=1) + "\n", "utf-8")
        out.append(f)
    items = TextEdits(mod_dir, "items.txt", dst_tree, base_dirs)
    d = items.doc
    blk = d.get(f"cZombieClassItem {p.slot}")
    if blk is None:
        d.add(None, "cZombieClassItem", p.slot, p.class_keys)
    else:
        keep = {k for k, _ in p.class_keys}
        for pr in list(blk.props):
            if pr.key not in keep:
                d.unset(blk, pr.key)
        for k, v in p.class_keys:
            d.set(blk, k, v)
    for cls, name, props, children, values in p.behaviours:
        if d.get(f"{cls} {name}") is None:
            d.add(None, cls, name, list(props), list(children), values=list(values))
    out.append(items.save())
    if p.load_sets:
        sets = TextEdits(mod_dir, "zombiesets.txt", dst_tree, base_dirs)
        for level in p.load_sets:
            top = sets.doc.get(f"cZombieLoadSet {level}")
            for entry in top.children:
                types = [v.lower() for v in entry.numbered("type")]
                if p.slot in types or len(types) >= LOAD_SET_MAX:
                    continue                # full: a 14th type crashes the game at boot
                sets.doc.set(entry, f"type{len(types)}", p.slot)
                sets.doc.set(entry, "number", str(len(types) + 1))
                total = int(entry.get("total_cost") or 0) + p.cost
                sets.doc.set(entry, "total_cost", str(total))
        saved = sets.save()
        out.append(saved)
        # the same edits on the copy in persistent_filecache.big, the one the game reads
        # (measured 2026-10-13; the build evicts preload4.big's, profile preload_evict)
        mirror = root.joinpath(REPLACE_DIR, *split(CACHE), saved.name)
        mirror.parent.mkdir(parents=True, exist_ok=True)
        doc = json.loads(saved.read_text("utf-8"))
        doc["file"] = f"{CACHE}/zombiesets.txt"
        mirror.write_text(json.dumps(doc, indent=1) + "\n", "utf-8")
        out.append(mirror)
    m = Mod.load(root)
    games = sorted(set(m.requires.get("games", [])) | {p.src, p.dst})
    if games != sorted(m.requires.get("games", [])):
        m.requires["games"] = games
        m.save()
    log = root / "sources" / "zombies.json"
    log.parent.mkdir(parents=True, exist_ok=True)
    old = json.loads(log.read_text("utf-8")) if log.is_file() else {}
    old[p.slot] = {"type": p.type, "from": p.src, "into": p.dst,
                   "levels": sorted(p.load_sets),
                   "log": [r.__dict__ for r in p.log if r.how != "kept"]}
    log.write_text(json.dumps(old, indent=1) + "\n", "utf-8")
    return out + [log]


def import_zombie(mod_dir: str | Path, zombie: str, src: str, dst: str, dst_tree: AssetTree,
                  slot: str | None = None, levels: tuple[str, ...] = (),
                  base_dirs=()) -> tuple[ZombiePlan, list[Path]]:
    """Plan and write (module docstring). The mod becomes a mod for ``dst``."""
    from .leveledit import TextEdits
    from .manifest import Mod
    sets = TextEdits(mod_dir, "zombiesets.txt", dst_tree, base_dirs).doc.to_bytes()
    p = plan(crossgame.source_tree(src), dst_tree, src, dst, zombie, slot, levels,
             mod_slots(mod_dir), sets.decode("latin-1"))
    files = write(p, mod_dir, dst_tree, base_dirs)
    if p.gun:
        files += _bring_gun(mod_dir, p, dst_tree, base_dirs)
    m = Mod.load(mod_dir)
    if tuple(m.games) != (dst,):
        m.games = (dst,)
        m.save()
    return p, files


def _bring_gun(mod_dir, p: ZombiePlan, dst_tree: AssetTree, base_dirs) -> list[Path]:
    """The armed enemy's own gun (imported like any item) and a copy of its block under
    the name the target's program hands to the slot (Case Zero: ``MercAssaultRifle``).
    A real pickup: Case Zero's own soldier gun ``MercArmyM16`` (``IsWeapon = false``)
    vanished when the guard died (user, 2026-10-13)."""
    from .importitem import import_item
    from .leveledit import TextEdits
    gun, weapon = p.gun
    out = []
    items = TextEdits(mod_dir, "items.txt", dst_tree, base_dirs)
    if not any(b.name.lower() == gun.lower() for b in items.doc.blocks):
        _, files = import_item(mod_dir, gun, p.src, p.dst, dst_tree, base_dirs)
        out += files
        items = TextEdits(mod_dir, "items.txt", dst_tree, base_dirs)
    d = items.doc
    src = next(b for b in d.blocks if b.name.lower() == gun.lower())
    old = next((b for b in d.blocks if b.name.lower() == weapon.lower()), None)
    if old is not None:
        d.remove(old)
    d.add(None, src.cls, weapon, {pr.key: pr.value for pr in src.props})
    out.append(items.save())
    return out


def census(src_tree: AssetTree, dst_tree: AssetTree, src: str, dst: str) -> dict:
    """Plan every type of ``src`` into ``dst`` (each into its own default slot): the
    gate ``dr2 census --import`` reports with the items."""
    out = {"types": 0, "planned": 0, "refused": [], "slots": {}}
    taken: dict[str, str] = {}
    own = {t.lower() for t in crossgame.zombie_types(src)}
    for ty in sorted(shipped_types(src_tree) & own):     # (not CW's unused zombie_test)
        if ty in shipped_types(dst_tree):
            continue                              # the target has its own
        out["types"] += 1
        try:
            p = plan(src_tree, dst_tree, src, dst, ty, taken=taken)
        except Dr2Error as e:
            out["refused"].append(f"{ty}: {e}")
            continue
        taken[p.slot] = ty
        out["planned"] += 1
        out["slots"][ty] = p.slot
    return out

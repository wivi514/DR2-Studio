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
  levels asked for and warns when a level then costs more than the target's own levels
  ever do (its budget; Case Zero 18,304). The same edits go to the copy in
  ``data/datafile/persistent_filecache.big`` (the build evicts ``preload4.big``'s copy of
  that archive, profile ``preload_evict``): which copy the game reads is test U2.

Spawning it is then the same as for a native type: the Maps editor's zombie retype /
spawns (phase 11, guide 19) name the slot.

Case Zero → Case West needs Case West's table grown from 10 to the engine's 32 (a recomp
change approved by the user, ARCHITECTURE.md §Recomp integration 3, not built yet): until
then `plan` refuses it, saying so.

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

ZOMBIES = "data/models/zombies.big"
ITEMS = "data/datafile.big/items.txt"
SETS = "data/datafile.big/zombiesets.txt"
CACHE = "data/datafile/persistent_filecache.big"     # holds a copy of zombiesets.txt
COST = re.compile(r'type\d+ = "(\w+)" // (\d+)')


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
    log: list[Resolution] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

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
    """The most a level of the game's own costs (its load sets' ``total_cost``)."""
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
                       "growing it to the engine's 32 is a change to the Case West recomp "
                       "(approved, not built yet: ARCHITECTURE.md §Recomp integration 3)")
    free = empty_slots(dst_tree, dst, set(taken))
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
    p = ZombiePlan(src, dst, zombie, slot)

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
    a, b = _items(src_tree), _items(dst_tree)
    src_cls = a.get(f"cZombieClassItem {zombie}")
    if src_cls is None:
        raise Dr2Error(f"{src.upper()}'s items.txt has no cZombieClassItem {zombie}")
    have = {blk.name.lower() for blk in b.blocks if blk.cls == "cZombieBehaviourItem"}
    src_beh = {blk.name.lower(): blk for blk in a.blocks if blk.cls == "cZombieBehaviourItem"}
    from ..formats.levelscript import to_spec
    for pr in src_cls.props:
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

    # 3. the load sets
    p.cost = costs(src_tree).get(zl, 0)
    limit = budget(dst_tree)
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
        if new > limit:
            p.warnings.append(f"{name} then costs {new}, more than any of {dst.upper()}'s own "
                              f"levels ({limit}): it may run out of zombie memory; spawn "
                              f"fewer types there")
    return p


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
                if p.slot in types:
                    continue
                sets.doc.set(entry, f"type{len(types)}", p.slot)
                sets.doc.set(entry, "number", str(len(types) + 1))
                total = int(entry.get("total_cost") or 0) + p.cost
                sets.doc.set(entry, "total_cost", str(total))
        saved = sets.save()
        out.append(saved)
        # the same edits on the copy in persistent_filecache.big (which copy the game
        # reads is test U2; the build evicts preload4.big's, profile preload_evict)
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
    m = Mod.load(mod_dir)
    if tuple(m.games) != (dst,):
        m.games = (dst,)
        m.save()
    return p, files


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

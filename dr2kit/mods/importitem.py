"""Use an item of the other game: a Case West item in Case Zero, or the other way (phase 15
step 3, docs/phase15-kickoff.md).

Why: the user's phase 15 ("use items from Case West in Case Zero and items from Case Zero in
Case West… automatically assigned properly so it doesn't crash"). An item is a block of
``items.txt`` (with child blocks) and a pack in ``streamedassets.big`` (docs/formats.md
§Levels "Items → models"); its keys name many other things, and each game's program and
data know different names. `plan` goes through **every key** of the block and its child
blocks and resolves each name in the target game, one of:

* **kept**: the target has it (most keys; items both games have; effects 1-370; a model
  pack of the same name, which is the same object: ``clothesbox``, ``bowieknife``…);
* **brought**: copied from the source game by a recipe when the mod is built (the
  item's pack with its shaders `dr2kit.convert.shadercarry`, its move bank
  ``anm_<AnimBankName>.big``, its sound bank ``fx_<AudioFilename>(_p).big``, its combo
  card's pictures, another item it names, its text);
* **renumbered**: an effect number by the effect's name (the tables differ after 370),
  or, for an effect the target lacks, the number of a **free slot** of its table the
  effect is brought into (phase 13's own effects, `dr2kit.mods.neweffect`: the other
  game's effect copied under the slot's name, in the target's layout, with the particle
  pictures the target's ``effects.tex`` lacks; one slot per effect for the whole mod),
  a string id to a new id of the mod (the text copied from the source game's banks), a
  combo card number to a free one;
* **dropped**, with the reason: a child block of a class the target's program doesn't
  name (`crossgame.unknown_classes`), an effect when no free slot is left, an item reference the
  source game can't give, a paint-variant list naming the source game's textures.

Nothing is left unresolved: `Plan.unresolved` must be empty, and the census
(``dr2 census --import``: every item of each game planned into the other) checks it.
The mod gets recipes and blocks only, never game data (LICENSE): ``"from"`` recipes are
built from the player's own copy of the source game, so the mod needs both games
(`dr2kit.mods.requires`).

Not yet seen in game (tests U1-U3): a brought move bank's attacks (the animation graph's
chooser values may be another game's), brought shaders and their parameter numbers.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..catalog import weapons
from ..container.vpath import AssetTree, join, split
from ..convert import crossgame, placed
from ..errors import Dr2Error
from ..formats.levelscript import Block
from .manifest import ADD_DIR
from .newitem import COPY_EXT, COPY_FORMAT

STREAMED = placed.STREAMED
CARDS = "data/frontend/combocards.tex"
EFFECTS_BIG = "data/models/effects.big"
EFFECTS_TEX = "data/models/effects.tex"
ITEM_KEYS = re.compile(r"^(PieceWeaponName\d*|PropToShoot|PropToThrow|DispensedItem|ItemName\d*|"
                       r"PreciousItem|Weapon_\d|FIRE_WeaponToMimic|DamageProp|"
                       r"PrimaryPropAssetName|SecondaryPropAssetName)$")
STRING_KEYS = re.compile(r"^(DisplayName|Card_Label|Ticker_Description|Weapon_Description|"
                         r"Attack\d|Description|FullName|FEInteractionString|RescueQuote|"
                         r"GiftQuote|ItemRejectionDialogue|HostileDialog\d*|SoldOutStringID)$")
DROP_CHILDREN = {"cAlternateTextureInfoItem": "its paint variants name the source game's "
                                              "texture files"}
STRING_BASE = 70000                 # imported text: 70000 + 100 × a number from the mod id


@dataclass
class Resolution:
    """What happened to one name: ``how`` is kept / brought / renumbered / dropped."""
    where: str                       # "Laser_Sword: EffectOnImpact0"
    how: str
    what: str


@dataclass
class Plan:
    """Everything an import does (module docstring); nothing written yet."""
    src: str
    dst: str
    items: list[str] = field(default_factory=list)          # imported, the asked one first
    blocks: list[tuple[str, str, list, list]] = field(default_factory=list)
    recipes: dict[str, dict] = field(default_factory=dict)  # path under add/ -> recipe
    strings: dict[int, int] = field(default_factory=dict)   # new id -> source id
    log: list[Resolution] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    effects: dict[str, int] = field(default_factory=dict)   # brought effect -> its slot
    used_slots: set[int] = field(default_factory=set)       # effect slots taken in the mod

    def report(self) -> str:
        names = {"cz": "Case Zero", "cw": "Case West"}
        lines = [f"{', '.join(self.items)}: from {names[self.src]} into {names[self.dst]}"]
        for how in ("brought", "renumbered", "dropped"):
            hits = [r for r in self.log if r.how == how]
            if hits:
                lines.append(f"  {how} ({len(hits)}):")
                lines += [f"    {r.where}: {r.what}" for r in hits]
        kept = sum(1 for r in self.log if r.how == "kept")
        lines.append(f"  kept as they are: {kept} names")
        if self.unresolved:
            lines.append("  UNRESOLVED:")
            lines += [f"    {u}" for u in self.unresolved]
        return "\n".join(lines)


class _Game:
    """One game's items, packs, effects and text, read once."""

    def __init__(self, game: str, tree: AssetTree):
        self.game, self.tree = game, tree
        self.models = placed.ItemModels(tree)
        self.packs = {n.lower() for n in self.models.packs}
        self.effects = weapons.names(game)
        self.cards = {e.name.lower() for e in tree.open_archive(CARDS).entries}
        self._en = None
        self._fx = self._free = self._pictures = self._audio = None

    @property
    def audio_bits(self) -> int:
        """Every bit the game's own items use in ``PropAudioType`` (CZ: bits 0-11)."""
        if self._audio is None:
            self._audio = 0
            for blk in self.models.blocks.values():
                for x in blk.walk():
                    v = x.get("PropAudioType")
                    if v and v.isdigit():
                        self._audio |= int(v)
        return self._audio

    @property
    def effect_entries(self) -> dict:
        """effect name (lower case) → (entry, `Effect`) of ``effects.big``."""
        if self._fx is None:
            from ..formats.effect import read_all
            self._fx = {n.lower(): v for n, v in read_all(self.tree).items()}
        return self._fx

    @property
    def free_slots(self) -> list[tuple[int, str]]:
        """(number, name) of the effect table's free slots (`neweffect.free_slots`)."""
        if self._free is None:
            names = self.effect_entries
            self._free = [(i + 1, n) for i, n in enumerate(self.effects)
                          if n.lower() not in names]
        return self._free

    @property
    def pictures(self) -> dict[str, str]:
        """particle picture name (lower case, no ``.bct``) → its ``effects.tex`` entry."""
        if self._pictures is None:
            arc = self.tree.open_archive(self.tree.resolve(EFFECTS_TEX).vpath)
            self._pictures = {e.name.lower().removesuffix(".bct"): e.name for e in arc.entries}
        return self._pictures

    @property
    def strings(self) -> dict[int, str]:
        if self._en is None:
            from ..convert.strings import load_bank
            self._en = load_bank(self.tree, "en").strings
        return self._en

    def has_pack(self, name: str) -> bool:
        return f"{name.lower()}.big" in self.packs

    def pack_bytes(self, name: str) -> bytes:
        return self.tree.resolve(f"{STREAMED}/{name}.big").data()


_GAMES: dict[tuple[str, str], _Game] = {}


def _game(game: str, tree: AssetTree) -> _Game:
    key = (game, str(tree.root))
    if key not in _GAMES:
        _GAMES[key] = _Game(game, tree)
    return _GAMES[key]


def plan(src_tree: AssetTree, dst_tree: AssetTree, src: str, dst: str, item: str,
         mod_id: str = "import", taken_ids: set[int] | None = None,
         taken_cards: set[str] | None = None,
         taken_effects: dict[str, int] | None = None, used_slots: set[int] | None = None
         ) -> Plan:
    """What importing ``item`` (an ``items.txt`` name of ``src``) into ``dst`` does
    (module docstring). ``taken_effects``: effects the mod brought already (name → slot,
    reused); ``used_slots``: effect slots the mod uses already (`mod_effects`). Raises
    `Dr2Error` when it can't be done at all (no such item, or the target has an item of
    that name already)."""
    a, b = _game(src, src_tree), _game(dst, dst_tree)
    if item.lower() not in a.models.blocks:
        raise Dr2Error(f"{item!r} is not an item of {src.upper()}'s items.txt")
    if item.lower() in b.models.blocks:
        raise Dr2Error(f"{dst.upper()} already has an item named {item!r}: use its own")
    p = Plan(src, dst)
    p.effects = {k.lower(): v for k, v in (taken_effects or {}).items()}
    p.used_slots = set(used_slots or ()) | set(p.effects.values())
    ids = _IdPool(mod_id, set(b.strings), taken_ids or set())
    cards = set(taken_cards or ()) | {x.get("CardIndexNumber") for blk in b.models.blocks.values()
                                      for x in blk.walk() if x.cls == "cComboCardItem"}
    todo, seen = [a.models.blocks[item.lower()].name], set()
    while todo:
        name = todo.pop(0)
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        p.items.append(name)
        blk = a.models.blocks[name.lower()]
        if blk.cls in crossgame.unknown_classes(dst):
            raise Dr2Error(f"{name} is a {blk.cls}, a kind of item {dst.upper()}'s program "
                           f"doesn't know")
        p.blocks.append(_block(a, b, p, blk, name, ids, cards, todo, seen))
        _pack(a, b, p, name)
    return p


class _IdPool:
    def __init__(self, mod_id: str, game_ids: set[int], taken: set[int]):
        import zlib
        self.next = STRING_BASE + 100 * (zlib.crc32(mod_id.encode()) % 290)
        self.avoid = game_ids | taken

    def take(self) -> int:
        while self.next in self.avoid:
            self.next += 1
        self.avoid.add(self.next)
        return self.next


def _block(a: _Game, b: _Game, p: Plan, blk: Block, name: str, ids: _IdPool, cards: set,
           todo: list, seen: set) -> tuple[str, str, list, list]:
    """``(cls, name, props, children)`` of the block as the target gets it. A key whose
    value names a child block left out is left out too: the program would look that block
    up and find nothing (Case West's Impact Hammer: ``AttachmentItemName`` naming its
    ``cPropCharacterAttachmentItem``; Case Zero's program doesn't name that key, so there
    it is only tidy, but a key both programs know would not be)."""
    gone = {c.name.lower() for c in blk.children if c.name and
            (c.cls in crossgame.unknown_classes(b.game) or c.cls in DROP_CHILDREN)}
    props = []
    for pr in blk.props:
        where = f"{name}: {pr.key}"
        if pr.value.lower() in gone:
            p.log.append(Resolution(where, "dropped", f"it names {pr.value}, a block left out"))
            continue
        v = _value(a, b, p, pr.key, pr.value, where, ids, cards, todo, seen)
        if v is not None:
            props.append((pr.key, v))
    children = []
    for c in blk.children:
        where = f"{name}: {c.cls} {c.name}"
        if c.cls in crossgame.unknown_classes(b.game):
            p.log.append(Resolution(where, "dropped", f"{b.game.upper()}'s program doesn't "
                                                      f"know the class {c.cls}"))
            continue
        if c.cls in DROP_CHILDREN:
            p.log.append(Resolution(where, "dropped", DROP_CHILDREN[c.cls]))
            continue
        if c.cls == "cComboCardItem":
            missing = [w for k in ("Weapon_1", "Weapon_2") if (w := c.get(k))
                       and w.lower() not in b.models.blocks and w.lower() not in a.models.blocks]
            if missing:
                p.log.append(Resolution(where, "dropped", f"its items {missing} are in "
                                                          f"neither game"))
                continue
        children.append(_block(a, b, p, c, f"{name}/{c.name}", ids, cards, todo, seen))
    return (blk.cls, blk.name, props, children)


def _value(a: _Game, b: _Game, p: Plan, key: str, value: str, where: str, ids: _IdPool,
           cards: set, todo: list, seen: set) -> str | None:
    """The value ``key`` gets in the target, or None to leave the key out (logged)."""
    if ITEM_KEYS.match(key) and value:
        if value.lower() in b.models.blocks:
            p.log.append(Resolution(where, "kept", value))
            return value
        if value.lower() in a.models.blocks:
            if value.lower() not in seen and value not in todo:
                todo.append(a.models.blocks[value.lower()].name)
                p.log.append(Resolution(where, "brought", f"the item {value}"))
            return value
        p.log.append(Resolution(where, "dropped", f"{value} is an item of neither game"))
        return None
    if weapons.EFFECT_KEYS.match(key) and value.lstrip("-").isdigit():
        n = int(value)
        if n <= 0:
            return value
        if n > len(a.effects):
            p.unresolved.append(f"{where}: effect {n} is past {a.game.upper()}'s table")
            return None
        fx = a.effects[n - 1]
        low = [x.lower() for x in b.effects]
        if fx.lower() in low:
            m = low.index(fx.lower()) + 1
            p.log.append(Resolution(where, "renumbered" if m != n else "kept",
                                    f"{fx} {n} -> {m}" if m != n else fx))
            return str(m)
        return _bring_effect(a, b, p, fx, where)
    if STRING_KEYS.match(key) and value.isdigit() and int(value) in a.strings:
        new = ids.take()
        p.strings[new] = int(value)
        p.log.append(Resolution(where, "renumbered", f"text {value} -> {new} "
                                                     f"({a.strings[int(value)][:40]!r})"))
        return str(new)
    if key == "CardIndexNumber":
        k = value
        if k in cards:
            k = next(str(i) for i in range(1, 1000) if str(i) not in cards)
            p.log.append(Resolution(where, "renumbered", f"card {value} -> {k}"))
        cards.add(k)
        return k
    if key == "IconAsset" and value:
        for suffix in ("", "_no"):
            n = f"{value}{suffix}.bct"
            if n.lower() in b.cards:
                continue
            if n.lower() in a.cards:
                p.recipes[f"{CARDS}/{n}{COPY_EXT}"] = {"format": COPY_FORMAT, "from": a.game,
                                                       "copy": f"{CARDS}/{n}"}
                p.log.append(Resolution(where, "brought", f"card picture {n}"))
        return value
    if key == "PropAudioType" and value.isdigit():
        # a bit only the source game uses faults the target's load when the item is
        # placed (Case West's Impact Hammer, bit 17, in Case Zero: 2026-10-13)
        kept = int(value) & b.audio_bits
        if kept != int(value):
            p.log.append(Resolution(where, "renumbered",
                                    f"audio type {value} -> {kept} (bits {b.game.upper()}'s "
                                    f"program doesn't use: {int(value) & ~b.audio_bits:#x})"))
            return str(kept)
    if key == "AnimBankName" and value:
        _bring_pack(a, b, p, f"anm_{value}", where, "move bank")
        return value
    if key == "AudioFilename" and value:
        for n in (value, f"{value}_p"):
            if a.has_pack(n) or b.has_pack(n):
                _bring_pack(a, b, p, n, where, "sound bank")
        return value
    p.log.append(Resolution(where, "kept", value))
    return value


def _bring_effect(a: _Game, b: _Game, p: Plan, fx: str, where: str) -> str:
    """An effect the target lacks, brought into a free slot of its table (module
    docstring): the slot's number, or "0" (dropped) when none is left."""
    from .neweffect import OWN_ENTRY
    key = fx.lower()
    if key not in a.effect_entries:
        p.log.append(Resolution(where, "dropped", f"{fx}: {a.game.upper()}'s table names it "
                                                  f"but its effects.big has no such effect"))
        return "0"
    num = p.effects.get(key)
    if num is None:
        free = next(((n, s) for n, s in b.free_slots if n not in p.used_slots), None)
        if free is None:
            p.log.append(Resolution(where, "dropped", f"{b.game.upper()} has no effect {fx} "
                                                      f"and no free effect slot is left"))
            return "0"
        num = free[0]
        p.effects[key] = num
        p.used_slots.add(num)
    slot = b.effects[num - 1]
    path = f"{EFFECTS_BIG}/EFFECT_Common{OWN_ENTRY + num}{COPY_EXT}"
    if path not in p.recipes:
        entry, effect = a.effect_entries[key]
        p.recipes[path] = {"format": COPY_FORMAT, "from": a.game,
                           "copy": f"{EFFECTS_BIG}/{entry}",
                           "effect": {"from": effect.name, "name": slot, "changes": {}}}
        for em in effect.emitters:
            pic = em.texture.lower()
            if pic and pic not in b.pictures and pic in a.pictures:
                pp = f"{EFFECTS_TEX}/{pic}{COPY_EXT}"
                if pp not in p.recipes:
                    p.recipes[pp] = {"format": COPY_FORMAT, "from": a.game,
                                     "copy": f"{EFFECTS_TEX}/{a.pictures[pic]}"}
                    p.log.append(Resolution(where, "brought", f"particle picture {pic}"))
    p.log.append(Resolution(where, "brought", f"effect {fx} into the free slot {num} "
                                              f"({slot})"))
    return str(num)


def mod_effects(mod_dir: str | Path) -> tuple[dict[str, int], set[int]]:
    """(effects the mod brought from the other game: name → slot, every slot it uses)."""
    from .neweffect import own_effects
    brought, used = {}, set()
    for num, recipe in own_effects(mod_dir):
        used.add(num)
        if recipe.get("from") and (recipe.get("effect") or {}).get("from"):
            brought[recipe["effect"]["from"].lower()] = num
    return brought, used


def _bring_pack(a: _Game, b: _Game, p: Plan, name: str, where: str, what: str) -> None:
    path = f"{STREAMED}/{name}.big{COPY_EXT}"
    if b.has_pack(name) or path in p.recipes:
        p.log.append(Resolution(where, "kept", f"{what} {name}"))
        return
    if not a.has_pack(name):
        p.log.append(Resolution(where, "kept", f"{what} {name} (in neither game: the item "
                                               f"shipped without it)"))
        return
    p.recipes[path] = {"format": COPY_FORMAT, "from": a.game, "copy": f"{STREAMED}/{name}.big"}
    p.log.append(Resolution(where, "brought", f"{what} {name}"))


def _pack(a: _Game, b: _Game, p: Plan, item: str) -> None:
    """The item's model pack, with its shaders (`shadercarry`)."""
    from ..convert import shadercarry
    vp = a.models.resolve(item)
    if vp is None:
        p.log.append(Resolution(f"{item}: model", "kept",
                                f"none ({a.models.why.get(item.lower(), 'no model')})"))
        return
    parts = split(vp)
    base = len(split(STREAMED))
    if [x.lower() for x in parts[:base]] != [x.lower() for x in split(STREAMED)]:
        p.unresolved.append(f"{item}: its model {vp} is not a pack of {STREAMED}")
        return
    pack = parts[base][:-4]
    where = f"{item}: model"
    if b.has_pack(pack):
        if b.pack_bytes(pack) == a.pack_bytes(pack):
            p.log.append(Resolution(where, "kept", f"pack {pack} (the same in both)"))
            return
        p.log.append(Resolution(where, "kept", f"{b.game.upper()}'s own pack {pack} (the "
                                               f"same object; the two games' copies differ)"))
        return
    path = f"{STREAMED}/{pack}.big{COPY_EXT}"
    if path in p.recipes:
        return
    data = a.pack_bytes(pack)
    sd, ps = shadercarry.used_shaders(data)
    c = shadercarry.plan(a.tree, b.tree, a.game, b.game, sd, ps)
    recipe = {"format": COPY_FORMAT, "from": a.game, "copy": f"{STREAMED}/{pack}.big"}
    if c.sd or c.ps:
        recipe["shaders"] = c.to_json()
        for k, r in shadercarry.recipes(c, b.tree).items():
            p.recipes.setdefault(k, r)
        p.log.append(Resolution(where, "brought",
                                f"pack {pack} with its {a.game.upper()} shaders "
                                f"({len(c.sd)} descriptions, {len(c.vs)} vertex and "
                                f"{len(c.ps)} pixel shaders)"))
    else:
        p.log.append(Resolution(where, "brought", f"pack {pack}"))
    p.recipes[path] = recipe


def write(p: Plan, mod_dir: str | Path, dst_tree: AssetTree, base_dirs=()) -> list[Path]:
    """Write a `Plan` into a mod: its blocks (``items.txt.edits.json``), its recipes
    (``add/``), its text copies (every language's ``.bcs.json``), and ``[requires]``'s
    games. Returns the files written."""
    from ..convert import strings as cstr
    from .leveledit import TextEdits
    from .manifest import Mod
    if p.unresolved:
        raise Dr2Error("can't import: " + "; ".join(p.unresolved))
    root = Path(mod_dir)
    out = []
    for rel, recipe in p.recipes.items():
        f = root.joinpath(ADD_DIR, *split(rel))
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(recipe, indent=1) + "\n", "utf-8")
        out.append(f)
    s = TextEdits(mod_dir, "items.txt", dst_tree, base_dirs)
    for cls, name, props, children in p.blocks:
        if s.doc.get(f"{cls} {name}") is None:
            s.doc.add(None, cls, name, props, children)
    out.append(s.save())
    if p.strings:
        for lang in cstr.languages(dst_tree):
            if lang == "id":
                continue
            out.append(cstr.set_mod_copies(root, lang, {k: (p.src, v)
                                                        for k, v in p.strings.items()}))
    m = Mod.load(root)
    games = sorted(set(m.requires.get("games", [])) | {p.src, p.dst})
    if games != sorted(m.requires.get("games", [])):
        m.requires["games"] = games
        m.save()
    log = root / "sources" / "imported.json"
    log.parent.mkdir(parents=True, exist_ok=True)
    old = json.loads(log.read_text("utf-8")) if log.is_file() else {}
    old[p.items[0]] = {"from": p.src, "into": p.dst, "items": p.items,
                       "log": [r.__dict__ for r in p.log if r.how != "kept"]}
    log.write_text(json.dumps(old, indent=1) + "\n", "utf-8")
    return out + [log]


def taken_ids(mod_dir: str | Path) -> set[int]:
    """String ids the mod already uses (its ``.bcs.json`` files)."""
    from ..convert import strings as cstr
    out: set[int] = set()
    for lang in ("en",):
        out |= set(cstr.read_mod_strings(mod_dir, lang))
        out |= {int(k) for k in cstr.read_mod_copies(mod_dir, lang)}
    return out


def import_item(mod_dir: str | Path, item: str, src: str, dst: str, dst_tree: AssetTree,
                base_dirs=()) -> tuple[Plan, list[Path]]:
    """Plan and write (module docstring). The mod becomes a mod for ``dst``."""
    from .manifest import Mod
    m = Mod.load(mod_dir)
    brought, used = mod_effects(mod_dir)
    p = plan(crossgame.source_tree(src), dst_tree, src, dst, item, m.id, taken_ids(mod_dir),
             taken_effects=brought, used_slots=used)
    files = write(p, mod_dir, dst_tree, base_dirs)
    m = Mod.load(mod_dir)
    if tuple(m.games) != (dst,):
        m.games = (dst,)
        m.save()
    return p, files


def census(src_tree: AssetTree, dst_tree: AssetTree, src: str, dst: str) -> dict:
    """Plan every item of ``src`` the target lacks into ``dst`` (the importer's gate,
    ``dr2 census --import``): ``{"items", "planned", "refused": [...], "unresolved":
    [...], "how": {kept/brought/renumbered/dropped: n}, "dropped": {why: n}}``."""
    from collections import Counter
    a, b = _game(src, src_tree), _game(dst, dst_tree)
    names = [blk.name for k, blk in a.models.blocks.items() if k not in b.models.blocks]
    out = {"items": len(names), "planned": 0, "refused": [], "unresolved": [],
           "how": Counter(), "dropped": Counter()}
    for name in names:
        try:
            p = plan(src_tree, dst_tree, src, dst, name)
        except Dr2Error as e:
            out["refused"].append(f"{name}: {e}")
            continue
        out["planned"] += 1
        out["unresolved"] += [f"{name}: {u}" for u in p.unresolved]
        for r in p.log:
            out["how"][r.how] += 1
            if r.how == "dropped":
                out["dropped"][r.what.split(" (")[0][:60]] += 1
    out["how"], out["dropped"] = dict(out["how"]), dict(out["dropped"].most_common())
    return out

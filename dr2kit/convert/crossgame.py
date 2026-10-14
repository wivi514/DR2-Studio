"""Case West's things in Case Zero and the other way (phase 15, docs/phase15-kickoff.md).

Both games run the same engine and read the same formats, so models, textures, sounds and
animations cross over as they are; what differs is which **names** each game's program
and data know. This module answers "does the target know this name, and if not, what
happens to it", from two sources:

* ``dr2kit/profiles/crossgame.toml`` (made by ``tools/crossgame_table.py`` from both
  executables and both games' data, `table`): each program's zombie type table and level
  table, the script classes the other game uses that a program doesn't name, and the
  shader descriptions each game holds.
* the games' own data, read when needed (items, effects, move banks…).

`source_tree` opens the game a recipe copies from (``"from": "cw"``): a mod made from the
other game's files is built from the player's own copy of that game, so the mod still
holds no game data (`dr2kit.mods.requires` says the mod needs both games).

Facts and how they were found: docs/formats.md §Levels "Zombie types…", §"Across the
games".
"""

from __future__ import annotations

import tomllib
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from ..container.vpath import AssetTree
from ..errors import Dr2Error, GameNotFoundError


@lru_cache(maxsize=1)
def table() -> dict:
    """``crossgame.toml`` as a dict (module docstring)."""
    text = resources.files("dr2kit.profiles").joinpath("crossgame.toml").read_text("utf-8")
    return tomllib.loads(text)


def other(game: str) -> str:
    """The other game's id."""
    return {"cz": "cw", "cw": "cz"}[game]


def zombie_types(game: str) -> list[str]:
    """The program's zombie type table, in number order."""
    return list(table()[game]["zombie_types"])


def level_slots(game: str) -> list[str]:
    """The level table's script names (slot order); a name can repeat (``testlevel``)."""
    return list(table()[game]["levels"])


def empty_level_slots(game: str) -> list[str]:
    """Slots whose script the game doesn't ship (where a level of one's own can go),
    each name once, in slot order."""
    shipped = {s.lower() for s in table()[game]["levels_shipped"]}
    return list(dict.fromkeys(s for s in level_slots(game) if s.lower() not in shipped))


# Audio scenes a level loads with no file (measured in Case Zero, 2026-10-13: the empty
# slots main_menu, "MainMenu", and x_prologue, "Default", load and play; food_barn,
# "FoodBarn", stalls on the loading screen without data/audio/FoodBarn.txt and asserts
# "Bad file digest" with one, since the executable's digest list holds only the game's
# own files). Case West's w_mall and its cutscene sets are "Default" too.
NO_FILE_AUDIO = frozenset({"Default", "MainMenu"})


@dataclass(frozen=True)
class LevelSlot:
    """One slot of a program's level table (formats.md §Level slots): the level's name
    (``LEVEL_X_PROLOGUE``), its script (``x_prologue``: ``<script>.txt``,
    ``waypoint_<script>.txt``, ``nm_<script>.txt`` in ``datafile.big``), its zone list
    (``x_prologue/zonelist.big`` under ``data/models/environment``) and its audio scene."""
    game: str
    index: int
    level: str
    script: str
    zonelist: str
    audio: str
    shipped: bool

    @property
    def name(self) -> str:
        """The level name without ``LEVEL_``, as missions and ``cDoorPlacement`` write
        it (``X_PROLOGUE``)."""
        return self.level.removeprefix("LEVEL_")

    @property
    def loads(self) -> bool:
        """Can a level of one's own go here: the slot is empty and its audio scene needs
        no file or is one the game ships (`NO_FILE_AUDIO`)."""
        return not self.shipped and (self.audio in NO_FILE_AUDIO or
                                     self.audio in table()[self.game].get("audio_scenes", []))

    @property
    def why_not(self) -> str:
        if self.shipped:
            return f"{self.level} is one of the game's own levels"
        if not self.loads:
            return (f"{self.level}'s audio scene is {self.audio}: the game would load "
                    f"data/audio/{self.audio}.txt, which it doesn't ship and won't take from "
                    f"a mod (its digest is checked), so the level never finishes loading")
        return ""


def level_slot_list(game: str) -> list[LevelSlot]:
    """Every slot of ``game``'s level table, in slot order (`LevelSlot`)."""
    t = table()[game]
    shipped = {s.lower() for s in t["levels_shipped"]}
    return [LevelSlot(game, i, lv, s, zl, au, s.lower() in shipped)
            for i, (s, lv, zl, au) in enumerate(zip(t["levels"], t["level_ids"],
                                                    t["level_zonelists"], t["level_audio"]))]


def level_slot(game: str, name: str) -> LevelSlot:
    """The slot called ``name``: its level name with or without ``LEVEL_``
    (``LEVEL_X_PROLOGUE``, ``x_prologue``) or its script's name when no other slot
    shares it. `Dr2Error` otherwise."""
    key = name.strip().upper().removeprefix("LEVEL_")
    slots = level_slot_list(game)
    for s in slots:
        if s.name == key:
            return s
    by_script = [s for s in slots if s.script.lower() == name.strip().lower()]
    if len(by_script) == 1:
        return by_script[0]
    raise Dr2Error(f"{name!r} is not a level slot of {game.upper()}: "
                   f"dr2 level slots -g {game} lists them")


def free_level_slots(game: str, taken=()) -> list[LevelSlot]:
    """Slots a level of one's own can go into (`LevelSlot.loads`) whose script and zone
    list no slot in ``taken`` (slots or level names already used) shares, the ones that
    share neither with any other slot first. A script or zone list two slots share
    (``testlevel.txt``) holds one level for both."""
    used = [s if isinstance(s, LevelSlot) else level_slot(game, s) for s in taken]
    scripts = {s.script.lower() for s in used}
    zls = {s.zonelist.lower() for s in used}
    slots = level_slot_list(game)
    shared_s = Counter(s.script.lower() for s in slots)
    shared_z = Counter(s.zonelist.lower() for s in slots)
    out = [s for s in slots if s.loads and s.script.lower() not in scripts
           and s.zonelist.lower() not in zls]
    return sorted(out, key=lambda s: (shared_s[s.script.lower()] > 1 or
                                      shared_z[s.zonelist.lower()] > 1, s.index))


def unknown_classes(game: str) -> set[str]:
    """Script classes the other game's text files use that ``game``'s program doesn't
    name: a block of one of them can't be built in ``game``."""
    return set(table()[game]["classes_unknown"])


_TREES: dict[str, AssetTree] = {}


def source_tree(game: str, why: str = "") -> AssetTree:
    """The asset tree of ``game`` (a recipe's ``"from"``), or a `Dr2Error` saying the mod
    needs that game's data on this computer."""
    from ..profiles import load_profile, locate
    game = game.lower()
    if game not in _TREES:
        try:
            _TREES[game] = AssetTree(locate(game).root)
        except GameNotFoundError:
            name = load_profile(game).name
            raise Dr2Error(f"{why}{': ' if why else ''}made from {name}'s files, so it needs "
                           f"{name}'s game data on this computer (Game folders… in Studio, "
                           f"or dr2 games set {game} <folder>)") from None
    return _TREES[game]


# --- scenes the target's program reads differently ---------------------------------------

HIERARCHY = "_BONEHIERARCHY_"


def fit_scenes(data: bytes, game: str, name: str = "pack") -> bytes:
    """``data`` (a pack, scene archive or picture from the other game) made right for
    ``game``'s program: every texture gets the game's writer version (profile
    ``texture_version``, `_fit_texture`), and, when the profile says so
    (``scene_hierarchy``, Case Zero), every scene with nodes that lacks ``_BONEHIERARCHY_`` gets it, written from its node records
    (`Skeleton.hierarchy_pairs`) right after them, stored, declared alignment 4: where
    and how Case Zero's own scenes hold it.

    Why: Case West ships no scene with that chunk and its program copes; Case Zero's
    program walks a placed item's node parents through it (``sub_827ACAD8``) and, without
    it, never finishes: the load hangs on the loading screen (Laser Sword test U1,
    2026-10-12; docs/formats.md §Across the games). Unchanged bytes when nothing lacks it."""
    from ..profiles import load_profile
    prof = load_profile(game)
    from ..container.big import BigArchive, is_big
    from ..formats.bct import is_bct
    if is_bct(data[:4]):                                  # a loose picture
        return _fit_texture(data, prof.texture_version)
    if not is_big(data):
        return data
    arc = BigArchive.parse(data, name)
    return arc.to_bytes() if _fit(arc, name, prof) else data


def _fit_texture(data: bytes, version: int) -> bytes:
    """A ``.bct`` with the target's writer version at byte 9 (profile ``texture_version``:
    Case Zero draws a Case West texture, 0x24, as flat white; docs/formats.md
    §Textures, U1 2026-10-13)."""
    if not version or len(data) < 10 or data[9] == version:
        return data
    return data[:9] + bytes([version]) + data[10:]


def _fit(arc, where: str, prof) -> bool:
    from ..container.big import BigArchive, is_big
    from ..formats.bct import is_bct
    changed = False
    names = {e.name for e in arc.entries}
    if prof.scene_hierarchy and "SceneHeader" in names and HIERARCHY not in names:
        changed = _add_hierarchy(arc, where) or changed
    for e in arc.entries:
        data = e.data()
        if is_bct(data[:4]):
            new = _fit_texture(data, prof.texture_version)
            if new is not data:
                e.set_data(new)
                changed = True
        elif e.name.lower().endswith((".big", ".tex")) and is_big(data):
            try:
                inner = BigArchive.parse(data, e.name)
            except Exception:                                   # noqa: BLE001
                continue
            if _fit(inner, f"{where}/{e.name}", prof):
                e.set_data(inner.to_bytes())
                changed = True
    return changed


def _add_hierarchy(arc, where: str) -> bool:
    """Add ``_BONEHIERARCHY_`` to a scene with nodes (False: it has none). A scene with
    no node keeps none: Case Zero's ``ZONE_ORGANIZATION.big`` never has one, and an
    empty one made Case Zero ask its heap 0 for 256 MiB while a brought level loaded
    (Storage Pens, 2026-10-13); its 662 street pieces and 11 ``MERGED_COLLISION.big``
    all have one."""
    import struct
    from ..formats.scene import Scene
    sk = Scene.parse(arc.to_bytes(), where).skeleton
    if not sk.nodes:
        return False
    data = b"".join(struct.pack(">Ii", i, p) for i, p in sk.hierarchy_pairs())
    node_names = {n.name for n in sk.nodes}
    # after the last node record (Case Zero: nodes, then this chunk, then the data)
    at = max((k + 1 for k, e in enumerate(arc.entries) if e.name in node_names and
              e.size == 52), default=0)
    e = arc.add(HIERARCHY, data, flags=4, alignment=4)
    arc.entries.remove(e)
    arc.entries.insert(at, e)
    return True

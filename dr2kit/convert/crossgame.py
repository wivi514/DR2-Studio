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
    (``scene_hierarchy``, Case Zero), every scene that lacks ``_BONEHIERARCHY_`` gets it, written from its node records
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
        _add_hierarchy(arc, where)
        changed = True
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


def _add_hierarchy(arc, where: str) -> None:
    import struct
    from ..formats.scene import Scene
    sk = Scene.parse(arc.to_bytes(), where).skeleton
    data = b"".join(struct.pack(">Ii", i, p) for i, p in sk.hierarchy_pairs())
    node_names = {n.name for n in sk.nodes}
    # after the last node record (Case Zero: nodes, then this chunk, then the data)
    at = max((k + 1 for k, e in enumerate(arc.entries) if e.name in node_names and
              e.size == 52), default=0)
    e = arc.add(HIERARCHY, data, flags=4, alignment=4)
    arc.entries.remove(e)
    arc.entries.insert(at, e)

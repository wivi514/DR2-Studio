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

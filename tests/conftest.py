"""Shared test helpers.

Two kinds of tests (docs/dev/testing.md):

* **Unit tests** build tiny synthetic archives in code. They run everywhere, CI included.
  Never put real game files (or anything extracted from them) in tests: the data is
  copyrighted (CLAUDE.md).
* **Game-data tests** (marker ``gamedata``) read a real install found through the game
  profiles, and **skip with a message saying why** when the game isn't there.
"""

from __future__ import annotations

import pytest

from dr2kit.container.big import BigArchive, BigEntry, LZX, STORED
from dr2kit.errors import GameNotFoundError


def make_archive(*entries, alignment: int = 4) -> BigArchive:
    """Build an archive from ``(name, data)`` or ``(name, data, compression)`` tuples."""
    arc = BigArchive(source="<test>")
    for spec in entries:
        name, data, *rest = spec
        arc.add(name, data, compression=rest[0] if rest else STORED, alignment=alignment)
    return arc


@pytest.fixture
def game_root():
    """Return a function: ``game_root("cz")`` -> the data root, or skip saying why."""
    from dr2kit.profiles import locate

    def get(game: str):
        try:
            return locate(game).root
        except GameNotFoundError as e:
            pytest.skip(f"{game} game data not available: {e}")
    return get


__all__ = ["make_archive", "BigArchive", "BigEntry", "LZX", "STORED"]

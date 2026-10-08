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


def make_bct(fmt_name: str = "DXT1", width: int = 64, height: int = 64, levels: int = 1,
             cube: bool = False, fill=None) -> bytes:
    """A synthetic `.bct` texture: header built field by field, payload sized by the
    layout model and filled by ``fill(i) -> byte`` (default: a repeating pattern)."""
    from dr2kit.formats.bct import FORMATS, FLAG_ALWAYS, FLAG_CUBE, BctHeader, model_data_size
    fmt = next(f for f in FORMATS.values() if f.name == fmt_name)
    hdr = BctHeader(flags=0xE0 | FLAG_ALWAYS | (FLAG_CUBE if cube else 0), width=width,
                    height=height, format_code=fmt.code, version=0x23, levels=levels,
                    bpp=fmt.bpp, word_0c=0x12345660, depth_minus_1=5 if cube else 0)
    size = model_data_size(hdr)
    hdr.data_size, hdr.data_end = size, 0x30 + size
    fill = fill or (lambda i: (i * 37 + 11) & 0xFF)
    return hdr.to_bytes() + bytes(fill(i) for i in range(size))


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


__all__ = ["make_archive", "make_bct", "BigArchive", "BigEntry", "LZX", "STORED"]

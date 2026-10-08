"""The engine's 32-bit string hash.

The game looks archive entries up by this hash (it is stored next to each name in a
`.big` index), and passes items, props and events around as hashes of their names.

Algorithm, transcribed by the CZ recomp from the game's own code (``sub_8276E398``;
``tools/name_hash.py`` there): start at 0, and for each byte ``h = h * 33 ^ c``, where
``c`` is the byte as a **signed** char, with 32-bit wrap-around. It stops at a NUL.

For `.big` entries the hash is taken over the **lower-cased** name: true for every entry
of Case Zero and Case West, nested archives included (``dr2 census`` checks it).
"""

from __future__ import annotations


def name_hash(name: str | bytes) -> int:
    """Hash a name exactly as the engine does (no case folding; see `entry_hash`)."""
    raw = name.encode("latin-1") if isinstance(name, str) else name
    h = 0
    for ch in raw:
        if ch == 0:
            break
        c = ch - 256 if ch >= 128 else ch          # signed char
        h = ((h * 33) ^ (c & 0xFFFFFFFF)) & 0xFFFFFFFF
    return h


def entry_hash(name: str) -> int:
    """The hash a `.big` index stores for an entry called ``name`` (lower-cased first)."""
    return name_hash(name.lower())

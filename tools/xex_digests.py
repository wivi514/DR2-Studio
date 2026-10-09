"""List the files a game's executable checks against a SHA-1 digest.

Why: the games verify a few data files when they load them and crash on an edited copy
(an assert, "Bad file digest", in `digestmanager.cpp`). A mod must not touch those, so
the toolkit keeps the list in each game profile (`digest_checked` in cz.toml / cw.toml)
and `dr2 mod build` refuses them. This script is how that list was measured; run it
again if a game version changes.

Where the list is: the XEX's `Digest` resource (the resource table is optional header
`0x000002FF`: a size, then `{char name[8]; be32 address; be32 size}` entries). Its bytes
are only readable in the decrypted image, which a recomp keeps as
`assets/game/default_image.bin` (loaded at 0x82000000). Layout, measured on both games:

    be32 count
    count x { be32 key; u8 sha1[20] }

`key` is the engine's name hash (`dr2kit.hashing.name_hash`) of the path as the game
writes it (``data/audio/Prologue.txt``); `sha1` is SHA-1 over the file's bytes followed
by its length as a big-endian u32. The script hashes every loose file and every entry of
the game the same way and prints each match, plus any digest it could not match.

Usage: python tools/xex_digests.py <cz|cw> <default.xex> <default_image.bin>
"""

from __future__ import annotations

import hashlib
import struct
import sys

from dr2kit.container.vpath import AssetTree, entry_components, join
from dr2kit.hashing import name_hash

IMAGE_BASE = 0x82000000
RESOURCES = 0x000002FF


def digest_resource(xex: bytes) -> tuple[int, int]:
    """(address, size) of the `Digest` resource, from the XEX header."""
    count = struct.unpack_from(">I", xex, 20)[0]
    for k in range(count):
        key, value = struct.unpack_from(">II", xex, 24 + 8 * k)
        if key == RESOURCES:
            size = struct.unpack_from(">I", xex, value)[0]
            for e in range((size - 4) // 16):
                name, addr, n = struct.unpack_from(">8sII", xex, value + 4 + 16 * e)
                if name.rstrip(b"\0") == b"Digest":
                    return addr, n
    raise SystemExit("no Digest resource in this XEX")


def file_digest(data: bytes) -> bytes:
    h = hashlib.sha1(data)
    h.update(struct.pack(">I", len(data)))
    return h.digest()


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    game, xex_path, image_path = argv
    addr, size = digest_resource(open(xex_path, "rb").read())
    image = open(image_path, "rb").read()
    off = addr - IMAGE_BASE
    n = struct.unpack_from(">I", image, off)[0]
    if 4 + 24 * n != size:
        raise SystemExit(f"Digest resource is {size} bytes, {n} entries need {4 + 24 * n}")
    wanted = {image[off + 8 + 24 * k:off + 28 + 24 * k]:
              struct.unpack_from(">I", image, off + 4 + 24 * k)[0] for k in range(n)}
    print(f"{n} digest entries in {xex_path}")
    tree = AssetTree.for_game(game)
    found = {}
    for vp, path in tree.files():
        d = file_digest(path.read_bytes())
        if d in wanted:
            found[d] = vp
    for vp, arc, _ in tree.walk_archives():
        for comp, e in zip(entry_components(arc), arc.entries):
            d = file_digest(e.data())
            if d in wanted:
                found[d] = join(vp, comp)
    for d, key in wanted.items():
        vp = found.get(d)
        if vp is None:
            print(f"  {key:08x}  (no file of the game has this digest)")
        else:
            ok = "key = name hash" if name_hash(vp) & 0xFFFFFFFF == key else "key differs"
            print(f"  {key:08x}  {vp}  ({ok})")
    return 0 if len(found) == n else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

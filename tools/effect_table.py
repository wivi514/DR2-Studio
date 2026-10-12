"""Read the particle-effect table out of a game's executable image.

Why: every effect number of ``items.txt`` (``EffectOnVictim<n>``, ``EffectOnImpact<n>``,
``PyroEffect<n>``…) and of ``zombie_effects.txt`` is a 1-based index into a table of effect
names compiled into the executable (docs/formats.md §Weapons, "Effect numbers"). The
toolkit keeps the names as data (``dr2kit/catalog/effects.toml``, ``names``, read by ``dr2kit/catalog/weapons.py``) so the weapon
wizard can show "snowtrail_wpn_bs_1" instead of "215" without needing the executable.
This script is how that list was made, and how to check it again.

Input: a recomp's ``assets/game/default_image.bin`` (the executable's image, mapped at
``0x82000000``: file offset = address − ``0x82000000``).

The table: 12-byte big-endian records ``{u32 name address, u32, u32}``; both words read
``0xFFFFFFFF`` in the image (filled in at run time ❓). Found from the string
``fireextinguisher_wpn_dc_2`` (the Fire Extinguisher's ``PyroEffect 141``): the u32 holding
its address is a record's name field; records are walked back and forward while the name
field points at a printable string and the two words don't. CZ: 371 records at file
offset ``0x9D24F0``; CW: 414 at ``0x9E69A0``, the first 371 the same as CZ's.

Usage::

    python tools/effect_table.py ../Dead_Rising_2_Case_West_Xenon_Recomp/assets/game/default_image.bin
    python tools/effect_table.py <image> --check cz     # compare with effects.toml

Prints the ``names`` array for ``effects.toml``, or with ``--check`` whether the catalogue
agrees (exit 1 when not).
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

BASE = 0x82000000
KEY = b"fireextinguisher_wpn_dc_2"


def _cstr(img: bytes, addr: int) -> str | None:
    o = addr - BASE
    if not 0 <= o < len(img):
        return None
    end = img.find(b"\0", o)
    raw = img[o:end]
    if not raw or end - o > 80 or not all(32 <= c < 127 for c in raw):
        return None
    return raw.decode("ascii")


def _is_record(img: bytes, at: int) -> bool:
    if at < 0 or at + 12 > len(img):
        return False
    p, a, b = struct.unpack_from(">III", img, at)
    return _cstr(img, p) is not None and _cstr(img, a) is None and _cstr(img, b) is None


def effect_table(img: bytes) -> tuple[int, list[str]]:
    """(file offset of the first record, [effect name] in number order: number = index + 1)."""
    s = img.find(b"\0" + KEY + b"\0")
    if s < 0:
        raise SystemExit("effect name not found: not a DR2 CZ/CW image?")
    ptr = img.find(struct.pack(">I", BASE + s + 1))
    if ptr < 0 or not _is_record(img, ptr):
        raise SystemExit("no table record points at the effect name")
    first = ptr
    while _is_record(img, first - 12):
        first -= 12
    end = ptr
    while _is_record(img, end):
        end += 12
    names = [_cstr(img, struct.unpack_from(">I", img, at)[0]) for at in range(first, end, 12)]
    return first, names


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("image", type=Path, help="a recomp's assets/game/default_image.bin")
    ap.add_argument("--check", metavar="GAME", choices=("cz", "cw"),
                    help="compare with dr2kit/catalog/effects.toml for this game")
    args = ap.parse_args(argv)
    first, names = effect_table(args.image.read_bytes())
    if args.check:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from dr2kit.catalog import weapons as effects
        have = effects.names(args.check)
        if have == names:
            print(f"{args.check}: the catalogue's {len(have)} effect names match the image "
                  f"(table at file offset {first:#x})")
            return 0
        bad = next((i for i, (a, b) in enumerate(zip(have, names)) if a != b),
                   min(len(have), len(names)))
        print(f"{args.check}: DIFFERENT (catalogue {len(have)}, image {len(names)}; first "
              f"difference at number {bad + 1})")
        return 1
    print(f"# {len(names)} effects, table at file offset {first:#x}")
    print("names = [")
    for i in range(0, len(names), 4):
        print("  " + " ".join(f'"{n}",' for n in names[i:i + 4]))
    print("]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

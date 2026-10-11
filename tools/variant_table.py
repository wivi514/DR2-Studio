"""Read the zombie shape-group table and slot table out of a game's executable image.

Why: the game decides which shapes of a zombie it draws from the shapes' **names**,
through a table of name patterns compiled into the executable (docs/formats.md
§Variants). The toolkit keeps a copy of that table as data in each game profile
(``dr2kit/profiles/cz.toml``, ``cw.toml``, section ``[variants]``) so it never needs the
executable. This script is how that copy was made, and how to check it again.

Input: a recomp's ``assets/game/default_image.bin`` (the executable's image, mapped at
``0x82000000``: file offset = address − ``0x82000000``). It is not part of the game data
the toolkit reads, only of a recomp checkout.

* **Group table**: 53 records ``{u64 mask, u32 pattern address, u32 0}``, big-endian.
  Found from the string ``head1_*,chestupper_neck1*``: the u32 holding its address is a
  record's pattern field; records are walked back and forward from there. The loader
  (CZ ``sub_825AC588``) calls the classifier with this address and the count 53.
* **Slot table**: 7 rows of 7 u64 masks (heads, headwear, shirts, trousers, skirt, feet,
  tall boots; unused entries 0). CZ ``0x8208A2E0``, read by the same loader. Found here by
  building the expected bytes from the group table and searching for them.

Usage::

    python tools/variant_table.py ../Dead_Rising_2_Case_Zero_Xenon_Recomp/assets/game/default_image.bin
    python tools/variant_table.py <image> --check cz   # compare with the profile's copy

Prints the ``[variants]`` TOML for a profile, or with ``--check`` says whether the profile
agrees.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

BASE = 0x82000000
COUNT = 53
SLOT_ROWS = (("head", 0x10000, 5), ("headwear", 0x2000000, 5), ("shirt", 0x40000000, 6),
             ("pants", 0x2000000000, 7), ("skirt", 0x100000000000, 1),
             ("feet", 0x200000000000, 7), ("tallboots", 0x10000000000000, 1))


def _cstr(img: bytes, addr: int) -> str:
    o = addr - BASE
    return img[o:img.index(b"\0", o)].decode("ascii")


def group_table(img: bytes) -> tuple[int, list[tuple[int, str]]]:
    """(address of the first record, [(mask, pattern)] × 53)."""
    s = img.find(b"head1_*,chestupper_neck1*,")
    if s < 0:
        raise SystemExit("pattern string not found: not a DR2 CZ/CW image?")
    ptr = img.find(struct.pack(">I", BASE + s))
    if ptr < 0:
        raise SystemExit("no pointer to the pattern string")
    rec = ptr - 8                      # the record holding that pointer starts 8 bytes before
    while True:                        # walk back while the record before looks like one
        mask, p, z = struct.unpack_from(">QII", img, rec - 16)
        if z != 0 or not (BASE <= p < BASE + len(img)) or mask == 0:
            break
        rec -= 16
    out = []
    for i in range(COUNT):
        mask, p, z = struct.unpack_from(">QII", img, rec + 16 * i)
        out.append((mask, _cstr(img, p)))
    if out[0][1] != "head*,cap_neck*,cap_gas_neck*,cap_black_neck*":
        raise SystemExit(f"table start not recognised: {out[0][1]!r}")
    return rec + BASE, out


def slot_table(img: bytes) -> int:
    """Address of the 7×7 slot table (checked against `SLOT_ROWS`)."""
    want = b"".join(struct.pack(">7Q", *([first << i for i in range(n)] + [0] * (7 - n)))
                    for _, first, n in SLOT_ROWS)
    o = img.find(want)
    if o < 0:
        raise SystemExit("slot table not found")
    return o + BASE


def to_toml(group_addr: int, groups: list[tuple[int, str]], slot_addr: int) -> str:
    lines = ["[variants]",
             "# The game's shape-group table, copied from the executable by",
             "# tools/variant_table.py (docs/formats.md §Variants). Each entry: the mask bit",
             "# and the name patterns (comma list; each is a prefix, '*' ends it). A shape's",
             "# bits are the OR of every entry that matches; '*' only counts when none does.",
             f'group_table = "{group_addr:#010x}"',
             f'slot_table = "{slot_addr:#010x}"',
             "groups = ["]
    lines += [f'  ["{m:#x}", "{p}"],' for m, p in groups]
    lines.append("]")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("image", type=Path)
    ap.add_argument("--check", metavar="GAME", help="compare with this profile (cz or cw)")
    a = ap.parse_args(argv)
    img = a.image.read_bytes()
    gaddr, groups = group_table(img)
    saddr = slot_table(img)
    if a.check:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from dr2kit.profiles import load_profile
        prof = load_profile(a.check).variants
        same = ([(int(m, 16), p) for m, p in prof.get("groups", [])] == groups
                and int(prof.get("group_table", "0"), 16) == gaddr
                and int(prof.get("slot_table", "0"), 16) == saddr)
        print(f"{a.check}: {'the profile agrees with' if same else 'DIFFERS from'} "
              f"the image (groups at {gaddr:#x}, slots at {saddr:#x})")
        return 0 if same else 1
    sys.stdout.write(to_toml(gaddr, groups, saddr))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

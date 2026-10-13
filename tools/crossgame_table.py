"""Make (or check) ``dr2kit/profiles/crossgame.toml``: what each game's program and data
know that the other's doesn't (phase 15, docs/phase15-kickoff.md).

Why: putting Case West's things into Case Zero (and the other way) must never leave a
name the target game doesn't know: a zombie type its program has no slot for, a script
class it can't build, a shader its banks don't hold. Those lists are compiled into each
executable or spread over thousands of files, so this script reads them once and the
toolkit keeps them as data (like ``tools/effect_table.py`` for the effect table), read by
`dr2kit.convert.crossgame`.

What it reads, per game:

* **The zombie type table** (from the executable, ``default_image.bin``, mapped at
  ``0x82000000``): an array of pointers to type names starting at ``zombie_fat``, walked
  while the names are lower-case. The program holds two such arrays: the type table and a
  debug "override" list that has ``AverageNormalZombie`` next to it (CZ before its first
  name, CW after its last); the type table is the other one. CZ: 32 at ``0x829DF688``;
  CW: 10 at ``0x829F2598`` (formats.md §Levels "Zombie types").
* **The level table**: the array of pointers to the levels' script names (``*.txt``)
  holding ``safehouse.txt``, and the zone-list array that follows it in Case Zero (82
  slots, ``0x829D4DFC`` / ``0x829D5F7C``); Case West's script names at ``0x829EED1C``
  (10). A slot is **shipped** when its script is in ``datafile.big``, else **empty**.
* **Script classes**: every block class of every text file of either game's
  ``datafile.big``, and whether this program names it (the string ``cName`` with a NUL
  after it): a class the target's program lacks can't be built there.
* **Shaders** (from the data): every shader description (``data/shaders/*-sd.big``
  entries, ``<hash>.sdo``) and the names models give them (``UsedShaders.txt`` of every
  scene). A model brought from the other game draws with **its own game's** shaders,
  copied into the target's banks (decision 2, user 2026-10-12: "the proper Case West
  shader"; `dr2kit.convert.crossgame`), so this list is for reports: which names the
  target already has.

Usage::

    python tools/crossgame_table.py                  # write crossgame.toml (~2 min)
    python tools/crossgame_table.py --check          # compare with it (exit 1 if not)

The games are found the way the toolkit finds them (``dr2 games``); the executables are
each recomp's ``assets/game/default_image.bin``.
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

BASE = 0x82000000
OUT = Path(__file__).resolve().parents[1] / "dr2kit" / "profiles" / "crossgame.toml"

def _cstr(img: bytes, addr: int) -> str | None:
    o = addr - BASE
    if not 0 <= o < len(img):
        return None
    end = img.find(b"\0", o)
    raw = img[o:end]
    if not raw or end - o > 100 or not all(32 <= c < 127 for c in raw):
        return None
    return raw.decode("ascii")


def _ptr(img: bytes, at: int) -> str | None:
    return _cstr(img, struct.unpack_from(">I", img, at)[0]) if 0 <= at <= len(img) - 4 else None


def _pointers_to(img: bytes, text: bytes) -> list[int]:
    out, s = [], -1
    while (s := img.find(b"\0" + text + b"\0", s + 1)) >= 0:
        target = struct.pack(">I", BASE + s + 1)
        p = -1
        while (p := img.find(target, p + 1)) >= 0:
            if p % 4 == 0:
                out.append(p)
    return out


def _names(img: bytes, name: str) -> bool:
    """Does the program hold ``name`` as a whole word (class names sit in string pools,
    in ``sizeof(cName)`` texts, not always after a NUL)?"""
    return re.search(rb"(?<![A-Za-z0-9_])" + re.escape(name.encode()) + rb"(?![A-Za-z0-9_])",
                     img) is not None


def code_refs(img: bytes, addr: int) -> int:
    """How many times the code builds ``addr`` (``lis rX, ha`` then, within 8
    instructions, ``addi``/``lwz``… ``rY, lo(rX)``): how a table the program walks is told
    from a debug menu's copy of the same names."""
    ha, lo = ((addr + 0x8000) >> 16) & 0xFFFF, addr & 0xFFFF
    n, at = 0, 0
    lis = re.compile(rb"[\x3c-\x3f][\x00-\xff]" + re.escape(struct.pack(">H", ha)), re.S)
    for m in lis.finditer(img):
        at = m.start()
        if at % 4 or (img[at] >> 2) != 15 or (struct.unpack_from(">I", img, at)[0] >> 16) & 0x1F:
            continue                                    # lis = addis rX, 0, ha
        rx = (struct.unpack_from(">I", img, at)[0] >> 21) & 0x1F
        for k in range(1, 9):
            w = struct.unpack_from(">I", img, at + 4 * k)[0] if at + 4 * k + 4 <= len(img) else 0
            if (w >> 16) & 0x1F == rx and w & 0xFFFF == lo and (w >> 26) in (14, 32, 34, 40, 48):
                n += 1
                break
    return n


def zombie_types(img: bytes) -> tuple[int, list[str]]:
    """(address, names) of the program's zombie type table (module docstring): of the
    arrays of type names starting at ``zombie_fat``, the one the code builds the address
    of (a debug menu holds the names too)."""
    lower = re.compile(r"^[a-z][a-z0-9_]*$")
    found = []
    for p in _pointers_to(img, b"zombie_fat"):
        names, at = [], p
        while (s := _ptr(img, at)) and lower.match(s):
            names.append(s)
            at += 4
        if _ptr(img, p - 4) == "AverageNormalZombie" or _ptr(img, at) == "AverageNormalZombie":
            continue                                    # the debug override list
        if len(names) >= 5:
            found.append((code_refs(img, BASE + p), BASE + p, names))
    if not found:
        raise SystemExit("zombie type table not found: not a DR2 CZ/CW image?")
    refs, addr, names = max(found)
    if not refs:
        raise SystemExit("no code builds the address of a zombie type array")
    return addr, names


def level_table(img: bytes) -> tuple[int, list[str], list[str]]:
    """(address, script names, zone lists) of the level table (zone lists: Case Zero's
    second array, [] when the program keeps them elsewhere)."""
    best = None
    for p in _pointers_to(img, b"safehouse.txt"):
        first = p
        while (s := _ptr(img, first - 4)) and s.endswith(".txt"):
            first -= 4
        names, at = [], first
        while (s := _ptr(img, at)) and s.endswith(".txt"):
            names.append(s)
            at += 4
        if best is None or len(names) > len(best[1]) or \
                (len(names) == len(best[1]) and first < best[0] - BASE):
            best = (BASE + first, names, at)
    if best is None:
        raise SystemExit("level table not found")
    zl, at = [], best[2]
    while (s := _ptr(img, at)) and "zonelist" in s:
        zl.append(s)
        at += 4
    if len(zl) != len(best[1]):
        zl = []
    return best[0], best[1], zl


def _games():
    from dr2kit.container.vpath import AssetTree
    from dr2kit.profiles import locate
    out = {}
    for g in ("cz", "cw"):
        loc = locate(g)
        img = loc.root / "default_image.bin"
        if not img.is_file():
            raise SystemExit(f"{img}: missing (the recomp's executable image)")
        out[g] = (AssetTree(loc.root), img.read_bytes())
    return out


def script_classes(tree) -> set[str]:
    from dr2kit.formats.levelscript import Document
    arc = tree.open_archive("data/datafile.big")
    out = set()
    for e in arc.entries:
        if not e.name.lower().endswith(".txt"):
            continue
        try:
            doc = Document.parse(e.data(), e.name)
        except Exception:                          # noqa: BLE001 - not a block file
            continue
        for b in doc.blocks:
            for x in b.walk():
                if re.match(r"^c[A-Z]\w+$", x.cls):
                    out.add(x.cls)
    return out


def shaders(tree) -> tuple[set[int], dict[str, set[int]]]:
    """(description hashes in the game's -sd banks, name -> hashes models give it)."""
    have = set()
    folder = tree.root / "data" / "shaders"
    for p in folder.iterdir():
        if p.name.lower().endswith("-sd.big"):
            for e in tree.open_archive(f"data/shaders/{p.name}").entries:
                m = re.match(r"^([0-9a-f]{8})\.sdo$", e.name.lower())
                if m:
                    have.add(int(m.group(1), 16))
    names: dict[str, set[int]] = {}
    for vp, arc, _ in tree.walk_archives(on_error=lambda *a: None):
        for e in arc.entries:
            if e.name.lower() != "usedshaders.txt":
                continue
            for line in e.data().decode("latin-1").splitlines():
                m = re.match(r"\s*0x([0-9A-Fa-f]{1,8})\s*:\s*(\S+)", line)
                if m:
                    names.setdefault(m.group(2), set()).add(int(m.group(1), 16))
    return have, names


def build() -> str:
    games = _games()
    lines = ["# What each game's program and data know (phase 15). Made by",
             "# tools/crossgame_table.py from both recomps' default_image.bin and data; check:",
             "# python tools/crossgame_table.py --check. Read by dr2kit/convert/crossgame.py.",
             "#",
             "# zombie_types   the program's zombie type table, in number order (a type is a",
             "#                model name of data/models/zombies.big)",
             "# levels         the level table's script names, in slot order; level_zonelists",
             "#                the zone list each slot loads (Case Zero only: Case West keeps",
             "#                them elsewhere); levels_shipped the slots whose script ships",
             "# classes_unknown  block classes the OTHER game's text files use that this",
             "#                program doesn't name: they can't be built here",
             "# shaders        name = hash of every shader description this game holds (that",
             "#                models of either game name)",
             ""]
    classes = {g: script_classes(t) for g, (t, _) in games.items()}
    sh = {g: shaders(t) for g, (t, _) in games.items()}
    for g, (tree, img) in games.items():
        za, zt = zombie_types(img)
        la, lv, zl = level_table(img)
        dfnames = {e.name.lower() for e in tree.open_archive("data/datafile.big").entries}
        shipped = sorted({s for s in lv if s.lower() in dfnames})
        other = "cw" if g == "cz" else "cz"
        unknown = sorted(c for c in classes[other] if not _names(img, c))
        have = sh[g][0]
        names: dict[str, set[int]] = {}                 # both games' models' names
        for _, nm in sh.values():
            for n, h in nm.items():
                names.setdefault(n, set()).update(h)
        own = {n: sorted(h & have)[0] for n, h in sorted(names.items()) if h & have}
        lines += [f"[{g}]",
                  f"zombie_table = 0x{za:08X}",
                  "zombie_types = [" + ", ".join(f'"{n}"' for n in zt) + "]",
                  f"level_table = 0x{la:08X}",
                  "levels = [" + ", ".join(f'"{n[:-4]}"' for n in lv) + "]",
                  "levels_shipped = [" + ", ".join(f'"{n[:-4]}"' for n in shipped) + "]"]
        if zl:
            lines.append("level_zonelists = [" + ", ".join(f'"{n}"' for n in zl) + "]")
        lines.append("classes_unknown = [" + ", ".join(f'"{c}"' for c in unknown) + "]")
        lines.append(f"[{g}.shaders]")
        lines += [f'"{n}" = 0x{h:08X}' for n, h in own.items()]
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="compare with crossgame.toml")
    a = ap.parse_args(argv)
    text = build()
    if a.check:
        same = OUT.is_file() and OUT.read_text("utf-8") == text
        print("crossgame.toml matches the games" if same else "crossgame.toml differs")
        return 0 if same else 1
    OUT.write_text(text, "utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

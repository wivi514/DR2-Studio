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
  holding ``safehouse.txt`` (Case Zero 82 slots at ``0x829D4DFC``, Case West 10), the
  array of zone lists in the same order (`zone_lists`), the level names (`level_ids`:
  ``LEVEL_LIGHTINGTEST`` is ``lighting.txt``), and each slot's **audio scene**
  (`level_audio`, read from the switch that hands it to the audio manager). A slot is
  **shipped** when its script is in ``datafile.big``, else **empty**; an empty slot
  loads only when its audio scene is one the game ships or needs no file
  (`dr2kit.convert.crossgame.level_slot`, formats.md §Level slots).
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
    return best[0], best[1], zone_lists(img, len(best[1]))


def zone_lists(img: bytes, count: int) -> list[str]:
    """The zone list each slot loads (relative to ``data/models/environment/``), slot
    order: the run of ``count`` pointers to ``…zonelist….big`` names (Case Zero
    ``0x829D5F7C``; Case West keeps one too). [] when there is none."""
    for p in _pointers_to(img, b"safehouse/zonelist.big") + \
            _pointers_to(img, b"living_research/zonelist.big"):
        first = p
        while (s := _ptr(img, first - 4)) and "zonelist" in s:
            first -= 4
        out, at = [], first
        while (s := _ptr(img, at)) and "zonelist" in s:
            out.append(s)
            at += 4
        if len(out) == count:
            return out
    return []


def level_ids(img: bytes, count: int) -> list[str]:
    """The level enum's names (``LEVEL_PROLOGUE``…) in slot order: the program keeps them
    as one run of strings, the slots' names from the last to the first (``LEVEL_NONE``
    stands apart; both games, 2026-10-13). A door's ``Level`` and a mission's ``LevelName`` are
    these names; they are not always ``LEVEL_`` + the script's name
    (``LEVEL_LIGHTINGTEST`` is ``lighting.txt``, ``LEVEL_MADHATTER`` ``gs_hattrick.txt``)."""
    for m in re.finditer(rb"\0(LEVEL_[A-Z0-9_]+)\0", img):
        names, o = [], m.start() + 1
        while len(names) < count and img.startswith(b"LEVEL_", o):
            end = img.find(b"\0", o)
            names.append(img[o:end].decode("ascii"))
            o = end
            while img[o] == 0:
                o += 1
        if len(names) == count and "LEVEL_NONE" not in names:
            return names[::-1]
    raise SystemExit("the level names (one run of LEVEL_ strings, one per slot) were not "
                     "found")


def _word(img: bytes, at: int) -> int:
    return struct.unpack_from(">I", img, at)[0]


def _lis_addi(img: bytes, at: int, reg: int | None = None) -> str | None:
    """The string ``lis rX, hi`` at ``at`` and ``addi rY, rX, lo`` right after build."""
    a, b = _word(img, at), _word(img, at + 4)
    if a >> 26 != 15 or b >> 26 != 14 or (b >> 16) & 0x1F != (a >> 21) & 0x1F:
        return None
    if reg is not None and (b >> 21) & 0x1F != reg:
        return None
    lo = b & 0xFFFF
    return _cstr(img, ((a & 0xFFFF) << 16) + (lo - 0x10000 if lo & 0x8000 else lo))


def level_audio(img: bytes, count: int) -> list[str]:
    """Each slot's **audio scene** (slot order): the name the program gives the audio
    manager when the level loads, which then reads ``data/audio/<name>.txt`` and checks
    that file's digest (formats.md §Level slots "audio scene"). Read from the switch that
    passes the names in ``r5`` (with ``r4 = 2``): Case Zero's is a jump table on
    ``level - 1`` (``addi r11,r4,-1; cmplwi cr6,r11,N; bgt default; …lbzx; …bctr``),
    Case West's a run of ``cmpwi cr6,r4,K; beq`` (each case: ``lis``, ``addi r5``).
    Found by the code that builds ``MainMenu`` into ``r5``. Slots past the switch get its
    default (``Default``)."""
    target = img.find(b"\0MainMenu\0") + 1
    if target <= 0:
        raise SystemExit("MainMenu not found")
    sites = [o for o in range(0, len(img) - 8, 4)
             if _lis_addi(img, o, 5) == "MainMenu"]
    for site in sites:
        for o in range(site, max(site - 1600, 0), -4):
            w = _word(img, o)
            if w == 0x396BFFFF or w == 0x3964FFFF:            # addi r11,r4,-1
                out = _jump_table(img, o, count)
            elif w == 0x2F040001:                              # cmpwi cr6,r4,1
                out = _compare_chain(img, o, count)
            else:
                continue
            if out and "MainMenu" in out:
                return out
    raise SystemExit("the level audio switch was not found")


def _first_r5(img: bytes, at: int) -> str | None:
    """The first string a ``lis rX`` + ``addi r5, rX`` pair (up to 3 instructions apart)
    builds from ``at`` on (Case Zero's ``YucatanCasino`` case has ``li r4,2`` between)."""
    for k in range(0, 40, 4):
        a = _word(img, at + k)
        if a >> 26 != 15:
            continue
        for j in range(4, 16, 4):
            b = _word(img, at + k + j)
            if b >> 26 == 14 and (b >> 21) & 0x1F == 5 and (b >> 16) & 0x1F == (a >> 21) & 0x1F:
                lo = b & 0xFFFF
                return _cstr(img, ((a & 0xFFFF) << 16) + (lo - 0x10000 if lo & 0x8000 else lo))
    return None


def _jump_table(img: bytes, at: int, count: int) -> list[str] | None:
    cmp, bgt = _word(img, at + 4), _word(img, at + 8)
    if cmp >> 16 != 0x2B0B or bgt >> 26 != 16:
        return None
    n = (cmp & 0xFFFF) + 1
    default = _first_r5(img, at + 8 + ((bgt & 0xFFFC) - (0x10000 if bgt & 0x8000 else 0)))
    tab = _lis_addi(img, at + 12)
    hi, lo = _word(img, at + 12), _word(img, at + 16)
    lo = lo & 0xFFFF
    table = ((hi & 0xFFFF) << 16) + (lo - 0x10000 if lo & 0x8000 else lo) - BASE
    for k in range(20, 60, 4):                                 # the case code's base
        a = _word(img, at + k)
        if a >> 26 == 15 and (a >> 21) & 0x1F == 12 and k > 24:
            b = next(_word(img, at + j) for j in range(k + 4, k + 16, 4)
                     if _word(img, at + j) >> 26 == 14)
            lo = b & 0xFFFF
            base = ((a & 0xFFFF) << 16) + (lo - 0x10000 if lo & 0x8000 else lo) - BASE
            break
    else:
        return None
    del tab
    out = []
    for i in range(count):
        out.append(_first_r5(img, base + 4 * img[table + i]) if i < n else default)
    return out if all(out) else None


def _compare_chain(img: bytes, at: int, count: int) -> list[str] | None:
    cases, o = {}, at
    while True:
        c, b = _word(img, o), _word(img, o + 4)
        if c >> 16 != 0x2F04 or b >> 26 != 16:
            break
        cases[c & 0xFFFF] = _first_r5(img, o + 4 + ((b & 0xFFFC) - (0x10000 if b & 0x8000 else 0)))
        o += 8
    default = _first_r5(img, o)
    if not cases or not default:
        return None
    return [cases.get(i + 1) or default for i in range(count)]


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
             "#                the zone list each slot loads (under data/models/environment);",
             "#                levels_shipped the slots whose script ships; level_ids the",
             "#                slots' level names (a door's Level); level_audio each slot's",
             "#                audio scene (data/audio/<name>.txt, digest-checked);",
             "#                audio_scenes the audio scene files the game ships",
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
        lines.append("level_ids = [" + ", ".join(f'"{n}"' for n in level_ids(img, len(lv)))
                     + "]")
        lines.append("level_audio = [" + ", ".join(f'"{n}"' for n in level_audio(img, len(lv)))
                     + "]")
        audio = tree.root / "data" / "audio"
        lines.append("audio_scenes = [" + ", ".join(
            f'"{f.stem}"' for f in sorted(audio.iterdir(), key=lambda f: f.name.lower())
            if f.suffix.lower() == ".txt" and f.stem[:1].isupper()) + "]")
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

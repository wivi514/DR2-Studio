"""The ``dr2`` command: list, search, extract and census the games' archives.

Every command is a thin layer over `dr2kit`; no format knowledge lives here. Each
subcommand has a ``cmd_<name>`` function; `build_parser` wires them up. Run
``dr2 <command> --help`` for the options, or read docs/modding/02-game-data.md for a
guided tour.

Exit codes: 0 success, 1 an error or a census that found problems, 2 bad usage.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

from .. import __version__
from ..errors import Dr2Error
from ..profiles import GAME_IDS, config_path, find_packages, locate, set_game_root


def _tree(args):
    from ..container.vpath import AssetTree
    return AssetTree.for_game(args.game)


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


# ---- doctor / games -------------------------------------------------------------------

def cmd_doctor(args) -> int:
    """Print what the toolkit sees: versions, LZX decoder, config, games."""
    from ..container import lzx
    print(f"dr2kit {__version__} on Python {platform.python_version()} "
          f"({platform.system()} {platform.machine()})")
    print(f"LZX decoder: {lzx.backend_detail()}")
    print(f"config file: {config_path()}")
    return cmd_games(args)


def cmd_games(args) -> int:
    """List each game and where its data was found; or `set` a folder for one."""
    if getattr(args, "action", None) == "set":
        root = set_game_root(args.set_game, args.folder)
        print(f"{args.set_game}: using {root}  (saved in {config_path()})")
        return 0
    for g in GAME_IDS:
        try:
            loc = locate(g)
            print(f"{g}: {loc.profile.name}: {loc.root}  (found via {loc.how})")
        except Dr2Error as e:
            print(f"{g}: {e}")
        for p in find_packages(g):
            print(f"    XBLA package: {p}")
    return 0


# ---- ls / find --------------------------------------------------------------------------

def cmd_ls(args) -> int:
    """List a folder, or the entries of an archive (on disk or nested)."""
    from ..container.vpath import entry_components, join
    tree = _tree(args)
    node = tree.resolve(args.vpath)
    if node.kind == "dir":
        for child in sorted(node.path.iterdir(), key=lambda p: p.name.lower()):
            if child.is_symlink():
                continue
            mark = "/" if child.is_dir() else ""
            size = "" if child.is_dir() else _human(child.stat().st_size)
            print(f"{size:>10}  {join(node.vpath, child.name)}{mark}")
        return 0
    arc = tree.open_archive(node.vpath)
    print(f"{node.vpath}: {len(arc)} entries")
    if args.long:
        print(f"{'#':>5} {'stored':>10} {'size':>10} {'flags':>6} {'comp':>4} {'hash':>8}  name")
    for i, (comp, e) in enumerate(zip(entry_components(arc), arc.entries)):
        if args.long:
            print(f"{i:>5} {e.size:>10} {e.size2:>10} {e.flags:>#6x} {e.compression:>4} "
                  f"{e.hash:08X}  {comp}")
        else:
            packed = "  (compressed)" if e.compressed else ""
            print(f"{_human(e.size2):>10}  {join(node.vpath, comp)}{packed}")
    return 0


def cmd_find(args) -> int:
    """Search every archive (nested too) for entry names containing some text."""
    from ..container.vpath import entry_components, join
    tree = _tree(args)
    needle = args.text.lower()
    hits = 0
    failed = []
    for vp, arc, _ in tree.walk_archives(on_error=lambda v, e: failed.append((v, e))):
        for comp, e in zip(entry_components(arc), arc.entries):
            if needle in e.name.lower():
                hits += 1
                print(f"{_human(e.size2):>10}  {join(vp, comp)}")
    print(f"{hits} entries match {args.text!r}", file=sys.stderr)
    if failed:
        # Named, never silent: a search that could not open an archive can't speak for it.
        print(f"{len(failed)} archives could not be read, so they were NOT searched:",
              file=sys.stderr)
        for vp, e in failed:
            print(f"    {vp}: {e}", file=sys.stderr)
        return 1
    return 0


# ---- extract --------------------------------------------------------------------------

def cmd_extract(args) -> int:
    """Write entries (or whole archives, with --recursive) to a folder."""
    from ..container.big import is_big
    from ..container.vpath import entry_components, join
    tree = _tree(args)
    out = Path(args.out)
    written = 0

    def write(vpath: str, data: bytes) -> None:
        nonlocal written
        dest = out.joinpath(*vpath.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        written += 1
        if not args.quiet:
            print(f"{_human(len(data)):>10}  {dest}")

    def expand(vpath: str, data: bytes) -> None:
        """Write an archive's entries under a folder named after the archive."""
        from ..container.big import BigArchive
        arc = BigArchive.parse(data, vpath)
        for comp, e in zip(entry_components(arc), arc.entries):
            sub = join(vpath, comp)
            data = e.data()
            if args.recursive and is_big(data):
                expand(sub, data)
            else:
                write(sub, e.stored if args.raw else data)

    for vp in args.vpaths:
        node = tree.resolve(vp)
        if node.kind == "dir":
            raise Dr2Error(f"{node.vpath} is a folder; give a file or entry")
        data = node.data()
        if args.recursive and is_big(data):
            expand(node.vpath, data)
            continue
        if node.kind == "entry" and args.raw and node.entry.compressed:
            print(f"note: {node.vpath} is compressed and --raw keeps it that way: "
                  f"what is written is the LZX stream, not the asset", file=sys.stderr)
            data = node.entry.stored
        write(node.vpath, data)
    print(f"wrote {written} file{'' if written == 1 else 's'} under {out}", file=sys.stderr)
    return 0


# ---- census ---------------------------------------------------------------------------

def cmd_census(args) -> int:
    """Read every archive and entry of one or both games; report and run the gates."""
    from ..census import format_report, run_census
    from ..container.vpath import AssetTree
    games = list(GAME_IDS) if args.games in ([], ["all"]) else args.games
    reports = []
    for g in games:
        tree = AssetTree(locate(g).root)
        progress = None if args.quiet else (lambda vp: print(f"  {vp}", file=sys.stderr))
        rep = run_census(g, tree, python_lzx=args.python_lzx, reencode=args.reencode,
                         workers=args.workers, progress=progress)
        print(format_report(rep))
        reports.append(rep)
    if args.json:
        Path(args.json).write_text(json.dumps([r.to_json() for r in reports], indent=1))
    return 1 if any(r.problems for r in reports) else 0


# ---- unpack ---------------------------------------------------------------------------

def cmd_unpack(args) -> int:
    """Unpack an XBLA package (STFS) into a folder, or list what it holds."""
    from ..container.stfs import Package, unpack
    with Package(args.package) as pkg:
        print(pkg.describe(), file=sys.stderr)
        if args.list or not args.out:
            for name in sorted(pkg.files):
                print(f"{pkg.files[name][0]:>12,}  {name}")
            return 0
    n, size = unpack(args.package, args.out, args.only or None,
                     progress=None if args.quiet else
                     (lambda name, sz: print(f"{sz:>12,}  {name}")))
    print(f"extracted {n} files, {size:,} bytes -> {args.out}", file=sys.stderr)
    print(f"next: dr2 games set <cz|cw> {args.out}", file=sys.stderr)
    return 0


# ---- wiring ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="dr2", description="Dead Rising 2: Case Zero / Case West modding toolkit.")
    ap.add_argument("--version", action="version", version=f"dr2kit {__version__}")
    sub = ap.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def game_opt(p):
        p.add_argument("-g", "--game", default="cz", choices=GAME_IDS,
                       help="which game (default: cz)")

    p = sub.add_parser("doctor", help="show versions, the LZX decoder in use, and the games found")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("games", help="show where each game's data is, or set it")
    gsub = p.add_subparsers(dest="action")
    ps = gsub.add_parser("set", help="use this folder for a game")
    ps.add_argument("set_game", choices=GAME_IDS, metavar="GAME")
    ps.add_argument("folder", help="the folder that contains data/ (or data/ itself)")
    p.set_defaults(func=cmd_games)

    p = sub.add_parser("ls", help="list a folder or an archive's entries")
    p.add_argument("vpath", nargs="?", default="data", help="virtual path (default: data)")
    p.add_argument("-l", "--long", action="store_true",
                   help="index details: stored size, size, flags, compression, hash")
    game_opt(p)
    p.set_defaults(func=cmd_ls)

    p = sub.add_parser("find", help="search entry names in every archive (nested too)")
    p.add_argument("text", help="part of a name, any case")
    game_opt(p)
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("extract", help="write entries to a folder (decompressed)")
    p.add_argument("vpaths", nargs="+", metavar="VPATH")
    p.add_argument("-o", "--out", default="extracted", help="output folder (default: extracted)")
    p.add_argument("-r", "--recursive", action="store_true",
                   help="unpack archives into folders, nested ones too")
    p.add_argument("--decompress", action="store_true",
                   help="decompress compressed entries (the default; kept for clarity)")
    p.add_argument("--raw", action="store_true",
                   help="write compressed entries as stored (the LZX stream), not decoded")
    p.add_argument("-q", "--quiet", action="store_true")
    game_opt(p)
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("census", help="read everything, report it, and run the format gates")
    p.add_argument("games", nargs="*", choices=[*GAME_IDS, "all"], metavar="GAME",
                   help="cz, cw or all (default: all)")
    p.add_argument("--json", help="also write the full report as JSON to this file")
    p.add_argument("--reencode", action="store_true",
                   help="also re-encode every compressed entry and decode it back (slow)")
    p.add_argument("--python-lzx", action="store_true",
                   help="also decode every compressed entry with the pure-Python decoder")
    p.add_argument("--workers", type=int, help="processes for --reencode (default: all CPUs)")
    p.add_argument("-q", "--quiet", action="store_true", help="no per-archive progress")
    p.set_defaults(func=cmd_census)

    p = sub.add_parser("unpack", help="unpack an Xbox 360 XBLA package into a folder")
    p.add_argument("package", help="the package file (under <TitleID>/000D0000/)")
    p.add_argument("out", nargs="?", help="output folder (omit to list the contents)")
    p.add_argument("--list", action="store_true", help="list the contents only")
    p.add_argument("--only", action="append", help="extract just this path (repeatable)")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_unpack)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "raw", False) and getattr(args, "decompress", False):
        print("error: --raw and --decompress contradict each other", file=sys.stderr)
        return 2
    try:
        return args.func(args)
    except Dr2Error as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:  # e.g. `dr2 ls | head`
        return 0


if __name__ == "__main__":
    sys.exit(main())

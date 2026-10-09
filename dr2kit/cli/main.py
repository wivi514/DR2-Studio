"""The ``dr2`` command: list, search, extract, census, index and mod the games' data,
and check or import models edited in Blender (``dr2 model``).

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
    lookup = None

    def write(vpath: str, data: bytes) -> None:
        nonlocal written, lookup
        if args.png and data[:3] == b"\x05\x01\x01":
            vpath, data = vpath + ".png", _texture_png(vpath, data, args.level)
        elif args.wav and vpath.lower().endswith(".xma"):
            from ..convert.audio import AudioLookup, decode
            lookup = lookup or AudioLookup(tree)
            pcm = decode(data, lookup.info(vpath, data))
            vpath, data = vpath + ".wav", pcm.wav_bytes()
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
        if args.glb:
            write(node.vpath + ".glb", _scene_glb(args, tree, node.vpath, data))
            continue
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


def _scene_glb(args, tree, vpath: str, data: bytes) -> bytes:
    """A scene as .glb bytes (``extract --glb``); says which textures were not found."""
    from ..container.big import BigArchive, is_big
    from ..convert import gltf
    from ..convert.model import TextureFinder
    from ..formats.scene import Scene, is_scene
    if not is_big(data) or not is_scene(BigArchive.parse(data, vpath)):
        raise Dr2Error(f"{vpath} is not a model or skeleton (no SceneHeader); --glb "
                       f"needs one, e.g. data/models/npcs.big/boss_mechanic.big")
    scene = Scene.parse(data, vpath)
    if args.skeleton or not scene.meshes:
        return gltf.skeleton_to_glb(scene)
    finder = None if args.no_textures else TextureFinder(tree, vpath, args.game)
    st = gltf.ExportStats()
    out = gltf.model_to_glb(scene, finder, stats=st)
    if not args.quiet:
        print(f"    {st.meshes} meshes, {st.primitives} draws, {st.vertices:,} vertices, "
              f"{st.triangles:,} triangles, {len(scene.skeleton)} bones, "
              f"{st.textures} textures", file=sys.stderr)
    for name in st.missing_textures:
        print(f"    note: texture {name!r} not found (run `dr2 index build` to search "
              f"the whole game)", file=sys.stderr)
    return out


# ---- model -----------------------------------------------------------------------------

def cmd_model(args) -> int:
    """Check a .glb against a model (the rig validator), or import it into the model."""
    from ..convert.model_import import format_plan, import_glb, plan_import
    from ..formats.scene import Scene
    tree = _tree(args)
    node = tree.resolve(args.vpath)
    data = node.data()
    glb = Path(args.glb).read_bytes()
    if args.action == "check":
        plan = plan_import(Scene.parse(data, node.vpath), glb, args.glb)
        print(format_plan(plan))
        return 0 if plan.ok else 1
    out, plan = import_glb(Scene.parse(data, node.vpath), glb, args.glb)
    print(format_plan(plan))
    dest = Path(args.out)
    if dest.is_dir():
        dest = dest / node.vpath.split("/")[-1]
    dest.write_bytes(out)
    same = " (identical to the original)" if out == data else ""
    print(f"wrote {dest}: {_human(len(out))}{same}", file=sys.stderr)
    return 0


def _texture_png(vpath: str, data: bytes, level: int = 0) -> bytes:
    from ..convert import png
    from ..convert.texture import png_mode, to_image
    from ..formats.bct import Bct
    tex = Bct.parse(data, vpath)
    img = to_image(tex, level)
    return png.encode(img, png_mode(tex, img))


# ---- info -----------------------------------------------------------------------------

def cmd_info(args) -> int:
    """Describe one asset: its index entry and, for a texture, the header and layout."""
    tree = _tree(args)
    node = tree.resolve(args.vpath)
    if node.kind == "dir":
        raise Dr2Error(f"{node.vpath} is a folder (use dr2 ls)")
    print(f"vpath:      {node.vpath}")
    if node.kind == "entry":
        e = node.entry
        print(f"entry:      #{e.index} of {node.archive.source}, flags {e.flags:#x}, "
              f"hash {e.hash:08X}")
        print(f"stored:     {e.size:,} bytes{' (LZX-compressed)' if e.compressed else ''}")
    data = node.data()
    print(f"size:       {len(data):,} bytes")
    from ..census import content_kind
    kind = content_kind(data)
    print(f"content:    {kind}")
    if kind == "bct":
        from ..formats.bct import Bct, model_data_size
        tex = Bct.parse(data, node.vpath)
        h = tex.header
        print(f"texture:    {h.width}x{h.height} {tex.format.name} ({tex.format.channels}), "
              f"{h.levels} mip level{'s' if h.levels > 1 else ''}"
              f"{', cube map (6 faces)' if h.is_cube else ''}")
        print(f"header:     flags {h.flags:#04x}, byte 9 {h.version:#04x}, bpp {h.bpp}, "
              f"word 0x0C {h.word_0c:08X}, payload {h.data_size:#x} "
              f"(layout model {model_data_size(h):#x})")
        print(f"{'level':>5} {'face':>4} {'size':>11} {'offset':>8} {'pitch':>5}  packed at")
        for lv in tex.levels():
            where = f"({lv.tile_x},{lv.tile_y})" if lv.packed else ""
            print(f"{lv.level:>5} {lv.face:>4} {f'{lv.width}x{lv.height}':>11} "
                  f"{lv.offset:>#8x} {lv.pitch:>5}  {where}")
    elif node.vpath.lower().endswith(".xma"):
        _audio_info(tree, node.vpath, data)
    elif node.vpath.lower().endswith(".sfx"):
        from ..formats.audioscript import sfx_tracks
        names = {e.name.lower() for e in node.archive.entries} if node.kind == "entry" else set()
        for t in sfx_tracks(data.decode("latin-1"), node.vpath):
            print(f"track:      {t}{'' if t.lower() in names else '  (not in this bank)'}")
    elif kind == "big":
        from ..container.big import BigArchive
        from ..formats.scene import Scene, is_scene
        arc = BigArchive.parse(data, node.vpath)
        print(f"archive:    {len(arc)} entries (dr2 ls {node.vpath})")
        if is_scene(arc):
            _scene_info(Scene.from_archive(arc, node.vpath))
    return 0


def _audio_info(tree, vpath: str, data: bytes) -> None:
    """The `dr2 info` lines for a sound."""
    from ..convert.audio import AudioLookup, decode, have_decoder, length_check
    from ..formats import xma
    info = AudioLookup(tree).info(vpath, data)
    layout = {1: "mono", 2: "stereo", 6: "5.1"}.get(info.channels, f"{info.channels} ch")
    print(f"audio:      XMA2, {layout}, {info.rate} Hz, {info.streams} stream(s), "
          f"{'RIFF file' if info.shape == 'riff' else 'raw packets'}; metadata from "
          f"{info.source}")
    pk = data[info.packets_offset:info.packets_offset + info.packets_size]
    frames = xma.frame_count(pk, info.streams)
    print(f"packets:    {len(pk) // xma.PACKET} x 2 KB, {frames} frames per stream")
    if info.expected_samples:
        print(f"length:     {info.expected_samples:,} samples "
              f"({info.expected_samples / info.rate:.2f} s, stored)")
    if info.loop:
        a, b = info.loop
        print(f"loop:       samples {a:,}..{b:,} ({a / info.rate:.2f} s..{b / info.rate:.2f} s)")
    if have_decoder():
        pcm = decode(data, info)
        problem = length_check(pcm, info, pk)
        print(f"decoded:    {pcm.frames:,} samples ({pcm.seconds:.2f} s), peak "
              f"{pcm.peak:.3f}{'' if problem is None else '  PROBLEM: ' + problem}")
    else:
        print("decoded:    (install PyAV to decode: pip install av)")


def _scene_info(sc) -> None:
    """The `dr2 info` lines for a model or skeleton."""
    roots = [n.name for n in sc.skeleton.nodes if n.is_root]
    print(f"scene:      {sc.kind}, {len(sc.skeleton)} nodes (root: {', '.join(roots) or '-'}), "
          f"{len(sc.materials)} materials, {len(sc.meshes)} meshes")
    for i, m in enumerate(sc.materials):
        tex = ", ".join(s.name for s in m.slots if not s.engine)
        print(f"  material {i}: {tex or '(no textures)'}")
    for m in sc.meshes:
        for d in m.draws:
            src = "/".join(sorted({(s.buffer or "run-time").replace(m.name + " ", "")
                                   for s in d.streams.values()}))
            print(f"  {m.name} draw {d.number}: {d.vertex_count} vertices, "
                  f"{d.index_count} strip indices, material {d.material}, "
                  f"shader {sc.shaders.get(d.shader, f'{d.shader:08X}')}, "
                  f"bones {d.palette_start}..{d.palette_start + d.palette_count - 1}, "
                  f"from {src}")
            print(f"      {'; '.join(e.describe() for e in d.declaration)}")
    if sc.unknown:
        print(f"other chunks: {', '.join(sc.unknown)}")


# ---- index ----------------------------------------------------------------------------

def _db(args):
    from ..index.build import connect
    return connect(args.db)


def cmd_index(args) -> int:
    """Build, refresh or search the asset index."""
    from ..index import query
    if args.action == "build":
        from ..container.vpath import AssetTree
        from ..index.build import build_index, default_db_path, format_stats
        games = list(GAME_IDS) if args.games in ([], ["all"]) else args.games
        problems = 0
        for g in games:
            tree = AssetTree(locate(g).root)
            progress = None if args.quiet else (lambda vp: print(f"  {vp}", file=sys.stderr))
            st = build_index(g, tree, args.db, thumbs=not args.no_thumbs, full=args.full,
                             progress=progress)
            print(format_stats(st))
            problems += len(st.problems)
        print(f"index: {args.db or default_db_path()}", file=sys.stderr)
        return 1 if problems else 0
    con = _db(args)
    if args.action == "stats":
        for r in query.counts(con):
            print(f"{r['game']}  {r['kind']:>13}  {r['n']:>8}")
        return 0
    if args.action == "search":
        rows = query.search(con, " ".join(args.text), game=args.game, kind=args.kind,
                            fmt=args.format, limit=args.limit)
        for r in rows:
            print(f"{r['game']}  {r['kind']:>13}  {_human(r['size']):>10}  {r['vpath']}")
        print(f"{len(rows)} result{'s' if len(rows) != 1 else ''}"
              f"{' (limit reached)' if len(rows) == args.limit else ''}", file=sys.stderr)
        return 0
    row = query.get(con, args.game or "cz", args.vpath)
    if row is None:
        raise Dr2Error(f"{args.vpath}: not in the index for {args.game or 'cz'} "
                       f"(dr2 index build?)")
    if args.action == "textures-of":
        for r in query.textures_of(con, row["id"]):
            where = r["vpath"] or "(not found in this game)"
            print(f"slot {r['slot']:>3}  {r['dst_name']:<32} {where}")
    elif args.action == "used-by":
        for r in query.used_by(con, row["id"]):
            print(f"{'next to it' if r['rank'] == 0 else 'elsewhere':>10}  {r['vpath']}")
    return 0


# ---- mods -----------------------------------------------------------------------------

def cmd_mod(args) -> int:
    """Create, check, build and deploy mod packages."""
    from ..mods import manifest
    if args.action == "new":
        root = manifest.create(args.folder, args.id, args.name)
        print(f"created {root / manifest.MANIFEST}; put replacement files under "
              f"{root / manifest.REPLACE_DIR}/ (see docs/modding/06-mod-packages.md)")
        return 0
    from ..container.vpath import AssetTree
    from ..mods import build as mbuild
    from ..mods import deploy as mdeploy
    game = args.game
    loc = locate(game)
    tree = AssetTree(loc.root)
    if args.action == "undeploy":
        target = Path(args.to) if args.to else mdeploy.recomp_folders(loc.root)["mods"]
        removed = mdeploy.undeploy(target)
        print(f"removed {len(removed)} file{'s' if len(removed) != 1 else ''} from {target}")
        return 0
    mods = [manifest.Mod.load(m) for m in args.mods]
    if args.action == "check":
        plan = mbuild.classify(mods, game, tree)
        for p in plan:
            print(f"{p.mod.id:>16}  {p.override.kind:<11}  {p.vpath}")
        print(f"{len(plan)} override{'s' if len(plan) != 1 else ''} OK for {game}")
        return 0
    recomp = mdeploy.is_recomp_root(loc.root)
    base = []
    if not args.no_patched_base:
        base = [Path(b) for b in (args.base or [])]
        patched = mdeploy.recomp_folders(loc.root)["patched"]
        if recomp and not args.base and patched.is_dir():
            base = [patched]
    progress = None if args.quiet else (lambda vp: print(f"  built {vp}", file=sys.stderr))
    if args.action == "build":
        res = mbuild.build(mods, game, tree, args.out, base, progress=progress)
        print(f"built {len(res.files)} file{'s' if len(res.files) != 1 else ''} for {game} "
              f"in {args.out}")
        for vp, b in res.base_used.items():
            print(f"    {vp}: built on top of {b}")
        for w in res.warnings:
            print(f"note: {w}", file=sys.stderr)
        return 0
    # deploy
    import tempfile
    if args.to:
        target = Path(args.to)
    elif recomp:
        target = mdeploy.recomp_folders(loc.root)["mods"]
    else:
        raise Dr2Error(f"{game}'s data is not in a recomp ({loc.root}); say where to put "
                       f"the files with --to FOLDER")
    with tempfile.TemporaryDirectory(prefix="dr2mod-") as tmp:
        res = mbuild.build(mods, game, tree, tmp, base, progress=progress)
        written = mdeploy.deploy(res, target)
    for vp in written:
        print(f"deployed {vp}")
    for vp, b in res.base_used.items():
        print(f"    {vp}: built on top of {b}")
    for w in res.warnings:
        print(f"note: {w}", file=sys.stderr)
    if recomp and not args.to:
        for w in mdeploy.shadowed_layers(loc.root, written):
            print(f"warning: {w}", file=sys.stderr)
        env = "CZ_NO_MODS" if game == "cz" else "CW_NO_MODS"
        print(f"{len(written)} file{'s' if len(written) != 1 else ''} in {target}. "
              f"Start the recomp to use them; {env}=1 turns mods off, "
              f"`dr2 mod undeploy -g {game}` removes them.")
    return 0


def cmd_studio(args) -> int:
    """Start DR2 Studio (needs PySide6)."""
    try:
        from ..studio.app import main as studio_main
    except ImportError as e:
        raise Dr2Error(f"DR2 Studio needs PySide6: pip install 'dr2kit[studio]' ({e})") from None
    return studio_main([])


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
                         textures=args.textures, models=args.models,
                         reimport=args.reimport, audio=args.audio, workers=args.workers,
                         progress=progress)
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
    p.add_argument("--png", action="store_true",
                   help="write textures as PNG images (<name>.png) instead of .bct bytes")
    p.add_argument("--level", type=int, default=0,
                   help="with --png: which mip level (0 = full size)")
    p.add_argument("--wav", action="store_true",
                   help="write sounds (.xma) as 16-bit WAV files (<name>.xma.wav); needs PyAV")
    p.add_argument("--glb", action="store_true",
                   help="write models and skeletons as glTF binary (<name>.glb) for Blender: "
                        "meshes, skeleton, skin and textures")
    p.add_argument("--skeleton", action="store_true",
                   help="with --glb: only the skeleton (an armature)")
    p.add_argument("--no-textures", action="store_true",
                   help="with --glb: don't embed textures (smaller, faster)")
    p.add_argument("-q", "--quiet", action="store_true")
    game_opt(p)
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("model", help="check or import a .glb edited in Blender into a model")
    msub = p.add_subparsers(dest="action", required=True, metavar="ACTION")
    for name, helptext in (("check", "check a .glb against a model (bones, weights, "
                                     "materials, palettes); write nothing"),
                           ("import", "put a .glb's meshes into a model and write the "
                                      "model file (to test outside a mod)")):
        pm = msub.add_parser(name, help=helptext)
        pm.add_argument("glb", help="the .glb file (from Blender, or dr2 extract --glb)")
        pm.add_argument("vpath", help="the model it goes into, e.g. "
                                      "data/models/npcs.big/chest_young_chuck.big")
        game_opt(pm)
        if name == "import":
            pm.add_argument("-o", "--out", required=True,
                            help="output file (or folder: the model's own name is used)")
    p.set_defaults(func=cmd_model)

    p = sub.add_parser("info", help="describe one asset (texture header and layout, ...)")
    p.add_argument("vpath")
    game_opt(p)
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("index", help="build or search the asset index (SQLite)")
    isub = p.add_subparsers(dest="action", required=True, metavar="ACTION")
    pi = isub.add_parser("build", help="index one or both games (only changed files are re-read)")
    pi.add_argument("games", nargs="*", choices=[*GAME_IDS, "all"], metavar="GAME")
    pi.add_argument("--full", action="store_true", help="re-read every file")
    pi.add_argument("--no-thumbs", action="store_true", help="skip texture thumbnails (faster)")
    pi.add_argument("-q", "--quiet", action="store_true")
    pi = isub.add_parser("search", help="find assets by name (words, * and ? wildcards)")
    pi.add_argument("text", nargs="+")
    pi.add_argument("-g", "--game", choices=GAME_IDS)
    pi.add_argument("--kind", help="texture, model, skeleton, audio, text, ...")
    pi.add_argument("--format", help="texture format: DXT1, DXT5, DXN, A8R8G8B8, L8")
    pi.add_argument("--limit", type=int, default=200)
    isub.add_parser("stats", help="assets per game and kind")
    for name, helptext in (("textures-of", "the textures a model's materials name"),
                           ("used-by", "the models whose materials name this texture")):
        pi = isub.add_parser(name, help=helptext)
        pi.add_argument("vpath")
        pi.add_argument("-g", "--game", choices=GAME_IDS, default="cz")
    for pi in isub.choices.values():
        pi.add_argument("--db", help="index file (default: the per-user cache folder)")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("mod", help="create, check, build and deploy mod packages")
    msub = p.add_subparsers(dest="action", required=True, metavar="ACTION")
    pm = msub.add_parser("new", help="make an empty mod folder with a mod.toml")
    pm.add_argument("folder")
    pm.add_argument("--id")
    pm.add_argument("--name")
    for name, helptext in (("check", "check a mod's files against the game, write nothing"),
                           ("build", "build replacement files into a folder"),
                           ("deploy", "build and copy into the recomp's game_mods/ (or --to)")):
        pm = msub.add_parser(name, help=helptext)
        pm.add_argument("mods", nargs="+", metavar="MOD", help="mod folder(s)")
        game_opt(pm)
        pm.add_argument("-q", "--quiet", action="store_true")
        if name == "build":
            pm.add_argument("-o", "--out", required=True, help="output folder")
        if name == "deploy":
            pm.add_argument("--to", help="deploy into this folder instead of the recomp")
        if name != "check":
            pm.add_argument("--base", action="append",
                            help="patch this folder's copy of a file when it has one "
                                 "(default: the recomp's game_patched)")
            pm.add_argument("--no-patched-base", action="store_true",
                            help="always start from the shipped files")
    pm = msub.add_parser("undeploy", help="remove what the last deploy wrote")
    game_opt(pm)
    pm.add_argument("--to", help="the folder deployed to with --to")
    p.set_defaults(func=cmd_mod)

    p = sub.add_parser("studio", help="start DR2 Studio, the graphical browser")
    p.set_defaults(func=cmd_studio)

    p = sub.add_parser("census", help="read everything, report it, and run the format gates")
    p.add_argument("games", nargs="*", choices=[*GAME_IDS, "all"], metavar="GAME",
                   help="cz, cw or all (default: all)")
    p.add_argument("--json", help="also write the full report as JSON to this file")
    p.add_argument("--reencode", action="store_true",
                   help="also re-encode every compressed entry and decode it back (slow)")
    p.add_argument("--python-lzx", action="store_true",
                   help="also decode every compressed entry with the pure-Python decoder")
    p.add_argument("--textures", action="store_true",
                   help="also decode every texture and re-encode it to the same bytes (slow)")
    p.add_argument("--models", action="store_true",
                   help="also decode every draw of every model (vertices, triangles, skin)")
    p.add_argument("--reimport", action="store_true",
                   help="also export every model to .glb and import it back (must give the "
                        "same bytes), and rebuild every shape from its own geometry (slow)")
    p.add_argument("--audio", action="store_true",
                   help="also decode every sound (.xma) and check its length, and resolve "
                        "every .sfx track (needs PyAV)")
    p.add_argument("--workers", type=int,
                   help="processes for --reencode / --audio (default: all CPUs)")
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

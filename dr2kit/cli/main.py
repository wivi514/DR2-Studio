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
    print(f"audio/movies: {_av_detail()}")
    print(f"config file: {config_path()}")
    return cmd_games(args)


def _av_detail() -> str:
    """PyAV and its ffmpeg: version, licence, and the decoders the toolkit needs."""
    try:
        import av
        import av._core as core
    except ImportError:
        return "PyAV not installed (pip install av): no sounds or movies"
    meta = core.library_meta.get("libavcodec", {})
    missing = []
    for name in ("xma2", "binkvideo"):
        try:
            av.codec.Codec(name, "r")
        except Exception:  # noqa: BLE001 - any failure means "missing"
            missing.append(name)
    return (f"PyAV {av.__version__}, libavcodec {'.'.join(map(str, meta.get('version', ())))} "
            f"({meta.get('license', 'licence unknown')})"
            + (f"; MISSING decoders: {', '.join(missing)}" if missing else ""))


def cmd_games(args) -> int:
    """List each game and where its data was found; or `set` a folder for one."""
    if getattr(args, "action", None) == "set-recomp":
        from ..mods.play import find_recomp, set_recomp
        set_recomp(args.set_game, args.program)
        print(f"{args.set_game}: Play starts {find_recomp(args.set_game)}")
        return 0
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
        elif args.mp4 and vpath.lower().endswith(".bik"):
            import tempfile
            from ..convert.video import to_mp4
            with tempfile.TemporaryDirectory(prefix="dr2mp4-") as tmp:
                to_mp4(data, Path(tmp) / "m.mp4")
                vpath, data = vpath + ".mp4", (Path(tmp) / "m.mp4").read_bytes()
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
    if vpath.lower().endswith(".anm"):
        from ..convert import holding
        glb, clp = holding.animation_glb(tree, args.game, vpath, textures=not args.no_textures)
        if not args.quiet:
            body = "Chuck" if holding.body_for(tree, vpath) == "chuck" else "its rig's bones"
            print(f"    the move on {body}: {clp['length']:.2f} s, {len(clp['nodes'])} nodes "
                  f"({', '.join(f.rsplit('/', 2)[-2] for f in clp['files'])}); Blender: an "
                  f"Action, Space plays it", file=sys.stderr)
        return glb
    if not is_big(data) or not is_scene(BigArchive.parse(data, vpath)):
        raise Dr2Error(f"{vpath} is not a model or skeleton (no SceneHeader); --glb "
                       f"needs one, e.g. data/models/npcs.big/boss_mechanic.big")
    scene = Scene.parse(data, vpath)
    if args.skeleton or not scene.meshes:
        return gltf.skeleton_to_glb(scene)
    from ..convert.model import model_glb
    from ..convert.variants import read_variants
    finder = None if args.no_textures else TextureFinder(tree, vpath, args.game)
    st = gltf.ExportStats()
    mv = read_variants(tree, scene, args.game)
    choice = mv.parse(args.variant)
    out = model_glb(tree, scene, game=args.game, finder=finder, textures=finder is not None,
                    stats=st, variant=choice, mode=args.variants, variants=mv)
    if mv.has_choices and not args.quiet:
        print(f"    look: {choice.text()} ({'only its parts' if args.variants == 'shown' else 'every part, the others hidden'}; "
              f"`dr2 variants {vpath}` lists the choices)", file=sys.stderr)
    if not args.quiet:
        print(f"    {st.meshes} meshes, {st.primitives} draws, {st.vertices:,} vertices, "
              f"{st.triangles:,} triangles, {len(scene.skeleton)} bones, "
              f"{st.textures} textures"
              + (f" ({st.baked} colours baked from shader constants)" if st.baked else ""),
              file=sys.stderr)
    for name in st.missing_textures:
        print(f"    note: texture {name!r} not found (run `dr2 index build` to search "
              f"the whole game)", file=sys.stderr)
    return out


# ---- variants ---------------------------------------------------------------------------

def cmd_variants(args) -> int:
    """What a model can show: slots, on/off parts, prop states, colour choices; with
    --variant, which parts that look shows and the game's hide mask for it."""
    from ..container.vpath import AssetTree
    from ..convert.model import read_scene
    from ..convert.variants import read_variants
    tree = AssetTree(locate(args.game).root)
    scene = read_scene(tree, args.vpath)
    mv = read_variants(tree, scene, args.game)
    print(scene.source)
    if not mv.has_choices:
        print("  no variants: the game draws every part of this model")
        return 0
    choice = mv.parse(args.variant)
    for line in mv.describe(choice):
        print("  " + line)
    if args.parts:
        print()
        for p, shown in zip(mv.parts, mv.shown(choice)):
            print(f"  {'shown ' if shown else 'hidden'}  {p.group:<18} {p.bits:#018x}  {p.name}")
    return 0


# ---- level -----------------------------------------------------------------------------

def cmd_level(args) -> int:
    """Levels: list them and their zones, or describe a level, a zone, its placements."""
    from ..convert import level as clevel
    tree = _tree(args)
    if args.action == "list":
        for L in clevel.list_levels(tree):
            print(f"{L.name:<22} {len(L.zones):>2} zones   {L.vpath}")
            print("    " + " ".join(L.zone_names()))
        return 0
    if args.action == "things":
        return _level_things(args, tree)
    if args.action in ("show", "edit", "diff"):
        return _level_text(args, tree)
    L = clevel.Level.open(tree, args.level)
    if not args.zone:
        print(f"{L.name}: {len(L.zones)} zones ({L.vpath})")
        for z in L.zones:
            zd = L.zone(z)
            c = z.centre
            print(f"  {z.zone:<24} {len(zd.pieces):>4} pieces {len(zd.placements):>4} placed   "
                  f"centre {c[0]:8.1f} {c[1]:6.1f} {c[2]:8.1f}  radius {z.radius:6.1f} m")
            for name in zd.unplaced:
                print(f"      never placed: {name}")
            for name in zd.missing:
                print(f"      placed, but not in the zone: {name}")
        return 0
    zd = L.zone(args.zone)
    print(f"{zd.vpath}: {len(zd.pieces)} pieces, {len(zd.placements)} placements")
    import math
    for p in zd.placements:
        x, y, z = p.position
        yaw = math.degrees(2 * math.atan2(p.rotation[1], p.rotation[3]))
        rot = "" if p.rotation[:3] == (0.0, 0.0, 0.0) else (
            f"  turned {yaw:.0f}°" if p.rotation[0] == p.rotation[2] == 0.0 else
            f"  rotation {' '.join(f'{c:.3f}' for c in p.rotation)}")
        scale = "" if p.scale == (1.0, 1.0, 1.0) else f"  scale {' '.join(f'{c:.3f}' for c in p.scale)}"
        flags = f"  flags {p.flags:#x}" if p.flags else ""
        print(f"  {p.index:>3} {p.piece:<32} at {x:8.2f} {y:7.2f} {z:8.2f}{rot}{scale}{flags}")
    return 0


def _level_text(args, tree) -> int:
    """``dr2 level show / edit / diff``: the level text files, and level edits in a mod
    (phase 11; `dr2kit.mods.leveledit`, guide 19)."""
    from ..container.vpath import join
    from ..convert import placed
    from ..formats import leveledits as le
    from ..formats.levelscript import Document
    from ..mods import leveledit
    from ..mods.deploy import recomp_folders
    file = args.file if args.file.lower().endswith(".txt") else args.file + ".txt"
    patched = recomp_folders(tree.root)["patched"]
    base = [patched] if patched.is_dir() else []
    if args.action == "show":
        doc = Document.parse(leveledit.game_bytes(tree, file, base), file)
        if not args.path:
            for b in doc.blocks:
                print(f"{b.cls} {b.name}".rstrip())
            return 0
        b = doc.find(args.path)
        print(doc.text(b), end="")
        return 0
    if args.action == "diff":
        edited = Document.parse(Path(args.edited).read_bytes(), args.edited)
        original = Document.parse(leveledit.game_bytes(tree, file, base), file)
        e = le.diff(original, edited)
        text = le.to_json(e, join(placed.DATAFILE, file))
        if args.mod:
            from ..mods.manifest import Mod
            dest = leveledit.edits_path(Mod.load(args.mod).root, file)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, "utf-8")
            print(f"wrote {dest} ({e.count()} change{'s' if e.count() != 1 else ''})")
        else:
            print(text, end="")
        return 0
    # edit
    from ..mods.manifest import Mod
    mod = Mod.load(args.mod)
    session = leveledit.TextEdits(mod.root, file, tree, base)
    doc = session.doc
    if args.op == "remove":
        doc.remove(doc.find(args.path))
    elif args.op == "set":
        b = doc.find(args.path)
        for k, v in leveledit.parse_assignments(args.values).items():
            if v is None:
                doc.unset(b, k)
            else:
                doc.set(b, k, v)
    elif args.op == "add":
        from ..formats.levelscript import split_path
        parts = split_path(args.path)
        parent = doc.find("/".join(parts[:-1])) if len(parts) > 1 else None
        cls, _, name = parts[-1].partition(" ")
        props = {k: v for k, v in leveledit.parse_assignments(args.values).items() if v}
        if args.like:
            src = doc.find(args.like)
            props = {**{p.key: p.value for p in src.props}, **props}
        doc.add(parent, cls, name, props)
    f = session.save()
    n = session.edits().count()
    print(f"{f}: {n} change{'s' if n != 1 else ''} to {file}")
    for note in session.notes:
        print(f"note: {note}", file=sys.stderr)
    return 0


def _level_things(args, tree) -> int:
    """``dr2 level things``: what a level's text files place, by kind."""
    from ..convert import level as clevel
    from ..convert import placed
    scripts = placed.script_names(tree)
    if not args.script:
        levels = [L.name for L in clevel.list_levels(tree)]
        for s in scripts:
            print(f"{s:<24} on the level {placed.geometry_of(s, levels) or '?'}")
        return 0
    strings = None
    try:
        from ..convert.strings import load_bank
        strings = load_bank(tree, "en").strings
    except Dr2Error:
        pass
    ls = placed.read_script(tree, args.script, placed.ItemModels(tree), strings)
    print(f"{args.script}: " + ", ".join(f"{placed.LAYERS.get(k, k).lower()}: {n}"
                                         for k, n in ls.counts().most_common()))
    for t in ls.things:
        if args.kind and t.kind != args.kind:
            continue
        pos = " ".join(f"{c:.2f}" for c in t.position) if t.position else (
            f"{len(t.polygon)} corners" if t.polygon else "")
        extra = t.item or t.label or t.props.get("Level") or ""
        model = f"  -> {t.model}" if t.model and args.models else ""
        print(f"  {t.kind:<12} {t.name:<34} {pos:<28} {extra}{model}")
    return 0


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
    elif node.vpath.lower().endswith(".bik"):
        from ..convert.video import have_bink, probe
        print(f"movie:      {probe(data).describe()}" if have_bink() else
              "movie:      Bink (install PyAV to read it: pip install av)")
    elif node.vpath.lower().endswith(".bcs"):
        from ..formats.bcs import StringBank
        bank = StringBank.parse(data, node.vpath)
        print(f"strings:    {len(bank.strings):,} (ids {min(bank.strings)}..{bank.last_id}); "
              f"dr2 strings search / export")
    elif node.vpath.lower().endswith(".anm") and data:
        from collections import Counter

        from ..formats import anim
        a = anim.Animation.parse(data, node.vpath)
        kinds = Counter(f"{anim.KINDS[t.kind][0]}{' (animated)' if t.animated else ''}"
                        for t in a.tracks)
        print(f"animation:  {a.frames} frames at {a.rate:g}/s ({a.length:.2f} s), "
              f"{len(a.tracks)} tracks: " + ", ".join(f"{n} {k}" for k, n in kinds.items()))
        c = a.decode()
        keys = sum(len(ch.frames) for ch in c.channels)
        print(f"keys:       {keys:,} (every one read; dr2 extract --glb plays it in Blender)")
        from ..convert import holding
        sk = holding.skeleton_for(tree, a, node.vpath)
        print(f"rig:        {sk or 'unknown'} (skeleton id {a.skeleton_id:08X}; track numbers "
              f"are its nodes)")
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


# ---- library / export (phase 8) ------------------------------------------------------

def cmd_library(args) -> int:
    """The Library: groups and counts, a group's items, or the count gate (--check)."""
    from ..catalog.groups import catalog, check
    from ..index import query
    con = _db(args)
    cat = catalog()
    games = list(GAME_IDS) if args.check and args.game is None else [args.game or "cz"]
    if args.check:
        bad = 0
        for g in games:
            if not query.library_counts(con, g):
                print(f"== {g}: not indexed (dr2 index build {g})")
                bad += 1
                continue
            report, problems = check(con, g)
            print(f"== {g}")
            print("\n".join(report))
            for p in problems[:50]:
                print(f"PROBLEM: {p}")
            if len(problems) > 50:
                print(f"... and {len(problems) - 50} more")
            print(f"{len(problems)} problem(s)")
            bad += len(problems)
        return 1 if bad else 0
    game = games[0]
    counts = query.library_counts(con, game)
    if not counts:
        raise Dr2Error(f"{game} is not indexed yet: dr2 index build {game}")
    if not args.group:
        per: dict[str, dict[str, int]] = {}
        for r in counts:
            per.setdefault(r["grp"], {})[r["sub"]] = r["n"]
        for section in cat.sections():
            print(section)
            for g in cat.groups:
                if g.section != section or g.id not in per:
                    continue
                subs = per[g.id]
                more = f"  ({len(subs)} sub-groups)" if len(subs) > 1 or "" not in subs else ""
                print(f"  {g.id:<20} {sum(subs.values()):>6}  {g.title}{more}")
        print("(dr2 library <group> lists one; dr2 export <group> -o <folder> exports it)",
              file=sys.stderr)
        return 0
    from ..catalog.export import group_rows
    rows = group_rows(con, game, args.group)
    levels: dict[int, list[tuple[str, str]]] = {}     # detail levels folded into an item
    for r in rows:
        if r["detail_of"] is not None:
            levels.setdefault(r["detail_of"], []).append((r["vpath"].lower(), r["detail"]))
    shown = [r for r in rows if r["detail_of"] is None]
    sub = None
    for r in shown:
        if r["sub"] != sub:
            sub = r["sub"]
            if sub:
                print(f"[{sub}]")
        label = f"{r['label']}  " if r["label"] else ""
        more = (f"  [detail: {r['detail']}, {', '.join(d for _v, d in sorted(levels[r['id']]))}]"
                if r["id"] in levels else "")
        print(f"  {label}{r['name']}  ({_human(r['size'])})  {r['vpath']}{more}")
    print(f"{len(shown)} item(s)" + (f" (+{len(rows) - len(shown)} detail levels in them)"
                                     if len(rows) > len(shown) else ""), file=sys.stderr)
    return 0


def cmd_export(args) -> int:
    """Export Library groups, sections or single assets to a folder in one go."""
    from ..catalog import export as cx
    from ..container.vpath import AssetTree
    from ..index import query
    from ..convert.level import list_levels
    tree0 = AssetTree(locate(args.game).root, cache_size=32)
    levels = {L.name.lower(): L.name for L in list_levels(tree0)}
    lv = [t for t in args.targets if t.lower() in levels]
    if lv:                                                    # levels (phase 10)
        if len(lv) != len(args.targets):
            raise Dr2Error("export levels and Library groups in separate commands")
        return _export_levels(args, tree0, [levels[t.lower()] for t in lv])
    if args.zone or args.whole:
        raise Dr2Error("--zone and --whole are for levels (dr2 level list)")
    con = _db(args)
    rows, singles = [], []
    for t in args.targets:
        if "/" in t and query.get(con, args.game, t) is not None:
            singles.append(dict(query.get(con, args.game, t)))
        else:
            rows += cx.group_rows(con, args.game, t)
    jobs = cx.plan(singles, args.out, args.game, by_group=False) + \
        cx.plan(rows, args.out, args.game, con=con)
    outputs = {o for o in cx.OUTPUTS if getattr(args, o)} or None
    if args.list:
        for j in jobs:
            print(f"{j.row['vpath']}  ->  {j.dest}")
        print(f"{len(jobs)} asset(s)", file=sys.stderr)
        return 0
    ex = cx.Exporter(AssetTree(locate(args.game).root, cache_size=32), args.game, args.db,
                     outputs, variant=args.variant, mode=args.variants)

    def progress(done, total, vpath):
        if vpath and not args.quiet:
            print(f"[{done + 1}/{total}] {vpath}", file=sys.stderr)
    try:
        res = ex.run(jobs, progress=progress)
    finally:
        ex.close()
    for vp, why in res.failed:
        print(f"FAILED {vp}: {why}")
    print(res.summary())
    return 1 if res.failed else 0


def _export_levels(args, tree, names: list[str]) -> int:
    """``dr2 export <level>``: zones as .glb with items and markers, the text files."""
    from ..catalog.level_export import DEFAULT_MARKERS, export_level
    from ..convert.placed import LAYERS
    if args.markers in (None, "default"):
        markers = DEFAULT_MARKERS
    elif args.markers == "none":
        markers = ()
    elif args.markers == "all":
        markers = tuple(k for k in LAYERS if k not in ("item", "door"))
    else:
        markers = tuple(args.markers.split(","))
        bad = [m for m in markers if m not in LAYERS]
        if bad:
            raise Dr2Error(f"unknown marker kind(s) {', '.join(bad)} (known: "
                           f"{', '.join(k for k in LAYERS if k not in ('item', 'door'))})")
    failed = 0
    for name in names:
        def progress(done, total, what, name=name):
            if not args.quiet:
                print(f"[{done + 1}/{total}] {name}: {what}", file=sys.stderr)
        res = export_level(tree, args.game, name, args.out, zones=args.zone or None,
                           script=args.script, items=not args.no_items, markers=markers,
                           whole=args.whole, lod=args.lod, db_path=args.db,
                           progress=progress, dry_run=args.list, zombies=args.zombies,
                           collision=args.collision)
        for p in res.files:
            print(("would write " if args.list else "") + str(p))
        for a, b in res.failed:
            print(f"FAILED {a}: {b}")
        failed += len(res.failed)
        for n in res.unplaced_collision:
            print(f"note: collision shape {n} left out (where it goes is unknown)",
                  file=sys.stderr)
        print(f"{name}: {len(res.files)} files ({len(res.skipped)} already there), "
              f"{res.pieces} pieces, {res.items} items and doors, {res.markers} markers, "
              f"{res.zombies} zombies, "
              + (f"{res.collision:,} collision triangles, " if args.collision else "") +
              f"{res.triangles:,} triangles -> {res.folder}", file=sys.stderr)
    return 1 if failed else 0


# ---- mods -----------------------------------------------------------------------------

def cmd_mod(args) -> int:
    """Create, check, build and deploy mod packages; manage the mod library."""
    from ..mods import library as mlib
    from ..mods import manifest
    if args.action == "new":
        root = manifest.create(args.folder, args.id, args.name)
        print(f"created {root / manifest.MANIFEST}; put replacement files under "
              f"{root / manifest.REPLACE_DIR}/ (see docs/modding/06-mod-packages.md)")
        return 0
    if args.action in _LIBRARY_ACTIONS:
        return _cmd_library(args, mlib)
    from ..container.vpath import AssetTree
    from ..mods import build as mbuild
    from ..mods import deploy as mdeploy
    game = args.game
    loc = locate(game)
    tree = AssetTree(loc.root)
    if args.action == "new-item":
        from ..mods import newitem
        from ..mods.deploy import recomp_folders
        patched = recomp_folders(loc.root)["patched"]
        mod = manifest.Mod.load(args.mod)                 # a mod folder, or an error
        textures = {}
        for t in args.texture or []:
            if "=" not in t:
                raise Dr2Error(f"--texture {t!r}: write TEXTURE=file.png")
            k, v = t.split("=", 1)
            textures[k] = v
        files = newitem.new_item(tree, mod.root, args.name, args.like, args.glb,
                                 [patched] if patched.is_dir() else [], textures)
        for f in files:
            print(f"wrote {f}")
        print(f"{args.name} is an item of the mod now: place it in a level (Maps tab, Add "
              f"item…, or dr2 level edit {args.mod} <level> add \"cItemPlacement My{args.name}\" "
              f"ItemName={args.name} Location=x,y,z)")
        return 0
    if args.action == "import-item":
        from ..mods import importitem
        from ..mods.deploy import recomp_folders
        patched = recomp_folders(loc.root)["patched"]
        src = args.source or ("cw" if game == "cz" else "cz")
        if args.dry_run:
            from ..convert.crossgame import source_tree
            p = importitem.plan(source_tree(src), tree, src, game, args.item)
            print(p.report())
            return 1 if p.unresolved else 0
        p, files = importitem.import_item(args.mod, args.item, src, game, tree,
                                          [patched] if patched.is_dir() else [])
        print(p.report())
        print(f"wrote {len(files)} files into {args.mod}; the mod now needs both games' "
              f"data to build (dr2 mod info {args.mod}). Place it from the Maps tab "
              f"(Add item…), or dr2 level edit.")
        return 0
    if args.action in ("new-weapon", "remove-weapon"):
        return _cmd_weapon(args, tree, loc)
    if args.action in ("effect", "new-effect", "effect-picture"):
        return _cmd_effect(args, tree)
    if args.action == "import-textures":
        from ..mods import texture_import as ti
        mod = manifest.Mod.load(args.mod)
        tp = ti.plan(tree, args.model, args.sources, game)
        print(tp.report())
        if args.dry_run or not tp.items:
            return 0 if tp.items else 1
        for f in ti.apply(tp, mod.root):
            print(f"wrote {f}")
        return 0
    if args.action == "undeploy":
        target = Path(args.to) if args.to else mdeploy.recomp_folders(loc.root)["mods"]
        removed = mdeploy.undeploy(target)
        print(f"removed {len(removed)} file{'s' if len(removed) != 1 else ''} from {target}")
        return 0
    if args.mods:
        mods = [manifest.Mod.load(m) for m in args.mods]
    else:
        lib = mlib.ModLibrary(args.library)
        mods = lib.active(game)
        print(f"enabled mods for {game} in {lib.folder}: "
              f"{', '.join(m.id for m in mods) or 'none'}", file=sys.stderr)
        if not mods:
            raise Dr2Error("no mod given and none enabled in the library "
                           "(dr2 mod list / dr2 mod enable ID)")
    if args.action in ("check", "conflicts"):
        mplan = mbuild.plan_mods(mods, game, tree)
        if args.action == "check":
            for p in mplan.planned:
                print(f"{p.mod.id:>16}  {p.override.kind:<11}  {p.vpath}")
        for what, lost, won in mplan.shadowed:
            print(f"{what}: {won} wins over {lost}")
        for n in mplan.notes:
            print(f"note: {n}", file=sys.stderr)
        if args.action == "check":
            print(f"{len(mplan.planned)} override{'s' if len(mplan.planned) != 1 else ''} "
                  f"OK for {game}")
        else:
            print(f"{len(mplan.shadowed)} conflict{'s' if len(mplan.shadowed) != 1 else ''} "
                  f"between {len(mods)} mods for {game} (the later mod in the load order wins)")
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
        _report_build(res)
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
    _report_build(res)
    if recomp and not args.to:
        for w in mdeploy.shadowed_layers(loc.root, written):
            print(f"warning: {w}", file=sys.stderr)
        env = "CZ_NO_MODS" if game == "cz" else "CW_NO_MODS"
        print(f"{len(written)} file{'s' if len(written) != 1 else ''} in {target}. "
              f"Start the recomp to use them; {env}=1 turns mods off, "
              f"`dr2 mod undeploy -g {game}` removes them.")
    return 0


def _report_build(res) -> None:
    for vp, b in res.base_used.items():
        print(f"    {vp}: built on top of {b}")
    for what, lost, won in res.shadowed:
        print(f"    {what}: {won} wins over {lost}")
    for w in res.warnings:
        print(f"note: {w}", file=sys.stderr)


_LIBRARY_ACTIONS = ("list", "install", "remove", "enable", "disable", "move", "library",
                    "link", "sets", "status",
                    "pack", "info")


def _cmd_mod_info(args, mlib) -> int:
    """``dr2 mod info``: what a mod needs (`dr2kit.mods.requires`) and whether this
    computer has it."""
    import json as _json
    from ..mods import requires
    from ..mods.manifest import Mod
    lib = mlib.ModLibrary(args.library)
    if Path(args.mod).is_dir():
        mod = Mod.load(args.mod)
    else:
        mod = lib.get(args.mod).mod
    req = requires.infer(mod, with_hash=True)
    on = {e.mod.id: e.mod.version for e in lib.entries() if e.enabled}
    on.setdefault(mod.id, mod.version)
    missing = requires.check(req, None, on)
    if args.json:
        print(_json.dumps({**req.to_json(), "missing": missing}, indent=1))
        return 1 if missing else 0
    print(f"{mod.name} ({mod.root})")
    print(req.to_text().rstrip())
    if req.written:
        print("Written by the modder in [requires]: " + ", ".join(req.written))
    if missing:
        print("\nThis computer can't build it yet:")
        for m in missing:
            print(f"  - {m}")
        return 1
    print("\nThis computer has everything it needs.")
    return 0


def _cmd_library(args, mlib) -> int:
    """The mod manager actions (`dr2kit.mods.library`)."""
    if args.action == "status":
        from ..mods.play import deployed
        for g in ([args.game] if args.game else list(GAME_IDS)):
            try:
                print(f"{g}: {deployed(g).describe()}")
            except Dr2Error as e:
                print(f"{g}: {e}")
        return 0
    if args.action == "info":
        return _cmd_mod_info(args, mlib)
    if args.action == "pack":
        out = mlib.pack(args.folder, args.out)
        print(f"wrote {out}")
        return 0
    if args.action == "library":
        if args.reset:
            mlib.set_default_library(None)
        elif args.folder:
            mlib.set_default_library(args.folder)
        print(f"mod library: {mlib.default_library()}  (config: {config_path()})")
        return 0
    lib = mlib.ModLibrary(args.library)
    if args.action == "install":
        for src in args.sources:
            mod = lib.install(src, replace=args.replace)
            print(f"installed {mod.id} {mod.version} ({mod.name}) -> {mod.root}, enabled")
            for c in lib.last_changes:
                print(f"    {c}")
        return 0
    if args.action == "link":
        for src in args.sources:
            mod = lib.link(src)
            print(f"linked {mod.id} ({mod.root}): it stays there, and it is on")
        return 0
    if args.action == "sets":
        if args.set_action == "save":
            print(f"set {args.name!r}: {', '.join(lib.save_set(args.name)) or '(no mod on)'}")
        elif args.set_action == "use":
            gone = lib.use_set(args.name)
            print(f"switched on the mods of {args.name!r}"
                  + (f"; not installed any more: {', '.join(gone)}" if gone else ""))
        elif args.set_action == "delete":
            lib.delete_set(args.name)
        else:
            for name, ids in lib.sets().items():
                print(f"{name}: {', '.join(ids) or '(none)'}")
        return 0
    if args.action == "remove":
        for mid in args.ids:
            print(f"removed {lib.remove(mid)}")
        return 0
    if args.action in ("enable", "disable"):
        for mid in args.ids:
            lib.enable(mid, args.action == "enable")
            print(f"{mid}: {args.action}d")
        return 0
    if args.action == "move":
        pos = lib.move(args.id, args.where)
        print(f"{args.id}: now number {pos} in the load order (higher numbers win)")
        return 0
    entries = lib.entries()
    print(f"mod library: {lib.folder}")
    if not entries:
        print("  (empty: dr2 mod install <folder or .zip>)")
        return 0
    print(f"{'#':>3}  on   {'id':<24} {'version':<9} {'games':<6} files  name")
    for e in entries:
        flag = "yes" if e.enabled else "new" if e.new else "no"
        print(f"{e.position + 1:>3}  {flag:<4} {e.mod.id:<24} {e.mod.version:<9} "
              f"{','.join(e.mod.games):<6} {len(e.mod.files()):>5}  {e.mod.name}")
    print("Later mods win over earlier ones (dr2 mod move ID up|down|top|bottom|N).")
    return 0


# ---- strings --------------------------------------------------------------------------

def _cmd_weapon(args, tree, loc) -> int:
    """``dr2 mod new-weapon`` / ``remove-weapon``: the weapon wizard (mods.newweapon)."""
    from ..mods import manifest
    from ..mods import newweapon as nw
    from ..mods.deploy import recomp_folders
    patched = recomp_folders(loc.root)["patched"]
    base = [patched] if patched.is_dir() else []
    mod = manifest.Mod.load(args.mod)
    if args.action == "remove-weapon":
        for f in nw.remove_weapon(tree, mod.root, args.name, base):
            print(f"removed {f}")
        return 0
    if args.name in nw.weapons_of(mod.root):
        spec = nw.load_spec(mod.root, args.name)          # change only what is given
        if args.kind:
            spec.kind = args.kind
    else:
        if not args.kind:
            raise Dr2Error("--kind is needed for a new weapon (dr2 effects --kinds lists them)")
        spec = nw.WeaponSpec(name=args.name, kind=args.kind)
    for lang, text in (("en", args.name_en), ("fr", args.name_fr)):
        if text:
            spec.names[lang] = text
    for key in ("handle", "length", "turn", "slide", "effect_start", "shine", "damage",
                "durability", "element", "icon"):
        v = getattr(args, key)
        if v is not None:
            setattr(spec, key, v)
    if args.glb is not None:
        spec.model = None if args.glb == "keep" else args.glb
    for slot in ("impact", "victim", "held", "swinging"):
        v = getattr(args, slot)
        if v is not None:
            if v in ("0", "none"):
                spec.effects.pop(slot, None)
            else:
                spec.effects[slot] = v
    if args.no_combo:
        spec.combo = None
    elif args.combo:
        a, sep, b = args.combo.partition("+")
        if not sep:
            raise Dr2Error("--combo ITEM+ITEM, e.g. Broadsword+FireExtinguisher")
        spec.combo = nw.Combo([a.strip(), b.strip()])
    if spec.combo:
        if args.card_text_en:
            spec.combo.description["en"] = args.card_text_en
        if args.card_text_fr:
            spec.combo.description["fr"] = args.card_text_fr
        if args.card_picture:
            spec.combo.picture = args.card_picture
        if args.card_number is not None:
            spec.combo.number = args.card_number
    made = nw.make_weapon(tree, args.game, mod.root, spec, base)
    for f in made.files:
        print(f"wrote {f}")
    for n in made.notes:
        print(f"note: {n}")
    ids = ", ".join(f"{k} {v}" for k, v in made.string_ids.items())
    print(f"{spec.name}: a {spec.kind} of {mod.id} (string ids: {ids}"
          + (f"; combo card number {made.card_number}" if made.card_number else "") + ")")
    print(f"place it in a level: Maps tab, Add item…, or dr2 level edit {args.mod} <level> "
          f"add \"cItemPlacement My{spec.name}\" ItemName={spec.name} Location=x,y,z")
    return 0


def _effect_changes(args) -> dict:
    ch: dict = {}
    for key in ("hue", "saturation", "brightness", "alpha", "size", "time"):
        v = getattr(args, key, None)
        if v is not None:
            ch[key] = v
    for swap in args.texture or []:
        if "=" not in swap:
            raise Dr2Error(f"--texture {swap!r}: write OLD=NEW (picture names)")
        a, b = swap.split("=", 1)
        ch.setdefault("texture", {})[a] = b
    return ch


def _cmd_effect(args, tree) -> int:
    """``dr2 mod effect`` / ``new-effect`` / ``effect-picture`` (mods.neweffect)."""
    from ..mods import manifest, neweffect
    mod = manifest.Mod.load(args.mod)
    if args.action == "effect-picture":
        f = neweffect.new_particle_texture(tree, mod.root, args.name, args.png)
        print(f"wrote {f}; use it with --texture OLD={args.name}")
        return 0
    ch = _effect_changes(args)
    if args.action == "effect":
        if args.remove:
            for f in neweffect.remove(mod.root, args.effect):
                print(f"removed {f}")
            return 0
        f = neweffect.change_effect(tree, mod.root, args.effect, ch)
        print(f"wrote {f}: {args.effect} changes everywhere the game uses it")
        return 0
    num, f = neweffect.new_effect(tree, args.game, mod.root, args.effect, ch, args.slot)
    print(f"wrote {f}: your effect is number {num}; give it to a weapon "
          f"(dr2 mod new-weapon … --held {num}) or any effect key")
    return 0


def cmd_hold(args) -> int:
    """``dr2 hold``: Chuck holding an item, frozen in the game's idle for it (phase 13.2)."""
    from ..convert import holding, render
    tree = _tree(args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.mod:
        from ..mods import newweapon as nw
        mod_dir = Path(args.mod)
        spec = nw.load_spec(mod_dir, args.item)
        sources = mod_dir / "sources"
        glb = nw.hold_glb(tree, args.game, spec, sources, textures=not args.no_textures,
                          moves=args.moves)
        scene = nw.hold_scene(tree, args.game, spec, sources, mod_dir)
        chuck, name = scene.chuck, spec.name
        m = nw.fit_weapon(tree, args.game, spec, sources)
        parts = m.parts
        place = [[scene.placement[c * 4 + r] for c in range(4)] for r in range(4)]
    else:
        glb, chuck = holding.item_hold_glb(tree, args.game, args.item,
                                           textures=not args.no_textures, moves=args.moves)
        name = args.item
        parts = place = None
        if args.png:
            from ..convert import placed
            from ..formats.scene import Scene
            from ..mods.newweapon import _game_parts
            vp = placed.ItemModels(tree).resolve(args.item)
            sc = Scene.parse(tree.resolve(vp).data(), vp)
            parts = _game_parts(tree, sc)
            place = holding.item_placement(chuck.hand, holding.grip_matrix(sc))
    f = out / f"{name}_held.glb"
    f.write_bytes(glb)
    idle = chuck.idle
    print(f"{f}: Chuck in {idle.fullbody.rsplit('/', 1)[-1]} (first frame, idle value "
          f"{idle.idle_value}), hands {idle.hand.rsplit('/', 1)[-1] if idle.hand else 'none'} "
          f"(hand value {idle.hand_value})")
    for n in idle.notes:
        print(f"  note: {n}")
    if args.moves:
        from ..convert.gltf import Glb
        moves = Glb.parse(glb).gltf["asset"].get("extras", {}).get("dr2", {}).get("moves") or []
        print(f"  moves (glTF animations, Blender Actions; the item follows his hand): "
              + (", ".join(moves) or "none"))
    if args.png:
        if not render.available():
            raise Dr2Error("--png needs numpy (pip install numpy)")
        pic = holding.picture(tree, args.game, chuck, parts, place)
        p = out / f"{name}_held.png"
        p.write_bytes(render.to_png(pic))
        print(f"{p}: front, side and three-quarter views")
    return 0


def cmd_effects(args) -> int:
    """List weapon kinds, or the effect table by group, with what uses each effect."""
    from ..catalog import weapons
    if args.kinds:
        for k in weapons.kinds(args.game):
            print(f"{k.id:14} {k.name:26} from {k.template(args.game):18} {k.note}")
        return 0
    doc = None
    try:
        from ..container.vpath import AssetTree
        from ..formats.levelscript import Document
        tree = AssetTree(locate(args.game).root)
        doc = Document.parse(tree.resolve("data/datafile.big/items.txt").data())
    except Dr2Error:
        pass                                                # names only, without the game
    if args.free:
        from ..container.vpath import AssetTree
        from ..mods import neweffect
        free = neweffect.free_slots(AssetTree(locate(args.game).root), args.game)
        for num, name in free:
            print(f"{num:4}  {name}")
        print(f"{len(free)} free slot(s): numbers with no effect in the game, for effects of "
              f"your own (dr2 mod new-effect … --slot N)")
        return 0
    if args.show:
        from ..container.vpath import AssetTree
        from ..convert.effects import describe
        from ..formats import effect as fx
        tree = AssetTree(locate(args.game).root)
        allfx = fx.read_all(tree)
        hit = allfx.get(args.show) or next((f for n, f in allfx.items()
                                            if n.lower() == args.show.lower()), None)
        if hit is None:
            raise Dr2Error(f"no effect named {args.show!r} in {args.game}")
        entry, e = hit
        print(f"{e.name} ({fx.EFFECTS_BIG}/{entry}), {len(e.emitters)} emitter(s):")
        for line in describe(e):
            print("  " + line)
        if args.out:
            from ..convert import effect_preview as ep
            from ..convert import png
            pic = ep.preview(e, ep.texture_finder(tree))
            png.write(args.out, png.Image(pic.shape[1], pic.shape[0], pic.tobytes()))
            print(f"wrote {args.out} (a sketch from the effect's data)")
        return 0
    words = [w.lower() for w in args.words]
    names = dict(weapons.groups())
    shown = 0
    for e in weapons.effects(args.game, doc):
        if args.group and e.group != args.group:
            continue
        if words and not all(w in e.name.lower() for w in words):
            continue
        how = {True: "keeps going", False: "burst", None: ""}[e.loops]
        line = f"{e.number:4}  {e.name:30} {names[e.group]:24} {how:11}"
        if e.used_by:
            line += " used by " + ", ".join(e.used_by[:3]) + (" …" if len(e.used_by) > 3 else "")
        print(line)
        if e.tested:
            print(f"      checked: {e.tested}")
        shown += 1
    print(f"{shown} effect(s); 'keeps going' / 'burst' are read from the names (docs/modding/"
          f"20-make-a-weapon.md)")
    return 0


def cmd_strings(args) -> int:
    """Search, show and export the string banks; change strings in a mod."""
    from ..convert import strings as cstr
    from ..formats import bcs
    tree = _tree(args)
    labels = cstr.load_labels(tree)
    if args.action == "search":
        langs = cstr.languages(tree) if args.lang == ["all"] else args.lang or ["en"]
        hits = cstr.search(tree, " ".join(args.text), langs, args.limit)
        for h in hits:
            text = h.text.replace("\n", "\\n")
            print(f"{h.id:>6}  {h.lang}  {h.label:<36} {text}")
        print(f"{len(hits)} string{'s' if len(hits) != 1 else ''}"
              f"{' (limit reached)' if len(hits) == args.limit else ''}", file=sys.stderr)
        return 0
    if args.action == "show":
        i = cstr.resolve_id(args.id, labels)
        print(f"id {i}  {labels.get(i, '')}")
        for lang in cstr.languages(tree):
            if lang == "id":
                continue
            t = cstr.load_bank(tree, lang).strings.get(i)
            print(f"  {lang}: {'(none)' if t is None else t!r}")
        return 0
    if args.action == "export":
        langs = cstr.languages(tree) if args.lang == "all" else [args.lang]
        out = Path(args.out)
        for lang in langs:
            dest = out / f"str_{lang}.bcs.json" if out.is_dir() or len(langs) > 1 else out
            dest.parent.mkdir(parents=True, exist_ok=True)
            bank = cstr.load_bank(tree, lang)
            dest.write_text(bcs.to_json(bank, cstr.bank_vpath(lang), labels), "utf-8")
            print(f"wrote {dest}: {len(bank.strings)} strings")
        return 0
    # set / unset: change a mod's string overrides
    from ..mods.manifest import Mod
    mod = Mod.load(args.mod)
    i = cstr.resolve_id(args.id, labels)
    bank = cstr.load_bank(tree, args.lang)
    if args.action == "set":
        text = args.text.replace("\\n", "\n")
        _, notes = bcs.apply(bank, {i: text})
        f = cstr.set_mod_strings(mod.root, args.lang, {i: text}, labels, bank.strings)
        for n in notes:
            print(f"note: {n}", file=sys.stderr)
        print(f"{mod.id}: {args.lang} id {i} ({labels.get(i, '')}) -> {text!r}  ({f})")
    else:
        f = cstr.set_mod_strings(mod.root, args.lang, {i: None}, labels, bank.strings)
        print(f"{mod.id}: {args.lang} id {i} back to the game's text  ({f})")
    return 0


# ---- play -----------------------------------------------------------------------------

def cmd_play(args) -> int:
    """Deploy the library's switched-on mods and start the recomp."""
    from ..mods import play
    from ..mods.library import ModLibrary
    if args.no_mods:
        print(f"starting {play.find_recomp(args.game)} with mods off "
              f"({play.load_profile(args.game).no_mods_env}=1)")
        play.launch(args.game, mods=False)
        return 0
    lib = ModLibrary(args.library)
    progress = None if args.quiet else (lambda vp: print(f"  built {vp}", file=sys.stderr))
    files, res = play.deploy_library(args.game, lib, progress)
    print(play.deployed(args.game).describe())
    if res is not None:
        _report_build(res)
    if args.deploy_only:
        return 0
    exe = play.find_recomp(args.game)
    print(f"starting {exe}")
    play.launch(args.game)
    return 0


# ---- help -----------------------------------------------------------------------------

def cmd_help(args) -> int:
    """The modding guides in the terminal (the same pages as DR2 Studio's help)."""
    from .. import help as dhelp
    topics = dhelp.topics(args.lang)
    if args.search:
        hits = dhelp.search(" ".join(args.topic), args.lang)
        for h in hits:
            print(f"{h.topic.name:<26} {h.heading[:40]:<40}  {h.line[:90]}")
        print(f"{len(hits)} line(s); show a page with: dr2 help <page>", file=sys.stderr)
        return 0
    if not args.topic:
        print("Help pages (dr2 help 05, dr2 help text, dr2 help --search <words>):")
        for t in topics:
            print(f"  {t.name:<26} {t.title}")
        return 0
    want = " ".join(args.topic).lower()
    if want.isdigit():
        want = f"{int(want):02d}" if int(want) else "readme"
    match = next((t for t in topics if t.name.lower().startswith(want)), None) or \
        next((t for t in topics if want in t.name.lower()[:-3].split("-")), None) or \
        next((t for t in topics if want in t.name.lower()), None) or \
        next((t for t in topics if want in t.title.lower()), None)
    if match is None:
        raise Dr2Error(f"no help page matches {want!r}; dr2 help lists them, "
                       f"dr2 help --search {want} searches them")
    print(dhelp.read(match.name, args.lang))
    return 0


def cmd_studio(args) -> int:
    """Start DR2 Studio (needs PySide6)."""
    try:
        from ..studio.app import main as studio_main
    except ImportError as e:
        raise Dr2Error(f"DR2 Studio needs PySide6: pip install 'dr2kit[studio]' ({e})") from None
    game = args.game if (args.map or args.mod) else None
    if args.mod and not game:
        from ..mods.manifest import Mod
        games = Mod.load(args.mod).games
        game = games[0] if len(games) == 1 else None
    return studio_main(args.files, game=game, map_level=args.map, at=args.at,
                       mod=args.mod, weapon=args.weapon)


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
                         progress=progress, variants=args.variants, levels=args.levels,
                         anims=args.anims)
        print(format_report(rep))
        reports.append(rep)
    bad = any(r.problems for r in reports)
    if getattr(args, "imports", False):                   # phase 15: the importer's gate
        from ..mods import importitem
        trees = {g: AssetTree(locate(g).root) for g in GAME_IDS}
        for src, dst in (("cw", "cz"), ("cz", "cw")):
            r = importitem.census(trees[src], trees[dst], src, dst)
            print(f"import {src} -> {dst}: {r['items']} items the target lacks, "
                  f"{r['planned']} planned, {len(r['refused'])} refused, "
                  f"{len(r['unresolved'])} unresolved; names {r['how']}")
            print("  dropped: " + ", ".join(f"{k} ×{v}" for k, v in list(r["dropped"].items())[:12]))
            for x in r["refused"] + r["unresolved"]:
                print(f"  PROBLEM {x}")
            bad = bad or bool(r["refused"] or r["unresolved"])
            reports_json = getattr(args, "_imports", [])
            reports_json.append({"from": src, "into": dst, **r})
            args._imports = reports_json
    if args.json:
        Path(args.json).write_text(json.dumps([r.to_json() for r in reports] +
                                              getattr(args, "_imports", []), indent=1))
    return 1 if bad else 0


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

    def variant_opts(p):
        p.add_argument("--variant", metavar="CHOICE",
                       help="models with variants: the look, e.g. head=2,shirt=1,"
                            "colour.jersey=4 (default: the first of each; `dr2 variants` "
                            "lists them)")
        p.add_argument("--variants", choices=("all", "shown"), default="all",
                       help="all: every part, sorted into groups, the others hidden "
                            "(default); shown: only the parts of that look")

    p = sub.add_parser("doctor", help="show versions, the LZX decoder in use, and the games found")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("games", help="show where each game's data is, or set it")
    gsub = p.add_subparsers(dest="action")
    pr = gsub.add_parser("set-recomp", help="the recomp program `dr2 play` starts for a game")
    pr.add_argument("set_game", choices=GAME_IDS, metavar="GAME")
    pr.add_argument("program", help="cz_runtime / cw_runtime (.exe), or the recomp's AppImage")
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
    p.add_argument("--mp4", action="store_true",
                   help="write Bink movies (.bik, Case West) as .mp4 (<name>.bik.mp4); needs PyAV")
    p.add_argument("--glb", action="store_true",
                   help="write models and skeletons as glTF binary (<name>.glb) for Blender: "
                        "meshes, skeleton, skin and textures")
    p.add_argument("--skeleton", action="store_true",
                   help="with --glb: only the skeleton (an armature)")
    p.add_argument("--no-textures", action="store_true",
                   help="with --glb: don't embed textures (smaller, faster)")
    variant_opts(p)
    p.add_argument("-q", "--quiet", action="store_true")
    game_opt(p)
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("variants", help="what a model can show: heads, shirts, colours… "
                       "(the game shows one choice per slot)")
    p.add_argument("vpath", help="a model, e.g. data/models/zombies.big/zombie_skinny.big/"
                                 "zombie_skinny_2.big")
    p.add_argument("--variant", metavar="CHOICE",
                   help="a look to describe, e.g. head=2,shirt=3,colour.jersey=4")
    p.add_argument("--parts", action="store_true",
                   help="list every part: its group, the game's bits, shown or hidden")
    game_opt(p)
    p.set_defaults(func=cmd_variants)

    from ..convert.placed import LAYERS as placed_kinds
    p = sub.add_parser("level", help="the games' levels: zones, pieces and where they go")
    lsub = p.add_subparsers(dest="action", required=True, metavar="ACTION")
    pl = lsub.add_parser("list", help="every level and its zones")
    game_opt(pl)
    pl = lsub.add_parser("things", help="what a level's text files place: items, doors, "
                         "spawn points, areas, triggers (no name: list the scripts)")
    pl.add_argument("script", nargs="?", help="a level script, e.g. prologue or "
                    "prologue_safehouse (Case Zero), living_research (Case West)")
    pl.add_argument("--kind", choices=sorted(k for k in placed_kinds if k != "navmesh"), help="only this kind")
    pl.add_argument("--models", action="store_true", help="show each item's model")
    game_opt(pl)
    pl = lsub.add_parser("show", help="a level text file's blocks, or one block's text "
                         "(as the game has it)")
    pl.add_argument("file", help="a text file of datafile.big: prologue, waypoint_prologue, "
                    "missions, items, zombiesets…")
    pl.add_argument("path", nargs="?", help='a block path: "cItemPlacement Scissors1", '
                    '"cMissionDefinition X/cMissionLevelReady Y/…"')
    game_opt(pl)
    pl = lsub.add_parser("edit", help="change a level text file in a mod: set keys, add or "
                         "remove a block (saved as the mod's .edits.json)")
    pl.add_argument("mod", help="the mod folder")
    pl.add_argument("file", help="the text file (prologue, missions…)")
    pl.add_argument("op", choices=("set", "add", "remove"))
    pl.add_argument("path", help="the block path (for add: the new block's)")
    pl.add_argument("values", nargs="*", help="KEY=VALUE (set, add); KEY= removes a key")
    pl.add_argument("--like", help="add: copy the keys of this block first")
    game_opt(pl)
    pl = lsub.add_parser("diff", help="turn a whole edited text file into an .edits.json "
                         "(only the changes)")
    pl.add_argument("file", help="which game file it is (prologue, missions…)")
    pl.add_argument("edited", help="your edited copy of it")
    pl.add_argument("--mod", help="write it into this mod folder (else print it)")
    game_opt(pl)
    pl = lsub.add_parser("info", help="a level's zones, or one zone's placements")
    pl.add_argument("level", help="a level, e.g. prologue (Case Zero) or living_research (Case West)")
    pl.add_argument("zone", nargs="?", help="a zone, e.g. z05 or prologue_z05")
    game_opt(pl)
    p.set_defaults(func=cmd_level)

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

    p = sub.add_parser("library", help="the games' assets by what they are (characters, "
                       "music, rigs…): groups, counts, a group's items")
    p.add_argument("group", nargs="?", help="a group (characters), sub-group "
                   "(zombies/zombie_cop) or section (sounds) to list")
    p.add_argument("-g", "--game", choices=GAME_IDS, help="which game (default: cz)")
    p.add_argument("--check", action="store_true",
                   help="the count gate: every asset in its group, counts match the index")
    p.add_argument("--db", help="index file (default: the per-user cache folder)")
    p.set_defaults(func=cmd_library)

    p = sub.add_parser("export", help="export Library groups or assets in one go: models "
                       "with textures and rig, sounds as WAV, movies as MP4…")
    p.add_argument("targets", nargs="+", metavar="GROUP_OR_VPATH",
                   help="a group (characters, music), sub-group (zombies/zombie_cop), section "
                   "(sounds), an asset's vpath, or a level (prologue, living_research)")
    p.add_argument("-o", "--out", required=True, help="folder to write into")
    game_opt(p)
    for o, h in (("glb", "models and rigs as .glb"), ("png", "textures as PNG"),
                 ("wav", "sounds as WAV"), ("mp4", "movies as MP4"),
                 ("json", "string banks as .bcs.json"), ("raw", "other files as they are")):
        p.add_argument(f"--{o}", action="store_true", help=f"only {h} (combine several)")
    p.add_argument("--list", action="store_true", help="only show what would go where")
    lg = p.add_argument_group("levels (a target that names a level: dr2 level list)")
    lg.add_argument("--zone", action="append", metavar="ZONE",
                    help="only this zone, e.g. z05 (repeat for several; default: all)")
    lg.add_argument("--whole", action="store_true", help="one .glb for all the zones")
    lg.add_argument("--no-items", action="store_true", help="leave the items and doors out")
    lg.add_argument("--markers", metavar="KINDS",
                    help="marker kinds: spawn,zombie_area,map_area,map_point,trigger,navmesh "
                         "(the default), 'all' or 'none'")
    lg.add_argument("--script", help="the item set, e.g. prologue_safehouse (default: the "
                    "level's own)")
    lg.add_argument("--lod", action="store_true", help="the game's small textures (smaller files)")
    lg.add_argument("--zombies", action="store_true",
                    help="zombies where the missions put crowds (example spots)")
    lg.add_argument("--collision", action="store_true",
                    help="the collision mesh (what the player bumps into)")
    variant_opts(p)
    p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument("--db", help="index file (default: the per-user cache folder)")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("mod", help="create, check, build and deploy mods; the mod library")
    msub = p.add_subparsers(dest="action", required=True, metavar="ACTION")
    pm = msub.add_parser("new", help="make an empty mod folder with a mod.toml")
    pm.add_argument("folder")
    pm.add_argument("--id")
    pm.add_argument("--name")
    for name, helptext in (("check", "check mods against the game, write nothing"),
                           ("conflicts", "list the assets and strings two mods both replace"),
                           ("build", "build replacement files into a folder"),
                           ("deploy", "build and copy into the recomp's game_mods/ (or --to)")):
        pm = msub.add_parser(name, help=helptext)
        pm.add_argument("mods", nargs="*", metavar="MOD",
                        help="mod folder(s); none = the library's enabled mods, in order")
        game_opt(pm)
        pm.add_argument("--library", help="the mod library folder (default: dr2 mod library)")
        pm.add_argument("-q", "--quiet", action="store_true")
        if name == "build":
            pm.add_argument("-o", "--out", required=True, help="output folder")
        if name == "deploy":
            pm.add_argument("--to", help="deploy into this folder instead of the recomp")
        if name in ("build", "deploy"):
            pm.add_argument("--base", action="append",
                            help="patch this folder's copy of a file when it has one "
                                 "(default: the recomp's game_patched)")
            pm.add_argument("--no-patched-base", action="store_true",
                            help="always start from the shipped files")
    pm = msub.add_parser("new-item", help="a new item of your own, made from one the game "
                         "has (its model pack and items.txt block, under a new name)")
    pm.add_argument("mod", help="the mod folder")
    pm.add_argument("name", help="the new item's name (letters, digits, _)")
    pm.add_argument("--like", required=True, help="the game's item to start from "
                    "(SledgeHammer, Workbench, MilitaryBarrier…)")
    pm.add_argument("--glb", help="a .glb (from Blender) for its shape")
    pm.add_argument("--texture", action="append", metavar="NAME=PNG",
                    help="a PNG over one of its textures (same size), e.g. "
                         "Sledgehammer_cm=red.png; repeat for more")
    game_opt(pm)
    pm = msub.add_parser("import-item", help="use an item of the other game (Case West's in "
                         "Case Zero, or the other way): its model, shaders, moves, sounds and "
                         "text are brought, every name checked (phase 15)")
    pm.add_argument("mod", help="the mod folder")
    pm.add_argument("item", help="the item's items.txt name in the other game")
    pm.add_argument("--from", dest="source", choices=GAME_IDS,
                    help="the game it comes from (default: the other one)")
    pm.add_argument("-g", "--game", choices=GAME_IDS, default="cz",
                    help="the game it goes into (default: cz)")
    pm.add_argument("-n", "--dry-run", action="store_true", help="only say what it would do")
    pm = msub.add_parser("new-weapon", help="a weapon of your own: the weapon wizard (kind, "
                         "model, damage, element, effects, icon, combo card); run again to "
                         "change it")
    pm.add_argument("mod", help="the mod folder")
    pm.add_argument("name", help="the weapon's item name (letters, digits, _)")
    pm.add_argument("--kind", help="what it swings like: sword, knife, bat, hammer… "
                    "(dr2 effects --kinds)")
    pm.add_argument("--name-en", help="its name in English (default: the item name)")
    pm.add_argument("--name-fr", help="its name in French (default: the English one)")
    pm.add_argument("--glb", help="its model: a .glb (any orientation and size: it is laid "
                    "along the game weapon), 'sample' for the sample sword, 'keep' for the "
                    "game weapon's")
    pm.add_argument("--handle", choices=("auto", "min", "max"),
                    help="which end of the model is the handle (auto: the end nearer the "
                         "model's origin)")
    pm.add_argument("--length", type=float, help="its length in metres (default: the game "
                    "weapon's)")
    pm.add_argument("--turn", type=float, help="spin it about its length (degrees)")
    pm.add_argument("--shine", choices=["game", "matte", "little", "mirror"],
                    help="how shiny: the game weapon's, or like the Baseball Bat (matte), "
                         "the Lead Pipe (little) or the Broadsword (mirror)")
    pm.add_argument("--effect-start", type=float, help="effects while held / swinging start "
                    "this far from the hand toward the tip (metres, default 0.10)")
    pm.add_argument("--slide", type=float, help="move it along its length (metres, + toward "
                    "the tip): where the hands hold it")
    pm.add_argument("--damage", type=int, help="damage per attack (Broadsword 125)")
    pm.add_argument("--durability", type=int, help="hits before it breaks (Broadsword 40)")
    pm.add_argument("--element", choices=("none", "fire", "freeze", "shock"))
    for slot, what in (("impact", "where it hits"), ("victim", "on the zombie hit"),
                       ("held", "on the weapon while held"),
                       ("swinging", "on the weapon while swinging")):
        pm.add_argument(f"--{slot}", metavar="EFFECT",
                        help=f"an effect {what}: a number or a name (dr2 effects); none "
                             f"removes it")
    pm.add_argument("--icon", help="the inventory icon: auto (a picture of the model, the "
                    "default), keep (the game weapon's), or a PNG")
    pm.add_argument("--combo", metavar="ITEM+ITEM",
                    help="make it at a workbench from two items, e.g. "
                         "Broadsword+FireExtinguisher (a combo card comes with it)")
    pm.add_argument("--no-combo", action="store_true", help="take the combo away")
    pm.add_argument("--card-text-en", help="the card's description in English")
    pm.add_argument("--card-text-fr", help="the card's description in French")
    pm.add_argument("--card-picture", help="the card's picture: auto (the model) or a PNG "
                    "(315×262)")
    pm.add_argument("--card-number", type=int, help="the card's number (default: the first "
                    "free one)")
    game_opt(pm)
    def change_opts(pm):
        pm.add_argument("--hue", type=float, help="turn the colours to this hue (0-360: 0 red, "
                        "120 green, 210 ice blue)")
        for key, what in (("saturation", "× saturation"), ("brightness", "× brightness"),
                          ("alpha", "× opacity"), ("size", "× every size"),
                          ("time", "× the lifetime (colour key times)")):
            pm.add_argument(f"--{key}", type=float, help=what)
        pm.add_argument("--texture", action="append", metavar="OLD=NEW",
                        help="swap a particle picture (names in effects.tex, or yours)")
    pm = msub.add_parser("effect", help="change one of the game's particle effects in a mod "
                         "(everywhere the game uses it)")
    pm.add_argument("mod", help="the mod folder")
    pm.add_argument("effect", help="the effect's name (dr2 effects)")
    pm.add_argument("--remove", action="store_true", help="take the change out of the mod")
    change_opts(pm)
    game_opt(pm)
    pm = msub.add_parser("new-effect", help="an effect of your own: a game effect copied into "
                         "a free number of the effect table, with changes")
    pm.add_argument("mod", help="the mod folder")
    pm.add_argument("effect", help="the game effect to start from (dr2 effects)")
    pm.add_argument("--slot", help="which free number or name (default: the first free one)")
    change_opts(pm)
    game_opt(pm)
    pm = msub.add_parser("effect-picture", help="a particle picture of your own (a PNG) for "
                         "effects (--texture OLD=NAME)")
    pm.add_argument("mod", help="the mod folder")
    pm.add_argument("name", help="its name (letters, digits, _)")
    pm.add_argument("png", help="the picture (see-through background)")
    game_opt(pm)
    pm = msub.add_parser("remove-weapon", help="take a wizard weapon out of a mod")
    pm.add_argument("mod", help="the mod folder")
    pm.add_argument("name", help="the weapon's item name")
    game_opt(pm)
    pm = msub.add_parser("import-textures",
                         help="put textures exported from Substance Painter, Blender… into a mod")
    pm.add_argument("mod", help="the mod folder")
    pm.add_argument("model", help="the model they were painted on, e.g. "
                                  "data/models/npcs.big/chest_young_chuck.big")
    pm.add_argument("sources", nargs="+", help="exported pictures, folders, or a .glb")
    pm.add_argument("-n", "--dry-run", action="store_true", help="show what would go where")
    game_opt(pm)
    pm = msub.add_parser("undeploy", help="remove what the last deploy wrote")
    game_opt(pm)
    pm.add_argument("--to", help="the folder deployed to with --to")
    # the mod manager (dr2kit.mods.library)
    pm = msub.add_parser("list", help="the mod library: load order, which mods are on")
    pm = msub.add_parser("install", help="copy mod folders or .zip files into the library")
    pm.add_argument("sources", nargs="+", metavar="FOLDER_OR_ZIP")
    pm.add_argument("--replace", action="store_true", help="update a mod already installed")
    pm = msub.add_parser("remove", help="delete mods from the library")
    pm.add_argument("ids", nargs="+", metavar="ID")
    for name in ("enable", "disable"):
        pm = msub.add_parser(name, help=f"{name} mods in the library")
        pm.add_argument("ids", nargs="+", metavar="ID")
    pm = msub.add_parser("move", help="change a mod's place in the load order")
    pm.add_argument("id")
    pm.add_argument("where", help="up, down, top, bottom, or a position (1 = lowest)")
    for name in ("list", "install", "remove", "enable", "disable", "move"):
        msub.choices[name].add_argument("--library",
                                        help="the mod library folder (default: dr2 mod library)")
    pm = msub.add_parser("library", help="show or set the mod library folder")
    pm.add_argument("folder", nargs="?")
    pm.add_argument("--reset", action="store_true", help="back to the default folder")
    pm = msub.add_parser("link", help="add mod folders that stay where they are (mods you make)")
    pm.add_argument("sources", nargs="+", metavar="FOLDER")
    pm.add_argument("--library", help="the mod library folder (default: dr2 mod library)")
    pm = msub.add_parser("sets", help="saved sets of switched-on mods: list, save, use, delete")
    pm.add_argument("set_action", nargs="?", choices=["list", "save", "use", "delete"],
                    default="list")
    pm.add_argument("name", nargs="?")
    pm.add_argument("--library", help="the mod library folder (default: dr2 mod library)")
    pm = msub.add_parser("status", help="what is deployed in each game now")
    pm.add_argument("-g", "--game", choices=GAME_IDS)
    pm = msub.add_parser("info", help="what a mod needs: games (also the ones its things "
                         "come from), other mods, saves, co-op; and what this computer lacks")
    pm.add_argument("mod", help="a mod folder or a library mod's id")
    pm.add_argument("--json", action="store_true", help="print requirements.json (+ missing)")
    pm.add_argument("--library", help="the mod library folder (default: dr2 mod library)")
    pm = msub.add_parser("pack", help="package a mod folder to share (<id>-<version>.dr2mod)")
    pm.add_argument("folder")
    pm.add_argument("-o", "--out", help="zip file or folder (default: current folder)")
    p.set_defaults(func=cmd_mod)

    p = sub.add_parser("hold", help="Chuck holding an item, frozen in the game's idle for it "
                       "(a .glb for Blender, --png a picture): to line a weapon up")
    p.add_argument("item", help="a game item's items.txt name (Broadsword, LeadPipe…), or with "
                   "--mod a weapon of that mod (New weapon…)")
    p.add_argument("--mod", help="the mod folder holding the weapon")
    p.add_argument("-o", "--out", default="extracted", help="output folder (default: extracted)")
    p.add_argument("--png", action="store_true", help="also a picture (front, side, "
                   "three-quarter)")
    p.add_argument("--no-textures", action="store_true", help="no pictures in the .glb")
    p.add_argument("--moves", action="store_true", help="also its attacks, as animations "
                   "(Blender Actions): Chuck swinging it")
    game_opt(p)
    p.set_defaults(func=cmd_hold)

    p = sub.add_parser("effects", help="the game's particle effects by group (for weapons), "
                       "or the weapon kinds (--kinds)")
    p.add_argument("words", nargs="*", help="only effects whose name has these words")
    from ..catalog.weapons import groups as effect_groups
    p.add_argument("--group", choices=[g for g, _ in effect_groups()],
                   help="only one group (ice, fire, electric, blood…)")
    p.add_argument("--kinds", action="store_true", help="list the weapon kinds instead")
    p.add_argument("--show", metavar="NAME", help="one effect's emitters in words")
    p.add_argument("--free", action="store_true", help="the free slots: numbers with no "
                   "effect, for effects of your own")
    p.add_argument("--out", metavar="PNG", help="with --show: a picture of it (a sketch)")
    game_opt(p)
    p.set_defaults(func=cmd_effects)

    p = sub.add_parser("strings", help="search and export the game's text; change it in a mod")
    ssub = p.add_subparsers(dest="action", required=True, metavar="ACTION")
    ps = ssub.add_parser("search", help="find strings by text, label or id")
    ps.add_argument("text", nargs="+")
    ps.add_argument("--lang", action="append",
                    help="language code (en, fr, it, es, ja, ko; id = labels), or 'all' "
                         "(default: en; repeatable)")
    ps.add_argument("--limit", type=int, default=200)
    ps = ssub.add_parser("show", help="one string in every language")
    ps.add_argument("id", help="a string id (3) or label (IDS_START_DEMO)")
    ps = ssub.add_parser("export", help="write a string bank as JSON")
    ps.add_argument("--lang", default="en", help="language code, or 'all' (default: en)")
    ps.add_argument("-o", "--out", default=".", help="file, or folder (default: here)")
    ps = ssub.add_parser("set", help="change one string in a mod (writes its .bcs.json)")
    ps.add_argument("mod", help="the mod folder")
    ps.add_argument("id", help="a string id (3) or label (IDS_START_DEMO)")
    ps.add_argument("text", help=r"the new text (\n for a new line)")
    ps.add_argument("--lang", default="en", help="language code (default: en)")
    ps = ssub.add_parser("unset", help="drop a mod's change to one string")
    ps.add_argument("mod")
    ps.add_argument("id")
    ps.add_argument("--lang", default="en")
    for ps in ssub.choices.values():
        game_opt(ps)
    p.set_defaults(func=cmd_strings)

    p = sub.add_parser("play", help="deploy the switched-on mods and start the recomp")
    game_opt(p)
    p.add_argument("--no-mods", action="store_true", help="start the game with mods off")
    p.add_argument("--deploy-only", action="store_true", help="deploy, don't start the game")
    p.add_argument("--library", help="the mod library folder (default: dr2 mod library)")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_play)

    p = sub.add_parser("help", help="read the modding guides here (dr2 help, dr2 help 05, "
                                    "dr2 help --search colour)")
    p.add_argument("topic", nargs="*", help="a page number, file name or word of its title")
    p.add_argument("--search", action="store_true", help="search every guide for the words")
    p.add_argument("--lang", default="en", help="help language (default: en)")
    p.set_defaults(func=cmd_help)

    p = sub.add_parser("studio", help="start DR2 Studio, the graphical browser")
    p.add_argument("files", nargs="*", help="a .dr2mod to install")
    p.add_argument("--map", metavar="LEVEL", help="open the Maps tab on this level "
                   "(prologue, living_research…; with -g for the game)")
    p.add_argument("--at", metavar="X,Y,Z[,HEADING]",
                   help="with --map: put the camera there (heading in degrees)")
    p.add_argument("--mod", metavar="FOLDER", help="open this mod")
    p.add_argument("--weapon", metavar="NAME", help="with --mod: open its wizard weapon")
    game_opt(p)
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
    p.add_argument("--variants", action="store_true",
                   help="also classify every model's parts as the game does (heads, "
                        "shirts…), and check every colour choice (phase 9)")
    p.add_argument("--levels", action="store_true",
                   help="also read every level: zones, placements, pieces (~1 min per game)")
    p.add_argument("--import", dest="imports", action="store_true",
                   help="also plan every item of each game into the other (phase 15's "
                        "importer: every name resolved, ~10 s; needs both games)")
    p.add_argument("--anims", action="store_true",
                   help="also read every animation (.anm): header, tracks, every key "
                        "(~30 s per game)")
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

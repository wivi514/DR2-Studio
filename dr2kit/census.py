"""Census: read every archive and entry of a game, and report what was found.

A census turns format guesses into facts (glossary: "Census"). It reads *all* of one
game's data, nested archives and compressed entries included, counts what it sees, and
**names everything it could not parse** (CLAUDE.md, hard-won rule 6): a census that
silently skips is how a claim from one family of files ends up stated as a rule.

The phase 1 gates are checks inside the census:

* **round trip**: every archive (on disk or nested) re-serialises to identical bytes;
* **decode**: every compressed entry decodes to exactly its ``size2``;
* **re-encode** (``reencode=True``, slow): every decoded entry, compressed again with the
  toolkit's encoder, decodes back to the same bytes;
* **Python cross-check** (``python_lzx=True``): the pure-Python decoder gives the same
  bytes as the native one, for every compressed entry.

Phase 2 adds textures (every entry starting ``05 01 01``):

* **texture parse**: every texture's header decodes, its format is known, and its layout
  fits in its payload (`dr2kit.formats.bct`); format, mip, cube and flag histograms;
* **texture re-encode** (``textures=True``, slower): every level of every texture,
  decoded to pixels and encoded again with the original blocks as reference, gives back
  the identical stored bytes (`dr2kit.convert.texture`). This is the phase 2
  "decode then re-encode" gate.

Phase 3 adds scenes (models and skeletons, every archive with a ``SceneHeader``):

* **scene parse** (always): every scene's skeleton, materials, meshes and command
  buffers parse (`dr2kit.formats.scene`); chunk names the reader doesn't use are counted;
* **model decode** (``models=True``): every draw of every mesh decodes: vertex types
  known, indices inside the draw's vertex range, normals of unit length (or zero),
  skin weights summing to 1, palettes inside the skeleton, unit quaternions. This is
  the phase 3 "every model parses" gate.

Phase 4 adds the writer gates:

* **scene rewrite** (always): every chunk the reader interprets, rebuilt from the parsed
  scene by `dr2kit.formats.scene_write`, equals the stored chunk (the no-op writer);
* **vertex re-encode** (``models=True``): every element of every vertex of every draw,
  decoded and encoded again, gives back the stored bytes;
* **re-import** (``reimport=True``, slow): every model exported to ``.glb`` and imported
  again (`dr2kit.convert.model_import`) gives back the identical file; and every shape,
  rebuilt from its own decoded geometry (new strips, buffers, packets, bounds), decodes
  to the same triangles with the same vertex values.

Phase 5 adds audio (``audio=True``, needs PyAV):

* **audio decode**: every `.xma` finds its metadata (its own RIFF header, or its
  ``cache.big`` stream-table record) and decodes to the length that metadata says
  (`dr2kit.convert.audio.length_check`: exact where a length is stored, the packet
  headers' frame total otherwise). Shapes, channels, rates and silent sounds are counted;
* **sfx tracks**: every `.sfx` parses (`dr2kit.formats.audioscript`) and every track's
  sample resolves to an entry of its bank; the ones the game data lacks are named;
* **first packets**: how many sounds share their first packet with a *different* sound
  (the recomp's audio substitution recognises a sound by that packet).

Phase 9 adds variants (``variants=True``, `dr2kit.convert.variants`):

* **shape groups**: every shape of every model is classified the way the game does
  (zombies) or by the prop-state name rules; no shape carries two numbers of one slot;
  shapes of zombie models that match no pattern, misplaced digits
  (``headwearShape2Deformed``) and environment pieces with variant-like shapes (burnt,
  damaged, LOD copies) are named; the slots of each zombie's detail levels are listed;
* **colour choices**: every material's choices by the name rule, and every choice the
  game's list (``zombie_pdv_variations.txt``) names is found in the shader bank and
  given by the rule.

Phase 10 adds levels (``levels=True``, `check_levels`; `dr2kit.formats.level`):

* **zones**: every level's ``zonelist.big`` parses, every zone's archive is there, and
  each zone record has the same bounds as the zone's own ``_ZONEINFO_``;
* **placements**: every record of every zone parses and writes back to the stored bytes;
  its quaternion has unit length; it names a piece of its zone, and every piece is
  placed (the exceptions are named); the bytes whose meaning is unknown hold the values
  seen so far (others named); and the world bounds it stores equal the piece's own
  bounds rotated, scaled and moved by it (the placement maths, worst error reported);
* **pieces**: every piece's scene parses, and every texture it names is found (the
  ones the game doesn't ship are listed);
* **collision** (`dr2kit.formats.collision`): every zone's shapes parse, counted by how
  they are placed (`convert.level.zone_collision`); those whose place is unknown are named;
* **level text files** (`dr2kit.formats.levelscript`, `dr2kit.convert.placed`): every
  script's ``.txt``, ``waypoint_`` and ``nm_`` files, ``items.txt`` and ``missions.txt``
  parse and write back to the same bytes; classes the toolkit doesn't know are named;
  every placed item and door finds its model and that model's scene parses; every
  navigation-mesh polygon names existing vertices;
* **level edits** (phase 11, `check_level_edits`; `dr2kit.formats.leveledits`): in every
  file a mod can edit (the scripts' files, ``missions.txt``, ``items.txt``,
  ``zombiesets.txt``), every block is written back by ``levelscript.render`` exactly as
  shipped (those that aren't, hand-edited, are named); and for a sample of blocks spread
  over each file, an ``.edits.json`` that changes a key, and (blocks in the tool's style)
  one that removes the block, one that adds a key and one that removes a key, each
  applied and then **reversed** (`leveledits.diff`), give the original file (byte for
  byte, or the same lines apart from blank ones where a file mixes gap sizes; both
  counted); and the meaning checks (`convert.levelcheck`) run on every shipped block,
  each finding named (the game's own data is the measure of a check that is too strict).

Results for both games are recorded in docs/formats.md. Run it with ``dr2 census``.
"""

from __future__ import annotations

import math
import os
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, FIRST_COMPLETED, wait
from dataclasses import dataclass, field

from .container import xcompress
from .container.big import BigArchive, is_big, STORED, LZX
from .container.lzx.pydecode import _Bits
from .container.vpath import AssetTree, entry_components, join
from .formats import bct as bctfmt
from .formats import scene as scenefmt
from .formats import scene_write
from .formats import vertex as vx

# A .bct texture starts 05 01 01; the 4th byte varies (a flags byte, phase 2 work), so
# only the first three are a magic (docs/formats.md, "Textures", retraction 2026-10-08).
BCT_MAGIC = b"\x05\x01\x01"

# Entry names that would break a vpath ('#', '/', '\\', leading '@', empty) or can't be a
# file name on Windows (`dr2 extract` writes entries as files). None exist in either game.
_UNSAFE_NAME = re.compile(r'^$|^@|[#/\\<>:"|?*\x00-\x1f]|[ .]$|'
                          r'^(con|prn|aux|nul|com\d|lpt\d)(\..*)?$', re.IGNORECASE)


def content_kind(data: bytes) -> str:
    """A rough label for an entry's (decoded) bytes, from its first bytes."""
    if not data:
        return "empty"
    if is_big(data):
        return "big"
    if data[:3] == BCT_MAGIC:
        return "bct"
    sample = data[:4096]
    printable = sum(1 for c in sample if c in (9, 10, 13) or 32 <= c < 127)
    if printable * 100 >= len(sample) * 95:
        return "text"
    return "binary"


@dataclass
class CensusReport:
    """Everything one census counted. ``problems`` is the list that must be empty."""
    game: str
    root: str
    files_by_ext: Counter = field(default_factory=Counter)
    archive_files: int = 0
    archives: int = 0
    archives_by_depth: Counter = field(default_factory=Counter)
    entries: int = 0
    entries_by_ext: Counter = field(default_factory=Counter)
    kind_by_ext: dict = field(default_factory=lambda: defaultdict(Counter))
    flags: Counter = field(default_factory=Counter)
    flags_by_ext: dict = field(default_factory=lambda: defaultdict(Counter))
    compression: Counter = field(default_factory=Counter)
    compressed_top_level: int = 0
    compressed_bytes_stored: int = 0
    compressed_bytes_unpacked: int = 0
    compressed_by_archive: Counter = field(default_factory=Counter)
    lzx_block_types: Counter = field(default_factory=Counter)
    lzx_chunk_padding: Counter = field(default_factory=Counter)
    lzx_chunks: int = 0
    decoded_ok: int = 0
    python_checked: int = 0
    reencoded_ok: int = 0
    reencode_ratio: list = field(default_factory=lambda: [0, 0])  # ours, shipped
    roundtrip_ok: int = 0
    hash_ok: int = 0
    zero_size: int = 0
    alignments: Counter = field(default_factory=Counter)
    bct_byte3: Counter = field(default_factory=Counter)  # 4th header byte of textures
    tex_parsed: int = 0
    tex_formats: Counter = field(default_factory=Counter)
    tex_format_by_suffix: dict = field(default_factory=lambda: defaultdict(Counter))
    tex_levels: Counter = field(default_factory=Counter)
    tex_versions: Counter = field(default_factory=Counter)
    tex_cubes: int = 0
    tex_npot: int = 0
    tex_npot_mipped: int = 0
    tex_size_model: Counter = field(default_factory=Counter)   # exact / larger / SMALLER
    tex_largest: tuple = (0, 0, "")
    tex_reencoded_ok: int = 0
    scenes: Counter = field(default_factory=Counter)          # model / skeleton
    scene_nodes: int = 0
    scene_meshes: int = 0
    scene_draws: int = 0
    scene_draws_decoded: int = 0
    scene_vertices: int = 0
    scene_triangles: int = 0
    scene_unused_chunks: Counter = field(default_factory=Counter)
    scene_vertex_types: Counter = field(default_factory=Counter)
    scene_buffers: Counter = field(default_factory=Counter)   # own / combined / animated
    scene_checks: Counter = field(default_factory=Counter)    # named measurements
    audio_shapes: Counter = field(default_factory=Counter)    # riff / raw (+ loop)
    audio_channels: Counter = field(default_factory=Counter)
    audio_rates: Counter = field(default_factory=Counter)
    audio_decoded_ok: int = 0
    audio_seconds: float = 0.0
    audio_silent: list = field(default_factory=list)
    audio_shared_first: int = 0
    sfx_parsed: int = 0
    sfx_tracks: Counter = field(default_factory=Counter)      # xma / sfx / missing
    sfx_missing: list = field(default_factory=list)
    movies: int = 0                                           # .bik decoded (with --audio)
    movie_seconds: float = 0.0
    string_banks: int = 0                                     # .bcs parsed and rewritten
    strings: Counter = field(default_factory=Counter)         # bank -> string count
    duplicate_name_archives: int = 0
    duplicate_name_entries: int = 0
    unsafe_names: list = field(default_factory=list)
    problems: list = field(default_factory=list)   # (vpath, what went wrong)
    # variants (phase 9)
    var_models: Counter = field(default_factory=Counter)      # zombie / prop states / none
    var_groups: Counter = field(default_factory=Counter)      # parts per group kind
    var_unmatched: list = field(default_factory=list)         # zombie shapes: '*' only
    var_misplaced: list = field(default_factory=list)
    var_env: list = field(default_factory=list)               # environment, variant-like
    var_levels: dict = field(default_factory=dict)            # zombie -> {level: slots}
    colour_materials: int = 0
    colour_choices: int = 0
    colour_listed: int = 0                                    # list entries found by the rule
    # levels (phase 10)
    levels: dict = field(default_factory=dict)                # level -> {zones, pieces, …}
    level_counts: Counter = field(default_factory=Counter)    # named measurements
    level_bounds_error: float = 0.0                           # worst placement-maths error, m
    level_notes: list = field(default_factory=list)           # named, not problems
    seconds: float = 0.0
    lzx_backend: str = ""

    def to_json(self) -> dict:
        """A plain-dict copy for ``--json`` (Counters become dicts)."""
        out = {}
        for k, v in self.__dict__.items():
            if isinstance(v, defaultdict):
                out[k] = {a: dict(b) for a, b in v.items()}
            elif isinstance(v, Counter):
                out[k] = {str(a): b for a, b in v.items()}
            else:
                out[k] = v
        return out


def _first_block_type(stream: bytes) -> int:
    b = _Bits(stream[:8])
    b.read(1)               # Intel E8 flag
    return b.read(3)


def texture_suffix(name: str) -> str:
    """The role suffix of a texture name (``_cm``, ``_nm``…), lower-case, or ``(none)``."""
    stem = name.rsplit(".", 1)[0] if name.lower().endswith(".bct") else name
    head, sep, tail = stem.rpartition("_")
    return f"_{tail.lower()}" if sep and head and 1 <= len(tail) <= 3 and tail.isalpha() else "(none)"


def check_texture(rep: "CensusReport", evp: str, name: str, data: bytes,
                  reencode: bool) -> None:
    """Parse one texture into the report; with ``reencode``, run the re-encode gate."""
    try:
        tex = bctfmt.Bct.parse(data, evp)
    except Exception as ex:  # noqa: BLE001 - reported
        rep.problems.append((evp, f"texture: {ex}"))
        return
    h = tex.header
    rep.tex_parsed += 1
    rep.tex_formats[tex.format.name] += 1
    rep.tex_format_by_suffix[texture_suffix(name)][tex.format.name] += 1
    rep.tex_levels[h.levels] += 1
    rep.tex_versions[f"{h.version:#04x}"] += 1
    rep.tex_cubes += h.is_cube
    npot = (h.width & (h.width - 1)) or (h.height & (h.height - 1))
    if npot:
        rep.tex_npot += 1
        rep.tex_npot_mipped += h.levels > 1
    model = bctfmt.model_data_size(h)
    rep.tex_size_model["exact" if model == h.data_size else
                       "larger" if h.data_size > model else "SMALLER"] += 1
    if model > h.data_size:
        rep.problems.append((evp, f"texture: payload {h.data_size:#x} smaller than the "
                                  f"layout model {model:#x}"))
    if h.width * h.height > rep.tex_largest[0] * rep.tex_largest[1]:
        rep.tex_largest = (h.width, h.height, evp)
    if reencode:
        from .convert.texture import decode_level, encode_level
        try:
            for lv in tex.levels():
                stored = tex.untile(lv)
                again = encode_level(tex, lv, decode_level(tex, lv))
                if again != stored:
                    rep.problems.append((evp, f"texture re-encode: level {lv.level} face "
                                              f"{lv.face} differs"))
                    return
            out = bctfmt.Bct(tex.header, bytearray(tex.payload), evp)
            for lv in tex.levels():
                out.set_level(lv, tex.untile(lv))
            if out.to_bytes() != data:
                rep.problems.append((evp, "texture re-tile: file differs"))
                return
            rep.tex_reencoded_ok += 1
        except Exception as ex:  # noqa: BLE001 - reported
            rep.problems.append((evp, f"texture re-encode: {ex}"))


def run_census(game: str, tree: AssetTree, *, python_lzx: bool = False,
               reencode: bool = False, textures: bool = False, models: bool = False,
               reimport: bool = False, audio: bool = False, workers: int | None = None,
               progress=None, variants: bool = False, levels: bool = False) -> CensusReport:
    """Census one game's data folder. See the module docstring for what is checked.

    ``progress(message)`` is called once per file on disk. ``workers`` sets the process
    count for ``reencode`` (default: all CPUs).
    """
    from .container import lzx
    t0 = time.time()
    rep = CensusReport(game, str(tree.root), lzx_backend=lzx.backend_detail())
    var_ctx = None
    if variants:
        from .convert import variants as cvar
        var_ctx = (cvar.Classifier.for_game(game), cvar.ColourBank(tree, game), game, set())
    pool = ProcessPoolExecutor(max_workers=workers or os.cpu_count()) if reencode else None
    pending: set = set()
    audio_pool = None
    audio_pending: set = set()
    first_packets: dict = {}            # sha1 of a stream's first packet -> sound sha1s
    if audio:
        from .convert.audio import AudioLookup, have_decoder
        if not have_decoder():
            from .convert.audio import AudioBackendMissing
            raise AudioBackendMissing("census --audio needs PyAV with the xma2 decoder "
                                      "(pip install av)")
        lookup = AudioLookup(tree)
        audio_pool = ProcessPoolExecutor(max_workers=workers or os.cpu_count())

    def drain_audio(limit: int) -> None:
        nonlocal audio_pending
        while len(audio_pending) > limit:
            done, audio_pending = wait(audio_pending, return_when=FIRST_COMPLETED)
            for f in done:
                try:
                    err, frames, peak = f.result()
                except Exception as e:  # noqa: BLE001 - reported
                    err, frames, peak = f"decode: {e}", 0, 0.0
                if err:
                    rep.problems.append((f.vp, f"audio: {err}"))
                    continue
                rep.audio_decoded_ok += 1
                rep.audio_seconds += frames / f.rate
                if peak == 0.0:
                    rep.audio_silent.append(f.vp)

    def check_audio(evp: str, data: bytes) -> None:
        import hashlib
        from .formats import xma as xmafmt
        try:
            info = lookup.info(evp, data)
        except Exception as ex:  # noqa: BLE001 - reported
            rep.problems.append((evp, f"audio metadata: {ex}"))
            return
        rep.audio_shapes[info.shape + (" looped" if info.loop_length else "")] += 1
        rep.audio_channels[info.channels] += 1
        rep.audio_rates[info.rate] += 1
        pk = data[info.packets_offset:info.packets_offset + info.packets_size]
        sound = hashlib.sha1(pk).digest()
        for i in xmafmt.stream_starts(pk, info.streams):
            key = hashlib.sha1(pk[i * xmafmt.PACKET:(i + 1) * xmafmt.PACKET]).digest()
            first_packets.setdefault(key, set()).add(sound)
        fut = audio_pool.submit(_audio_job, data, info)
        fut.vp, fut.rate = evp, info.rate
        audio_pending.add(fut)
        drain_audio(256)

    def check_sfx(evp: str, data: bytes, arc_names: set) -> None:
        from .formats import audioscript
        try:
            tracks = audioscript.sfx_tracks(data.decode("latin-1"), evp)
        except Exception as ex:  # noqa: BLE001 - reported
            rep.problems.append((evp, f"sfx: {ex}"))
            return
        rep.sfx_parsed += 1
        for t in tracks:
            if t.lower() in arc_names:
                rep.sfx_tracks[t.rsplit(".", 1)[1]] += 1
            else:
                rep.sfx_tracks["missing"] += 1
                rep.sfx_missing.append(f"{evp} -> {t}")

    def drain(limit: int) -> None:
        nonlocal pending
        while len(pending) > limit:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for f in done:
                vp, shipped = f.vp, f.shipped
                try:
                    ours = f.result()
                    rep.reencoded_ok += 1
                    rep.reencode_ratio[0] += ours
                    rep.reencode_ratio[1] += shipped
                except Exception as e:  # noqa: BLE001 - reported
                    rep.problems.append((vp, f"re-encode: {e}"))

    def visit(arc: BigArchive, original: bytes, vp: str, depth: int) -> None:
        rep.archives += 1
        rep.archives_by_depth[depth] += 1
        if arc.to_bytes() == original:
            rep.roundtrip_ok += 1
        else:
            rep.problems.append((vp, "round trip: re-written archive differs"))
        comps = entry_components(arc)
        names = Counter(e.name.lower() for e in arc.entries)
        name_set = set(names)
        dups = sum(n - 1 for n in names.values() if n > 1)
        if dups:
            rep.duplicate_name_archives += 1
            rep.duplicate_name_entries += dups
        for comp, e in zip(comps, arc.entries):
            evp = join(vp, comp)
            rep.entries += 1
            ext = e.ext or "(none)"
            rep.entries_by_ext[ext] += 1
            rep.flags[f"{e.flags:#x}"] += 1
            rep.flags_by_ext[f"{e.flags:#x}"][ext] += 1
            rep.compression[e.compression] += 1
            if e.size:
                rep.alignments[e.alignment] += 1
            else:
                rep.zero_size += 1
            if e.hash == e.computed_hash():
                rep.hash_ok += 1
            else:
                rep.problems.append((evp, f"hash {e.hash:08X} != engine hash of the "
                                          f"lower-cased name {e.computed_hash():08X}"))
            if _UNSAFE_NAME.search(e.name):
                rep.unsafe_names.append(evp)
            if e.compression == STORED:
                data = e.stored
                if e.size != e.size2:
                    rep.problems.append((evp, f"stored entry with size {e.size} != "
                                              f"size2 {e.size2}"))
            elif e.compression == LZX:
                rep.compressed_by_archive[vp] += 1
                if depth == 0:
                    rep.compressed_top_level += 1
                rep.compressed_bytes_stored += e.size
                rep.compressed_bytes_unpacked += e.size2
                try:
                    info = xcompress.parse_stream(e.stored, evp)
                    for c in info.chunks:
                        rep.lzx_chunks += 1
                        rep.lzx_chunk_padding[c.padding] += 1
                        rep.lzx_block_types[_first_block_type(
                            e.stored[c.offset:c.offset + c.compressed])] += 1
                    data = e.data()
                    rep.decoded_ok += 1
                except Exception as ex:  # noqa: BLE001 - reported
                    rep.problems.append((evp, f"decode: {ex}"))
                    continue
                if python_lzx:
                    try:
                        if e.data(python_lzx=True) != data:
                            rep.problems.append((evp, "pure-Python LZX gives different bytes"))
                        else:
                            rep.python_checked += 1
                    except Exception as ex:  # noqa: BLE001 - reported
                        rep.problems.append((evp, f"pure-Python LZX: {ex}"))
                if pool is not None:
                    fut = pool.submit(_reencode_job, data)
                    fut.vp, fut.shipped = evp, e.size
                    pending.add(fut)
                    drain(64)
            else:
                rep.problems.append((evp, f"unknown compression marker {e.compression}"))
                continue
            kind = content_kind(data)
            rep.kind_by_ext[ext][kind] += 1
            if audio and ext == "xma":
                check_audio(evp, data)
            elif audio and ext == "sfx":
                check_sfx(evp, data, name_set)
            if kind == "bct":
                rep.bct_byte3[f"{data[3]:02X}"] += 1
                check_texture(rep, evp, e.name, data, textures)
            if kind == "big":
                try:
                    sub = BigArchive.parse(data, evp)
                except Exception as ex:  # noqa: BLE001 - reported
                    rep.problems.append((evp, f"nested archive: {ex}"))
                    continue
                visit(sub, data, evp, depth + 1)
        if scenefmt.is_scene(arc):
            check_scene(rep, vp, arc, models or reimport, reimport, var_ctx)

    try:
        for vp, path in tree.files():
            ext = path.suffix.lower().lstrip(".") or "(none)"
            rep.files_by_ext[ext] += 1
            raw = path.read_bytes()
            if ext == "bcs":                # a string bank (formats/bcs.py)
                check_bcs(rep, vp, raw)
                continue
            if ext == "bik" and audio:      # a movie (convert/video.py)
                check_movie(rep, vp, path)
                continue
            if raw[:3] == BCT_MAGIC:       # a loose texture on disk
                rep.bct_byte3[f"{raw[3]:02X}"] += 1
                check_texture(rep, vp, path.name, raw, textures)
                continue
            if not is_big(raw):
                continue
            rep.archive_files += 1
            if progress:
                progress(vp)
            try:
                arc = BigArchive.parse(raw, vp)
            except Exception as ex:  # noqa: BLE001 - reported
                rep.problems.append((vp, f"parse: {ex}"))
                continue
            visit(arc, raw, vp, 0)
        drain(0)
        if var_ctx is not None:
            check_colour_list(rep, var_ctx)
        if levels:
            check_levels(rep, tree, game)
        if audio_pool is not None:
            drain_audio(0)
            rep.audio_shared_first = sum(1 for v in first_packets.values() if len(v) > 1)
    finally:
        if pool is not None:
            pool.shutdown(cancel_futures=True)
        if audio_pool is not None:
            audio_pool.shutdown(cancel_futures=True)
    rep.seconds = time.time() - t0
    return rep


_NUMBERS = re.compile(r"\d+")

# How far a placement's stored world bounds may be from the piece's own bounds placed by
# it: the stored values are float32 and the pieces sit up to ~900 m from the origin.
LEVEL_BOUNDS_TOLERANCE = 0.01


def piece_bounds(sc) -> list[tuple[float, float, float]]:
    """The 8 corners of every shape's stored bounds (`convert.level.piece_corners`)."""
    from .convert.level import piece_corners
    return piece_corners(sc)


def piece_vertices(sc) -> list[tuple[float, float, float]]:
    """Every vertex of every shape, in the piece's own space (rigid shapes through
    their node's rest matrix)."""
    world = sc.skeleton.world_matrices() if sc.skeleton.nodes else []
    out = []
    for m in sc.meshes:
        n = sc.rigid_node(m)
        mat = world[n] if n is not None else [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]]
        for d in m.draws:
            for c in sc.draw_data(d, m.name).positions:
                out.append(tuple(sum(mat[i][j] * c[j] for j in range(3)) + mat[i][3]
                                 for i in range(3)))
    return out


def check_level_scripts(rep: CensusReport, tree: AssetTree) -> None:
    """The level text files (module docstring); counts in ``rep.level_counts``."""
    from .convert import placed
    from .convert.model import read_scene
    from .formats.levelscript import Document
    lc = rep.level_counts
    for name in ("items.txt", "missions.txt"):
        try:
            raw = tree.resolve(f"{placed.DATAFILE}/{name}").data()
        except Exception:  # noqa: BLE001 - a game without it: nothing to check
            continue
        try:
            same = Document.parse(raw, name).to_bytes() == raw
        except Exception as ex:  # noqa: BLE001 - reported
            rep.problems.append((f"{placed.DATAFILE}/{name}", f"text: {ex}"))
            continue
        if not same:
            rep.problems.append((f"{placed.DATAFILE}/{name}", "text: written back, it differs"))
        lc["text files read and written back"] += 1
    models = placed.ItemModels(tree)
    scenes_ok: dict[str, bool] = {}
    for name in placed.script_names(tree):
        try:
            ls = placed.read_script(tree, name, models)
        except Exception as ex:  # noqa: BLE001 - reported
            rep.problems.append((f"{placed.DATAFILE}/{name}.txt", f"level script: {ex}"))
            continue
        for fname, doc in ls.documents.items():
            raw = tree.resolve(f"{placed.DATAFILE}/{fname}").data()
            if doc.to_bytes() != raw:
                rep.problems.append((f"{placed.DATAFILE}/{fname}", "text: written back, it differs"))
            lc["text files read and written back"] += 1
        for cls, n in ls.unknown.items():
            rep.level_notes.append(f"{name}: {n} × {cls} (a class the Maps tab doesn't draw)")
        info = rep.levels.setdefault(f"script {name}", Counter())
        info.update(ls.counts())
        for t in ls.things:
            if not t.item:
                continue
            if t.model is None:
                lc["items without a model"] += 1
                rep.problems.append((f"{placed.DATAFILE}/{name}.txt",
                                     f"{t.name}: {t.item}: {models.why.get(t.item.lower())}"))
                continue
            if t.model not in scenes_ok:
                try:
                    read_scene(tree, t.model)
                    scenes_ok[t.model] = True
                except Exception as ex:  # noqa: BLE001 - reported
                    scenes_ok[t.model] = False
                    rep.problems.append((t.model, f"item model: {ex}"))
            lc["items and doors with their model" if scenes_ok[t.model]
               else "items and doors whose model fails"] += 1
            if t.position is None:
                rep.problems.append((f"{placed.DATAFILE}/{t.file}", f"{t.name}: no Location"))
        lc["item models (different scenes)"] = len(scenes_ok)
        if ls.navmesh:
            lc["navigation polygons"] += len(ls.navmesh.polygons)


def check_level_edits(rep: CensusReport, tree: AssetTree, sample: int = 30) -> None:
    """The level-edit gate (module docstring); counts in ``rep.level_counts``."""
    from .convert import placed
    from .formats import leveledits as le
    from .formats.levelscript import Document, render_block
    lc = rep.level_counts
    names = ["missions.txt", "items.txt", "zombiesets.txt"]
    for s in placed.script_names(tree):
        names += [f"{s}.txt", f"waypoint_{s}.txt", f"nm_{s}.txt"]

    def same(a: bytes, b: bytes) -> str:
        if a == b:
            return "identical"
        strip = [ln for ln in a.splitlines() if ln.strip()], \
            [ln for ln in b.splitlines() if ln.strip()]
        return "same apart from blank lines" if strip[0] == strip[1] else "differs"

    from .convert import levelcheck
    facts = levelcheck.GameFacts(tree)
    for name in names:
        vp = f"{placed.DATAFILE}/{name}"
        try:
            raw = tree.resolve(vp).data()
        except Exception:  # noqa: BLE001 - a script without that file
            continue
        doc = Document.parse(raw, name)
        blocks = list(doc.walk())
        # the meaning checks on the game's own blocks: what they'd refuse in a mod
        for b in blocks:
            level = levelcheck._level_of(doc, doc.path(b)) \
                if name == "missions.txt" and "Zombie" in b.cls else None
            for f in levelcheck._check_block(facts, doc.path(b), b, level):
                lc["shipped blocks the level checks " + ("refuse" if f.error
                                                         else "warn about")] += 1
                rep.level_notes.append(f"{name}: {f} (shipped)")
        styled = set()
        for b in blocks:
            depth = len(doc.lines[b.line]) - len(doc.lines[b.line].lstrip("\t"))
            if "".join(render_block(b, depth, doc.newline)) == doc.text(b):
                lc["blocks written back by render"] += 1
                styled.add(id(b))
            else:
                lc["blocks not in the tool's style (hand-edited)"] += 1
                rep.level_notes.append(f"{name}: {doc.path(b)} is not in the tool's style "
                                       f"(written back as is unless edited)")
        step = max(1, len(blocks) // sample)
        for b in blocks[::step]:
            path = doc.path(b)
            if doc.get(path) is not b:                 # not addressable (a repeated path)
                lc["sampled blocks with a repeated path (skipped)"] += 1
                continue
            # a hand-edited block is changed key by key only: removed and added back it
            # would come back in the tool's style
            tries = [le.Edits(set={path: {b.props[0].key: b.props[0].value + "1"}})] \
                if b.props else []
            if id(b) in styled:
                tries.append(le.Edits(remove=[path]))
                tries.append(le.Edits(set={path: {"Dr2kitGateKey": "1"}}))
                if b.props:
                    tries.append(le.Edits(set={path: {b.props[0].key: None}}))
            for e in tries:
                try:
                    d = Document.parse(raw, name)
                    le.apply(d, e)
                    edited = d.to_bytes()
                    d2 = Document.parse(edited, name)
                    le.apply(d2, le.diff(d2, doc))
                    verdict = same(d2.to_bytes(), raw)
                except Exception as ex:  # noqa: BLE001 - reported
                    verdict = "differs"
                    rep.problems.append((vp, f"level edit of {path}: {ex}"))
                lc[f"level edits applied and reversed: {verdict}"] += 1
                if verdict == "differs":
                    rep.problems.append((vp, f"level edit of {path}: reversed, it differs"))


def check_levels(rep: CensusReport, tree: AssetTree, game: str) -> None:
    """The phase 10 level census (module docstring); results in ``rep.levels``."""
    from .convert import level as clevel
    check_level_scripts(rep, tree)
    from .convert.model import TextureFinder, read_scene
    from .formats import level as lvlfmt
    check_level_edits(rep, tree)
    lc = rep.level_counts
    for L in clevel.list_levels(tree):
        info = rep.levels.setdefault(L.name, Counter())
        info["zones"] += len(L.zones)
        for z in L.zones:
            try:
                zd = L.zone(z)
            except Exception as ex:  # noqa: BLE001 - reported
                rep.problems.append((f"{L.vpath}/{z.zone}", f"zone: {ex}"))
                continue
            org = zd.organization
            if org.info is None or any(abs(a - b) > 1e-3 for a, b in zip(
                    org.info, (*z.bounds_min, *z.bounds_max, *z.centre, z.radius))):
                rep.level_notes.append(f"{zd.vpath}: _ZONEINFO_ differs from the zone list")
                lc["zone info differs from the zone list"] += 1
            else:
                lc["zone info = zone list"] += 1
            if org.dynamic:
                rep.level_notes.append(f"{zd.vpath}: {len(org.dynamic)} bytes of dynamic placements")
            stored = tree.resolve(f"{zd.vpath}/{clevel.ORGANIZATION}/ModelInstanceArray").data()
            if org.placements_bytes() != stored:
                rep.problems.append((zd.vpath, "placements: written back, they differ"))
            for name in zd.missing:
                rep.problems.append((zd.vpath, f"placement names no piece: {name}"))
            for name in zd.unplaced:
                rep.level_notes.append(f"{zd.vpath}: piece {name} is never placed")
                lc["pieces never placed"] += 1
            info["pieces"] += len(zd.pieces)
            info["placements"] += len(zd.placements)
            scenes = {}
            for p in zd.placements:
                lc["placements"] += 1
                q = math.sqrt(sum(c * c for c in p.rotation))
                if abs(q - 1) > 1e-4:          # CW glower_fl: 1.017 (drawn normalised)
                    lc["rotation not of unit length"] += 1
                    rep.level_notes.append(f"{zd.vpath}: {p.piece}: rotation of length "
                                           f"{q:.5f} (drawn normalised)")
                lc["scale 1,1,1" if p.scale == (1.0, 1.0, 1.0) else "scale other"] += 1
                lc["rotated" if p.rotation[:3] != (0.0, 0.0, 0.0) else "not rotated"] += 1
                if p.name2 != p.piece:
                    lc["second name differs"] += 1
                    rep.level_notes.append(f"{zd.vpath}: {p.piece} / {p.name2}")
                lc[f"flags {p.flags:#x}"] += 1
                if p.flags not in lvlfmt.FLAG_VALUES:
                    rep.level_notes.append(f"{zd.vpath}: {p.piece}: flags {p.flags:#x}")
                if p.tail != lvlfmt.EXPECTED_TAIL:
                    lc["unknown bytes not as seen"] += 1
                    rep.level_notes.append(f"{zd.vpath}: {p.piece}: unknown bytes "
                                           f"{p.tail.hex()}")
                name = clevel.piece_name(p, zd)
                if name is None:
                    continue
                if name not in scenes:
                    try:
                        scenes[name] = read_scene(tree, zd.pieces[name])
                    except Exception as ex:  # noqa: BLE001 - reported
                        rep.problems.append((zd.pieces[name], f"piece: {ex}"))
                        scenes[name] = None
                sc = scenes[name]
                if sc is None:
                    continue
                pts = [p.to_world(c) for c in piece_bounds(sc)]
                if not pts:
                    lc["pieces with no shapes"] += 1
                    continue
                lo = [min(c[i] for c in pts) for i in range(3)]
                hi = [max(c[i] for c in pts) for i in range(3)]
                err = max(max(abs(a - b) for a, b in zip(lo, p.bounds_min)),
                          max(abs(a - b) for a, b in zip(hi, p.bounds_max)))
                if err <= LEVEL_BOUNDS_TOLERANCE:
                    rep.level_bounds_error = max(rep.level_bounds_error, err)
                    lc["placed bounds = stored bounds"] += 1
                    continue
                # Some pieces' shapes store bounds that don't fit their own vertices; the
                # placement's bounds then hold the placed vertices, with room to spare.
                pts = [p.to_world(c) for c in piece_vertices(sc)]
                out = max([b - a for a, b in zip((min(c[i] for c in pts) for i in range(3)),
                                                 p.bounds_min)] +
                          [a - b for a, b in zip((max(c[i] for c in pts) for i in range(3)),
                                                 p.bounds_max)])
                if out <= LEVEL_BOUNDS_TOLERANCE:
                    lc["placed vertices inside the stored bounds (loose shape bounds)"] += 1
                else:
                    lc["placed vertices outside the stored bounds"] += 1
                    rep.level_notes.append(f"{zd.pieces[name]}: placed vertices {out:.2f} m "
                                           f"outside the stored bounds (unexplained)")
            try:
                col = clevel.zone_collision(tree, zd)
            except Exception as ex:  # noqa: BLE001 - reported
                rep.problems.append((f"{zd.vpath}/MERGED_COLLISION.big", f"collision: {ex}"))
            else:
                for rule, n in col.shapes.items():
                    lc[f"collision shapes placed: {rule}"] += n
                lc["collision triangles"] += len(col.triangles)
                for name in col.unplaced:
                    lc["collision shapes not placed (piece unknown)"] += 1
                    rep.level_notes.append(f"{zd.vpath}: collision shape {name}: "
                                           f"its piece is unknown, left out")
            for name, sc in scenes.items():
                if sc is None:
                    continue
                lc["pieces read"] += 1
                finder = TextureFinder(tree, zd.pieces[name], game)
                for m in sc.materials:
                    for slot in m.slots:
                        if slot.engine:
                            continue
                        lc["texture names"] += 1
                        if finder.bct(slot.name) is None:
                            info["textures missing"] += 1
                            rep.level_notes.append(f"{zd.pieces[name]}: texture {slot.name} "
                                                   f"is not in the game")
                        elif "_lod.tex/" in finder.found[slot.name].lower():
                            lc["textures found only small (_LOD)"] += 1


def check_movie(rep: CensusReport, vp: str, path) -> None:
    """A Bink movie must decode: every frame, and a sound as long as the pictures."""
    from .convert import video
    try:
        info = video.probe(path)
        n = sum(1 for _ in video.frames(path))
        if abs(n - info.frames) > 1:
            rep.problems.append((vp, f"movie: {n} frames decoded, {info.frames} expected"))
            return
        if info.audio_tracks:
            pcm = video.audio(path)
            if abs(pcm.seconds - info.seconds) > 0.25:
                rep.problems.append((vp, f"movie: sound lasts {pcm.seconds:.2f} s, pictures "
                                         f"{info.seconds:.2f} s"))
                return
    except Exception as ex:  # noqa: BLE001 - reported
        rep.problems.append((vp, f"movie: {ex}"))
        return
    rep.movies += 1
    rep.movie_seconds += info.seconds


def check_bcs(rep: CensusReport, vp: str, raw: bytes) -> None:
    """A string bank must parse and write back to the same bytes."""
    from .formats.bcs import StringBank, bank_name
    try:
        bank = StringBank.parse(raw, vp)
    except Exception as ex:  # noqa: BLE001 - reported
        rep.problems.append((vp, f"string bank: {ex}"))
        return
    if bank.to_bytes() != raw:
        rep.problems.append((vp, "string bank: re-written bank differs"))
        return
    rep.string_banks += 1
    rep.strings[bank_name(vp)] = len(bank.strings)


# burnt, damaged, broken or lower-detail copies by name (not "blackjack", "clod"…)
_VARIANT_LIKE = re.compile(r"_black(?:shape|_|\d|$)|_dmg|broken|(?:^|_)lod(?:\d|_|shape|$)",
                           re.IGNORECASE)


def check_variants(rep: CensusReport, vp: str, sc, ctx) -> None:
    """The phase 9 variant census of one model (module docstring)."""
    from .convert import variants as cvar
    classifier, bank, game, seen_own = ctx
    mv = cvar.model_variants(sc, game, classifier)
    rep.var_models["zombie (the game's table)" if mv.zombie else
                   "prop states" if mv.states else "no variants"] += 1
    low = vp.lower()
    for p in mv.parts:
        kind = (p.group.rsplit(" ", 1)[0] if p.group[-1:].isdigit() else p.group)
        rep.var_groups[kind] += 1
        if mv.zombie and p.bits == cvar.DEFAULT_BIT:
            rep.var_unmatched.append(f"{vp}: {p.name}")
        if p.misplaced:
            rep.var_misplaced.append(f"{vp}: {p.name}")
        if mv.zombie:
            for slot in cvar.SLOTS:
                if bin(p.bits & slot.all_bits).count("1") > 1:
                    rep.problems.append((vp, f"variants: {p.name} has two {slot.label} numbers"))
    if "/environment/" in low:
        odd = [m.name for m in sc.meshes if _VARIANT_LIKE.search(m.name)]
        if odd:
            rep.var_env.append(f"{vp}: {', '.join(odd[:4])}{'…' if len(odd) > 4 else ''}")
    m = re.search(r"zombies\.big/[^/]+/([^/]+)_(\d)\.big$", low)
    if m and mv.zombie:
        rep.var_levels.setdefault(m.group(1), {})[m.group(2)] = {
            k: v for k, v in mv.slots.items()}
    try:
        cols = cvar.colour_choices(sc, bank)
    except Exception as ex:  # noqa: BLE001 - reported
        rep.problems.append((vp, f"colour choices: {ex}"))
        return
    for c in cols:
        rep.colour_materials += 1
        rep.colour_choices += len(c.options)
        for name in c.options:
            if bank.valueset(name) is None:
                rep.problems.append((vp, f"colour choice {name}: no such value set"))
        seen_own.add(c.own)


def check_colour_list(rep: CensusReport, ctx) -> None:
    """Every choice the game's list names is in the bank and given by the name rule."""
    from .convert import variants as cvar
    _cls, bank, _game, _seen = ctx
    listed = bank.listed() or {}
    names = list(bank.names())
    for model, table in listed.items():
        for own, alts in table.items():
            rule = cvar.colour_rule(own, names)
            for a in alts:
                if a not in bank.names():
                    rep.problems.append((model, f"colour list: {a} is not in the shader bank"))
                elif a in rule:
                    rep.colour_listed += 1
                else:
                    rep.problems.append((model, f"colour list: {a} is not found by the name "
                                                f"rule for {own}"))


def check_scene(rep: CensusReport, vp: str, arc: BigArchive, decode: bool,
                reimport: bool = False, variants=None) -> None:
    """Parse one scene (and, with ``decode``, every draw); count and check what it holds.
    ``reimport`` adds the phase 4 re-import gates (`check_reimport`); ``variants`` (a
    context from `run_census`) the phase 9 variant census (`check_variants`)."""
    import math
    try:
        sc = scenefmt.Scene.from_archive(arc, vp)
    except Exception as ex:  # noqa: BLE001 - reported
        rep.problems.append((vp, f"scene: {ex}"))
        return
    rep.scenes[sc.kind] += 1
    rewrite = scene_write.rewrite_problems(sc)
    rep.scene_checks["scene rewrite identical" if not rewrite else "scene rewrite differs"] += 1
    for pr in rewrite:
        rep.problems.append((vp, f"scene rewrite: {pr}"))
    rep.scene_nodes += len(sc.skeleton)
    for name in sc.unknown:
        rep.scene_unused_chunks[_NUMBERS.sub("N", name)] += 1
    chk = rep.scene_checks
    if sc.description and sc.header[3] != len(sc.description):
        rep.problems.append((vp, f"SceneHeader word 3 = {sc.header[3]}, "
                                 f"SceneDescription has {len(sc.description)} records"))
    if sc.hierarchy and sorted(sc.hierarchy) != sorted((n.index, n.parent)
                                                       for n in sc.skeleton.nodes):
        rep.problems.append((vp, "_BONEHIERARCHY_ pairs differ from the node records"))
    for n in sc.skeleton.nodes:
        chk["node quaternion unit" if abs(scenefmt.unit_norm(n.rotation) - 1) < 1e-3
            else "node quaternion NOT unit"] += 1
        if n.parent == n.index:
            chk["node is its own parent (split-rig root)"] += 1
    for m in sc.meshes:
        rep.scene_meshes += 1
        if m.words[5] != len(m.draws):
            rep.problems.append((f"{vp}/{m.name}", f"shape word 5 = {m.words[5]}, "
                                                   f"{len(m.draws)} draws"))
        for d in m.draws:
            rep.scene_draws += 1
            for e in d.declaration:
                t = e.vtype
                rep.scene_vertex_types[f"{t.name if t else hex(e.type)} {e.usage_name}"] += 1
            for s in d.streams.values():
                rep.scene_buffers["run-time (animated)" if s.buffer is None else
                                  "combined" if s.buffer.startswith("Combined") else "own"] += 1
            if sc.materials and d.material < 0:
                rep.problems.append((f"{vp}/{m.name}", f"draw {d.number}: no material has "
                                                       f"id {d.strip[0] + 1}"))
            if len({mt.id for mt in sc.materials}) != len(sc.materials):
                rep.problems.append((vp, "two materials share an id"))
            if d.skinned and d.palette_start + d.palette_count > len(sc.skeleton):
                rep.problems.append((f"{vp}/{m.name}", f"draw {d.number}: palette "
                                                       f"{d.palette_start}+{d.palette_count} "
                                                       f"outside {len(sc.skeleton)} nodes"))
            if not decode:
                continue
            try:
                dd = sc.draw_data(d, m.name)
            except Exception as ex:  # noqa: BLE001 - reported
                rep.problems.append((f"{vp}/{m.name}", f"draw {d.number}: {ex}"))
                continue
            rep.scene_draws_decoded += 1
            rep.scene_vertices += len(dd.positions)
            rep.scene_triangles += len(dd.triangles)
            chk["draws with index count not a multiple of 3 (strips)"] += d.index_count % 3 != 0
            for p in dd.positions:
                if not all(math.isfinite(c) for c in p):
                    rep.problems.append((f"{vp}/{m.name}", f"draw {d.number}: non-finite position"))
                    break
            for n in dd.normals or ():
                ln = math.sqrt(sum(c * c for c in n))
                chk["normal unit" if abs(ln - 1) < 0.02 else
                    "normal zero" if ln < 1e-3 else "normal NOT unit"] += 1
            for w in dd.weights or ():
                chk["skin weights sum to 1" if abs(sum(w) - 1) < 0.005
                    else "skin weights do NOT sum to 1"] += 1
            bad = _reencode_vertices(sc, d)
            chk["vertex elements re-encode identically" if not bad
                else "vertex elements re-encode DIFFERENTLY"] += 1
            if bad:
                rep.problems.append((f"{vp}/{m.name}", f"draw {d.number}: {bad}"))
    if reimport and sc.meshes:
        check_reimport(rep, vp, arc.to_bytes())
    if variants is not None and sc.meshes:
        check_variants(rep, vp, sc, variants)


def _reencode_vertices(sc, d) -> str | None:
    """Decode then encode every element of a draw's vertices; describe the first
    difference with the stored bytes (None: all identical)."""
    for el in d.declaration:
        s = d.streams.get(el.stream)
        if s is None or s.buffer is None:
            continue
        raw = sc.entry(s.buffer).data()
        first = s.first + d.base_vertex + d.first_vertex
        size = el.vtype.size
        for i, v in enumerate(vx.decode_element(el, raw, s.stride, first, d.vertex_count)):
            o = (first + i) * s.stride + el.offset
            if vx.encode_value(el, v) != raw[o:o + size]:
                return (f"{el.describe()} of vertex {i} re-encodes to "
                        f"{vx.encode_value(el, v).hex()}, stored {raw[o:o + size].hex()}")
    return None


def _vertex_key(dd, v: int) -> tuple:
    """Everything a vertex carries, joints only where they have weight (a rebuilt
    palette may start elsewhere, which moves the unused slots)."""
    sk = None
    if dd.joints:
        sk = tuple(sorted((j, w) for j, w in zip(dd.joints[v], dd.weights[v]) if w > 0))
    return (dd.positions[v], dd.normals[v] if dd.normals else None,
            dd.tangents[v] if dd.tangents else None, dd.colors[v] if dd.colors else None,
            tuple(u[v] for u in dd.uvs), sk)


def _triangle_set(dd) -> list:
    out = []
    for t in dd.triangles:
        keys = [_vertex_key(dd, v) for v in t]
        i = min(range(3), key=lambda k: keys[k])
        out.append(tuple(keys[i:] + keys[:i]))
    return sorted(out)


def check_reimport(rep: CensusReport, vp: str, data: bytes) -> None:
    """The phase 4 gates for one model (the census's ``reimport`` option):

    1. ``.glb`` export then import, no edits → the identical model bytes;
    2. every shape rebuilt from its own decoded geometry (`SceneEditor.replace_mesh`)
       → the same triangles with the same vertex values (strip, buffers, packets,
       palettes and bounds all regenerated).
    """
    from .convert.gltf import model_to_glb
    from .convert.model_import import import_glb
    chk = rep.scene_checks
    try:
        out, _ = import_glb(scenefmt.Scene.parse(data, vp),
                            model_to_glb(scenefmt.Scene.parse(data, vp)))
        ok = out == data
    except Exception as ex:  # noqa: BLE001 - reported
        rep.problems.append((vp, f"glb re-import: {ex}"))
        ok = None
    if ok is not None:
        chk["glb re-import identical" if ok else "glb re-import DIFFERS"] += 1
        if not ok:
            rep.problems.append((vp, "glb re-import: the model's bytes differ"))
    sc = scenefmt.Scene.parse(data, vp)
    try:
        ed = scene_write.SceneEditor(sc)
        before = {}
        for m in sc.meshes:
            try:
                scene_write.own_buffers(m)
            except Exception:  # noqa: BLE001 - vertex-animated: not replaceable
                chk["shapes not rebuilt (vertex-animated)"] += 1
                continue
            before[m.name] = [sc.draw_data(d, m.name) for d in m.draws]
        for m in sc.meshes:                 # decode everything first: edits are in place
            if m.name not in before:
                continue
            ed.replace_mesh(m.name, [
                scene_write.DrawGeometry(d.material, dd.positions, dd.triangles, dd.normals,
                                         dd.uvs, dd.colors, dd.joints, dd.weights,
                                         dd.tangents)
                for d, dd in zip(m.draws, before[m.name])])
        sc2 = scenefmt.Scene.parse(ed.to_bytes(), vp)
    except Exception as ex:  # noqa: BLE001 - reported
        rep.problems.append((vp, f"shape rebuild: {ex}"))
        return
    for m in sc2.meshes:
        if m.name not in before:
            continue
        old = before[m.name]
        if len(m.draws) != len(old):
            rep.problems.append((f"{vp}/{m.name}", f"rebuilt with {len(m.draws)} draws, "
                                                   f"had {len(old)}"))
            continue
        for d, dd in zip(m.draws, old):
            same = _triangle_set(sc2.draw_data(d, m.name)) == _triangle_set(dd)
            chk["draws rebuilt identically" if same else "draws rebuilt DIFFERENTLY"] += 1
            if not same:
                rep.problems.append((f"{vp}/{m.name}", f"draw {d.number}: rebuilt geometry "
                                                       f"differs"))


def _audio_job(data: bytes, info) -> tuple[str | None, int, float]:
    """Worker: decode one `.xma` and check its length. Returns (problem, frames, peak)."""
    from .convert.audio import decode, length_check
    pcm = decode(data, info)
    err = length_check(pcm, info, data[info.packets_offset:info.packets_offset + info.packets_size])
    return err, pcm.frames, pcm.peak


def _reencode_job(data: bytes) -> int:
    """Worker: compress + verify (compress_entry decodes its own output). Returns size."""
    return len(xcompress.compress_entry(data, verify=True))


def format_report(rep: CensusReport) -> str:
    """The census as text for people (``dr2 census`` prints this)."""
    L = []
    w = L.append
    w(f"== census: {rep.game} ({rep.root})")
    w(f"LZX decoder: {rep.lzx_backend}")
    w(f"files under data/: {sum(rep.files_by_ext.values())} "
      f"({_fmt(rep.files_by_ext)})")
    w(f"archive files: {rep.archive_files}   archives incl. nested: {rep.archives} "
      f"(by depth: {_fmt(rep.archives_by_depth, sort_keys=True)})")
    w(f"entries: {rep.entries}   zero-size: {rep.zero_size}")
    w(f"entry extensions ({len(rep.entries_by_ext)}): {_fmt(rep.entries_by_ext)}")
    w("content by extension (decoded first bytes):")
    for ext, c in sorted(rep.kind_by_ext.items(), key=lambda kv: -sum(kv[1].values())):
        w(f"    {ext:>10}: {_fmt(c)}")
    w(f"flags: {_fmt(rep.flags)}")
    for fl, c in sorted(rep.flags_by_ext.items()):
        w(f"    {fl:>6}: {_fmt(c, limit=8)}")
    w(f"compression marker: {_fmt(rep.compression)}")
    w(f"compressed entries: {rep.compression.get(LZX, 0)} "
      f"({rep.compressed_top_level} in archives on disk), "
      f"{rep.compressed_bytes_stored:,} bytes stored -> "
      f"{rep.compressed_bytes_unpacked:,} unpacked, in {len(rep.compressed_by_archive)} archives")
    w(f"LZX chunks: {rep.lzx_chunks}; first block type: "
      f"{_fmt(rep.lzx_block_types, sort_keys=True)}; chunk padding: "
      f"{_fmt(rep.lzx_chunk_padding, sort_keys=True)}")
    w(f"payload alignment (largest power of two dividing the offset, capped 0x800): "
      f"{_fmt({hex(k): v for k, v in rep.alignments.items()})}")
    w(f"texture (.bct) header byte 3: {_fmt(rep.bct_byte3)}")
    w(f"textures parsed: {rep.tex_parsed}; formats: {_fmt(rep.tex_formats)}; "
      f"cube maps: {rep.tex_cubes}; header byte 9: {_fmt(rep.tex_versions)}")
    w(f"    mip levels: {_fmt(rep.tex_levels, sort_keys=True)}")
    w(f"    non-power-of-two: {rep.tex_npot} ({rep.tex_npot_mipped} with mips); "
      f"largest: {rep.tex_largest[0]}x{rep.tex_largest[1]} {rep.tex_largest[2]}")
    w(f"    payload size vs layout model: {_fmt(rep.tex_size_model)}")
    w("    format by name suffix:")
    for suf, c in sorted(rep.tex_format_by_suffix.items(), key=lambda kv: -sum(kv[1].values()))[:12]:
        w(f"        {suf:>7}: {_fmt(c)}")
    if rep.scenes:
        w(f"scenes: {_fmt(rep.scenes)}; nodes: {rep.scene_nodes}; meshes: {rep.scene_meshes}; "
          f"draws: {rep.scene_draws}; vertex streams: {_fmt(rep.scene_buffers)}")
        w(f"    vertex elements: {_fmt(rep.scene_vertex_types)}")
        w(f"    chunks the scene reader doesn't use: {_fmt(rep.scene_unused_chunks)}")
        if rep.scene_draws_decoded:
            w(f"    decoded: {rep.scene_vertices:,} vertices, {rep.scene_triangles:,} triangles")
        if rep.scene_checks:
            w(f"    checks: {_fmt(rep.scene_checks)}")
    if rep.var_models:
        w(f"variants: models: {_fmt(rep.var_models)}")
        w(f"    parts by group: {_fmt(rep.var_groups)}")
        w(f"    zombie parts matching no pattern (always drawn): {len(rep.var_unmatched)}"
          + (f" ({'; '.join(x.rsplit('/', 1)[-1] for x in rep.var_unmatched[:6])}"
             f"{'…' if len(rep.var_unmatched) > 6 else ''})" if rep.var_unmatched else ""))
        w(f"    misplaced digits (the game loses the variant): {len(rep.var_misplaced)}")
        for x in rep.var_misplaced:
            w(f"        {x}")
        w(f"    colour choices: {rep.colour_choices} for {rep.colour_materials} materials "
          f"(by name); the game's list: {rep.colour_listed} found by the rule")
        w("    zombie slots per detail level (2 high, 3 medium, 4 low):")
        for z, lv in sorted(rep.var_levels.items()):
            w(f"        {z}: " + "; ".join(
                f"{n}: " + (" ".join(f"{k}{''.join(map(str, v))}" for k, v in sl.items()) or "-")
                for n, sl in sorted(lv.items())))
        w(f"    environment pieces with variant-like shapes (not classified): "
          f"{len(rep.var_env)}")
        for x in rep.var_env[:8]:
            w(f"        {x}")
        if len(rep.var_env) > 8:
            w(f"        ... and {len(rep.var_env) - 8} more (use --json for all)")
    if rep.audio_shapes:
        w(f"audio (.xma): {_fmt(rep.audio_shapes)}; channels: "
          f"{_fmt(rep.audio_channels, sort_keys=True)}")
        rates = rep.audio_rates
        w(f"    rates: 48000 Hz: {rates.get(48000, 0)}, others: "
          f"{sum(rates.values()) - rates.get(48000, 0)} ({min(rates)}..{max(rates)} Hz)")
        w(f"    decoded: {rep.audio_seconds / 3600:.2f} h; silent: {len(rep.audio_silent)} "
          f"({', '.join(v.rsplit('/', 1)[-1] for v in rep.audio_silent[:6])}"
          f"{'…' if len(rep.audio_silent) > 6 else ''})")
        w(f"    first packets shared by different sounds: {rep.audio_shared_first}")
        w(f"sfx: {rep.sfx_parsed} parsed; tracks: {_fmt(rep.sfx_tracks)}")
        for m in rep.sfx_missing[:5]:
            w(f"    missing from the game data: {m}")
        if len(rep.sfx_missing) > 5:
            w(f"    ... and {len(rep.sfx_missing) - 5} more")
    if rep.movies:
        w(f"movies (.bik): {rep.movies} decoded (every frame, and the sound), "
          f"{rep.movie_seconds / 60:.1f} min")
    if rep.string_banks:
        counts = set(rep.strings.values())
        w(f"string banks (.bcs): {rep.string_banks} parsed and re-written identically, "
          f"{'same' if len(counts) == 1 else 'DIFFERENT'} ids count: "
          f"{_fmt(rep.strings, sort_keys=True) if len(counts) > 1 else counts.pop()}")
    if rep.levels:
        geo = {k: v for k, v in rep.levels.items() if not k.startswith("script ")}
        w(f"levels: {len(geo)}; " + "; ".join(
            f"{k}: {v['zones']} zones, {v['pieces']} pieces, {v['placements']} placed"
            + (f", {v['textures missing']} textures missing" if v['textures missing'] else "")
            for k, v in geo.items()))
        for k, v in rep.levels.items():
            if k.startswith("script "):
                w(f"    {k}: {_fmt(v)}")
        w(f"    {_fmt(rep.level_counts)}")
        w(f"    placement maths (world bounds = piece bounds placed): worst error "
          f"{rep.level_bounds_error * 1000:.2f} mm")
        for x in rep.level_notes[:12]:
            w(f"    note: {x}")
        if len(rep.level_notes) > 12:
            w(f"    ... and {len(rep.level_notes) - 12} more notes (use --json for all)")
    w(f"duplicate names: {rep.duplicate_name_entries} entries in "
      f"{rep.duplicate_name_archives} archives")
    w(f"names unsafe in a vpath or as a Windows file name: {len(rep.unsafe_names)}")
    for vp in rep.unsafe_names[:10]:
        w(f"    {vp}")
    w("-- gates")
    w(f"round trip identical: {rep.roundtrip_ok}/{rep.archives} archives")
    w(f"hash == engine hash of lower-cased name: {rep.hash_ok}/{rep.entries}")
    n = rep.compression.get(LZX, 0)
    w(f"decoded to size2: {rep.decoded_ok}/{n} compressed entries")
    if rep.python_checked:
        w(f"pure-Python decoder agrees: {rep.python_checked}/{n}")
    if rep.reencoded_ok:
        ours, shipped = rep.reencode_ratio
        w(f"re-encoded and decoded back: {rep.reencoded_ok}/{n} "
          f"(our streams are {ours / max(shipped, 1):.2f}x the shipped size)")
    if rep.tex_reencoded_ok:
        w(f"textures decoded + re-encoded to identical bytes: "
          f"{rep.tex_reencoded_ok}/{rep.tex_parsed}")
    if rep.scenes:
        w(f"scenes parsed: {sum(rep.scenes.values())} ({_fmt(rep.scenes)})")
    if rep.scene_draws_decoded:
        w(f"model draws decoded: {rep.scene_draws_decoded}/{rep.scene_draws}")
    if rep.audio_shapes:
        w(f"audio decoded to the stored length: {rep.audio_decoded_ok}/"
          f"{sum(rep.audio_shapes.values())}")
    w(f"PROBLEMS (unparsed or failed): {len(rep.problems)}")
    for vp, why in rep.problems[:40]:
        w(f"    {vp}: {why}")
    if len(rep.problems) > 40:
        w(f"    ... and {len(rep.problems) - 40} more (use --json for all)")
    w(f"took {rep.seconds:.1f} s")
    return "\n".join(L)


def _fmt(c, limit: int = 0, sort_keys: bool = False) -> str:
    items = sorted(c.items()) if sort_keys else sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0])))
    if limit and len(items) > limit:
        rest = sum(v for _, v in items[limit:])
        items = items[:limit] + [("…", rest)]
    return ", ".join(f"{k}: {v}" for k, v in items)

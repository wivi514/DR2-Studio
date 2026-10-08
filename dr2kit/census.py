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

Results for both games are recorded in docs/formats.md. Run it with ``dr2 census``.
"""

from __future__ import annotations

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
    duplicate_name_archives: int = 0
    duplicate_name_entries: int = 0
    unsafe_names: list = field(default_factory=list)
    problems: list = field(default_factory=list)   # (vpath, what went wrong)
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
               reencode: bool = False, textures: bool = False,
               workers: int | None = None, progress=None) -> CensusReport:
    """Census one game's data folder. See the module docstring for what is checked.

    ``progress(message)`` is called once per file on disk. ``workers`` sets the process
    count for ``reencode`` (default: all CPUs).
    """
    from .container import lzx
    t0 = time.time()
    rep = CensusReport(game, str(tree.root), lzx_backend=lzx.backend_detail())
    pool = ProcessPoolExecutor(max_workers=workers or os.cpu_count()) if reencode else None
    pending: set = set()

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

    try:
        for vp, path in tree.files():
            ext = path.suffix.lower().lstrip(".") or "(none)"
            rep.files_by_ext[ext] += 1
            raw = path.read_bytes()
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
    finally:
        if pool is not None:
            pool.shutdown(cancel_futures=True)
    rep.seconds = time.time() - t0
    return rep


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

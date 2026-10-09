"""Audio overrides: what a mod build writes so a recomp plays new audio for a sound.

Why not a new `.xma`: nobody can redistribute an XMA encoder (it is in the Xbox 360
SDK), so the toolkit can't make the game's own format. Instead the **recomps substitute
PCM** (docs/ARCHITECTURE.md §Recomp integration, item 2): they decode XMA anyway, one
2 KB packet per call, so when they decode a packet of a replaced sound they output the
mod's samples in place of the decoded ones. The game's files and everything the game
sees (buffers, read offsets, sample counts, timing) stay exactly as shipped.

**How the recomp knows where it is** (docs/dev/recomp-integration.md §Audio
substitution): every packet of a replaced sound is listed by its 64-bit FNV-1a hash
(`dr2kit.formats.xma.fingerprint`) with the position, in decoded samples, where its
output begins (`dr2kit.convert.audio.stream_packets`). So each decoded packet says by
itself which replacement samples go out: loops, streaming through ring buffers, a
context reused for another sound, or a sound started part-way all work without the
runtime tracking which file a buffer came from. The hardware decodes one stream per
context (a 5.1 sound is three stereo streams), so a sound is substituted per stream.

What `build_audio` writes into the build folder (deployed into ``game_mods/``):

* ``dr2kit_audio/<vpath hash>_<stream>.wav``: 16-bit PCM with the stream's channels at
  the sound's rate, **exactly as long as the original decodes**
  (`convert.audio.conform` cuts or pads; the game decides how long a sound plays);
* ``dr2kit_audio/substitutions.txt``::

      sound <n> <channels> <samples> <file>        # <vpath> stream <k>
      <fingerprint hex> <n> <start sample> <u|c>   # one line per packet of sound n

  ``u``: the packet occurs nowhere else in the game, so it may start a substitution;
  ``c``: it also occurs in another sound, so it is only used to continue one already
  running on that context (at the expected position).

Checks (rule 6, named, not skipped): every packet is compared with every packet of
every other sound of the game; packets that collide are marked ``c`` and counted in a
note. A sound with no ``u`` packet can't be recognised at all: that is an error.
"""

from __future__ import annotations

import hashlib

from ..container.vpath import AssetTree, entry_components, join
from ..convert import audio as caudio
from ..formats import xma
from .manifest import ModError

AUDIO_DIR = "dr2kit_audio"
SUBSTITUTIONS = "substitutions.txt"
HEADER = ("# dr2kit audio substitutions v1. Written by `dr2 mod build`; read by the CZ/CW\n"
          "# recomps (CZ_NO_AUDIO_MODS=1 / CW_NO_AUDIO_MODS=1 turn it off).\n"
          "# sound <n> <channels> <samples> <file>\n"
          "# <fnv1a64 of a 2 KB XMA packet> <sound n> <first output sample> <u=may start|c=continue only>\n")


def build_audio(items, tree: AssetTree, out, res, progress=None) -> None:
    """Write the substitution files for the audio overrides ``items`` (`Planned` list).

    Appends the written paths to ``res.files`` and notes to ``res.warnings``. Raises
    `ModError` for files that can't be read or sounds that can't be recognised.
    """
    if not caudio.have_decoder():
        raise ModError("replacing sounds needs PyAV to decode the originals: pip install av")
    lookup = caudio.AudioLookup(tree)
    folder = out / AUDIO_DIR
    folder.mkdir(parents=True, exist_ok=True)
    sounds = []      # (vpath, [(channels, frames, file, [(sha1, fp, start)])])
    own = set()
    for p in items:
        data = tree.resolve(p.vpath).data()
        info = lookup.info(p.vpath, data)
        packets = data[info.packets_offset:info.packets_offset + info.packets_size]
        original = caudio.decode(data, info)
        try:
            new = caudio.load_audio(p.override.source)
        except Exception as e:  # noqa: BLE001 - any read failure is the modder's file
            raise ModError(f"{p.mod.id}: replace/{p.override.source.name}: {e}") from None
        fitted, notes = caudio.conform(new, info.channels, info.rate, original.frames)
        res.warnings += [f"{p.vpath}: {n}" for n in notes]
        pieces = caudio.split_streams(fitted)
        layout = caudio.stream_packets(data, info)
        if len(layout) != len(pieces):
            raise ModError(f"{p.vpath}: {len(layout)} XMA streams found, expected "
                           f"{len(pieces)} for {info.channels} channels")
        own.add(hashlib.sha1(packets).digest())
        streams = []
        tag = f"{hashlib.sha1(p.vpath.lower().encode()).hexdigest()[:12]}"
        for k, (sp, piece) in enumerate(zip(layout, pieces)):
            name = f"{tag}_{k}.wav"
            (folder / name).write_bytes(piece.wav_bytes())
            res.files.append(f"{AUDIO_DIR}/{name}")
            rows = []
            for i, start in zip(sp.packets, sp.starts):
                pk = packets[i * xma.PACKET:(i + 1) * xma.PACKET]
                rows.append((hashlib.sha1(pk).digest(), xma.fingerprint(pk), start))
            streams.append((piece.channels, piece.frames, name, rows))
        sounds.append((p.vpath, streams))
        if progress:
            progress(f"{AUDIO_DIR}: {p.vpath} ({len(pieces)} stream(s), "
                     f"{fitted.seconds:.2f} s)")
    wanted = {row[0] for _, streams in sounds for *_, rows in streams for row in rows}
    shared = shared_packets(tree, lookup, wanted, own)
    lines = [HEADER]
    n = 0
    for vpath, streams in sounds:
        for k, (ch, frames, name, rows) in enumerate(streams):
            lines.append(f"sound {n} {ch} {frames} {name}  # {vpath} stream {k}\n")
            starters = 0
            for sha, fp, start in rows:
                flag = "c" if sha in shared else "u"
                starters += flag == "u"
                lines.append(f"{fp:016x} {n} {start} {flag}\n")
            if not starters:
                raise ModError(f"{vpath} stream {k}: every packet also occurs in other "
                               f"sounds, so the recomp can't recognise it")
            if starters < len(rows):
                res.warnings.append(
                    f"{vpath} stream {k}: {len(rows) - starters} of {len(rows)} packets also "
                    f"occur in other sounds ({', '.join(sorted(shared_names(shared, rows))[:3])}"
                    f"); those only continue a replacement already playing")
            n += 1
    (folder / SUBSTITUTIONS).write_text("".join(lines), "utf-8")
    res.files.append(f"{AUDIO_DIR}/{SUBSTITUTIONS}")
    verify_audio(out, n)


def shared_names(shared: dict, rows) -> set:
    return {v for sha, *_ in rows for v in shared.get(sha, ())}


def shared_packets(tree: AssetTree, lookup, wanted: set, own: set) -> dict:
    """``{sha1 of a packet: {vpaths}}`` for the ``wanted`` packets that also occur in
    a sound of the game other than the replaced ones (and their identical copies)."""
    out: dict = {}
    for vp, arc, _ in tree.walk_archives():
        for comp, e in zip(entry_components(arc), arc.entries):
            if not e.name.lower().endswith(".xma"):
                continue
            evp = join(vp, comp)
            data = e.data()
            try:
                info = lookup.info(evp, data)
            except Exception:  # noqa: BLE001 - the census names these; nothing to match
                continue
            packets = data[info.packets_offset:info.packets_offset + info.packets_size]
            if hashlib.sha1(packets).digest() in own:
                continue
            for i in range(len(packets) // xma.PACKET):
                h = hashlib.sha1(packets[i * xma.PACKET:(i + 1) * xma.PACKET]).digest()
                if h in wanted:
                    out.setdefault(h, set()).add(evp)
    return out


def verify_audio(out, sounds: int) -> None:
    """Read the written substitutions back: every file exists, is PCM, has its length,
    and every packet line points at a declared sound inside its length."""
    folder = out / AUDIO_DIR
    declared = {}
    for ln in (folder / SUBSTITUTIONS).read_text("utf-8").splitlines():
        ln = ln.split("#", 1)[0].split()
        if not ln:
            continue
        if ln[0] == "sound":
            _, n, ch, frames, name = ln
            pcm = caudio.read_wav((folder / name).read_bytes())
            if pcm.channels != int(ch) or pcm.frames != int(frames):
                raise ModError(f"build check failed: {name} reads back as {pcm.channels} ch, "
                               f"{pcm.frames} samples; {SUBSTITUTIONS} says {ch}, {frames}")
            declared[int(n)] = int(frames)
        else:
            fp, n, start, flag = ln
            if int(n) not in declared or not 0 <= int(start) <= declared[int(n)] or \
                    flag not in "uc" or len(fp) != 16:
                raise ModError(f"build check failed: bad line in {SUBSTITUTIONS}: {ln}")
    if len(declared) != sounds:
        raise ModError(f"build check failed: {len(declared)} sounds declared, wrote {sounds}")

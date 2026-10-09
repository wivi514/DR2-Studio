# CLAUDE.md — DR2 CZ/CW Modding Toolkit

A modding toolkit for **Dead Rising 2: Case Zero** and **Dead Rising 2: Case West**
(Xbox 360 XBLA titles, Blue Castle Games engine) as run by the two Xenon recomps.

Goal: make modding easy. Browse every asset in both games, **see** what a texture is
and **hear** a sound before extracting it, export models and skeletons to Blender, and
put edited or new models back into the game when their bones match the game's rig.

**Status: phase 5 (audio) done 2026-10-09: both `.xma` shapes read (RIFF XMA2; raw
packets + `cache.big` stream tables), decode to WAV through PyAV, Studio playback,
`.sfx`/scene-script names in the index, and sound mods through PCM substitution in both
recomps (every packet recognised by fingerprint + output position); decode gate (every
sound of both games decodes to its stored length) and in-game gate (title music swap,
CZ and CW) passed. Script-level remap ruled out: CZ digest-checks `Prologue.txt`.
After phase 5, fixes from the user's Studio review: value-set colours baked for zombie
clothing (`formats/shader.py`, `convert/material.py`), `_dm` / `_cm<hex>` colour maps,
packs next to loose models.
Phases 1-4 (container, LZX, census, CLI; textures, index, Studio, mods, `game_mods/`;
models → Blender and back) done 2026-10-08. Next: phase 6 (polish and distribution);
start from `docs/phase6-kickoff.md`.** Read these before writing code:

| Doc | What it holds |
|---|---|
| `docs/ARCHITECTURE.md` | Components, data flow, the asset index, the mod package format, stack choices |
| `docs/formats.md` | Everything known about every file format, with a status per format (cracked / partial / unknown) |
| `docs/phase6-kickoff.md` | Phase 6 handoff: scope, what phase 5 left open, post-phase-5 fixes, facts to keep in mind |
| `docs/dev/code-tour.md` | Every module of `dr2kit` and how a read flows through them |
| `THIRD_PARTY.md` | Reused code and its licenses (libmspack is LGPL: keep it in its own library) |
| `docs/roadmap.md` | Phases, what each phase delivers, and the gate that proves it works |
| `docs/README.md` | Docs index: modder guides (`docs/modding/`), developer guides (`docs/dev/`), glossary, devlog |
| `docs/prior-art.md` | Community tools (ProBoards, wiki, Gibbed, mariokart64n's MaxScript, Chrrox) and what to learn or avoid from each |

## Documentation rules (user requirement, 2026-10-08)

**Document everything we do**, so people can understand the code and the docs, and can
learn to mod with the toolkit. Documentation is part of done, not a follow-up task.
Every change, however small, updates whichever of these it affects, **in the same commit**:

| What changed | Update |
|---|---|
| Any code | Module docstring (purpose, *why*, key facts, link to `formats.md`), public docstrings + type hints, `docs/dev/code-tour.md` for new modules |
| A format fact | `docs/formats.md` (keep retractions; state how it was verified) |
| Something a modder can now do, or do differently | A guide in `docs/modding/` (template in `docs/modding/README.md`) and its status row there; `asset-catalogue.md` / `12-troubleshooting.md` when relevant |
| A new term | `docs/glossary.md`, in plain words |
| A decision or design change | `docs/ARCHITECTURE.md` and/or `docs/roadmap.md` |
| Every work session | A `docs/devlog.md` entry: done, why, learned, docs updated, next |

Write for a newcomer: plain words, define jargon or link the glossary, explain *why*
before *how*, and show real examples. Modder guides need no programming knowledge and
give the Studio (GUI) steps first, then the `dr2` CLI equivalent. Full style and the
definition-of-done checklist: `docs/dev/README.md`. Docs index: `docs/README.md`.

## Where the games live

Both recomps sit next to this repo. They are separate repos with their own CLAUDE.md
files and conventions. Treat them as **read-only references**, except for the two
approved integration changes (a `game_mods/` VFS layer and PCM audio substitution,
`docs/ARCHITECTURE.md` §Recomp integration). Make those in each recomp following its own
CLAUDE.md, and keep CZ and CW in step.

| | Case Zero | Case West |
|---|---|---|
| Recomp repo | `../Dead_Rising_2_Case_Zero_Xenon_Recomp` | `../Dead_Rising_2_Case_West_Xenon_Recomp` |
| Unpacked game data | `…/assets/game/data/` (146 `.big`, 832 MB) | `…/assets/game/data/` (154 `.big`, 1.2 GB) |
| Title ID | `58410A8D` | `58410B00` |
| XBLA package | `…/assets/package/58410A8D/000D0000/` (256 files) | `…/assets/package/58410B00/000D0000/` (305 files) |
| Extra content vs CZ | — | `.bik` movies (Bink), `controls/`, `dynamicprops/`, more `.csv` |
| Runtime VFS overlays | `assets/game_bootskip`, `game_kbm`, `game_patched` | `game_kbm`, `game_patched` |

The game data is **copyrighted**. Never commit it, never copy it into this repo, never
put extracted assets in test fixtures. Tests that need real data locate it through the
game profile config and **skip, saying so,** when it is absent.

## Prior work to reuse (in the CZ recomp's `tools/`)

The CZ recomp already cracked a lot. Port it here, don't rediscover it. Phase 1 ported
`big_list.py`, `read_big`/`write_big`, the LZX encoder, `name_hash.py` and
`extract_stfs.py` (`THIRD_PARTY.md` maps each to its module); the rest is still to port. Its docs record
*why* each detail is the way it is, including retractions; read them before changing
behaviour.

| Existing | What it gives us |
|---|---|
| `docs/big-archive-format.md` | The `.big` container: layout, the variable-length names, the compression, two retractions |
| `tools/big_list.py` | Listing and extracting `.big` entries (stored bytes) |
| `tools/big_decompress.cpp` | LZX decode of compressed entries, linked from XenonRecomp's `lzxDecompress` (which wraps libmspack's **LGPL-2.1** `lzxd.c`, so keep it a separate shared library), checked against an oracle |
| `tools/gen_pc_options.py` | `read_big` / `write_big`, a **real pure-Python LZX encoder** (`lzx_encode_stream`), `verify_fake_lzx`, a `.bcs` string-bank patcher |
| `tools/patch_coop_ending_bike.py` | A worked example of re-packing a modified entry that the game accepted |
| `tools/tex_decode.py` | Xenos `Tiled2DOffset` untiling + DXT1/DXT5 decode (ported in phase 2) |
| `tools/vsdump_skin.py`, `CZ_CAPTURE_DUMP_VS` | Draw dumps (constants + stream bytes) of one shader; the toolkit's `tools/capture_gate.py` reads them (phase 3) |
| `tools/name_hash.py` | The engine's string hash (`h = h*33 ^ c`); `.big` entries are looked up by hash |
| `runtime/audio/xma_decoder.cpp` | How to feed raw XMA to ffmpeg's `xma2` decoder (the 34-byte XMA2 extradata); `runtime/kernel/audio.cpp` holds the audio substitution added in phase 5 |
| `runtime/kernel/vfs.cpp` | The overlay layers; the `game_mods/` layer was added here in phase 2 (both recomps) |

## Hard-won rules (inherited from the recomp work, all measured)

1. **Endianness flips inside one file.** The `.big` header and index are **little-endian**;
   the compressed stream inside an entry, and every payload (textures, models,
   skeletons), is **big-endian**. Choose byte order per structure, never per file.
2. **`.big` names are variable-length.** Read each name up to the NUL from its own
   `name_offset`. A fixed width only holds within the shader banks.
3. **`size` is the stored length, `size2` the uncompressed length; `resv == 2` marks
   compression.** 1,671 entries of CZ's `.big` files are compressed (10,754 counting
   nested archives; CW 21,354). An empty compressed entry is just `00 00 00 00`.
4. **Compressed entries must be re-encoded, not stored.** The game asserts and crashes on
   a stored replacement where it expects compression, and crashes on degenerate LZX
   streams that other decoders accept. Use the real encoder and verify by decoding.
5. **Shipped textures are tiled.** Untile with `Tiled2DOffset` before you look at them, and
   re-tile before you write them back.
6. **Name what you could not parse.** A tool that silently skips what it can't read gives
   confident wrong answers (the first `big_list` dropped 95 of 146 archives). Every
   reader reports unknown chunks, unknown formats and leftover bytes.
7. **A structural constant seen in one family of files belongs to that family** until a
   second family agrees. Check a format claim against more than one archive *and* both
   games before writing it down as a rule.

## Verification gates (use these, not eyeballing)

- **Round-trip identity.** `read → write` with no edits must produce byte-identical
  output for every archive in both games. This is the first test of every writer.
- **Decode oracles.** LZX output must have the right `size2` and the expected magic
  (`05 01 01` for `.bct`; the 4th byte varies, so `05 01 01 E2` was a retracted claim).
  Two independent LZX decoders (native libmspack, pure Python) must agree. Decoded
  skeleton quaternions must have unit norm.
- **Cross-game census.** A format change is not done until a census over *all* entries of
  that type in CZ and CW reports zero unparsed entries (or names each one).
- **In-game proof.** A replacement counts only once it loads in the recomp. The
  recomp's `game_patched` overlay is the existing path for that.

## Commands

```
python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"   # setup (docs/dev/setup.md)
cmake -S native/lzx -B native/lzx/build -DCMAKE_BUILD_TYPE=Release && cmake --build native/lzx/build
python -m pytest -q                       # unit + game-data tests (game tests skip if absent)
dr2 doctor                                # LZX backend in use, games found
dr2 census                                # both games: counts + round-trip/decode gates (~30 s)
dr2 census --reencode --python-lzx        # the slow LZX gates (~20 min, all CPUs)
dr2 census --textures                     # the texture re-encode gate (~4 min CZ, ~6 min CW)
dr2 census --models                       # decode every draw of every model (~40 s / ~70 s)
dr2 census --reimport                     # + .glb re-import and shape rebuild gates (~4 / ~8 min)
dr2 extract --glb <model vpath> -o out    # model or skeleton -> .glb for Blender
dr2 census --audio                        # decode every sound, check lengths (~30 / ~42 s; PyAV)
dr2 extract --wav <sound vpath> -o out    # .xma -> WAV (pip install av)
dr2 model check <file.glb> <model vpath>  # rig validator (import: dr2 model import … -o)
python tools/blender_skeleton_gate.py     # skeleton round trip through Blender (~25 s)
dr2 index build                           # the asset index (~1-2 min per game)
dr2 studio                                # the GUI (pip install -e ".[studio]")
```

## Conventions

- Language: **Python 3.11+** for the core library, CLI and GUI. Pure Python plus optional
  numpy, so the same core imports inside Blender's bundled Python. The only native code
  is the LZX decoder (a small C shared library loaded through ctypes, with a pure-Python
  fallback). See `docs/ARCHITECTURE.md` §Stack.
- Paths inside archives are written `data/models/npcs.big/chest_default.tex/chest_default_cm`
  (archive path, then `/` for each nesting level). This "virtual path" is the asset's
  identity everywhere: the index, mod manifests, the CLI and the GUI.
- Every format module has a reader, a writer (once supported), a census command and a
  section in `docs/formats.md`. When a fact changes, update that doc in the same commit,
  and keep a retraction in place rather than silently rewriting history.
- **Windows, Linux and macOS are all supported** (core, CLI, PySide6 Studio). `pathlib`
  only, case-insensitive virtual paths, `platformdirs` for user folders, no shelling out
  to Unix tools, and a pure-Python fallback for every native piece. Data must be
  obtainable without a recomp (the STFS package). Details: `docs/ARCHITECTURE.md` §Platforms.
- License: `LICENSE`, free and non-commercial. The toolkit can't be sold, and mods for these
  games can't be sold or paywalled. Don't add dependencies whose licenses conflict
  with distributing the toolkit for free (LGPL/MIT/BSD/Apache are fine; PySide6 is LGPL).
- Game profiles (`cz`, `cw`) are data, not branches in code. Format differences between
  the games go into the profile.

## Host environment (as of 2026-10-08)

Fedora 44, Python 3.14 (system), Blender 5.2.1 LTS at `/usr/bin/blender`, ffmpeg with
`xma1`/`xma2` and Bink decoders. No `xxd` (use `od`). `vgmstream-cli` not installed.
`uv` is available (it also provides Python 3.11/3.12 for compatibility checks). Dev venv:
`.venv/` (`uv venv .venv --python 3.14 && uv pip install -e ".[dev,studio]"`; PyAV, numpy,
PySide6 6.12 and Pillow installed there too). DR2 Studio runs headless with
`QT_QPA_PLATFORM=offscreen` (screenshots via `window.grab()`). CMake + Ninja + gcc/clang present; the native LZX library is built in
`native/lzx/build/`. Python 3.14 uses the *forkserver* start method, so any script that
runs `dr2 census --reencode` (a process pool) needs an `if __name__ == "__main__"` guard.

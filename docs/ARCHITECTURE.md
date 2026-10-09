# Architecture

## What we are building

```
                ┌──────────────────────────── dr2kit (core library) ──────────────────────────┐
 game data ───► │ container: .big read/write, LZX dec/enc, virtual paths                       │
 (CZ, CW,       │ formats:  bct/tex · model · skeleton · anim · xma · bik · bcs · txt/csv       │
  read-only)    │ convert:  tex⇄PNG/DDS · model⇄glTF · skeleton⇄glTF · xma→WAV · bcs⇄JSON        │
                │ index:    SQLite catalogue of every asset + relations (model↔texture↔skeleton) │
                │ mods:     mod manifest, build, conflict check, deploy                         │
                └──────┬─────────────────────┬──────────────────────┬───────────────────────────┘
                       │                     │                      │
                  dr2 (CLI)           DR2 Studio (GUI)        io_dr2 (Blender add-on)
             scripting, CI, batch   browse, preview, play,    import model/skeleton,
                                    extract, build mods       validate rig, export back
                                             │
                                             ▼
                     mod build output ──► recomp `assets/game_mods/` overlay (proposed)
                                      └─► patched .big files (also work on Xenia / real 360)
```

Every front end calls one library. Format knowledge lives only in `dr2kit`.

## Repository layout

Phase 1 built the parts marked ✅; the rest is the plan. Module-by-module guide:
`dev/code-tour.md`.

```
dr2kit/                 core library (pure Python; numpy optional)
  errors.py ✅          exception hierarchy (Dr2Error → FormatError/LzxError, GameNotFoundError, VPathError)
  hashing.py ✅         the engine's string hash
  census.py ✅          read every archive/entry of a game, count it, run the gates
  container/ ✅         big.py (read/write), xcompress.py (chunk framing), lzx/ (native loader,
                        pure-Python decoder, encoder), vpath.py, stfs.py (XBLA package)
  profiles/ ✅          cz.toml, cw.toml + data discovery (env var, user config, sibling recomp)
  cli/ ✅               the `dr2` command (main.py)
  formats/              bct.py ✅ (phase 2); scene.py ✅, vertex.py ✅ (phase 3: chunks,
                        skeleton, materials, draws, vertex decode, bone palettes);
                        scene_write.py ✅ (phase 4: chunk writers, strips, new geometry);
                        later: anim.py, xma.py, bik.py, bcs.py, scripts.py
  convert/              png.py ✅, dxt.py ✅, texture.py ✅ (phase 2); gltf.py ✅, model.py ✅
                        (phase 3); model_import.py ✅ (phase 4: .glb → model, rig
                        validator); later: audio.py, strings.py
  index/ ✅             schema.sql, build.py, query.py (phase 2)
  mods/ ✅              manifest.py, build.py, deploy.py (phase 2)
  studio/ ✅            DR2 Studio v0: app.py, viewers.py (phase 2; inside the package so
                        `dr2 studio` works after pip install)
native/lzx/ ✅          dr2lzx: libmspack's lzxd.c (LGPL, separate library) + a small wrapper, CMake
blender/io_dr2/         Blender add-on (vendors dr2kit at build time)
tests/ ✅               unit tests on synthetic data; game-data tests (skip if absent)
tools/ ✅               developer scripts (PyAV codec check, the phase 3-4 gates)
docs/                   this file, formats.md, roadmap.md, guides
```

*Change from the phase 0 plan:* the CLI lives inside the package (`dr2kit/cli/`) rather
than in a top-level `cli/`, so `pip install` ships it with the `dr2` entry point and
`python -m dr2kit` works.

## Stack and why

| Choice | Why |
|---|---|
| **Python core** | The CZ recomp's working tooling (`.big` I/O, LZX encoder, untiling, hashes) is already Python. Blender add-ons must be Python, so one core serves the CLI, the GUI and Blender. |
| **Pure Python + optional numpy** | Blender bundles numpy but no compiler and no pip-installed C extensions. Hot loops (untiling, DXT decode, vertex unpacking) use numpy when it is present and fall back to plain Python. |
| **LZX decode as a small native library via ctypes**, plus a pure-Python fallback | The decoder is the only part where pure Python is painfully slow, because whole archives are compressed. ctypes needs no build integration with Blender. Ship prebuilt `.so`/`.dll`. |
| **glTF 2.0 (`.glb`) as the interchange format** | Blender imports and exports glTF natively, with armatures, skin weights, materials and **custom properties through `extras`**. So v1 needs no add-on: export `.glb`, edit, export `.glb`, import back. `extras` carry what the game needs (original node names, bone indices, material hashes, palette layout). |
| **Blender add-on (later)** | Nicer UX on top of the same glTF path: one-click import from the index, a rig check panel ("this mesh uses bones the target skeleton lacks"), export straight to a mod folder. |
| **PySide6 (Qt) desktop GUI** | Native file dialogs, a fast thumbnail grid, `QMediaPlayer`/`QAudioSink` for audio, and `QWebEngineView` + three.js for the 3D preview of the same `.glb` the exporter writes (one renderer path to maintain, not two). Runs on Linux and Windows, like the recomps. |
| **SQLite index** | One file, zero setup, fast search across ~25k entries for both games. Rebuilt incrementally from archive mtimes and sizes. |
| **ffmpeg through PyAV** for XMA→PCM (and Bink preview later) | It decodes `xma2`; the recomp runtimes use the same decoder, so packet-by-packet output positions computed by the toolkit match theirs. PyAV wheels bundle an LGPL ffmpeg; it is an optional dependency (`pip install av`), like Pillow. |

## Platforms: Windows, Linux and macOS

All three are first-class targets for the core, the CLI and DR2 Studio (decided
2026-10-08). The recomps don't run on macOS, so the toolkit must **not depend on a
recomp** to get game data.

- **Game data sources:** a recomp's `assets/game/` (auto-discovered next to the
  checkout); any folder holding an unpacked `data/` tree (`dr2 games set`, saved in the
  user config); **the XBLA package itself**, unpacked by `dr2 unpack`
  (`dr2kit/container/stfs.py`, ported from the CZ recomp's `tools/extract_stfs.py` in
  phase 1), so a macOS user needs only their package. Lookup order per game: the
  `DR2_CZ_DATA` / `DR2_CW_DATA` environment variable, then the user config, then a sibling
  recomp (`dr2kit/profiles/__init__.py`).
- **Paths:** `pathlib` everywhere. Virtual paths always use `/` and are compared
  **case-insensitively**. A repeated entry name is addressed as `name#1`, `name#2`… and any
  entry by position as `@N` (phase 1; no shipped name contains `#` or starts with `@`).
  The archives mix cases (e.g. `Prologue.txt`, `chest_Bowling_…`), and names that
  differ only in case count as repeats, so `#N` also keeps extracted names distinct.
  macOS and Windows filesystems are case-insensitive by default and Linux is not, so
  output folders must never contain two names that differ only in case.
- **User folders** via `platformdirs` (config, index database, thumbnail cache):
  `%APPDATA%` on Windows, `~/Library/Application Support` on macOS, XDG dirs on Linux.
- **Native LZX library:** CI builds `.dll` (x64), `.so` (x86_64, aarch64) and a universal
  `.dylib` (arm64 + x86_64), and keeps them as artifacts. Loading falls back to pure
  Python (about 3-4 MB/s, roughly 30x slower), so a missing or blocked binary (e.g. macOS
  Gatekeeper) is slow, not broken. `dr2 doctor` says which path it is using.
- **ffmpeg:** use **PyAV** wheels, which bundle ffmpeg on all three OSes, for XMA and Bink
  decoding. Falling back to a system `ffmpeg` binary is allowed. **Checked in phase 1**
  (`tools/check_pyav_codecs.py`): PyAV 19.0.1 (ffmpeg 9.0.2) on Linux x86_64 has `xma1`,
  `xma2`, `binkvideo`, `binkaudio_dct` and `binkaudio_rdft`. CI runs the same check on
  Windows, macOS arm64 and macOS x64 (job `pyav-codecs`); if one lacks a decoder, ship
  our own minimal ffmpeg build (the CZ recomp has `tools/build_ffmpeg_lgpl.sh`).
- **3D preview:** `QWebEngineView` + three.js exists on all three platforms in PySide6 6.x.
  **Built in phase 3** (`studio/model_view.py`): three.js 0.186.1 vendored unmodified
  (MIT), served with the model's `.glb` over a custom `dr2:` URL scheme (Chromium
  refuses ES modules from `file://`). Without WebEngine, Studio says so and offers
  *Export .glb…*; a `QOpenGLWidget` renderer remains the fallback plan if a platform
  needs it (macOS caps OpenGL at 4.1, so keep shaders GLSL 3.30-compatible).
- **Audio playback:** decode to PCM ourselves and play through `QAudioSink` (QtMultimedia).
  Don't hand XMA to the OS media backend.
- **Packaging:** PyInstaller (or Nuitka) per OS in a GitHub Actions matrix:
  `windows-latest`, `ubuntu-22.04` (AppImage, with an old glibc baseline like the recomps'
  "oldbase" builds), `macos-14` (arm64) + `macos-13` (x64) or one universal2 build.
  macOS builds need ad-hoc signing at least; notarization once an Apple developer
  account exists. The Blender add-on is plain Python and works the same on all three.
- **CI:** unit tests (synthetic data) run on all three OSes on every push. Census tests
  need game data and run locally only.

## The asset index

Built once per game install by `dr2 index build`, then refreshed incrementally. One row
per entry, at every nesting level:

```
asset(id, game, vpath, archive_file, parent_id, name, name_hash, ext, kind,
      stored_size, size, compressed, data_offset, sha1)
texture(asset_id, width, height, format, mips, tiled, is_cube, thumb_png)
audio(asset_id, channels, rate, shape, samples, exact, loop_start, loop_end)   -- phase 5
sound_ref(src_id, kind, slot, bank, name, context)   -- what a .sfx / scene script names
model(asset_id, mesh_count, vert_count, bone_count, skeleton_guess)
skeleton(asset_id, bone_count, root_name)
relation(src_id, dst_id, kind)   -- model→texture (material slot), .sfx→xma ('sfx-track'),
                                  -- scene script→sound ('script-asset'); later model→skeleton,
                                  -- cinematic→anim
```

This answers the "which texture is what" questions:

- Texture → which models use it, in which material slot (`_cm`/`_dm` colour, `_nm` normal, …),
  found by reading each model's `MatTextureInfoArray`.
- Model → its textures (thumbnails in the side panel) and the skeleton it binds to,
  matched by bone-name set against `data/skeleton/*.big`.
- Sound → the `.sfx` that play it and the scene-script events that trigger it, from the
  `.sfx` tracks and `data/audio/*.txt` / `scenegraph.txt` (`cAudioScene` /
  `cAudioJukebox` / `Asset = "music.big/…"`) (✅ phase 5). Voice lines (the numbered
  `charvocals.big` sounds) have no names yet: the GASP dialogue tables in `gasp.big` link
  them by number only.
- Later, if the recomp runtime gains an "identify" hook: the textures bound in the frame
  the player is looking at (the CZ recomp's F9 census already produces this), shown
  highlighted in the browser.

## DR2 Studio (GUI)

- **Left:** game switcher (CZ / CW / both) and a tree of archives with nested entries.
  Search by name, hash, kind, or relation ("textures used by `chest_default`").
- **Centre:** a viewer per kind.
  - Texture: zoom, alpha/RGB/single channel, mip selector, cube faces, tiled/untiled
    toggle (for debugging), format and size info.
  - Audio: waveform per channel, play/stop, click to seek, loop region shaded and
    *Loop* to hear it repeat (✅ phase 5, `studio/audio_view.py`).
  - Model: three.js orbit view with textures applied, skeleton overlay (✅ phase 3, with
    wireframe and *Export .glb…*); per-mesh visibility, bone-name hover (later).
  - Skeleton: the 3D view shows the bones (✅ phase 3); a bone tree (later).
  - Text/scripts/strings: syntax-highlighted, editable as a mod override.
  - Bink (CW): play through ffmpeg.
- **Right:** metadata and relations, plus **Extract** (in native or converted format),
  **Add to mod** and **Replace…** buttons.
- **Mod panel:** the active mod's overrides, a conflict check against other mods,
  **Build** and **Deploy to recomp**.

## Mod package format

A mod is a folder (zipped for distribution) holding **user-format** files, so modders
never touch tiled DXT or LZX:

```
my_mod/
  mod.toml                    # id, name, version, games = ["cz","cw"], author, description, priority
  replace/
    data/models/npcs.big/chest_default.tex/chest_default_cm.png
    data/models/npcs.big/chest_default.big.glb
    data/audio/music.big/HB_Indemnify.xma.wav  # or .ogg/.flac/.mp3; played by the recomp
    data/frontend/str_en.bcs.json            # string overrides, by id
  add/                        # new entries (later phase; needs loader/manifest support)
```

`dr2 mod build my_mod` converts each file to the native format (encode DXT, re-tile,
generate mips, re-encode LZX when the original was compressed, rebuild the model chunks),
re-packs every touched archive (nested `.big` included), and writes an output tree that
mirrors `data/`. Two deploy targets:

1. **Recomp overlay (preferred):** copy the tree to `assets/game_mods/` in a recomp
   (✅ both recomps since phase 2). Audio replacements only work here: they are not
   game files but `dr2kit_audio/` (WAVs and a substitution table) that the recomps read.
   See "Recomp integration" below.
2. **Patched archives:** whole replacement `.big` files that work anywhere (Xenia, a real
   console, or dropped into `game_patched` today).

Build is deterministic and verified: every output archive passes a read-back and an LZX
decode check before deploy. With no overrides, `build` must reproduce the original files
byte for byte (the round-trip gate).

## Model and skeleton pipeline

**Export (game → Blender).**
1. Read the model `.big` (nested chunks: `_BONEHIERARCHY_`, `_BONENAMES_`,
   `Combined Vertices`, `Combined Indices`, `MatArray`, `MatTextureInfoArray`,
   `SceneDescription`, `persistent.big`, …).
2. Decode vertex streams (layout from each draw's own vertex declaration,
   `D3DVertexDesc` in the model's `persistent.big`; the shader banks were not needed),
   triangle strips, and per-draw **bone palettes** (a run of skeleton nodes named by
   `RenderStrip`; the old community tools stalled exactly here). ✅ phase 3.
3. Build a glTF scene: one armature from the model's own bone hierarchy (every model
   carries its rig), skinned meshes, materials with decoded textures. ✅ phase 3;
   mapping in `dev/gltf-mapping.md`. Materials whose colour is in shader constants
   (value sets: zombie clothing and others) get a texture **baked** with the game's
   formula (`convert/material.py`, 2026-10-09); texture packs are searched in the
   model's archives, its folder on disk, then the index.
4. Put identity data in `extras`: original node and chunk names, bone indices, material
   hashes, shader name (`UsedShaders.txt`, e.g. `LIT_CM`), source vpath.

**Skeleton-only export.** `data/skeleton/<rig>fullbody.big` (plus `face`/`hand`/`upperbdy`
parts) → a `.glb` armature with no mesh, so modellers start from the game's rig.
Same bone names and rest pose as the game. This is the starting point for new models.

**Import (Blender → game).** ✅ phase 4 (`convert/model_import.py` over
`formats/scene_write.py`; rules in `dev/gltf-mapping.md` §Coming back: models).
1. Read the `.glb`. Map bones **by name** to the target skeleton. Refuse with a clear list
   when a mesh is weighted to a bone the target lacks. Parts are matched to the model's
   shapes by object name; skinned vertices are brought back to the rest pose with the
   file's own joint matrices, so Blender's bone orientation doesn't matter.
2. Rebuild the bone palettes (split meshes when a palette would exceed the shader's
   bone-constant limit: 61 bones per draw, `gWorldMatrix[183]` from `c8`, measured in
   phase 3). A palette is a contiguous run of nodes, so a draw whose bones are far apart
   in node order needs a long run or a split.
3. Re-encode the vertex format exactly as the original (positions, normals/tangents,
   UVs, weights/indices in the same packed formats), copying a **template draw** of the
   same material (declaration, command packet, flags). A shape's own buffers are
   rewritten; the shared `Combined Vertices/Indices` are appended to so other shapes keep
   their bytes. Bounds, header counts and packet offsets follow. `SceneDescription` needs
   no change because shapes are replaced, never added. A shape whose parts are unchanged
   keeps its bytes, so a no-edit round trip gives the identical model.
4. v1 rule: **replacement only**. The new mesh takes an existing shape's place and uses
   the model's existing materials and bones. New shapes, materials, shaders or bones come
   later.

Known pitfalls from the community (see `prior-art.md`): finger and face weights broke
the old MaxScript; DR2 vs Off the Record skeleton differences crashed the game; mesh
names the game expects (e.g. no `…deformed` pieces where the target has none) must be
preserved.

## Audio pipeline

Built in phase 5 (`formats/xma.py`, `formats/audioscript.py`, `convert/audio.py`,
`mods/audio.py`, `studio/audio_view.py`; facts in `formats.md` §Audio).

- **Preview/extract:** `.xma` entry → its format: its own RIFF `fmt` chunk (sound-effect
  banks) or its record in `data/audio/cache.big/<bank>.$$$` (streamed banks: music,
  voices, cinematics) → raw packets wrapped in a RIFF header so both shapes take one
  path → ffmpeg's `xma2` decoder through **PyAV** (optional dependency) → 16-bit PCM →
  WAV (`dr2 extract --wav`) or Studio playback (`QAudioSink`).
- **Names:** the `.sfx` that play a recording and the scene-script events that trigger
  it, through the index (`sound_ref` → `relation`).
- **Replace:** no redistributable XMA encoder exists. Two routes:
  1. **Recomp-side PCM substitution (✅ phase 5, both recomps):** the recomps decode XMA
     on the host one packet at a time, so they overwrite the decoded samples of a
     replaced sound with the mod's. The build fits the modder's audio (WAV/OGG/FLAC/MP3)
     to the sound's channels, rate and decoded length and lists every packet's
     fingerprint and output position. See "Recomp integration".
  2. **Native XMA:** run a user-supplied XMA encoder (`xma2encode` from the Xbox 360 SDK;
     we cannot redistribute it) for builds that must run on Xenia or hardware. Not built.
  3. ~~Script-level remap~~ (point an event at another sound in the scene script, as the
     PC community did): **ruled out on Case Zero**, which checks `Prologue.txt` against a
     SHA-1 digest in the executable and crashes on an edited copy (checked in game,
     2026-10-09). Use route 1 with the other sound's audio.

## Textures

Built in phase 2 (`formats/bct.py`, `convert/dxt.py`, `convert/texture.py`; facts in
`formats.md` §Textures).

Decode: `.bct` header (48 bytes, BE: format code, size, mip count, flags; *not* a fetch
constant, which was the phase 0 guess) → layout of every level and cube face (4 KB-aligned
regions, packed mip tail) → untile (`Tiled2DOffset`) → byte swap → DXT1 / DXT5 / DXN /
A8R8G8B8 / L8 → RGBA → PNG. Cube maps export as a strip of six faces.

Encode (replacement, same size and format in v1): PNG → RGBA → per level: encode with
the **original blocks as reference** (a block whose pixels are unchanged keeps its exact
bytes; only edited blocks are re-encoded) → byte swap → re-tile into a copy of the
original payload → header unchanged → back into the `.tex` archive, LZX re-encoded where
the original was compressed. Mips: kept as shipped when level 0 is unchanged, otherwise
rebuilt from the new image with a 2×2 box filter. The encoder is numpy-based (PCA
endpoints + least-squares refinement); calling an external encoder
(`compressonatorcli`/`nvcompress`) for higher quality stays an option for later.

*Changed from the phase 0 plan:* no DDS round trip is needed for lossless re-import: the
reference-block rule makes PNG → `.bct` reproduce the shipped bytes wherever the pixels
are unchanged (checked on every texture of both games).

## Recomp integration (approved 2026-10-08 for CZ and CW)

Two runtime changes, made in each recomp repo following that repo's own conventions
(its CLAUDE.md, a `CZ_`/`CW_` off-switch env var for every new behaviour, a gotcha entry).

1. **`game_mods/` VFS layer.** Checked **before** `game_patched`, `game_kbm` and
   `game_bootskip` in `runtime/kernel/vfs.cpp`, and keyed on the same translated path.
   Off switch `CZ_NO_MODS=1` / `CW_NO_MODS=1`. Log every file served from it. **Conflict
   rule:** when `game_patched` (the recomp's own options/co-op patches) and a mod both
   carry the same archive (e.g. `datafile.big`), a whole-file override would silently drop
   the recomp's patch. So `dr2 mod deploy` builds the mod archive **on top of the
   `game_patched` copy when one exists**, and the runtime only serves whole files.
   Merging stays in the toolkit; the runtime stays simple.
2. **PCM audio substitution** (✅ phase 5, both recomps, `runtime/kernel/audio.cpp`).
   After each XMA packet is decoded, if the packet belongs to a replaced sound, the
   samples it produced are overwritten with the mod's (`game_mods/dr2kit_audio/`).
   Off switch `CZ_NO_AUDIO_MODS=1` / `CW_NO_AUDIO_MODS=1` (and `*_NO_MODS`).
   **Design change from the plan above:** the plan was to map a guest XMA buffer back to
   its `.big` entry by tracking `NtReadFile` handles and offsets in the VFS. Instead
   every packet of a replaced sound is listed by a 64-bit hash with the position its
   output starts at, so each packet identifies itself: no VFS bookkeeping, and loops,
   streaming through re-armed buffers and reused contexts need no special cases. Packets
   that also occur in another sound only continue a substitution, never start one.
   Details and the test procedure: `dev/recomp-integration.md` §Audio substitution.

Timing: (1) landed with phase 2, (2) with phase 5.

## Non-goals (for now)

- Editing levels/zones (`models/environment/prologue/*.big`, 10-73 MB each). We index and
  preview them; editing comes after characters and props work.
- Animation editing. Export for reference later; import is a stretch goal.
- Supporting the PC releases of DR2 / Off the Record. The formats are close and the old
  community tools target them, but our oracles are the 360 data. Keep the code
  platform-aware (byte order, tiling) so PC support stays possible.

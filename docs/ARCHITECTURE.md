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
                        xma.py ✅, audioscript.py ✅ (phase 5); shader.py ✅;
                        bcs.py ✅ (phase 6: string banks); later: anim.py
  convert/              png.py ✅, dxt.py ✅, texture.py ✅ (phase 2); gltf.py ✅, model.py ✅
                        (phase 3); model_import.py ✅ (phase 4: .glb → model, rig
                        validator); audio.py ✅ (phase 5); material.py ✅; strings.py ✅,
                        video.py ✅ (phase 6: Bink through PyAV, no format code of ours);
                        render.py ✅ (phase 8: model pictures for the Library)
  index/ ✅             schema.sql, build.py, query.py (phase 2; scene facts, rigs, Library: phase 8)
  catalog/ ✅           groups.toml + groups.py (the Library's groups), export.py (export all) (phase 8)
  help/ ✅              the in-app help: the modding guides as pages, search, context help (phase 7)
  mods/ ✅              manifest.py, build.py, deploy.py (phase 2), audio.py (phase 5),
                        library.py (phase 6: the mod manager), play.py (phase 7: Play)
  studio/ ✅            DR2 Studio v0: app.py, viewers.py (phase 2; inside the package so
                        `dr2 studio` works after pip install)
native/lzx/ ✅          dr2lzx: libmspack's lzxd.c (LGPL, separate library) + a small wrapper, CMake
blender/io_dr2/ ✅       Blender add-on (phase 6), GPL-3.0; imports dr2kit from the user's
                        toolkit folder at run time, never bundles it (decision 2026-10-09)
packaging/ ✅           PyInstaller spec, entry scripts, the release README (phase 6)
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
- **Packaging** (✅ phase 6, `dev/packaging.md`): PyInstaller, one folder with two
  executables (`DR2Studio` windowed, `dr2` console), per OS in a GitHub Actions matrix
  (`.github/workflows/release.yml`): `ubuntu-22.04` (AppImage + tar.zst, glibc 2.35
  floor like the recomps' "oldbase" builds), `windows-latest` (zip), `macos-14` (arm64,
  zip of an ad-hoc-signed app; notarisation once an Apple developer account exists).
  *Decision:* releases bundle PyAV **built against an own LGPL ffmpeg**
  (`tools/release/build_ffmpeg_lgpl.sh`), because PyPI's PyAV wheels link GPL x264/x265;
  the release builder refuses any bundle with a GPL library. The Blender add-on is
  plain Python and works the same on all three.
- **User folders without platformdirs** (`dr2kit/userdirs.py`): Blender's Python lacks
  platformdirs, so dr2kit computes the same default folders itself when it is missing
  (a test compares both on every CI OS).
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
scene(asset_id, bones, meshes, draws, vertices, max_part_vertices, max_draw_bones,
      materials, bone_names, bone_pos, thumb_png, problem)              -- phase 8
library_item(asset_id, game, grp, sub, label, copy_of)                   -- phase 8
relation(src_id, dst_id, kind)   -- model→texture (material slot), .sfx→xma ('sfx-track'),
                                  -- scene script→sound ('script-asset'), model→skeleton
                                  -- ('model-rig', phase 8); later cinematic→anim
```

This answers the "which texture is what" questions:

- Texture → which models use it, in which material slot (`_cm`/`_dm` colour, `_nm` normal, …),
  found by reading each model's `MatTextureInfoArray`.
- Model → its textures (thumbnails in the side panel) and the skeleton file it was made
  for (✅ phase 8, `build.link_rigs`): the skeletons whose bone names include all of the
  model's, ranked by rest pose, because the player, female, large and child rigs share
  their 98 names and differ only in proportions.
- Sound → the `.sfx` that play it and the scene-script events that trigger it, from the
  `.sfx` tracks and `data/audio/*.txt` / `scenegraph.txt` (`cAudioScene` /
  `cAudioJukebox` / `Asset = "music.big/…"`) (✅ phase 5). Voice lines (the numbered
  `charvocals.big` sounds) have no names yet: the GASP dialogue tables in `gasp.big` link
  them by number only.
- Later, if the recomp runtime gains an "identify" hook: the textures bound in the frame
  the player is looking at (the CZ recomp's F9 census already produces this), shown
  highlighted in the browser.

## The Library (phase 8)

The archive tree shows the games as they are stored; the **Library** shows them by what
they are. A rules file (`dr2kit/catalog/groups.toml`, data, not code) puts every model,
skeleton, sound, texture, string bank, movie and game text file into one group of a
section (Models → Characters, Zombies & enemies, Weapons & items…; Sounds → Music,
Voices, Footsteps…), optionally a sub-group (by name prefix, by the archive it is in, by
texture role) and a friendlier label. The index applies the rules after each build
(`library_item`), so Studio and the CLI list a group in milliseconds and the counts can
be checked against the index (`dr2 library --check`). Identical copies are folded into
one item (`copy_of`), preferring the copy outside `preload4.big`. Phase 9 folds a
model's **detail levels** the same way (`[[detail]]` rules: `zombie_cop_2/_3/_4` →
one *Zombie Cop* with a Detail choice; `detail_of`); exports still write every level.

Model pictures are **3D renders** (user decision, 2026-10-09) made while the index is
built, by a numpy software renderer (`convert/render.py`) rather than Studio's 3D page:
the index is built by the CLI too, without a window or a GPU, and the renderer needs
~0.05 s per model, using the index's own texture thumbnails (and baking zombie clothing
colours from shader constants, like the export) (measured: about a minute
for the ~1,400 models of a game).

**Export everything at once** (`dr2kit/catalog/export.py`): one folder per model
(`<name>.glb` with textures and skin, `textures/*.png` + `textures.txt`, `skeleton.glb`,
`info.txt`), one file per sound (WAV), movie (MP4), string bank (`.bcs.json`) or texture
(PNG) (user decision: one folder per asset). Group exports go to `<out>/<game>/<group>/
<sub>/` so the two games never mix; files are written under a temporary name and renamed,
and existing ones are skipped, so an export can be cancelled and resumed. Studio runs it
in a worker thread with a progress bar; `dr2 export` is the same from the terminal.

## DR2 Studio (GUI)

- **Left:** game switcher (CZ / CW / both); the **Library** tab (first, phase 8: groups by
  what things are, pictures, export of a selection or a whole group); **Files**, the tree
  of archives with nested entries; **Search** by name, hash, kind, or relation ("textures
  used by `chest_default`").
- **Centre:** a viewer per kind.
  - Texture: zoom, alpha/RGB/single channel, mip selector, cube faces, tiled/untiled
    toggle (for debugging), format and size info.
  - Audio: waveform per channel, play/stop, click to seek, loop region shaded and
    *Loop* to hear it repeat (✅ phase 5, `studio/audio_view.py`).
  - Model: three.js orbit view with textures applied, skeleton overlay (✅ phase 3, with
    wireframe and *Export .glb…*); per-mesh visibility, bone-name hover (later).
  - Skeleton: the 3D view shows the bones (✅ phase 3); a bone tree (later).
  - Text/scripts: editable into the open mod, with a diff against the game's text;
    strings: a filterable table whose edits go into the mod's `.bcs.json` (✅ phase 6,
    `studio/text_view.py`; no syntax highlighting yet).
  - Bink (CW): play through ffmpeg, pictures and sound (✅ phase 6, `studio/video_view.py`).
- **Maps** (✅ phase 10, `studio/maps_view.py`, `web/maps.js`): the second left tab
  lists the levels; the centre is a three.js page that streams a level zone by zone
  (nearest the camera first, the game's small `_LOD` textures far away), each zone built
  once into a `.glb` on disk (`convert/mapdata.py`'s `MapCache`, named by what it was built
  from, so a changed game file or mod is never shown stale) by three builder threads.
  Markers (spawn points, areas, triggers, the nav mesh) come as JSON and are drawn by the
  page. Level materials (lightmaps, two-texture blends) travel in the `.glb` as the
  occlusion texture and material extras and are drawn by `web/levelmaterials.js` the way
  the level shaders do (both 3D views use it). *Export zone / level* writes
  `catalog/level_export.py`'s folder (one `.glb` per zone, grouped by layer; the add-on's
  *Import zone* turns the groups into collections).
- **With my mods** (✅ phase 10, `mods/preview.py`, toolbar switch, Ctrl+M): every view
  (assets, Library marks, Maps, exports) reads a `ModdedTree`: the game with the mod
  library's switched-on mods applied the way Play builds them (the same bytes), so a
  change is seen without the game; off, the game as shipped. Mod folders are watched:
  a saved file redraws. Checks of a mod against the game (rig check, mod plans) keep
  reading the game itself.
- **Help inside the app** (✅ phase 7): the modding guides are the help (`dr2kit/help`,
  copied into packages by `setup.py`; English, one folder per language for
  translations, user decision 2026-10-09), shown in a searchable window (F1), a "How to
  mod this" box per asset kind, a Help button on errors, a Welcome checklist, and
  `dr2 help` in the terminal.
- **Right:** metadata and relations, plus **Extract** (in native or converted format),
  **Add to mod** and **Replace…** buttons.
- **Mod panel:** the active mod's overrides, **Build && deploy**, **Undeploy**.
- **Mod manager** (✅ phase 6, `studio/mod_manager.py`): the mod library, load order,
  on/off, conflicts, install/pack zips, deploy every switched-on mod.

## Mod package format

A mod is a folder (zipped for distribution) holding **user-format** files, so modders
never touch tiled DXT or LZX:

```
my_mod/
  mod.toml                    # id, name, version, games = ["cz","cw"], author, description, priority
                              # [requires]: other games' data, mods, saves, co-op (phase 15)
  replace/
    data/models/npcs.big/chest_default.tex/chest_default_cm.png
    data/models/npcs.big/chest_default.big.glb
    data/audio/music.big/HB_Indemnify.xma.wav  # or .ogg/.flac/.mp3; played by the recomp
    data/frontend/str_en.bcs.json            # string overrides, by id
    data/datafile.big/prologue.txt.edits.json  # level / mission edits, by block (phase 11)
    data/models/environment/prologue/prologue_z04.big/ZONE_ORGANIZATION.big.pieces.json
    data/models/environment/prologue/prologue_z04.big/MERGED_COLLISION.big.pieces.json
                              # buildings: hidden, moved, copied; their collision (phase 11)
  add/                        # new entries (phase 11): add/<archive vpath>/<name>, or a
    data/streamedassets.big/MyItem.big.copy.json   # recipe that makes it from the player's game
    data/models/environment/prologue/prologue_z02.big/my_box.big.copy.json   # a new level piece
    data/models/environment/food_barn/zonelist.big.copy.json  # a NEW FILE (phase 14): its
                              # folder is a folder, not an archive
    data/shaders/deadrisingprologue-ps.big/1c2d3e40.po.copy.json  # phase 15: a recipe
                              # "from": "cw" (built from the player's own Case West), here
                              # a Case West shader brought under a new name ("shader")
  sources/                    # the modder's own .glb / PNGs a recipe uses
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

**Several mods and the mod manager** (phase 6, `mods/library.py`). Any number of mods
build together; an asset two mods replace goes to the higher priority, and string
overrides merge per string id. The mod manager keeps installed mods in a **library**
folder (per-user data folder by default) with a `modlist.toml` holding the **load
order** and an on/off switch per mod. *Decision:* the load order *is* the priority
(later wins), so two switched-on mods never tie and a conflict is reported, not an
error; `priority` in `mod.toml` only places a newly installed mod. Mods are shared as
zips (`dr2 mod pack`), installed with `dr2 mod install` (zip entries that would land
outside the mod are refused).

**From making to playing (phase 7).** The library also holds the mod being made: a new
mod is created inside it, a mod opened elsewhere is *linked* (stays in its folder). So
"what's in the game" is always "the library's switched-on mods": **Play**
(`mods/play.py`, `dr2 play`) builds them, deploys them into `game_mods/` and starts the
recomp (found beside its game folder; user decision 2026-10-09: Studio may start it).
*Decision:* a shared mod is a **`.dr2mod`**, a zip with its own extension
(`mod.toml`, `replace/`, `preview.png`, `README.md`; never game data), made by *Share…*
/ `dr2 mod pack` after a check against each game it names. Mod sets save which mods are
on.

**The other game's things (phase 15, `mods/importitem.py`, `convert/shadercarry.py`).**
A recipe can read the other game (`"from": "cw"`), so a mod uses Case West's items in
Case Zero and still holds no game data; text comes the same way (a `.bcs.json`'s
`"copy"`). *Decision (user, 2026-10-12):* a brought model draws with **its own game's
shaders**, copied into the target's banks under new names, never remapped to a nearest
one. The importer resolves every name an item uses (kept / brought / renumbered /
dropped with a reason); `dr2 census --import` checks every item of each game resolves
into the other. Engine limit found on the way: the renderer's pool of shader constant
sets (CZ 384, CW 1,340, one per pixel shader) leaves room for ~26 brought pixel shaders
in CZ and ~3 in CW; growing it is a recomp change (asked, 2026-10-12).

**What a mod needs (phase 15, `mods/requires.py`).** A mod made from the other game's
files (a recipe with `"from": "cw"`) can only be built where that game's data is, and
some mods need other mods, change what saves hold, or change the world every co-op player
must share. *Decision (user, 2026-10-12, proposed default):* `[requires]` in `mod.toml`
(optional, what the modder writes) + **`requirements.json`** (machine-readable, the
contract a launcher such as XenonLive reads: title ids, mods with versions, saves, co-op,
a `content_hash`) + **`REQUIRES.txt`** (plain words), both written into every `.dr2mod`
and the build's `dr2kit-build.json`. The toolkit fills what the modder didn't write
(`infer`: games from recipes, `saves = "needs-mod"` when the mod adds anything, `coop =
"local"` when it only changes looks and sounds). The build refuses a mod whose needs this
computer lacks (`plan_mods` → `check`), naming what is missing; a build for one game needs
that game and the games its recipes copy from, not the other game it also supports.

**Level edits (phase 11).** The engine's block text files (`prologue.txt`,
`missions.txt`…) are changed by **`.edits.json`** files that hold only a mod's changes,
by block path (`formats/leveledits.py`). *Decision (user, 2026-10-11):* edits by block,
not whole `.txt` replacements, because the CZ recomp edits `missions.txt` itself (its
co-op changes in `game_patched`) and two mods each moving one zombie must not replace each
other's file. The build applies them over the copy underneath, merges several mods
(conflict only on the same key of the same block), and checks their meaning
(`convert/levelcheck.py`); a whole `.txt` still works but the build warns that it drops
the recomp's changes, and `dr2 level diff` turns one into an `.edits.json`. Editing
tools hold the edited file and save its difference from the game's (`mods/leveledit.py`),
so the mod always holds exactly its changes.

**Building edits (phase 11 step 4).** The zones' buildings (binary placement records) and
their collision (Havok shapes) are changed the same way: `.pieces.json` files next to a
zone's `ZONE_ORGANIZATION.big` and `MERGED_COLLISION.big` hold only what a mod changes, by
piece and by shape (`formats/pieceedits.py`), merged across mods. *Decisions (2026-10-11,
from the in-game tests):* a hidden piece is parked under the level rather than removed
(no other record moves); collision is not tied to a piece, so the editor works on whole
**buildings** (`convert/buildings.py`: pieces and shapes grouped by shape, name and
touch; the modder can correct the grouping) and moves their collision with them; collision
is only moved or sent away, never turned, because Havok's search tree can't be rebuilt.

**DR2 Studio's window (2026-10-11).** Every panel is a dock window (`studio/docks.py`):
resized, moved, tabbed or floated, the layout kept between sessions; the Maps tab's editor
works like a game editor's (Inspector, Hierarchy, Place with drag and drop, arrow-key
nudging). dev/studio.md, "Dock windows".

**New files (phase 11).** `add/` puts new entries into archives (inserted in name order,
compressed like their neighbours, declaring their siblings' alignment in `flags`: the
game hangs on a new entry declared 0). *Decision:* a new item copied from a game item is
stored as a **recipe** (`.copy.json`, `mods/newitem.py`), never as the copied bytes, so a
shared mod holds no game data; the build makes the pack from the player's own game.

**New loose files and new level pieces (phase 14).** An `add/` file whose folder is a
folder (or a folder the game doesn't have) is a **new file** of the build (kind `file`),
and `layout.bin` gets a record for it (the game's table of loose files; it hashes the
names itself: `formats.md` §Levels, "Level slots"). A copy recipe also copies plain files
(a level's text files, with level edits applied) and level pieces (the scene inside
renamed, its pictures given names of their own: a zone shows the first texture of a
name). *Decisions (phase 12, the user's):* a building of one's own is a **new level piece
plus an invisible collision item**; a map of one's own goes only into the executable's
**empty level slots**, started as a copy of a level. Whether the game takes them: the
in-game tests T4a, T4b, T5 (`phase14-kickoff.md`).

**Animations (phase 14).** Every `.anm` is read to its last key (`formats/anim.py`); a
move is turned into a clip by node name (`convert/holding.py`) that Studio's three.js
pages sample each frame (`web/hold.js`: the weapon follows the hand node) and that goes
into `.glb` files as a glTF animation (Blender: an Action) on every copy of the rig's
nodes (each of Chuck's parts carries the rig). Nodes a move doesn't touch get Chuck's
rig's rest values, never a part's own (the boots' rest pose differs).

**Particle effects (phase 13).** A mod changes a game effect with an `.effect.json`
(its name and the changes: hue, size, pictures…; `convert/effects.py`) or adds one of its
own as a copy recipe into one of the effect table's **36 free slots** (`mods/neweffect.py`;
the table of numbers is in the executable and can't grow). Three build rules, each
measured in game (CZ, 2026-10-12; `formats.md` §Particle effects): an added effect is
listed in the effects' scene file (`register_in_scene`); a file the game keeps a copy of
in `preload4.big` is **evicted** there (its index hash flipped, 4 bytes; re-encoding
inside `preload4.big` crashes the boot) so the loose file is read, per the profile's
`preload_evict`; and when a built file changes size, a re-pinned **`layout.bin`** (every
file's size) is written (`repin_layout`), since a file bigger than its pinned size
crashes when opened.

**Other games' assets (phase 13, decision 3).** Bringing a model or an effect in from
another game is a **local tool** (`tools/wow_import.py`, not in Studio or the CLI): it
reads the modder's own install and writes into a mod it marks **`local_only`**, which
`library.pack` (*Share…*) refuses. Any model still comes in as a `.glb` through the weapon
wizard; another game's particle emitters become one effect of one's own (the `layout`
change: copies of a base emitter, then their fields).

**Chuck holding a weapon (phase 13.2).** The 3D view never hard-codes a pose or an
outfit: Chuck's parts come from the game's `outfits.csv`, the idle from its animation
graph `sgraph.txt` (the item's `AnimationChooserValueForIdle` / `…ForHand`), the pose
from the `.anm`'s first frame on the game's rig `playerfullbody.big`, and the weapon
hangs from his `r_hand_prop` node by its own grip node (`convert/holding.py`). Studio
sends Chuck once at rest and the pose as data, so the page poses him (changing kinds is
instant); the same pose baked into one `.glb` is `dr2 hold` for Blender. Drag handles in
the page only send numbers back (slide, turn, length, effect start): the wizard's
`WeaponSpec` stays the one source, and the model is fitted again from it.

**Files mods can't touch.** The executables digest-check a few data files (CZ 1, CW 6;
`formats.md` §Digest-checked files). Each game profile lists them (`digest_checked`) and
the build refuses an override of one, since the game would crash.

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

**Variants (phase 9, `convert/variants.py`; guide `modding/17-variants.md`).** A zombie
model holds every look at once; the game shows one choice per slot, decided by the
**shape names** through a table compiled into the executable. The toolkit keeps that
table as profile data (`[variants]` in `cz.toml`/`cw.toml`, copied once by
`tools/variant_table.py`, so the executable is never needed) and classifies shapes with
the game's own prefix rule, so a look converts to the game's 64-bit hide mask and back.
Design choices (user: "whatever is best", 2026-10-10):
- The **default look** (pictures, 3D view, exports) is one choice per slot (the first),
  never everything; *Show everything* stays one click away. The game's own pick is not
  known yet, so the default is not claimed to be the game's.
- **Two export modes**, one code path (`convert.model.model_glb`): *as shown* (only the
  chosen parts; the viewer's Export .glb) and *everything, organised* (every part tagged
  with its group and shown flag, colour choices as `KHR_materials_variants`; Export all,
  Open in Blender, groups). Blender has no glTF visibility extension, so node extras +
  our Blender scripts make the collections; other programs get the shown export.
- **Colour choices** are other value sets found by name in the shader bank; they only
  change shader constants, so they reuse the colour bakes.
- **Prop states** (twin shapes: `slot_logo` / `slot_logo_dmg`) by name rules, off by
  default; buildings are not classified (the census lists variant-like pieces).
- Re-import needs nothing new: shapes are matched by name, and parts a file leaves out
  are kept as they are.

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
   *Known limit (phase 6):* `game_kbm` (keyboard prompts) and `game_bootskip` are
   toggles, so a mod is not built on top of them; a deployed mod carrying the same file
   (`str_en.bcs`, `fecmn.big`) wins over the toggle while installed, and deploy warns.
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

3. **Growing Case West's tables** (approved by the user 2026-10-12 for phase 15; not
   built yet). Case West's program is built for 10 zombie types (its type table and every
   loop over it, count `0xA`) and 10 level slots; the engine takes 32 types (the type is
   checked against 31 in both games) and Case Zero is built for 32 types and 82 levels.
   The Case West recomp grows its zombie type table to 32 (every place that walks it, and
   any array sized by it) and its level table (script names, zone lists, ids), so mods
   can add zombie types and maps natively. Made in the CW repo following its CLAUDE.md,
   with a `CW_` off switch and the census of every place changed; Case Zero gets the same
   check (already 32). `phase15-kickoff.md` §How many types and levels.
4. **Growing the shader constant set pool** (approved by the user 2026-10-12 for phase
   15, "Yes you got my approval"; not built yet), **in both recomps**. The renderer's
   pool of shader constant sets (one per loaded pixel shader) is sized from a table in
   the executable's data: CZ `0x829ED7F4` = 384 (~26 free), CW `0x82A00D34` = 1,340 (~3
   free); more brought pixel shaders assert "Shader constant set overflow" (formats.md
   §Across the games: shader banks). Each recomp writes a larger value (proposed 4,096)
   into guest memory after the image loads and before the renderer builds its pools,
   with an off switch (`CZ_NO_SHADER_POOL_GROWTH=1` / `CW_…`), in a file of its own (the
   CZ repo has the user's uncommitted `vk_renderer.cpp`: don't touch it), following each
   repo's CLAUDE.md; checked by a headless load with the Laser Sword mod (test U1). The
   same approval covers adding the deployed mods' shader banks to the first-run shader
   build (no pop-in), if wanted.

## Non-goals (for now)

- Editing levels/zones (`models/environment/prologue/*.big`, 10-73 MB each). We index and
  preview them; editing comes after characters and props work.
- Animation editing. Export for reference later; import is a stretch goal.
- Supporting the PC releases of DR2 / Off the Record. The formats are close and the old
  community tools target them, but our oracles are the 360 data. Keep the code
  platform-aware (byte order, tiling) so PC support stays possible.

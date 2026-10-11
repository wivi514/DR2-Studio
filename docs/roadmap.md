# Roadmap

Each phase ends with a **gate**: a measurable check, not "it looks right". A phase is
also not done until its docs are: the modder guides it enables (`docs/modding/`), the dev
pages (`docs/dev/`), and a devlog entry.

## Phase 0: preparation ✅ (2026-10-08)
CLAUDE.md, architecture, format inventory, prior-art survey, this roadmap. Skeleton
record layout verified across all 76 skeleton files in both games.

## Phase 1: core container and census ✅ (2026-10-08)
- `dr2kit.container.big`: read/write ported from `gen_pc_options.read_big/write_big` +
  `big_list.py`, with nested virtual paths (`name#N` for repeated names, `@N` by
  position), duplicate names and zlib support in the reader. ✅
- LZX: native decoder (ctypes, libmspack in its own library) + pure-Python fallback
  written from the format description; `lzx_encode_stream` ported (now also writes
  uncompressed blocks for chunks that don't compress, as the game's encoder does). ✅
- Game profiles `cz.toml` / `cw.toml` with auto-discovery of the sibling recomps, a user
  config (`dr2 games set`), env vars, plus STFS package extraction (`dr2 unpack`). ✅
- Cross-platform skeleton: `pyproject.toml`, CI matrix on Windows/Linux (x64 + arm64)/macOS,
  native LZX builds for all three, and a check of PyAV's `xma2`/Bink decoders on each OS
  (✅ on Linux; Windows/macOS run in CI once the GitHub remote exists).
- `dr2 ls`, `dr2 extract [--decompress]` (decompresses by default; `--raw` keeps the
  stored stream), `dr2 census`, plus `dr2 find`, `dr2 games`, `dr2 unpack`, `dr2 doctor`. ✅
- Docs: `dev/code-tour.md`, `dev/setup.md`, `dev/adding-a-format.md`, `dev/testing.md`,
  `modding/02-game-data.md`, `modding/12-troubleshooting.md`, `THIRD_PARTY.md`. ✅
- **Gate:** every archive in CZ *and* CW round-trips byte-identically; every compressed
  entry decodes to its `size2`; the census names every extension and every
  unparsed entry (target zero).
  **Result:** CZ 7,413/7,413 and CW 8,017/8,017 archives (nested included) round-trip;
  10,754 + 21,354 compressed entries decode, re-encode and decode back, and two
  independent decoders agree on all of them; 0 unparsed in either game. Details:
  `dev/testing.md`, `formats.md`.
- **Not proven yet:** that the *game* accepts entries re-encoded by our encoder. That
  is the phase 2 in-game gate (`game_mods/`).

## Phase 2: textures + index + first GUI ✅ (2026-10-08)
Handoff was `phase2-kickoff.md`; the next one is `phase3-kickoff.md`.
- `.bct` decode (`formats/bct.py`): the header is the engine's own (format code, size,
  mips, flags), not a fetch constant; layout of mips, packed mip tail and cube faces;
  untile; DXT1/DXT5/DXN/A8R8G8B8/L8 → PNG. Census of every texture in both games. ✅
- SQLite index (`index/`) with thumbnails; model→texture relations from
  `MatTextureInfoArray`; incremental rebuilds; `dr2 index build|search|used-by|textures-of`. ✅
- DR2 Studio v0 (`studio/`): tree, search with thumbnails/grid, texture viewer (zoom,
  channels, mips, cube faces), related assets, extract / export PNG, mod bar. ✅
- Texture **replacement** (same size and format): PNG → DXT (reference blocks keep
  unchanged blocks) → tile → `.bct` → `.tex` → LZX → archive. Mod packages
  (`mods/`): `dr2 mod new|check|build|deploy|undeploy`. ✅
- Recomp `game_mods/` VFS layer in both CZ (`057d45b`) and CW (`ebf0bb2`). ✅
- Docs: `modding/03`, `04` (textures), `05`, `06`, `asset-catalogue.md`,
  `12-troubleshooting.md`; `dev/studio.md`, `dev/recomp-integration.md`. ✅
- **Gate:** decode then re-encode reproduces the original data; a recoloured texture in a
  compressed entry shows up in **both** recomps and disappears with the off switch.
  **Result:** 12,237 + 23,139 textures re-encode to identical bytes; Chuck's CZ "04"
  shirt and CW jacket turn green in game through `game_mods/`, and are back to the
  shipped colours with `CZ_NO_MODS=1` / `CW_NO_MODS=1`. The game accepts our LZX streams.
  Details: `dev/testing.md`.
- **Not proven yet:** re-encoded entries in `preload4.big` (boot path); the meaning of
  `.bct` flag bits 0x04/0xE0 and header word 0x0C; why 0.4% of textures carry a larger
  payload than the layout model; texture *resizing* (v1 keeps the size).

## Phase 3: skeletons and models → Blender ✅ (2026-10-08)
Handoff was `phase3-kickoff.md`; the next one is `phase4-kickoff.md`.
- Scene reader (`formats/scene.py`, `vertex.py`): skeleton (52-byte records, truncated
  names, split rigs), materials (by id), meshes and draws from `persistent.big`'s
  `RenderStrip` + `CommandBuffer`, both buffer families (own / `Combined Vertices
  <stride>`), the 360 vertex declarations, triangle strips, **bone palettes** (a run of
  skeleton nodes). Census: every scene of both games parses, every draw decodes. ✅
- Skeleton and model → `.glb` (`convert/gltf.py`, `model.py`): armature with the game
  records in `extras`, skinned meshes, materials with PNG textures found by name;
  `dr2 extract --glb`, `dr2 info` for scenes. ✅
- DR2 Studio 3D view: three.js in `QWebEngineView` on the same `.glb`; *Export .glb…*. ✅
- Docs: `formats.md` §Scene container, `dev/gltf-mapping.md`, `modding/04`, `07`,
  asset catalogue (rigs, models), troubleshooting. ✅
- **Gate (skeleton):** 3,474 / 3,474 node records of the 75 `data/skeleton` rigs of both
  games come back bit-identical after Blender 5.2 import → export
  (`tools/blender_skeleton_gate.py`); 41,184 / 41,209 over every rig in every scene (the
  25 others carry a rest scale Blender bones can't hold).
- **Gate (models):** 6,954 / 6,954 CZ and 10,548 / 10,548 CW draws decode
  (`dr2 census --models`).
- **Gate (in game, CZ):** 30 of Chuck's draws in a captured frame match the reader's
  buffers byte for byte; draws sharing a bone get identical matrices under the reader's
  palette mapping and never under a shifted one; the reader's rest pose keeps the game's
  bone lengths; skinned, projected vertices land on Chuck in the frame
  (`tools/capture_gate.py`). Details: `dev/testing.md`.
- **Not proven yet:** a Case West capture; the meaning of `_ATTRIBUTE_`, `_COLLPRIMS_`,
  value sets, the material floats, tangent w; the unbound extra streams of 10 CW shapes;
  posing in a real *animation* (animations are not decoded yet).

## Phase 4: model replacement (Blender → game) ✅ (2026-10-08)
Handoff was `phase4-kickoff.md`; the next one is `phase5-kickoff.md`.
- Scene writer (`formats/scene_write.py`): serialisers for every chunk the reader
  interprets (each scene of both games rewrites identically), exact vertex encoders
  (`vertex.py`), triangles → strips, and `SceneEditor.replace_mesh`: new vertex and index
  buffers (own buffers rewritten, combined ones appended to), packets cloned from a
  template draw of the same material, `RenderStrip` words (packet offsets found:
  word 5), shape words, bounds, `_BOUNDINGBOX_`. ✅
- `.glb` → model (`convert/model_import.py`): parts matched by object name, bones by
  name, materials by exported name, vertices skinned back to the rest pose, 4 weights
  quantised to 255, palettes of ≤ 61 nodes with automatic splitting; unchanged shapes
  kept byte for byte. ✅
- Rig validator (`plan_import`): `dr2 model check`, `dr2 model import`, Studio's
  *Replace with .glb…*, and `dr2 mod check` for `replace/<model>.glb` overrides. The
  Blender add-on is still later. ✅
- Docs: `formats.md` §Writing scenes (+ the unclamped snorm retraction, tangent w),
  `dev/gltf-mapping.md` §Coming back: models, `modding/08`, `09`, troubleshooting,
  glossary. ✅
- **Gate (no-op):** every model of both games exported to `.glb` and imported back is
  byte-identical (1,397 CZ, 1,495 CW; `dr2 census --reimport`); every shape rebuilt from
  its own geometry decodes to the same triangles and vertex values (6,953 + 10,547 draws;
  the vertex-animated larva is skipped).
- **Gate (in game, CZ):** a `.glb` that went through Blender with the shirt untouched,
  the arms inflated and the watch replaced by a new mesh weighted to every face and
  finger bone (split into 2 draws) loads; all 32 dumped skinning draws match the mod
  build byte for byte; the new mesh's palettes get the same bone matrices as Chuck's own
  head and hand draws (face bones moving, fingers bent up to 45°); the picture shows the
  thicker arms and the spheres on the fingers and face (`tools/blender_gate_model.py`,
  `tools/capture_gate.py --root`). Details: `dev/testing.md`.
- **Not proven yet:** a Case West run in game; a combined-buffer prop replaced in game;
  the look of new tangents on normal maps; adding parts, bones or materials (v1 is
  replacement only).

## Phase 5: audio ✅ (2026-10-09)
- XMA metadata: two shapes of `.xma` (RIFF XMA2 files in the fx banks; raw packets in
  the streamed banks, described by `cache.big`'s `$GIB` stream tables, cracked this
  phase) (`formats/xma.py`). ✅
- → WAV through PyAV (`convert/audio.py`, `dr2 extract --wav`, `dr2 info`), playback in
  Studio (`studio/audio_view.py`: waveform, play, seek, loop). ✅
- Names: `.sfx` tracks and scene-script `Asset` lines parsed (`formats/audioscript.py`)
  and linked in the index with their trigger events (`audio`, `sound_ref` tables). Voice
  lines stay numbered (the GASP tables give no names). ✅
- Replacement: **PCM substitution in both recomps** (`mods/audio.py`; CZ/CW
  `runtime/kernel/audio.cpp`, `CZ_NO_AUDIO_MODS` / `CW_NO_AUDIO_MODS`): `replace/<sound>.xma.wav`
  (or `.ogg`/`.flac`/`.mp3`), fitted to the sound's channels, rate and length. Every packet
  is recognised by its hash and output position, instead of the planned VFS read tracking. ✅
- Script-level remap (planned as the easy path): **ruled out** for Case Zero, which
  digest-checks `Prologue.txt` and crashes on an edited copy (checked in game). The
  guide shows the substitution way to point an event at another sound. User-supplied XMA
  encoder: not built.
- Docs: `formats.md` §Audio (with the "no RIFF header" retraction), `modding/10-audio.md`,
  `dev/recomp-integration.md` §Audio substitution, troubleshooting, glossary. ✅
- **Gate (decode):** every `.xma` of both games decodes to the length its metadata says
  (8,916 CZ + 11,735 CW, `dr2 census --audio`; exact where a length is stored, the packet
  headers' frame total otherwise); every `.sfx` parses (4,745 + 5,194). **Passed.**
- **Gate (in game, both games):** the title-screen music replaced by another track of the
  game plays in its place (recorded through SDL's disk driver: the recording follows the
  replacement at the right positions); the off switch on the same binary plays the
  original. **Passed** in CZ and CW. Details: `formats.md` §In-game check (phase 5).
- **Not proven yet:** a 5.1 cinematic and an fx-bank sound replaced in game; longer
  replacements than the original (the game sets a sound's length; v1 cuts or pads).

## Phase 6: polish and distribution ✅ (2026-10-09)
- Blender add-on `io_dr2` (index browser in Blender, validator panel, export to mod) ✅
  (`blender/io_dr2`, guide `13-blender-addon.md`; scripted through in Blender 5.2).
  *Decision (user, 2026-10-09):* the add-on's own code is **GPL-3.0-or-later** (Blender
  treats add-ons using `bpy` as GPL) and does **not bundle dr2kit**: it imports the
  toolkit from a folder set in its preferences (or from Blender's Python), so dr2kit
  keeps the toolkit license.
- Mod manager: a library folder, load order = priority (later wins), enable/disable,
  conflicts listed with the winner, install/pack zips, deploy every switched-on mod
  (`mods/library.py`, `dr2 mod list/install/enable/move/conflicts/pack`, Studio's
  **Mod manager…**). ✅
- Strings (`.bcs` ⇄ JSON, `formats/bcs.py`, `dr2 strings`, Studio's strings table;
  `.bcs.json` mod overrides merge per string id), text editing into a mod with a diff
  (Studio), CW Bink preview and `.mp4` export (`convert/video.py`). ✅
- Files the executables digest-check, read from the XEX for both games (CZ 1, CW 6):
  mods refuse them (answers phase 5's open question about Case West). ✅
- Packaging: PyInstaller bundle (GUI + CLI), AppImage + tar.zst (Linux), zip (Windows,
  macOS), the add-on zip, `.sha256` files, as the recomps ship; an own LGPL ffmpeg and a
  licence gate (`tools/build_release.py`, `dev/packaging.md`). ✅ on Linux (built and
  tried on Fedora 44); the release workflow for all three OSes is written but has not
  run (no GitHub remote yet). Studio's **Game folders…** for installs without a recomp. ✅
- Guides `01-install.md` ✅, `11-text.md` ✅, `asset-catalogue.md` (text, movies ✅).
- **Gate (strings, in game, both games):** a `.bcs.json` changing `IDS_PRESS_START`
  shows on the title screen. **Passed** in CZ and CW (`formats.md` §Strings).
- **Gate (census):** all 16 string banks re-write byte-identically; all 10 Bink movies
  decode (frames and sound). **Passed.**

## Phase 7: the easiest possible modding, help inside the app (user, 2026-10-09) ✅ mostly
The user's direction: make modding as easy as possible, put the documentation inside
the app, make packaging a mod and installing it in game easy. Handoff and full scope:
`phase7-kickoff.md`.
- Help inside DR2 Studio: the guides rendered and searchable, "how to mod this" for the
  selected asset, a first-start walkthrough, errors that link to their explanation;
  `dr2 help`. ✅ (`dr2kit/help`, `studio/help_view.py`, `studio/welcome.py`)
- Easiest editing loop: *Edit in image editor…* with automatic re-import, *Open in
  Blender*, drag and drop, the open mod's items with status and removal. ✅
- Packaging: a *Share…* window (metadata, preview, checks) writing one `.dr2mod`. ✅
- Installing and playing: open a mod package to install it, *Play* (deploy + start the
  recomp), what is deployed now, remove from the game, mod sets. ✅ (`mods/play.py`)
  Not done: registering `.dr2mod` with the operating system (double-click).
- An icon for the app (our own art). ✅ (see devlog)
- Texturing programs (user request): *Import textures…* for Substance Painter / Blender /
  any program's exports (`mods/texture_import.py`), guide `14-texturing-tools.md`, and
  the game's limits measured and written down (`15-limits.md`, `formats.md` §Engine
  limits, §Texture conventions). ✅ (not yet followed in Painter itself)
- Carried over: the first release on all OSes (needs the GitHub remote), the in-game
  gates still owed, value-set colours, longer sounds, keyboard prompts with string mods.
- **Gate:** a newcomer, with only the in-app help and no terminal, makes a texture mod
  and a text mod, sees them in game, packages them and installs the package on a second
  setup (both games). **The chain passed scripted, in game, in CZ and CW**
  (`tools/newcomer_gate.py`, `dev/testing.md` §Phase 7 results); the run by a person is
  still owed.

## Phase 8: find things by what they are, export them in one go (user, 2026-10-09) ✅
Done 2026-10-09 (`phase8-kickoff.md` §Status, guide `modding/16-library.md`).
- A **Library** tab (Studio opens on it; the archive tree becomes **Files**): Characters,
  Zombies, Weapons & items, Cutscene props, Environments; Music, Voices, Cutscene audio,
  Sound effects; Textures, Skeletons, Text & strings, Movies. Models with 3D-rendered
  thumbnails (user decision), duplicates shown once.
- A model shown with everything it uses: textures by role, the rig it matches (new
  model → skeleton link), parts and counts.
- **Export all…**: one model, a selection or a whole group, one folder per asset (user
  decision): `.glb`, `textures/*.png`, `skeleton.glb`, `info.txt`; sounds as WAV, movies
  as MP4, strings as JSON; progress, cancel, resume. `dr2 export <group|vpath…>`.
- Friendlier names where the data gives them (characters, sound banks, voice lines).
- **Gate:** from the Library alone, one character exported with everything (opens in
  Blender with textures and bones) and whole groups exported in one go, in both games.

## Phase 9: variants: choose what a model wears, see it, export it that way (user, 2026-10-10) ✅
Done 2026-10-10 except the in-game check (`phase9-kickoff.md` §Status, guide
`modding/17-variants.md`). Look-alike files (`chair_1…9`) stay separate items (decision:
they are different objects); colour-choice mods and Chuck's outfits are not started.
- Confirm in game how zombies pick their parts and colours (both games).
- The variant model: the executable's shape-group table as profile data, colour choices
  from `zombie_pdv_variations.txt` and the shader banks, prop states by name rules.
- Studio: a Variants panel (one choice per slot, colours, Random, Game default, Show
  everything); pictures and the 3D view show the game's default look; one Library item
  per zombie with a Detail choice.
- Export **as shown**, or **everything, organized** (slot collections in Blender, colour
  choices as `KHR_materials_variants`); `dr2 variants`, `--variant`.
- Re-import keeps the groups; a guide to adding a shirt. Stretch: colour-choice mods,
  Chuck's outfits assembled from `outfits.csv`.
- **Gate:** a chosen look shows and exports as chosen, the organized export switches in
  Blender, every shape is grouped (census), and captured zombies match (in game).

## Phase 10: Maps: see a whole level, extract it, see your mods in it (user, 2026-10-11)
Planned 2026-10-11 and approved by the user, nothing built (`phase10-kickoff.md`: research,
plan, gate). The user
called it much bigger than phase 9: built in steps, each usable on its own.
- Read levels: zone lists, piece placements (`ZONE_ORGANIZATION.big`), `dr2 level`,
  `census --levels`.
- Placed things from the level text files: items and doors (with their models), spawn
  points, zombie areas, map areas, triggers, the navigation mesh.
- Studio's **Maps** tab: fly through a level, zones loaded near the camera first, layers,
  click a piece or item; level materials (AO maps, two-texture blends).
- Extract a zone or a level as `.glb` (pieces placed, collections per zone and layer),
  `dr2 export <level>`.
- **See your mods without the game**, Studio-wide: a `ModdedTree` that draws the bytes
  Play would deploy (the switched-on mods); one click to see it without mods, and Compare.
- **Gate:** CZ `prologue` and CW `living_research` assembled and compared with recomp
  frames; every placement and level file parsed (census); a zone opens in Blender as in
  Studio; a texture and a model mod show in Studio exactly as deployed and as in game.
- Stretch: collision; time of day.

## Phase 11 (maybe): edit levels (user, 2026-10-11)
Not planned yet; the user "will add later" if wanted: modify zombie spawns, move placed
objects, add more objects, saved as mods (the level text files are not digest-checked).
Phase 10 shows spawns and placements as layers and reads the text files so they can be
written back.

## Stretch (phase 11 or later)
- In-game "identify": the recomp sends the textures/models under the crosshair to Studio.
- Animation export (and later import); level editing beyond phase 10's stretch.
- PC DR2/OTR read support.

## Decisions (user, 2026-10-08)
1. **Recomp integration: yes, in both recomps.** A `game_mods/` VFS layer (with phase 2)
   and PCM audio substitution (with phase 5). Design in `ARCHITECTURE.md` §Recomp integration.
2. **GUI: PySide6**, and it must work on **Windows, Linux and macOS**
   (`ARCHITECTURE.md` §Platforms).
3. **License:** a custom free non-commercial license (`LICENSE`). Anyone may use, change
   and share the toolkit. Nobody may sell it, and nobody may sell or paywall
   (Patreon, memberships, paid early access) mods for these games. Voluntary donations
   that gate nothing are allowed. Not a lawyer-reviewed text, and not OSI "open source".
4. **Git:** local repo now; the user creates the GitHub remote later.

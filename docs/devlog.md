# Devlog

What was done, when, and **why**: newest first. One entry per work session or
milestone. Each entry links the commits, docs and guides it touched. This is the
narrative; `formats.md` and `roadmap.md` hold the current state.

Entry template:

```
## YYYY-MM-DD — short title
**Done:** what changed, in plain words.
**Why:** the problem it solves or the decision behind it.
**Learned:** anything surprising about the games or tools (and where it is now documented).
**Docs updated:** list of files.
**Next:** what this unblocks.
```

---

## 2026-10-09 — Phase 7: help inside the app, Play, Share and Install
**Done:** the user's three choices first (Play starts the recomp; mods are shared as
`.dr2mod`; help in English, laid out for translations). Then:
- **Help inside DR2 Studio**: the modding guides *are* the help (`dr2kit/help`; a built
  package carries them through a `setup.py` hook), in a searchable window (F1), a "How
  to mod this" box per asset kind (`docs/modding/context.toml`), a Help button on every
  error that opens the matching troubleshooting row, a Welcome checklist, and
  `dr2 help` in the terminal.
- **The shortest editing loop**: *Edit in image editor…* (each save goes into the mod
  and shows in Studio as the game will get it), *Open in Blender* (the model arrives
  tagged for the add-on), drag and drop, the mod's changes listed with problems marked,
  only the buttons that apply shown, *New mod…* when an action needs one.
- **Share and install**: *Share…* (name, preview, readme, a check per game, one
  `.dr2mod`); *Install mod…* / drop / `dr2 studio file.dr2mod` shows the mod before
  installing; updates list what changed; mod sets.
- **Play** (`mods/play.py`, `dr2 play`): deploy the switched-on mods and start the
  recomp; *Play without mods*; *Remove mods from game*; the status bar says what is in
  the game. New mods live in the library; opened folders are linked.
- Guides 01, 05, 06, 08-11, 13 and the guides index rewritten for these buttons.
- **Gate, scripted in game in both games** (`tools/newcomer_gate.py`): make, share,
  install on an empty second library, Play: the new title text and a red shirt/jacket.

**Why:** the user's phase 7 direction: modding as easy as possible, documentation in
the app, packaging and installing easy.

**Learned:** `closeEvent` isn't called for a window never shown, and waiting on a job's
thread with `wait()` deadlocks (it quits through a queued signal): `wait_for_jobs()`
keeps the event loop turning. The Studio tests linked test mods into the real mod
library once the open mod joined the library: every test now gets its own user folders
(conftest). A one-liner `open(p,'w').write(open(p).read())` empties the file (the write
open truncates first): `app.py` had to be restored from git and re-patched. The CZ
recomp's `build-release` is a month older than `build`, so Play takes the newest
source build. `pkill -f` with a pattern that matches its own command kills the shell.

**Docs updated:** `modding/README.md` (start here), `01-install.md`,
`05-first-mod-texture.md`, `06-mod-packages.md`, `08`-`11`, `13-blender-addon.md`,
`context.toml` (new), `dev/studio.md`, `dev/code-tour.md`, `dev/testing.md`,
`ARCHITECTURE.md`, `roadmap.md`, `phase7-kickoff.md` (decisions), `glossary.md`,
`CLAUDE.md`.

**Next:** a person runs the gate from the in-app help on a clean profile; `.dr2mod`
file associations in releases; the carried-over items (first release on all OSes,
in-game gates owed, value-set colours, longer sounds, keyboard prompts with string mods).

## 2026-10-09 — Phase 7 set by the user; the app icon
**Done:** the user set phase 7's direction: the easiest possible modding, the help inside
DR2 Studio, easy packaging and installing of mods, and an app icon
(`phase7-kickoff.md`, `roadmap.md` rewritten; earlier proposals kept as "carried over").
Made the icon: `dr2kit/studio/icon/dr2studio.svg` (a combination wrench on a blood-red
tile with drips, our own drawing), set as Studio's window icon, rendered for releases by
`tools/release/make_icons.py` (PNG, `.ico`, `.icns`) and used by the executables, the
macOS app and the AppImage. The first wrench was a rough shape the user found weird; the
second is drawn from exact geometry (open jaw, hexagonal ring, tapered handle, shadow)
and checked at 16-256 px.

**Docs updated:** `phase7-kickoff.md`, `roadmap.md`, `dev/packaging.md` (§The icon),
`dev/studio.md`, `dev/code-tour.md`, `CLAUDE.md`.

**Next:** settle phase 7's open questions (starting the recomp from Studio, `.zip` or
`.dr2mod` packages, help language), then the in-app help.

## 2026-10-09 — Clean-up, phase 6 closed, phase 7 proposed
**Done:** deleted 17 finished sessions' scratch folders from `/tmp/claude-1000` (25 GB
→ 4.9 GB used; what is left belongs to running sessions), this phase's test captures,
test mods and the local Linux release build. Marked phase 6 done; wrote a proposed
phase 7 (`phase7-kickoff.md`, `roadmap.md`) from what phases 4-6 left open.

**Why:** the user found `/tmp` (RAM-backed) full and asked for clean-up, and for it to
become a habit: now a rule in `CLAUDE.md` (§Clean up after yourself).

**Docs updated:** `CLAUDE.md`, `roadmap.md`, `phase7-kickoff.md` (new),
`docs/README.md`, `README.md`.

**Next:** the user decides on phase 7; the first step needs the GitHub remote.

## 2026-10-09 — Phase 6, part 2: Blender add-on, release builds, game folders
**Done:** the Blender add-on `blender/io_dr2` (a Blender 4.2+ extension: search the
index, import a model or skeleton in one click into its own collection, **Check rig**
with the report in the Text editor, **Export to mod**), scripted end to end in Blender
5.2 (`tools/blender_addon_gate.py`). Release packaging: `tools/build_release.py`
(PyInstaller bundle with DR2Studio + dr2, add-on zip, toolkit sources for Blender,
licences; tar.zst, zip, AppImage, `.sha256`), `tools/release/build_ffmpeg_lgpl.sh`,
`.github/workflows/release.yml`. DR2 Studio's **Game folders…** window (choose a folder,
unpack the package), opened when no game is found. `dr2kit/userdirs.py` (works without
platformdirs), `dr2 doctor` reports PyAV's ffmpeg and its licence.

**Why:** phase 6 scope: the add-on and installers are what let people mod without a
terminal or a Python setup.

**Learned:** Blender treats add-ons as GPL, so the user chose a GPL add-on that imports
dr2kit from a folder instead of bundling it. PyPI's PyAV links GPL x264/x265 into
libavcodec: releases need an own LGPL ffmpeg (as the CZ recomp found), and PyAV builds
from source against it in under 2 minutes. The licence gate caught PyInstaller
collecting Fedora's GPL codec libraries through the system `libavcodec` (ffmpeg's
libraries have no RUNPATH); fixed with `LD_LIBRARY_PATH`. ffmpeg's configure calls the
Bink video decoder `bink` (the codec is `binkvideo`); buffer filters are always built.
An installed (non-checkout) toolkit doesn't see sibling recomps, hence the Game folders
window. Blender's manifest validator limits `tagline` and permission texts to 64
characters.

**Docs updated:** `modding/01-install.md` and `13-blender-addon.md` (new),
`dev/packaging.md` and `dev/blender-addon.md` (new), `02-game-data.md`,
`07-blender-setup.md`, `12-troubleshooting.md`, `modding/README.md`, `dev/code-tour.md`,
`dev/studio.md`, `dev/setup.md`, `dev/testing.md`, `ARCHITECTURE.md`, `roadmap.md`,
`THIRD_PARTY.md` (add-on GPL, what a release bundles), `glossary.md`, `README.md`,
`docs/README.md`, `CLAUDE.md`.

**Next:** push to a GitHub remote and let the release workflow run on Windows and macOS
(the Windows ffmpeg step is the least certain); try a release build on a real game on
each OS; the items in `phase6-kickoff.md` §Left open.

## 2026-10-09 — Phase 6, part 1: strings, text editing, movies, the mod manager
**Done:** string banks (`formats/bcs.py`: read, write byte-identically, JSON, apply
changes with notes) and `dr2 strings search/show/export/set/unset`; mods change strings
with `replace/…/str_<lang>.bcs.json` (only the listed ids; several mods merge per id).
DR2 Studio got a strings table (edit a cell → the mod), a text editor that saves a text
file into the mod with a coloured diff, a Bink movie player and *Export MP4…*
(`convert/video.py`, `dr2 extract --mp4`). The mod manager (`mods/library.py`, `dr2 mod
list/install/remove/enable/disable/move/conflicts/library/pack`, Studio's **Mod
manager…**) keeps installed mods in a library with a load order. The files the
executables digest-check were read from both XEXs (`tools/xex_digests.py`) into the
profiles; the build refuses them. In game: a changed `IDS_PRESS_START` shows on the
title screen of both recomps.

**Why:** phase 6 scope (roadmap): text and translations are the most asked-for mods after
textures, and several mods at once need an order and a conflict report, not an error.

**Learned:** every bank of a game has the same ids and the same size (zero-padded to the
largest, `str_lg`); `str_id.bcs` is the label bank (`IDS_…`); every string with colour
or icon markup starts with `@`; CZ's last string is the developers' joke-reminder
`IDS_LAST_LETTER_OF_LAST_STRING_IS_ALWAYS_MISSING`. The XEX `Digest` resource is
`count, {name hash, SHA-1(file + be32 length)}`: Case West checks six files, including
`padmap.txt` and `zombie_pdv_variations.txt`. Bink 5.1 is four tracks (FL/FR, C, LFE,
SL/SR). PyAV's wheels carry GPL x264/x265 next to an LGPLv3 ffmpeg (matters for
packaging). Frame dumps of a 3440×1440 window filled the RAM-backed `/tmp`: put them
on disk. The Blender add-on raised a license question; the user chose a GPL add-on that
doesn't bundle dr2kit.

**Docs updated:** `formats.md` (§Strings, §Digest-checked files, §Movies, table, the CW
digest sentence superseded), `modding/11-text.md` (new), `06-mod-packages.md` (mod
manager, string files, pack), `04-extracting.md` (movies), `asset-catalogue.md` (text,
movies), `12-troubleshooting.md`, `modding/README.md`, `glossary.md`,
`dev/code-tour.md`, `dev/studio.md`, `dev/testing.md` (phase 6 results),
`dev/recomp-integration.md` (§Phase 6), `ARCHITECTURE.md`, `roadmap.md`,
`THIRD_PARTY.md` (PyAV licences).

**Next:** the Blender add-on, packaging and CI, `01-install.md`.

## 2026-10-09 — White models: colour textures named `_dm` or `_cm<hex>`, packs on disk
**Done:** the user found Case West's final boss (`boss_commander_epi`) white in DR2
Studio. His colour maps are `_dm` ("diffuse map"); the role rule only knew `_cm`. A
check of every material of both games found two more gaps: environment colour maps with
a hex tag (`glass_cmda77`, 1,000+ slots) and loose models whose `.tex` pack is a
separate file in the same folder. `formats/scene.texture_role` now knows `_dm` and hex
tags, `Material.texture("colour")` falls back to the first plain-named texture (never a
lightmap or reflection map), and `TextureFinder` searches the model's folder on disk.
Left without a colour texture: 25 / 30 materials that really have none (lights, glass).

**Why:** a white model in a preview looks like a broken model.

**Learned:** count over every asset instead of fixing the one reported: the reported
case (`_dm`) was 6 slots; the hex-tag case it led to was over a thousand.

**Docs updated:** `formats.md` (§Materials, role rule), `dev/code-tour.md`,
`modding/12-troubleshooting.md`.

## 2026-10-09 — Zombie clothing colours: value sets and baked colours
**Done:** the user saw zombies with red/green/purple clothes in DR2 Studio (skin was
right). Their `_cm1` texture is a weight map; the colours are pixel-shader constants in
each material's value set (`valuesets.big/<hash>.scv`). Added `formats/shader.py`
(shader constant tables, value sets) and `convert/material.py` (bakes the pattern,
body-part and channel families with the shaders' own formulas, read from the shaders
translated with XenosRecomp); the `.glb` export (CLI, Studio) uses the baked texture.
All 674 / 819 value sets parse; all 297 / 212 affected materials bake; checked visually
on seven models.

**Why:** previews and Blender exports must show what the game shows; the phase 3 export
had used the `_cm1` weight map as the colour.

**Learned:**
- A texture suffix doesn't say it's a colour: `_cm1` on zombie clothing is a weight
  map. Even Chuck's DR2 t-shirt under the jacket (`chest_default_mtl_tshirt`) uses one.
- Value-set records hold the pixel-shader **register**; the shader's D3DX constant table
  names it. The 32-bit "name hash" next to it isn't any hash we know.
- XenosRecomp (sibling repo, built) turns a game `.po` into readable HLSL: the fastest
  way to learn what a material does.
- Cutscene zombies tile their pattern (scale 10 × 20) and some use scale 0 (one flat
  colour): the bake follows the shader's UV transform.

**Docs updated:** `formats.md` (§Materials: value sets, with the correction; status
rows), `dev/gltf-mapping.md`, `dev/code-tour.md`, `glossary.md`,
`modding/12-troubleshooting.md`.

**Next:** compare with an in-game capture; let mods change these colours (value-set
overrides).

## 2026-10-09 — Phase 5: audio (listen, export, replace through the recomps)
**Done:**
- Sound formats (`formats/xma.py`): `.xma` comes in two shapes, RIFF XMA2 files in the
  sound-effect banks and raw packets in the streamed banks; the raw ones are described by
  `data/audio/cache.big`'s `$GIB` stream tables (rate, channels, loop), cracked this
  session. Packet headers, multi-stream (5.1) layout, the FNV-1a packet fingerprint.
- Decoding (`convert/audio.py`) through PyAV (ffmpeg's `xma2`, the recomps' decoder):
  `dr2 extract --wav`, `dr2 info` on sounds, `dr2 census --audio` (every sound of both
  games decodes to its stored length: 8,916 + 11,735).
- `.sfx` and audio scene scripts (`formats/audioscript.py`); the index links sounds to
  the `.sfx` that play them and to scene-script events (`audio`, `sound_ref` tables;
  schema version 2).
- DR2 Studio's audio view (`studio/audio_view.py`): waveform per channel, play, seek,
  loop, *Export WAV…*, *Replace with audio…*.
- Sound mods: `replace/<sound>.xma.wav|ogg|flac|mp3` (`mods/audio.py`) build into
  `dr2kit_audio/` (fitted WAV per stream + a table of every packet's fingerprint and
  output position); **PCM substitution in both recomps** (`runtime/kernel/audio.cpp`,
  `CZ_NO_AUDIO_MODS` / `CW_NO_AUDIO_MODS`, CZ gotcha 635, CW gotcha 331; commits CZ
  `54b5283` on master, CW `dea8734` on xlive-integration).
- In-game gate in both games: the title music replaced by another track, recorded
  through SDL's disk driver, follows the replacement; the off switch plays the original.

**Why:** phase 5 of the roadmap: hear a sound before extracting it, and replace music,
voices and effects, although no XMA encoder can be shipped.

**Learned:**
- **Phase 0's "no RIFF header" was wrong for most sounds**: it held for the streamed
  banks it looked at. 7,647 / 9,190 sounds are complete RIFF files. Retraction in
  `formats.md`.
- The stream tables hash the entry name **with its case**, unlike the `.big` index.
- A decode is always 384 samples shorter than the frames encoded; loop points count
  those samples. With that, every length rule holds over both games (`formats.md`
  §Lengths); a few looping effects carry a tail past the loop end.
- Decoding packet by packet (as the recomps do) gives the same samples as a whole-file
  decode, so a packet's output position is fixed. That replaced the planned design
  (map guest buffers to `.big` entries through VFS read tracking) with one where every
  packet identifies itself: no VFS state, and loops, streaming and reused contexts need
  no special cases.
- **Case Zero digest-checks `data/audio/Prologue.txt`**: an edited copy crashes the game
  (checked in game). The planned "easy path" (script remap, as on PC) is ruled out; the
  guide shows the substitution way to make an event play another track.
- The 5.1 prologue cinematic decodes to 316.45 s, as the CZ recomp measured from its
  packet headers (316.5 s): two independent readings agree.
- Both recomps' playback drifts about 1% slow against the source in the disk recordings,
  modded or not (runtime pacing, not substitution). One CW run ignored SIGTERM at exit
  (substitution off): use `timeout -s KILL`.
- The first schema bump (index version 2) failed on a real index: dropping the old
  tables with foreign keys on gives "no such table: main.source_file". Fixed (keys off
  while dropping) with a test; found when building the index to launch Studio.
- Qt Multimedia aborts at exit if a widget using it outlives the test's QApplication
  ("shared QObject was deleted directly"): delete it first.

**Docs updated:** `formats.md` (§Audio rewritten: shapes, stream tables, lengths,
packet-by-packet decoding, `.sfx`, scene scripts and the digest, substitution, census,
in-game check; status rows), `dev/recomp-integration.md` (§Audio substitution, test
procedure, the remap result), `dev/code-tour.md`, `dev/studio.md`, `dev/testing.md`,
`dev/setup.md`, `ARCHITECTURE.md` (index, Studio, audio pipeline, recomp integration
design change), `roadmap.md`, `modding/10-audio.md` (new), `modding/03`, `04`, `06`, `12`,
`asset-catalogue.md`, `modding/README.md`, `glossary.md`, `THIRD_PARTY.md`,
`prior-art.md`, `phase6-kickoff.md` (new), `docs/README.md`, `README.md`, `CLAUDE.md`;
in the recomps: CZ `docs/gotchas.md` #635 and `docs/instruments.md`, CW
`docs/gotchas.md` #331.

**Next:** phase 6, polish and distribution (`phase6-kickoff.md`). Open from phase 5: a
5.1 cinematic and an fx sound replaced in game, longer replacements, voice-line names
(GASP tables), Case West's digest list.

## 2026-10-09 — Docs: phase 4 sweep
**Done:** pages written before phase 4 stopped calling model import future work:
`modding/04-extracting.md` and `07-blender-setup.md` link the new guides 08 and 09,
`docs/README.md` lists them in the reading path, and `prior-art.md` records which limits
of the old MaxScript and the community import workflow phase 4 now covers.
**Why:** the user asked for memory and documentation to be brought up to date after
phase 4.
**Docs updated:** the four files above, this devlog.
**Next:** phase 5 (`phase5-kickoff.md`).

## 2026-10-08 — Phase 4: model replacement (Blender → game), rig validator, in-game check
**Done:**
- The scene writer (`formats/scene_write.py`): serialisers for every chunk the reader
  interprets (`rewrite_problems`: every scene of both games rewrites identically),
  triangles → strips, and `SceneEditor.replace_mesh`, which writes new geometry for a
  shape by copying a template draw of the same material: own buffers rewritten, combined
  buffers appended to, packets cloned, `RenderStrip`, shape words, bounds,
  `_BOUNDINGBOX_`.
- Exact vertex encoders (`formats/vertex.py`: `encode_element`, `encode_value`).
- `.glb` → model (`convert/model_import.py`): parts by object name, bones by name,
  materials by exported name, skinned back to the rest pose with the file's own
  matrices, 4 influences quantised to 255, palettes split at 61 nodes; unchanged shapes
  kept byte for byte. The same code is the **rig validator**: `dr2 model check`,
  `dr2 model import`, Studio's *Replace with .glb…*, and `.glb` overrides in mods
  (`replace/<model vpath>.glb`).
- Census gates: `dr2 census` checks the rewrite; `--models` the vertex re-encode;
  `--reimport` the `.glb` round trip and a rebuild of every shape.
- In-game gate on Case Zero (`tools/blender_gate_model.py` + `tools/capture_gate.py
  --root`): shirt rebuilt through Blender, arms inflated, the watch replaced by spheres
  on every face and finger bone (split into two draws). The game drew all of it from the
  mod's bytes, with the same bone matrices as Chuck's own head and hands.

**Why:** phase 4 of the roadmap: put edited and new rigged models back into the games,
the part the old community tools never got right (fingers and face).

**Learned:**
- **The games store −1.0 as the lowest signed code** (−512 in 10 bits) on most packed
  fields, so phase 3's clamping decoder had two codes for one value and no exact
  inverse. Decoding without the clamp makes every element of both games re-encode to
  its bytes. Retraction recorded in `formats.md`.
- `RenderStrip` word 5 is the packet's byte offset in the command buffer and word 6 its
  length up to the draw command; 106 packets have no `0x04` end, so word 5, not the
  end marker, says where packets start.
- Every skinned shape of both games has exactly one draw; a split palette (several draws
  in one skinned shape) is new to the games, and the game takes it (in-game gate).
- The skin shader uses tangent w as the bitangent's sign, but the shipped w values don't
  follow the UV handedness, and half are 0. New tangents use a chosen convention, not yet
  checked on a normal map (`formats.md` §Tangent w).
- Blender re-orders vertices and bones and adds float noise (≤ 1 µm here): matching must
  go by names, and an "unchanged" shape can only be detected in our own files.
- Importing Chuck's chest `.glb` into the mechanic "worked" at first (same shape names);
  the validator now warns when a file comes from another model and no longer guesses
  materials by number.
- The user asked about the dark blobs on Chuck's face in the gate capture: they are the
  test mesh (spheres on face bones, using the shirt material), as intended. Gate pictures
  need that said next to them.

**Docs updated:** `formats.md` (§Writing scenes, §Tangent w, snorm retraction,
RenderStrip/shape rows, census, in-game check), `dev/gltf-mapping.md`, `dev/code-tour.md`,
`dev/testing.md`, `dev/studio.md`, `dev/recomp-integration.md`, `modding/08`, `09`, `06`,
`12`, `README`, `glossary.md`, `roadmap.md`, `ARCHITECTURE.md`, `phase4-kickoff.md`
(historical), `phase5-kickoff.md`, `CLAUDE.md`, `README.md`.

**Next:** phase 5, audio (`phase5-kickoff.md`). Open from phase 4: a CW in-game run, a
combined-buffer prop in game, tangents on normal maps, adding shapes/materials/bones,
the Blender add-on.

## 2026-10-08 — Phase 3: models and skeletons → Blender, 3D view, in-game check
**Done:**
- The scene reader (`formats/scene.py`, `formats/vertex.py`): skeleton, materials,
  meshes, draws, vertex declarations, triangle strips, bone palettes, both buffer
  families, vertex animation. Every scene of both games parses; every draw decodes
  (`dr2 census --models`, also run by a slow game-data test).
- `.glb` export (`convert/gltf.py`, `convert/model.py`): armature with the game records in
  `extras`, skinned meshes, materials with their PNG textures; `skeleton_from_glb` reads
  records back. `dr2 extract --glb [--skeleton] [--no-textures]`; `dr2 info` explains a
  model (materials, draws, bones per draw).
- DR2 Studio: a 3D view (three.js 0.186.1 vendored, in `QWebEngineView`, fed over a
  `dr2:` URL scheme), *Export .glb…*, scene details.
- Gates as tools: `tools/blender_skeleton_gate.py`, `tools/capture_gate.py`.

**Why:** phase 3 of the roadmap: get every model and rig into Blender correctly, the
base for putting edited models back (phase 4).

**Learned:**
- **Each model carries its own vertex declarations** (`persistent.big`,
  `<shape> D3DVertexDesc N`, the 360's `D3DVERTEXELEMENT9` as is) next to a recorded
  **command buffer** per shape that says which buffers, ranges and declaration each draw
  uses. The shader banks were not needed (phase 0 thought they were).
- **The bone palette, where the old community tools stopped, is a run of consecutive
  skeleton nodes** (first node, count in `RenderStrip`). Proven in game: in a captured
  frame, Chuck's draws sharing a bone get identical matrices under this mapping and
  never under a shifted one.
- Skinning read from the game's own shader (translated with XenosRecomp): 4 influences,
  weight k with index k, index = 3 × slot, at most 61 bones per draw.
- `Combined Vertices 12` is named by its **stride**, not a counter (retracted in
  formats.md). Indices are strips (the GPU state in the capture agrees: primitive 6).
- The games' axes, units and winding are glTF's own: nothing is converted.
- **Materials are named by id, not position.** The first export gave the mechanic boss
  the wrong textures (his apron wore the shoes'); the user spotted it in the Studio
  screenshot taken to check the 3D view, which had been looked at and judged fine.
  `RenderStrip` word 0 is the material id − 1, and `MatArray` isn't in id order. Chuck's
  parts happen to be, which is why they looked right. The census now checks every draw
  finds its material. Lesson: the numeric gates checked geometry, not material binding;
  look at more than one model.
- Blender keeps bone custom properties through import/export; its float noise grows with
  distance from the origin (1.4e-4 at 400 m), so the snap tolerance is relative.
- Studio's `run_job` delivered results in the worker thread (a phase 2 bug: a lambda
  slot runs where the signal is emitted); harmless for text, fatal for Chromium. Fixed
  with a GUI-thread relay.
- The recomp's widescreen patch is applied after the dumped constants: projection row 1
  × 9W/16H.

**Side effects on the user's machine (reported):** the first capture run's F9 also
triggered the CZ recomp's bug-report capture, which pruned the oldest capture in
`~/.config/XenonLive/captures/` (`20261007-052710-93d0`, over the 256 MB cap). The
capture that run added was removed again; later runs used `CZ_BUG_REPORTS=0` (now in
`dev/recomp-integration.md`). A frame-dump run filled the temporary folder's quota; its
files were deleted. The recomps' code and `game_mods/` were not touched; saves were
copies.

**Docs updated:** `formats.md` (§Scene container rewritten, retractions, status table),
`dev/gltf-mapping.md` (new), `dev/code-tour.md`, `dev/studio.md`, `dev/testing.md`,
`dev/recomp-integration.md`, `modding/04-extracting.md`, `modding/07-blender-setup.md`
(new), `modding/asset-catalogue.md`, `modding/12-troubleshooting.md`, `modding/README.md`,
`glossary.md`, `ARCHITECTURE.md`, `roadmap.md`, `README.md`, `docs/README.md`,
`THIRD_PARTY.md`, `CLAUDE.md`, `phase3-kickoff.md` (historical), `phase4-kickoff.md` (new).

**Next:** phase 4 from `phase4-kickoff.md`: a byte-identical scene writer, then
`.glb` → draws, then the in-game gates.
**Follow-up (same evening):** a sweep for docs still describing phase 3 as future work:
`prior-art.md` (bone palette solved; 360 has both buffer families), `ARCHITECTURE.md`
(Studio's model/skeleton views marked built), `dev/README.md` (index rows for
`studio.md`, `gltf-mapping.md`, `recomp-integration.md`), `dev/setup.md` (every gate
command), `modding/03-browsing.md` (the 3D view), `dev/adding-a-format.md` (lessons
from scenes).

---

## 2026-10-08 — Phase 2: textures, index, DR2 Studio, mods, in-game gate
**Done:**
- `.bct` textures decoded: `formats/bct.py` (header, layout, tiling),
  `convert/dxt.py` (DXT1/DXT5/DXN encode + decode, numpy and pure Python),
  `convert/png.py` (pure-Python PNG), `convert/texture.py` (texture ⇄ image, replace).
- Census of every texture in both games, with a re-encode gate (`dr2 census --textures`).
- The SQLite asset index (`index/`, `dr2 index …`): every asset, texture thumbnails,
  model→texture links.
- DR2 Studio v0 (`studio/`, `dr2 studio`).
- Mod packages (`mods/`, `dr2 mod new|check|build|deploy|undeploy`).
- `dr2 extract --png`, `dr2 info`.
- The `game_mods/` VFS layer in both recomps (CZ `057d45b`, CW `ebf0bb2`), each with an
  off switch, a log line per served file and a gotcha entry.

**Why:** phase 2 of the roadmap: see and replace textures, the first thing modders
want, and prove end to end that a toolkit-built archive loads in the game.

**Learned:**
- **The `.bct` header is not a fetch constant** (retracting the phase 0 plan). It is
  the engine's own description: format code (08 DXT1, 0A DXT5, 1B DXN, 00 A8R8G8B8,
  21 L8), mip count, bits per pixel, a flags byte (0x08 = cube map, verified), a
  version byte (0x23 CZ / 0x24 CW). The layout (4 KB-aligned levels, packed mip tail
  including small bases, six faces per level) was confirmed by where real data sits,
  by mip chains, and by a payload-size model that matches 99.6% of textures (the rest
  are larger, never smaller).
- Every one of 12,237 + 23,139 textures decodes and re-encodes to its exact bytes.
  Keeping reference blocks makes PNG round trips lossless where pixels are unchanged.
- **The game accepts our LZX encoder's output.** Chuck's shirt (CZ,
  `chest_young_chuck.tex/young_cr_shirt_cm`) and jacket (CW, `chest_default.tex/cr_jacket_cm`),
  both inside compressed `.tex` entries of `npcs.big`, turned green in game and are back
  to normal with `CZ_NO_MODS=1` / `CW_NO_MODS=1`. The user pointed out that CZ's default
  outfit is the orange "04" shirt, not the IJIEK jacket (DR2's); the first run had
  recoloured the jacket, which this save doesn't wear. `dr2 index textures-of` on
  `chest_young_chuck.big` then found the right texture at once.
- Headless recomp runs play the save (START,A,A = Continue): use a copy of the save
  folder (`CZ_SAVE_DIR`). The user's save was checked unchanged.
- SQLite without statistics planned the relation join as two nested 125k-row scans
  (10 minutes); a `CROSS JOIN` order plus `ANALYZE` made it 0.4 s.
- Normal maps aren't all DXN (583 DXT1 `_nm` in CZ). `MatTextureInfoArray` is 100-byte
  records, name at +4; its hash at +0x38 is not the engine hash.

**Decisions:** the runtime layer only swaps whole files and is checked first; the
toolkit builds mod files on top of `game_patched` and warns about the toggle layers
(`dev/recomp-integration.md`). Studio lives in `dr2kit/studio/` so `pip install` ships
it. No DDS round trip: reference blocks make PNG lossless enough. No game imagery in the
repository, screenshots included.

**Docs updated:** `formats.md` (§Textures rewritten, with the retraction), `ARCHITECTURE.md`,
`roadmap.md`, `glossary.md`, `dev/code-tour.md`, `dev/testing.md`, `dev/setup.md`,
`dev/adding-a-format.md`, `dev/studio.md` (new), `dev/recomp-integration.md` (new),
`modding/03`, `04`, `05`, `06`, `asset-catalogue.md` (new), `12-troubleshooting.md`,
`modding/README.md`, `README.md`, `docs/README.md`, `CLAUDE.md`, `THIRD_PARTY.md`,
`phase2-kickoff.md` (marked historical), `phase3-kickoff.md` (new); in the recomps:
`docs/gotchas.md` (CZ 634, CW 330), CZ `docs/instruments.md`.

**Next:** phase 3 from `phase3-kickoff.md`: skeletons → `.glb`, then vertex streams
and bone palettes.
**Follow-up (same evening):** a `cz_runtime` the user had left running for ~5 h (started
before this session, so on the pre-`game_mods` binary) was stopped at the user's request
with a normal SIGTERM. Their save was checked unchanged. Both recomps' `game_mods/`
folders were removed after the gate, so the next launch of either recomp runs the new
binary with an empty mods layer: identical to before unless a mod is deployed.

## 2026-10-08 — Phase 1: container, LZX, census, `dr2` CLI
**Done:**
- `dr2kit` package (`pyproject.toml`, `dr2` entry point, `python -m dr2kit`), CI on
  Windows / Linux x64+arm64 / macOS with Python 3.11 and 3.13.
- `.big` reader/writer (`container/big.py`), virtual paths (`container/vpath.py`, with
  `name#N` and `@N`), compressed-entry framing (`container/xcompress.py`).
- LZX: libmspack's `lzxd.c` in a separate `dr2lzx` library loaded by ctypes, a pure-Python
  decoder written from the format description, and the CZ recomp's encoder ported.
- Game profiles (`cz.toml`, `cw.toml`), discovery (env var, user config, sibling recomp),
  STFS package unpacking (`dr2 unpack`).
- `dr2 doctor | games | ls | find | extract | census | unpack`.
- 78 unit tests (synthetic data) + 6 game-data tests; `THIRD_PARTY.md`.

**Why:** everything later (textures, models, audio, mods) reads and writes through the
container. The gate demanded byte-identical round trips over both games before anything
is built on it.

**Learned** (all now in `formats.md`):
- The census counts **7,413 archives in CZ and 8,017 in CW** once nested and
  *compressed* nested archives are opened (the recomp counted the 146 top-level files).
  All round-trip byte-identically; all 10,754 + 21,354 compressed entries decode; two
  independent decoders agree; our encoder re-encodes every one (streams 7% larger than
  the game's).
- Every gap between payloads is zero padding to some power of two. Each entry's
  alignment can therefore be recovered from its offset, so the writer stores no offsets
  at all and still reproduces every archive.
- The index hash is the engine hash of the **lower-cased** name, for every entry.
- New `flags` values: `0x10` (textures in `.tex`), `0x20` (scene chunks), `0x100`
  (nested `.big`), besides `0x4`, `0x80`, `0x800`.
- An empty compressed entry is `00 00 00 00`. CW's `preload4.big` has 27 of them. The
  first CW census flagged them as unparseable, which is how they were found.
- The game's encoder writes **uncompressed LZX blocks** (type 3) for small or
  hard-to-compress chunks, in archives it reads at boot. The recomp had believed the
  game's decoder lacked type 3. Our encoder now uses type 3 too, but only when a chunk
  would otherwise grow.
- **Retracted:** "`.bct` magic `05 01 01 E2`". The 4th byte varies (13 values over
  35,350 textures, all with bit `0x02` set).
- **Retracted:** the duplicate-name example "several `Combined Vertices`". Those are
  numbered. Real duplicates are rare (`zonelist.big` ×7/×19).
- 9 of 11 CZ `.bcf` fonts (6 of 11 in CW) are `.big` archives; the rest use an unknown
  `04 03 02 01` container.
- PyAV 19.0.1 on Linux has `xma1`, `xma2` and the Bink decoders; CI checks the other OSes.
- Unpacking each XBLA package gives files byte-identical to the recomp's data.

**Decisions:** `dr2 extract` decompresses by default (`--raw` keeps the stored stream);
the CLI lives in `dr2kit/cli/` (`ARCHITECTURE.md`).
**Docs updated:** `formats.md`, `ARCHITECTURE.md`, `roadmap.md`, `glossary.md`,
`dev/setup.md`, `dev/code-tour.md`, `dev/testing.md`, `dev/adding-a-format.md`,
`dev/README.md`, `modding/02-game-data.md`, `modding/12-troubleshooting.md`,
`modding/README.md`, `README.md`, `docs/README.md`, `CLAUDE.md`, `THIRD_PARTY.md`,
`native/lzx/README.md`, `phase2-kickoff.md` (new).
**Docs follow-up:** `CLAUDE.md` (CW title ID, package paths, dev environment notes), `phase1-kickoff.md` marked historical.
**Next:** phase 2 from `phase2-kickoff.md`: `.bct` decode, texture census, the index,
Studio v0, texture replacement, the recomps' `game_mods/` layer. The in-game gate there
is also the first proof that the game accepts our LZX streams.

## 2026-10-08 — Phase 1 handoff
**Done:** wrote `phase1-kickoff.md` (order of work, exact files and lines to port, test-data
policy). Checked the licenses of the code we will reuse.
**Learned:** the LZX decoder behind XenonRecomp's `lzxDecompress` is libmspack's `lzxd.c`
(**LGPL-2.1**). It's fine as a separate shared library loaded through ctypes, but a
line-by-line Python translation would also be LGPL. The recomp tools are the user's own
(PolyForm Noncommercial), so they can be re-licensed here.
**Docs updated:** `phase1-kickoff.md`, `CLAUDE.md`, `docs/README.md`, this devlog.
**Next:** phase 1, in a fresh conversation.

## 2026-10-08 — Documentation rules
**Done:** set up the documentation layout: `docs/README.md` (index), `glossary.md`, this
devlog, `modding/` (modder guides), `dev/` (contributor guides), `CONTRIBUTING.md`, and a
"Documentation rules" section in `CLAUDE.md`.
**Why:** the project must be easy to understand both for people who want to mod and
for people who want to work on the code. Documentation is part of "done" for every change.
**Docs updated:** all of the above.
**Next:** phase 1 (archive container + census).

## 2026-10-08 — Decisions: license, platforms, recomp integration
**Done:** added a free non-commercial `LICENSE` (no selling the toolkit, no selling or
paywalling mods). Committed to Windows/Linux/macOS support for PySide6 Studio. Approved a
`game_mods/` VFS layer and PCM audio substitution for both recomps (not implemented yet).
**Why:** user decisions (see `roadmap.md` §Decisions).
**Docs updated:** `LICENSE`, `README.md`, `CLAUDE.md`, `ARCHITECTURE.md` (§Platforms,
§Recomp integration), `roadmap.md`.

## 2026-10-08 — Phase 0: planning
**Done:** surveyed both games' data and the Case Zero recomp's existing tools, and wrote
`CLAUDE.md`, `ARCHITECTURE.md`, `formats.md`, `prior-art.md` and `roadmap.md`.
**Learned:**
- The 52-byte bone record layout, verified on all 3,474 bones in both games.
- Skeleton files share the model layout.
- Models list their textures by name in `MatTextureInfoArray`.
- Audio is raw XMA without a header.
- Case West adds Bink movies.
- The old community tools (Gibbed, mariokart64n's MaxScript, Chrrox) are PC- and 3ds
  Max-only, and stalled on bone palettes and on finger and face weights.

**Docs updated:** all initial docs (commit `0fa498f`).

# Phase 6 kickoff: polish and distribution

A handoff for the session that starts phase 6. Read `CLAUDE.md` first (especially the
documentation rules), then this. Scope: `roadmap.md` §Phase 6. What phase 5 built:
`dev/code-tour.md` (formats/xma, formats/audioscript, convert/audio, mods/audio,
studio/audio_view); what it learned: `devlog.md` (2026-10-09, "Phase 5") and
`formats.md` §Audio.

## What you start with

- Every asset kind the roadmap promised can be read, previewed and replaced: textures
  (PNG), models and skeletons (`.glb` both ways, rig validator), sounds (WAV/OGG/FLAC/MP3
  through the recomps' PCM substitution). Mods are folders with `mod.toml` + `replace/`,
  built by `dr2 mod build/deploy` and Studio's mod bar.
- Both recomps carry the two approved integration changes: the `game_mods/` file layer
  (phase 2) and audio substitution (phase 5, `runtime/kernel/audio.cpp`, CZ gotcha 635,
  CW gotcha 331). Nothing else may change in the recomps without the user's approval.
- Optional dependencies: numpy (speed), Pillow (PNG), PySide6 (Studio), **PyAV** (all
  audio; bundles ffmpeg's `xma2` decoder). `pyproject.toml` extras: `fast`, `audio`,
  `studio`, `dev`.

## Phase 6 scope (roadmap)

1. **Blender add-on `io_dr2`**: browse the index from Blender, import a model or
   skeleton in one click, run the rig validator in a panel, export straight into a mod
   folder. The core already imports inside Blender's Python (pure Python + numpy); the
   add-on is UI over `convert/gltf.py`, `convert/model_import.py` and `mods/`.
2. **Mod manager**: several mods at once with priorities and conflicts (the build
   already merges and reports conflicts), enable/disable, deploy to `game_mods/`.
3. **Strings** (`.bcs` ⇄ JSON; the CZ recomp's `gen_pc_options.py` has a patcher), and
   mission/data text editing with a diff view; CW Bink preview (PyAV decodes Bink).
4. **Packaging**: AppImage / Windows zip / macOS build, matching the recomps' release
   style; CI on all three (the workflow exists; it runs once the GitHub remote exists).
5. Guide `01-install.md`, `11-text.md`; finish `asset-catalogue.md`.

## Left open by phase 5 (decide whether they belong in phase 6)

- **Not proven in game:** a 5.1 cinematic replaced (three streams; built and checked
  against PyAV per stream, not heard), a sound effect from an `fx_*.big` bank.
- **Longer replacements**: the game sets a sound's length; v1 cuts or pads. Making a
  sound longer would need a longer `.xma` (the stream tables and RIFF headers say the
  size) whose packets still decode, i.e. an encoder or valid filler packets.
- **Voice-line names**: `charvocals.big` etc. are numbered; `audio/gasp.big` (GASP
  dialogue tables: `*_smp`, `*_sg`, `*_snt`, `*_kwd`, `stmts`) links numbers to
  situations, maybe to string ids. Worth a look for the asset catalogue.
- **Case West digest coverage**: which files its `Digest` resource lists (CZ: only
  `Prologue.txt`). Reading the XEX resource would answer it without a run.
- Studio: play a replacement next to the original before building.
- From phase 4: a CW in-game run of a replaced model, a combined-buffer prop in game,
  tangents on normal maps, adding shapes/materials/bones.

## Facts to keep in mind

- Headless recomp runs: check `pgrep -x cz_runtime` first; `CZ_BUG_REPORTS=0`; a **copy**
  of the save (`CZ_SAVE_DIR`); no frame dumps; `timeout -s KILL` (a CW run ignored
  SIGTERM at exit); `dr2 mod undeploy` and remove the empty `game_mods/` afterwards.
  For audio, SDL's `disk` driver records the output silently
  (`SDL_AUDIODRIVER=disk SDL_DISKAUDIOFILE=…`). Procedures:
  `dev/recomp-integration.md`.
- Don't `pkill -f <pattern>` with a pattern that also matches your own shell command.
- An index built by an older toolkit is dropped and must be rebuilt (schema version 2
  since phase 5).
- Look at (listen to) several real assets, not only the reference one; say up front what
  deliberate test artefacts look or sound like.

## Test data policy (unchanged)

Unit tests build synthetic data in code. Census and decode tests read the real games and
skip with a message when a game (or PyAV) is absent. No game audio, textures, meshes or
exports in the repository.

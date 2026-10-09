# Phase 7 kickoff: first release, and proving what isn't proven yet

**Status: proposed (2026-10-09), not yet approved by the user.** The original plan
(`roadmap.md`) ended at phase 6; this phase gathers what phases 4-6 left open. Read
`CLAUDE.md` first (documentation rules, and the clean-up rule: delete your temp files,
captures and test mods when done), then this. What phase 6 built: `dev/code-tour.md`
(formats/bcs, convert/strings, convert/video, mods/library, studio/text_view,
video_view, mod_manager, setup_dialog, userdirs), `dev/blender-addon.md`,
`dev/packaging.md`; what it learned: `devlog.md` (2026-10-09, "Phase 6, part 1/2").

## What you start with

- Every asset kind the roadmap promised can be read, previewed and changed by a mod:
  textures, models and skeletons (Blender both ways, rig validator, GPL Blender add-on),
  sounds (PCM substitution in the recomps), strings and text files. Case West's movies
  can be played and exported (not replaced: no Bink encoder).
- Mods are folders (`mod.toml` + `replace/`), combined by the mod manager (load order =
  priority), deployed to the recomps' `game_mods/`.
- Release packaging works on Linux (`tools/build_release.py`, own LGPL ffmpeg, licence
  gate). The GitHub release workflow (`.github/workflows/release.yml`) is written for
  Linux, Windows and macOS but **has never run**: there is no GitHub remote yet (the user
  creates it).

## Proposed scope

1. **First release (v0.1.0).** Once the remote exists: run `ci.yml` and `release.yml`,
   fix what breaks (the Windows ffmpeg build with MSVC from MSYS2 is the least certain
   step; macOS app layout and ad-hoc signing next), then try each OS's build on a real
   game (Game folders → index → a texture mod deployed) before publishing the draft.
   Release notes in the recomps' style.
2. **Prove in game what was only built** (each one a gate, both games where possible):
   - Case West: a model replaced from a `.glb` (phase 4 ran on CZ only), a
     combined-buffer prop, a model exported by the Blender add-on;
   - a 5.1 cinematic sound and an `fx_*.big` sound effect replaced (phase 5);
   - a text-file mod (e.g. `datafile.big/zombie_effects.txt`) changing behaviour.
3. **Mod features modders will ask for next:**
   - colour overrides for value-set materials (zombie clothing: today a mod can't
     recolour it, `formats.md` §Materials: value sets);
   - longer sound replacements than the original (needs a longer `.xma` whose packets
     decode, or filler packets);
   - string mods on top of the recomp's keyboard layer (`game_kbm`), so keyboard
     prompts survive a deployed string mod (needs a design: the layer is a toggle);
   - Studio: play a replacement next to the original before building; show a replaced
     model in the 3D view before building.
4. **Names and catalogue:** voice lines (`charvocals.big` etc.) linked to situations or
   subtitles through the GASP tables in `audio/gasp.big`; finish `asset-catalogue.md`.

## Later (the roadmap's "Stretch", phase 8 or beyond)

In-game "identify" (the recomp tells Studio what's under the crosshair), animation
export then import, environment/zone browsing and editing, PC DR2/OTR read support.

## Facts to keep in mind

- Headless recomp runs: `pgrep -x cz_runtime` first, `CZ_BUG_REPORTS=0`, a copy of the
  save, `timeout -s KILL`; frame dumps go to `~/.cache/…`, never `/tmp` (RAM-backed);
  `dr2 mod undeploy` and remove the empty `game_mods/` afterwards. Procedures:
  `dev/recomp-integration.md`.
- An installed (non-checkout) toolkit doesn't find the sibling recomps: set the game
  folders (`dr2 games set`, or `DR2_CZ_DATA` / `DR2_CW_DATA` for scripted runs).
- Index schema is 3 (string banks); an older index is rebuilt.
- Licences: the Blender add-on is GPL and must never include dr2kit; releases must
  never bundle a GPL library (the PyPI PyAV wheel links x264/x265).
- Files the games digest-check can't be modded (profiles' `digest_checked`).

## Test data policy (unchanged)

Unit tests build synthetic data in code. Game-data tests skip with a message when a game
is absent. No game data, exports or captures in the repository.

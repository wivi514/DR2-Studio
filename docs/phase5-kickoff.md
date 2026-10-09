# Phase 5 kickoff: audio

A handoff for the session that starts phase 5. Read `CLAUDE.md` first (especially the
documentation rules), then this. Scope and gate: `roadmap.md` §Phase 5. What phase 4
built: `dev/code-tour.md` (scene_write, model_import); what it learned: `devlog.md`
(2026-10-08, "Phase 4") and `formats.md` §Writing scenes.

## What you start with

- `.xma` entries: 8,916 in CZ, 11,735 in CW, raw XMA packets with **no RIFF/XMA2
  header** (`formats.md` §Audio). Channels and sample rate must come from elsewhere: the
  audio scene scripts (`audio/*.txt`, `datafile.big`), a bank table (`cache.big`?), or the
  recomp's log of the XMA contexts it decodes.
- The CZ recomp's `runtime/audio/xma_decoder.cpp`: how it feeds XMA to ffmpeg's `xma2`
  decoder (34-byte XMA2 extradata, block size 0x10000). PyAV is in the dev venv and
  `tools/check_pyav_codecs.py` checks it has `xma1`/`xma2`.
- Mods already replace whole assets (`replace/<vpath>`), re-compressing where the
  original was compressed, and deploy into `game_mods/` (both recomps).
- Studio has a viewer slot per asset kind (`studio/viewers.py`); audio playback goes there.

## Order of work

1. **Metadata.** Find where each `.xma`'s channels / rate / loop live. Census over every
   `.xma` of both games: a decode must give a sane duration; compare with what the
   scripts or the runtime log say. Name every entry the rule doesn't cover (rule 6).
2. **Decode → WAV** (`convert/audio.py`, PyAV, optional dependency like Pillow):
   `dr2 extract --wav`, the census gate (every `.xma` decodes to the expected duration).
3. **Studio playback** (Qt Multimedia, or PCM through `QAudioSink`), with event names from
   the scene scripts in the index.
4. **Replacement, easy path:** script-level remap (point an event at another asset;
   the community's music swap did this). A guide.
5. **Replacement, real:** PCM substitution in both recomps (approved,
   `ARCHITECTURE.md` §Recomp integration item 2): a `game_mods/…/<name>.wav` fed instead
   of decoding the XMA. Follow each recomp's CLAUDE.md, an off switch (`CZ_`/`CW_`), a
   gotcha entry; keep CZ and CW in step. Mapping a guest XMA buffer back to its asset is
   the hard part.
6. Guide `modding/10-audio.md`, troubleshooting rows, glossary.

## Facts to keep in mind (from phases 1-4)

- Audio banks are 0x800-aligned; the `.big` writer keeps that alignment on rewrite.
- Headless recomp runs: `CZ_BUG_REPORTS=0`, a **copy** of the save (`CZ_SAVE_DIR`), no
  frame dumps (they fill the temporary folder's quota), `dr2 mod undeploy` afterwards and
  remove the empty `game_mods/`, check `pgrep -x cz_runtime` first.
  `dev/recomp-integration.md` has the capture procedures of phases 2-4.
- Look at (listen to) several real assets, not only the reference one: numeric gates
  only check what they were written to check (phase 3's material bug).

## Left open by phase 4 (not blocking audio)

- A Case West in-game run of a replaced model; a combined-buffer prop replaced in game.
- New tangents' look on normal maps (`formats.md` §Tangent w).
- Adding shapes, materials or bones (v1 is replacement only); the Blender add-on.

## Test data policy (unchanged)

Unit tests build synthetic data in code. Census and decode tests read the real games and
skip with a message when a game is absent. No game audio, textures, meshes or exports in
the repository.

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

## Phase 3: skeletons and models → Blender
- Skeleton → `.glb` armature (rest pose, names, extras). **Gate:** importing into
  Blender, exporting, and converting back reproduces each bone record bit for bit.
- Model reader: vertex declarations (from `-vd.big` / the shader banks), streams,
  indices, materials, **bone palettes**. Census: every model in both games parses.
- Model → `.glb` with skin and textures. 3D preview in Studio (three.js on the same `.glb`).
- **Gate:** for a set of reference models, the exported mesh drawn in Blender lines up
  with an in-game capture (the recomp can dump draws: `CZ_CAPTURE_DUMP_VS`,
  `vsdump_skin.py`).

## Phase 4: model replacement (Blender → game)
- `.glb` → scene chunks: bone mapping by name, palette rebuild and splitting, vertex
  re-encode, bounds, keep material slots.
- Rig validator (CLI + Studio + later the add-on): missing bones, unweighted vertices,
  too many influences, names the game expects.
- **Gate:** (a) a no-op round trip of the original model loads in game unchanged;
  (b) an edited mesh (moved vertices) loads; (c) a new mesh rigged to the exported
  skeleton loads and animates, fingers and face included (the old MaxScript's failure case).

## Phase 5: audio
- XMA metadata (channels/rate), → WAV, playback in Studio, event names from scene scripts.
- Replacement: script-level remap (easy path); recomp PCM substitution in both recomps
  (approved); optional user-supplied XMA encoder.
- **Gate:** every `.xma` in both games decodes to the duration the scripts or runtime
  log report; one music swap is audible in the recomp.

## Phase 6: polish and distribution
- Blender add-on `io_dr2` (index browser in Blender, validator panel, export to mod).
- Mod manager: priorities, conflicts, enable/disable, deploy to `game_mods/`.
- Strings (`.bcs` ⇄ JSON), mission/data text editing with diff, CW Bink preview.
- Packaging: AppImage / Windows zip (match the recomps' release style).

## Stretch
- In-game "identify": the recomp sends the textures/models under the crosshair to Studio.
- Animation export (and later import); environment/zone browsing and editing.
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

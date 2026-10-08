# Roadmap

Each phase ends with a **gate**: a measurable check, not "it looks right".

## Phase 0: preparation ✅ (2026-10-08)
CLAUDE.md, architecture, format inventory, prior-art survey, this roadmap. Skeleton
record layout verified across all 76 skeleton files in both games.

## Phase 1: core container and census
- `dr2kit.container.big`: read/write ported from `gen_pc_options.read_big/write_big` +
  `big_list.py`, with nested virtual paths, duplicate names and zlib support in the reader.
- LZX: native decoder (ctypes) + pure-Python fallback; port `lzx_encode_stream` +
  `verify_fake_lzx`.
- Game profiles `cz.toml` / `cw.toml` with auto-discovery of the sibling recomps, plus
  STFS package extraction (port `extract_stfs.py`) for users without a recomp (macOS).
- Cross-platform skeleton: `pyproject.toml`, CI matrix on Windows/Linux/macOS, native LZX
  builds for all three, and a check of PyAV's `xma2`/Bink decoders on each OS.
- `dr2 ls`, `dr2 extract [--decompress]`, `dr2 census`.
- **Gate:** every archive in CZ *and* CW round-trips byte-identically; every compressed
  entry decodes to its `size2`; the census names every extension and every
  unparsed entry (target zero).

## Phase 2: textures + index + first GUI
- `.bct` header decode (fetch constant → format/mips/cube), untile, DXT1/3/5, DXN,
  A8R8G8B8, … → PNG. Census of formats in both games.
- SQLite index with thumbnails; model→texture relations from `MatTextureInfoArray`.
- DR2 Studio v0: tree, search, texture viewer, extract.
- Texture **replacement** (same size and format): PNG → DXT → tile → `.bct` → `.tex` →
  LZX → archive. First mod-package build.
- Recomp `game_mods/` VFS layer, in both CZ and CW.
- **Gate:** decode then re-encode reproduces the original block data for lossless
  formats; a recoloured texture shows up in **both** recomps through `game_mods/`, and
  disappears with `CZ_NO_MODS=1` / `CW_NO_MODS=1`.

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

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

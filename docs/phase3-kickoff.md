# Phase 3 kickoff: skeletons and models → Blender

A handoff for the session that starts phase 3. Read `CLAUDE.md` first (especially the
documentation rules), then this. Scope and gate: `roadmap.md` §Phase 3. What phase 2
built: `dev/code-tour.md`; what it learned: `devlog.md` (2026-10-08, "Phase 2").

## What phases 1-2 give you

- Any asset by vpath (`AssetTree`), archives read/written byte-identically, LZX both ways,
  and the in-game proof that the game accepts re-encoded model packs (`npcs.big`).
- Textures fully decoded (`formats/bct.py`, `convert/texture.py`): a model's materials
  can be exported with real PNGs. `index/` already links every model to the textures its
  `MatTextureInfoArray` names (`query.textures_of`), so the exporter doesn't have to
  search.
- The index classifies scenes: `kind = 'model'` (has `… Vertices 0` entries) or
  `'skeleton'` (a `SceneHeader` but no geometry): 1,397 models in CZ, 1,495 in CW.
- DR2 Studio has a centre `QStackedWidget` waiting for a model viewer.

## Order of work

1. **Skeleton reader** (`dr2kit/formats/scene.py` or `skeleton.py`): `_BONEHIERARCHY_`,
   `_BONENAMES_`, the 52-byte node records (layout ✅ in `formats.md`, verified on 3,474
   records), `SceneHeader`, `SceneDescription`. Write the census first: every skeleton
   *and* every model's bone records in both games, unit quaternions, parents in range.
2. **Skeleton → `.glb`** (`dr2kit/convert/gltf.py`), pure Python (a glb is JSON + one
   binary buffer; no dependency needed). Names, rest pose, original indices and flags in
   `extras`. Gate: Blender import → export → convert back gives every bone record bit for
   bit. Blender 5.2 is at `/usr/bin/blender` and runs headless
   (`blender -b --python-expr …`), so this gate can be automated.
3. **Vertex streams.** The open problem. Per mesh: `geo_<name>Shape Vertices N` /
   `Indices N` entries (the old "Combined Vertices" naming appears in other files: check
   both with a census). Layout comes from the vertex declaration, held in the shader banks
   `data/shaders/*-vd.big` (`.vdo`, 98.6% located per `formats.md`). Facts already
   measured by the CZ recomp, from one crowd-zombie shader (`tools/vsdump_skin.py`):
   weights `TEXCOORD2` as 8_8_8_8 UNORM (`.yzw`), bone indices `TEXCOORD3` as 8_8_8_8
   (`.ywz`), **pre-multiplied by 3** (rows of a 3×4 matrix palette starting at `c8`),
   and a stream dword's x is the *last* byte in memory. Treat that as one family's fact
   (rule 7) until a census of every declaration agrees.
4. **Indices**: 16-bit BE probably; strips or lists? Restart markers (gotcha 633 in the
   CZ recomp: check restart values, out-of-range indices, endianness explicitly).
5. **Bone palettes**: per-mesh local→skeleton bone maps; where they live is open (the
   old community tools stalled here). The `×3` above means the shader indexes a constant
   palette; find what fills `c8…` per draw (a capture with `CZ_CAPTURE_DUMP_VS` gives the
   constants *and* the stream bytes of every draw of one shader).
6. **Model → `.glb`** with skin and textures (`index.query.textures_of` for the PNGs;
   `UsedShaders.txt` for the shader name), then a model census: every model in both games
   parses or is named.
7. **Studio 3D view**: `QWebEngineView` + three.js on the same `.glb` (ARCHITECTURE.md
   §Stack), or the `QOpenGLWidget` fallback.
8. **The gate**: reference models drawn in Blender line up with an in-game capture. The
   recomp's `CZ_CAPTURE_DUMP_VS=<hash>` + F9 (headless: `CZ_FAKE_PRESS_SEQ` takes `F9`)
   dumps each draw's stream bytes and constants; compare positions after skinning.
9. Guides: `modding/07-blender-setup.md`, `04-extracting.md` (models part), the
   asset catalogue's skeleton rigs; `dev/` page for the glTF mapping.

## Facts to keep in mind

- Scene chunks are big-endian; names contain dots (`dummy01.l_thigh`), so `.ext` logic
  only counts 1-3 letter extensions (`BigEntry.ext`).
- `MatTextureInfoArray` is 100-byte records, texture name at +4 (52 bytes NUL-padded);
  the word at +0x38 is a hash but **not** the engine's name hash or CRC-32 of the name.
  Engine samplers (`gExposureTexture`, …) sit among the model's own slots.
- Chuck is assembled from parts (`chest_*`, `leg_*`, `feet_*_over/_under`, `hands_*`,
  `head_*`, `headwear_*` in `npcs.big`); Case Zero's default set is `*_young_chuck`.
  Good first reference models: one part (`chest_young_chuck.big`) and one whole NPC
  (`boss_mechanic.big`).
- Headless recomp runs **play the game** (`START,A,A` continues the latest save): always
  point `CZ_SAVE_DIR`/`CW_SAVE_DIR` at a copy (`dev/recomp-integration.md`), and
  `dr2 mod undeploy` afterwards.
- A `cz_runtime` started by the user may be running; leave other processes alone.

## Test data policy (unchanged)

Unit tests build tiny synthetic scenes in code. Census and decode tests read the real
games through the profiles and skip with a message when a game is absent. No game
meshes, textures, screenshots or `.glb` exports in the repository.

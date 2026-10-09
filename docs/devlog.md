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

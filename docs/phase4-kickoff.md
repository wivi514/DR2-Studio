# Phase 4 kickoff: model replacement (Blender → game)

> **Historical.** Phase 4 was completed on 2026-10-08 (devlog, "Phase 4"); the next
> handoff is [`phase5-kickoff.md`](phase5-kickoff.md). Kept as the record of the plan.
> Corrected since: packets are cut at `RenderStrip` word 5 (not every packet ends with
> `0x04`); signed-normalised values decode without clamping (the lowest code is how the
> games store −1); tangent w is used by the shader as a sign but doesn't follow the UV
> handedness in the shipped data; every skinned shape has one draw, so splitting a
> palette writes several draws in one shape (checked in game).

A handoff for the session that starts phase 4. Read `CLAUDE.md` first (especially the
documentation rules), then this. Scope and gate: `roadmap.md` §Phase 4. What phase 3
built: `dev/code-tour.md`, `dev/gltf-mapping.md`; what it learned: `devlog.md`
(2026-10-08, "Phase 3") and `formats.md` §Scene container.

## What phase 3 gives you

- `Scene` (`formats/scene.py`): every chunk of a model with the raw words kept: node
  records, materials, meshes, each draw's `RenderStrip` words, declaration, buffers,
  command-buffer packet. Every scene of both games parses; every draw decodes.
- `vertex.py` documents each packing the games use (FLOAT3/2, HEND3N normals, DEC4N
  tangents, SHORT2N UVs, UBYTE4N/UBYTE4 skin); encoders are the inverse of `_decode_one`.
- `.glb` export with game data in `extras` (records, material, palette, shader,
  declaration per primitive) and `skeleton_from_glb` (bit-exact records back).
- Two gates as tools: `tools/blender_skeleton_gate.py` and `tools/capture_gate.py`
  (draw dumps from the CZ recomp; procedure in `dev/recomp-integration.md` §Phase 3).

## Order of work

1. **Scene writer, no-op first.** `Scene → archive` that reproduces every model of both
   games byte for byte (keep raw chunks; regenerate only what changed). Census gate:
   every scene round-trips. Then the vertex encoders (decode → encode → identical bytes
   for every draw, like the texture gate).
2. **Strip builder.** Triangles → one strip per draw with degenerate joins (`… a a b b …`,
   watch the odd/even winding: `scene.strip_to_triangles` is the reference). A list of
   independent triangles joined by degenerates is a valid, simpler first version.
3. **glTF → draws.** Joints are game node indices already. Per draw: the set of nodes
   used → a contiguous run (`palette_start`, `count` ≤ 61; split the draw if needed),
   blend indices = 3 × (node − start), weights to bytes summing to 255, component k with
   k. Bounds (radius from origin, box) and shape words 5/6/7; `RenderStrip` word 0 =
   material **id** − 1.
4. **Command buffer.** Rebuild packets from the original's (copy sampler/state words,
   change the stream/index/draw arguments). Own-buffer shapes (characters) are simplest:
   `0x0B`/`0x0C` + the draw word; leave combined-buffer models for later.
5. **Rig validator:** bones the target lacks, unweighted vertices, > 4 influences,
   palette > 61 after splitting.
6. **Gates** (roadmap): (a) no-op round trip loads in game; (b) moved vertices load;
   (c) a new mesh rigged to the exported armature loads and animates, fingers and face
   included. Use `game_mods/` (phase 2) and a capture (phase 3) to prove each.
7. Guides `modding/08-edit-a-model.md`, `09-new-model.md`; troubleshooting rows.

## Facts to keep in mind

- Characters use **own** buffers (`<shape> Vertices N`); props and environments use
  `Combined Vertices <stride>` shared by every shape. A replacement must keep the
  layout family of the original.
- Weights must sum to 255 exactly (all 1.36 M skinned vertices of both games do); a
  shader pulls a vertex with a smaller sum toward the world origin.
- Tangent w decodes to 0 on half the vertices: understand it before writing new tangents
  (or copy the original's convention per shader).
- The 25 prop nodes with a rest scale don't survive Blender exactly; compare by world
  matrix or keep their records (`dev/gltf-mapping.md`).
- Unknown words are preserved, never zeroed: `RenderStrip` words 1, 2, 5, 6, shape words
  0-4, `VDHeader`, `_ATTRIBUTE_`, `_COLLPRIMS_`, value sets.
- Headless recomp runs: `CZ_BUG_REPORTS=0` (F9 otherwise writes, and prunes, the
  launcher's bug-report folder), a **copy** of the save, no frame dumps, `dr2 mod
  undeploy` afterwards, and check for a recomp the user started first
  (`pgrep -x cz_runtime`).

## Test data policy (unchanged)

Unit tests build synthetic scenes in code (`tests/conftest.py`'s `make_scene`). Census
and decode tests read the real games and skip with a message when a game is absent. No
game meshes, textures, screenshots or `.glb` exports in the repository.

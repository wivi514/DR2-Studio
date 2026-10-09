# The glTF mapping: game scenes ⇄ `.glb`

How `dr2kit/convert/gltf.py` turns a scene (`dr2kit/formats/scene.py`) into glTF 2.0
binary, and what it keeps so phase 4 can put a model back. The format facts it relies
on are in [`../formats.md`](../formats.md) §Scene container; the words are in the
[glossary](../glossary.md).

Why glTF: Blender imports and exports it without add-ons, three.js (DR2 Studio's 3D view)
loads it, and a `.glb` is just JSON plus one binary buffer, so it is written in pure
Python with no dependency (and runs inside Blender's Python too).

## What goes where

| Game | glTF | Notes |
|---|---|---|
| node record (52 bytes) | a node: `name`, `translation`, `rotation`, `scale` (only when not 1) | relative to the parent, like the game. The rotation is normalised (glTF requires unit quaternions; 8 prop records are not) |
| node index, parent, flag, the record bytes | node `extras.dr2 = {index, parent, flag, record}` | `record` is the 52 bytes in hex: what makes the round trip bit-exact |
| parent | `children` of the parent node | roots (parent −1, or itself in split rigs) go in the scene's node list |
| the whole skeleton | one **skin**: `joints` = every node in game order, `inverseBindMatrices` = the inverse of each node's rest pose in model space | because the joints are in game order, a vertex's `JOINTS_0` value **is** the game node index. Blender builds an armature only from a skin, so skeleton files get one too |
| shape (`<shape>` in `persistent.big`) | a mesh + a node of the same name (with `skin` when skinned) | node `extras.dr2 = {shape, words}` keeps the shape's 8 header words |
| draw (`RenderStrip` record + command packet) | a primitive | `extras.dr2 = {draw, material, palette, shader, shader_name, declaration}` |
| POSITION, NORMAL | `POSITION`, `NORMAL` (float) | normals normalised; a zero normal (136 CZ / 2,117 CW vertices) becomes (0, 0, 1) |
| TEXCOORD n (FLOAT2 or SHORT2N) | `TEXCOORD_n` (float), in usage order | UV origin is the top-left in both, so nothing flips |
| COLOR | `COLOR_0` (float RGBA) | |
| TANGENT | — | not exported: half the stored w (bitangent sign) values are 0, which glTF forbids; Blender recomputes tangents |
| BLENDINDICES + BLENDWEIGHT | `JOINTS_0` (unsigned short) + `WEIGHTS_0` (float) | palette slot → node through `palette_start + slot`; weights renormalised to sum exactly 1 |
| an unskinned draw in a skinned model | `JOINTS_0` = its first palette node, weight 1 | so every primitive of a skinned mesh has joints |
| triangle strip | `indices` as a triangle list | degenerate triangles dropped; odd triangles swapped to keep counter-clockwise fronts |
| material (`MatArray` + its slots) | a material named `NN_<colour texture>` | `baseColorTexture` = the `_cm` texture, `normalTexture` = the `_nm` one (DXN normal maps get their Z rebuilt); `extras.dr2` keeps id, hash, value set, the 4 floats and every texture name |
| textures | PNG images inside the `.glb` | found by `convert/model.py`'s `TextureFinder` |

**Axes and units:** none converted. The games are Y-up, metres, characters face +Z with
their left at +X, and front faces are counter-clockwise: all of that is glTF's own
convention (formats.md has how it was checked).

## Coming back from Blender: `skeleton_from_glb`

Reads node records back from any `.glb` whose nodes carry `extras.dr2` (Blender keeps
them as custom properties on bones and writes them back with *Include → Custom
Properties*). Blender stores bones as float32 matrices in armature space, so a round trip
brings back float noise: up to 1.5e-6 on rigs at the origin, 1.4e-4 on the cinematic
tiger rig placed ~400 m away. A value is taken as **unchanged** when it is within
`SNAP_TOLERANCE` (1e-5) + `SNAP_RELATIVE` (2e-6) × the node's distance from the origin
of the original, and the record's exact float32 bits are used; anything further is an
edit and is written as the new value.

**The gate** (`tools/blender_skeleton_gate.py`, phase 3): game rig → `.glb` → Blender
import → Blender export → `skeleton_from_glb`:

| | rigs | node records | bit-identical |
|---|---|---|---|
| `data/skeleton/*.big`, both games | 75 | 3,474 | **3,474** |
| every scene with a skeleton, both games (`--all-scenes`) | 3,058 | 41,209 | 41,184 |

The 25 that differ are prop and crowd nodes with a non-unit or negative rest **scale**
(the mirrored hand of `cine_jacket_sc701`, sky domes, cacti, `blender.big`). A Blender
armature bone has no rest scale, so the importer moves it elsewhere and the values that
come back are a different (equivalent or lossy) split. Phase 4 should compare such nodes
by their world matrices, or keep their records when the mesh is unchanged.

## Coming back: models (`model_import.py`, phase 4)

`plan_import(scene, glb)` reads a `.glb` (ours, or Blender's export of it) against the
model it goes into; `import_glb` then writes it through `formats/scene_write.py`. What it
relies on, and why:

| glTF | Game | How it is matched / converted |
|---|---|---|
| mesh node | shape | by node name (Blender's object name), then `extras.dr2.shape`, then the mesh name; a trailing `.001` is ignored. Unmatched objects (Blender's `Icosphere` bone shape, new objects) are reported and ignored; shapes the file doesn't have stay as they are |
| `skins[].joints` | skeleton nodes | **by name** (Blender re-orders bones), `extras.dr2.index` as a fallback. A weight on a bone the skeleton lacks is an error |
| primitive | one or more draws | one draw per primitive, more if its bones span over 61 node numbers (`split_by_palette`) |
| material | game material | by the exported name `NN_<colour texture>` (Blender keeps material names), then by a texture name inside it, else the shape's own material with a warning |
| `POSITION`, `NORMAL` | model space | skinned to the rest pose with the file's own matrices: Σ wᵢ · joint worldᵢ · inverse bindᵢ (the glTF rule), so Blender's own bind matrices and bone orientation don't matter; when that matrix is the identity within 1e-5 the values pass through bit for bit. Unskinned nodes use the node's world matrix |
| `JOINTS_0/1` + `WEIGHTS_0/1` | 4 influences | merged per bone, the 4 strongest kept, quantised to bytes summing to 255 |
| `TEXCOORD_n` | the declaration's `TEXCOORD` elements in usage order | missing sets copy UV 0 (warning) |
| `COLOR_0` | `COLOR` | white when absent |
| `TANGENT` | — | ignored: tangents are computed from UV 0 (formats.md §Tangent w) |
| `extras.dr2.source` (asset and scene) | — | a file exported from another model gets a warning |

**Unchanged shapes are not rewritten.** If a shape's primitives decode to exactly what
the model holds (same vertex order, triangles, material, float32 positions, UVs, normals
within 1e-3, the same weight bytes) it is kept byte for byte. That is what makes
"export, import, no edits" give back the identical file (every model of both games,
`dr2 census --reimport`). After Blender, vertices are re-ordered and split, so edited or
not, a shape that went through Blender is rebuilt (same triangles and weights; positions
within 1 µm).

**The armature must sit where the game's does.** Bone edits are not written in phase 4:
a joint more than 1 mm away from the game's rest pose gives a warning, and the mesh is
placed as Blender shows it while the game animates it with its own bones.

## What the export keeps for the way back

The primitive extras (material, palette, declaration, shader) say how each draw was
built; `JOINTS_0` are game node indices in our own files; material names carry the game
material number and colour texture; node extras carry the shape's words and the skeleton
records; asset and scene extras name the source model. Phase 4's importer uses the
names first, because Blender keeps names and re-orders everything else.

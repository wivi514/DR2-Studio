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

## What phase 4 needs from this

To write a model back: the primitive extras (material, palette, declaration, shader) say
how each draw was built; `JOINTS_0` are game node indices, so a new mesh rigged to the
exported armature maps straight back to node numbers, and a new palette is a run of
nodes (`palette_start`, `count` ≤ 61) covering the joints a draw uses; vertex attributes
re-encode with the declaration's types (`dr2kit/formats/vertex.py` documents each
packing).

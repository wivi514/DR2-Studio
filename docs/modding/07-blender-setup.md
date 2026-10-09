# Set up Blender for Dead Rising 2 models and skeletons

**You will:** open a game model in Blender with its skeleton, weights and textures, pose
it, and save it so its skeleton stays exactly the game's.
**Time:** ~10 min.   **Games:** both.
**You need:** Blender 4.2 or newer (tested with 5.2), and a `.glb` exported from the
game ([`04-extracting.md`](04-extracting.md)). No add-on: Blender's built-in glTF
importer is enough.

## Steps

1. Export a model: in DR2 Studio, click `data/models/npcs.big/boss_mechanic.big` and
   **Export .glb…**; or `dr2 extract --glb data/models/npcs.big/boss_mechanic.big -o out`.
2. In Blender: **File → Import → glTF 2.0 (.glb/.gltf)**, pick the file, keep the default
   options, **Import glTF 2.0**.
3. What you get in the Outliner: an **Armature** (98 bones for characters, named like the
   game: `dummy01.l_upperarm`), and one mesh object per game mesh (`geo_apronShape`,
   `geo_headShape` …), each with an Armature modifier and vertex groups named after the
   bones. The materials carry the colour and normal textures. Blender also adds a small
   `Icosphere` object: the importer's bone display shape, safe to ignore.
4. Look around: switch the viewport to **Material Preview** (press `Z`, then pick it).
   Characters stand in a T-pose, facing you when you look from Blender's **Front** view
   (numpad `1`), at real size (metres).
5. Pose it to check the skin: select the armature, switch to **Pose Mode**
   (`Ctrl+Tab`), click a bone (an upper arm) and rotate it (`R`). The mesh follows,
   fingers and face included. `Alt+R` puts the bone back.

### Several parts of Chuck in one scene

Chuck is built from parts (`chest_young_chuck`, `leg_young_chuck`,
`feet_young_chuck_over`, `hands_naked`, `head_young_chuck` in Case Zero's `npcs.big`).
Import each `.glb`: every part comes with its own copy of the same 98-bone rig and lines
up with the others. To pose them together, keep one armature and, on the other meshes,
point the Armature modifier at it.

### Saving your work

Keep a `.blend` as your working file. When you export back to `.glb` (for checking, and
for phase 4's "put it back in the game"):

1. **File → Export → glTF 2.0**, format **glTF Binary (.glb)**.
2. Under **Include**, tick **Custom Properties**. Each bone carries its original game
   record as a custom property (`dr2`); with it, the toolkit can rebuild the skeleton
   bit for bit. Without it, bone names and positions still come back but not the exact
   game values.

## Check it worked

- The model looks like it does in game, with textures (the mechanic: overalls, leather
  apron, welding mask, gauges on his back).
- In Pose Mode, bending a bone bends the right part of the mesh, with nothing torn.
- *Advanced:* select a bone, open **Bone Properties → Custom Properties**: there is a
  `dr2` entry with `index`, `parent`, `flag` and `record`.

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| Only dots or lines, no mesh | You exported a skeleton file or used `--skeleton` | Expected for `data/skeleton/*.big`: they have no mesh. Export the model instead. |
| Grey or pink surfaces | Textures weren't embedded, or the viewport is in Solid mode | Switch to Material Preview. If a texture was not found during export, run `dr2 index build` and export again. |
| The model is lying down or far away | A cinematic or level piece placed in its scene | Some props and cinematic rigs sit hundreds of metres from the origin, where the game places them. Press numpad `.` to frame the selection. |
| A few prop bones come back slightly different after export | They carry a scale in their rest pose, which Blender armatures can't store | Known limit (25 bones of 41,209 in both games, none on characters): see [`../dev/gltf-mapping.md`](../dev/gltf-mapping.md). |
| Import is slow | Big level pieces | Characters import in seconds; whole environment chunks have hundreds of thousands of triangles. |

## Going further

- Edit a model and put it back in the game: `08-edit-a-model.md` (phase 4).
- What the `.glb` holds and how it maps to the game: [`../dev/gltf-mapping.md`](../dev/gltf-mapping.md).
- Which rig a character uses: [`asset-catalogue.md`](asset-catalogue.md) §Skeletons.

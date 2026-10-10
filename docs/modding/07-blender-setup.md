# Set up Blender for Dead Rising 2 models and skeletons

**You will:** open a game model in Blender with its skeleton, weights and textures, pose
it, and save it so its skeleton stays exactly the game's.
**Time:** ~10 min.   **Games:** both.
**You need:** Blender 4.2 or newer (tested with 5.2), and a `.glb` exported from the
game ([`04-extracting.md`](04-extracting.md)). No add-on: Blender's built-in glTF
importer is enough. (The optional DR2 add-on does the import, the check and the export
to a mod from a sidebar tab: [`13-blender-addon.md`](13-blender-addon.md).)

## Steps

1. **Quickest:** in DR2 Studio, select the model (Library → Models → Characters →
   *Mechanic (boss)*, i.e. `data/models/npcs.big/boss_mechanic.big`) and click **Open in
   Blender**. Blender starts with the model imported, textures showing; skip to step 3.
   *By hand:* **Export .glb…** in Studio (or `dr2 extract --glb
   data/models/npcs.big/boss_mechanic.big -o out`), then step 2.
2. In Blender: **File → Import → glTF 2.0 (.glb/.gltf)**, pick the file. Under **Bones &
   Skin**, tick **Disable Bone Shape** (otherwise every bone is drawn as a ball), then
   **Import glTF 2.0**.
3. What you get in the Outliner: an **Armature** (98 bones for characters, named like the
   game: `dummy01.l_upperarm`), and one mesh object per game mesh (`geo_apronShape`,
   `geo_headShape` …), each with an Armature modifier and vertex groups named after the
   bones. The materials carry the colour and normal textures. (If you imported without
   *Disable Bone Shape*, Blender also adds a small `Icosphere` object, in a
   `glTF_not_exported` collection: the shape it draws bones with, safe to ignore.)
4. **See the textures:** press **`Z`** in the 3D view and pick **Material Preview** (or
   click the third sphere icon at the top right of the 3D view). The model is grey until
   you do: Blender's default *Solid* view doesn't draw textures. Open in Blender starts
   in Material Preview already.
   Characters stand in a T-pose, facing you when you look from Blender's **Front** view
   (numpad `1`), at real size (metres). The bones are drawn over the model: to hide
   them, see [below](#seeing-the-model-clearly-textures-and-bones).
5. Pose it to check the skin: select the armature, switch to **Pose Mode**
   (`Ctrl+Tab`), click a bone (an upper arm) and rotate it (`R`). The mesh follows,
   fingers and face included. `Alt+R` puts the bone back.

### Seeing the model clearly: textures and bones

| You want to… | Do this in Blender |
|---|---|
| **See the textures** | In the 3D view press **`Z` → Material Preview** (or the third sphere icon at the top right of the 3D view). *Solid* view draws everything grey. |
| **Hide the bones, keep everything else** | In the 3D view's top-right bar, open the **Viewport Overlays** dropdown (the small arrow next to the two-circles icon) and untick **Bones**. Only this 3D view changes. |
| **Hide the whole armature** | In the Outliner (top right), click the **eye** next to `Armature`, or select it and press **`H`** (**`Alt+H`** shows it again). The mesh still follows the bones; they just aren't drawn. |
| **Keep the bones but out of the way** | Select the armature → **Object Data Properties** (the running-man tab) → **Viewport Display**: *Display As* **Stick** or **Wire**, and untick **In Front** so the body hides the bones inside it. |
| **No balls on every bone** | Imported by hand without *Disable Bone Shape*: re-import with it ticked (**File → Import → glTF 2.0 → Bones & Skin**). Open in Blender and the DR2 add-on's Import already do this. |

Turn the bones back on the same way when you paint weights or pose the model.

### Several parts of Chuck in one scene

Chuck is built from parts (`chest_young_chuck`, `leg_young_chuck`,
`feet_young_chuck_over`, `hands_naked`, `head_young_chuck` in Case Zero's `npcs.big`).
Import each `.glb`: every part comes with its own copy of the same 98-bone rig and lines
up with the others. To pose them together, keep one armature and, on the other meshes,
point the Armature modifier at it.

### Saving your work

Keep a `.blend` as your working file. When you export back to `.glb` (for checking, and
to put it back in the game, [`08-edit-a-model.md`](08-edit-a-model.md)):

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
| Grey surfaces | The 3D view is in *Solid* mode, which doesn't draw textures | Press **`Z` → Material Preview**. |
| Pink surfaces | A texture wasn't found when the `.glb` was made | Run `dr2 index build` (Studio: *Build / refresh index*) and export again. |
| Balls all over the model | Blender draws each bone with a sphere (imported without *Disable Bone Shape*) | Re-import with **Bones & Skin → Disable Bone Shape**, or use Open in Blender. |
| Bones (spikes, pyramids) drawn over the model | That's the armature | **Viewport Overlays → untick Bones**, or hide `Armature` in the Outliner ([how](#seeing-the-model-clearly-textures-and-bones)). |
| The model is lying down or far away | A cinematic or level piece placed in its scene | Some props and cinematic rigs sit hundreds of metres from the origin, where the game places them. Press numpad `.` to frame the selection. |
| A few prop bones come back slightly different after export | They carry a scale in their rest pose, which Blender armatures can't store | Known limit (25 bones of 41,209 in both games, none on characters): see [`../dev/gltf-mapping.md`](../dev/gltf-mapping.md). |
| Import is slow | Big level pieces | Characters import in seconds; whole environment chunks have hundreds of thousands of triangles. |

## Going further

- Edit a model and put it back in the game: [`08-edit-a-model.md`](08-edit-a-model.md);
  a brand-new rigged mesh: [`09-new-model.md`](09-new-model.md).
- What the `.glb` holds and how it maps to the game: [`../dev/gltf-mapping.md`](../dev/gltf-mapping.md).
- Which rig a character uses: [`asset-catalogue.md`](asset-catalogue.md) §Skeletons.

# Edit a model in Blender and put it back in the game

**You will:** change the shape of part of a character (make Chuck's arms bigger), and see
it in game.
**Time:** ~20 min.   **Games:** both (checked in game on Case Zero).
**You need:** the toolkit, Blender 4.2 or newer (tested with 5.2), a recomp to try it in,
and Blender set up as in [`07-blender-setup.md`](07-blender-setup.md).

A model is made of **parts** (Blender objects such as `geo_larmShape`, the left arm). You
edit parts in Blender, export the whole file again, and the toolkit puts each part you
changed back into the game's model. Parts you didn't touch stay exactly as they were.

## Steps

1. **Export the model.** DR2 Studio: click `data/models/npcs.big/chest_young_chuck.big`
   (Case Zero's default shirt and arms), **Export .glb…**, save it as
   `chest_young_chuck.glb`.
   *Command line:* `dr2 extract --glb data/models/npcs.big/chest_young_chuck.big -o work`
2. **Open it in Blender:** **File → Import → glTF 2.0**, pick the file, default options.
   You get an armature and five parts: `geo_tshirtShape`, `geo_shirtbottomShape`,
   `geo_larmShape`, `geo_rarmShape`, `geo_watchShape`.
3. **Edit.** Click `geo_larmShape`, press `Tab` (Edit Mode), `A` (select all), then
   **Mesh → Transform → Shrink/Fatten** (`Alt+S`), move the mouse a little and click.
   Do the same for `geo_rarmShape`. `Tab` again to leave Edit Mode.
   Rules while editing (the [checker](#check-before-you-build) tells you if you broke one):
   - **Keep each object's name** (`geo_larmShape`). The name is how the toolkit knows
     which part of the game model it is.
   - **Keep the materials** (`01_young_cr_arms_naked_cm`…). The number and texture name
     tell the toolkit which game material to use.
   - Adding or deleting vertices is fine; new vertices need **bone weights** (Weight
     Paint mode, or **Ctrl+P → With Automatic Weights** on the armature).
   - **Don't move bones** of the armature: the game animates the mesh with its own
     skeleton.
4. **Export:** **File → Export → glTF 2.0**, format **glTF Binary (.glb)**, under
   **Include** tick **Custom Properties**, save as `chest_young_chuck_big_arms.glb`.

### Check before you build

5. DR2 Studio: select `data/models/npcs.big/chest_young_chuck.big` again, click
   **Replace with .glb…** and pick your export. Studio runs the **model check** and shows
   what it will do:

   ```
   replace geo_larmShape: 1 part(s) → 1 draw(s), 305 vertices, 546 triangles
   replace geo_rarmShape: 1 part(s) → 1 draw(s), 305 vertices, 546 triangles
   replace geo_shirtbottomShape: …
   OK
   ```

   `OK` means it can go in. (Parts you didn't edit are rebuilt too after a trip through
   Blender, because Blender renumbers vertices; they look the same.) If a mod is open, the file is
   copied into it as `replace/data/models/npcs.big/chest_young_chuck.big.glb`.
   *Command line:* `dr2 model check chest_young_chuck_big_arms.glb data/models/npcs.big/chest_young_chuck.big`
6. **Make the mod** (if you didn't have one open): **New mod…** in Studio (it asks for a
   name), then repeat
   step 5. Or by hand: `dr2 mod new big_arms`, then copy the `.glb` to
   `big_arms/replace/data/models/npcs.big/chest_young_chuck.big.glb` (the model's path
   plus `.glb`, exactly like a texture's `.png` in [`05-first-mod-texture.md`](05-first-mod-texture.md)).
7. **See it in game:** **▶ Play** in Studio (it deploys the mod and starts the recomp),
   or `dr2 mod deploy big_arms -g cz` and start the recomp.

## Check it worked

Start the recomp and load your save. Chuck's forearms are visibly thicker than without
the mod (start once with `CZ_NO_MODS=1` to compare). The recomp's log says
`'game:\data\models\npcs.big' served from the MODS overlay`.

Remove it again with **Remove mods from game** (or `dr2 mod undeploy -g cz`).

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| `object '…' matches no shape of the model` and nothing is replaced | The object was renamed | Rename it back to the part's name (`geo_larmShape`). Blender's `.001` endings are ignored. |
| `material '…' is not one of this model's` | A new or renamed material | Use one of the materials that came with the file (their texture decides the look); a part with an unknown material keeps the original part's material. |
| `N of M vertices have no bone weight` | New vertices that aren't weighted to any bone | Weight Paint them, or re-parent with **Automatic Weights**. |
| `vertices are weighted to bone 'Bone.001', which the game skeleton doesn't have` | A bone you added | The game can only use its own bones; move those weights to an existing bone. |
| `more than 4 bone weights; the 4 strongest are kept` (warning) | The game takes 4 influences per vertex | Usually fine. To control it: **Weights → Limit Total** (limit 4) in Weight Paint mode. |
| `N bone(s) are not where the game's skeleton has them` (warning) | Bones were moved, or the armature object was moved/scaled | Undo the move; put the armature back at the origin with scale 1. |
| `this file was exported from …, not from …` (warning) | You picked the wrong model in Studio | Select the model the `.glb` came from. |
| The part is invisible or stretched in game | Report it with the `.glb`, the model's path and the model check output | |

More in [`12-troubleshooting.md`](12-troubleshooting.md) §Model replacement.

## Going further

- Build a brand-new part and rig it: [`09-new-model.md`](09-new-model.md).
- How the file maps to the game: [`../dev/gltf-mapping.md`](../dev/gltf-mapping.md)
  §Coming back: models.
- What the toolkit writes: [`../formats.md`](../formats.md) §Writing scenes.

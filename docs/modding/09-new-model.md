# Put a brand-new mesh on a character, rigged to the game's skeleton

**You will:** replace a part of a character with a mesh of your own (something you
modelled, or imported from another file), rig it to the game's armature, and see it
animate in game, fingers and face included.
**Time:** ~30 min.   **Games:** both (checked in game on Case Zero).
**You need:** everything from [`08-edit-a-model.md`](08-edit-a-model.md), which you
should do first.

**How it works.** A game model has a fixed list of parts (Blender objects such as
`geo_watchShape`). Your new mesh **takes the place of one part**: give it that part's
name. It can have any shape and any number of vertices (up to 65,536 per part), it can
use any material the model already has, and it can be weighted to any bones of the
game's skeleton. The toolkit writes it in the game's own format and, if it uses bones
too far apart for one draw call (the game sends at most 61 bones per draw), splits it
into several draws by itself.

What you can't do yet: add a part the model doesn't have, add bones, or bring new
textures in the same step (replace a texture with a PNG as in
[`05-first-mod-texture.md`](05-first-mod-texture.md)).

## Steps

1. **Export the model** that has the part you want to replace, and import it into
   Blender ([`08-edit-a-model.md`](08-edit-a-model.md) steps 1-2). Here: Case Zero's
   `data/models/npcs.big/chest_young_chuck.big`, replacing the watch `geo_watchShape`.
2. **Remove the old part:** click `geo_watchShape`, press `X` → **Delete**.
3. **Bring your mesh in:** model it, or **File → Import** / **Append** it from another
   file. Place it on the character in the T-pose: scale and position it in Blender until
   it sits where you want it on the body. Apply its transforms: **Object → Apply → All
   Transforms**.
4. **Name it like the part it replaces:** double-click it in the Outliner and type
   `geo_watchShape`.
5. **Give it a material from the model:** in **Material Properties**, pick one of the
   existing materials from the list (`00_young_cr_shirt_cm`, `01_young_cr_arms_naked_cm`,
   `02_watch_cm`). Each part of your mesh can use a different one. The texture comes from
   that material. Unwrap your mesh (**UV → Smart UV Project**) so the texture lands
   somewhere sensible.
6. **Rig it:** click your mesh, then **Shift+click** the armature, press **Ctrl+P →
   With Automatic Weights**. Blender gives every vertex weights to the nearest bones,
   fingers and face included.
   - Check in **Pose Mode**: bend a finger bone and the jaw; your mesh should follow.
   - Fix weights in **Weight Paint** mode if needed. Every vertex needs at least one bone.
   - Only the game's bones: don't add bones to the armature.
7. **Export** as `.glb` with **Custom Properties** ticked ([`08`](08-edit-a-model.md) step 4).
8. **Check it:** DR2 Studio → select the model → **Replace with .glb…** (or
   `dr2 model check my_watch.glb data/models/npcs.big/chest_young_chuck.big`). For a mesh
   on both hands and the face you will see something like:

   ```
   replace geo_watchShape: 1 part(s) → 2 draw(s), 3,600 vertices, 1,200 triangles
   info: geo_watchShape part 0: uses bones over more than 61 node numbers: split into 2 draws (25-85, 86-91)
   OK
   ```

   The split is normal and automatic.
9. **Build and deploy** the mod (Studio **Build && deploy**, or
   `dr2 mod deploy my_mod -g cz`), start the game.

## Check it worked

Your mesh is where the watch was (or wherever you placed it) and moves with Chuck:
walk, look at his hands when he holds something, watch his face when he talks. What the
toolkit was tested with (`tools/blender_gate_model.py` builds it): a small sphere on
every finger and face bone. In game they sat on the fingers curled round a bottle and on
the lips and nose, and the game's own bone matrices for those bones were identical to the
ones Chuck's real hands and head got in the same frame.

## If something went wrong

Everything in [`08-edit-a-model.md`](08-edit-a-model.md) §If something went wrong, plus:

| Symptom | Cause | Fix |
|---|---|---|
| `the material's shader is rigid … weight every vertex of this part to one bone` | The material you picked belongs to a part that never bends (glasses, a buckle) | Use another material, or weight the whole part to one bone (select all, assign to one vertex group with weight 1). |
| `the material's shader is skinned, but the part has no bone weights` | The mesh isn't parented to the armature with weights | Step 6. |
| `a triangle uses nodes A..B, more than 61 apart` | One triangle is weighted to bones far apart in the skeleton's numbering (a finger and the face) | Split that triangle's weights: no single triangle should mix far-apart bone groups. |
| `N vertices; a shape holds at most 65,536` | Too many vertices for one part | Decimate (**Modifiers → Decimate**, then apply). |
| `no UVs: textures will not map` (warning) | The mesh was never unwrapped | Step 5. |
| Your mesh is in the right place in Blender but floats or sinks in game | The armature or mesh object had a transform when exported | Apply all transforms on the mesh (step 3); keep the armature at the origin with scale 1. |
| The mesh looks too dark or too shiny | It uses a material made for another kind of surface (the watch's eye-like shader) | Try another of the model's materials, then fix the look with a texture mod. |

More in [`12-troubleshooting.md`](12-troubleshooting.md) §Model replacement.

## Going further

- The rules the checker applies, and why: [`../dev/gltf-mapping.md`](../dev/gltf-mapping.md)
  §Coming back: models; [`../formats.md`](../formats.md) §Writing scenes (bone
  palettes, splitting, the 255 weight rule).
- Which models and skeletons a character uses: [`asset-catalogue.md`](asset-catalogue.md).

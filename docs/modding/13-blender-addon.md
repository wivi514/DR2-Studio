# The Blender add-on: find, import, check and export models from inside Blender

**You will:** install the DR2 add-on for Blender, import a game model with one click,
check your edit against the game's rig, and write it into a mod without leaving
Blender.   **Time:** ~10 min.   **Games:** both.
**You need:** Blender 4.2 or newer (tested with 5.2), the toolkit set up with its
**asset index built** (DR2 Studio: **Build / refresh index**, or `dr2 index build`), and
the add-on zip `io_dr2-<version>.zip` (in a DR2 Studio release, or built from the
toolkit, below).

Seeing it: press **`Z` → Material Preview** for the textures; to hide the bones, untick
**Bones** in the 3D view's **Viewport Overlays** dropdown
([more ways](07-blender-setup.md#seeing-the-model-clearly-textures-and-bones)).

Shortcut: in DR2 Studio, select a model and click **Open in Blender**: Blender starts
with it imported and the add-on's mod folder set to Studio's open mod.

The add-on is optional: [`07-blender-setup.md`](07-blender-setup.md) and
[`08-edit-a-model.md`](08-edit-a-model.md) do the same with export/import by hand. It
saves the round trips through files and dialogs.

**Why it asks for the toolkit's folder.** Blender's add-ons are GPL software; the
toolkit has its own free, non-commercial licence. So the add-on (GPL) does not contain
the toolkit: it uses the copy you already have, from the folder you give it.

## Steps

### Install

1. In Blender: **Edit → Preferences → Get Extensions**, the **⌄** menu at the top right
   → **Install from Disk…**, pick `io_dr2-<version>.zip`. (Blender 4.2+: add-ons are
   "extensions".)
2. Still in Preferences, **Add-ons**, find **DR2 Modding Toolkit**, open it, and set
   **Toolkit folder** to the toolkit's folder: the one that contains the `dr2kit`
   folder (your git checkout, or the `python` folder of a DR2 Studio release). The line
   under it turns into `dr2kit 0.1.0 (…), LZX: native` when it's right.
3. In the 3D viewport press `N` to open the sidebar; there is a **DR2** tab.

### Import a model

4. In the **DR2** tab, pick **Case Zero** or **Case West**, type part of a name
   (`chest_young_chuck`, `mechanic`, `*fullbody` for rigs) and press the magnifier. The
   list shows models (mesh icon) and skeletons (bone icon); the path of the selected one
   is under the list.
5. Leave **Textures** on (off is faster), tick **Skeleton only** for just the armature,
   and click **Import**. The model arrives in its own collection, named after it, with
   its armature, meshes, weights and textures, exactly as `dr2 extract --glb` and the
   glTF importer would give. A model with **variants** (a zombie's heads, shirts…) gets
   one collection per group inside it (*Head 1*, *Head 2*, *Shirt 3*, *Wound caps*…),
   with the parts of the default look shown and the others hidden (eye icons in the
   Outliner); its colour choices are in the **glTF Variants** tab
   ([`17-variants.md`](17-variants.md)). **Export to mod** sends the visible parts; the
   hidden ones stay as they are in the game.

### Edit, check, export to a mod

6. Edit the meshes as in [`08-edit-a-model.md`](08-edit-a-model.md) or
   [`09-new-model.md`](09-new-model.md) (keep the object names of the parts you
   replace; weight new meshes to the game's bones).
7. Select any object of the model and click **Check rig**. The tab shows `OK: 0
   error(s), …` or `FAILED: …`; the full report (each part, its draws, every problem)
   is in the **Text editor**, in a text called `DR2 rig check`.
8. Set **Mod folder** to your mod (or an empty folder: the add-on makes a mod there, for
   this game only) and click **Export to mod**. It checks again and, if the check
   passes, writes `replace/<model path>.glb` into the mod.
9. Deploy the mod with DR2 Studio (**Open mod…**, **▶ Play**) or
   `dr2 mod deploy <mod folder> -g cz`.

### Building the add-on zip yourself

From the toolkit's folder:

```
blender --command extension build --source-dir blender/io_dr2 --output-dir build/addon
```

or, without Blender, `python tools/build_release.py addon` (the same zip).

## Check it worked

- The **DR2** tab shows the game switch and the search box (not "Toolkit not found").
- An imported, unchanged model passes **Check rig** with 0 errors.
- After **Export to mod**, `dr2 mod check <mod folder> -g cz` lists the model as
  `model-glb … OK`.

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| "Toolkit not found" in the tab | The add-on can't import dr2kit | Set **Toolkit folder** in the add-on's preferences to the folder that contains `dr2kit`. |
| "Another dr2kit is already loaded … restart Blender" | You changed the folder after a first use | Restart Blender. |
| "No asset index yet" | The index was never built | DR2 Studio: **Build / refresh index**, or `dr2 index build`. |
| The search finds nothing | Wrong game, or the name is a texture or a sound | The tab lists models and skeletons only; check the game switch. |
| "Select an object of a model imported with the DR2 tab" | The selected object isn't in a collection made by **Import** | Select an object of that collection (or move your new mesh into it). |
| **Check rig** fails | The validator found a problem (an unknown bone, a part without weights…) | Read `DR2 rig check` in the Text editor; [`08-edit-a-model.md`](08-edit-a-model.md) explains each message. |
| "The mod … is not for cw" | The mod's `mod.toml` lists other games | Add the game to `games` in `mod.toml`, or use another mod folder. |

## Going further

- What the checks mean and the replacement rules: [`08-edit-a-model.md`](08-edit-a-model.md),
  [`09-new-model.md`](09-new-model.md).
- How the add-on is built: [`../dev/blender-addon.md`](../dev/blender-addon.md).

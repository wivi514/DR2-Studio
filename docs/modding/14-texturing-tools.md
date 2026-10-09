# Texture a model in Substance Painter (or Blender, GIMP, Krita…) and put it in the game

**You will:** take a game model into a texturing program, paint it, export the textures
the way the game needs them, and get them into your mod in one step.
**Time:** ~20 min (plus your painting).   **Games:** both.
**You need:** DR2 Studio with the index built ([`01-install.md`](01-install.md)), and a
texturing program: Substance 3D Painter, Blender, ArmorPaint, Quixel Mixer, or a 2D
editor (GIMP, Krita, Photoshop, Paint.NET).

## What the game needs (read this once)

DR2 is not a "PBR" game. Its materials use three kinds of picture, and only these:

| Game texture | Ends in | Painter channel | Rules |
|---|---|---|---|
| **Colour** | `_cm` (also `_dm`) | Base Color / Diffuse | RGB. **Transparency (alpha) only works if the original has it** (hair, eyelashes: DXT5 textures); on other colour maps alpha is dropped, or kept as on/off at most. |
| **Normal** | `_nm` | Normal | **OpenGL-style (green up)**, like Blender and glTF. A DirectX-style map is detected and fixed for you. |
| **Specular** | `_sm` | Specular | RGB colour of the shine (not greyscale only). Many models have none. |

There is **no** roughness, metallic, height or ambient-occlusion map in DR2. Bake AO
into the colour if you want it. If you paint in metal/roughness, export *Metallic* too:
the toolkit turns BaseColor + Metallic into colour + specular.

Sizes: export at any size **with the same shape** (square stays square); the toolkit
resizes to the game texture's size (usually 256-1024 px for characters). The game
textures keep their size in v1. Limits for models, UVs and textures:
[`15-limits.md`](15-limits.md).

## Steps

### 1. Get the model out

In DR2 Studio, select the model (e.g. `data/models/npcs.big/chest_young_chuck.big`) and
**Export .glb…** (or `dr2 extract --glb <model> -o out`). Each material in the file is
named like `00_young_cr_shirt_cm`: its number, then its colour texture. **Keep these
names**; they are how the textures find their way back.

### 2. Substance 3D Painter

1. **File → New**. *Template*: **PBR - Specular Glossiness** (closest to DR2) or the
   default metal/roughness one (both work). *File*: the `.glb`. *Normal map format*:
   **OpenGL**. *Document resolution*: 1024 or 2048 (you'll export at the shape of the
   game texture). Leave *Use UV tile workflow* (UDIM) **off**: DR2 uses one 0-1 tile.
   *Compute tangent space per fragment*: on (default).
2. Each **texture set** is one game material (`00_young_cr_shirt_cm`, `01_…`). Paint.
   Baking mesh maps (ambient occlusion, curvature) for your generators is fine; only the
   final Base Color, Normal and Specular (or Metallic) reach the game.
3. **File → Export Textures**:
   - *Output template*: **PBR Specular Glossiness** (gives `…_Diffuse`, `…_Specular`,
     `…_Glossiness`, `…_Normal`) or **PBR Metallic Roughness** (`…_BaseColor`,
     `…_Metallic`, `…_Roughness`, `…_Normal`). The default file names
     (`$mesh_$textureSet_<channel>`) are fine; don't remove `$textureSet`.
   - *File type*: **png**, 8 bits. *Size*: the document's, or the game texture's.
   - *Padding*: dilation (default) is good: it avoids seams in the game's mip levels.
   - Export into an empty folder.
4. Glossiness, Roughness and the like are ignored by the import (it says so); you don't
   need to delete them.

### 3. Put the textures into the mod

**In DR2 Studio:** open your mod (or **New mod…**), select the same model, click
**Import textures…** and pick the export folder (or drop the folder on the window).
Studio lists what goes where, for example:

```
colour   young_cr_shirt_cm   ← chest_young_chuck_00_young_cr_shirt_cm_Diffuse.png  (resized 2048×2048 → 1024×1024)
normal   young_cr_shirt_nm   ← chest_young_chuck_00_young_cr_shirt_cm_Normal.png  (resized 2048×2048 → 512×512)
skipped  …_Glossiness.png: DR2 has no map for this channel
```

Click **Yes**; the mod's list shows the textures. Select a texture to see it as the game
will get it, then **▶ Play**.

**With the `dr2` command:**

```
dr2 mod import-textures my_mod data/models/npcs.big/chest_young_chuck.big painter_export/ -n   # show
dr2 mod import-textures my_mod data/models/npcs.big/chest_young_chuck.big painter_export/      # do it
dr2 play -g cz
```

## Other programs

The import accepts any files named **`<texture set>_<channel>`** (channel: BaseColor,
Diffuse, Albedo, Color, Normal, Normal_DirectX, Specular, Metallic) or named **exactly
like the game texture** (`young_cr_shirt_cm.png`), as PNG (JPEG, TGA and TIFF too when
Pillow is installed, which a release includes). So:

- **Blender** (texture paint, or baking): import the `.glb` ([`07-blender-setup.md`](07-blender-setup.md)),
  paint on the material's images (keep the material names), then either **File → Export
  → glTF** and give that `.glb` to **Import textures…** (it takes the base colour and
  normal images of each material), or save each image as `<game texture name>.png`.
  Blender's normal maps are OpenGL-style, as the game's.
- **ArmorPaint, Quixel Mixer, 3DCoat:** import the `.glb` (or an FBX made from it in
  Blender), keep the material names as texture sets, export PNG with
  `<texture set>_BaseColor` / `_Normal` names, OpenGL normals.
- **2D editors (GIMP, Krita, Photoshop, Paint.NET):** for a colour change you don't need
  a 3D program: select the texture in Studio and **Edit in image editor…** (each save
  goes into the mod). For several textures at once, export them with
  `dr2 extract --png`, edit, keep their names, and **Import textures…** the folder.
  Normal maps need a normal-map tool (NVIDIA Texture Tools, Krita's normal-map filter,
  Materialize); keep them OpenGL-style.
- **3ds Max, Maya:** for *texturing* these are like Blender: paint, export images named
  as above. For *modelling*, go through Blender (FBX → Blender → `.glb`) so the bones and
  names stay right ([`08-edit-a-model.md`](08-edit-a-model.md)).

## Check it worked

- **Import textures…** lists each of your textures with the game texture it replaces,
  and nothing important under "skipped".
- Selecting a replaced texture in Studio shows your version ("showing the open mod's
  version" in Details).
- In game, the model wears your textures; bumps look raised, not dented.

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| `no material of this model is called 'Material.001'` | The texture set was renamed (or a new material was made) | Keep the exported names (`00_young_cr_shirt_cm`), or name files like the game textures. |
| `… doesn't have the shape of young_cr_shirt_cm` | The export isn't the same width:height ratio | Export square for a square texture (or the right ratio). |
| Bumps look dented / lit from the wrong side | A normal map with the other green direction that the toolkit couldn't measure (a nearly flat map) | Export with *Normal OpenGL* (Painter: project setting **OpenGL**). |
| Transparent parts are solid in game | The game texture is DXT1 (no smooth alpha) | Only textures that already have alpha (hair, lashes) can be see-through; the import notes this. |
| `this material has no specular map` | That material uses colour (+ normal) only | Expected; the specular export is ignored. |
| Colours look darker than in Painter | Painter shows PBR lighting; the game lights with its own shaders | Judge in game; brighten the Base Color a little if needed. |
| Seams at UV edges in game | No padding around the UV islands | Keep Painter's dilation padding on. |

## Going further

- The limits of models, UVs, bones and textures: [`15-limits.md`](15-limits.md).
- Changing the mesh itself: [`08-edit-a-model.md`](08-edit-a-model.md),
  [`09-new-model.md`](09-new-model.md); the Blender add-on: [`13-blender-addon.md`](13-blender-addon.md).
- The measurements behind these rules: [`../formats.md`](../formats.md) §Texture
  conventions, §Engine limits.

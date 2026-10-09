# Export assets: textures as PNG, models and skeletons as `.glb`, sounds as WAV

**You will:** save textures as PNG images you can open anywhere, models or skeletons
as `.glb` files that Blender opens with their bones, weights and textures, and sounds as
WAV files any player opens.
**Time:** ~5 min.   **Games:** both.
**You need:** the toolkit pointed at your game ([`02-game-data.md`](02-game-data.md)).

> Sounds need PyAV (`pip install av`): it holds the XMA decoder.

## Steps

### In DR2 Studio

1. Find the texture ([`03-browsing.md`](03-browsing.md)) and click it.
2. **Export PNG…** saves the full-size image. Cube maps are saved as one strip of six
   faces side by side (+X, −X, +Y, −Y, +Z, −Z).
3. **Extract…** saves the asset exactly as the game stores it (a `.bct` texture, a
   `.txt` file…), unpacked from its archive. Useful for other tools; for editing
   textures, use PNG.

### With the `dr2` command

```
# one texture as PNG
dr2 extract --png data/models/npcs.big/chest_young_chuck.tex/young_cr_shirt_cm -o out
# a smaller mip level instead of the full size
dr2 extract --png --level 2 data/models/npcs.big/chest_young_chuck.tex/young_cr_shirt_cm -o out
# every texture of a pack (or of a whole archive, nested ones included) as PNG
dr2 extract --png -r data/models/npcs.big/chest_young_chuck.tex -o out
# one sound as WAV (writes out/data/audio/music.big/HB_Indemnify.xma.wav)
dr2 extract --wav data/audio/music.big/HB_Indemnify.xma -o out
# every sound of a bank
dr2 extract --wav -r data/audio/music.big -o out
```

In DR2 Studio, a sound has **Export WAV…** (and **Play**, [`10-audio.md`](10-audio.md)).

Files land under `out/` at their virtual path, with `.png` added:
`out/data/models/npcs.big/chest_young_chuck.tex/young_cr_shirt_cm.png`. Keep that
layout in mind: a mod uses the same path to know which texture a PNG replaces.

### Models and skeletons (`.glb`)

A model is a character, an outfit part, a weapon, a prop or a piece of a level; a
skeleton is a rig on its own (`data/skeleton/`). Both export to **`.glb`** (glTF binary),
one file holding the meshes, the skeleton, the skin weights and the textures.

**In DR2 Studio:** click the model (search for `mechanic`, or browse to
`data/models/npcs.big/boss_mechanic.big`). The centre shows it in 3D: drag to turn it,
right-drag to move, scroll to zoom; **Skeleton** shows the bones, **Wireframe** the
triangles. **Export .glb…** saves it. A skeleton file shows its bones.

**With the `dr2` command:**

```
# a whole character, textures included
dr2 extract --glb data/models/npcs.big/boss_mechanic.big -o out
# one of Chuck's outfit parts (Case Zero's default shirt)
dr2 extract --glb data/models/npcs.big/chest_young_chuck.big -o out
# only the skeleton of a model, or a rig from data/skeleton/
dr2 extract --glb --skeleton data/models/npcs.big/boss_mechanic.big -o out
dr2 extract --glb data/skeleton/playerfullbody.big -o out
# without textures (smaller, faster)
dr2 extract --glb --no-textures data/models/npcs.big/boss_mechanic.big -o out
```

The file is `out/<vpath>.glb`, e.g. `out/data/models/npcs.big/boss_mechanic.big.glb`.
`dr2 info data/models/npcs.big/boss_mechanic.big` lists its materials (with their
texture names), every mesh and draw, and the bones each draw uses.

What is in the `.glb`:

- **Meshes**, one per game mesh (`geo_apronShape` …), with normals and every UV set.
- **The skeleton** as a Blender armature, bones named as in the game
  (`dummy01.l_upperarm`), in the rest pose (a T-pose for characters).
- **Skin weights**, up to 4 bones per vertex, already mapped to the skeleton.
- **Materials** with the colour (`_cm`) and normal (`_nm`) textures. Other textures
  (specular `_sm`, tint `_mask`) are listed in the material's custom properties; export
  them as PNG if you need them.
- Each bone's original game record, so the skeleton can be put back exactly. Edited models go back into the game with
  [`08-edit-a-model.md`](08-edit-a-model.md).

Chuck is assembled from parts: `chest_*`, `leg_*`, `feet_*`, `hands_*`, `head_*`,
`headwear_*` in `npcs.big`, all on the same 98-bone player rig, so you can import several
into one Blender scene and they line up. Next: [`07-blender-setup.md`](07-blender-setup.md).

## What you get (textures)

| Texture format | PNG | Notes |
|---|---|---|
| DXT1 | RGB, or RGBA when it has transparent pixels | most colour maps |
| DXT5 | RGBA | textures with smooth transparency (UI, hair, foliage) |
| DXN | RGB | normal maps: R and G are the stored X and Y; B is rebuilt so it looks like a normal map |
| A8R8G8B8 | RGBA | uncompressed: colour-grading tables (`cc_*.bct`), some UI gradients |
| L8 | greyscale | font pages |

`dr2 info <vpath>` shows a texture's format, size, mip levels and how it is stored.

## What you get (sounds)

16-bit WAV with the sound's own channels and rate: mono for effects and voices, stereo
for music, **6 channels (5.1)** for cutscene audio (`data/audio/cinematics.big`), at
48000 Hz (some effects a few hertz off, as the game stores them). `dr2 info` on a sound
shows its channels, rate, length and loop. A few voice entries are 0.1 s of silence on
purpose (placeholders).

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| `… is a folder; give a file or entry` | You gave a folder | Give a file or archive entry; `-r` for whole archives. |
| The PNG is a strange colour | Normal map (`_nm`), specular (`_sm`) or mask (`_mask`) | Expected: they hold data, not colours. |
| `--glb needs one` / "not a model or skeleton" | The path is a texture pack, a sound bank… | Give the model's `.big` (the one next to its `.tex`). |
| `decoding XMA needs PyAV` | `--wav` without PyAV | `pip install av`. |
| `note: texture 'x' not found` | The texture lives in another archive | Run `dr2 index build` once; the export then searches the whole game. The model is still exported, without that texture. |
| The 3D view says it needs QtWebEngine | Your PySide6 install lacks it | `pip install PySide6-Addons`, or use **Export .glb…** and Blender. |

## Going further

- Edit one and put it back: [`05-first-mod-texture.md`](05-first-mod-texture.md).
- Set up Blender for these files: [`07-blender-setup.md`](07-blender-setup.md).
- How textures and models are stored: [`../formats.md`](../formats.md) §Textures,
  §Scene container; what the `.glb` holds exactly: [`../dev/gltf-mapping.md`](../dev/gltf-mapping.md).

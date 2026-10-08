# Export assets: textures as PNG (models and sounds later)

**You will:** save textures as PNG images you can open anywhere, one at a time or whole
archives at once.   **Time:** ~5 min.   **Games:** both.
**You need:** the toolkit pointed at your game ([`02-game-data.md`](02-game-data.md)).

> Models and skeletons (`.glb` for Blender) arrive in phase 3, sounds (WAV) in phase 5.
> This guide grows with them.

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
```

Files land under `out/` at their virtual path, with `.png` added:
`out/data/models/npcs.big/chest_young_chuck.tex/young_cr_shirt_cm.png`. Keep that
layout in mind: a mod uses the same path to know which texture a PNG replaces.

## What you get

| Texture format | PNG | Notes |
|---|---|---|
| DXT1 | RGB, or RGBA when it has transparent pixels | most colour maps |
| DXT5 | RGBA | textures with smooth transparency (UI, hair, foliage) |
| DXN | RGB | normal maps: R and G are the stored X and Y; B is rebuilt so it looks like a normal map |
| A8R8G8B8 | RGBA | uncompressed: colour-grading tables (`cc_*.bct`), some UI gradients |
| L8 | greyscale | font pages |

`dr2 info <vpath>` shows a texture's format, size, mip levels and how it is stored.

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| `… is a folder; give a file or entry` | You gave a folder | Give a file or archive entry; `-r` for whole archives. |
| The PNG is a strange colour | Normal map (`_nm`), specular (`_sm`) or mask (`_mask`) | Expected: they hold data, not colours. |

## Going further

- Edit one and put it back: [`05-first-mod-texture.md`](05-first-mod-texture.md).
- How textures are stored: [`../formats.md`](../formats.md) §Textures.

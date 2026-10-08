# Your first mod: recolour a texture and see it in game

**You will:** turn Chuck's orange "04" shirt a different colour, build that into a mod,
and see it in the game.   **Time:** ~15 min.   **Games:** both (the example uses Case Zero).
**You need:** the toolkit set up and pointed at your game
([`02-game-data.md`](02-game-data.md)), an image editor that saves PNG (GIMP, Krita,
Paint.NET, Photoshop…), and for the in-game check a Case Zero or Case West **recomp**.
On Xenia or a console, see [Going further](#going-further).

A *texture* is an image the game wraps around a 3D model: Chuck's shirt is a flat
picture of the shirt's fabric, folded around his body. You'll export it as a PNG, paint
on it, and give it back to the toolkit, which turns it into the game's own format.

## Steps

### In DR2 Studio

1. Start DR2 Studio (`dr2 studio`). The first time, click **Build / refresh index** and
   wait about a minute while it reads the game. The log at the bottom says when it's done.
2. Pick the game in the **Game** box at the top (Case Zero).
3. Click the **Search** tab, type `young_cr_shirt` and press Enter. Click
   `…/npcs.big/chest_young_chuck.tex/young_cr_shirt_cm`. The middle shows the texture;
   the right says it is a 1024×1024 DXT1 texture with 9 mip levels.
   (Case West: Chuck wears his IJIEK racing jacket there,
   `npcs.big/chest_default.tex/cr_jacket_cm`. Other outfits: [`asset-catalogue.md`](asset-catalogue.md).)
   *Tip:* the end of the name tells you what kind of texture it is: `_cm` is the colour
   map, the one to edit for colours. `_nm` (normal map) and `_sm` (specular) hold shading
   data and look strange on purpose.
4. Click **Export PNG…** and save `young_cr_shirt_cm.png` somewhere you'll find it.
5. Open the PNG in your image editor and change the colours: a hue shift, a tint,
   painting on it, anything. **Keep the size exactly 1024×1024** and save as PNG.
6. Back in DR2 Studio, click **New mod…** at the bottom and choose an empty folder, e.g.
   `Documents/dr2-mods/green_shirt`. The toolkit writes a `mod.toml` there (you can edit
   the name, author and description in it later).
7. With `young_cr_shirt_cm` still selected, click **Replace with PNG…** and pick your edited
   PNG. The mod's file list at the bottom now shows
   `data/models/npcs.big/chest_young_chuck.tex/young_cr_shirt_cm.png`.
8. Click **Build && deploy**. The log says which game file was rebuilt
   (`data/models/npcs.big`) and where it went (the recomp's `assets/game_mods/` folder).
9. Start the recomp as usual and load a game where Chuck wears his default outfit.

### With the `dr2` command

The same steps, typed:

```
dr2 extract --png data/models/npcs.big/chest_young_chuck.tex/young_cr_shirt_cm -o exported
# edit exported/data/models/npcs.big/chest_young_chuck.tex/young_cr_shirt_cm.png, keep 1024x1024
dr2 mod new green_shirt
mkdir -p green_shirt/replace/data/models/npcs.big/chest_young_chuck.tex
cp exported/data/models/npcs.big/chest_young_chuck.tex/young_cr_shirt_cm.png \
   green_shirt/replace/data/models/npcs.big/chest_young_chuck.tex/
dr2 mod check green_shirt -g cz         # checks names and sizes, writes nothing
dr2 mod deploy green_shirt -g cz        # builds, then copies into the recomp's game_mods/
```

The folder layout under `replace/` is the asset's **virtual path** plus `.png`: that is
how the toolkit knows which texture your PNG replaces.

## Check it worked

- In game, Chuck's shirt has your colours.
- The recomp's log has one line per file it loaded from your mod:
  `VFS: 'game:\data\models\npcs.big' served from the MODS overlay -> …/game_mods/…`.
- To compare with the original, start the recomp with mods switched off:
  `CZ_NO_MODS=1` (Case West: `CW_NO_MODS=1`). The shirt is back to normal; nothing
  else changed.

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| `the image is 512x512; this texture needs exactly 1024x1024` | The PNG was resized | Resize it back to the size the error names. Changing texture sizes comes in a later version. |
| `no asset '…' in cz` | A typo in the folder path under `replace/`, or the texture only exists in the other game | Copy the path from DR2 Studio's details panel. Set `games = ["cz"]` in `mod.toml` if the mod is for one game. |
| The colour doesn't change in game | The outfit you see isn't the one you edited (Chuck has many outfits, each with its own textures; Case Zero ships the DR2 jacket too, unused at the start) | Find the outfit's model (`chest_…` in `npcs.big`), then `dr2 index textures-of` it, or check [`asset-catalogue.md`](asset-catalogue.md). |
| No `MODS overlay` line in the log | The recomp is older than this feature, or `CZ_NO_MODS` is set | Update the recomp; unset the variable. |
| Colours look blocky at the edges of what you painted | DXT1 compression stores each 4×4 pixel block with only 4 colours | That's how the game stores it; soft gradients and large flat areas look best. |

More in [`12-troubleshooting.md`](12-troubleshooting.md).

## Going further

- Undo: `dr2 mod undeploy -g cz`, or **Undeploy** in DR2 Studio. Only the files the
  toolkit put in `game_mods/` are removed.
- For Xenia or a real console, build the patched files into a folder instead:
  `dr2 mod build green_shirt -g cz -o out` (or `dr2 mod deploy … --to out`), then replace
  the game's own file with `out/data/models/npcs.big` (keep a backup of the original).
- What a mod folder holds, `mod.toml`, several mods at once: [`06-mod-packages.md`](06-mod-packages.md).
- Finding other textures: [`03-browsing.md`](03-browsing.md), [`asset-catalogue.md`](asset-catalogue.md).
- How it works inside: [`../formats.md`](../formats.md) §Textures.

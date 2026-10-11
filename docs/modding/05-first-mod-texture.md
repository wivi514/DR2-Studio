# Your first mod: recolour a texture and see it in game

**You will:** turn Chuck's orange "04" shirt a different colour, build that into a mod,
and see it in the game.   **Time:** ~10 min.   **Games:** both (the example uses Case Zero).
**You need:** the toolkit set up and pointed at your game
([`02-game-data.md`](02-game-data.md)), an image editor that saves PNG (GIMP, Krita,
Paint.NET, Photoshop…), and for the in-game check a Case Zero or Case West **recomp**.
On Xenia or a console, see [Going further](#going-further).

A *texture* is an image the game wraps around a 3D model: Chuck's shirt is a flat
picture of the shirt's fabric, folded around his body. You'll paint on it in your own
image editor; DR2 Studio turns each save into the game's own format.

## Steps

### In DR2 Studio

1. Start DR2 Studio. The **Welcome** window lists the first steps; its buttons do them:
   point Studio at your games (**Game folders…**) and **Build index** (about a minute,
   once). Close it when steps 1 and 2 have a ✔.
2. Pick the game in the **Game** box at the top (Case Zero).
3. Click the **Search** tab, type `young_cr_shirt` and press Enter. Click
   `…/npcs.big/chest_young_chuck.tex/young_cr_shirt_cm`. The middle shows the texture;
   the right says it is a 1024×1024 DXT1 texture, and the box at the top right says how
   to change it.
   (Case West: Chuck wears his IJIEK racing jacket there,
   `npcs.big/chest_default.tex/cr_jacket_cm`. Other outfits: [`asset-catalogue.md`](asset-catalogue.md).)
   *Tip:* the end of the name tells you what kind of texture it is: `_cm` is the colour
   map, the one to edit for colours. `_nm` (normal map) and `_sm` (specular) hold shading
   data and look strange on purpose.
4. Click **Edit in image editor…**. No mod open yet? Studio asks for a name (type
   `Green shirt`) and makes the mod for you. Then the texture opens in your image editor
   (the program your computer opens PNG files with; another one can be chosen in
   **Game folders…**).
5. Change the colours: a hue shift, a tint, painting on it, anything. **Keep the size
   exactly 1024×1024** and **save** (as PNG, same file). Each time you save, Studio puts
   the picture in your mod and shows it in the middle as the game will get it; the
   mod's list at the bottom shows `texture  data/models/npcs.big/chest_young_chuck.tex/young_cr_shirt_cm`.
   (Already have an edited PNG? Drop it on the Studio window instead.)
6. Click **▶ Play** in the toolbar. Studio puts your mod into the game (the log says
   which game file was rebuilt) and starts the recomp. Load a game where Chuck wears his
   default outfit.

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
# or: dr2 mod link green_shirt && dr2 play -g cz   (deploys every switched-on mod, starts the game)
```

The folder layout under `replace/` is the asset's **virtual path** plus `.png`: that is
how the toolkit knows which texture your PNG replaces.

## Check it worked

- **Without the game first** (phase 10): when your mod is switched on in the mod
  library (a mod you create or open in DR2 Studio is), Studio shows every asset **with
  your mods**: the texture view, the 3D view, the Library (a ✎ before what a mod
  changes) and the Maps tab. It is the exact texture the game will get (compressed and
  tiled as Play does it). Press **Ctrl+M** (or the toolbar's *With my mods* button) to
  flip between your version and the original; the 3D view keeps its camera, so it is a
  side-by-side in time. Saving the PNG again redraws it within a second.
- In game, Chuck's shirt has your colours.
- The recomp's log has one line per file it loaded from your mod:
  `VFS: 'game:\data\models\npcs.big' served from the MODS overlay -> …/game_mods/…`.
- To compare with the original, start the recomp with mods switched off:
  `CZ_NO_MODS=1` (Case West: `CW_NO_MODS=1`). The shirt is back to normal; nothing
  else changed.

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| `The picture is 512×512; this texture needs exactly 1024×1024` | The PNG was resized | Resize it back to the size the error names. Changing texture sizes comes in a later version. |
| `no asset '…' in cz` | A typo in the folder path under `replace/`, or the texture only exists in the other game | Copy the path from DR2 Studio's details panel. Set `games = ["cz"]` in `mod.toml` if the mod is for one game. |
| The colour doesn't change in game | The outfit you see isn't the one you edited (Chuck has many outfits, each with its own textures; Case Zero ships the DR2 jacket too, unused at the start) | Find the outfit's model (`chest_…` in `npcs.big`), then `dr2 index textures-of` it, or check [`asset-catalogue.md`](asset-catalogue.md). |
| **Play** says `no recomp program found` | Studio can't find the recomp's program | **Game folders…** → the recomp program row → **Choose…** (`cz_runtime`, `cz_runtime.exe` or the recomp's AppImage). |
| Nothing happens after saving in the editor | The editor saved a new file elsewhere (Save As) | Save over the same file (Studio says its path in the log), or drop the new file on Studio. |
| No `MODS overlay` line in the log | The recomp is older than this feature, or `CZ_NO_MODS` is set | Update the recomp; unset the variable. |
| Colours look blocky at the edges of what you painted | DXT1 compression stores each 4×4 pixel block with only 4 colours | That's how the game stores it; soft gradients and large flat areas look best. |

More in [`12-troubleshooting.md`](12-troubleshooting.md).

## Going further

- Undo: **Remove mods from game** in DR2 Studio (or `dr2 mod undeploy -g cz`); **Play
  without mods** starts the game without them, without removing anything. The status
  line at the bottom right always says what is in the game.
- Share it: **Share…** at the bottom (name, picture, readme, then one `.dr2mod` file):
  [`06-mod-packages.md`](06-mod-packages.md#sharing-a-mod).
- For Xenia or a real console, build the patched files into a folder instead:
  `dr2 mod build green_shirt -g cz -o out` (or `dr2 mod deploy … --to out`), then replace
  the game's own file with `out/data/models/npcs.big` (keep a backup of the original).
- What a mod folder holds, `mod.toml`, several mods at once: [`06-mod-packages.md`](06-mod-packages.md).
- Finding other textures: [`03-browsing.md`](03-browsing.md), [`asset-catalogue.md`](asset-catalogue.md).
- How it works inside: [`../formats.md`](../formats.md) §Textures.

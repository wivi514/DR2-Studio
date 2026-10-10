# Find assets: browse, search, and see which textures a model uses

**You will:** build the asset index, find any texture by name, see it, and find out
which models use it (and which textures a model uses).   **Time:** ~10 min.
**Games:** both.   **You need:** the toolkit pointed at your game
([`02-game-data.md`](02-game-data.md)). To hear sounds: PyAV (`pip install av`).

> **Looking for something by what it is?** The **Library** tab (Studio opens on it)
> lists characters, zombies, music, rigs… with pictures, and exports whole groups:
> [`16-library.md`](16-library.md). This guide covers the **Files** tree and **Search**,
> for finding anything by its name or place.

> Sounds: click any `.xma` to see its waveform and **Play** it; the Related list shows
> the `.sfx` and game events that play it. Details in [`10-audio.md`](10-audio.md).

The games hold about 125,000 (Case Zero) and 172,000 (Case West) files, most of them
inside archives inside archives. The **index** is the toolkit's catalogue of all of them,
with a small picture of every texture. It is built once and refreshed when the game
files change.

## Steps

### In DR2 Studio

1. Start it: `dr2 studio`.
2. Choose the game in the **Game** box, then click **Build / refresh index**. The first
   time takes a few minutes per game (it also draws a picture of every model); later
   refreshes re-read only files that changed.
3. **Files** tab: the game's folders and archives. Click ▸ to open an archive; nested
   archives open the same way. Compressed entries say "(compressed)": the toolkit
   unpacks them for you.
4. **Search** tab: type words and press Enter. All words must appear in the name:
   `young shirt`, `apron _cm`. `*` and `?` are wildcards (`z_*_cm`). A word with a `/`
   searches the whole path (`npcs.big/ _cm` = colour maps inside `npcs.big`). The box
   next to it filters by kind: texture, model, skeleton, audio, text….
   **Grid** shows texture and model results as a wall of pictures.
5. Click a result. A texture appears in the middle: scroll to zoom, drag to move.
   - **Show**: `RGBA` (transparency over a checkerboard), `RGB`, or one channel as grey.
     Normal maps (`_nm`) store their direction in R and G; masks (`_mask`) and
     transparency live in single channels.
   - **mip**: the smaller copies the game uses at a distance. **face**: the six sides of
     a cube map (reflections, skies).
6. The **Related** list on the right:
   - for a texture: the models that use it (*used by*), and identical copies stored
     elsewhere (*same bytes*). The same texture is often shipped in several archives.
   - for a model (`.big` with geometry): every texture its materials name, slot by slot.
   Double-click a line to go there.
7. A **model or skeleton** appears in 3D in the middle: drag to turn it, right-drag to
   move, scroll to zoom; **Skeleton** and **Wireframe** show the bones and triangles.
   Details on the right list its bones, meshes, draws and shaders. Saving it for Blender:
   [`04-extracting.md`](04-extracting.md).

### With the `dr2` command

```
dr2 index build                         # both games; add --full to re-read everything
dr2 index search young shirt -g cz --kind texture
dr2 index used-by data/models/npcs.big/chest_young_chuck.tex/young_cr_shirt_cm -g cz
dr2 index textures-of data/models/npcs.big/chest_young_chuck.big -g cz
dr2 index stats                         # how many assets of each kind
dr2 info data/models/npcs.big/chest_young_chuck.tex/young_cr_shirt_cm   # texture details
```

## Check it worked

`dr2 index stats` lists thousands of assets per kind for each game you indexed, and a
search for `_cm` finds colour textures.

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| The tree is empty | The game isn't indexed yet | **Build / refresh index** (or `dr2 index build`). |
| "The index may be out of date" when clicking | Game files changed since the index was built | Rebuild the index. |
| A search finds nothing | Words must all be in the *name* | Use fewer words, or `*`. Put a `/` in a word to search paths. |
| The texture looks like a rainbow or purple | It's a normal map or a mask, not a colour map | That's what they look like. The colour map is the `_cm` one. |

## Going further

- Exporting textures as PNG: [`04-extracting.md`](04-extracting.md).
- Changing one: [`05-first-mod-texture.md`](05-first-mod-texture.md).
- Where things are: [`asset-catalogue.md`](asset-catalogue.md).
- The index's tables, for people who want to query it directly with SQLite:
  `dr2kit/index/schema.sql`. Its location: `dr2 index build` prints it.

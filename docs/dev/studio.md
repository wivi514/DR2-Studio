# DR2 Studio: how it is built

DR2 Studio is the graphical front end (PySide6). Like the `dr2` command it holds **no
format knowledge**: it asks `dr2kit` for pixels, bytes and index rows and shows them.
Start it with `dr2 studio` (or `python -m dr2kit studio`). Install the GUI extras with
`pip install -e ".[studio]"`.

## Modules

```
dr2kit/studio/
  app.py       MainWindow: toolbar, browse/search tabs, centre viewers, details, mod bar
  viewers.py   TextureViewer (zoom, channels, mip, face), PlainViewer (text / hex)
```

## The window

```
┌ Game [Case Zero ▾]  Build / refresh index ───────────────────────────────────────┐
│ ┌ Browse | Search ─┐ ┌ Show [RGBA▾] mip [0] face [0] Zoom [fit▾] ┐ ┌ Details ───┐ │
│ │ data/            │ │                                            │ │ name, size │ │
│ │  models/         │ │           texture / text / hex             │ │ format...  │ │
│ │   npcs.big ▸     │ │                                            │ ├ Related ───┤ │
│ │    hero.tex ▸    │ │                                            │ │ used by... │ │
│ └──────────────────┘ └────────────────────────────────────────────┘ │ [Extract…] │ │
│                                                                      │ [Export…]  │ │
│                                                                      │ [Replace…] │ │
├ Mod: Red jacket (red)  [Open mod…][New mod…][Build && deploy][Undeploy] ──────────┤
│ mod's files                  │ log                                                │
└──────────────────────────────────────────────────────────────────────────────────┘
```

- **Browse** is a `QStandardItemModel` filled lazily. The top levels (folders and files
  on disk) come from `query.files()`; an archive gets a placeholder child and is filled
  from `query.children()` when expanded, so opening the tree costs nothing even with
  170k entries.
- **Search** runs `query.search()` (words, `*`/`?`, `/` for vpath matches) for the
  current game and kind; texture rows show the thumbnail stored in the index. **Grid**
  switches the list to an icon grid.
- **Viewers**: `TextureViewer` decodes with `convert.texture.decode_level` (the same
  call as `dr2 extract --png`), shows it in a `QGraphicsView` with nearest-neighbour
  scaling (so texels stay sharp), and can show one channel as grey: useful for normal
  maps (R/G), masks and alpha.
- **Related**: for a texture, the models whose `MatTextureInfoArray` names it
  (`query.used_by`) and identical copies elsewhere (`query.same_content`); for a model,
  its textures slot by slot (`query.textures_of`). Double-click jumps there.
- **Actions**: *Extract…* writes the asset's bytes (decompressed); *Export PNG…* the
  texture as PNG; *Replace with PNG…* checks the PNG's size and copies it to
  `<mod>/replace/<vpath>.png`.
- **Mod bar**: *Open mod…* / *New mod…* select a mod folder (`mods.manifest`); *Build &&
  deploy* runs `mods.build.build` + `mods.deploy.deploy` into the recomp's
  `game_mods/` (on top of `game_patched`), the same as `dr2 mod deploy`.

## Threads and the index

Building the index and building a mod run in a `QThread` (`Job`); they report lines to
the log through a signal, so the window stays responsive. The index is opened in WAL
mode (`index/build.connect`), so the window keeps reading while a build writes.
Asset bytes always come from the game files (`AssetTree`), never from the index: the
index can be out of date, the files can't. If a vpath from the index no longer
resolves, Studio says to rebuild the index.

## Testing

`QT_QPA_PLATFORM=offscreen` runs the window without a display. A smoke test opens the
window on a synthetic index (`tests/test_studio.py`, skipped when PySide6 is missing).
Grabbing the window to a PNG (`window.grab().save(...)`) is how the screenshots in the
guides are made.

## Next (later phases)

Audio playback (phase 5), the 3D model view (phase 3, `QWebEngineView` + three.js on
the exported `.glb`), editing text assets as mod overrides.

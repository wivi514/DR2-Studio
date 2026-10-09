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
  model_view.py  ModelViewer: the 3D view (QWebEngineView + three.js), phase 3
  web/         viewer.html + viewer.js, and three.js 0.186.1 (MIT) under vendor/three/
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
  `<mod>/replace/<vpath>.png`; *Replace with .glb…* (models, phase 4) runs the rig
  validator (`model_import.plan_import`) on a `.glb`, shows the report in the log (and a
  dialog on errors), and copies the file to `<mod>/replace/<vpath>.glb` when it passes,
  or just reports when no mod is open.
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

## The 3D view (phase 3)

Clicking a model or skeleton exports it to `.glb` in a worker thread
(`convert.gltf.model_to_glb`, textures through `convert.model.TextureFinder` with the
index), then `ModelViewer.show_glb()` hands the bytes to the page. Same file as
`dr2 extract --glb`, so the preview shows exactly what Blender will get.

- **Serving the page.** A custom `dr2:` URL scheme (`register_scheme()`, called when
  `app.py` is imported because Qt requires it before the `QApplication` exists) is
  answered by a `QWebEngineUrlSchemeHandler`: `dr2://studio/viewer.html` and the
  vendored three.js from `web/`, and `dr2://studio/model.glb` from memory. Not `file://`,
  because Chromium refuses ES modules there; the scheme needs the `FetchApiAllowed` flag
  (Qt 6.6+) for three.js's `fetch()`. One off-the-record profile is shared and parented
  to the application so it outlives every page.
- **Talking to it.** Python calls `window.dr2.load(url)`, `setSkeleton`, `setWireframe`,
  `resetView` with `runJavaScript`; the page answers with console lines starting `dr2:`
  (`ready`, then "N draws, N triangles, N bones" or an error), shown in the log.
- **Skeleton files** have no mesh: the page always draws their bones and frames them by
  bone positions.
- **No WebEngine** (missing add-on, or `DR2_STUDIO_NO_3D=1`): the pane says so and
  *Export .glb…* still works.
- **Threads.** `run_job` now delivers `on_done` through `_Relay`, a QObject living in
  the GUI thread. Before, `on_done` ran in the worker thread (a signal connected to a
  lambda runs where it is emitted); text widgets put up with it, Chromium aborts.

## Testing

`QT_QPA_PLATFORM=offscreen` runs the window without a display. A smoke test opens the
window on a synthetic index (`tests/test_studio.py`, skipped when PySide6 is missing),
shows a texture, a text file and a synthetic model (with `DR2_STUDIO_NO_3D=1`, so CI
needs no WebEngine), and checks the `dr2:` scheme serves only `web/` files. The 3D view
itself was checked offscreen too (WebGL works there through software rendering):
`window.grab()` after the page reports the model.
Grabbing the window to a PNG (`window.grab().save(...)`) is how the screenshots in the
guides are made.

## Next (later phases)

Audio playback (phase 5), editing text assets as mod overrides, and showing the
replaced model in the 3D view before building (the rig validator and *Replace with
.glb…* came in phase 4).

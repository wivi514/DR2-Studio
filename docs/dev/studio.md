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
  audio_view.py  AudioViewer: waveform, play / stop / seek / loop (QAudioSink), phase 5
  text_view.py   TextEditor (edit text into the mod, diff), StringsViewer (string banks), phase 6
  video_view.py  VideoViewer: Bink movies (pictures + sound), phase 6
  mod_manager.py ModManager: the mod library window (order, on/off, conflicts, deploy), phase 6
  setup_dialog.py GameSetup: "Game folders…" (folders, unpack, the programs Studio starts), phases 6-7
  help_view.py   HelpWindow: the modding guides inside the app, searchable (phase 7)
  welcome.py     Welcome: the first steps as a live checklist (phase 7)
  edit_tools.py  TextureEdit (image editor + re-import on save), open_in_blender (phase 7)
  share_dialog.py ShareDialog (details, preview, check, .dr2mod), InstallDialog (phase 7)
  library_view.py LibraryView: the Library tab, by category, with export (phase 8)
  maps_view.py   MapsList + MapsView: the Maps tab, levels in 3D (phase 10)
  icon/        dr2studio.svg, the app icon (our own drawing; dev/packaging.md §The icon)
  web/         viewer.html + viewer.js (3D view), maps.html + maps.js (Maps tab),
               levelmaterials.js (lightmaps, blends: both pages), three.js 0.186.1 (MIT)
               under vendor/three/
```

## The window

```
┌ Game [Case Zero ▾]  Build / refresh index  Mod manager… ─────────────────────────┐
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
index, colours from shader constants baked by `TextureFinder.baker` /
`convert.material`), then `ModelViewer.show_glb()` hands the bytes to the page. Same file as
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

## The audio view (phase 5)

Clicking a sound (`kind` audio) reads its format (`convert.audio.AudioLookup`: RIFF
header or `cache.big` stream table), lists the details (channels, rate, shape, loop) and
the Related rows (`query.sound_users`: the `.sfx` that use it, the scene-script events
with their trigger names), then decodes it in a worker thread
(`convert.audio.decode`, the same call as `dr2 extract --wav`) and hands the `Pcm` to
`AudioViewer.show_sound()`.

- **Waveform**: min/max per pixel column per channel (`envelope`, numpy), one lane per
  channel labelled L/R or L R C LFE Ls Rs, the loop region shaded, a play head. Clicking
  seeks and plays from there.
- **Playback**: `QAudioSink` reading 16-bit PCM from a `QBuffer`; the head follows
  `processedUSecs()` on a 30 ms timer. 5.1 is mixed to stereo for listening
  (`playback_bytes`: front + 0.7 × centre and surround). *Loop* restarts at the loop
  start when the end (or the loop end) is reached. No output device or no Qt Multimedia:
  the waveform still shows and the view says so.
- **Actions**: *Export WAV…*; *Replace with audio…* copies a WAV/OGG/FLAC/MP3 into
  `<mod>/replace/<vpath>.<ext>` (one per sound: another extension is removed). The build
  fits it (`mods/audio.py`).
- A `.sfx`, and a scene script, show as text with Related rows for what they play
  (`query.sound_targets`) and, for a `.sfx`, which events or parent effects use it.
- Without PyAV the view says how to install it; everything else works.

## Text, strings and movies (phase 6)

- **Text** (kinds `text` and `sfx`): `TextEditor` shows the game's text, or the open
  mod's copy when it has one (`replace/<vpath>`). With a mod open it is editable; *Save
  to mod* writes the whole file there (bytes ↔ text through Latin-1, line ends written
  back as the original's `\r\n` or `\n`; saving the game's own text removes the
  override), *Changes* shows `difflib`'s unified diff in colour, *Revert to the game's*
  deletes the mod's copy. A file in the profile's `digest_checked` opens read-only with
  the reason. Audio scene scripts keep their Related rows.
- **Strings** (kind `strings`, a `.bcs`): `StringsViewer`, a `QTableWidget` of id,
  label (from `str_id.bcs`) and text, with a filter over all three. With a mod open the
  text column is editable; each edit calls back into the window, which writes
  `replace/data/frontend/str_<lang>.bcs.json` (`convert.strings.set_mod_strings`) and
  shows `bcs.apply`'s notes under the table. Changed rows are highlighted, with the
  game's text as tooltip; *Revert string* puts the game's text back (and drops the
  change).
- **Movies** (kind `video`, Case West's `.bik`): the sound is decoded in a worker thread
  (`convert.video.audio`), then `VideoViewer` decodes pictures on the GUI thread as the
  clock reaches them (`convert.video.frames`), skipping pictures when behind. The clock
  is the `QAudioSink`'s position while sound plays, an elapsed timer otherwise. *Loop*
  is on by default for the monitor loops. *Export MP4…* runs `convert.video.to_mp4` in a
  worker.

## The mod manager (phase 6)

**Mod manager…** in the toolbar opens `ModManager`, a window over the same library as
`dr2 mod list` (`mods.library.ModLibrary`): mods in load order (the bottom wins), a
check box per mod (`enable`), *Up* / *Down* (`move`), *Install folder…* / *Install
.zip…* (`install`; an already installed id asks to update), *Remove*, *Pack .zip…*,
*Edit in Studio* (makes it the open mod of the main window), *Conflicts* (runs
`ModLibrary.plan` for the main window's game in a worker; lists what each mod wins over)
and *Deploy* (`MainWindow.deploy_mods` with the switched-on mods, the same job as
*Build && deploy* in the mod bar). *Library folder…* changes the folder
(`set_default_library`, saved in the user config).

## Game folders (phase 6)

A release (or a pip install) has no recomp next to it, so `profiles.locate` finds
nothing until told. **Game folders…** (`setup_dialog.GameSetup`) shows each game's
status (`game_status`: where, and found through which rule) and offers *Choose folder…*
(`profiles.set_game_root`, the `dr2 games set` setting) and *Unpack package…*
(`container.stfs.unpack` in a worker, then the same setting). The main window opens it
at start when no game is found (`DR2_STUDIO_NO_SETUP=1` skips that, for scripted runs).

## Phase 7: help inside, and the shortest path from idea to game

Phase 7's aim (user, 2026-10-09): modding as easy as possible, the documentation in the
app, easy packaging and installing.

- **Help** (`help_view.HelpWindow`, F1 / toolbar **Help**): the modding guides
  (`dr2kit.help`) in reading order, a search box over every line, the page rendered by
  `QTextBrowser` (GitHub-flavoured Markdown). Links between guides and `#section` links
  open in the window (the heading is scrolled to the top); web links open in the
  browser; developer docs open from the source checkout when it is there. **Back**.
- **How to mod this**: a box above Details with the context help for the selected
  asset's kind (`dr2kit.help.context`, `docs/modding/context.toml`) and **Open the
  guide**. The action buttons below show only what applies to that kind.
- **Errors** have a **Help** button: `help_for_error` picks the troubleshooting row (or
  guide table row) sharing the most words with the message. `DR2_STUDIO_NO_DIALOGS=1`
  sends errors to the log only (tests, scripted runs).
- **Welcome** (`welcome.Welcome`): five steps (game folders, index, new mod, change
  something, Play), each with its button and a ✔ computed from the real state; shown at
  start until unticked (`[studio] welcome = "off"`), and from the toolbar.
  `DR2_STUDIO_NO_SETUP=1` skips it.
- **The open mod lives in the library**: *New mod…* asks for a name and creates the mod
  inside the library (`ModLibrary.create`); *Open mod…* links an outside folder
  (`ModLibrary.link`), so **Play** always includes the mod being made. The mod's list at
  the bottom shows each change (kind, asset), marks problems with ⚠ from a background
  `plan_mods`, jumps to the asset on double-click, and **Delete** removes a change.
- **Editing in other programs** (`edit_tools`): *Edit in image editor…* writes the
  texture (or the mod's version of it) to the per-user `edits/` folder, opens it, and a
  `QFileSystemWatcher` (watching the file and its folder, debounced 600 ms) turns every
  save into the mod's PNG (size checked) and refreshes the view, which shows the mod's
  version encoded as the build will (`replace_image`). *Open in Blender* exports the
  model (or the mod's `.glb`) and starts Blender with a generated script that imports
  it into a collection tagged for the add-on and sets the add-on's mod folder. The
  script imports from a `bpy.app.timers` callback once Blender's window is up: run
  straight from `--python` in a windowed Blender, the glTF importer fails (`'Context'
  object has no attribute 'object'`) and leaves only its bone-shape Icosphere (user
  report, 2026-10-10; background runs don't show it, so the test runs the script in
  Blender and the windowed path was checked by hand). It passes `disable_bone_shape`
  (when the importer has it), so bones aren't drawn as spheres, and sets the 3D views
  to Material Preview so the textures show; the add-on's **Import** passes the same
  option.
- **Import textures…** (models): pictures exported by a texturing program (a folder,
  files, or a `.glb`) → `mods.texture_import.plan` in a worker, the plan in the log and
  a confirmation, then `apply` into the open mod.
- **Drag and drop** (`drop_file`): a `.dr2mod`/`.zip`/mod folder installs; a PNG on a
  texture, audio on a sound, a `.glb` on a model goes into the open mod; a folder or
  pictures dropped on a model go through *Import textures…*; any action
  that needs a mod offers *New mod…* first (`ensure_mod`).
- **Share / Install** (`share_dialog`): see its docstring; *Share…* writes `mod.toml`
  (`Mod.save`), `preview.png` (≤ 512 px) and `README.md`, checks each game in a worker,
  then `pack`s a `.dr2mod`. `dr2 studio file.dr2mod` (or a release's
  `DR2Studio file.dr2mod`) opens the Install window at start.
- **Play** (toolbar **▶ Play**, **Play without mods**; bottom bar **Deploy**, **Remove
  mods from game**): `mods.play` in a worker (build + deploy the switched-on mods), then
  the recomp is started detached. The status bar's right end says what is in the game
  (`play.deployed`), updated on game change and after each deploy.
- **Game folders…** also shows and sets the programs Studio starts: each game's recomp,
  Blender, the image editor.
- **Closing** waits for background jobs (`wait_for_jobs`, which keeps the event loop
  turning: a job's thread quits through a queued signal, so a plain `wait()` deadlocks).
  `closeEvent` isn't called for a never-shown window, so tests call `wait_for_jobs()`.

## The Library tab (phase 8)

Studio opens on **Library** (left, first tab; the archive tree is now **Files**).
`LibraryView` reads `query.library_counts` for a tree of sections → groups → sub-groups
(from `catalog/groups.toml`), and `query.library_items` for the selected one, shown in a
`QListView` backed by `LibraryModel`: pictures (`query.picture`: a model's render or a
texture's thumbnail, both stored in the index) are read only when an item is first
painted, so a group of 18,000 textures opens at once. A filter box narrows by label or
name; groups of models and textures default to the grid, others to a list.

Selecting an item calls the window's `show_asset`, as the other tabs do. For a model the
details add the Library place, the largest part and bone palette against the game's
limits, and the rig (`query.rigs_of`); the Related list shows the textures with their
pictures and roles, the rig, a sound bank with the same name, and identical copies
("also in"). For a skeleton it lists the models on that rig.

**Export…** (Library, for the selection or the whole group) and **Export all…** (right
panel, one model or skeleton) both go through `library_view.run_export`: the jobs are
planned in the GUI thread (`catalog.export.plan`), then `_ExportWorker` runs
`Exporter.run` in a `QThread` with its own index connection and `AssetTree`, reporting
each step to a `QProgressDialog` whose *Cancel* sets a `threading.Event` checked
between files. Results (and failures) go to the log; with `DR2_STUDIO_NO_DIALOGS` set
(tests) there is no dialog.

## The Maps tab (phase 10)

**Maps** is the second left tab (`MapsList`: levels, zones). Choosing it hands the centre
to `MapsView` and hides the right panel (the view has its own: item set, Layers, Go to,
what was clicked, *Open in Library / Blender*, *Export .glb…*, *How to use Maps*, *Copy
camera position*); leaving it gives back the viewer shown before.

The page (`web/maps.html`, `maps.js`) talks with `dr2:` console lines like the 3D view:
`ready`, `status`, `want {zone, part, detail, script}`, `pick {…}`, `camera {…}`; Python
calls `dr2.openLevel(meta)`, `zoneReady(zone, part, detail, url)`, `setLayer`, `goTo`,
`setView` (an exact camera: a recomp capture's), `pickAt(x, y)` and `reload()`. Every 0.3 s
the page works out which zones it wants at which detail (full size within 40 m of a
zone's bounds, small textures otherwise, backdrops over 300 m always small) and asks,
nearest first, three at a time. `MapsView` hands each request to one of three `_Builder`
threads (each with its own `MapCache` and `AssetTree`: the trees' archive caches are not
shared between threads), registers the built file with the scheme handler under a new
URL (`dr2://studio/maps/<n>-<file>`), and answers `zoneReady`. A level change bumps a
generation number; answers of an older generation are dropped. `_MapsPage` keeps the
page's own console errors (a shader that doesn't compile) in `errors`.

Checking it: a scratch driver opens the window in a real display, drives the page with
`dr2.goTo` / `setView` / `pickAt` and saves `view.grab()` pictures; for the gate, the
camera of a recomp capture (`c0`–`c3` of a vertex shader dump, row 1 divided by the
widescreen factor) goes into `setView` and the two pictures are compared.

## With my mods (phase 10)

`MainWindow.refresh_mods` builds a `mods.preview.Preview` of Play's mods for the game
(on a game switch, when the mod manager closes, and one second after a watched mod file
changes: `QFileSystemWatcher` on every library mod's folders and `replace/` files and the
library's `modlist.toml`). The toolbar's checkable **With my mods** (Ctrl+M; on by
default when a mod is on; remembered per game) picks the tree: `asset_tree()` (GUI
thread) and `worker_tree()` (a new one per worker) give a `ModdedTree` or the plain game;
`plain_tree()` is always the game (mod checks, texture import plans). Switching clears
the trees, gives the Maps view new trees (`MapsView.use_tree`), and shows the current
asset again keeping the 3D camera (`_keep_view_once`). The details say *changed by mod:
…*; the Library puts ✎ before changed items (`LibraryModel.changed_by`); the Maps
panel says *Changed by mod* for a clicked piece or item. The Library's pictures stay
the game's (they are in the index).

## Testing

`QT_QPA_PLATFORM=offscreen` runs the window without a display. A smoke test opens the
window on a synthetic index (`tests/test_studio.py`, skipped when PySide6 is missing),
shows a texture, a text file and a synthetic model (with `DR2_STUDIO_NO_3D=1`, so CI
needs no WebEngine), and checks the `dr2:` scheme serves only `web/` files. The audio
view is tested on a synthetic 5.1 `Pcm` (the stereo mix, the waveform envelope); delete
the widget (`deleteLater` + `processEvents`) before the test ends, or Qt Multimedia
aborts at interpreter exit ("shared QObject was deleted directly"). The 3D view
itself was checked offscreen too (WebGL works there through software rendering):
`window.grab()` after the page reports the model.
A Library test (phase 8) opens the window on a synthetic game with two characters and
a rig, checks it opens on the Library, filters a group, selects a model (rig and
textures in Related), and runs *Export all…* and a group *Export…* to the end.
A second test edits a text file (CRLF kept, diff, revert), changes a string through the
table, and switches a mod off in the mod manager, on a synthetic game.
Grabbing the window to a PNG (`window.grab().save(...)`) is how the screenshots in the
guides are made.
A Maps test (phase 10) opens the window on a synthetic level, checks the level list, the
centre and panel swap, *Go to*, a zone file built on request and a picked item's
description (the page's messages are fed in, since CI has no WebEngine).

## Next (later phases)

Showing the replaced model in the 3D view before building (the rig validator and
*Replace with .glb…* came in phase 4), playing a replacement sound next to the original
before building, and registering `.dr2mod` with the OS so a double-click opens Studio
(today: drop it on Studio, *Install mod…*, or `DR2Studio file.dr2mod`).

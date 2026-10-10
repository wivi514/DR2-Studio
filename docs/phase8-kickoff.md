# Phase 8 kickoff: find things by what they are, and take them out in one go

**Direction (user, 2026-10-09):** "make it easier to get stuff, like only show models
with their texture, bones and all, and can export all of this at once. Just show audio,
etc." Today DR2 Studio shows the game the way it is stored: folders, archives inside
archives, texture packs next to models, sounds in banks. A modder thinks in things:
*Chuck's shirt* (a model, its textures, its skeleton), *the title music*, *the zombie
groans*. Phase 8 shows the game that way and makes "give me all of it" one click.

Read `CLAUDE.md` first (documentation and clean-up rules), then `phase7-kickoff.md`
§Status (what phase 7 left owed), then this.

## Status at the end of 2026-10-09 (read this first)

**Done**, gate passed in both games (`dev/testing.md` §Phase 8 results):

- **Library tab** (Studio opens on it; the archive tree is **Files**): sections → groups →
  sub-groups from a rules file (`dr2kit/catalog/groups.toml`), with counts, descriptions,
  a filter, a grid of pictures loaded on demand; identical copies shown once ("also in…").
  `dr2 library [group]` and `dr2 library --check` (the count gate).
- **Model pictures**: 3D renders made while the index is built, by a numpy software
  renderer (`convert/render.py`: ~0.05 s a model; the index build went from ~1-2 to 3-4.5
  minutes per game). Measured first, as decided: the CLI builds the index too, so no Qt.
- **A model with everything it uses**: textures with pictures by role, the rig it
  matches (new relation `model-rig`, by bone names *and rest pose*: the rig families
  share their names), its counts against the game's limits, a sound bank with the same
  name, copies.
- **Export all**: one model (*Export all…*), a selection or a whole group (*Export…*), or
  `dr2 export <group|sub-group|section|vpath…>`: one folder per model (`.glb`,
  `textures/*.png` + `textures.txt`, `skeleton.glb`, `info.txt`), WAV, MP4, `.bcs.json`,
  PNG; progress, Cancel, resume (existing files skipped), `--wav/--png/--glb/--mp4/--json`.
- **Friendlier names**: characters by part and role ("Young Chuck (headwear)", "Archie
  (survivor)"), zombie variants, sound banks by what they are, single names from the
  asset catalogue.

**Fixed after the gate (2026-10-10, from the user testing Studio; `devlog.md` has each):**

- Model colours: zombie clothing baked in the pictures; glasses (`gLensColour`) and
  eyelashes / hair (`gDiffuseColourControl`) baked from their shaders; hair and
  opacity-map materials see-through (`.glb` `alphaMode`), cloth and skin opaque.
- Rigid parts (props, vehicles, level pieces: ~1,000 models) placed by their node in the
  `.glb`, the 3D view and the pictures; re-import still byte-identical for every model.
- Play: source builds of the recomps started without their renderer (`play_defaults`).
- Open in Blender: imported only an Icosphere in a windowed Blender (now imports from a
  timer); bones no longer drawn as spheres; opens in Material Preview. How to see
  textures and hide bones is in `07-blender-setup.md` and the model's "How to mod this".
- The renderer handles pictures bigger than 128 px.

**Not done / owed:**

1. **Voice lines with their subtitle**: not possible from the data found. The GASP tables
   link voice numbers to concepts named by hash only (2 of 41 resolved), and nothing links
   them to `IDS_SUBTITLE_*` (`formats.md` §Voice lines and the GASP tables). Voices are
   listed by number.
2. The gate as written is "from the Library"; it was driven by a script through Studio's
   own widgets, not clicked by a person.
3. "The sounds or text that mention a model when known": only a same-name `.sfx` bank is
   shown; no other link is known.
4. Environments export one piece per folder; a whole zone as one scene is not done
   (stretch: environment browsing).
5. Everything still owed from phase 7 (`phase7-kickoff.md` §Status).
6. **Striped faces** on Chuck's hat and mohawk heads (`formats.md` §Striped head
   textures): the shipped texture has the bands; how the game shows these heads is not
   known. Check in game (wear the mohawk) and, if the game binds another texture, show
   that one.
7. Play and Open in Blender were fixed from the user's tests, not re-run end to end by a
   gate script (Play: the environment was checked, the game not started by us).
8. **Release test builds (2026-10-10)**, waiting for the user's test: Linux in
   `build/release/` (AppImage, tar.zst), Windows unpacked at `C:\dr2kit\test3` on the build
   laptop (zip in `C:\dr2kit\src\build\release`). The first two Windows builds had no help
   and no three.js (both fixed, the gate now checks them, `dev/packaging.md`). After the
   user switches: delete `C:\dr2kit\test` and `test-new`; after testing, `build/release`.
   Not tried by us on Windows: Studio's GUI (Play, Open in Blender, the 3D view).

## What exists to build on

- The index (`dr2kit/index`): every asset with its kind (`model`, `texture`, `audio`,
  `skeleton`, `strings`, `text`, `video`…), texture thumbnails, model → texture links
  (`material-texture` relations, by slot), sound → `.sfx` / script-event links.
- Exports: `.glb` with textures embedded (`convert/model.export_glb`), skeleton `.glb`,
  PNG, WAV, MP4, strings JSON; Studio's Search tab filters by kind.
- Not there yet: a model → skeleton link (which rig a model uses), categories, friendly
  names, batch export.

## Scope

1. **Categories instead of folders.** A new first tab in Studio, **Library** (the
   archive tree stays as **Files**, for advanced use), with groups measured from the
   paths (2026-10-09):
   - *Models*: Characters (`models/npcs.big`: CZ 91, CW 166), Zombies
     (`models/zombies.big`), Weapons & items (`models/weapons`, `models/special`,
     `dynamicprops`), Cutscene props (`cine_props.big`), Crowd, Environments
     (`models/environment`, by area: ~930 / ~970);
   - *Sounds*: Music (`audio/music.big`), Voices (`charvocals`, `chuck`, `bossvocals`),
     Cutscene audio (`cinematics.big`), Sound effects (`streamedassets.big/fx_*`, by bank:
     footsteps, zombies, weapons, vehicles…), Ambience;
   - *Textures* (by role: colour, normal…), *Skeletons* (the rigs), *Text & strings*,
     *Movies* (CW).
   Each group a grid or list with thumbnails and a short description; identical copies
   (same bytes in several archives) shown once, with "also in…".
2. **A model shown with everything it uses.** Selecting a model shows, next to the 3D
   view: its **textures** (thumbnails, by role and material), the **skeleton/rig** it
   matches (new index link: model → rig by bone names), its parts and counts, and the
   sounds or text that mention it when known.
3. **Export everything at once.**
   - For one model: **Export all…** writes a folder: `<model>.glb` (meshes, skeleton,
     skin, textures embedded), `textures/*.png` (every texture, named as in the game,
     plus a note of which is colour/normal/specular), `skeleton.glb` (the rig alone),
     `info.txt` (paths, sizes, rig, limits), ready for Blender or Substance Painter.
   - For a selection or a whole group: the same for every item, sounds as WAV, movies as
     MP4, strings as JSON; a progress bar, *Cancel*, existing files skipped.
   - CLI: `dr2 export <group or vpath…> -o folder` (e.g. `dr2 export characters`,
     `dr2 export music --wav`).
4. **Friendlier names** where the data gives them: characters and outfits from the asset
   catalogue's table, sound-effect banks by what they are, voice lines with their
   subtitle when the GASP tables link them (carried over from phase 5).

## Decisions (user, 2026-10-09)

- **Model thumbnails: 3D renders**, made while the index is built (a few more minutes
  for the first build per game; Studio's 3D page rendered offscreen, or a small
  software renderer if that proves too slow: measure first).
- **Exports: one folder per asset** (`chest_young_chuck/` holding the `.glb`,
  `textures/*.png`, `skeleton.glb`, `info.txt`; sounds as `music/HB_Indemnify.wav`…).
- **Studio opens on the Library**; the archive tree stays as a **Files** tab.

## Gate

From the Library, without the Files tab: export one character with everything
(the `.glb` opens in Blender with textures and bones; the PNGs and rig are there), and a
whole group in one go (every sound of the music bank as WAV; every character as a
folder), in both games; every category count matches the index.

## Facts to keep in mind

- The index is a cache: a schema change bumps `SCHEMA_VERSION` and forces a rebuild.
- Big exports: characters ~1-7 MB each as `.glb`; environments are large (hundreds of
  them, tens of MB); the export must be cancellable and resumable.
- Tests use their own user folders (conftest); Studio dialogs are off in tests.
- Clean up after yourself (CLAUDE.md); recomp runs as in `dev/recomp-integration.md`.

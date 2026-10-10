# Phase 7 kickoff: the easiest possible modding, with the help inside the app

**Direction (user, 2026-10-09):** "make things the easiest to mod, and all include
documentation right in the app, make it easy to package a mod and to install it in
game, and all these kinds of stuff." So phase 7 is about the person using the toolkit,
not about new formats: someone who has never modded should go from "I want Chuck's
shirt red" to "it's red in my game", and share it, **without a terminal and without
leaving DR2 Studio to read docs**.

Read `CLAUDE.md` first (documentation rules, and the clean-up rule), then this. What
exists: `dev/code-tour.md`, `dev/studio.md`; what phase 6 learned: `devlog.md`.

## Status at the end of 2026-10-09 (read this first)

Done the same day (commits `f26d08f` icon, `5fba10e` phase 7, `db5fe94` texturing):

- **Help inside the app**: the guides are the help (`dr2kit/help`, packaged by
  `setup.py`), F1 window with search, "How to mod this" per asset kind
  (`docs/modding/context.toml`), Help button on errors, Welcome checklist, `dr2 help`.
- **Editing**: *Edit in image editor…* (re-import on save), *Open in Blender*, drag and
  drop, *Import textures…* for Substance Painter / Blender / any program
  (`mods/texture_import.py`), the mod's changes listed with problems marked.
- **Share / Install / Play**: `.dr2mod` packages (Share window with preview, readme and
  checks; Install window), **▶ Play** / Play without mods / Deploy / Remove mods from game
  (`mods/play.py`, `dr2 play`), deploy status in the status bar, mod sets, linked mods,
  new mods created in the library, Game folders also sets the recomp, Blender and
  image-editor programs.
- **Docs**: guides 01, 05, 06, 08-11, 13 rewritten for the new buttons; new guides
  `14-texturing-tools.md` and `15-limits.md`; `formats.md` §Texture conventions and
  §Engine limits, measured on both games (normal maps are OpenGL-style; 16-bit indices,
  65,536 vertices per character part; 61 bones per draw; 4 weights per vertex).
- **Gate, scripted in game** (`tools/newcomer_gate.py`): make → share → install on an
  empty library → Play shows the new title text and the red shirt (CZ) / jacket (CW).

Still owed:

1. **The gate by a person**: someone new follows only the in-app help on a clean
   profile, without a terminal, in both games.
2. Follow `14-texturing-tools.md` in Substance Painter itself (tested only with
   Painter-style files).
3. `.dr2mod` file associations (double-click opens Studio) in the release packages.
4. The "Carried over" list below (first release on all OSes needs the GitHub remote).
5. Unknown: what each channel of `_mask` and the lighting maps (`_si`, `_rm`, `_om`) means.

## Where we started (what was hard before phase 7)

- The guides are Markdown files in `docs/modding/`, outside the app; a release copies
  them into a `docs/` folder nobody opens.
- Making a change takes several separate steps: export, edit elsewhere, "Replace with…",
  remember to build, deploy, start the recomp. Nothing tells you what to do next.
- A mod is a bare folder; sharing it means `dr2 mod pack` or the mod manager's *Pack
  .zip…*, with no name/description/preview prompts, and nothing checks it is complete.
- Installing someone's mod: mod manager → *Install .zip…* → *Deploy*, then start the
  recomp yourself. No "play with these mods" button; no view of what is installed in
  the game right now.
- Error messages are precise but written for people who know the vocabulary.

## Scope

1. **Help inside the app.**
   - A **Help** pane/window in DR2 Studio that shows the modding guides, rendered
     (Qt shows Markdown natively), searchable, with working links between them. The
     guides ship inside the package (package data), so the CLI, Studio and releases
     always carry the same version.
   - **Context help:** for the selected asset, a short "How to mod this" box (texture /
     model / sound / strings / text / movie) with the steps and buttons that do them, and
     a link to the full guide.
   - **First start:** a welcome screen that walks through game folders → index → "make
     your first mod" (the texture guide as an interactive checklist).
   - Every error the user can hit says what to do in plain words and links to the help
     section that explains it (the troubleshooting tables become help pages).
   - `dr2 help [topic]` prints the same guides in a terminal.
2. **Easiest editing loop.**
   - **Edit in…** for textures: export to a work folder, open in the user's image editor,
     and re-import automatically when the file is saved (watch the file), with the
     result shown in Studio; size problems explained before anything is written.
   - **Open in Blender** for models: start Blender with the add-on and the model loaded
     (the add-on's *Export to mod* already writes back).
   - Drag and drop: drop a PNG / audio file / `.glb` on an asset to replace it.
   - The open mod as a list with thumbnails, kind and status (ok / problem), revert per
     item, and checks run as you go (no surprise at build time).
3. **Packaging a mod to share.**
   - A **Share mod…** wizard: name, author, version, description, games, a preview
     picture (screenshot or a texture), a readme; checks the mod against each game it
     claims; writes one file to share.
   - A single-file mod package (decide: a `.zip` with a `.dr2mod` name or plain `.zip`)
     that carries `mod.toml`, `replace/`, preview and readme, and never game data.
4. **Installing and playing.**
   - Open / double-click / drag a mod package onto Studio to install it (mod manager),
     with its preview, description and what it changes.
   - **Play**: deploy the switched-on mods and start the recomp in one click (find the
     recomp's executable next to its game folder); **Play without mods**.
   - Always visible: what is deployed in each game right now; **Uninstall from game**.
   - Updating a mod keeps its place and switch (exists), with a "what changed" list.
   - Mod sets (profiles): save and switch between lists of switched-on mods.
5. **An icon for the app** (user, 2026-10-09): our own art, no game logo or Capcom
   artwork; used for the window, the executables (Windows `.ico`, macOS `.icns`), the
   AppImage and desktop file, and the Blender add-on's docs.
6. **The docs side** (documentation rules apply as always): the guides rewritten so each
   one is also good as in-app help (short steps first, details after), screenshots of
   our own UI where they help (no game art), and a "Help" section in `dev/studio.md`.

## Carried over (smaller, do when they fit)

- First release on Windows/macOS: needs the GitHub remote; the release workflow has
  never run (`dev/packaging.md`).
- In-game gates still owed: a Case West model replacement, the add-on's output, a 5.1
  cinematic and an fx-bank sound, a text-file mod.
- Mod features: zombie-clothing colours (value-set overrides), sounds longer than the
  original, string mods that keep the recomps' keyboard prompts, voice-line names.

## Gate

A person who has never used the toolkit, starting from the release (or a fresh install)
and reading only the help inside DR2 Studio, makes a texture mod and a text mod, sees
both in game, packages them, and installs the package on a second setup, **without a
terminal**. Checked by following the in-app help step by step on a clean user profile,
in both games; every step's screen matches what the help says.

## Decisions (user, 2026-10-09)

- **Play button: yes.** DR2 Studio deploys the switched-on mods and starts the recomp
  (found next to its game folder, or picked once); also *Play without mods*.
- **Mod package: `.dr2mod`**, a zip with our own extension (Studio and `dr2` also accept
  `.zip`).
- **Help language: English, laid out for translations** (one folder per language, the
  English one being `docs/modding/`), so a translation is files, not code.

## Facts to keep in mind

- Headless recomp runs: `pgrep -x cz_runtime` first, `CZ_BUG_REPORTS=0`, a copy of the
  save, `timeout -s KILL`; frame dumps go to `~/.cache/…`, never `/tmp`; undeploy and
  remove the empty `game_mods/` afterwards (`dev/recomp-integration.md`).
- An installed toolkit doesn't find the sibling recomps by itself (Game folders).
- Licences: the Blender add-on is GPL and must never include dr2kit; releases must never
  bundle a GPL library.
- Files the games digest-check can't be modded (profiles' `digest_checked`).

## Test data policy (unchanged)

Unit tests build synthetic data in code. Game-data tests skip with a message when a game
is absent. No game data, exports or captures in the repository.

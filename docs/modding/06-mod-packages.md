# Mod packages: what's in a mod folder, building, sharing

**You will:** understand a mod folder, write its `mod.toml`, run several mods at once
with the mod manager, and share a mod without sharing game files.   **Time:** ~10 min to read.   **Games:** both.
**You need:** a mod made as in [`05-first-mod-texture.md`](05-first-mod-texture.md).

## What a mod is

A mod is a **folder** of files you made, plus a small text file describing it:

```
red_jacket/
  mod.toml
  replace/
    data/models/npcs.big/chest_default.tex/cr_jacket_cm.png
    data/datafile.big/zombie_effects.txt
```

Everything under `replace/` mirrors the game's **virtual paths** (the address of an
asset inside the archives, see the [glossary](../glossary.md)):

| File under `replace/` | What it does |
|---|---|
| `<texture's vpath>.png` | Replaces that texture. Same size as the original (the error tells you the size). |
| `<model's vpath>.glb` | Puts the meshes of a `.glb` you edited in Blender into that model (`…/npcs.big/chest_young_chuck.big.glb`). Each object replaces the part with the same name; the rest of the model stays as it was. The model check runs first ([`08-edit-a-model.md`](08-edit-a-model.md)). |
| `<sound's vpath>.wav` (or `.ogg`, `.flac`, `.mp3`) | The recomp plays your audio instead of that sound (`…/music.big/PressStartPrologue.xma.ogg`). Fitted to the sound's length, channels and rate; recomps only ([`10-audio.md`](10-audio.md)). |
| `<string bank's vpath>.json` | Changes only the strings it lists, by id or label (`…/frontend/str_en.bcs.json`). Several mods can change one bank ([`11-text.md`](11-text.md)). |
| `<any asset's vpath>` (no `.png` / `.glb` added) | Replaces that asset with your file's bytes, as they are. For text files (`.txt`, `.csv`) and anything you edited with another tool. A few files can't be replaced: the game checks them and crashes on a changed copy ([`11-text.md`](11-text.md#files-you-cant-change)). |

| `<level text file's vpath>.edits.json` | Changes only the blocks it names in a level or mission file (`…/datafile.big/prologue.txt.edits.json`); several mods can change one file ([`19-edit-a-level.md`](19-edit-a-level.md)). |
| `<zone>.big/ZONE_ORGANIZATION.big.pieces.json`, `<zone>.big/MERGED_COLLISION.big.pieces.json` | Hide, move, turn, resize and copy a zone's buildings, and move or hide their collision; several mods can change one zone, by building ([`19-edit-a-level.md`](19-edit-a-level.md)). |

**New files** go under `add/` instead of `replace/`: `add/<archive's vpath>/<new name>`
puts a new entry into that archive. A new item's model pack is
`add/data/streamedassets.big/MyItem.big.copy.json`, a *recipe* that copies another item's
pack from the player's game when the mod is built; your own `.glb` and PNGs for it sit in
`sources/` ([`19-edit-a-level.md`](19-edit-a-level.md#steps-an-item-of-your-own-your-own-model)).

Letter case doesn't matter (`DATA/Models/…` works). A mod only ever holds **your** files:
no game archives, nothing copied from the game. That's what makes it safe to share.

## `mod.toml`

`dr2 mod new <folder>` (or **New mod…** in DR2 Studio) writes this, with comments:

```toml
[mod]
id = "red_jacket"           # lower-case letters, digits, _ . -
name = "Red jacket"
version = "1.0.0"
games = ["cz", "cw"]        # which games it is for
author = "you"
description = "Chuck's default jacket in red."
priority = 0                # higher wins when two mods replace the same asset
```

- **games**: a mod is checked against each game listed. If a path exists in only one
  game (Case West has many textures Case Zero lacks), list only that game.
- **priority**: when two mods replace the *same* asset, the one with the higher number
  wins. At equal priority the toolkit refuses to guess and tells you which mods clash.
  Once a mod is installed in the mod manager, its place in the load order decides
  instead (below); `priority` only says where it lands when installed.
- **local_only** (optional): `local_only = true` marks a mod that holds files from
  another game (a model or effect brought in for yourself,
  [`22-from-other-games.md`](22-from-other-games.md)). It builds and plays, but
  **Share…** and `dr2 mod pack` refuse it.

## Play, deploy, remove

| DR2 Studio | Command | What happens |
|---|---|---|
| (automatic: the mod's list marks problems with ⚠) | `dr2 mod check MOD -g cz` | Checks every file: does the asset exist, is the PNG the right size, does each `.glb` pass the model check, do mods clash. Writes nothing. |
| **▶ Play** (toolbar) | `dr2 play -g cz` | Builds every switched-on mod of your library, copies the result into the recomp's `assets/game_mods/` folder, and starts the recomp. |
| **Deploy** (bottom bar) | `dr2 play -g cz --deploy-only`, or `dr2 mod deploy MOD [MOD…] -g cz` | The same without starting the game. |
| **Play without mods** | `dr2 play -g cz --no-mods` | Starts the recomp with mods switched off for that run (nothing is removed). |
| **Remove mods from game** | `dr2 mod undeploy -g cz` | Removes exactly the files the last deploy wrote. Files you put there yourself stay. |
| status line, bottom right | `dr2 mod status` | Which mods are in each game now, and since when. |
| — | `dr2 mod build MOD [MOD…] -g cz -o OUT` | Builds into the folder `OUT` (laid out like the game: `OUT/data/…`). For Xenia or a console. |

Studio finds the recomp's program next to its game folder (a release has it beside
`assets/`, a source build under `runtime/build`); if it can't, choose it in **Game
folders…** (or `dr2 games set-recomp cz <file>`).

Building rewrites whole game files. A texture three archives deep means rewriting the
`.big` file on disk that holds it, so one small PNG can produce a 100 MB file. The
toolkit:

- re-compresses every entry that was compressed in the original (the game crashes on
  uncompressed replacements),
- keeps every untouched entry byte for byte,
- reads every replaced asset back from the result before writing anything, and stops
  if one doesn't match.

**Several mods at once:** give them all to one command
(`dr2 mod deploy red_jacket blue_pants -g cz`). They are combined into one build, so two
mods that touch different textures in the same archive both apply. Deploying again
replaces the previous deploy, so always deploy the whole set you want.

**Recomp patches are kept.** The recomps ship some game files already patched (the PC
options menu, translations), in `assets/game_patched/`. When your mod touches one of
those files, the toolkit builds on the recomp's patched copy, so you keep both. If a
recomp option layer (`game_kbm`, keyboard prompts; `game_bootskip`, skip intro logos)
carries the same file, deploy prints a warning: while your mod is installed, its copy
is used.

## Several mods: the mod manager

The **mod library** is a folder where your installed mods live, with their **load
order** and an on/off switch for each. Mods later in the order win when two change the
same texture, model, sound or string. Deploying deploys every switched-on mod at once.

### In DR2 Studio

1. Click **Mod manager…** in the toolbar. The window lists the library's mods in load
   order (the folder is shown at the top; **Library folder…** changes it).
2. **Install mod file…** (a `.dr2mod` or `.zip`) shows the mod first (picture, readme,
   what it changes), then copies it in, switched on; **Install folder…** does the same
   for a folder; **Link folder…** adds a folder that stays where it is (a mod you are
   making: Studio links the mod you open or create automatically). A mod already
   installed asks whether to update it (it keeps its place and switch).
3. Tick or untick a mod to switch it on or off; **Up** / **Down** move the selected mod.
   Lower in the list = wins.
4. **Conflicts** lists, for the game picked in the main window, everything two
   switched-on mods both change and which one wins:
   `data/models/npcs.big/chest_default.tex/cr_jacket_cm: blue_jacket wins over red_jacket`.
5. **Deploy** builds and deploys all switched-on mods for that game into the recomp
   (replacing the previous deploy). **Remove mods from game** in the main window removes
   them; **▶ Play** does the deploy and starts the game.
6. **Edit in Studio** makes the selected mod the open mod in the main window, so new
   replacements go into it. **Share…** packages it (below); **Remove**
   deletes it from the library folder.

### With the `dr2` command

```
dr2 mod install red_jacket blue_jacket.zip    # folders or zips, switched on
dr2 mod list                                  # load order, on/off, files
dr2 mod move red_jacket top                   # up, down, top, bottom, or a number
dr2 mod disable blue_jacket                   # enable / disable
dr2 mod conflicts -g cz                       # who wins over whom
dr2 mod deploy -g cz                          # no folder given: every switched-on mod
dr2 mod remove blue_jacket
dr2 mod library D:/dr2-mods                   # use another library folder
```

`dr2 mod check`, `conflicts`, `build` and `deploy` take mod folders as before; with
none, they use the library's switched-on mods in order. A folder you copy into the
library by hand shows up as "new" and switched off until you enable it.

## Turning mods off

- Recomp: start it with `CZ_NO_MODS=1` (Case Zero) or `CW_NO_MODS=1` (Case West). The
  `game_mods/` folder is ignored and the game is exactly as without mods.
- In Studio: **Play without mods**, or **Remove mods from game**.
- Or `dr2 mod undeploy -g cz`.

### Mod sets

A **mod set** remembers which mods are switched on, so you can go back and forth (say,
"all my mods" and "just the translation"). In the mod manager: switch mods on and off,
**Save set as…**, and later pick it and **Use set**. Command: `dr2 mod sets save all`,
`dr2 mod sets use all`, `dr2 mod sets`.

## Sharing a mod

A shared mod is one **`.dr2mod`** file (a zip with its own name, so it's clearly a DR2
mod; `.zip` works too).

### In DR2 Studio

1. With your mod open, click **Share…** at the bottom (or select it in the mod manager
   and click **Share…**).
2. Fill in the name, version, author and description; tick the games it is for; choose a
   **preview picture** (any image, or **Use one of the mod's textures**); write a short
   readme (what it changes, anything to know).
3. Click **Save .dr2mod…**. Studio first checks the mod against each game you ticked (the
   same checks as a build); if a game reports a problem, nothing is written and the box
   says why. Otherwise choose where to save `my_mod-1.0.0.dr2mod`.
4. Share that file. Whoever gets it drops it on DR2 Studio (or **Install mod…**), sees
   your picture and readme, clicks **Install**, then **▶ Play**.

### With the `dr2` command

`dr2 mod pack my_mod` writes `my_mod-1.0.0.dr2mod` (`-o name.zip` for a plain zip);
`dr2 mod install my_mod-1.0.0.dr2mod` installs one (`--replace` to update; it lists
what changed). Hidden files and build leftovers are left out of the package.

Never share the built
files from `game_mods/` or `dr2 mod build`: those are the game's archives with your
change inside, i.e. copyrighted game data. The person installing your mod runs
`dr2 mod deploy` on their own copy of the game.

A mod marked `local_only = true` can't be shared: it holds another game's files.

Mods made with this toolkit must be free for everyone (see the rules in
[`README.md`](README.md#rules-for-mods-made-with-this-toolkit)).

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| `replaced by both a and b at the same priority` | Two mods change the same asset | Raise one mod's `priority`, or remove one of the files. |
| `… replaces X as a whole, and … replaces Y inside it` | One mod replaces an archive, another a file inside it | Make the first mod replace only the files it changes. |
| `… both have id 'x'` (mod manager) | Two folders in the library have the same `id` | Remove or rename one. |
| `refusing entry '../…'` when installing a zip | The zip would write outside the mod | Don't install it; ask its author for a clean zip. |
| `expected one mod … found 2` | The zip holds several mods | Unzip it and install each folder. |
| `id 'My Mod' must be lower-case…` | `id` has spaces or capitals | Use e.g. `my_mod` (the `name` can be anything). |
| `… is not in a recomp; say where to put the files with --to` | Your game data isn't a recomp's `assets/game` | Use `dr2 mod build … -o OUT` and copy the files over the game's own (keep backups). |

## Going further

- The format details behind building: [`../formats.md`](../formats.md),
  [`../ARCHITECTURE.md`](../ARCHITECTURE.md) §Mod package format.
- How the recomp loads `game_mods/`: [`../dev/recomp-integration.md`](../dev/recomp-integration.md).

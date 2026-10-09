# Mod packages: what's in a mod folder, building, sharing

**You will:** understand a mod folder, write its `mod.toml`, combine several mods, and
share a mod without sharing game files.   **Time:** ~10 min to read.   **Games:** both.
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
| `<any asset's vpath>` (no `.png` / `.glb` added) | Replaces that asset with your file's bytes, as they are. For text files (`.txt`, `.csv`) and anything you edited with another tool. |

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

## Build, deploy, undeploy

| DR2 Studio | Command | What happens |
|---|---|---|
| (automatic) | `dr2 mod check MOD -g cz` | Checks every file: does the asset exist, is the PNG the right size, does each `.glb` pass the model check, do mods clash. Writes nothing. |
| **Build && deploy** | `dr2 mod deploy MOD [MOD…] -g cz` | Builds the game files that hold your assets and copies them into the recomp's `assets/game_mods/` folder. |
| — | `dr2 mod build MOD [MOD…] -g cz -o OUT` | Builds into the folder `OUT` (laid out like the game: `OUT/data/…`). For Xenia or a console. |
| **Undeploy** | `dr2 mod undeploy -g cz` | Removes exactly the files the last deploy wrote. Files you put there yourself stay. |

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

## Turning mods off

- Recomp: start it with `CZ_NO_MODS=1` (Case Zero) or `CW_NO_MODS=1` (Case West). The
  `game_mods/` folder is ignored and the game is exactly as without mods.
- Or `dr2 mod undeploy -g cz`.

## Sharing a mod

Zip the mod folder (`mod.toml` + `replace/`) and share the zip. Never share the built
files from `game_mods/` or `dr2 mod build`: those are the game's archives with your
change inside, i.e. copyrighted game data. The person installing your mod runs
`dr2 mod deploy` on their own copy of the game.

Mods made with this toolkit must be free for everyone (see the rules in
[`README.md`](README.md#rules-for-mods-made-with-this-toolkit)).

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| `replaced by both a and b at the same priority` | Two mods change the same asset | Raise one mod's `priority`, or remove one of the files. |
| `… replaces X as a whole, and … replaces Y inside it` | One mod replaces an archive, another a file inside it | Make the first mod replace only the files it changes. |
| `id 'My Mod' must be lower-case…` | `id` has spaces or capitals | Use e.g. `my_mod` (the `name` can be anything). |
| `… is not in a recomp; say where to put the files with --to` | Your game data isn't a recomp's `assets/game` | Use `dr2 mod build … -o OUT` and copy the files over the game's own (keep backups). |

## Going further

- The format details behind building: [`../formats.md`](../formats.md),
  [`../ARCHITECTURE.md`](../ARCHITECTURE.md) §Mod package format.
- How the recomp loads `game_mods/`: [`../dev/recomp-integration.md`](../dev/recomp-integration.md).

# Point the toolkit at your game

**You will:** tell the toolkit where Case Zero and/or Case West are, then look around
inside the game's files and copy some out.   **Time:** ~10 min.   **Games:** both.
**You need:** the toolkit installed (for now, follow the developer setup in
[`../dev/setup.md`](../dev/setup.md); an installer comes later), and your own copy of
the game in one of the three forms below.

> **DR2 Studio** (the window-based app) arrives in phase 2. Until then, everything here
> uses the `dr2` command in a terminal: PowerShell on Windows, Terminal on macOS and
> Linux. You type one line, press Enter, and read the answer. That's all the
> "programming" involved.

## Which form is your game in?

The toolkit reads the game's `data` folder: about 150 files ending in `.big` (the
game's archive files, see the [glossary](../glossary.md)). You can give it that folder
in three ways:

| You have… | Go to |
|---|---|
| A Case Zero or Case West **recomp** set up next to the toolkit | [A. Recomp](#a-you-have-a-recomp) |
| A folder that already has `data/` in it (an earlier unpack, a copy from a friend's tool…) | [B. A data folder](#b-you-have-a-data-folder) |
| The **XBLA package** only: one big file with a long hex name | [C. The XBLA package](#c-you-have-the-xbla-package) |

## Steps

### A. You have a recomp

If the recomp folders sit next to the toolkit's folder, with their usual names
(`Dead_Rising_2_Case_Zero_Xenon_Recomp`, `Dead_Rising_2_Case_West_Xenon_Recomp`), there's
nothing to do. Type:

```
dr2 games
```

You should see each game with `(found via recomp)`:

```
cz: Dead Rising 2: Case Zero: …/Dead_Rising_2_Case_Zero_Xenon_Recomp/assets/game  (found via recomp)
cw: Dead Rising 2: Case West: …/Dead_Rising_2_Case_West_Xenon_Recomp/assets/game  (found via recomp)
```

If the recomp is somewhere else, use B with its `assets/game` folder.

### B. You have a data folder

Tell the toolkit where it is, once per game (`cz` = Case Zero, `cw` = Case West). You
can give either the `data` folder itself or the folder that contains it:

```
dr2 games set cz "D:\Games\DR2 Case Zero"
dr2 games set cw ~/games/case-west/data
```

Put the path in quotes if it has spaces. The toolkit checks the folder has `.big` files
in it and remembers the choice in its settings file (`dr2 doctor` shows where that is).

### C. You have the XBLA package

The game is sold as one package file. Its name is 42 hexadecimal characters, and it
sits in a folder named after the game's title ID:

| Game | Title ID | Package folder |
|---|---|---|
| Case Zero | `58410A8D` | `…/58410A8D/000D0000/` |
| Case West | `58410B00` | `…/58410B00/000D0000/` |

On an Xbox 360 drive that's under `Content/0000000000000000/`; Xenia keeps it in its own
`content` folder. Copy the file to your computer, then unpack it into a new folder:

```
dr2 unpack "path/to/58410A8D/000D0000/3A98C69EE94FD53A3D592BBAC2236F2247A2957158" my-case-zero
```

It prints what it found first. Check that the title ID and name are the game you
expect:

```
display name: 'DEAD RISING 2: CASE ZERO'
title id    : 58410A8D   media id: 00000000
…
extracted 256 files, 859,007,897 bytes -> my-case-zero
next: dr2 games set <cz|cw> my-case-zero
```

Then do what the last line says:

```
dr2 games set cz my-case-zero
```

(Case West's package unpacks to 305 files, 1.2 GB.) To look inside a package without
unpacking it, use `dr2 unpack <package> --list`.

## Check it worked

```
dr2 games
dr2 ls
```

`dr2 ls` lists the game's `data` folder for Case Zero. Add `-g cw` for Case West
(`dr2 ls -g cw`). You should see folders and `.big` files:

```
            data/anim/
            data/audio/
   47.7 MB  data/cine_props.big
            …
  926.6 KB  data/datafile.big
```

## Look around

Every file inside the game has an address called a **virtual path**: the archive's
path, then a `/` for each level inside it ([glossary](../glossary.md)). Letter case
doesn't matter. `dr2 ls` opens archives as if they were folders:

```
dr2 ls data/models/npcs.big
```
```
data/models/npcs.big: 185 entries
  807.3 KB  data/models/npcs.big/boss_mechanic.big  (compressed)
    4.6 MB  data/models/npcs.big/boss_mechanic.tex  (compressed)
  …
```

`boss_mechanic.big` is a character model and `boss_mechanic.tex` its textures. Both are
archives themselves, so you can keep going: `dr2 ls data/models/npcs.big/boss_mechanic.tex`.
"(compressed)" is just information: the toolkit decompresses for you.

To find something by name anywhere in the game, nested archives included, use `find`
with part of the name:

```
dr2 find mech_apron
```
```
  188.0 KB  data/models/npcs.big/boss_mechanic.tex/mech_apron_cm
  116.0 KB  data/models/npcs.big/boss_mechanic.tex/mech_apron_nm
   60.0 KB  data/models/npcs.big/boss_mechanic.tex/mech_apron_sm
3 entries match 'mech_apron'
```

(It reads the whole game: about 10 seconds, or a few minutes if `dr2 doctor` says the
LZX decoder is the slow Python one.)

## Copy files out

```
dr2 extract data/models/npcs.big/boss_mechanic.tex/mech_apron_cm -o my-files
```

writes `my-files/data/models/npcs.big/boss_mechanic.tex/mech_apron_cm`, following the
virtual path. Add `-r` to unpack a whole archive, nested archives included, into
folders:

```
dr2 extract data/datafile.big -r -o my-files
```

What you get in phase 1 are the game's **own** file formats, decompressed. Textures,
for instance, are still Xbox 360 GPU data, not pictures. Converting them to PNG, glTF
and WAV comes in later phases ([`04-extracting.md`](README.md), planned). Text files
such as the ones in `datafile.big` (`missions.txt`, `items.txt`, …) open in any text
editor.

Please don't share files you extract: they're the game's, not yours. Share mods instead
(see the rules in [`README.md`](README.md)).

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| `error: Dead Rising 2: Case Zero: game data not found.` | No recomp next to the toolkit, and no folder set | Use B or C above. |
| `… the configured folder … has no game data any more` | The folder you set was moved or deleted | `dr2 games set cz <new folder>` |
| `dr2 games set` says `no 'data' folder with .big files there` | Wrong folder | Give the folder that **contains** `data`, or `data` itself. On Linux, check the name's case. |
| `error: … not an XContent package` from `dr2 unpack` | That file isn't a package | Use the big file inside `…/000D0000/`, not the folder or a smaller file next to it. |
| `dr2: command not found` / `not recognized` | The toolkit's environment isn't active | Activate it ([`../dev/setup.md`](../dev/setup.md)) or use `python -m dr2kit` instead of `dr2`. |
| `dr2 doctor` shows `LZX decoder: python (slow fallback …)` | The fast decoder library isn't built or couldn't load | Everything still works, just slower. To speed up: [`../dev/setup.md`](../dev/setup.md), "Build the native LZX library". |
| `error: …: no entry named 'x'` | A typo in the virtual path, or the file is one level deeper | `dr2 ls` the archive to see the exact names, or `dr2 find x`. |

More problems and fixes: [`12-troubleshooting.md`](12-troubleshooting.md).

## Going further

- The toolkit can also check every file of a game for you: `dr2 census`. It prints a
  long report that format researchers use (what's in the game, and whether the toolkit
  read and re-wrote every archive exactly). You don't need it to mod.
- Next guide: browsing with thumbnails and sound previews ([`03-browsing.md`](README.md),
  phase 2).
- Where things are in the game: [`asset-catalogue.md`](README.md) (grows from phase 2).

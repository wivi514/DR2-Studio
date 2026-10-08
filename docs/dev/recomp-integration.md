# Recomp integration: the `game_mods/` layer

How the two recomps load mods built by this toolkit, and how to test that they do.
Decision and design: [`../ARCHITECTURE.md`](../ARCHITECTURE.md) §Recomp integration.
PCM audio substitution (the second approved change) comes in phase 5 and will be
documented here too.

## What the runtime does

Both recomps resolve every file the game opens through one function,
`VfsResolveExisting()` in `runtime/kernel/vfs.cpp`. It already checked overlay folders
next to the game folder (`assets/game`) before the shipped file:

```
assets/game_bootskip/   CZ only: fecmn.big with the intro logos skipped (launcher toggle)
assets/game_kbm/        keyboard-prompt glyphs (on while the native keyboard is used)
assets/game_patched/    the recomp's own patches: PC options menu, string banks, ...
assets/game/            the shipped data
```

Phase 2 added **`assets/game_mods/`, checked first**. For each path the game opens
(e.g. `game:\data\models\npcs.big`):

1. If `CZ_NO_MODS` / `CW_NO_MODS` is set, skip the layer entirely.
2. If `assets/game_mods/` exists and holds the same relative path (exact case first,
   then case-insensitively), serve that file and log
   `VFS: 'game:\data\models\npcs.big' served from the MODS overlay -> … (CZ_NO_MODS=1 turns mods off)`.
3. Otherwise fall through to the existing layers, unchanged.

The result is cached per path, like every other answer of the resolver, so the layer
costs one directory check per distinct file opened.

**The runtime only swaps whole files.** All format work (nested archives, LZX, tiling)
happens in the toolkit at build time (`dr2kit/mods/build.py`). That keeps the C++ change
to ~40 lines per recomp and puts every format rule in one place.

### Why first, and the conflict rule

A mod is something a player chose to install, so it wins. Two consequences, both handled
by the toolkit rather than the runtime:

- **`game_patched` files.** If a mod touches a file the recomp has patched (e.g.
  `datafile.big`, `frontend/fecmn.big`), serving the mod's copy would drop the recomp's
  patch. So `dr2 mod deploy` builds the mod **on top of `game_patched`'s copy** when one
  exists (`--base`, on by default for a recomp; `--no-patched-base` to opt out).
- **Toggle layers** (`game_kbm`, `game_bootskip`) are switched at run time, so the
  toolkit can't know which copy to build on. If a mod carries one of their files,
  deploy prints a warning: while the mod is installed, its copy is used.

## Where it lives

| | Case Zero | Case West |
|---|---|---|
| Code | `runtime/kernel/vfs.cpp`, block "THE MODS OVERLAY" before the boot-skip overlay | same file, before the keyboard-prompt overlay |
| Off switch | `CZ_NO_MODS=1` | `CW_NO_MODS=1` |
| Docs | `docs/instruments.md` (mods overlay section), `docs/gotchas.md` #634 | `docs/gotchas.md` #330 |

Both recomps follow their own CLAUDE.md conventions: an off switch, a log line per
served file, a gotcha entry. `CZ_NO_PATCHED_ASSETS` / `CW_NO_PATCHED_ASSETS` do **not**
turn mods off, so each layer can be A/B-tested alone.

## Testing it (the phase 2 in-game gate)

The gate: a recoloured texture inside a **compressed** `.tex` shows up in both recomps,
and disappears with the off switch. Being inside a compressed entry, it also proves the
game accepts the toolkit's LZX encoder's output (nothing had shown that before).

Headless, with the recomp's own instruments (no window, scripted button presses, a PPM
of every 64th frame). Use a **copy of the save folder** (`CZ_SAVE_DIR`), because the
scripted presses play the game:

```
dr2 mod deploy my_mod -g cz
cp -r <recomp>/assets/save /tmp/save_copy
cd <recomp>/runtime/build
CZ_SAVE_DIR=/tmp/save_copy CZ_NO_WINDOW=1 CZ_VKDRAW=1 CZ_VK_FRAME_DUMP=/tmp/on \
  CZ_FAKE_START_MS=8000 CZ_FAKE_PRESS_SEQ=START,A,A timeout 170 ./cz_runtime > on.log 2>&1
CZ_NO_MODS=1 CZ_SAVE_DIR=/tmp/save_copy CZ_NO_WINDOW=1 CZ_VKDRAW=1 CZ_VK_FRAME_DUMP=/tmp/off \
  CZ_FAKE_START_MS=8000 CZ_FAKE_PRESS_SEQ=START,A,A timeout 170 ./cz_runtime > off.log 2>&1
grep "MODS overlay" on.log off.log        # one line per modded file in on.log, none in off.log
dr2 mod undeploy -g cz                    # leave the recomp as it was
```

Case West: the same with `CW_` names and `./cw_runtime`.

`START,A,A` walks title → menu → *Continue*, so the run loads the latest save: the
texture you test must be on screen in it. With the save used on 2026-10-08, Case Zero's
Chuck wears his default orange "04" shirt (`npcs.big/chest_young_chuck.tex/young_cr_shirt_cm`),
and Case West's Chuck his default jacket (`npcs.big/chest_default.tex/cr_jacket_cm`).
`dr2 index textures-of data/models/npcs.big/chest_young_chuck.big` is how the shirt
texture was found.

### Results (2026-10-08)

See [`../devlog.md`](../devlog.md) (phase 2 entry) and [`testing.md`](testing.md)
§Phase 2 results for the frames and log lines of each run.

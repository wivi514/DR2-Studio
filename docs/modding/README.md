# Modding guide

Guides for people who want to **make mods**. You don't need to know how to program.
Each guide is written when the feature it covers works, and is tested by following it
step by step on a clean setup.

New to the vocabulary? Keep the [glossary](../glossary.md) open.

## Guides

| Guide | You will learn to… | Status |
|---|---|---|
| `01-install.md` | Install DR2 Studio on Windows, Linux or macOS | planned (phase 6, early builds from phase 2) |
| [`02-game-data.md`](02-game-data.md) | Point the toolkit at your game: a recomp folder, an unpacked `data/` folder, or the XBLA package; look around and copy files out | ✅ written (phase 1, CLI) |
| `03-browsing.md` | Find assets, search, see which textures a model uses, play sounds | planned (phase 2) |
| `04-extracting.md` | Export textures (PNG), models and skeletons (`.glb`), sounds (WAV) | planned (phases 2-5) |
| `05-first-mod-texture.md` | **Your first mod:** recolour a texture and see it in game | planned (phase 2) |
| `06-mod-packages.md` | What's in a mod folder, `mod.toml`, building, sharing | planned (phase 2) |
| `07-blender-setup.md` | Set up Blender to work with DR2 models and skeletons | planned (phase 3) |
| `08-edit-a-model.md` | Edit an existing model in Blender and put it back | planned (phase 4) |
| `09-new-model.md` | Rig a brand-new model to a game skeleton and replace a character/outfit/weapon | planned (phase 4) |
| `10-audio.md` | Replace music, voices and sound effects | planned (phase 5) |
| `11-text.md` | Change in-game text and translations | planned (phase 6) |
| [`12-troubleshooting.md`](12-troubleshooting.md) | Fix common problems: the mod doesn't show, the game crashes, rig errors | started (phase 1: game data); grows with each phase |
| `asset-catalogue.md` | Where things are: Chuck's outfits, zombies, weapons, music, maps… | grows from phase 2 |

## Rules for mods made with this toolkit

From the [`LICENSE`](../../LICENSE): mods for these games **must be free for everyone**.
No selling them, no Patreon/membership paywalls, no paid early access. Voluntary donations
are fine if they unlock nothing. You need your own legally obtained copy of the games,
and you must never share the original game files: share your mod package instead, which
contains only your own work.

## Writing a guide (for contributors)

Every guide follows this shape, so readers always know where to look:

```markdown
# <Task in plain words>

**You will:** one sentence.   **Time:** ~N min.   **Games:** CZ / CW / both.
**You need:** the toolkit version, Blender version, files…

## Steps
1. One action per step, naming the exact button, menu or command.
   (A screenshot for every GUI step, saved in `docs/modding/img/<guide>/`.)
2. …

## Check it worked
What you should see in game (and a screenshot).

## If something went wrong
Symptom → cause → fix, for each known problem.

## Going further
Links to the next guide and the relevant reference docs.
```

Show both ways where both exist: the DR2 Studio buttons first, then the matching `dr2`
command line for people who prefer scripts.

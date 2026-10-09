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
| [`03-browsing.md`](03-browsing.md) | Find assets, search, see which textures a model uses (playing sounds: phase 5) | ✅ written (phase 2: Studio + CLI) |
| [`04-extracting.md`](04-extracting.md) | Export textures (PNG), models and skeletons (`.glb`), sounds (WAV) | ✅ textures (phase 2), models and skeletons (phase 3); sounds in phase 5 |
| [`05-first-mod-texture.md`](05-first-mod-texture.md) | **Your first mod:** recolour a texture and see it in game | ✅ written (phase 2), checked in both recomps |
| [`06-mod-packages.md`](06-mod-packages.md) | What's in a mod folder, `mod.toml`, building, sharing | ✅ written (phase 2) |
| [`07-blender-setup.md`](07-blender-setup.md) | Set up Blender to work with DR2 models and skeletons | ✅ written (phase 3), followed with Blender 5.2 |
| [`08-edit-a-model.md`](08-edit-a-model.md) | Edit an existing model in Blender and put it back | ✅ written (phase 4); its edit checked in game on CZ (scripted Blender run, `tools/blender_gate_model.py`) |
| [`09-new-model.md`](09-new-model.md) | Rig a brand-new mesh to a game skeleton and replace a part of a character | ✅ written (phase 4); a new rigged mesh checked in game on CZ, fingers and face (scripted Blender run) |
| `10-audio.md` | Replace music, voices and sound effects | planned (phase 5) |
| `11-text.md` | Change in-game text and translations | planned (phase 6) |
| [`12-troubleshooting.md`](12-troubleshooting.md) | Fix common problems: the mod doesn't show, the game crashes, rig errors | started (phases 1-4: game data, textures, mods, model export and import); grows with each phase |
| [`asset-catalogue.md`](asset-catalogue.md) | Where things are: Chuck's outfits, zombies, weapons, rigs, music, maps… | started (phase 2, rigs and models in phase 3); grows |

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

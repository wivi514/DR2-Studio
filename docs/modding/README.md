# Modding guide

Guides for people who want to **make mods**. You don't need to know how to program.
Each guide is written when the feature it covers works, and is tested by following it
step by step on a clean setup.

**Start here.** In DR2 Studio, the **Welcome** window (toolbar) walks you through the
first steps with buttons, and these guides are inside the app: **Help** in the toolbar
(or **F1**), with a search box. Next to every asset you select, a box says how to change
it and opens the right guide. The quickest first mod:
[`05-first-mod-texture.md`](05-first-mod-texture.md) (about 10 minutes).

In the terminal, `dr2 help` lists these pages and `dr2 help 05` shows one.

New to the vocabulary? Keep the [glossary](../glossary.md) open.

## Guides

| Guide | You will learn to… | Status |
|---|---|---|
| [`01-install.md`](01-install.md) | Install DR2 Studio on Windows, Linux or macOS; point it at your games | ✅ written (phase 6); the Linux build tried on Fedora 44, Windows/macOS builds not run yet |
| [`02-game-data.md`](02-game-data.md) | Point the toolkit at your game: a recomp folder, an unpacked `data/` folder, or the XBLA package; look around and copy files out | ✅ written (phase 1, CLI) |
| [`03-browsing.md`](03-browsing.md) | Find assets, search, see which textures a model uses, listen to sounds | ✅ written (phase 2: Studio + CLI; sounds phase 5; animations played, phase 14) |
| [`04-extracting.md`](04-extracting.md) | Export textures (PNG), models and skeletons (`.glb`), sounds (WAV), Case West's movies (MP4) | ✅ textures (phase 2), models and skeletons (phase 3), sounds (phase 5), movies (phase 6), animations as Blender Actions (phase 14) |
| [`05-first-mod-texture.md`](05-first-mod-texture.md) | **Your first mod:** recolour a texture and see it in game | ✅ written (phase 2), checked in both recomps |
| [`06-mod-packages.md`](06-mod-packages.md) | What's in a mod folder, `mod.toml`, building, the mod manager (several mods, load order), sharing | ✅ written (phase 2; mod manager phase 6) |
| [`07-blender-setup.md`](07-blender-setup.md) | Set up Blender to work with DR2 models and skeletons | ✅ written (phase 3), followed with Blender 5.2 |
| [`08-edit-a-model.md`](08-edit-a-model.md) | Edit an existing model in Blender and put it back | ✅ written (phase 4); its edit checked in game on CZ (scripted Blender run, `tools/blender_gate_model.py`) |
| [`09-new-model.md`](09-new-model.md) | Rig a brand-new mesh to a game skeleton and replace a part of a character | ✅ written (phase 4); a new rigged mesh checked in game on CZ, fingers and face (scripted Blender run) |
| [`10-audio.md`](10-audio.md) | Listen to sounds, export WAV, replace music, voices and sound effects | ✅ written (phase 5); a music swap checked in game in both recomps |
| [`11-text.md`](11-text.md) | Change in-game text and translations; edit the game's text data files with a diff | ✅ written (phase 6); a changed string checked in game in both recomps |
| [`13-blender-addon.md`](13-blender-addon.md) | Find, import, check and export models from inside Blender with the DR2 add-on | ✅ written (phase 6); the whole flow scripted in Blender 5.2 |
| [`14-texturing-tools.md`](14-texturing-tools.md) | Texture a model in Substance Painter, Blender, ArmorPaint or a 2D editor, export it the way the game needs, and import it into a mod in one step | ✅ written (phase 7); the import tested on Painter-style exports of a game model, not yet followed in Painter itself |
| [`16-library.md`](16-library.md) | Find things by what they are (characters, music, rigs…) in the **Library**, and export a model with all its textures and rig, or a whole group, in one go | ✅ written (phase 8); exports checked in both games (Blender opens the `.glb` with textures and bones) |
| [`17-variants.md`](17-variants.md) | Choose what a zombie wears (head, hat, shirt, trousers, colours), see it, and export that look or every part organised for Blender | ✅ written (phase 9); checked in DR2 Studio and Blender on both games; how the game picks a look in game is not known yet |
| [`18-maps.md`](18-maps.md) | See a whole level in 3D in the **Maps** tab (and arrange DR2 Studio's windows): fly through it, spawn points, zombie areas, map areas, triggers, the navigation mesh, zombie crowds, time of day, the collision mesh; click anything to see what it is | ✅ written (phase 10); checked in DR2 Studio on Case Zero's street (against a recomp frame from the same camera); Case West checked by eye by the user; collision checked in Studio pictures in both games |
| [`19-edit-a-level.md`](19-edit-a-level.md) | Edit a level in the **Maps** tab: move, turn, add and delete items and whole buildings (with their collision), drag things in from **Place**, nudge with the arrow keys; change zombies; add save points, workbenches, doors, spawn points and blockers from prefabs; make items of your own; all saved as edits that work beside other mods | ✅ written (phase 11); every kind of edit checked in game in Case Zero (buildings 2026-10-11/12), the items, prefabs and zombie retypes in Case West too |
| [`20-make-a-weapon.md`](20-make-a-weapon.md) | Make a weapon of your own with the weapon wizard: your model laid into a game weapon's hands, its moves, damage, fire / freeze / shock, effects picked by name, an inventory icon and a combo card drawn from your model | ✅ written (phase 13); the wizard's output built and checked in both games, a wizard sword seen in Case Zero's street (headless); the icon, card and swinging not yet seen in game. Phase 13.2: Chuck holding it in 3D (the game's idle for the kind), drag handles, effects playing, `dr2 hold`; not yet compared with the game. Phase 14: Chuck swinging it (the kind's attacks, every key of the game's animations), `dr2 hold --moves` for Blender |
| [`21-effects.md`](21-effects.md) | Change the game's particle effects (fire, snow, sparks…: colour, size, lifetime, pictures) or make your own from them, with your own particle pictures, and put them on a weapon | ✅ written (phase 13); a changed effect, an effect of your own and an own picture seen in Case Zero (headless); Case West loads with them (headless), not yet seen. Phase 13.2: the effect plays in 3D on a weapon in Chuck's hand (a sketch: motion not measured) |
| [`22-from-other-games.md`](22-from-other-games.md) | Bring a weapon model (any game, through Blender; WoW 3.3.5 directly) or WoW's particle effects into a mod, for yourself only (such a mod can't be shared) | ✅ written (phase 13); Frostmourne's model fitted by the wizard, its seven frost emitters converted and seen in Case Zero (headless, at a fixed place); on a held weapon not yet seen |
| [`15-limits.md`](15-limits.md) | The limits of the game and the toolkit: vertices, bones, weights, UVs, texture sizes and formats, sounds, text | ✅ written (phase 7), every number measured on both games |
| [`12-troubleshooting.md`](12-troubleshooting.md) | Fix common problems: the mod doesn't show, the game crashes, rig errors | started (phases 1-6: game data, textures, mods, models, sounds, text); grows with each phase |
| [`asset-catalogue.md`](asset-catalogue.md) | Where things are: Chuck's outfits, zombies, weapons, rigs, music, text, movies… | started (phase 2, rigs and models in phase 3, sounds in phase 5, text and movies in phase 6); grows |

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

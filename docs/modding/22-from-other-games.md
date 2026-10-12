# Models and effects from other games (on your own computer)

**You will:** bring a weapon model, or its particle effects, from another game you own
into a mod, to play with it yourself.   **Time:** ~15 min.   **Games:** both.
**You need:** the toolkit ([`02-game-data.md`](02-game-data.md)), the weapon wizard
([`20-make-a-weapon.md`](20-make-a-weapon.md)), and the other game installed. For World of
Warcraft 3.3.5 (Wrath of the Lich King): the toolkit's `tools/wow_import.py` and, to read
WoW's archives, `pip install mpyq`. For other games: Blender and an importer add-on for
that game's format.

> Phase 13. Tried: Frostmourne's model and its seven frost emitters from a WoW 3.3.5
> install, its model fitted by the weapon wizard (the handle found by itself) and played
> in Case Zero (phase 12); its effect converted and seen in game: see the status line in
> [`../phase13-kickoff.md`](../phase13-kickoff.md) §Status.

## Read this first: it stays on your computer

Another game's models, textures and effects belong to its makers. You may use them on
your own computer, with your own copy of that game, but **you can't share them**, not
even inside a DR2 mod. So:

* a mod that holds anything from another game is marked **local only**
  (`local_only = true` in its `mod.toml`; the WoW tool does this itself). DR2 Studio's
  *Share…* and `dr2 mod pack` refuse such a mod;
* to share a weapon, make (or have someone make) a model of your own, and share that.

## Steps: a model from another game

### Any game, through Blender

1. Find a Blender importer for the game's model format (search "<game> Blender import";
   community add-ons exist for most big games). Install it: *Edit → Preferences →
   Add-ons → Install from disk…*
2. *File → Import →* the game's format. Delete what isn't the weapon (a hand, a stand).
3. Bake its materials into one colour picture if it has several that repeat (the wizard
   puts several materials side by side in one picture; repeating ones look stretched):
   [`14-texturing-tools.md`](14-texturing-tools.md).
4. *File → Export → glTF 2.0*, format *glTF Binary* (`.glb`).
5. In DR2 Studio: **New weapon…** → *Model* → **Model file (.glb)…**. The wizard lays the
   model into the game weapon's hands by itself (its longest side along the weapon, the
   handle found from its shape); check the red diamonds (where the hands go) and use
   *Its handle is*, *Slide*, *Turn* if needed ([`20-make-a-weapon.md`](20-make-a-weapon.md)).
6. Open the mod's `mod.toml` and add `local_only = true` under `[mod]`.

### World of Warcraft 3.3.5, directly

```
pip install mpyq
python tools/wow_import.py extract "<WoW>/Data" ^
    "Item\ObjectComponents\Weapon\Sword_2H_Frostmourne_D_01.m2" ^
    "Item\ObjectComponents\Weapon\Sword_2H_Frostmourne_D_0100.skin" -o wow
python tools/wow_import.py model wow/Sword_2H_Frostmourne_D_01.m2 --wow "<WoW>/Data" -o frostmourne.glb
```

(`^` continues a line in the Windows terminal; on Linux and macOS use `\`.)

`extract` copies files out of WoW's archives (the patches win, as in the game). `model`
writes a `.glb` with one mesh per part and its texture; `--wow` lets it find the textures
in the archives. A weapon's own texture is named by WoW's item tables, not by the model:
the tool tries `<model name>.blp` in the model's folder (right for WoW's weapons); give
another with `--texture <path in the archives>`. Then step 5 above.

To find a model's path, use a WoW file browser (the community's MPQ viewers list every
file). Only 3.3.5's `.m2` (version 264) is read; later versions are refused, saying so.

## Steps: particle effects from WoW

WoW's weapons carry their glow and mist as **particle emitters** inside the `.m2`. The
tool turns each into a DR2 emitter of one effect of your own
([`21-effects.md`](21-effects.md)):

```
python tools/wow_import.py effect wow/Sword_2H_Frostmourne_D_01.m2 my-mod -g cz --wow "<WoW>/Data"
```

It prints the effect's number (e.g. `your effect number 6`) and marks the mod local only.
Put that number on your weapon: **New weapon…** → *Effect: while held* (your effects are
listed first), or `dr2 mod new-weapon my-mod Frostmourne … --held 6`.

What it keeps from each WoW emitter: its colours and opacity over its life, its sizes, its
lifetime, how many particles it makes, where it sits on the model and the area it throws
particles from, gravity, and its particle picture (made see-through from its brightness).
`--length` is the model's length in metres in DR2 (default 1.1, about the Broadsword's):
positions and sizes are scaled by it. Speeds and spin are not converted yet (DR2's fields
for them are not known): the base emitter's are kept. Change the result in **Effects…** like any effect
of yours (hue, size, lifetime).

## Check it worked

* **Effects…** → *Yours (this mod)* lists the effect; its sketch shows the WoW pictures in
  their colours.
* In game: the weapon shows the effect while held.
* *Share…* says the mod is local only.

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| `reading WoW's MPQ archives needs mpyq` | the reader isn't installed | `pip install mpyq` |
| `.m2 version …: only 3.3.5's (264) is known` | a model from a later WoW | use a 3.3.5 install, or Blender's route |
| `…: not next to the .m2 (give --wow …)` | a texture or `.skin` isn't in the folder | add `--wow "<WoW>/Data"`, or `extract` it next to the `.m2` |
| The model is grey | its texture wasn't found | `--texture <path in the archives>` |
| `… is a local-only mod` when sharing | it holds another game's files | share a mod with a model of your own |
| The effect is too big or too small | the length used for scaling | run `effect` again with `--length`, or **Effects…** → *Size* |

## Going further

* Effects of your own made from the game's: [`21-effects.md`](21-effects.md).
* How the fields map, and what each DR2 field was measured to do:
  [`../formats.md`](../formats.md) §Particle effects.

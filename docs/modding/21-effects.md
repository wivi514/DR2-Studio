# Particle effects: change the game's, make your own

**You will:** recolour, resize or re-time one of the game's particle effects (fire, snow,
sparks, blood…), or make an effect of your own from one of them, with your own particle
picture if you like, and put it on a weapon.   **Time:** ~10 min.   **Games:** both
(one game per mod for effects of your own).
**You need:** the toolkit with your game folders set ([`02-game-data.md`](02-game-data.md))
and a mod ([`06-mod-packages.md`](06-mod-packages.md)). For a weapon:
[`20-make-a-weapon.md`](20-make-a-weapon.md).

> Phase 13. Seen in game (Case Zero, 2026-10-12, a test run without a window): a game
> effect recoloured everywhere (the Flaming Sword's flame turned green), an effect of your
> own in a free slot (the Flaming Sword copied and turned blue, as number 69), and a
> particle picture of your own. Case West: a mod with a changed effect and an effect of
> your own loads into the game (headless); the effects themselves not yet seen there.
> The picture in DR2 Studio is a **sketch** from the effect's data, not the game drawing
> it: in game the particles move, spread and fade.

## What an effect is

A **particle effect** ([glossary](../glossary.md#particle-effect)) is a small file in
`data/models/effects.big` with a name (`flamingsword_wpn_c_3_unq`) and a few
**emitters**: each one throws out little pictures (*particles*: a flame, a puff of smoke,
a glow) with a colour that changes over their life, a size and a lifetime. The Flaming
Sword's flame is four emitters: dark smoke, the flame, sparks of smoke and a glow.

Weapons and levels pick effects **by number** (a weapon's `EffectOnImpact`, `PyroEffect`…
keys). The numbers are a fixed list inside the game's program, the
[effect table](../glossary.md#effect-table): 371 in Case Zero, 414 in Case West. You
can't add numbers, but **36 numbers of that list have no effect in the game** (names like
`wip_1`, `unused`, `garbage_wpn_dbs_2`): these are the **free slots**
([glossary](../glossary.md#free-slot-effects)), the same in both games. An effect of your
own goes into one of them and takes its number.

So there are two ways:

| | What it does | When to use it |
|---|---|---|
| **Change in my mod** | changes a game effect **everywhere the game uses it** (every Flaming Sword, every fire) | you want the game's own effect to look different |
| **Make my own from this** | copies the effect into a free slot with your changes; the game's stays as it was | you want a new effect for your weapon (a blue flame next to the normal one) |

What you can change: the **hue** (turn every colour: 0 red, 120 green, 200-210 ice blue),
**saturation**, **brightness**, **opacity**, **size**, **lifetime**, and each emitter's
**particle picture** (another of the game's, or a PNG of your own). Dark smoke stays
dark when you change the hue: only coloured parts turn.

## Steps (DR2 Studio)

1. Open or create a mod (bottom bar: *New mod…* / *Open mod…*), and pick the game at the
   top left.
2. Click **Effects…** (bottom bar). The list shows every effect of the game by number,
   with its group (*Ice and snow*, *Fire*, *Electric*…), ✓ for the ones checked in game,
   and, when you hover, what the game uses it for.
3. Type in the search box (`flame`, `snow`, `spark`…) or pick a group, and click an
   effect. The picture (left) is a sketch of it; **Colours** shows its colour keys; the
   text says what each emitter throws out, its colours, sizes and lifetime.
   *Yours (this mod)* in the group box lists what your mod already changes or adds.
4. Move the sliders. The picture follows:
   * **Hue**: all the way left is *(keep)*; anywhere else turns every colour to that hue
     (the Flaming Sword at ~200 is an icy blue flame).
   * **Saturation**, **Brightness**, **Opacity**, **Size**, **Lifetime**: ×1.00 keeps it.
   * **Picture**: pick one of the effect's pictures on the left of the arrow, and the
     picture to use instead on the right. **My own picture…** adds a PNG of yours
     (see-through background; it is fitted to the nearest size the game uses, 16 to 256
     pixels square) and picks it.
5. Then:
   * **Change in my mod** changes the game's effect everywhere, or
   * **Make my own from this** copies it, with your changes, into the next free slot. The
     window says its **number** (e.g. *Your effect is number 69*).
   * **Reset** puts the sliders back; **Remove from mod** takes a change or an effect of
     your own out.
6. Put your effect on a weapon: **New weapon…** → the *Effects* boxes list your own
   effects first (*Yours: 69 (from flamingsword_wpn_c_3_unq)*). *While held* is an aura on the weapon all the time,
   *while swinging* a trail, *on impact* where it hits, *on the zombie hit* on the zombie
   ([`20-make-a-weapon.md`](20-make-a-weapon.md)).
7. **▶ Play**.

## The same with the `dr2` command

```
dr2 effects flame -g cz                         # effects with "flame" in their name
dr2 effects --group ice -g cz                   # one group
dr2 effects --free -g cz                        # the free slots
dr2 effects --show flamingsword_wpn_c_3_unq -g cz --out flame.png   # its emitters, a sketch

# change the game's effect everywhere:
dr2 mod effect my-mod flamingsword_wpn_c_3_unq --hue 120 -g cz
dr2 mod effect my-mod flamingsword_wpn_c_3_unq --remove -g cz      # take it out again

# an effect of your own (prints its number):
dr2 mod new-effect my-mod flamingsword_wpn_c_3_unq --hue 205 --saturation 1.3 -g cz
dr2 mod new-effect my-mod snowtrail_wpn_bs_1 --size 2 --slot wip_2 -g cz   # a chosen slot

# a particle picture of your own, then use it in place of one of the effect's:
dr2 mod effect-picture my-mod frost_shard shard.png -g cz
dr2 mod new-effect my-mod flamingsword_wpn_c_3_unq --texture fire_flame=frost_shard -g cz

# on a weapon (69 = your effect's number):
dr2 mod new-weapon my-mod FrostBlade --kind sword --glb sample --held 69 -g cz
```

The `--show` output reads like this (Case Zero):

```
flamingsword_wpn_c_3_unq (data/models/effects.big/EFFECT_Common137), 4 emitter(s):
  0: cloud_smoke2 (box), colours #080808@0.60 → … → #020202@0.03, size 0-0.4 m, over 1.00 s
  1: fire_flame (box), colours #000080@0.60 → #f17e16@0.50 → …, size 0.06-0.1 m, over 0.32 s
  …
```

Each line is an emitter: its particle picture, the shape it throws particles from, its
colour keys (colour@opacity, from birth to death), its size and how long its colours last.

## What goes into your mod

| File | What it is |
|---|---|
| `replace/data/models/effects.big/EFFECT_Common137.effect.json` | a change to a game effect: its name and your changes |
| `add/data/models/effects.big/EFFECT_Common1069.copy.json` | an effect of your own (number 69): the game effect it starts from, the slot's name and your changes |
| `add/data/models/effects.tex/frost_shard.copy.json`, `sources/frost_shard.png` | a particle picture of your own |

Your mod holds only your changes, never the game's effects: they are made from your own
game when the mod is built, so you can share the mod. The build also does three things the
game needs (measured in Case Zero): it lists a new effect in the effects' scene file (an
effect not listed there never shows), it makes the game read the effects from
`effects.big` instead of the copy kept in `preload4.big` (otherwise your change never
shows), and it writes the new sizes into `layout.bin` (otherwise a bigger `effects.big`
crashes the game). You don't have to do anything for these.

## Check it worked

* In DR2 Studio, *Yours (this mod)* lists your effect; the mod bar shows the files with
  no error; *Share…* → *Check* passes.
* In game: an effect you changed shows changed wherever the game uses it (the Flaming
  Sword's flame); an effect of your own shows where you put its number (on your weapon,
  while held).
* Case West: built and checked like Case Zero by the toolkit's tests; it loads in game
  (see the status line at the top of this guide).

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| The effect looks the same in game | the mod isn't switched on, or another mod changes the same effect after yours | the mod manager: switch it on, move it down the list ([`06-mod-packages.md`](06-mod-packages.md)) |
| `no free effect slot left` | your mod already uses all 36 free slots | change game effects instead, or remove some of yours |
| `… is a game effect, not a free slot` | `--slot` named a number the game uses | `dr2 effects --free` lists the free ones |
| `no effect named …` | a typo, or the effect is only in the other game | `dr2 effects <words>` |
| The colour didn't change on smoke | grey keys keep their grey | raise **Saturation** above ×1.00 to colour them too |
| The effect fills the screen | it is a level's effect (fog, smoke) | pick a small one, or lower **Size** |
| The game crashes while loading after an effect change | an old build without the `layout.bin` fix | build again with this toolkit (**▶ Play** rebuilds) |

More in [`12-troubleshooting.md`](12-troubleshooting.md#particle-effects-phase-13).

## Going further

* Change any field of one emitter by hand (for those who like to experiment): the
  `"emitters"` key of the recipe, e.g. `{"emitters": {"1": {"gravity": [0, 2, 0]}}}` in
  the `.effect.json` / `.copy.json`, and `"remove": [3]` drops an emitter. Most fields
  have guessed names only: what they do is in [`../formats.md`](../formats.md) §Particle
  effects. Tell us what you find.
* Put your effect on a weapon: [`20-make-a-weapon.md`](20-make-a-weapon.md).
* Effects from World of Warcraft (for yourself only):
  [`22-from-other-games.md`](22-from-other-games.md).
* What was measured so far, changing one value at a time: `count_20` is how many
  particles, the last colour key time is their life ([`../formats.md`](../formats.md)
  §Particle effects).

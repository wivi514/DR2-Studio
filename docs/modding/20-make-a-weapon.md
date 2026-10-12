# Make a weapon of your own

**You will:** make a new weapon with your own model: what it swings like, how hard it
hits, whether it burns, freezes or shocks zombies, sparkles or trails, its picture in the
inventory, and a combo card to build it at a workbench.   **Time:** ~10 min.   **Games:** both
(one game per mod).
**You need:** the toolkit with your game folders set ([`02-game-data.md`](02-game-data.md)),
a mod ([`06-mod-packages.md`](06-mod-packages.md)), and a model as a `.glb` if you have one
(Blender: *File → Export → glTF 2.0*, format *glTF Binary*). No model yet? Use the
**sample sword** that comes with the toolkit.

> Phase 13. Written: the weapon wizard (DR2 Studio's *New weapon…*, `dr2 mod new-weapon`),
> the named effects, the icon and the card made from your model. What has been seen in
> game: moves borrowed from another weapon, the hands at the model's grip nodes, fire,
> freeze and shock, effects on the weapon while held or swung, a combo card (all in Case
> Zero, phase 12), and a wizard-made sword standing in Case Zero's street (headless,
> 2026-10-12). **Not yet seen in game:** the new icon in the inventory, the new card
> picture, picking the weapon up and swinging it, and anything in Case West. Tell us what
> you see.

## How a weapon is made

A weapon in Dead Rising 2 is two things ([glossary](../glossary.md#weapon-kind)):

* a **block of `items.txt`**: which moves it uses (`AnimBankName` and one set of keys per
  attack), its damage, durability, effects, sounds, its name (a *string id*) and its
  icon's name;
* a **pack** `data/streamedassets.big/<Name>.big`: its model, its textures and its
  inventory icon.

The wizard starts from a game weapon of the **kind** you choose (a sword starts from the
Broadsword in Case Zero, the Katana in Case West) and copies it under your weapon's name:
so your weapon swings, sounds and is held like that one. Then it changes what you asked
for. Your mod holds only **your** files and a recipe; the copy is made from your own game
when the mod is built, so you can share the mod.

**Where the hands go.** Chuck's hands go to the **grip nodes** inside the weapon's model
(`LOC_rhand`, `IK_lhand`…), whatever the moves: measured in game. Your model is laid
where the game weapon lies, and the wizard shows you where the hands will be (red
diamonds) so you can slide it until the handle is in the hands.

## Steps (DR2 Studio)

1. Open or create a mod (bottom bar: *New mod…* / *Open mod…*), and pick the game at the
   top left.
2. Click **New weapon…** (bottom bar).
3. **Item name**: one word, letters, digits and `_`, e.g. `FrostBlade`. This is the name
   level files use. **Name (English)** / **Name (French)**: what the player sees. The
   other languages get the English name.
4. **Swings like**: the kind of weapon (hover for a note). Each kind is a game weapon;
   your weapon gets its moves, sounds and how it is held.
5. **Model**: *The game weapon's own shape* (only change its looks and behaviour), *The
   sample sword*, or **Model file (.glb)…** for yours. Any size and direction is fine: the
   wizard lays its longest side along the game weapon, its flat side the same way, at the
   game weapon's length.
   * The preview (right) shows your shape over the game weapon (faded), with **red
     diamonds where the hands go**.
   * **Its handle is**: if the blade ended up in the hands, choose *one end* / *the other
     end*.
   * **Length** (0 = the game weapon's), **Turn about its length** (try 90°), **Slide**
     (moves it along: + towards the tip) until the hands sit on the handle.
6. **Damage per hit** (the Broadsword hits for 125) and **Durability** (hits before it
   breaks; the Broadsword lasts 40). 0 keeps the game weapon's.
7. **Element**: *Fire* sets zombies on fire, *Freeze* freezes them (a thrown weapon
   freezes the zombie it sticks in), *Shock* shocks them with chain lightning.
8. **Effects** (particles; they only change what you see):
   * *on impact*: where it hits; *on the zombie hit*: on the zombie;
   * *while held*: on the weapon all the time; *while swinging*: a trail.
   Type to search (`snow`, `fire`, `spark`…). Each is listed by group; ✓ marks the ones
   checked in game; hover to see what the game uses it for. "Keeps going" or "burst"
   (read from the effect's name, a guess) helps choose: a trail or an aura should keep
   going. **Careful:** some are a whole room's effect (286 `dryice_env_c_3` is a fog the
   size of a street).
9. **Inventory icon**: *A picture of the model* (drawn like the game's icons: lying on a
   slant, handle left, a thin dark outline), *The game weapon's icon*, or **My own PNG…**
   (128×64, see-through background).
10. **Combo weapon** (optional): tick it, choose the **two items** that make it at a
    workbench, write the **card text**, and choose the card's picture: *A picture of the
    model* (your weapon on a glow in its element's colour, with line drawings of the two
    items under it, made from your game when the mod is built) or **My own picture…**
    (315×262). The card number is the first free one unless you set it.
11. Click **Make weapon**. The weapon is in your mod. Open it again later from the
    **Weapon** list at the top of the window, change anything, and click *Make weapon*
    again; **Remove from mod** takes it out.
12. Put it in a level: **Maps** tab → *Add item…* ([`19-edit-a-level.md`](19-edit-a-level.md)),
    or build it at a workbench with its combo. Then **▶ Play**.

## The same with the `dr2` command

```
dr2 mod new my-mod
dr2 effects --kinds -g cz                        # the kinds of weapon
dr2 effects --group ice -g cz                    # effects by group (or: dr2 effects snow)
dr2 mod new-weapon my-mod FrostBlade --kind sword --glb sample \
    --name-en "Frost Blade" --name-fr "Lame de givre" \
    --damage 150 --element freeze --impact 181 --held snowtrail_wpn_bs_1 \
    --combo Broadsword+FireExtinguisher --card-text-en "A blade of ice." -g cz
dr2 mod new-weapon my-mod FrostBlade --slide 0.05 --turn 90      # change only these
dr2 level edit my-mod prologue add "cItemPlacement MyFrostBlade" \
    ItemName=FrostBlade Location=-278,3.6,-36
dr2 play -g cz
```

`--glb` takes your file, `sample`, or `keep` (the game weapon's shape). Running
`new-weapon` again on the same name changes only the options you give.
`dr2 mod remove-weapon my-mod FrostBlade` takes it out.

## What goes into your mod

| File | What it is |
|---|---|
| `sources/FrostBlade.weapon.json` | your choices (the wizard opens it again) |
| `sources/FrostBlade.glb`, `FrostBlade_*.png` | your model laid into the weapon, its colour picture (several materials are put side by side in one picture), a flat normal map |
| `sources/FrostBlade_icon.png`, `FrostBlade_card.png` | the icon and card pictures |
| `add/data/streamedassets.big/FrostBlade.big.copy.json` | the recipe: copy the game weapon's pack under the new name, with your model, textures and icon |
| `add/data/frontend/combocards.tex/comboc_frostblade(_no).bct.copy.json` | the card's two pictures (found / not found yet), made when the mod is built |
| `replace/data/datafile.big/items.txt.edits.json` | the weapon's block |
| `replace/data/frontend/str_<language>.bcs.json` | its name and the card's texts, in every language |

A mod with a weapon is for **one game** (the wizard sets it): a weapon starts from that
game's weapon. Make a second mod for the other game.

## Check it worked

* In DR2 Studio, the mod bar lists the new files with no error; *Share…* → *Check* passes.
* In game: the weapon lies where you placed it, with your model; pick it up and look at
  the inventory: your icon and name. Swing it: the moves of its kind, your effects, and
  the element on zombies. With a combo: put the two items on a workbench.

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| Chuck holds it by the blade | the wrong end was taken as the handle | *Its handle is* → the other end |
| The hands are on the guard or past the handle | the model's handle is longer or shorter than the game weapon's | *Slide* (a few centimetres at a time), or *Length* |
| The blade is edge-on in the icon or looks thin | the model's flat side is the other way | *Turn about its length* 90° |
| Parts of the model look stretched | several materials with repeating textures share one picture | one material per model (bake it in Blender) |
| "a weapon shape takes at most 65,535" | the model has too many vertices | Blender: *Decimate* ([limits](15-limits.md)) |
| "is already an item of the game" | the item name is taken | pick another name |
| "now a mod for CZ only" | weapons are made per game | make another mod for Case West |
| The effect fills the screen | it is a level effect | pick a small one (✓ marks the checked ones) |

More in [`12-troubleshooting.md`](12-troubleshooting.md).

## Going further

* Change the weapon's other keys by hand: see a game weapon's with
  `dr2 level show items "cPlayerWeaponItem Broadsword"`, then
  `dr2 level edit my-mod items set "cPlayerWeaponItem FrostBlade" ThrowForce=20`
  ([`19-edit-a-level.md`](19-edit-a-level.md)). Running the wizard again rebuilds the
  block, so make these changes last.
* What every weapon key does, the elements and the effect table:
  [`../formats.md`](../formats.md) §Weapons.
* Your own effects (not only the game's): phase 13, planned
  ([`../phase13-kickoff.md`](../phase13-kickoff.md)).

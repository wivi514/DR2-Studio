# Phase 13 kickoff: weapons of your own, made easy, and effects of your own

**Direction (user, 2026-10-12, at the end of phase 12's tests):** phase 12 is closed with
what its in-game tests proved (Frostmourne played in Case Zero: its own model, the
Broadsword's moves, freeze, a combo card with its own picture and French name). Phase 13
turns that into tools, and adds what the user asked for while testing:

1. **"More tools for modders to add their own FX"**, and **"grab the effects of WoW and put
   them in"**: effects of one's own, made or brought in, while **reusing the game's
   effects stays the easy option** ("at least players will have this easy option to re-use
   the fx of the game if they don't know how to do their own").
2. **"The icon in the inventory should be a picture of the 3D object."**
3. Everything phase 12 planned but didn't build: the weapon wizard, the grip editor, combo
   weapons with new cards, buildings and maps of one's own.

Phase 12's tests and research: [`phase12-kickoff.md`](phase12-kickoff.md) §Status;
the facts: [`formats.md`](formats.md) §Weapons and §Particle effects.

## What phase 12 proved (in game, CZ, 2026-10-12)

| Question | Answer |
|---|---|
| How does a weapon freeze, burn, shock? | shock = `Can_Electrocute = true`; fire / freeze = a child `cPropHitZombieInfoItem` with `PropHitZombieEffect` 0 / 1 (works on melee hits and on thrown weapons); `Fire` / `Can_Freeze` alone do nothing to the zombie |
| What are the effect numbers? | a 1-based index into a table of 371 (CZ) / 414 (CW) particle effects in the executable: looks only |
| Can a weapon borrow another's moves? | yes: `AnimBankName` and the per-attack keys of the other weapon |
| Where do the hands go? | at the **item model's own** grip nodes (`LOC_rhand`, `IK_lhand`), whatever the moves: place the mesh |
| An effect on the weapon itself? | `PropEffectsOnCondition` 30 (always) / 31 (swinging) + `PyroEffect`, locator 16: works in CZ |
| A combo card of one's own? | yes: a `cComboCardItem` in the result's block, a free `CardIndexNumber` (3), an existing picture replaced in place; texts **in the player's language** (the user plays in French) |
| New files (packs, card textures, string ids) | **stalled the street's load** (zone z10, every time, headless too), even unused: cause unknown. Everything that worked used **replacements only** (a carrier item: the Lead Pipe) |

Not tested: `PropHitZombieEffect` 2 and 3; why swords always slice; a card number past 50;
buildings (T4) and maps (T5); the `.anm` format.

## Plan (proposed; in this order, each step documented and tested as it goes)

1. **The loading stall (blocker).** Bisect the stalled test mod (kept:
   `~/.cache/dr2kit-p12-handoff/mods/p12-t123-stalls`) headless on a copy of the user's
   save (`scripts/headless.py`): no strings → no card textures → one pack → four packs; then
   compare the built `streamedassets.big` / `combocards.tex` / `str_en.bcs` with the
   shipped ones (entry order, hashes, alignment, sizes: phase 11's single new pack loaded).
   If new packs can't be fixed: **carrier items** become the way (a list per game of items
   that ship a model but are never placed, `formats.md` §Weapons), and the wizard uses
   them.
2. **Weapon data files:** `catalog/weapon_kinds.toml` (each kind, the game weapons whose
   moves it borrows, the keys that come with the moves) and `catalog/effects.toml`:
   - **elements** as measured (Shock, Fire, Freeze: the keys above);
   - **the effect table, named** (all 371 / 414 numbers with the executable's names, read
     by a tool from `default_image.bin`, `tools/effect_table.py`), grouped for people
     ("ice", "fire", "electric", "blood", "sparks", "smoke"…) with the ones checked in game
     marked (215 snow trail and 225 snow puff on a sword: good; 286 dry ice: a level fog,
     too big);
   - **effect slots** of a weapon: on impact (`EffectOnImpact`), on the victim
     (`EffectOnVictim`), always on the weapon (condition 30), while swinging (31).
3. **The weapon wizard** (Studio *New weapon…*, `dr2 mod new-weapon`): name (every
   language, English and French first), kind, moves, damage, element, effects picked from
   the named list **with a preview** (step 6), its `.glb` and textures, inventory icon
   (step 4), a combo recipe and card (step 5). Writes only what step 1 allows.
4. **Inventory icon from the model:** render the weapon (`convert/render.py`) in the
   game's icon style (128×64, see-through background, handle top left, tip bottom right,
   lit like `w_broadsword`) into the pack's `w_<name>.bct`; *Change icon…* takes a PNG.
   Also for combo cards: the picture rendered from the result, the modder's own PNG, and
   the small icon square (x 21-59, y 18-57 of the 364×512 card).
5. **Combo weapons:** the card's texts in every language, its picture (new texture if step
   1 allows, else a game card's picture replaced), a card number past the game's (test
   how many the game takes).
6. **Effects of one's own** (the user's new request):
   1. **Read the effect format** (`data/models/effects.big`, `EFFECT_Common<k>`: a name,
      then one record per emitter with its particle texture and float blocks), a census
      over every effect of both games (zero unread bytes), and a writer that gives every
      effect back byte for byte (CLAUDE.md gates). Find colours, sizes, rates, lifetimes,
      spread by changing one value at a time in game (the user looks).
   2. **Reuse and tweak:** copy a game effect and change colour, size, amount, lifetime,
      texture. First target: Dead Rising 2's **Flaming Sword** aura
      (`flamingsword_wpn_c_3_unq`, a flame along the whole blade) recoloured icy blue, for
      Frostmourne.
   3. **Preview** in Studio (particles drawn in the 3D view, on the weapon).
   4. **Effects of one's own:** a new effect from scratch (emitters, a particle texture
      PNG); where new effects go depends on whether the effect table in the executable
      limits them (the numbers are an index into it: maybe only replacing an effect is
      possible, like level ids: then "slots" of effects CZ never uses, as for levels).
   5. **Bring effects in from another game:** WoW's `.m2` particle emitters (texture,
      colours, sizes, rates) converted to DR2 emitters (local tests with the user's own
      install only: never shared, LICENSE).
7. **The grip editor** (phase 12 plan step 4): Chuck holding the weapon in Studio, the
   borrowed weapon see-through, the new mesh moved with handles; it places the mesh so the
   item's own grip nodes land in the hand (measured: hands follow `LOC_rhand` /
   `IK_lhand`).
8. **Bring a model in from another game** (local only): `tools/m2glb.py` (WoW WotLK `.m2`
   + `.skin` → a `.glb` laid into a game weapon's space) worked for Frostmourne; generalise
   it into an import guide (Blender add-ons for other formats first).
9. **Carried from phase 12:** buildings of one's own (T4a/T4b), maps in empty level slots
   (T5), the door's destination list, `.anm` animations (Chuck swinging in the grip
   editor), guides 20-22.

## Decisions to take (proposed defaults in bold)

1. **Effects first or the wizard first?** **The stall, then the weapon wizard with the
   game's effects (steps 1-5), then effects of one's own (step 6)**: modders get the easy
   path first.
2. **Effects of one's own: replace or add?** **Find out in step 6.1** (if the executable's
   table can't grow, offer the "unused effect slots" of each game, like level slots).
3. **Models and effects from other games:** **local tools only**, never in a shared
   `.dr2mod` (the toolkit can't help distribute others' copyrighted assets).
4. **Languages:** **English and French written by the wizard**, the other banks get the
   English text unless the modder fills them.

## Gate

- **Frostmourne made only in DR2 Studio** with its own icon picture (rendered from the
  model), the Broadsword's moves, freeze, a frost aura of its own (a recoloured game
  effect), and a combo card; shared as one `.dr2mod` (with a model of the modder's own,
  not WoW's), installed on a clean library, played.
- An effect made from scratch (or brought in) shows on a weapon in game.
- Census: every effect of both games read and written back byte for byte; every weapon
  block parses into the wizard's model and back.

## Status

**Started 2026-10-12** with the proposed decisions (the user: "Do phase 13", away, the
game not to be started for them: in-game checks headless on a copy of their save).

* **Step 1 (the stall): done, not a stall.** Phase 12's mod, rebuilt whole and with the
  user's other mods, loads into gameplay headless every time (frames dumped during the
  run). A good load's file list ends the same way (`prologue_z10.big`, `Prologue.txt`,
  `combocards.tex`), so phase 12 took a finished load for a stall. New packs, card
  textures and string ids load: the wizard makes new items, no carriers needed. The
  user's windowed phase 12 runs are not explained ❓ (formats.md §Weapons).
* **Step 2: done.** `tools/effect_table.py`, `catalog/effects.toml` (CZ 371 / CW 414
  names; only the first 370 shared), `catalog/weapon_kinds.toml` (19 kinds),
  `catalog/weapons.py`, `dr2 effects`.
* **Step 3 (the wizard): done.** `mods/newweapon.py`, `studio/weapon_dialog.py` (*New
  weapon…*), `dr2 mod new-weapon` / `remove-weapon`; any `.glb` fitted along the game
  weapon (`convert/weapon_fit.py`, handle end from the model's blood/FX nodes); the
  sample sword. Built in both games (tests), a wizard sword seen in CZ's street (headless).
* **Step 4 (icon from the model): done** (`convert/icon.weapon_icon`; CZ `w_<name>.bct`,
  CW `<name>.bct`, renamed `w_<name>` with `IconFilename`). **Not seen in game yet.**
* **Step 5 (combo cards): done** (texts in every bank, English + French written; the card
  drawn on an empty card made from the game's cards, the items as line drawings, the
  faded `_no` copy). **Not seen in game yet;** a card number past the game's not tried.
* **Step 7 (grip editor): mostly** in the wizard's preview (the new shape over the faded
  game weapon, the hands' grip nodes as red diamonds, slide / turn / length / handle end).
  Chuck holding it (needs `.anm`) not done.
* **Owed by the user (windowed):** pick up and swing a wizard weapon (CZ and CW), its
  icon in the inventory, the combo card at a workbench (found and not found), French
  names.

## Start here (handoff)

- Read this file, `phase12-kickoff.md` §Status, `formats.md` §Weapons and §Particle
  effects, guide 19 (own items), `mods/newitem.py`.
- **Phase 12's working files** (outside the repo, on disk):
  `~/.cache/dr2kit-p12-handoff/`:
  - `mods/p12-elements`: the working Frostmourne test mod (Lead Pipe carrier,
    `leadpipe.big.glb` and PNGs, items / prologue edits, strings en/fr/lg, the card
    pictures); **it contains a WoW model: never share or commit it**;
  - `mods/p12-t123-stalls`: the mod whose added files stalled the load (step 1);
  - `scripts/`: `make_frost.py` (rebuilds p12-elements), `m2glb.py` (WoW `.m2` → `.glb`),
    `fxtab.py` (dumps the effect table from `default_image.bin`), `headless.py` (a headless
    load of a copy of the user's save, prints the files opened last), `floor.py` (open
    floor near a point from the zone collision), `keys.py` / `blocks.py` (items.txt
    research);
  - `fxtab_cz.txt`, `fxtab_cw.txt` (the effect table, 0-based: number = index + 1);
    `wow/` (Frostmourne's model, texture, icon; the Lead Pipe's `.glb` template).
- **State of the user's library (2026-10-12 end of phase 12):** on: `keep-cz-test-save`,
  `keep-cw-test-save`, `test_01`, `my_mod`, `p12-elements` (linked from the handoff
  folder, deployed in CZ); **off: the user's `test_01_2`, `test_01_3`** (switched off for
  the tests; ask the user before switching them back on). The user's CZ save is the
  `default` profile; the user plays in **French**; they start at the safehouse exit
  (place test items there, on floor checked against collision).
- How the user likes tests: small builds with no new files when possible, launched at once
  (`dr2kit.mods.play.launch`), headless checks only to diagnose (memory: test item
  placement).

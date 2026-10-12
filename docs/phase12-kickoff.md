# Phase 12 kickoff: make your own weapons, combo weapons, buildings and maps

**Direction (user, 2026-10-12):** "make it the easiest to create new weapon, building,
combo weapon (like mix broadsword with fire extinguisher it make Frostmourne […] they just
changed the normal sword to Frostmourne). We can make weapon have effect: Dead Rising 2
made elemental damage so we can apply that it freeze enemies, burn or whatever effect
there is; choose what type of damage, what type of weapon it is, like if it is a sword
type we re-use the broadsword or katana animation whichever we prefer and then we see the
character holding that animation with that weapon but see through (ex: katana) and we
place the handle in his hand so it's properly aligned. If it's something big with two
hands we can do like the animation for the trash can. Building is easier since you don't
need animation for it but will need to make collision etc. Also can make our own map and
use the prefab to go somewhere and then select that it goes to that map."

So, four goals, each a **wizard in DR2 Studio** that a modder with a `.glb` from Blender
can finish without reading a file format:

1. **A new weapon.** Pick what kind it is (sword, knife, blunt one-hand, pole, big
   two-hand, thrown, spray, gun), which game weapon's moves it borrows (the Katana's or the
   Broadsword's swings…), its damage and durability, and an **effect** (freeze, burn,
   electrocute…). Load its model, then **align its handle in Chuck's hand** against a
   see-through copy of the weapon whose moves it borrows.
2. **A combo weapon.** Pick the two items that make it (Broadsword + Fire Extinguisher)
   and what comes out: a weapon of your own (Frostmourne, freezing) or one the game has.
   Its combo card (picture, name, description) goes with it.
3. **A building of your own.** A `.glb` placed in a level that Chuck can't walk through.
4. **A map of your own**, and a door (the existing *Door to another level* prefab) that
   leads to it.

**Decisions taken (user, 2026-10-12): every proposed default** under §Decisions, with
combo cards made precise: **a combo weapon always gets a new card of its own, and the
modder can change the card's picture** (see §Decisions 5).

This file holds the research (2026-10-12, both games' data and executables), what can be
reused, the unknowns and the in-game tests that settle them, the plan, the decisions to
take, and the gate. Facts go to [`formats.md`](formats.md) once checked.

## What the research found

### Weapons are `items.txt` blocks (both games, plain text, editable by `.edits.json`)

`data/datafile.big/items.txt`: CZ 599 blocks (130 `cPlayerWeaponItem`, 11 `cFirearmItem`,
9 `cExplosiveItem`, 6 `cSprayItem`…), CW 1,180 (120, 14, 16, 5…). A weapon's block holds
everything that makes it behave (Katana, CW, abridged):

| Key(s) | What it does | Values seen |
|---|---|---|
| `AnimBankName` | **which moves** (the animation pack `data/streamedassets.big/anm_<bank>.big`) | `Sword` (Broadsword, Katana), `1hand_bank1` (Crowbar, Dynamite: 19), `BowlingBall` (Lead Pipe, 2×4: 14), `LargeBox_bank1` (acetylene tank, garbage can: 12), `ThrustSpear` (broom, pool cue), `Bucket`, `Chair`, `FireExtinguisher`, `Flamethrower`… 52 packs in CW |
| `AnimationAttackName0…5` | the attacks, by animation name inside the bank | `male_attack_sword_6_to_1_a`, `male_sword_a_2_to_8_360`… |
| `ActionButton<n>`, `ActionDesiredAnimState<n>`, `AnimationAttackChooserValue<n>`, `ComboBlend*<n>` | which button does which attack, how attacks chain | per attack |
| `AttackDamage<n>`, `MaxDamageDealtPerAttack`, `MaxProjectileDamage`, `Durability` | damage per attack, when thrown, how long it lasts | Katana 100/150, Broadsword 125, Durability 20-40 |
| `WeaponType` | the kind | 1 (75: blunt and most), 2 (48: big two-hand), 3 (knives, saws), **4 (swords: Katana, Laser Sword, Reaper)**, 6 (thrown explosives), 15 (guns)… |
| `HandlingStyle` | how it is held and carried | 0 one hand (110), 1 long pole (8), **2 big two-hand (propane tank, garbage cans)**, 3 guns, 5 large boxes, 6 cement saw |
| `AnimationChooserValueForHand / Idle / Pickup / Throw / WalkRun` | the holding pose, throw… | numbers into the animation chooser ❓ |
| `Is_Sharp`, `Is_Blunt`, `Arbitraty_Slice`, `WeaponCanSliceLimbs` | cuts limbs or not | |
| **`Can_Freeze`**, **`Can_Electrocute`**, **`Fire`**, `ExplosionCausesFire` | **the elements** | CW freezing: Fire Extinguisher, Whipped Cream, Liquid Nitrogen, Freezer Bomb; electric: Electric Prod, Car Tire (CZ also Electric Rake, Bike Forks, Bike Engine, Handle Bar); fire: Flamethrower, Flaming Aces, Gasoline Canister (CZ Molotov) |
| `EffectOnVictim<n>`, `EffectOnImpact<n>`, `EffectOnWeapon<n>`, `PyroEffect<n>`, `PropEffect*` | what happens to the zombie hit, the particles at impact and on the weapon | victim 20 (51×), 14 (21), 15, 17 (Liquid Nitrogen), 18 (Gasoline), 24, 249 (Electric Rake)…; impact 279 / 280 / 281; pyro 66 (Freezer Bomb), 141 (Fire Extinguisher), 226 (Electric Prod)… **meaning of each number: not known** ❓ |
| `AssetFilename`, `MergedFilename`, `IconFilename`, `DisplayName` (a string id) | the model pack, the inventory icon, the name | |
| children `cComboCardItem`, `cAttachedToZombieInfoItem`, `cPrestigePointInfoItem`, `cPlayerWeaponOverrideItem` | combo card, stuck-in-zombie pose, PP | |

### Combo weapons: a card inside the result's block

Each combo weapon's block holds a **`cComboCardItem`** (CZ 9, CW 17): `Weapon_1` and
`Weapon_2` (the two items: `BaseballBat` + `BoxOfNails` → Spiked Bat; CW `FireExtinguisher`
+ `Dynamite` → Freezer Bomb, `FireExtinguisher` + `WaterGun` → Snowball Cannon),
`ComboStationRotation_1/2` (how they lie on the workbench), `CardIndexNumber` (1…48 in CZ),
`IconAsset` (`comboc_spikedbat`: the card's picture, a texture
`data/frontend/combocards.tex/comboc_spikedbat.bct`, 96 KB, beside `comboc_spikedbat_no.bct`,
likely the card not yet found ❓), `Card_Label` / `Weapon_Description` /
`Ticker_Description` / `Attack1` / `Attack2` (string ids), `PP_Multiplier`,
`CanBeBuiltInProlog`, `AttackIndexToDisableIfNoColouredComboCard` (the bonus attack needs
the card). The result is an ordinary weapon block (`SpikedBat`, `Combo_Paddlesaw`…), some
with their own animation pack (`anm_Combo_PaddleSaw.big`, `anm_Combo_ShotgunPitchfork.big`).
Food combos (the blender) are `combostation_juices.csv` instead.

### Holding a weapon: locators in its model

A weapon's model has **locator nodes** (empty nodes) the game uses: Katana `katana.LOC_WEP_katana_R`
and `_L` (the right and left hand's grip), `LOC_slice`, `LOC_particle_pos`, `POS_stuck`
(where it sits in a zombie); Fire Extinguisher `LOC_rhand`, `FX` (the spray), `POS_launch`.
So "put the handle in his hand" means: the mesh around the grip locator, or the locator
moved. The toolkit already reads nodes and writes models back (phase 4), but its `.glb`
import keeps the original's nodes ("new parts, materials or bones: not possible yet").

### Animations: per attack, not read yet

`anm_Sword.big` holds `root.big` (7 entries) and `fullbody.big` (7), one `.anm` per attack
(`male_attack_sword_6_to_1_a.anm`, 724 / 8,812 bytes). Header (big-endian): a word that
differs between the two packs (a bone-set id ❓), a float that reads as the length in
seconds (1.5-2.0), a float ~29.5 (frames per second ❓), then counts (CW full body 0x74 =
116, root 0x1C = 28: bones? channels? ❓) and packed curves. **The format is not cracked.**
Showing Chuck *swinging* the new weapon needs it; showing him *holding* it needs only his
skeleton (phase 3) and the grip locator.

### Collision of an item: made by the engine

An item's scene has `_COLLPRIMS_` and `_COLLISIONLIST_` entries, empty for the chair
checked; the blocker item (`MilitaryBarrier`, `CollisionType 3`) stopped Chuck in game
(phase 11). So the engine makes an item's collision from its model (a box? a hull? ❓).
A level piece's collision is a Havok mesh with a search tree the toolkit can move but not
build (phase 11 step 4), so a **building of one's own** can't get level-piece collision.

**Invisible collision items exist:** `cBlockingVolumeItem` (CZ 2, CW 8: `wall_short_blocking`,
`moosehead_platform_walls`…) are unmovable items with `MeshVisible = false`,
`CollisionType 3` and `CollisionBits = WORLDCOLLISIONFILTER_BLOCKING_VOLUME`: collision with
no look (none is placed in the shipped levels; their models aren't shipped either). So a
building can be **seen as a level piece and felt through an invisible item** (below).

### Levels: a fixed table in the executable, with empty slots

The level ids (`LEVEL_PROLOGUE_SAFEHOUSE`) are not defined in any data file: they, their
script names (`prologue_safehouse.txt`) and level folders are compiled into the
executable. **No mod can add a level id.** But CZ's executable still lists **83 level ids
and 81 script names from Dead Rising 2** (`LEVEL_FOOD_BARN` / `food_barn.txt`,
`LEVEL_ARENA_STADIUM`, `LEVEL_ATLANTICA_CASINO`, `LEVEL_LABORATORY`, `LEVEL_FORTUNE_EXTERIOR`,
`LEVEL_SOUTH_PLAZA`…), while CZ ships the data of only 4 (`prologue`, `_safehouse`,
`_menu`, `_menu2`). CW lists 15, among them **`LEVEL_W_MALL` (`w_mall.txt`), not shipped**.
These **empty slots** could hold a modder's map, if the game still loads one (unknown: the
code for them may be gone or need more files: a loading screen, an in-game map, a zombie
load set, audio). A door is already a prefab (`ActionType 3`, `Level`, `LevelSpawnPoint`;
phase 11, works in game).

### Text: names and descriptions

New weapons need a name, a combo card label, descriptions: string mods (`.bcs.json`,
phase 6) can change strings and **add new ids in the gaps below a bank's last id**, so a new
weapon gets its own strings.

## What earlier phases give

| Piece | Gives | Phase 12 adds |
|---|---|---|
| `mods/newitem.py`, `dr2 mod new-item` | a new item as a **recipe** (a copy of a game item's pack under a new name, a `.glb` shape, PNG textures, its `items.txt` block): checked in game, a new hammer works | the settings wizard (kind, moves, damage, effect), the grip alignment |
| `convert/model_import.py` | a `.glb` into a game model, checked against the rig | moving a locator (if the game accepts it), a mesh of any vertex count on a rigid weapon |
| `formats/leveledits.py` | `.edits.json` for `items.txt` (blocks added and changed) | combo cards (a block inside the result's block) |
| `formats/bcs.py` | strings changed and added | the wizard writes them |
| `catalog/prefabs.py` | the door to another level, spawn points, blockers | the door's destination chosen from the maps (own ones included) |
| `formats/pieceedits.py`, `convert/buildings.py` | buildings hidden, moved, copied; collision moved | collision copied with a copied building |
| Studio's 3D view (phase 3), Maps editor (phase 11) | models with skeletons, transform handles | a "hold" scene: Chuck, the base weapon see-through, the new one with handles |

## Unknowns, and the in-game tests that settle them (do these first)

Each is a small hand-made mod, played by the user (memory: *User tests in game*), on a
copy of their save or a new game (memory: *Protect the user's saves*).

1. **T1, a new weapon from a template:** a copy of the Katana under a new name with the
   Broadsword's `AnimBankName` / attack names, `Can_Freeze = true`, `EffectOnVictim0 = 17`
   (Liquid Nitrogen's) and a freezing `PyroEffect`. Does it swing like the Broadsword? Does a
   hit freeze? Then the same with `Fire = true`, `Can_Electrocute = true`. Answers: which
   keys make an element, and the effect numbers worth naming.
2. **T2, a combo card of one's own:** a `cComboCardItem` with `Weapon_1 = Broadsword`,
   `Weapon_2 = FireExtinguisher` inside the T1 weapon's block, a new `CardIndexNumber` (CZ
   uses 1…48). Does the workbench combine them? Does the card show (in the pause menu's
   cards)? Is there a maximum number of cards (`CardIndexNumber` into a fixed table ❓)?
3. **T3, the grip:** the T1 weapon's model with its `LOC_WEP_…_R` node moved 10 cm. Does
   Chuck hold it there? If yes, the wizard can move the grip; if not, it moves the mesh.
4. **T4, a building of one's own** (a `.glb`: a box with a doorway), in two halves:
   - **T4a, its look as a new level piece:** the piece's archive added to a zone (`add/`) and
     a placement record for it (`.pieces.json` copies append records: proved). Does it
     show from everywhere, with the small textures far away, like the game's buildings?
   - **T4b, its collision as an invisible item:** the same model as an unmovable item with
     `MeshVisible = false` (a blocking volume, above). Does it block Chuck, and with what
     shape: its box (the doorway blocked), a hull, the mesh? Also a visible unmovable item
     for comparison (`LoadDistance`: when does it appear?).
5. **T5, a map in an empty slot:** CZ: a copy of a small level (the menu street
   `prologue_menu2`, one zone) as `food_barn` (`food_barn.txt`, `models/environment/food_barn/`
   with its `zonelist.big` names changed, `nm_`, `waypoint_`, a `cZombieLoadSet
   LEVEL_FOOD_BARN`) and a door prefab with `Level = LEVEL_FOOD_BARN`. Does it load? What
   else does it ask for (the log: `cz_runtime.log` names files it opens)? CW: the same with
   `w_mall`.
6. **T6, collision for a copied building** (stretch): a copy of a building's collision
   shapes as new entries of `persistent.big` (renamed, moved: translation only), listed in
   `_COLLISIONLIST_` and the collision scene. Does the copy block Chuck?

## Plan (proposed; each step documented and tested as it goes)

1. **Research and the early tests** (above). Write the answers into `formats.md` (§Items,
   new: weapons, effects, combo cards; §Levels: level slots).
2. **Weapon kinds as data:** `catalog/weapon_kinds.toml`: each kind (Sword, Knife, Blunt
   one-hand, Pole, Big two-hand, Thrown, Spray, Gun) with the game weapons whose moves it
   can borrow (Sword: Katana, Broadsword, Laser Sword; Big two-hand: Propane Tank, Garbage
   Can…), the keys that come from the borrowed weapon (bank, attacks, buttons, chains,
   handling) and those the modder sets (damage, durability, sharp / blunt). **Effects** as
   data too (`effects.toml`: Freeze, Burn, Electrocute, … each the keys and numbers T1
   proved), so a new effect found later is one entry.
3. **The weapon wizard** (Studio: *New weapon…*, CLI `dr2 mod new-weapon`): name, kind,
   moves, damage, effect, its `.glb` and textures, inventory icon (a picture rendered from
   its model, phase 8's renderer), name and description strings. Writes a `newitem` recipe,
   the `items.txt` block (`.edits.json`), the strings (`.bcs.json`). Checked by `dr2 mod check`
   (the borrowed bank exists in this game, damage numbers sane).
4. **The grip editor:** a 3D scene in Studio with Chuck (his rig, a holding pose: the rest
   pose with the arm posed, or the bank's first frame once `.anm` is read), the borrowed
   weapon **see-through** at his hand, the new model with move / turn / size handles; Save
   puts the mesh (or the grip locator, per T3) where it was aligned. Two-hand kinds show
   both grip locators.
5. **Combo weapons:** *New combo weapon…* (or a *Combo* page in the weapon wizard): the two
   items (from the game's items and the mod's own), the result (the new weapon or a game
   one), the workbench rotations (copied from a combo with similar items), and **a new
   card**: its number after the game's, its texts, and its picture: two new textures in
   `combocards.tex` (`comboc_<name>` and `comboc_<name>_no`) made by a recipe from a game
   card's (`newitem`'s copy recipe), with the modder's PNG over them (or a picture rendered
   from the result, as a start); *Change picture…* replaces it later. Writes the
   `cComboCardItem`.
6. **Buildings of your own:** *New building…*: a `.glb` → **a new level piece** in the
   zone it stands in (always seen, small textures far away, like the game's buildings) **and
   an invisible collision item** with its shape (or a simpler collision `.glb` the modder
   gives: walls only), placed and moved together as one building in the Maps editor
   (`convert.buildings` groups them); Place lists it. If T4b gives only boxes: the
   collision is several invisible items, one per wall. If T6 works: a copied level building
   keeps its collision. **Baked shadows** (a lightmap for the new piece): later (user,
   2026-10-12).
7. **Maps of your own:** *New map…*: an empty level slot (listed per game), started from a
   copy of a level the game has (or a flat ground), opened in the Maps editor; the *Door to
   another level* prefab gets a **destination list** with the game's levels and the mod's
   own maps and their spawn points.
8. **Stretch: animations.** Read `.anm` (census over every bank, both games), show attacks
   in the grip editor and the Library (Chuck swinging the new weapon), export them to
   Blender.
9. **Guides:** *Make a weapon* (guide 20), *Make a combo weapon* (21), *Buildings and maps of
   your own* (22); glossary (locator, animation bank, combo card, level slot, effect).

## Decisions to take (proposed defaults in bold)

1. **Weapon kinds:** the kinds above, each borrowing a game weapon's moves, **as data**
   (`weapon_kinds.toml`), so adding a kind needs no code. Alternative: a free form of every
   key.
2. **Grip alignment:** **align the mesh to the borrowed weapon's grip** (works whatever T3
   says); move the grip locator only if T3 shows the game follows it.
3. **The holding scene:** **a still holding pose first**, animated attacks later (needs the
   `.anm` format, step 8).
4. **Effects:** **only effects checked in game are offered by name** (Freeze, Burn,
   Electrocute…); every number stays settable under *Advanced*.
5. **Combo cards:** **always a new card** (the user, 2026-10-12): a number after the game's
   and its own picture the modder can change (two new textures in `combocards.tex`). If T2
   shows the game can't take more cards, the plan comes back to the user.
6. **Buildings of your own:** **always seen like the game's buildings, simpler far away**
   (the user, 2026-10-12): the look as a new level piece, the collision as an invisible
   unmovable item (engine-made, T4); level buildings copied with their collision after T6;
   baked shadows later.
7. **Maps of your own:** **only the executable's empty level slots** (CZ many, CW
   `w_mall`), never a patched executable (the recomps stay read-only, CLAUDE.md); **a new map
   starts as a copy of a small level**, edited in the Maps editor.
8. **Text:** **new string ids** (in the banks' gaps) for every new name and description, in
   the languages the modder fills (English first).

## Gate

- **Frostmourne, made only in DR2 Studio**, in both games: a new sword from a Blender
  `.glb`, borrowing the Katana's (or Broadsword's) moves, held correctly (its grip aligned in
  the grip editor), that **freezes** zombies; and a **combo card**: Broadsword + Fire
  Extinguisher at a workbench gives it. Shared as one `.dr2mod`, installed on a clean
  library, played.
- A **two-hand** weapon (garbage-can moves) and a **thrown** one, each held right.
- A **building of one's own** from a `.glb` that Chuck can't walk through.
- A **door to a map of one's own** (CZ: an empty slot) that loads and brings Chuck back.
- Census: every weapon block of both games parses into the wizard's model (kind, moves,
  effects) and back to the same block.

## Status

* **T1 (elements), CZ, played by the user 2026-10-12: done.** Shock = `Can_Electrocute`;
  fire / freeze = a child `cPropHitZombieInfoItem` with `PropHitZombieEffect` 0 / 1;
  effect numbers are only particles (an index into the executable's effect table). The
  effects data file can name them (formats.md §Weapons). The user's wish from the test: a
  freezing swing that also freezes the zombies around (no key for that: an explosive
  thrown by an attack is the idea to try).
* **T2 (combo card), CZ, 2026-10-12: done** with an existing result (Broadsword + Fire
  Extinguisher → the freezing Bowie Knife, card 3 with the Defiler picture). Strings must
  be written in every language (the user plays in French).
* Borrowed moves (T1d), T3 and a card for a NEW item not seen yet: the first test mod's added files stalled
  the load (formats.md §Weapons, "New items' files and the endless loading"); find the
  cause first.
* How the tests are made: small mods in the session scratchpad, linked into the user's
  library (`dr2 mod link`), deployed with `dr2 play -g cz --deploy-only`, the recomp
  started for the user. **Place test items on open floor checked against the zone's
  collision** (`convert.level.zone_collision`: a ray down for the floor, nothing solid up
  to 2 m around): a spot picked by eye was inside a wall. The safehouse exit
  (`cSpawnPoint AlternateExit`, Chuck at -282.1, 3.4, -38.9) is where the user starts;
  open floor at x -280…-276, z -40…-31.
* **Library state (2026-10-12, 03:30):** `keep-cz-test-save`, `keep-cw-test-save`, `test_01`,
  `my_mod` on; the user's `test_01_2`, `test_01_3` (their placed items, building edits)
  **disabled for the tests: turn them back on afterwards**; the test mod `p12-elements`
  (Broadsword / Bowie Knife / Chef Knife changed, placed at the safehouse exit) linked
  from the scratchpad and deployed: remove it when the tests are done.

## Start here (handoff)

- Read this file, then `formats.md` §Levels ("Level edits", "Piece edits", "Items →
  models"), `mods/newitem.py` (recipes), `convert/model_import.py` (how a `.glb` becomes a
  model; the rig validator), `catalog/prefabs.py`, guide 19 (*an item of your own*).
- **How the research was done** (scripts deleted; redo like this):
  `Document.parse(tree.resolve("data/datafile.big/items.txt").data())`, count keys per
  class with the trailing number replaced by `#`; combo cards are `cComboCardItem`
  children; animation packs are `data/streamedassets.big/anm_*.big` (`root.big`,
  `fullbody.big`, one `.anm` per attack); weapon locators are the scene's skeleton nodes
  (`read_scene(tree, ItemModels(tree).resolve("Katana"))`); the level table: every
  `LEVEL_[A-Z0-9_]+` and `\0<name>.txt\0` string in the recomp's
  `assets/game/default_image.bin`, compared with `datafile.big`'s `.txt` entries.
- **Decisions are taken** (all defaults; combo cards always new, picture changeable).
  **First:** T1-T5 (each a small mod the user plays; T2 also adds the two card textures),
  then the plan's steps in order.
- **State at handoff (2026-10-12):** the user starts T1-T5 in a fresh conversation. Their
  mod library holds `keep-cz-test-save`, `keep-cw-test-save` (they keep the user's test
  saves loadable: leave them on) and `test_01`; CZ's `game_mods/` holds those (deployed
  2026-10-12 00:09); no test mod of the toolkit is linked or deployed. Make each test a
  mod in the scratchpad, `dr2 mod link` it, `dr2 play -g cz` for the user, and afterwards
  `dr2 mod remove <id>` + `dr2 play -g cz --deploy-only` (the library and the game back as
  they were). T4 is two tests (T4a the look as a level piece, T4b the collision as an
  invisible item). Tell the user up front which visible changes each test makes on
  purpose.

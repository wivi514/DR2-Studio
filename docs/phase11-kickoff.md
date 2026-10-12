# Phase 11 kickoff: edit levels (zombie spawns, objects) and add your own things, saved as mods

**Direction (user, 2026-10-11):** "probably will add later that we can toggle to see
zombie spawn, modify zombie spawn, modify placement of object and can add more but that
will be for phase 11 if we do it", then "can you also prepare the potential phase 11".

**This phase is optional and comes after phase 10** (`phase10-kickoff.md`), which it
builds on: the Maps tab, the level readers, the layers, and the "with my mods" view.
Phase 10 already *shows* zombie spawn areas and placed objects; phase 11 lets a modder
**change** them in the Maps tab and save the change as a mod:

1. **Zombie spawns:** see every way zombies appear (crowds in an area, single placed
   zombies, respawns), change how many and which types, move or reshape the areas, add
   or remove single zombies.
2. **Objects:** move, turn, remove and add placed items and doors (weapons, boxes,
   benches…), and change what they are (a bench → a chair).
3. **Level pieces** (stretch): move, hide or copy pieces of the buildings.
4. **Add your own things** (user, 2026-10-11): put new things on the map that **behave
   like the real thing**: a usable item, a save point, a workbench, a door to another
   level, zombies into a spawner, a spawn point, a building, a road… each from a
   **prefab** (a ready-made template taken from the game's own working examples), so
   an added save point saves and an added weapon can be picked up and used.

The research (2026-10-11) is below, then the plan. Facts also in
[`formats.md`](formats.md) §Levels.

## Status (2026-10-11): started; step 1 done

**Decisions taken (user, 2026-10-11): every proposed default** under §Decisions to take
(edits by block; zombies per mission; new zombie types allowed with a warning; a "mod
being edited" picked in the Maps tab; prefabs as data plus `.dr2prefab`; own models as
static items first, pieces without collision only until the collision test; new files
only after the in-game test).

**Step 1 done** (2026-10-11): `levelscript.Document` finds blocks by path, adds and
removes blocks and keys in the tool's style (`render`, checked against every shipped
block); `formats/leveledits.py` (`.edits.json`: apply, diff, merge); the `edits` kind in
`mods/build.py` (merged by block over the recomp's copy; checked on a real CZ build: the
co-op lines of `missions.txt` stay); `convert/levelcheck.py` (what edits mean);
`mods/leveledit.py` (a mod's edits of one file, undo, saved as the diff); `dr2 level
show|edit|diff`; census gate `check_level_edits` (0 failures in either game); guide 19
(CLI part). Still to do: steps 2-7 (in-game tests first, then the Maps tab editor).

**Step 2 (2026-10-11): in-game tests done in CZ, the Maps editor for items built.** The
early tests (§Start here) answered in the CZ recomp (the user played each build;
`formats.md` §Levels, "Level edits in game"): an added weapon, workbench and save point
**work**; an unmovable item with collision (`MilitaryBarrier`) **blocks the player**; a
type the level doesn't load (`pro_zombie_cop`) **showed**; changed values in the game's
missions work and keep saves; **a block added inside a game mission breaks saves and
stalls a new game** (refused now, `levelcheck.SAVE_BREAK`); a **mission of the mod's own**
loads and runs in a **new game** only. This changes plan step 3: new single zombies and
crowds go into the mod's own mission, the editor says they need a new game; the game's
own zombies are edited by value. The added-pack test (own models, step 5) is still owed,
and all of it in CW. Built: the Maps tab's Edit section (`studio/maps_edit.py`, the
vendored `TransformControls`), `zombies.mission_spawns`.

**Step 3 (2026-10-11): the zombie editor built.** The Maps tab's *Zombie spawns* layer
(single zombies, crates, clearings), editing a single zombie (place, facing, type, number,
held item; delete = number 0), a crowd's types and amounts, and *Add zombie…* into the
mod's own mission (`maps_edit.ZombieEdits`); checked in Studio on CZ's street with a
driver (pictures) and tests. Not done: reshaping zombie areas (polygon points), a mission
picker (every mission's spawns show at once, each labelled with its mission), the
load-set view.

**Step 5 (2026-10-11): prefabs built and checked in CZ.** `catalog/prefabs.toml` +
`prefabs.py` (save point, workbench, door to another level, spawn point, blocker; own
`.dr2prefab`), the Maps tab's *Add from prefab…*, *Settings…*, *Save as prefab…*. In game
(CZ): a new spawn point used by the safehouse's exit, a new door into the safehouse, both
work (save point, workbench, blocker were checked in step 2). New finding: **a save made
while a mod's own mission runs crashes when loaded without it** (warning `SAVE_NEEDS`).
Still owed: own models (a new item pack: the build must add files; untested whether the
engine finds them), map icons for added save points (`fe_map*.csv` isn't block format),
turning triggers after placing, CW in-game checks of all of this.

**Own models (2026-10-11): done and checked in CZ.** The build adds files (`add/`), a
new item is a recipe copying a game item's pack (`mods/newitem.py`, `dr2 mod new-item`,
Studio's *New item from this…*); in game a new pack is found and the item works, after
fixing the new entry's `flags` (the declared alignment: a new entry declared 0 made the
game load forever). Not done: new level pieces (step 4 stretch), textures of a new item
from Studio (CLI `--texture` only).

### Earlier status: researched, re-checked against phase 10, prefabs added

The user will start this phase **in a fresh conversation** (2026-10-11). Phase 10 is
done (stretch items included, `phase10-kickoff.md` §Status); this file was re-checked
against what it built the same day (§What phase 10 gives), and the user added a fourth
goal the same day: **add your own things from prefabs** (§What makes a thing work in
game, plan step 5). The decisions under §Decisions to take are still open.

## Start here (handoff, 2026-10-11)

- Phase 10 is done. Read this file, then `formats.md` §Levels (the level text files, the
  zombie spawns, "Collision"), `dev/code-tour.md` for `formats/levelscript.py`,
  `convert/placed.py`, `convert/zombies.py`, `convert/level.py`, `convert/mapdata.py`,
  `mods/preview.py` and `studio/maps_view.py`, `dev/studio.md` §The Maps tab (the page's
  `dr2:` messages), `mods/build.py` (how mods become game files; `base_dirs`), and the
  `.bcs.json` string mods (`formats/bcs.py`, guide `11-text.md`), the model for
  "edits by name" mods.
- **How the research was done** (scripts deleted; redo like this): read
  `data/datafile.big/missions.txt` and the level `.txt` files with `tree.resolve(vpath)`
  and count blocks with `re.findall(r"^\s*(c\w+) ", text, re.M)`; the recomp's patched
  copy is `<CZ recomp>/assets/game_patched/data/datafile.big` (compare entry by entry
  with `BigArchive.parse`).
- **First:** ask the user the open questions under §Decisions to take (with the proposed
  defaults), before writing code.
- **Suggested order** (everything stands on step 1; the unknowns that could change the
  plan get an in-game test early, before the editor is built around them):
  1. `levelscript.Document`: add / remove blocks and keys, block paths; the `.edits.json`
     build kind; census: apply then reverse = the original.
  2. Quick in-game tests, both games, each with a hand-made mod: an **added save point**
     (a cloned `cTriggerVolume` `ActionType 4` in `waypoint_<level>.txt`); an **added
     weapon** placement; an **unmovable item as a wall** (does `CollisionType` give it
     collision?); an **added pack** in `streamedassets.big` (does the engine find a new
     file? the build needs to add files first, step 5). Their answers settle the
     prefab routes and the "own models" decision.
  3. Maps tab editing of objects (step 2), then zombies (step 3), then prefabs (step 5),
     then the guide (step 7); level pieces (step 4) last, after its collision test.
- **How the prefab research was done:** walk every `.txt` of `datafile.big` with
  `Document.parse` and list `cTriggerVolume` blocks by `ActionType`; list `items.txt`
  blocks by class and the keys with *Collision* in their name; count Havok parts
  (`… hkpMoppCode`) inside `streamedassets.big`'s nested packs.

## What phase 10 gives (checked 2026-10-11)

| Piece | What it does today | What phase 11 still needs |
|---|---|---|
| `formats/levelscript.py` `Document` | Reads every block-format `.txt` of `datafile.big` and writes it back **byte for byte** (CZ 24, CW 39, `zombiesets.txt`, `missions.txt`, `items.txt` included; not block format, so not read: CZ `curves.txt`, `padmap.txt`, `zombie_pdv_variations.txt`, CW `sgraph_d.txt`, `sgraph_zombie_d.txt`). Blocks keep their line; `Document.set(block, key, value)` changes one line | **Adding and removing blocks** (a new `cItemPlacement`, a deleted zombie), adding a key to a block, all in the file's own style (CRLF, tabs, sorted keys); addressing a block by its path (`cMissionDefinition X/cMissionLevelReady Y/…`) |
| `convert/placed.py` | Every item, door, spawn point, zombie area (`cZombieWarehouse` polygons, `Thing.parent` = the area name), trigger, map / light / sound area, map point and the nav mesh of a level script, with file and line; every item and door finds its model (CZ 1,060, CW 1,835) | Nothing for objects; the item browser can use `ItemModels` |
| `convert/zombies.py` | `crowds()`: every `cMissionZombieFactory` of the missions run on a level (`cMissionLevelReady LevelName`), its area and amounts per type; `spots()`: example figures spread over the area | **`cMissionSpawnZombie`** (single zombies), **`cMissionSpawnZombieCrate`** (respawns), **`cMissionZombieRemoval`**, **`cMissionAdjustZombieTuning`** and **`zombiesets.txt`** (load sets) are not read yet; crowds carry their mission name but no block path |
| Maps tab (`studio/maps_view.py`, `web/maps.js`) | Layers (zombie areas, zombies, nav mesh, collision…), click → what it is (`dr2:pick`, with file and line for items), Go to, time of day, the in-game map. Items are **one glTF node each** (extras `dr2_name`, `dr2_file`, `dr2_line`), so the page can move one without a rebuild | Selection, a move / turn gizmo (three.js `TransformControls`: **not vendored**, only `OrbitControls`; same three.js 0.186.1, MIT), undo / redo, side-panel editors, a "save into mod" message to Python |
| Collision (`formats/collision.py`, `level.zone_collision`) | Every zone's collision mesh in world space (5 CZ shapes' place unknown) | **Snap to floor** and "is this spot reachable": a ray down onto the collision, not onto the drawn pieces (what the game stands on) |
| Nav mesh (`placed.read_navmesh`) | The polygons zombies walk on | A check that a zombie area or a single zombie stands on it |
| `mods/preview.py` (`Preview`, `ModdedTree`) | Studio shows the switched-on mods with the build's own bytes; Ctrl+M shows the game without them; only the zones a mod touches rebuild | Nothing, once the build knows `.edits.json`: an edit shows "with my mods" for free |
| `mods/build.py` | Whole-file replacements, `.bcs.json` merged by id over the recomp's copy (`base_dirs`); refuses a vpath the game doesn't have | **An `.edits.json` kind**: merge several mods' edits by block path, conflict only on the same key of the same block, applied over whatever file is underneath; **adding new files** (own models: a new pack, a new zone entry) for step 5 |
| `formats/level.py` placements | `ZONE_ORGANIZATION.big` records parse and write back identically (`placements_bytes`, census), placement maths checked to 0.8 mm (CZ) / 8 mm (CW) | For step 4 only: writing a changed table |
| Time of day (`mapdata.light_table`) | The hour slider | `zombiesets.txt` entries have their own clock (`start` / `end` in seconds from Day 1 0:00): the zombie view should pick the load set by game time, not the light hour |

Studio has **no "mod being edited"** yet (the Mods window manages the library; editing
writes into a mod folder only through *Edit in image editor* and the text editor):
step 2 needs one (pick or create the mod the edits go to).

## What the research found

### Where zombies come from (both games, plain text, not digest-checked)

Zombies are **not** placed in the level files; the **missions** spawn them
(`data/datafile.big/missions.txt`, inside each `cMissionDefinition`, under a
`cMissionLevelReady` block for a level). Counts CZ / CW:

| Block | CZ / CW | What it does | Keys |
|---|---|---|---|
| `cMissionZombieFactory` | 33 / 72 | **A crowd**: fills a named area with zombies | `ZombieWarehouseName` (the area), `Type0…`, `Amount0…` (how many of each), `ClumpSize`, `PercentClump`, `ClumpDiameter`, `ClumpNoise`, `PercentQueen` |
| `cMissionSpawnZombie` | 137 / 155 | **One zombie** (or a few) at a spot | `SpawnPoint` (x,y,z), `Rotation` (one angle), `ZombieType`, `NumberOfZombies`, `SpawnWithItem` (`HandGun`), `SlotFondler`, `QueenInfected`, `SpawnDeadZombie` |
| `cMissionSpawnZombieCrate` | 23 / 60 | **Respawning**: more zombies when the count drops | `ShapeName`, `ZombiesPerSpawnTime`, `TimeBetweenSpawns`, `StartWhenZombiesDropBelow`, `DisableIfChuckIsCloserThan` |
| `cMissionZombieRemoval` | 44 / 29 | Clears zombies around a spot | `Location`, `Radius` |
| `cMissionAdjustZombieTuning` | 2 / 7 | Limits | `MaxNumUpdatingZombies` (120 in CZ's street), `NumberOfAllowableZombiesChasingYouZone0…3`, `WanderingZombies`, `MaxAttractorsForSurvivor` |

The **areas** are `cZombieWarehouse` blocks in the level file (`prologue.txt`: 24, CW
`living_research.txt`: 11): named groups of floor polygons (`cPolygonLarge Ground`,
vertices x,y,z, a height). Every area a CZ factory names exists; CW names one that no
level file defines (`ArenaStairs`).

`zombiesets.txt` ("AUTOGENERATED BY MIDDEN, DO NOT EDIT BY HAND") lists, per level and
time of day, **which zombie types the level loads** and a memory cost per type
(`zombie_fat // 6176`, `total_cost`, `HWM` high-water mark). **A spawn of a type the
level does not load is likely to fail or be skipped** (to check in game): adding a new
type to a level means adding it to its load set, within a memory budget whose limit is
unknown.

### Where objects come from

- **Level objects:** `cItemPlacement` / `cDoorPlacement` /
  `cItemWithAttachedPropsPlacement` in `<level>.txt` (phase 10 §Placed things): name,
  `ItemName`, `Location`, `Rotation` (quaternion), and flags (`IsStatic`, `PropState`,
  `SpawnPropFromCategory`, `FixedOnInitialPlacement`, `IsDispenser`,
  `NonInteractableProp`, `TextureSubType`).
- **Mission objects:** `cMissionSpawnItem` (CZ 146, CW 111) and `cMissionSpawnNPC`
  (survivors, CZ 38, CW 15) in `missions.txt`.
- An `ItemName` must name a block of `items.txt` whose model ships. Every placed item and
  door of both games finds its model (phase 10; ~~CZ is a demo and some don't~~:
  retracted, the research's 482 "missing" were a wrong lookup). An *added* item can still
  name one whose model is missing in CZ: `dr2 mod check` must say so.
- **Level pieces** are binary (`ZONE_ORGANIZATION.big`, 208-byte records,
  `formats.md` §Levels). Moving one is a float edit; adding one means a new record and
  the piece's `.big`/`.tex` in that zone archive. Whether the game accepts more records
  than shipped is unknown.
- **A piece's collision is not in the piece** (found in phase 10's stretch): it sits in
  the zone's `MERGED_COLLISION.big`, one shape per piece node, already placed or in the
  piece's space, with a Havok search tree (`hkpMoppCode`) and edge welding built from the
  triangles. Moving or hiding a piece leaves its collision behind (an invisible wall
  where it was) unless the shape moves too; moving the vertices without rebuilding the
  MOPP tree is untested ❓ and rebuilding it needs Havok's algorithm (not available).
  Items and doors are not in the merged collision (they are separate props).

### What makes a thing work in game (researched 2026-10-11, for prefabs)

Every "usable" thing is a block in a text file, sometimes two, never code:

| Thing | Where | What makes it work | Shipped examples |
|---|---|---|---|
| **Usable item** (weapon, food, tool…) | `<level>.txt` `cItemPlacement` | `ItemName` names an `items.txt` block; its **class** gives the behaviour (`cPlayerWeaponItem` 130 CZ / 120 CW, `cFoodItem`, `cFirearmItem`, `cExplosiveItem`, `cToolItem`, `cSprayItem`…). The placement only says where, and flags (`IsStatic`, `SpawnPropFromCategory`, `FixedOnInitialPlacement`…) | every weapon in the street |
| **Workbench** (combine weapons) | `<level>.txt` `cItemPlacement` | `ItemName = "Workbench"`, a `cComboStationItem` | CZ `Workbench1`, `Workbench2`, the safehouse's |
| Vending / slot machine, clothing rack, pawn shop display | `<level>.txt` `cItemPlacement` | their item classes (`cVendingMachineItem`, `cSlotMachineItem`, `cClothingDispenserItem`, `cPawnShopDisplayItem`) | many |
| **Save point** | `waypoint_<level>.txt` `cTriggerVolume` | **`ActionType = 4`**, `DisplayName = 55094` (the prompt's string id), a box (`Location`, `Rotation`, `Vertex1…4`, `Height`, `Radius`), `ActionPoint` + `ActionActorRotation` (where Chuck stands and faces), `InteractButton = true`, `InteractionRadius`; CW adds `ActionCameraHeading` / `Pitch` and `AnimationChooser` (urinal or stall ❓). The toilet itself is only scenery (a piece) | CZ 4 (`SafehouseSave`, `UncleBills_SaveTrigger`…), CW 34 |
| Its icon on the in-game map | `fe_map*.csv` row (`LEVEL_<SCRIPT>`, kind, position) | phase 10's map points | — |
| **Door to another level** | `waypoint_<level>.txt` `cTriggerVolume` (+ a `cDoorPlacement`) | `ActionType = 3`, `Level = LEVEL_…`, the box and action point | CZ `Safehouse_entrance`, CW `PensUpper` |
| Other trigger actions | same | `ActionType` 28 (load upstairs), 36 (CZ zombification), 57 / 58 (CW Frank on / off) | — |
| **Spawn point** (where Chuck appears) | `<level>.txt` `cSpawnPoint` | name, position, facing | CZ 18 |
| **Zombies into a spawner** | `missions.txt` `cMissionZombieFactory` | another `Type<n>` / `Amount<n>`; the type must be in the level's **load set** (`zombiesets.txt`) | 33 / 72 |
| Single zombie, respawn crate | `missions.txt` | `cMissionSpawnZombie`, `cMissionSpawnZombieCrate` | 137 / 155, 23 / 60 |
| **Static model with collision** (wall, building, road part…) | `items.txt` + `<level>.txt` | an item that can't move: `cBlockingVolumeItem` `wall_long_blocking` (`Unmoveable = true`, `MeshVisible = true`, `CollisionBits`, `CollisionType = 3`); most items get their collision from the engine by `CollisionType` (3 on 316 CZ items), **not** from a Havok mesh (only 99 CZ / 76 CW item models carry one) ❓ to confirm in game | CZ `wall_long_blocking`, `wall_short_blocking` |
| Building piece | the zone archive | a `ZONE_ORGANIZATION` record + the piece's `.big` / `.tex`; lightmapped like the level, but its collision would need a Havok search tree (§Where objects come from) | every building |

**Own models need new files.** A new item model is a new pack
(`streamedassets.big/<Name>.big`, or `MergedFilename`'s `data/dynamicprops/…`) and a new
`items.txt` block; a new piece is new entries in a zone archive. **`mods/build.py` refuses
any vpath the game doesn't have** today ("unknown vpath"), and whether the game finds an
entry added to a `.big` (looked up by name hash) is untested ❓. A new item's on-screen name
needs a string id: reuse one, or add one to the string bank (`.bcs.json` adds ❓).

### The text files as mods

- Plain text, **CRLF** line ends, tabs, keys sorted alphabetically (`Vertex0`,
  `Vertex1`, `Vertex10`…: written by a tool), blocks `cClass Name { … }` nested, files
  end with blank lines; `zombiesets.txt` has `//` comments. Inside `datafile.big`, LZX
  compressed (the build re-encodes, rule 4).
- **Not digest-checked** (the digest lists name no `datafile.big` file), so edited copies
  load, as the CZ recomp's own edits prove.
- **The CZ recomp already edits two of them:** its `assets/game_patched/data/datafile.big`
  differs from the shipped one in `missions.txt` and `outfits.csv` (its co-op changes).
  CW's recomp has no `game_patched`. So **a whole-file `missions.txt` replacement would
  wipe the recomp's co-op edits**, and two mods that each change one zombie in
  `missions.txt` would conflict. `mods/build.py` already patches the recomp's copy
  (`base_dirs`); what is missing is a mod that holds **only its changes**.

## Plan

### 1. Level edits as a mod format: `.edits.json` (like `.bcs.json` for strings)

A mod stores **what it changed, by block name**, not a whole file:
`replace/data/datafile.big/prologue.txt.edits.json`:

```json
{"set":    {"cItemPlacement Scissors1": {"Location": "-140.0,3.399,-89.9"}},
 "add":    {"cItemPlacement MyKatana": {"ItemName": "Katana", "Location": "…", "Rotation": "0,0,0,1"}},
 "remove": ["cItemPlacement Shampoo"],
 "within": {"cMissionDefinition PrologueZombies/cMissionLevelReady PrologueZombieReady": {…}}}
```

- The build applies the edits to **whatever file is underneath** (the shipped one, or
  the recomp's patched one, `base_dirs`), so co-op edits survive and several mods merge
  (one conflict only when two mods set the same key of the same block).
- The level text reader/writer from phase 10 step 2 must write an untouched file back
  **byte-identical** (CRLF, tabs, key order, trailing blank lines): census gate over every
  `.txt` of both games' `datafile.big`. Edited blocks keep the tool's style (sorted keys).
- `dr2 mod check` validates: every `ItemName` / `ZombieType` / `SpawnWithItem` exists in
  `items.txt` / the zombie models, every factory's area exists, positions are numbers,
  quaternions unit length, names unique; it warns when a zombie type is not in the
  level's `zombiesets.txt` load set.

Builds on `levelscript.Document` (add: block insert / remove, key insert, path
addressing) and `mods/build.py` (add: the `.edits.json` kind next to `.bcs.json`);
`mods/preview.py` then shows edits without more work.

### 2. Maps tab: edit objects

- Select an item or door (click, or from a list); **move** (drag on the floor plane,
  arrow keys, or type x,y,z), **turn**, **snap to floor** (ray down onto the zone's
  **collision mesh**, `level.zone_collision`, sent to the page as the collision part),
  **delete**, **duplicate**, **add** from an item browser (the Library's Weapons &
  items, with pictures), **change** what it is.
- The page already has each item as its own node with its file and line; add
  `TransformControls` (vendor it from three.js 0.186.1) and a `dr2:edit {…}` message.
- Every change goes into the mod being edited (the Mod manager's current mod), as
  `.edits.json`; **undo/redo**; the "with my mods" view shows the result at once and
  "without mods" the original (phase 10).
- Flags in a side panel with plain names (static, fixed until picked up, dispenser…),
  their meaning from the game's use where known, raw otherwise.

### 3. Maps tab: edit zombie spawns

- Extend phase 10's **Zombies** layer (crowds only, example figures): read
  `cMissionSpawnZombie` (figures at their spot, type, held item, count),
  `cMissionSpawnZombieCrate` (respawn areas), `cMissionZombieRemoval` (circles) and
  `zombiesets.txt` into `convert/zombies.py`; colour crowd areas by density; a mission
  picker (spawns belong to missions) and the load set for the game time (see the table
  above: its own clock, not the light hour).
- Edit a crowd: types and amounts, clumping; reshape its area (drag polygon points, add
  and remove points); add a new area and a factory for it.
- Edit single zombies: move, turn, type, item, count; add and delete.
- Show the level's **load set** (`zombiesets.txt`) and its budget; adding a type the
  level doesn't load offers to add it (with the measured budget, step 6).

### 4. Level pieces (stretch)

- Move, hide (remove the record), or copy a piece within its zone
  (`ZONE_ORGANIZATION.big` rewrite; reading and writing back identically is done,
  phase 10); a new model as a piece is a further stretch (its `.big` + `.tex` added to
  the zone archive, textures by the first-copy rule).
- **First, the collision question** (§Where objects come from): in the recomp, move a
  piece's record only and see whether its collision stays behind (expected); then move
  the shape's vertices in `MERGED_COLLISION.big` without touching `hkpMoppCode` and see
  whether the game still collides correctly, crashes, or ignores it. Hiding a piece
  could drop its collision shape the same way. Until that is known, a moved or hidden
  piece is shown in the Maps tab with a warning, and only *visual* edits (a piece with no
  collision shape: signs, decals, lights) are offered without one.

### 5. Add your own things: prefabs

A **prefab** is a template for one kind of thing, made from a working example the game
ships, so what you add behaves like it:

- **Prefab data, not code** (`dr2kit/catalog/prefabs.toml`, per game where they differ;
  `ARCHITECTURE.md`: profiles are data): for each prefab, its name and group (*Usable
  items*, *Save points*, *Stations*, *Doors*, *Spawn points*, *Zombies*, *Static
  models*), the shipped block(s) it is cloned from (`waypoint_prologue_safehouse.txt /
  cTriggerVolume SafehouseSave`), which file each block goes to (the level script,
  `waypoint_<level>.txt`, `missions.txt`, `fe_map*.csv`), which keys the editor sets
  (position, facing, the box, the action point: moved with the thing) and which it
  keeps, and the checks it needs.
- **Placing one** in the Maps tab: pick it from a *Add…* palette (pictures from the
  Library), click on the floor (snapped to the collision), turn it; the editor clones the
  template blocks with a new unique name, moves every position key with it (a save
  point's box and its `ActionPoint` together), and saves them as `.edits.json` *adds*.
  A save point also gets its map icon row; a door its target level.
- **Usable items:** any `items.txt` item of a usable class; the palette groups them by
  class and warns when the model doesn't ship in this game.
- **Zombies into a spawner:** pick a crowd (or draw a new area: a `cZombieWarehouse`
  polygon + a factory in the level's mission) and add a type and amount; adding a type
  the level doesn't load also adds it to the load set, with the budget (step 6).
- **Own models** (a new weapon, a building, a road): import a `.glb` (phase 4's model
  import), choose the prefab it behaves like (a weapon class, a static model), and the
  editor writes the new `items.txt` block (cloned from that prefab's item) and the new
  pack. Needs the build to **add new files** (below) and an in-game test of each route.
  Buildings and roads go in as **static items first** (engine-made collision, no Havok
  tree to build); as zone pieces only once step 4's collision test allows. A new road
  zombies should walk on also needs the **navigation mesh** (`nm_<level>.txt`, text)
  extended: an editor for its polygons.
- **Your own prefabs:** save a configured thing (a save point with its toilet, a weapon
  rack) as a prefab file to reuse and share (`.dr2prefab`, plain JSON).
- **Build: new files.** `mods/build.py` learns *adds* (a new pack in `streamedassets.big`,
  a new entry in a zone archive), each checked: the name must not collide (by hash too),
  the archive written back with the real encoder. First test in game: does the engine
  find an added pack? (both games).
- `dr2 mod check` per prefab: a save point has its action point inside the box and on
  the floor; a door's level exists; an item's class is usable and its model ships; a
  zombie type is loaded; names are unique.

### 6. In-game proof and limits (both games)

- Each kind of edit (moved item, added item, removed item, changed crowd, added single
  zombie, reshaped area, new zombie type in a level) **checked in the recomp**, with
  captures (on disk, copy of the save, `CZ_BUG_REPORTS=0`, `timeout -s KILL`).
- Measure the limits that matter: how many items a level holds, how many zombies
  (`MaxNumUpdatingZombies`), the load-set budget, whether a factory's amounts are
  capped, how many triggers / save points a level takes. Write them into guide 15
  (engine limits).
- Prefabs, each in game: an added weapon picked up and used; an added save point saves
  (and loads back there); an added workbench combines; an added door goes to its level;
  zombies added to a crowd appear; a static model blocks the player (the
  `CollisionType` question); an own-model item (a new pack) loads.

### 7. A guide: `modding/19-edit-a-level.md` (after phase 10's `18-maps.md`)

Studio steps first (select, move, add from a prefab, zombies, your own model), then the
`.edits.json` and prefab formats, then
`dr2` CLI (`dr2 level set/add/remove …`), troubleshooting (item not in this game,
type not loaded, the recomp's co-op edits kept).

## Decisions to take (ask the user; proposed defaults)

- **Edits as `.edits.json` by block name** (merge-friendly, keeps the recomp's co-op
  edits), not whole-file `.txt` replacements. A modder can still ship a whole `.txt`;
  the build warns that it replaces the recomp's edits.
- **Zombie editing per mission**, with the street's main mission (CZ
  `PrologueZombies`) shown first; or a simpler "level view" that shows every mission's
  spawns at once with a filter.
- **Pieces (binary) are a stretch**; items, doors and zombies (text) are the goal. A
  moved piece needs its collision moved too (Havok search tree not rebuildable):
  limit piece edits to pieces without collision until the in-game test says more?
- **New zombie types in a level:** allowed with a warning and the measured budget, or
  refused until the budget is known.
- **Prefabs:** shipped as data (`prefabs.toml`, cloned from the game's own examples) plus
  the modder's own `.dr2prefab` files, proposed default. Own models: as **static items
  first** (engine collision), zone pieces only after the collision test?
- **Adding new files** (own models): the build learns to add packs and zone entries,
  after an in-game test that the engine finds them.
- **Where edits are saved:** a "mod being edited" picked in the Maps tab (new mod or an
  existing one from the library), proposed default; or always a new mod per level.

## Gate (both games)

- Census: every block-format `.txt` of `datafile.big` reads and writes back
  byte-identical (already true: CZ 24, CW 39; the 5 other formats named above); every
  `.edits.json` applied then reversed gives the original.
- Studio: move a weapon, add one, delete one, change a crowd's amounts and area, add a
  single zombie with an item; "without mods" (Ctrl+M) shows the original; `dr2 mod check`
  passes; the moved weapon snapped to the collision floor; from prefabs: a weapon, a save
  point, a workbench, zombies into a crowd, and a static model of your own.
- In game: each of those edits seen in the recomp (captures), and in CZ the recomp's
  co-op edits to `missions.txt` still present in the deployed file; each prefab
  **works**, not just shows (the added save point saves, the weapon is used, the static
  model blocks the player).

## Facts to keep in mind

- `missions.txt` holds much more than spawns (objectives, NPCs, timers): edits must touch
  only the blocks they name.
- Zombie `Rotation` in `cMissionSpawnZombie` is one angle (radians, `-3.1`…), item
  `Rotation` a quaternion.
- Mission blocks are nested several levels deep; names are unique per parent, not
  globally (`x2009` factory names): address blocks by their path.
- The recomps stay read-only; the `game_patched` copy is read as a base, never written.
  CZ's has `datafile.big` (its co-op `missions.txt` / `outfits.csv`); CW's recomp has no
  `game_patched` folder (checked 2026-10-11).
- A level texture shared by several packs of a zone uses its **first** copy (phase 10,
  seen in game): a piece edit that adds textures must follow that rule.

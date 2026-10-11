# Edit a level: move items, change zombies, add your own things

**You will:** move, add and remove items in a level, change how many zombies of which
types a crowd has, and save it all as a mod that keeps working beside other mods.   **Time:** ~10 min.   **Games:** both.
**You need:** the toolkit with your game folders set ([`02-game-data.md`](02-game-data.md)),
and a mod to put the changes in ([`06-mod-packages.md`](06-mod-packages.md)). Look at the
level first in the **Maps** tab ([`18-maps.md`](18-maps.md)): it shows every item's name,
file and line when you click it.

> This guide grows with phase 11. Written so far: editing items, doors and zombies in
> the Maps tab, the edits files and the `dr2 level` commands. Next: adding things from
> prefabs (save points, workbenches…).

## How the game places things

Nothing in a level is placed by code. Plain **text files** inside
`data/datafile.big` say what goes where ([glossary](../glossary.md#level-script)):

| File | What it holds | Example block |
|---|---|---|
| `prologue.txt` (Case Zero's street; Case West: `living_research.txt`…) | items and doors, spawn points, zombie areas | `cItemPlacement Scissors1` |
| `waypoint_prologue.txt` | triggers: doors to other levels, save points | `cTriggerVolume SafehouseSave` |
| `missions.txt` | the zombies (crowds, single zombies, respawns), mission items and survivors | `cMissionZombieFactory x2009` |
| `zombiesets.txt` | which zombie types each level loads, by time of day | `cZombieLoadSet LEVEL_PROLOGUE` |

Each thing is a **block**: a class, a name, and its settings:

```
cItemPlacement Scissors1
{
	IsStatic = ""
	ItemName = "Scissors"
	Location = "-140.911,3.399,-89.938"
	Rotation = "0.411,0.410,0.573,0.578"
}
```

`ItemName` is what it is (a block of `items.txt`, which gives its model and how it
behaves), `Location` where (x, y, z in metres; y is up), `Rotation` which way it is
turned (a *quaternion*: four numbers, don't type them by hand, copy them from another
block). Zombie spawns sit inside missions, several blocks deep, so a block is named by
its **block path**: the blocks around it joined with `/`:
`cMissionDefinition MainMenuZombie/cMissionLevelReady MainMenu/cMissionZombieFactory MenuZombies`.

## Why a mod holds only its changes

A mod doesn't replace the whole `prologue.txt`. It keeps a small **edits file**,
`replace/data/datafile.big/prologue.txt.edits.json`, that lists only what it changes:

```json
{"format": "dr2kit-level-edits/1",
 "set":    {"cItemPlacement Scissors1": {"Location": "-140.0,3.399,-89.0"}},
 "add":    {"cItemPlacement MyHammer": {"ItemName": "SledgeHammer",
                                        "Location": "-140.0,3.399,-89.0",
                                        "Rotation": "0.411,0.410,0.573,0.578"}},
 "remove": ["cItemPlacement Shampoo"]}
```

- **set** changes settings of a block (`null` instead of a value removes the setting),
- **add** puts in a new block (a setting that is itself `{…}` is a block inside it),
- **remove** takes a block out (with everything inside it).

Why: **the Case Zero recomp changes `missions.txt` itself** (its co-op changes), and two
mods that each moved one zombie would wipe each other out if each carried a whole copy.
With edits files, the toolkit applies every mod's changes to the file the game really has,
so the recomp's changes stay and several mods work together. Two mods only clash when
they change the *same setting of the same block*; then the one later in the load order
wins, and the mod manager tells you.

## Steps: move, turn, add and delete items in DR2 Studio

1. Open or create the mod your changes go into (bottom bar: **New mod…** or **Open
   mod…**). Every change is saved into it at once; there is no Save button.
2. Click the **Maps** tab and open a level (see [`18-maps.md`](18-maps.md)), then fly to
   the place you want to change.
3. Tick **Edit items and doors** in the right panel (under *Edit*). The panel says which
   mod the changes are saved into.
4. **Click an item or door.** A yellow box marks it and **handles** appear on it, and
   the panel shows what it is (**Item**), where (**Place**: x, y, z in metres, y is up)
   and its **Turn** (degrees).
5. **Move it:** drag one of the coloured arrows (red: x, green: y up, blue: z) or the
   small squares between them (two directions at once). Or type a new **Place**.
6. **Turn it:** press **R** (the handles become a green ring), drag the ring; **T**
   goes back to moving. Or type a **Turn** in degrees.
7. **Onto the floor:** press **F** (or **Onto floor**). It drops onto the floor below it,
   the one the game walks on (the collision mesh, [glossary](../glossary.md)), so it
   doesn't float or sink.
8. **Copy:** **Ctrl+D** (or **Copy**) puts another one beside it, with the same
   settings. **Delete:** **Delete** (or the button) takes it out of the level.
9. **Make it something else:** type another item's name in **Item** (it suggests names
   as you type), press Enter. The new model shows at once.
10. **Add one:** **Add item…**, pick an item (type to search: only items whose model
    this game has are listed). It goes where the middle of the view meets the floor;
    move it from there.
11. **Undo / Redo:** **Ctrl+Z / Ctrl+Y** (or the buttons), as many times as you like.
12. Click **Play** to try it in the game.

Click in the view first if the keys don't respond. While you move things, the level is
not rebuilt: the change shows at once. The mod's file list (bottom left) shows the
level files it changes.

**Saves:** a mod that adds items (and a save point) to a level file still loads your
saves (checked in Case Zero, 2026-10-11, with added items, a workbench and a save point;
moving and deleting not yet checked).

## Steps: change the zombies in DR2 Studio

Read [Zombies: what you can change](#zombies-what-you-can-change-and-new-zombies) first:
the game's saves set the rules.

1. With **Edit** ticked (as above), tick the layers **Zombie spawns** (single zombies:
   red cones facing their way, labelled *type ×number*; *(later)* when they wait for
   something in their mission; respawn floors in orange; blue circles where a mission
   clears zombies), **Zombies** (example crowds) and **Zombie areas**.
2. **A single zombie:** click its cone. Drag the handles (or type **Place**, **Turn**)
   to move and turn it, **F** puts it on the floor. Under the place: **Zombie** (its
   type; it suggests names as you type), **×** (how many), **Holds** (an item it carries,
   such as `HandGun`). **Delete** sets the number to 0: the game's own zombies are taken
   out this way, which keeps saves working.
3. **A crowd:** click one of its zombies (or its zombie area). The panel shows the
   crowd's types and amounts as a line, `zombie_skinny 40, zombie_fat 30`. Type a new
   line (`zombie_fat 15, zombie_cop 10`) and press Enter.
4. **New zombies:** **Add zombie…**, pick a type: they go where the middle of the view
   meets the floor, in your mod's own mission. **They appear in a new game only**
   (start one to see them); then move, turn and change them like the others.
5. **Undo / Redo** and **Play** as for items.

## Steps: change a level with the `dr2` command

1. Make a mod if you haven't: `dr2 mod new my_level_mod`.
2. Look at a block, as the game has it:

   ```
   dr2 level show prologue "cItemPlacement Scissors1" -g cz
   ```

   (`dr2 level show prologue -g cz` lists every block of the file.)
3. **Move it:** set its `Location` (and `Rotation` to turn it):

   ```
   dr2 level edit my_level_mod prologue set "cItemPlacement Scissors1" Location=-140.0,3.399,-89.0 -g cz
   ```

4. **Add one**, copying another block's settings and changing what it is:

   ```
   dr2 level edit my_level_mod prologue add "cItemPlacement MyHammer" --like "cItemPlacement Scissors1" ItemName=SledgeHammer -g cz
   ```

   The name after the class (`MyHammer`) must be new in that file.
5. **Remove one:** `dr2 level edit my_level_mod prologue remove "cItemPlacement Shampoo" -g cz`
6. **More zombies in a crowd:** zombie crowds are `cMissionZombieFactory` blocks of
   `missions.txt`; `Type0`, `Type1`… are the zombie types and `Amount0`, `Amount1`… how
   many:

   ```
   dr2 level edit my_level_mod missions set "cMissionDefinition MainMenuZombie/cMissionLevelReady MainMenu/cMissionZombieFactory MenuZombies" Amount0=60 Type1=zombie_fat Amount1=5 -g cz
   ```

7. Check it: `dr2 mod check my_level_mod -g cz`. It refuses mistakes the game would trip
   on (an `ItemName` the game doesn't have, a zombie type that doesn't exist, a crowd
   area the level doesn't have, a broken rotation) and warns about doubtful ones (an item
   whose model this game doesn't ship, a zombie type the level doesn't load).
8. Play: `dr2 play -g cz`, or **Play** in DR2 Studio.

Every `edit` saves the mod's edits file at once. Run `dr2 level edit … set … Key=` (an
empty value) to remove a setting.

**Edited a whole `.txt` in a text editor?** Turn it into an edits file:
`dr2 level diff prologue my_prologue.txt --mod my_level_mod -g cz` keeps only what you
changed (`dr2 level diff prologue my_prologue.txt` prints it instead).

## Zombies: what you can change, and new zombies

Zombies belong to the game's **missions** (`missions.txt`), and the game's saves remember
every mission. Tested in Case Zero:

- **Change the game's own zombies freely:** a crowd's types and amounts (and add a type
  to it: `Type3` / `Amount3`), a single zombie's type, place, facing or number. Your saves
  keep working. (Making every zombie of the street a cop, as a test, worked.)
- **Never add a block inside one of the game's missions:** the game then can't load your
  saves and a new game stalls. `dr2 mod check` and DR2 Studio refuse it.
- **New zombies go in a mission of your own**, a new `cMissionDefinition` at the top of
  `missions.txt`, with a `cMissionLevelReady` for the level and the zombies inside. It
  appears in a **new game**; a save made without your mod doesn't start it. Copy the
  settings of the level's main zombie mission (Case Zero's street: `PrologueZombies`):

  ```
  dr2 level show missions "cMissionDefinition PrologueZombies" -g cz
  ```

## Zombie types and the load set

A level only loads some zombie types (`zombiesets.txt`, by time of day: Case Zero's
street loads `zombie_fat`, `zombie_skinny`, `zombie_skinny_female`, `pro_zombie_trucker`,
`zombie_bertha`, `zombie_cop`, `zombie_waitress`, `zombie_soldier`, `pro_zombie_bowling`
from 7:00). Another type still showed in a test (8 `pro_zombie_cop` in the street), but
it uses memory the level didn't plan for, so `dr2 mod check` warns *"… is not in LEVEL_…'s
load set"*: keep such numbers small.

## Troubleshooting

| You see | Why | Fix |
|---|---|---|
| `no block 'cItemPlacement X'` | the name or class is spelled differently, or it is in another file | `dr2 level show <file>` lists the blocks; items are in `<level>.txt`, triggers in `waypoint_<level>.txt` |
| `2 blocks named 'cMissionLevelReady Ready'` | that name is used twice at that place | write the full path from the mission (`cMissionDefinition …/…`) |
| `ItemName 'Katana' is not an item of this game's items.txt` | Case Zero doesn't have every Case West item | pick another (`dr2 level things prologue --kind item -g cz` lists the ones in use) |
| `… replaces … as a whole, so the recomp's own changes to it are lost` | a mod has a whole `missions.txt` | turn it into an edits file with `dr2 level diff` |
| `changed by both A and B at the same priority` | two mods set the same setting of the same block | change one, or order them in the mod manager |
| `adds a block inside one of the game's own missions` | the game would fail to load saves | change the game's zombies' values, or put new ones in a mission of your own (above) |
| New zombies don't show | they are in your own mission: it runs in a new game only | start a new game |

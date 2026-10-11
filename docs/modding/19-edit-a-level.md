# Edit a level: move items, change zombies, add your own things

**You will:** move, add and remove items in a level, change how many zombies of which
types a crowd has, and save it all as a mod that keeps working beside other mods.   **Time:** ~10 min.   **Games:** both.
**You need:** the toolkit with your game folders set ([`02-game-data.md`](02-game-data.md)),
and a mod to put the changes in ([`06-mod-packages.md`](06-mod-packages.md)). Look at the
level first in the **Maps** tab ([`18-maps.md`](18-maps.md)): it shows every item's name,
file and line when you click it.

> This guide grows with phase 11. Written so far: the edits files and the `dr2 level`
> commands. Next: editing in the Maps tab, zombie spawns, adding things from prefabs.

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

## Zombie types and the load set

A level only loads some zombie types (`zombiesets.txt`, by time of day: Case Zero's
street loads `zombie_fat`, `zombie_skinny`, `zombie_skinny_female`, `pro_zombie_trucker`,
`zombie_bertha`, `zombie_cop`, `zombie_waitress`, `zombie_soldier`, `pro_zombie_bowling`
from 7:00). A crowd of a type the level doesn't load will probably not appear: `dr2 mod
check` warns *"… is not in LEVEL_… 's load set"*. How much a level can load (a memory
budget) is being measured; until then, prefer the types it already loads.

## Troubleshooting

| You see | Why | Fix |
|---|---|---|
| `no block 'cItemPlacement X'` | the name or class is spelled differently, or it is in another file | `dr2 level show <file>` lists the blocks; items are in `<level>.txt`, triggers in `waypoint_<level>.txt` |
| `2 blocks named 'cMissionLevelReady Ready'` | that name is used twice at that place | write the full path from the mission (`cMissionDefinition …/…`) |
| `ItemName 'Katana' is not an item of this game's items.txt` | Case Zero doesn't have every Case West item | pick another (`dr2 level things prologue --kind item -g cz` lists the ones in use) |
| `… replaces … as a whole, so the recomp's own changes to it are lost` | a mod has a whole `missions.txt` | turn it into an edits file with `dr2 level diff` |
| `changed by both A and B at the same priority` | two mods set the same setting of the same block | change one, or order them in the mod manager |

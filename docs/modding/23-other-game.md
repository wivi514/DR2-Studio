# Use the other game's items, zombies and levels: Case West's in Case Zero, Case Zero's in Case West

**You will:** put an item of the other game (Case West's Laser Sword in Case Zero, a Case
Zero item in Case West) into your mod, with everything it needs, and place it in a level;
or a zombie type, or a [whole level](#a-whole-level-of-the-other-game) with a door to it.
**Time:** ~5 min.   **Games:** both, **and you need both games' data** on your computer.
**You need:** the toolkit with **both** game folders set
([`02-game-data.md`](02-game-data.md): **Game folders…** in DR2 Studio) and a mod
([`06-mod-packages.md`](06-mod-packages.md)).

> Phase 15, started 2026-10-12. Every item of each game plans into the other with no
> name left unresolved (`dr2 census --import`), and a mod with one builds. **Seen
> loading (headless, 2026-10-13):** Case West's Laser Sword lying in Case Zero's street,
> Case Zero's Parasol in Case West's Storage Pens. **Not yet played** (tests U1-U3: does
> it draw right, swing, sound right): treat an imported item as an experiment and keep a
> copy of your save.
>
> The game keeps room for a fixed number of shaders; the recomps were changed on
> 2026-10-12 to keep room for many more, so a recomp **older than that** crashes while
> loading a mod whose item brings many shaders ("Shader constant set overflow" in the
> log). Update the recomp if you see that.

## Why both games are needed

A mod made with the toolkit never contains the games' files (that's what makes it safe to
share). An imported item is a **recipe**: "copy the Laser Sword's model from Case West".
The recipe is followed on the computer that builds the mod, from **its own** copy of Case
West. So whoever plays your mod needs both games, and the mod says so: DR2 Studio and
`dr2 mod info` show *Made from Case West's files* ([guide 06, What a mod
needs](06-mod-packages.md#what-a-mod-needs)).

## What comes with the item

Both games run the same engine, so models, textures, sounds and animations cross over as
they are. What differs is which **names** each game knows. The importer goes through
every setting of the item (its block of `items.txt`) and decides, for each name:

| What | What happens |
|---|---|
| The model | copied from the other game, drawn with **that game's own shaders**, which are copied into this game's shader banks under new names (the two games compiled their shaders differently). Each brought shader is changed to read its settings (fog, lights…) where **this** game's engine puts them: the two games keep them in different places, and without the change a Case West weapon drew flat white in Case Zero. A setting only Case West's engine fills (its "power is on" switch, which lights self-lit parts such as the Laser Sword's blade) is fixed to *on* |
| Its moves (`AnimBankName`) | the other game's move bank is copied when this game lacks it |
| Its sounds (`AudioFilename`) | the other game's sound bank is copied when this game lacks it |
| Its name and texts | new text numbers in your mod; the words are read from the other game's text when the mod is built, in every language |
| Effects (fire, sparks…) | matched **by name**: the two games number them differently after 370. An effect this game doesn't have is **brought** into one of the effect table's free numbers (the same ones [your own effects](21-effects.md) use), with any particle picture this game lacks; two imported items needing the same effect share its number. There are 36 free numbers; when your mod has used them all, the effect is left off (listed) |
| Other items it names (a combo's two items, a weapon's pieces) | kept if this game has them, otherwise imported too |
| A combo card | its picture copied, its card number changed if this game uses it |
| Its moves in the game's animation graph | brought when this game lacks them (the Impact Hammer's attacks; the Laser Sword's are already in Case Zero) |
| Its sound kind (`PropAudioType`) | only the kinds this game's program knows are kept (Case West's Impact Hammer has one Case Zero doesn't, which crashed the load) |
| Parts this game's program doesn't know (Case West's `cExternalLocatorItem`, `cTurretInfoItem`…) | left out, listed: Case Zero's program couldn't build them; a setting naming a part left out is left out too |
| How it is held | a Case West item that picks one of several hand points through a part Case Zero doesn't know (the Impact Hammer, its BFG, the Shovel, a water bottle, the broken pool cue) gets that hand point made the first one, the one Case Zero uses: otherwise the hammer was held upside down |
| The model's insides | made the way this game's program reads them: a Case West model gets the node list Case Zero needs (without it Case Zero hangs while loading) |
| A model this game has under the same name (`clothesbox`, `bowieknife`) | this game's own copy is used: it is the same object |

The window shows this list for the item you pick before anything is written.

## Steps

### In DR2 Studio

1. Open your mod (**Open mod…** / **New mod…**) and pick the game it is for (the game
   box in the toolbar): this is the game the item goes **into**.
2. Click **Other game's items…** (under the mod's buttons).
3. Type part of the name in the filter (`laser`), click the item. The right side says what
   comes with it: what is brought, renumbered or left out, and why.
4. Click **Add to mod**. The mod now holds the recipes, the item's block of `items.txt`
   and the text copies; its `mod.toml` says it needs both games.
5. Place it: **Maps** tab → **Add item…** → type its name (`LaserLightSword`)
   ([guide 19](19-edit-a-level.md)).
6. **▶ Play**.

### With the `dr2` command

```
dr2 mod import-item my_mod LaserLightSword --from cw -g cz -n   # only say what it does
dr2 mod import-item my_mod LaserLightSword --from cw -g cz      # add it to the mod
dr2 level edit my_mod prologue add "cItemPlacement MyLaser" ItemName=LaserLightSword Location=-278.5,3.39,-36.5
dr2 mod info my_mod                                              # it needs both games
dr2 play -g cz
```

## Check it worked

`dr2 mod info my_mod` lists *Made from Case West's files*; `dr2 mod build my_mod -g cz -o
out` builds without errors. In game, the item lies where you placed it.

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| `… needs Case West's game data on this computer` | The other game's folder isn't set | **Game folders…** in Studio, or `dr2 games set cw <folder>` |
| `Case Zero already has an item named X` | Both games have it | Use this game's own (place it from the Maps tab) |
| The window says *This window needs both games' data* | Same as the first row | Same fix |
| The game crashes as soon as guards appear | They are in a crowd (`cMissionZombieFactory`) | Retype single zombies instead (`dr2 mod check` warns) |
| Guards stand, aim once and fall over | An older toolkit gave them Case West's behaviour | Import them again with this toolkit |
| A brought item or zombie is flat white, without its textures | An older toolkit built it (before 2026-10-13 brought shaders read their settings from the wrong places) | Build again (**Play**, or `dr2 play`) with this toolkit |
| An effect is missing on the weapon | The report says *… no free effect slot is left* | Your mod's effects (yours and brought ones) used all 36 free numbers: take some out (**Effects…**, guide 21) or split the mod |
| The game hangs on the loading screen, or stops with a fault, after you placed a Case West item | An older toolkit built it (the model lacked a part Case Zero needs, written since 2026-10-13), or an item kind Case Zero can't use | Build again with this toolkit; if it still happens, take the item out and tell us which one |

## The other game's zombies

Case West's zombie types (the gas zombies, the security guards, the female fat zombie)
can be added to Case Zero **as real types of their own**, spawned like Case Zero's.

Why it works: Case Zero's program has room for **32 zombie types** (the whole of Dead
Rising 2's list) and ships 12, so 20 **slots** are empty. A Case West type takes one: its
own name when Case Zero's list has it (`zombie_gas`, `zombie_fat_female`), otherwise a free
name such as `zombie_bride`. Then, as for an item, the importer brings:

| What | What happens |
|---|---|
| The model and its detail levels | copied from Case West under the slot's name, drawn with Case West's own shaders |
| Its settings (health, damage, how it fights) | Case Zero's settings for that slot get Case West's |
| Its behaviours | Case Zero's own when it has one of that name, else brought |
| **An armed guard** (`security_light`, `security_light_hat`) | goes into one of Case Zero's **mercenary** slots and fights with **Case Zero's soldier behaviour** (`ArmyMerc`): with Case West's own (`EnemyRanged`) a guard aimed once, then fell over like a zombie, because Case Zero's animations lack its moves. Its **rifle** comes too (Case West's `SecurityAssaultRifle`, also under the name `MercAssaultRifle`, the gun Case Zero's program gives its mercenaries): it shoots, and a dead guard drops it for you to pick up |
| Its moves and voices | the animation and voice banks Case Zero's own files already name but don't ship (the gas zombies' `gaszombies.big` and their six voices) are copied: without the voices the street's load crashed |
| A level's zombie list (the *load set*) | it is added to the levels you name |
| **Memory** | the import says how much of the game's **Zombie heap** the type takes when it is loaded (its model and textures: the gas zombie 4.1 MB). The game makes that heap 30.2 MB, and Case Zero's street already fills it to 1.6 MB with its own zombies; the recomps (from 2026-10-13) make it 16 MiB bigger, which leaves 18.4 MB there. The import **warns** when your type fits only in the bigger heap (players with an older recomp crash while the street loads, "Failed to allocate memory") or not even there: then, where it spawns, it must **replace** a Case Zero type at least that big in the crowds (`zombie_skinny` 9.6 MB, `zombie_fat` 8.6 MB, `zombie_skinny_female` 4.6 MB) |
| A full load set | a level's load set lists at most **13** types per time of day (a 14th crashes the game as it starts). When it is full, the import leaves your type out of it and says so: it still loads wherever something spawns it |
| **The heavy and lab guards** (`security_heavy`, `security_lab`) | their way of fighting is Case West program code that Case Zero doesn't have, so they become **Case Zero soldiers** with a rifle, like the light guards (single spawns only) |

Then spawn it with the slot's name: **Maps** tab → a crowd's type or a zombie's type
([guide 19](19-edit-a-level.md)). **Armed guards one at a time only:** retype single
zombies (the Maps tab, or a mission's `cMissionSpawnZombie`), never a crowd: a crowd that
spawned guards crashed the game as soon as they appeared, and `dr2 mod check` warns about
it. Changing a single zombie's type is safe for saves (adding new spawns to the game's own
missions is not, [guide 19](19-edit-a-level.md)).

```
dr2 mod import-zombie my_mod zombie_gas --from cw -g cz --level prologue
dr2 mod import-zombie my_mod security_light --from cw -g cz --level prologue
dr2 level edit my_mod missions set "cMissionDefinition PrologueZombies/cMissionLevelReady PrologueZombieReady/cMissionSpawnZombie SherriffDept1" ZombieType=mercenary -g cz
```

> **Played in Case Zero (2026-10-13)**: gas zombies in every street crowd, and security
> guards in single spawns near the Sheriff's office: they carry their rifles, fight, and
> drop the rifle when they die. Too much at once runs out of memory: the guards, the gas
> zombies and two other brought weapons in the street together stopped the load ("Failed to
> allocate memory"); any two of them load. The full Zombie heap was the cause (measured
> 2026-10-13, [formats.md §Engine memory](../formats.md#engine-memory-the-heaps--measured-phase-15-2026-10-13));
> the recomps now give it 16 MiB more, and the same mix loads (headless). **Case Zero's zombies in Case West** need Case West's
> program to have room for more than its own 10 types: that is a change to the Case West
> recomp, not done yet (open for contributors: [`docs/TODO.md`](../TODO.md) #1), so the
> command says so and stops.

## A whole level of the other game

You can bring a **whole level**: Case West's Storage Pens into Case Zero, with its
buildings, items, zombie areas and doors, reached through a door of its own in the street.
(Case Zero's street into Case West works the same way, but is not seen working yet: below.)

Why it works: each game's program has a fixed list of **level slots** (Case Zero has 82,
named after Dead Rising 2's places: `food_barn`, `palisades_mall`…; Case West has 10).
Only a few hold the game's own levels; the rest are **empty**, and a level put under an
empty slot's file names loads like the game's own. Not every empty slot works: when a
level loads, the game also loads its **audio scene** (the level's sounds and music),
and an empty slot whose audio scene the game doesn't ship (`FoodBarn`) stalls on the
loading screen. A file of that name in your mod doesn't help either: the game checks those
files against a list built into the program and crashes on any other. So the toolkit only
offers the slots that load: **42 in Case Zero**, `w_mall` in Case West (`dr2 level slots`
lists them all and says why).

What the import does, the same way as for an item:

| What | What happens |
|---|---|
| The level's **zones** (its buildings, floors, lights, collision) | copied from the other game, drawn with its own shaders |
| Its **text files** (where every item, door, spawn point and zombie area is) | copied under the slot's names, every name checked |
| Its **items** | the ones this game lacks are brought, like **Other game's items…** (Storage Pens brings 54) |
| Its **doors** to the other game's levels | lead **back** to where you came from (in Case Zero: out of the safehouse door); keys and "locked" messages are taken off |
| Its **zombies** | the other game's zombie mission for that level becomes a mission of your mod (crowds, single zombies, crates), and its zombie types are this game's own or brought ([above](#the-other-games-zombies)). Armed guards are left out of crowds (a crowd spawning them crashes the game) |
| Its **zombie list** (load set) | made for the slot from the other game's |
| An **entry door** | added to this game's level, with the level's name as its prompt ("Storage Pens") |

Not brought: the other game's story missions, the in-game map (it shows nothing there),
the level's own sounds and music (a slot plays its own audio scene: Case Zero's
`prologue_bowling` plays the street's, most others none).

> **Seen in Case Zero (headless, 2026-10-13):** the door by the safehouse exit shows
> *Storage Pens*, the level loads, and Chuck walks in Case West's pens, textured and lit,
> with zombies. **Not yet played by a person** (test U4): the doors out, the items, the
> zombies in a new game. **Case Zero's street in Case West** (test U5): the door triggered
> the transition, but the imported Prologue load crashed in Case West (2026-10-14). The
> 32 MiB Zombie heap increase did not fix it. A 64 MiB retry is ready, but has not been
> tested in the Prologue yet. Keep a copy of your saves.

**Your saves:** the level's zombies come from your mod's own mission, which starts only
in a **new game**, and a save made with it, or made inside the brought level, needs the
mod: loaded without it, the game crashes ([guide 19](19-edit-a-level.md#zombies-what-you-can-change-and-new-zombies)).

### In DR2 Studio

1. Open your mod and pick the game it is for (the game box in the toolbar): the level goes
   **into** this game.
2. Click **Other game's levels…** (under the mod's buttons).
3. Pick the **Level** (`storage_pens`), the **Slot** (the first free one is fine), and
   where the **Door** goes (`x,y,z`; the default is by the safehouse exit in Case Zero,
   in the Storage Pens in Case West). Click **Show what it does**: the report lists what
   is brought, what leads back, what is left out and why.
4. Click **Add to mod**. Studio then builds the level's zones in the background (a few
   minutes, once: they are kept for the next builds). Leave the window open until it says
   *Done*.
5. **▶ Play**, go to the door and press the button it shows.

### With the `dr2` command

```
dr2 level slots -g cz --free                                   # where a level can go
dr2 mod import-level my_mod storage_pens --from cw -g cz -n    # only say what it does
dr2 mod import-level my_mod storage_pens --from cw -g cz       # add it (and build the zones)
dr2 mod import-level my_mod storage_pens --from cw -g cz --slot x_prologue --door -270,3.3,-40
dr2 play -g cz
```

The first build of a brought level converts ~160 MB of the other game's zones (2 minutes
on a 16-thread computer, longer on fewer); the result is kept in the toolkit's cache
folder (`recipes/`), so later builds take seconds. Delete that folder to free the space.

### If the level doesn't work

| Symptom | Cause | Fix |
|---|---|---|
| The door shows no prompt | It is somewhere Chuck can't stand | Move it: `--door x,y,z` (copy a position from the Maps tab) |
| Stuck on the loading screen after the door | A slot whose audio scene the game doesn't ship (an older toolkit offered them) | Import again into a slot `dr2 level slots --free` lists |
| Stuck loading, or a fault, with a level built by a toolkit before 2026-10-14 | Its archives were laid out with extra padding, which the game's level streaming misreads | Build again with this toolkit |
| No zombies in the brought level | You loaded a save: the zombies come in a new game | Start a new game (keep your old saves: they don't need the mod) |
| `… is not a zombie area of …` from `dr2 mod check` | An older toolkit | Update the toolkit |

## Going further

- What a mod needs, and the `requirements.json` a launcher reads:
  [guide 06](06-mod-packages.md#what-a-mod-needs).
- How it works, for developers: `dr2kit/mods/importitem.py`, `dr2kit/mods/importlevel.py`,
  `dr2kit/convert/shadercarry.py`, [`formats.md`](../formats.md) §"Across the games:
  shader banks", [`phase15-kickoff.md`](../phase15-kickoff.md).

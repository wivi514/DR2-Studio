# Phase 15 kickoff: Case West in Case Zero and Case Zero in Case West, and what a mod requires

> **Status 2026-10-12 (night): researched and planned, not started.** Prepared while the
> user is away (their words: "while I am not there we'll prepare the next phase"). Phase
> 14's in-game tests (T4a, T4b, T5) still come first when they are back
> (`phase14-kickoff.md` §Start here). Phase 16 (the same from the PC games):
> [`phase16-kickoff.md`](phase16-kickoff.md).

**Direction (user, 2026-10-12):** "be able to use items from Case West in Case Zero and
items from Case Zero in Case West, also import a map from one to the other with all the
items, zombie placement and all the building environment, all properly done so they can
talk to each other and work normally. This includes mutant zombies, special bosses and
all, so when importing from the other game everything gets **automatically assigned
properly so it doesn't crash**. Also a little file saying the mod requires this game and
this game, so when these mods go into something else like **XenonLive** it tells you that
you need these to play this mod, or else incompatible."

## The rule that shapes everything: mods hold recipes, so the player needs both games

A mod made with the toolkit holds only the modder's own work (LICENSE; ARCHITECTURE.md
"New files"): a new item is a **recipe** that copies a pack from the player's own game
when the mod is built. A Case West item in Case Zero is the same recipe **reading the
other game**, so building the mod needs Case West's data on the player's machine. That is
exactly what the requirements file says (§Requirements): *this mod is for Case Zero and
needs Case West installed*.

## What the research found (2026-10-12, both games' data and executables)

### Same engine, same formats, same rigs

Every format the toolkit reads is the same in both games (one reader, profiles for the
differences: phases 1-14). Chuck's and the zombies' rigs are the same skeletons (animation
skeleton ids `0x24F628C0` full body, `0x45E6F8E0` zombies, in both). So **models,
textures, animations, sounds and level geometry cross over as they are**; what differs is
which *names* each game's program knows.

### Shaders: nearly all shared, 5 not

A model's draw names a **shader description** by hash (`UsedShaders.txt` →
`deadrising*-sd.big/<hash>.sdo`, formats.md §Levels "Materials"). Case West has 222 of
Case Zero's 223 descriptions (same names; the shader programs inside are compiled
differently in each game: pixel shaders share 45 names of ~1,300). Used by models but
**missing from the other game** (census of every `UsedShaders.txt`, 2026-10-12):

| Shader | Only in | Used by |
|---|---|---|
| `ZombieGlow` `48c6e780` | CW | `zombie_gas_2/_3` (the gas mutants) |
| `ZombieClothRGBSpec` `cd112040`, `ZombieClothRGBReflective` `d9192300` | CW | `security_heavy_*` (14 and 9 parts) |
| `CM_SIX` `0833fbc0` | CW | `monitor_phenotrans` |
| `Larvae` `0064b9a0` (CW) / `630cee60` (CZ) | each its own | the larvae |

Everything else draws with the target game's own copy of the same description. For the
five: **remap** to the nearest shared description (`ZombieGlow` → `ZombieClothRGB…`
without the glow), or **bring the shader over** (its `.sdo` and programs into the target's
banks). The recomps draw from a **shader cache translated ahead of time**
(`assets/shader_spv`, 910 modules in CZ, `runtime/gpu/shader_translator.cpp`), so a new
shader also needs translating: a recomp question (U3), and the recomps change only with
the user's approval (CLAUDE.md).

### Items

| | CW items not in CZ | CZ items not in CW |
|---|---|---|
| `items.txt` blocks | 872 (217 with a model) | 291 (130 with a model) |
| Move banks the other game lacks (`anm_<AnimBankName>.big`) | Electricprod, Firecrackers, Flamethrower, ImpactHammer, Laser_Sword, Lawnmower, Reaper, SoccerBall, Tennis, defib | 2hand_bank1, AirHorn, BowandArrow, Combo_PaddleSaw, Moose, Parasol, SprayPaint |
| Item classes the other program doesn't know | `cExternalLocatorItem` (81), `cPropCharacterAttachmentItem` (15), `cPlayerWeaponOverrideItem` (13), `cElectricityInfoItem`, `cBlockingArcInfoItem`, `cThrowAttackBehaviour` (3 each), `cTurretInfoItem` (2) | none |

Also per item, all already handled for one game by phases 11-13 and needing a
cross-game table: effect numbers (CZ's table 371 effects, CW's 414; the same name can have
another number: map **by name**, `catalog/effects.toml`), the inventory icon's name (CZ
`w_<name>.bct`, CW `<name>.bct`), text (new string ids in the target's banks), sounds
(`AudioFilename` banks: copy the bank or pick the nearest), combo cards.

### Zombies: each program has its own list of types, Case Zero's has empty slots

A zombie type is a model name of `data/models/zombies.big`, and **each executable holds
its own table of type names** (found 2026-10-12): CZ `0x829DD2C4` region, CW
`0x829F03C0`:

* **Case Zero: 32 types, the whole of Dead Rising 2's list**: `zombie_fat`,
  `zombie_fat_female`, `zombie_skinny`, `zombie_skinny_female`, `zombie_bertha`,
  `zombie_bride`, `zombie_cheerleader`, `zombie_cocktaildress`, `zombie_construction`,
  `zombie_cop`, `zombie_dealer`, `zombie_kitty`, `zombie_knife`, `zombie_maintenance`,
  `zombie_protester`, `zombie_protester_female`, `zombie_sandwich`, `zombie_showgirl`,
  `zombie_soldier`, `zombie_stripper`, `zombie_tir`, `zombie_waitress`, `looter`,
  `mercenary`, `mercenary_army`, `mercenary_pheno`, `mercenary_tk`, `soldier`,
  `zombie_gas`, `pro_zombie_bowling`, `pro_zombie_trucker`, `pro_zombie_cop`. It ships
  models for 12: **20 empty zombie slots** (like the level slots).
* **Case West: 10 types**: `zombie_fat`, `zombie_fat_female`, `zombie_skinny`,
  `zombie_skinny_female`, `zombie_gas`, `security_heavy`, `security_lab`,
  `security_light`, `security_light_hat`, `zombie_security`; all used: **no empty slot**.
* Both programs know `zombie_gas` and have `GasZombie` code (5 references each): the
  **gas mutants'** behaviour may come with the type in Case Zero too (U2).

So **CW → CZ**: a Case West type takes one of Case Zero's empty slots (`security_light`
as `zombie_dealer`, `zombie_gas` as `zombie_gas`), its model copied under the slot's name,
its colour choices with it (phase 9). **CZ → CW**: no slot is free in Case West's table;
how Case West takes a type of its own is part of U2 (decision 1). Either way the
imported type is added **natively** (user's decision): in the load sets and the spawn
areas, factories and crates of the levels that use it (phase 11's spawn data), like the
game's own types.

### Bosses and human enemies

* Case Zero: the Mechanic (`boss_mechanic.txt`; "Mechanic" 22 times in CZ's program, once
  in CW's).
* Case West: the Commander (`boss_commander.txt`) and the security battles
  (`data/datafile/battles/battle_enemy_hazardunit.txt`, `…lightsecurity`,
  `…zombiecontroller`, `…enemyobservatory`, `…enemysafehouse`, `…debugbattle`): their
  **paths are written in CW's program only**.
* Every script class of those files is known to both programs (census below), but which
  battle file a boss reads, and its AI, are in each program's code. Whether the Mechanic
  fights in Case West (its program still names `boss_mechanic`) or the Commander in Case
  Zero is an in-game test (U6). Until then the importer turns a boss it can't carry into a
  **regular enemy of the target** (with its look) and says so, never a crash.

### Levels: Case Zero has 78 empty slots, Case West 1

* CZ: 82 slots, the files of 4 shipped (`phase14-kickoff.md`, formats.md §Levels "Level
  slots"): **78 empty**, named after Dead Rising 2's levels (`food_barn`,
  `palisades_mall`…) and developers' test levels.
* CW (`0x829E8FD8`): **10 slots**: `living_research`, `main_menu`, `safehouse`,
  `secure_laboratory`, `storage_pens`, **`w_mall` (empty)**, and four cutscene sets
  (`cine_exterior_after`, `cine_exterior_before`, `cine_rooftop`, `cine_warehouse`).

So a Case West level goes into any Case Zero slot; a Case Zero level into Case West's
`w_mall` (one at a time), or in place of a level (a cutscene set: its cutscenes then lose
their stage; the modder chooses, warned).

What a level carries (phase 10/11 + this research): zone archives (pieces, textures,
lightmaps, collision), `zonelist.big` (zones named `folder/zone`, so they can stay in a
folder of their own), the script files (`<script>.txt`, `waypoint_`, `nm_` navigation
mesh), zombie areas and load set (`zombiesets.txt`, also in `persistent_filecache.big`
and `preload4.big`), missions naming the level, the light setting files
(`cLightContextVolume ContextFileName`, CW `data/shaders/settings/epilogue_*.csv`), sound
ambience, the in-game map (`fe_map_points_<level>.csv`, map pictures), cutscenes'
`PreferedLevel`.

### Script classes the other program doesn't know

Every block class of every `datafile.big` text file of each game, looked up in the other
executable's strings (2026-10-12):

* CW classes CZ's program lacks: the 7 item classes above, `cHoldCameraEvent`
  (`sgraph.txt`), `cMissionObjectiveNPCState` (9, `missions.txt`), `cPhotographerCam`.
* CZ classes CW's program lacks: `cMissionDestroyNPC` (10), `cMissionKillNPC`,
  `cMissionObjectiveNPCJoin` (22), `cMissionObjectiveSurvivorLives` (11),
  `cHatTrickButtonPressEvent`, `cMiniGameHatTrickCam`, `cMiniGamePikeCam`.

An imported block of an unknown class is rewritten to a known one where one exists (a
turret as an unmovable item) or left out, listed in the import report.

## Unknowns, and the in-game tests that settle them (each a small mod the user plays)

| Test | Question |
|---|---|
| **U1** an item | A Case West weapon with its own move bank (the Laser Sword: `anm_Laser_Sword.big` added to CZ's `streamedassets.big`, its effects by name) in Case Zero's street: does it swing, hit, show its effects? |
| **U2** a zombie type | Case West's `security_light` in Case Zero's empty slot `zombie_dealer`, and `zombie_gas` as `zombie_gas`, added to the street's load set and spawn areas: do they spawn there, walk, attack; do gas zombies do their gas? And Case Zero's `zombie_cop` in Case West as an eleventh type (decision 1) |
| **U3** a shader | the gas zombie's `ZombieGlow` in Case Zero: remapped (works?) or brought over (does the recomp draw a shader its cache lacks?) |
| **U4** a CW map in CZ | `storage_pens` in Case Zero's slot `food_barn` (after T5 proves slots): loads, its items and zombies remapped, doors in and out |
| **U5** a CZ map in CW | the street (`prologue`) in Case West's `w_mall` |
| **U6** bosses | the Mechanic in Case West, the Commander in Case Zero |

## Plan (proposed; each step documented and tested as it goes)

1. **Both games at once.** The toolkit already locates both; recipes gain a **source
   game** (`"from": "cw"`); the build reads the other game's tree for them and fails
   with a clear message ("this mod needs Case West: Game folders…") when it isn't there.
2. **Cross-game tables as profile data** (`dr2kit/profiles/crossgame.toml`), written by
   tools from the executables and the data like `tools/effect_table.py`: zombie type
   tables and the default mapping, empty slots (levels, zombie types), shaders present in
   each game and the remap for the five, item class rewrites, effect numbers by name, move
   banks, icon naming.
3. **Import an item** (Studio: the other game's Library, *Use in Case Zero*; `dr2 mod
   import-item <mod> <item> --from cw`): the pack, its move bank, effects by name, icon,
   name and description strings, sounds, its `items.txt` block rewritten.
4. **Import a zombie type** natively (decision 1): its model in a type slot of the target,
   colour choices, load sets, and the spawn areas / factories / crates that use it.
5. **Import a map** into a slot (*Import level…*): zones, scripts, navigation mesh,
   zombies, items (each through step 3), light settings, map points, doors; then open it
   in the Maps editor.
6. **The importer's report and checker:** every substitution listed (this zombie type
   became that, this class was left out, this shader remapped); a check that every name
   the imported files use exists in the target (items, types, classes, shaders, banks,
   effects, strings, sounds, levels, spawn points): **the "doesn't crash" gate**, and a
   census importing **every** item and level of each game into the other with zero
   unresolved names.
7. **Bosses** after U6.
8. **Requirements** (§Requirements): written by the build, shown in Studio, the mod
   manager, `.dr2mod`, `dr2 mod info`; checked before Play.
9. **Guides**: *Use the other game's things* (23 or 25, numbered after phase 14's),
   requirements in guide 06, troubleshooting.

## Requirements: what a mod needs (the file XenonLive reads)

Every mod gets a `requires` section in `mod.toml` (written by the toolkit; the modder can
add to it), copied into a machine-readable **`requirements.json`** at the root of every
built and shared mod (`.dr2mod`), plus a plain-words **`REQUIRES.txt`** for people:

```toml
[requires]
games = ["cz", "cw"]          # game data needed on the player's machine to build it
                              # (made from Case West's files, played in Case Zero)
play = "cz"                   # the game it runs in (mod.games stays the list it supports)
toolkit = ">=0.15"            # the dr2kit version that can build it
mods = ["frostmourne>=1.0"]   # other mods it needs, with versions
saves = "needs-mod"           # "safe" | "needs-mod": saves made with it need it (own
                              #  levels, own missions; phases 11 and 14)
coop = "all-players"          # every co-op player needs it (anything that changes the
                              #  world: maps, items, zombies) | "host-only" | "local"
                              #  (only looks: textures, sounds)
```

```json
{"format": "dr2kit-requires/1", "id": "storage-pens-in-cz", "version": "1.0.0",
 "play": "cz", "games": {"cz": "58410A8D", "cw": "58410B00"},
 "mods": [{"id": "frostmourne", "version": ">=1.0"}], "toolkit": ">=0.15",
 "saves": "needs-mod", "coop": "all-players", "content_hash": "<sha1 of the build>"}
```

Title ids name the games for XenonLive (CZ `58410A8D`, CW `58410B00`; phase 16 adds the
PC games as sources). The launcher can then refuse to start, or warn ("This mod needs
Case West"), and compare players' mod sets before a co-op invitation (same ids, versions
and `content_hash`). The toolkit fills `saves` and `coop` from what the mod changes, so
the modder doesn't have to know. XenonLive's launcher has no mod support yet
(`XenonLive_Launcher/src`): this file is the contract it can read when it gets one.

## Decisions to take (proposed defaults in bold)

1. **Zombies of the other game: DECIDED (user, 2026-10-12): added the way the game's own
   are, as real types of their own, working with the spawn areas** ("foreign zombies are
   added how it would natively and work with their zombie spawn area"): each imported
   type gets its model under a type name the target's program knows, its colour choices,
   its entry in the level load sets (`zombiesets.txt`) and the spawn areas, factories and
   crates (`cZombieWarehouse`, `missions.txt`) that spawn it, exactly like a native type.
   No mapping to a "nearest" type. CW → CZ: into Case Zero's empty zombie slots. CZ → CW:
   Case West's program lists 10 types and none is free, so U2 also looks for how Case
   West can take an eleventh: whether the table is the only list the game checks (CW
   ships `zombie_test.big`, a model its table doesn't name), a type CW doesn't use in the
   imported level, or a slot of its debug list; the plan comes back to the user if none
   works.
2. **Shaders the target lacks:** **remap to the nearest shared shader** (works with no
   recomp change); bringing shaders over only if U3 shows the recomps can, and with the
   user's approval for any recomp change.
3. **A CZ level into CW:** **into `w_mall`**; replacing a cutscene set only on the
   modder's explicit choice.
4. **Bosses:** **a regular enemy of the target with the boss's look** until U6 proves a
   boss works across.
5. **Requirements:** **`[requires]` in `mod.toml` + `requirements.json` +
   `REQUIRES.txt`**, filled by the toolkit.

## Gate

* Every item of each game imported into the other by the checker with zero unresolved
  names (census); U1-U6 played by the user.
* A Case West level played in Case Zero with its items and zombies, entered and left by
  doors; a Case Zero level in Case West's `w_mall`.
* A cross-game mod shared as `.dr2mod`, installed on a library without the source game:
  Studio and `dr2 mod info` say what it needs and refuse to build; with it: builds, plays.

## Start here (when phase 15 starts)

Phase 14's tests and tools first. Then: ask the decisions above, then U1 and U2 (the
smallest), then steps 1-3. Research scripts of 2026-10-12 were throwaway (shader census
from `UsedShaders.txt`, script class census against the executables' strings, the
executables' level / zombie tables): the facts are above; step 2's tools redo them for
good.

# Phase 15 kickoff: Case West in Case Zero and Case Zero in Case West, and what a mod requires

> **Status 2026-10-12: started** (user: "Do phase 15"; phase 14's in-game tests moved
> after it by the user: "Later, start phase 15 now"). Decisions 2-5 taken (§Decisions).
> Map import (step 5) built 2026-10-14: U4 loads headless, U5 built (§Status).
> Progress: §Status. Phase 16 (the same from the PC games):
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

### How many types and levels the engine takes (user, 2026-10-12: "as many as we want without breaking the engine limit; Dead Rising 2 got way more and still works")

* *Retracted 2026-10-13 (the "check against 31" below is a byte of the looked-up name's
  string object in the name → type lookup, not the type number; no engine limit on the
  type count is proven: `TODO.md` #1).*
* **Zombie types: the engine's limit is 32.** The program keeps a zombie's type as a
  number checked against 31 (`cmplwi r5, 0x1f` in both games' spawn code: CZ
  `0x823000BC`, CW `0x822FC99C`) and walks the type table with a count compiled into the
  code: **CZ 32** (`li r11, 0x20`, table `0x829DF688`), **CW 10** (`li r11, 0xA`, table
  `0x829F2598`). Dead Rising 2 itself ships about 30 types (PC `deadrising2.exe`), Off the
  Record about 30 too (`zombie_wrestler`, `zombie_sexyspacegirl` added): the bigger games
  have more *content*, not a bigger engine table. So **Case Zero already takes 32 types**
  (20 free), and **Case West can take 32 once its program is built for 32**: its table
  and every loop over it (count 10) grown to 32. In the recomp that count is C++ code
  generated from the PowerPC (`ctx.r11.s64 = 10`), so growing it is **a change to the Case
  West recomp** (each place that walks the table, and any array sized by it, found by
  the same search), the third kind of recomp change after the `game_mods/` layer and the
  audio substitution: **approved by the user 2026-10-12** ("I do approve the growing case
  west zombie list and maps"; ARCHITECTURE.md §Recomp integration 3), made in that repo
  following its own CLAUDE.md, and the same check in Case Zero's (already 32).
* **More types per level** is a budget, not a count: each level's load set lists the
  types it loads with their memory cost (`zombiesets.txt` `total_cost`, the "HWM" line):
  the importer keeps every level within the budget the game's own levels use (measured
  per game) and says when a map asks for more.
* **Levels:** CZ's table has 82 slots (78 free: more than Dead Rising 2's 17 level
  folders); CW's has 10, `w_mall` free. Growing CW's level table is the same kind of
  recomp change as its zombie table (level ids are an enum in its code; Off the Record's
  program lists 56 `LEVEL_` ids, Dead Rising 2's 86).
* So "as many as we want": **up to the engine's 32 zombie types and the level table's
  slots in each game**, with Case West's tables grown to Case Zero's sizes (that recomp
  change approved by the user, 2026-10-12), and every level kept within its zombie budget.

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
 "play": ["cz"], "games": {"cz": "58410A8D", "cw": "58410B00"}, "built_from": ["cw"],
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
   Case West's program is built for 10 types: **grown to the engine's 32** (§How many
   types and levels: a Case West recomp change, approved by the user 2026-10-12), and its
   level table likewise. Every level stays within its zombie memory budget.
2. **Shaders: DECIDED (user, 2026-10-12): bring the other game's own shaders**, not
   the nearest shared one: "we will use the proper Case West shader and add it to the
   shader compilation". A brought model draws with its game's descriptions and programs,
   copied into the target's banks under new names where the target has a same-named one
   with other bytes (formats.md §Across the games: shader banks: no vertex shader and
   only 45 pixel shader names are shared, and parameter numbers differ). Both recomps
   already translate a shader at its first draw; adding the mods' banks to the first-run
   shader build (no pop-in) is a recomp change in both, approved with this decision.
   (The first proposal, remapping to the nearest shader, was dropped.)
3. **A CZ level into CW: DECIDED (user, 2026-10-12):** the first one **into `w_mall`**,
   and Case West's **level table grown** (the approved recomp change, §How many types and
   levels) so it takes more than one: "we will need more than one level". Replacing a
   cutscene set only on the modder's explicit choice.
4. **Bosses: DECIDED (user, 2026-10-12, the proposed default):** **a regular enemy of the
   target with the boss's look** until U6 proves a boss works across.
5. **Requirements: DECIDED (user, 2026-10-12, the proposed default):** **`[requires]` in
   `mod.toml` + `requirements.json` + `REQUIRES.txt`**, filled by the toolkit.

## Gate

* Every item of each game imported into the other by the checker with zero unresolved
  names (census); U1-U6 played by the user.
* A Case West level played in Case Zero with its items and zombies, entered and left by
  doors; a Case Zero level in Case West's `w_mall`.
* A cross-game mod shared as `.dr2mod`, installed on a library without the source game:
  Studio and `dr2 mod info` say what it needs and refuse to build; with it: builds, plays.

## Status

* **Step 8, requirements: built 2026-10-12** (`mods/requires.py`). `[requires]` read and
  kept by `mod.toml`; `infer` fills games (+ recipe sources), saves, co-op, toolkit;
  `requirements.json` + `REQUIRES.txt` in every `.dr2mod`, the requirements in
  `dr2kit-build.json`; builds refuse a mod whose games or mods are missing; `dr2 mod
  info`; Studio's mod manager and Install window show it. One change to the planned JSON:
  `play` is a list (a mod can play in both games) and `built_from` names the games its
  recipes copy from. Guide 06 §What a mod needs. Tests: `tests/test_requires.py`.

* **Steps 1-3 built 2026-10-12** (both games at once, the cross-game table, importing an
  item): recipes read the other game (`"from"`), `.bcs.json` copies text from it;
  `profiles/crossgame.toml` (`tools/crossgame_table.py`: zombie type and level tables,
  unknown classes, shaders); the shader banks' descriptions read and written
  (`formats/shaderbank.py`, census 0 problems both games); brought shaders
  (`convert/shadercarry.py`); the item importer (`mods/importitem.py`, `dr2 mod
  import-item`, Studio *Other game's items…*, guide 23). Gate: `dr2 census --import`:
  872 CW items into CZ and 291 CZ items into CW, **0 refused, 0 unresolved**.
* **Test U1 (headless, CZ, Laser Sword): the engine's limit found.** The mod builds;
  without its shaders it loads (no fault); with them the game asserts "Shader constant
  set overflow": the renderer's pool of shader constant sets holds 384 in CZ (~26 free)
  and 1,340 in CW (~3 free), set from a table in the executable's data (formats.md
  §Across the games: shader banks). One CW weapon brings 45 pixel shaders, a gas zombie
  73. **Next: grow that pool in both recomps** (a recomp change: the value set at boot;
  **approved by the user 2026-10-12**, ARCHITECTURE.md §Recomp integration 4), then U1
  again.
* Effects the target lacks are left off (listed); bringing them into the effect table's
  free slots (phase 13's own effects) is next after U1.
* **Recomp change 4 built 2026-10-12 (both recomps), U1 passes headless.** Each recomp
  grows two pools to 4,096 (Case Zero's pool was 1,300, not 384: its boot overwrites the
  image's value; a second pool runs out too: formats.md §Across the games). Then the Laser
  Sword still hung Case Zero's load: Case West's scenes lack `_BONEHIERARCHY_`, which Case
  Zero's program walks (`sub_827ACAD8`); the build now writes it
  (`crossgame.fit_scenes`). Headless on copies of the user's saves: the Laser Sword (45
  pixel shaders) plays in Case Zero's street, Case Zero's Parasol (14) plays in Case
  West's Storage Pens. **Owed: U1 in a window with the user** (looks, moves, sounds, card).
* **Step 3 rest and step 4 (Case West → Case Zero) built 2026-10-13.** Effects the target
  lacks are brought into free slots of its table (`importitem._bring_effect`, in the
  target's layout, `Effect.as_version`, with missing particle pictures): Case West → Case
  Zero needs 27 of Case Zero's 36 free slots; `PropAudioType` keeps the target's bits (the
  Impact Hammer faulted Case Zero's load with bit 17; found by bisecting its keys); keys
  naming a dropped child are left out. Zombie types: `mods/importzombie.py`, `dr2 mod
  import-zombie` (slot, model + shaders, class, behaviours, load sets with the budget
  warning, the `persistent_filecache.big` copy), `dr2 census --import` (7 Case West types
  into 7 slots). A third shader pool (descriptions) grown in both recomps (the gas zombie
  faulted without it). Headless on copies of the user's saves: the Impact Hammer plays in
  Case Zero; the gas zombie, `security_light` and `security_heavy` load with every street
  crowd retyped to them. **Owed: U2 in a window** (do they show, walk, fight, gas?).
* **U1/U2 played by the user 2026-10-13 (Case Zero, windowed):** sword swings and sounds
  right, but untextured handle, no glow; hammer untextured, attacks broken; retyped crowds
  empty. Fixed since (headless): the items' moves carried into the animation graph
  (`convert/graphcarry.py`, with the graph's header counts and source-style text), the gas
  zombies' animation bank brought; Case West's guards need graph *states* merged (warned,
  not done). **Open: brought shaders draw without textures** (formats.md §Zombie types /
  U1 notes; a recomp draw capture is next). Then U1/U2 again with the user.
* **Untextured brought shaders: cause found and fixed 2026-10-13** (no capture needed):
  a parameter's number is its constant register and the games' pixel registers differ
  (41 names), so a Case West program read Case Zero's point light as its
  `gShaderDebugParameters` and drew its flat debug output. Brought pixel shaders now have
  their constant operands moved to the target's registers (`formats/xenos.py`,
  `shadercarry.move_registers`; all 1,337 / 1,279 pixel shaders move both ways; formats.md
  §Across the games: constant registers). Owed: U1 again in a window.
* **U1 and U2 played by the user, 2026-10-13 (Case Zero, windowed): pass.** Laser Sword
  and Impact Hammer textured, the sword's glow (Case West's engine-only `gPowerOffParameter`
  read as 1), the hammer held right (the player's hand locator); gas zombies in the street
  crowds (their voices brought); Case West's guards in single spawns with Case Zero's
  soldier behaviour, carrying Case West's rifle, fighting, dropping it. Fixed on the way:
  value-set registers, engine-only parameters, voice banks, the grip, armed enemies
  (`importzombie` + profile `armed_enemies`, `levelcheck`'s crowd warning). Open: guards +
  gas + both weapons in one street run out of a renderer pool ("Failed to allocate
  memory"); `security_heavy` / `security_lab` (no `Range_Shoot`) still use Case West's
  behaviours.
* **Case Zero → Case West zombies: blocked on recomp change 3, which is bigger than
  planned** (formats.md §Zombie types: Case West's type data sits in arrays inline in a
  manager object, so growing it means re-laying out that object). **User's decision
  2026-10-13: do the full re-layout**, then the same day: **not now; kept as open work for a
  contributor**, everything found in [`TODO.md`](TODO.md) #1.

* **The memory limit, found 2026-10-13 (evening, headless with gdb on a copy of the
  user's save):** the full heap is the program's **Zombie heap** (heap 71), a constant
  30,177,280 bytes in both games, which Case Zero's street already fills to 1.6 MB with its
  own types. A loaded type takes its pack unpacked plus a shared ~5.5 MB (nine types
  measured); the load sets' `total_cost` doesn't measure memory; the game reads
  `persistent_filecache.big`'s `zombiesets.txt`, not `datafile.big`'s. The importer now
  reports a type's bytes and warns when it must replace a type (profile `zombie_heap`,
  `importzombie.pack_bytes`). formats.md §Engine memory: the heaps. **User: "Yes, +16
  MB"; built the same evening** (recomp change 5, both recomps, CZ `85900b8`, CW
  `3f17411`): the SW Texture heap gives 16 MiB to the Zombie heap; the crashing mix loads
  headless with 16.7 MB of the Zombie heap and 27.2 MB of the texture heap free in play.
  Found on the way: **a load-set entry holds at most 13 types** (a 14th faults at boot);
  the importer leaves a type out of a full entry.
* **`security_heavy` / `security_lab`, 2026-10-13:** Case West's program has its own code
  for them (`HazardUnit`, `ZombieController`, their battle files, `x_Boss_*` debug
  entries); Case Zero's has none, so they can't behave in Case Zero as in Case West.
  **User: Case Zero soldiers** (built: profile `as_soldiers`, mercenary slots, `ArmyMerc`,
  a rifle); test mod `~/.cache/dr2kit-p15/u2b` (gas crowds, light / heavy / lab guards in
  the Sheriff's office and junkyard single spawns, Laser Sword and Impact Hammer at the
  safehouse exit) loads headless. **Owed: u2b in a window with the user.**

* **Step 5, maps: built 2026-10-13/14** (user: "Do phase 15 maps"; phase 14's T5 answered
  headless first). Found on the way, each measured headless:
  - **Which empty slots load** (formats.md §Level slots "Audio scenes"): a level loads its
    *audio scene* `data/audio/<name>.txt`, digest-checked; a slot whose scene the game
    doesn't ship stalls (`FoodBarn`). 42 of Case Zero's 78 empty slots and Case West's
    `w_mall` can take a level. The slot table (level names, zone lists, audio scenes) is
    read from both executables (`tools/crossgame_table.py`); level names aren't always
    `LEVEL_` + the script (`LEVEL_LIGHTINGTEST`), the level checker now knows them.
  - **The `.big` writer's layout was wrong for edited archives**: the game puts each
    payload at the previous one's end aligned up to its `flags`, and Case Zero's level
    streaming relies on it. Our writer padded more; a re-encoded zone then made Case Zero
    read a texture pack 4 bytes early and ask for 256 MiB, or stall. Fixed in
    `container/big.py` (round trip still identical for every archive of both games), which
    may also help earlier mods with big edited archives. formats.md §`.big` container.
  - `_BONEHIERARCHY_` only for scenes with nodes (`ZONE_ORGANIZATION.big` never has it).
  - **The level importer** (`mods/importlevel.py`, `dr2 mod import-level`, `dr2 level
    slots`, Studio *Other game's levels…*, guide 23 §A whole level): zones with the source's
    shaders, text files with every name resolved (items brought through `importitem`,
    unknown classes dropped, doors to missing levels lead back: profile `level_door`, text
    copied), the source's zombie mission for the level as the mod's own (types through
    `importzombie`, armed ones out of crowds), the load set, an entry door, spawn points
    the target's doors ask for. Big recipes from the other game are **cached**
    (`newitem.build_copy`, `recipes/` in the cache folder) and built in parallel at import
    (`importlevel.prebuild`): ~2 min for a level on 16 threads, then seconds.
  - **U4 headless: Case West's Storage Pens loads in Case Zero** (slot
    `LEVEL_PROLOGUE_BOWLING`, door by the safehouse exit, prompt "Storage Pens"): Chuck
    arrives at its `Start`, textured and lit, zombies about. Test mod
    `~/.cache/dr2kit-p15/u4`. U4 and the user's Frostmourne mod also boot together
    headless. The two mods had assigned different effects to `EFFECT_Common1006` and
    `EFFECT_Common1007`; effect imports and new effects now reserve slots used by every
    mod in the user's library, including disabled mods. **Windowed launch still faults**:
    Case Zero exits while loading the prologue menu background, when heap 0 is asked for
    1,920 bytes with 668 free (`sub_8277DF48`, caller return `0x8277E50C`). Heap 71 still
    has 32,092,032 bytes free. The no-mods control survives 30 seconds; U4 + Frostmourne
    reproduces the fault without the save test mod. The pair passes headless. This points
    to main-heap pressure in the windowed menu. The allocation comes from
    `sub_8278DCF8` through the generic allocator `sub_8277E3D0`; identify what its
    21-entry allocation represents and which modded resource pushes heap 0 over its limit.
    **Owed: resolve that startup fault, then U4 in a window with the user** (walk, items,
    doors out, a new game for the zombies).
  - **U5 (Case Zero's street in Case West's `w_mall`): built** (`~/.cache/dr2kit-p15/u5`,
    `dr2 mod check` OK). The door triggered a transition in the 2026-10-14 windowed run:
    Case West opened the modded `w_mall/zonelist.big`, then loaded imported `prologue_z01`
    through `prologue_z09` from the mod overlay. It crashed during that load with a guest
    null-page read at `0x0000001C` (LR `0x827919EC`, CTR `0x827790F8`; guest backtrace
    starts `0x827919EC, 0x827926E0, 0x821CAC64`). The rotated runtime log is
    `cw_runtime.log.1` beside the Case West recomp (2026-10-14 13:20). The door works far enough to start loading the Prologue;
    isolate the imported-level crash next. Addr2line maps the host PC to heap allocator
    `sub_82791878`; registers show heap `0x3E`, a failed `0x11B000` (1.15 MiB) request,
    and the null-page read. The heap name is unconfirmed. CW's Zombie heap growth was set
    to 32 MiB for a retry, but the same allocation still failed. The runtime now logs the
    per-level Zombie heap id and failed allocations; growth is set to 64 MiB for the next
    windowed retry. This remains a hypothesis, not a confirmed fix.
  - Not done: Case West's level table grown (decision 3; only `w_mall` now), the 36 Case
    Zero slots whose audio scene would need a recomp change, the in-game map's points for
    a brought level, its own sound.

### What is left (2026-10-13)

| Step | State |
|---|---|
| 1 both games at once, 2 cross-game table | **done** |
| 3 import an item | **built**: brought shaders (constant registers moved, 2026-10-13), effects into free slots, moves into the animation graph, `PropAudioType` bits, `_BONEHIERARCHY_`; loads headless both ways. Untextured brought shaders **fixed** (registers), U1 again owed |
| Recomp change 4: shader pools (CZ, CW) | **done** (three pools, 4,096 each) |
| Recomp change 5: the Zombie heap (CZ, CW) | **done** 2026-10-13 (+16 MiB from the SW Texture heap) |
| U1 items in game (Laser Sword, Impact Hammer) | **passed** (user, 2026-10-13): textured, glowing, held right, attacks work |
| U3 shaders in game | **passed** with U1 (registers moved, engine-only parameters fixed to 1) |
| 4 zombie types CW → CZ + U2 | **passed** (user, 2026-10-13): gas zombies in crowds; guards armed, fighting, dropping rifles (single spawns, Case Zero's soldier behaviour). Since: the memory limit fixed (recomp change 5, the Zombie heap +16 MiB), 13 types per load-set entry, `security_heavy` / `security_lab` as Case Zero soldiers; test mod u2b loads headless, **owed in a window** |
| 4 zombie types CZ → CW | **deferred by the user**: Case West's type table, [`TODO.md`](TODO.md) #1 |
| 5 maps (CZ slots, `w_mall`, CW level table) + U4/U5 | **built** 2026-10-14 (`importlevel`, Studio, guide 23): U4 (Storage Pens in Case Zero) **loads headless**, owed in a window; U5 door triggers, but imported Prologue crashes during load; Case West's level table not grown |
| 6 the checker | items and zombie types done (`dr2 census --import`); levels: `dr2 mod check` on a brought level (real level names, a mod's own level scripts' areas and spawn points); a census of every level each way: not yet |
| 7 bosses + U6 | **not started** |
| 8 requirements | **done** (XenonLive's launcher has no mod support yet) |
| 9 guides | 23 (items, effects, zombies) and 06 written; maps and bosses sections to come |

## Start here (next conversation, updated 2026-10-14)

Maps (step 5) are built (§Status "Step 5"). In order: **U4 in a window with the user**
(`~/.cache/dr2kit-p15/u4`: link it into their library, `dr2 play -g cz`; the door is a few
metres from where Chuck leaves the safehouse; then a new game for the zombies, on a copy
of their saves); **U5**: retry the transition with the 64 MiB Zombie heap setting and
inspect the allocator's heap ID if it still crashes; u2b (below); phase 14's T5 (now in
`LEVEL_X_PROLOGUE`), T4a, T4b; bosses (step 7). Headless helpers of this session were in
the session scratchpad (gone); the method: `hl_gdb.py` with B pressed as `B@3000` entries
after the menus (`START,A,A,A,A,NONE@4000,B@3000…`), a door copy moved onto the save's
spot, `heaps_at_oom.gdb`.

## Start here (2026-10-13 night)

Done on 2026-10-13 (commits `0505cc2`..`554d3a4`): **U1 and U2 played by the user in Case
Zero and passed** (brought pixel shaders on the target's constant registers, Case West's
engine-only parameters read 1.0, gas zombie voice banks, the hammer's grip, armed guards in
single spawns). In the evening: the crash with everything at once was the program's fixed
**Zombie heap** (formats.md §Engine memory); with the user's approval both recomps give it
16 MiB from the SW Texture heap (recomp change 5, CZ `85900b8`, CW `3f17411`); a load-set
entry takes 13 types at most; the heavy and lab guards are Case Zero soldiers (user's
choice). The user was away when the last test build was ready (the game was closed at
their request, their four mods redeployed). In order:

1. **u2b with the user in a window**: everything at once with the grown Zombie heap, and
   the heavy and lab guards as Case Zero soldiers (do they look right, shoot, drop their
   rifles?). Watch the SW Texture heap on a long walk (the 16 MiB came from it; a
   texture-heap failure would crash elsewhere in the street). How heaps are measured:
   `~/.cache/dr2kit-p12-handoff/scripts/hl_gdb.py` with `heaps_at_oom.gdb` /
   `zombie_heap_late.gdb` (gdb attached to the headless recomp, the title's own
   `sub_8277C288` per heap); headless runs of the test save reach the ending film by
   ~200 s, so measure at ~100 s.
2. Phase 14's T5 with the user (does an empty level slot load?), then maps (step 5,
   U4/U5, Case West's level table), the level checker (step 6).
3. Bosses (step 7, U6), then guide 23's maps and bosses sections (step 9).
4. Case Zero → Case West zombies: deferred ([`TODO.md`](TODO.md) #1).

Test mods kept in `~/.cache/dr2kit-p15`: **`u2b`** (gas crowds; light guards in
`SherriffDept4-7`, heavy in `SherriffDept1-2`, lab in `SherriffDept3` and
`JunkyardLurker`; Laser Sword and Impact Hammer at the safehouse exit: loads headless,
owed in a window), `v-merc` (gas crowds + light guards in single spawns: works),
`v-noguard` (both weapons + gas: works), `session-cz` (the mix that crashed; loads with
the grown heap), `parasol-cw`. Deploy one with `dr2 mod deploy -g cz
~/.local/share/dr2kit/mods/keep-cz-test-save <mod>`, then launch the recomp; the user's
own deployment is `dr2 play -g cz --deploy-only`.

## Start here (when phase 15 starts)

Phase 14's tests and tools first. Then: ask the decisions above, then U1 and U2 (the
smallest), then steps 1-3. Research scripts of 2026-10-12 were throwaway (shader census
from `UsedShaders.txt`, script class census against the executables' strings, the
executables' level / zombie tables): the facts are above; step 2's tools redo them for
good.

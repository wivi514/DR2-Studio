# Phase 14 kickoff: buildings and maps of your own, animations played

> **Status 2026-10-12 (evening):** part 3 (**animations played**) is built and checked:
> every key of every `.anm` of both games is read the way the game reads it, Chuck swings
> a weapon in Studio's 3D view, every animation plays in the asset browser and exports to
> Blender. Parts 1 and 2 (**buildings** and **maps** of your own) have their in-game
> tests built (T4a, T4b, T5), checked by build only: the user's game was open, so no
> headless run yet. Next: §Start here.

**Direction (user, 2026-10-12: "Do phase 14"):** the roadmap's phase 14, carried from
phase 12 (`phase12-kickoff.md` §Research T4-T6, plan steps 6-8) and phase 13 step 9. Each
part starts with an in-game test by the user before tools are built (`roadmap.md`).
Decisions already taken in phase 12 (`phase12-kickoff.md` §Decisions 6-7, the user's):

* **Buildings of your own** are always seen like the game's buildings, simpler far away:
  the **look as a new level piece** in a zone, the **collision as an invisible unmovable
  item** (engine-made); level buildings copied with their collision after T6; baked
  shadows later.
* **Maps of your own** go only in the executables' **empty level slots** (never a
  patched executable: the recomps stay read-only), and **start as a copy of a level** the
  game has, edited in the Maps editor.

## Part 3: animations played ✅ (built and checked 2026-10-12)

| What | Where |
|---|---|
| Every key of every `.anm`, read as the game's own decoder does (CZ `0x827B5090` steps a frame; `0x8279AB98` / `0x8279AF68` read a rotation / translation key): 8-byte absolute rotations, **4-byte changes from the previous key**, 8-byte packed (21-bit) or 12-byte float translations, the later keys stored as each is needed | `formats/anim.py` `Animation.decode` → `Clip`; formats.md §Animations (with the retraction of 13.2's first-key reading) |
| Census: every file of both games read **to its last byte** (CZ 5,785 files, 6,655,401 keys; CW 6,268, 6,850,259), every rotation within 0.0002 of unit length | `dr2 census --anims` (~30 s / game) |
| Which rig an animation is for: its first word = the skeleton's id in `_ANIMCHANNELINFO_` (zombies `0x45E6F8E0` = `zombiefullbody.big`, cutscene casts, props, cameras) | `convert/holding.py` `skeleton_ids`, `skeleton_for` |
| An item's attacks: `AnimationAttackName<i>` in `streamedassets.big/anm_<AnimBankName>.big`, each with its `root.big` partner (how far the move carries him: up to 2 m) | `holding.item_moves`, `companions`, `clip` |
| Studio: *New weapon…* / *Effects…* 3D view: **Move** box (the kind's attacks), Pause, a time slider, *In place*; the weapon follows his hand | `studio/hold_view.py`, `web/hold.js` |
| Studio: any `.anm` in the asset browser **plays** (on Chuck, or on its rig as bones); *Export .glb…* / *Open in Blender* give it as an Action | `MainWindow._show_anim`, `holding.animation_glb` |
| CLI: `dr2 extract --glb <.anm>`, `dr2 hold <item> --moves` (every attack as a Blender Action, the item parented to his hand), `dr2 info <.anm>` (keys, rig) | `cli/main.py` |

Checked by eye: the Broadsword's 360° slash and first attack in Studio's 3D view (frames
at 15/35/55/80 %, the sword in his hand throughout), the same moves rendered in Blender
from `dr2 hold Broadsword --moves` (the sword follows the hand bone), a zombie idle on
the zombie rig's bones, Chuck's idle. Fixed on the way: parts' own rest poses (the
boots stayed behind until every rig node got the rig's rest value: `clip(rig=…)`).

Not done: comparing a swing with the game frame by frame (needs a capture), the left
hand on the weapon's `IK_lhand` (the game does IK), zombies drawn as a zombie model
instead of bones, editing or replacing animations.

## Parts 1 and 2: what the research found (2026-10-12)

**A level piece** is `<piece>.big` (scene `_COMP_<piece>.big`) with `<piece>.tex` and
`<piece>_LOD.tex` in its zone archive, placed by a 208-byte record of
`ZONE_ORGANIZATION.big/ModelInstanceArray` (formats.md §Levels). The record's "piece's
number" (+196) is not its place in the archive (z03 numbers go up to 205 for 126
pieces), so the game finds a piece **by name**; a new piece takes a number past the
zone's highest. A zone shows the **first texture of a name** it finds, so a new piece's
picture needs a name of its own. Level shaders: 256 street pieces use `CM_LM` (colour ×
baked lightmap on a second UV set, which a new shape doesn't have); 40 use `LIT_CM` (lit,
no lightmap): a new piece copies one of those (`z02_hardware`).

**Collision of an item** is made by the engine (phase 11: the `MilitaryBarrier` road
block stopped Chuck; Case Zero has no `data/dynamicprops`). Invisible blockers exist:
`cBlockingVolumeItem` with `MeshVisible = "false"` (CZ `wall_short_blocking`, CW
`block_1m_1m`…), but their models don't ship. An item finds its model pack by
`MergedFilename`'s name first, then its own name, then `AssetFilename`'s
(`convert/placed.py`), so a new item's block names its own pack in both.

**Level slots** (formats.md §Levels, "Level slots"): the executable holds 82 script
names and 82 zone-list paths in the enum's order; CZ ships 4 levels' files. A zone list
names zones as `folder/zone`, so a slot can play on another level's zones (the
safehouse script plays on the street's). Other files name levels by id: zombie load sets,
the map's points, missions, cutscenes. `layout.bin` lists every loose file (name, size,
disc position); the game hashes the names itself when it reads it.

## The in-game tests (built 2026-10-12; scripts and mods in `~/.cache/dr2kit-p14/`)

All in Case Zero's street, by the safehouse exit (Chuck comes out at about −280, 3.3,
−35, looking toward −z), made by `scripts/make_t4.py` / `make_t5.py` into
`~/.cache/dr2kit-p14/mods/`. **No mission is touched** (top-level blocks only), so saves
stay loadable without the mods, **except** a save made inside the new level (T5): don't
save there.

| Test | Mod | What it is | What to look for |
|---|---|---|---|
| **T4a** a building's look | `p14-t4a` | a 4 × 3 × 4 m box with a doorway (orange bricks, a blue band) as a **new level piece** `mod_box01` of zone `prologue_z02`, at (−277, 3.18, −39), its doorway toward the street, draw distance 200 m, small `_LOD` picture | Is it there, in front of you when you come out? Does it stay when you walk away (and from far: the picture gets coarser)? Light and shadow on it? |
| **T4b** a building's collision | `p14-t4b` | the same box as an **invisible item** `ModBoxCol` (`cBlockingVolumeItem`, `MeshVisible = false`, `CollisionType 3`, its pack a copy of the road block's with the box shape) at the same place | Does the box stop Chuck? Can he walk **through the doorway** into the box (collision = the mesh), or does the doorway block (a box or hull)? Is the item invisible? |
| **T5** a map in an empty slot | `p14-t5` | `LEVEL_FOOD_BARN` = copies of the safehouse script files (`food_barn.txt` + three road blocks by its `Start` spawn point) and of the street's zone list (`food_barn/zonelist.big`, a **new file** with a `layout.bin` record); a **door** at (−281.5, 4.2, −31.5) in the street, a few metres from where Chuck comes out, to `LEVEL_FOOD_BARN` / `Start` | Does the prompt show at the door? Does it load? Do you arrive at (−266, 3.2, −32) with **three road blocks** in front of you (that is the new level)? Zombies? The map? Going back through the safehouse door? What breaks |

What each answer gives the tools:

* T4a yes → *New building…* makes the piece from any `.glb`; no → find what else a piece
  needs (the zone's `_COLLPRIMS_`, `ZONE_ORGANIZATION.tex`…), headless.
* T4b mesh → one invisible item per building; box → one per wall (the tool splits the
  model into boxes); hull → the same.
* T5 yes → *New map…* (an empty slot, started from a copy of a level, opened in the Maps
  editor), the door prefab's destination list; no → the log names what it looked for.
* T6 (stretch, after T4b): collision copied with a copied level building.

## Plan after the tests (proposed)

1. **New building…** (Studio, Maps tab; `dr2 mod new-building`): a `.glb` (any size,
   pivot at its floor centre) → a new piece of the zone it stands in (`.copy.json`
   recipes and a `new` record: `formats/pieceedits.py`, `mods/newitem.py`
   `texture_names`, done) and its collision item(s) (T4b), placed and moved together as
   one building (`convert/buildings.py` groups them); listed in *Place*.
2. **New map…**: the empty slots per game as profile data (a tool reading the two tables
   from `default_image.bin`, like `tools/effect_table.py`), a new map started from a copy
   of a level's script files and zone list (`_build_plain` copies with edits, new files
   with `layout.bin` records: done), opened in the Maps editor; the door prefab's
   destination list with the game's levels and the mod's maps and their spawn points;
   zombie load set and map points if T5 asks for them.
3. **Guides:** *Buildings of your own* and *Maps of your own* (guide 23, 24), the
   glossary (level slot, new piece), troubleshooting.

## Decisions to take (proposed defaults in bold)

1. **A new building's look:** **a `LIT_CM` template** (lit, no lightmap: the game lights
   it as it lights its lit pieces); baked shadows later (phase 12 decision).
2. **A new building's collision:** what T4b shows; if the doorway blocks, **boxes per
   wall** made from the model by the tool.
3. **A new map's start:** **a copy of a level of the same game** (CZ: the street or the
   safehouse script on the street's zones; CW: one of its levels), in a free slot the
   modder picks from a list.
4. **A save made in a mod's map** needs the mod (like a mod's own mission, phase 11):
   **warn in Studio's New map… window and in the guide.**

## Gate

* Animations (done): `dr2 census --anims` reads every key of both games; the Studio and
  Blender checks above.
* Buildings: a `.glb` building made in Studio stands in the street in game (CZ and CW),
  seen from near and far, blocks Chuck as T4b says, moves with its collision in the Maps
  editor; shared as `.dr2mod`, installed on a clean library, played.
* Maps: a new map made in Studio in an empty slot of each game, reached by a door,
  played, left by a door; shared and installed the same way.

## Status

* **Part 3 built and checked** (above).
* **Toolkit pieces for parts 1-2 built** (2026-10-12): `.pieces.json` `new` records
  (`pieceedits.new_placement`), copy recipes of level pieces (`_COMP_` renamed,
  `texture_names`, pictures straight into a copied `.tex`), plain-file copies with level
  edits (`newitem._build_plain`), **new files** in mod builds (`add/` under a folder: kind
  `file`) with `layout.bin` records (`build.new_layout_record`), the level checker taking
  a mod's own level scripts (`build._added_scripts`). Unit tests: `test_mods.py`,
  `test_pieceedits.py`.
* **T4a, T4b, T5 built** (`~/.cache/dr2kit-p14/mods/p14-t4a`, `p14-t4b`, `p14-t5`) and
  checked by build and pictures (the piece and the item's shape rendered from the built
  files); **not yet run**: the user's Case Zero was open (started 16:44, before this
  session), so no headless pre-check and no deployment.

## Start here (handoff, 2026-10-12)

1. Ask the user to close Case Zero (`pgrep -x cz_runtime`), then run the three test mods
   headless on a **copy** of their save (`~/.cache/dr2kit-p12-handoff/scripts/hl_run.py
   p14 150 ~/.cache/dr2kit-p14/mods/p14-t4a ~/.cache/dr2kit-p14/mods/p14-t4b
   ~/.cache/dr2kit-p14/mods/p14-t5`): no guest fault, the box in the frames (camera toward
   −z from the safehouse exit), the log's files (`food_barn` is only opened when someone
   goes through the door). Then `dr2 play -g cz --deploy-only` puts their deployment back.
2. Link the three mods into the user's library (switched on), deploy and launch Case
   Zero for them in a window (memory: *User tests in game*), tell them what to look at
   (§The in-game tests), wait for their answers; afterwards unlink the test mods.
3. Build the tools (§Plan) from what the tests show; then Case West (`LEVEL_W_MALL`).

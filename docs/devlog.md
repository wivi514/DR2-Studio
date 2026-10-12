# Devlog

What was done, when, and **why**: newest first. One entry per work session or
milestone. Each entry links the commits, docs and guides it touched. This is the
narrative; `formats.md` and `roadmap.md` hold the current state.

Entry template:

```
## YYYY-MM-DD — short title
**Done:** what changed, in plain words.
**Why:** the problem it solves or the decision behind it.
**Learned:** anything surprising about the games or tools (and where it is now documented).
**Docs updated:** list of files.
**Next:** what this unblocks.
```

---

## 2026-10-11 — Phase 11: Case West checked, the gate
**Done:** a CW build in the Storage Pens (new game): an added Katana, a new red Katana item
(recipe), workbench, save point, Humvee blocker, every zombie retyped to fat; all work in
game (the own mission's security pack wasn't checked). The Humvee sank into the floor (an
item stands by its origin, the Humvee's is its middle), so Studio now drops a newly placed
item onto the floor by its bottom. Gate: `dr2 census --levels` 0 problems in both games;
396 tests pass.
**Docs updated:** `formats.md`, `prefabs.toml` (checked in CW), guide index,
`phase11-kickoff.md`.
**Next:** level pieces (plan step 4, stretch) need an in-game collision test first.

## 2026-10-11 — Phase 11: items of your own (new files in archives)
**Done:** mods can add entries to archives (`add/`, kind `add` in `mods/build.py`,
inserted in name order, compressed like their neighbours; shown by *With my mods*). A new
item is made from one the game has: `mods/newitem.py` (`dr2 mod new-item … --like …
[--glb] [--texture]`, Studio's *New item from this…*) writes a **recipe** (`.copy.json`:
copy this pack, rename, my shape and PNGs) instead of game bytes, and the `items.txt`
block. `LevelEditor` sees the mod's own items through a preview of the mod.
**Why:** plan step 5's "own models"; the recipe because a shared mod may hold only the
modder's own work.
**Learned:** the first in-game try loaded forever. Headless, the full build's log stopped
after the street's zones while its parts alone went on; the new index entry differed
from all 1,110 of `streamedassets.big` only in `flags` (0 vs 2048). **`flags` is each
entry's declared alignment**: every payload of both games starts at a multiple of it
(293,894 entries). With its siblings' value the item shows and works in game.
**Docs updated:** `formats.md` (the `flags` field, with a retraction; the in-game table),
guide 19 (own items), guide 06 (`add/`, `sources/`), `ARCHITECTURE.md`, `dev/code-tour.md`,
`phase11-kickoff.md`.
**Next:** CW in-game checks; level pieces (stretch).

## 2026-10-11 — Phase 11 step 5: prefabs
**Done:** `catalog/prefabs.toml` and `prefabs.py`: save point, workbench, door to another
level, spawn point and a blocker, each cloned from a block the game ships (per game), every
position near the anchor moved with it (CW's save points keep their corners in world
space), facings turned; own prefabs as `.dr2prefab`. In the Maps tab: *Add from prefab…*,
*Settings…* (any block's keys as text), *Save as prefab…*, the mod's added triggers and
spawn points drawn (`dr2.setEditedMarkers`), and `sync_edits` when a level opens.
`levelcheck`: a door's `LevelSpawnPoint` must be a spawn point of its level (counting those
mods add); a mod's own mission gets the `SAVE_NEEDS` warning.
**Why:** plan step 5, the user's "add our own things that behave like the real thing".
**Learned (CZ, in game):** a cloned spawn point, with the safehouse exit pointed at it,
puts Chuck there; a cloned door takes him into the safehouse. And the hard way: the
user's newest save, made during the new-game test, **crashed with no mods**: a save made
while a mod's own mission runs needs that mission (a headless run with the test mission
loads it), so it loads again with any mod that keeps that mission.
**Docs updated:** `formats.md` §Levels, guide 19 (prefab steps, save warning), guides 15
and 12, `glossary.md` (prefab), `dev/studio.md`, `dev/code-tour.md`, `roadmap.md`,
`phase11-kickoff.md`.
**Next:** own models (a new item pack, needs the build to add files), CW in-game checks.

## 2026-10-11 — Phase 11 step 3: the zombie editor
**Done:** the Maps tab's *Zombie spawns* layer (every single zombie as a cone facing its
way with *type ×n*, respawn floors, clearing circles) and zombie editing: move / turn a
single zombie with the handles, its type, number and held item in the panel, delete (=
number 0), a crowd's types and amounts as one line, *Add zombie…* into the mod's own
mission (`maps_edit.ZombieEdits`, cloned from the level's main zombie mission). Zombie
figures carry their crowd's block path (`MAP_VERSION` 6).
**Why:** plan step 3, in the shape step 2's in-game tests allow: the game's zombies by
value only, new ones in the mod's own mission (new game).
**Learned:** a driven Studio run showed the markers right on CZ's street; one rooftop
zombie's spawn point sits below the drawn roof (the game puts zombies on the ground
itself), so its cone hides under the roof.
**Docs updated:** guide 19 (zombie steps), `dev/studio.md`, `dev/code-tour.md`,
`phase11-kickoff.md`.
**Next:** prefabs (step 5): save points, workbenches, doors, items from templates.

## 2026-10-11 — Phase 11 step 2: in-game tests (CZ) and the Maps editor for items
**Done:** the early in-game tests of the plan, in the CZ recomp: the user played each
build, and when the first one crashed a headless bisect (scripted presses loading a copy
of the user's save, then new games; `=== guest fault` / which files loaded in
`cz_runtime.log`) found the cause in five rounds. Built the Maps tab's editing
(`studio/maps_edit.py`, the panel's Edit section, the page's move / turn handles with
three.js `TransformControls` vendored from the same 0.186.1 tarball, checked by its SHA-1)
and `zombies.mission_spawns` (every single zombie, crate and clearing with its block
path). `levelcheck` now refuses a block added inside a game mission and counts what it
says about the game's own blocks (the census: CW's `ArenaStairs` is the only refusal).
**Why:** the plan said to test what could change the plan before building the editor
around it, and it did change: zombies can't be added inside the game's missions.
**Learned:** an added weapon, workbench and save point work and keep saves; an unmovable
item with collision blocks the player (so own walls and buildings can be items); changed
values and keys in missions work (the whole street turned into cops); **a block added
inside a game mission stops saves from loading and stalls a new game at its first save**;
a mission of the mod's own loads and runs, but only in a new game; a zombie type the level
doesn't load still showed. Also: the game ships 30 placements whose quaternion isn't
length 1 (now a warning), and save points' corner points are sometimes in world space (the
action point check now uses the shipped save points' measured spread).
**Docs updated:** `formats.md` §Levels ("Level edits in game"), `dev/studio.md`
("Editing"), `dev/code-tour.md`, guides 19 (Studio steps, zombies), 15 (level limits) and
12 (troubleshooting), `roadmap.md`, `phase11-kickoff.md`, `THIRD_PARTY.md`.
**Next:** the zombie editor in the Maps tab (crowds and the game's zombies by value, new
ones into the mod's own mission), then prefabs; the same tests in CW.

## 2026-10-11 — Phase 11 step 1: level edits as mods (`.edits.json`)
**Done:** asked the phase's open decisions (the user took every proposed default;
`phase11-kickoff.md` §Status). Built the base everything else stands on:
`levelscript.Document` finds blocks by path and adds / removes blocks and keys;
`formats/leveledits.py` holds a mod's changes to a text file by block (`set`, `add`,
`remove`; apply, diff, merge); `mods/build.py` builds the new `edits` kind over the
recomp's copy, merging several mods (several merged overrides of one entry inside an
archive now all reach it: before, the last one alone would have); `convert/levelcheck.py`
checks what edits mean; `mods/leveledit.py` is the editing session the Maps tab will use;
`dr2 level show|edit|diff`; the census gate `check_level_edits`; tests.
**Why:** the CZ recomp changes `missions.txt` itself, and two mods must be able to change
one level file; a mod holding only its changes, by block, does both.
**Learned:** the game's tool sorts keys **ignoring case** (plain order fails on 399 CZ
`items.txt` blocks); its block layout is regular enough that `render` writes back every
shipped block of the editable files except one `items.txt` block and the hand-written
`zombiesets.txt`, whose `// cost` comments a changed value must keep (a bug in phase
10's `set`, fixed). Shipped files mix gap sizes between blocks (`prologue_menu.txt`), so a
re-added block can't always get its old blank lines back; the gate counts those
separately. On a real build, `zombie_fat` added to the main menu's crowd gets the warning
that `LEVEL_PROLOGUE_MENU` doesn't load it.
**Docs updated:** `formats.md` §Levels, `ARCHITECTURE.md` (mod format), `roadmap.md`,
`phase11-kickoff.md`, `dev/code-tour.md`, `glossary.md`, guide `19-edit-a-level.md`
(new, CLI part), `modding/README.md`, `mods/manifest.py` docstring.
**Next:** the early in-game tests (added save point, added weapon, blocking item, added
pack), then the Maps tab editor.

## 2026-10-11 — Phase 11 plan: add your own things from prefabs
**Done:** added to `phase11-kickoff.md` (user: add our own stuff to the map, a usable
item, a save point, zombies to a spawner, a building, a road…, each behaving like the
real thing, from prefabs): a research table of what makes each thing work, plan step 5
(prefabs as data cloned from shipped examples, the *Add…* palette, own models, the
modder's own `.dr2prefab`), decisions, gate and in-game checks.
**Learned (checked in both games' data):** a **save point is a trigger**:
`cTriggerVolume` with `ActionType = 4` in `waypoint_<level>.txt` (a box, the action point
and facing, `DisplayName 55094`; CZ 4, CW 34), the toilet only scenery; doors to levels
are `ActionType 3` with `Level`; a workbench is an item placement of the
`cComboStationItem` `Workbench`; an item's behaviour is its `items.txt` class. Most items'
collision is made by the engine from `CollisionType` (3 on 316 CZ items); only 99 CZ /
76 CW item models carry a Havok mesh, so own buildings and roads can go in as unmovable
items (like `wall_long_blocking`) without building a Havok search tree ❓ (in-game test).
The mod build refuses new vpaths: own models need it to add files.
**Docs updated:** `phase11-kickoff.md`, `roadmap.md`, this entry.
**Next:** phase 11 in a fresh conversation (user, 2026-10-11): the kickoff's §Start here
now gives the first questions, an order of work and the early in-game tests.

## 2026-10-11 — Phase 11 plan re-checked against phase 10
**Done:** `phase11-kickoff.md` updated (user: make it "properly ready"): a new §What
phase 10 gives table (each piece phase 11 builds on, and what it still lacks), the plan
steps pointed at those pieces, the gate and decisions brought up to date.
**Why:** the plan was written before phase 10 was built; it assumed readers and views
that now exist, and didn't know about the collision file.
**Learned (checked today):** every block-format `.txt` of `datafile.big` already writes
back byte for byte (CZ 24, CW 39; five other-format files named); `Document` can only
change a value, not add or remove blocks; single zombies, respawn crates, removals and
`zombiesets.txt` aren't read yet; items are one glTF node each with file and line (the
page can move one without a rebuild); three.js `TransformControls` isn't vendored;
Studio has no "mod being edited"; the CW recomp has no `game_patched`. A piece's
collision lives in `MERGED_COLLISION.big` with a Havok search tree, so moving a building
piece needs an in-game test first. The research's "CZ items without models" claim is
retracted there (phase 10 found every model).
**Docs updated:** `phase11-kickoff.md`, `roadmap.md`, `README.md`, `CLAUDE.md`, this entry.
**Next:** the user decides on phase 11 (§Decisions to take).

## 2026-10-11 — Phase 10 stretch: floors, zombies, time of day, collision
**Done:** the four stretch items, each a Maps layer or setting and in the level export:
- the in-game map's upper floor and basement pictures (CZ `map_prologue_2f`, CW `map_2f`,
  `map_b1`), placed by fitting them to the main map (profile `map_floors`);
- zombies standing in their areas: the crowds `missions.txt` puts in each zombie area
  (`convert/zombies.py`), example spots, a few looks per type; `--zombies`;
- time of day: the level's lighting table by hour and area (sky gradient as the `Skybox`
  shader draws it, fog, key and ambient light);
- the collision mesh: `formats/collision.py` reads every Havok triangle mesh of every
  zone (1,514 shapes); `level.zone_collision` places them; a *Collision* layer,
  `--collision`, and the add-on's *Zombies* / *Collision* boxes.
**Why:** the stretch list of `phase10-kickoff.md` (user: "do the stretch items").
**Learned:** collision shapes are found by their `hkCollisionShapeMesh` entry, not the
`meshCOL_` prefix (45 shapes don't have it). A shape's vertices are in its **piece's**
space with the node offsets already in (applying the node's matrix counted them twice), or
already in world space, and nothing in the file says which: the placement is kept when it
lands among the zone's pieces. Header word 1 is a collision-scene node number that finds
the piece of shapes named after nothing (CZ's street ground under the Start spawn was
missing until then). 5 CZ shapes stay unplaced and named. Checked: ground under the
spawn points, Studio pictures against the buildings in both games, census 0 problems,
the Blender add-on gate.
**Docs updated:** `formats.md` §Levels ("Collision"), `modding/18-maps.md`,
`13-blender-addon.md`, `dev/code-tour.md`, `glossary.md`, `roadmap.md`,
`phase10-kickoff.md` §Status, `CLAUDE.md`, this entry.
**Next:** the user's own test of the Maps tab; phase 11 waits for approval.

## 2026-10-11 — Phase 10 step 5: see your mods without the game
**Done:** `mods/preview.py`: the mod library's switched-on mods (Play's set and order,
over the recomp's `game_patched`) applied to a view of the game, `ModdedTree`, with the
build's own bytes. DR2 Studio's **With my mods** switch (Ctrl+M) puts every view on it
or back on the game; the Library marks changed items with ✎, the details and the Maps
panel name the mod; saving a mod's file redraws.
**Why:** the phase's third goal, and the user's: make "without mods" one click.
**Learned:** a level texture often sits in several packs of a zone, and the game uses
the **first** copy for every piece. A blue wall texture on the shed's own copy didn't
show in game; on the garage pack's copy (earlier in the zone), the user saw blue walls.
The texture finder now goes by archive order in a zone, and the build puts a level
texture on every identical copy (CZ 457, CW 1,217 shared names). Also: `COMMON_TEXTURE.tex`
isn't empty in 31 zones, and `.bct` name endings aren't a small-pack trait (retractions).
**Docs updated:** `formats.md` §Levels, `modding/05`, `12`, `18`, `dev/studio.md`,
`dev/code-tour.md`, `ARCHITECTURE.md`, `glossary.md`, `phase10-kickoff.md`, this entry;
memory: the user prefers to look in game themselves.
**Next:** the remaining gate items: Case West frames, the Maps overview picture, the index
rebuild; then hand over for the user's test.
*Later the same day:* the Maps overview picture (the in-game map in a corner, both games,
placed by `fe_map_points`), and the index rebuilt (both games, 0 Library problems; the
Library's world textures now have a *Lightmaps (levels)* group). The test mod was taken
out of the recomp. Then, for Case West: `dr2 studio --map LEVEL [--at]`, and a test mod
recolouring the safehouse showed in game (the user's screenshot: magenta walls).

## 2026-10-11 — Phase 10 step 4: exporting levels
**Done:** `catalog/level_export.py`: a level as one `.glb` per zone (or one for all),
buildings placed, items and doors, markers (spawn and map points as empties, areas and
triggers as outlines, the navigation mesh as a mesh), each group tagged by layer; the
level's text files and an `info.txt`. `dr2 export <level>`, *Export zone… / Export
level…* in the Maps tab, and the Blender add-on's **Import zone**: collections per zone
and layer, the lightmaps multiplied into the colours.
**Why:** the phase's second goal: take a level to Blender as the game builds it.
**Learned:** Blender evaluates an `EnumProperty`'s `items` lambda outside the module's
scope (a `NameError`), and in a fresh session the callback runs before anything has
loaded dr2kit: the callbacks are module functions that load the toolkit first.
**Docs updated:** `modding/18-maps.md` (export), `modding/13-blender-addon.md` (Import
zone), `modding/04-extracting.md`, `dev/blender-addon.md`, `dev/code-tour.md`,
`phase10-kickoff.md`, this entry.
**Next:** step 5, seeing the switched-on mods in every view.

## 2026-10-11 — Phase 10 step 3: the Maps tab
**Done:** DR2 Studio's **Maps** tab: the levels on the left; a three.js page that streams
a level zone by zone (nearest first, the game's small textures far away; each zone built
once into a `.glb` and kept on disk, three builder threads); layers for spawn points,
zombie / map / lighting areas, triggers, sound areas, map points and the navigation
mesh; Go to; fly and orbit camera; click anything to see what it is, with Open in
Library / Blender and Export. Level materials drawn as the game's shaders do: lightmaps
and two-texture blends. Guide 18.
**Why:** the phase's first goal: see a whole level, as the game shows it.
**Learned:**
- **A decoding bug since phase 3:** `SHORT2N` vertex elements (only the level
  lightmap UVs) have x in the *high* half of the word, not the low half. The Xbox's
  vertex fetch transposes 16-bit pairs and the game's shaders swap them back; the CZ
  recomp's notes describe exactly this. Found by drawing CZ's safehouse bathroom from a
  recomp capture's own camera: blocky shadows across the door, gone once swapped.
- 639 lightmap slots (`LM_…_NE`, `AO_…_si`…) were taken for normal / self-illumination
  / detail / specular maps by their ending: fixed (`texture_role` → `lightmap`).
- How the level shaders combine their textures (read with XenosRecomp): the lightmap is
  the lighting (`colour² × lightmap²`), on the draw's last UV set; floors mix two colour
  maps by a mask's green channel (`CM2DDU`) or the overlay's alpha (`CM2DDX`).
- The camera of a recomp capture can be rebuilt exactly from the dumped view-projection
  (`c0`–`c3`, row 1 ÷ 9W/16H): Studio and the game frame line up to the pixel.
- A search had sent Studio to the Files tab since phase 8 (by tab number): fixed.
**Docs updated:** `modding/18-maps.md` (new), `modding/README.md`, `formats.md` (§Levels
materials, §Vertex declarations with a retraction), `ARCHITECTURE.md`, `dev/studio.md`,
`dev/code-tour.md`, `glossary.md` (lightmap), `phase10-kickoff.md`, this entry.
**Next:** step 4, exporting zones and levels.

## 2026-10-11 — Phase 10 step 2: what the level text files place
**Done:** `formats/levelscript.py` reads the engine's block text files keeping every
line (so they write back byte for byte, and a later editor changes only the lines it
must); `convert/placed.py` turns a level's files into items, doors, spawn points, zombie
areas, map and lighting areas, triggers, sound areas, map points and the navigation
mesh, and finds every item's model; `level.things_glb` places the items; `dr2 level
things`; the level census reads every level file.
**Why:** the Maps tab shows these as layers, and phase 11 (editing) needs files that
come back unchanged when nothing changed.
**Learned:**
- Every placed item and door of both games finds its model (CZ 1,060, CW 1,835). The
  research thought 482 CZ items had none: CZ names its prop packs after the item
  (`Chair_3.big`), and a pack can be the scene itself or hold it under the asset's name.
- Some packs hold empty `.big` placeholders for texture variants (`adboard_cafe`),
  chosen by `TextureSubType` (not drawn yet).
- Item placements nest (a hot dog stand's sodas), with world positions.
- Polygons named by a lighting volume are lighting areas, not map areas.
- Rendered the bowling alley with its items: balls on the ball returns, bottles on the
  tables, pins at the lane ends: the item rotation convention is the zone one.
**Docs updated:** `formats.md` §Levels (grammar, classes, items → models with a
retraction), `dev/code-tour.md`, `glossary.md` (level script, spawn point, trigger, nav
mesh, map area / point), `phase10-kickoff.md` §Status, this entry.
**Next:** step 3, the Maps tab.

## 2026-10-11 — Phase 10 step 1: levels read and assembled
**Done:** `formats/level.py` reads the zone list and every zone's placement table (and
writes them back identically); `convert/level.py` lists levels, reads a zone and builds
it as one `.glb` with every piece in its place; `gltf.Assembler` merges `.glb` files
(one mesh per piece however often it is placed, shared textures stored once);
`dr2 level list|info`; `dr2 census --levels`.
**Why:** everything else in phase 10 (the Maps tab, the export, mods in the view) stands
on putting the pieces in the right place, so the placement maths had to be settled first.
**Learned:**
- world = rotation × (scale × local) + position, quaternion as stored: 1,868 of 1,894
  placements reproduce their stored bounds within 8 mm; 23 more have loose shape bounds
  but their vertices fit; 3 unexplained (named in `formats.md` §Levels). Pictures in
  Blender of the bowling alley (inside and out), all of Fortune City and CW's
  `living_research`: everything meets.
- The research had the piece number at +200 (it is +196) and +144 as a float 0 (it is a
  flags word; 0x20 on trees, foliage, fans, some lights and beams). Retraction kept.
- One CW record (`glower_fl`) stores a quaternion of length 1.017; normalised.
- **A bug since phase 3:** level pieces exported their small `_LOD` textures, because a
  zone lists `<piece>_LOD.tex` first and the finder didn't treat `<piece>.tex` as the
  piece's own pack (its scene is `_COMP_<piece>.big`). Fixed for every model: `_LOD`
  packs now rank last. 15 texture names in level pieces aren't in either game at all.
**Docs updated:** `formats.md` §Levels (and the format table), `dev/code-tour.md`,
`phase10-kickoff.md` §Status, this entry.
**Next:** step 2, the level text files (items, doors, spawn points, map areas…).

## 2026-10-11 — Research for a potential phase 11: edit levels
**Done:** the user asked to prepare the potential phase 11 (see, modify zombie spawns;
move and add objects). Researched and wrote `phase11-kickoff.md`. Not approved, not built.
**Learned:**
- Zombie spawns live in `missions.txt`, per mission and level: crowds
  (`cMissionZombieFactory` into named `cZombieWarehouse` areas of the level file), single
  zombies (`cMissionSpawnZombie`, with type and held item), respawns, removals, limits.
- `zombiesets.txt` decides which zombie types a level loads, with a memory cost: a new
  type in a level probably needs adding there.
- The CZ recomp's `game_patched` `datafile.big` already changes `missions.txt` and
  `outfits.csv` (co-op), so level edits must be mods of changes by block name
  (`.edits.json`), applied over that copy, not whole-file replacements.
**Docs updated:** `phase11-kickoff.md` (new), `formats.md` §Levels (zombie spawns, text
style, the recomp's edits), `roadmap.md`, `glossary.md` (zombie factory / area),
`phase10-kickoff.md`, `docs/README.md`, `CLAUDE.md`.
**Next:** phase 10 (fresh conversation); phase 11 only if the user decides after it.

## 2026-10-11 — Phase 10 plan approved; editing levels set aside for phase 11
**Done:** the user approved the phase 10 plan and its decisions, asking that the
switched-on mods be shown with an easy switch to see without them. Editing levels
(zombie spawns, moving and adding objects) is a possible phase 11.
**Why:** keep phase 10 about seeing and extracting; leave a clean path to editing.
**Learned:** nothing new about the games.
**Docs updated:** `phase10-kickoff.md` (§Status, §Decisions, phase 11 note),
`roadmap.md` (phase 11), `CLAUDE.md`.
**Next:** phase 10 step 1 when the user says go.

## 2026-10-11 — Research for phase 10: Maps
**Done:** the user asked for a much bigger phase: a tab to see the game's maps (levels)
in 3D, extract them, and see them with the player's mods applied without launching the
game. Researched the level data of both games and wrote `phase10-kickoff.md`. Not built.
**Learned:**
- A level is `models/environment/<level>/`: a `zonelist.big` (zone names, bounds,
  centres) and one archive per zone. Every piece in a zone is an ordinary scene our
  reader already handles (1,573 of 1,573 in the five main levels).
- `ZONE_ORGANIZATION.big/ModelInstanceArray` places them: 208-byte records with name,
  scale, quaternion, position, world bounds and a draw distance (CZ 922, CW 972). A piece
  is stored around its centre.
- Everything else is plain text in `datafile.big`: 886 / 902 placed items, doors, spawn
  points, zombie areas, map areas, triggers between levels, the navigation mesh, the
  in-game map's rooms and points, light by hour. Not digest-checked.
- Items find their models through `items.txt` (`AssetFilename`, CW `MergedFilename`) in
  `streamedassets.big`: all of CW's placements, 577 of 1,059 in CZ (a demo: the rest is
  to find or absent).
- Level materials add AO maps (second UV set) and two-texture blends that today's export
  ignores; collision geometry's form is unknown.
- Showing mods needs no new format work: `mods/build.py` already makes the exact bytes per
  vpath; a tree layer in front of `AssetTree` can serve them to every viewer.
**Docs updated:** `phase10-kickoff.md` (new), `formats.md` §Levels and status rows,
`roadmap.md` (phase 10), `glossary.md` (level, zone, piece, placement, navigation mesh,
AO map), `docs/README.md`, `CLAUDE.md`.
**Next:** phase 10 step 1 (read a level and assemble a zone) once the user says go;
phase 9's user test and in-game check are still owed.

## 2026-10-11 — Phase 9 handed to the user for testing
**Done:** started DR2 Studio (commit `89d8862`, index schema 5 already built for both
games) so the user can try the Variants panel, Detail, colour choices, *Export .glb…*
(as shown) and *Open in Blender* / *Export all…* (organised) in a real window.
**Why:** the phase 9 gate drove Studio headless only; a person's test in a real window
has caught what the gates missed before (phase 8's colours, Open in Blender).
**Learned:** nothing new yet.
**Docs updated:** `phase9-kickoff.md` §Status (owed: the user's test), `dev/testing.md`
§Phase 9 results (a row for it).
**Next:** fix what the user reports; then the in-game zombie check.

## 2026-10-10 — Phase 9: variants (one look per zombie, exported as shown or organised)
**Done:** built phase 9 from `phase9-kickoff.md`. `dr2kit/convert/variants.py` classifies a
model's parts the way the game does (its 53-record shape-group table, copied into the
profiles by the new `tools/variant_table.py`, and its prefix matcher) into slots (head,
headwear, shirt, trousers, skirt, feet, tall boots, head tumour), on/off parts (wound
caps, burnt, bare arms, glasses…) and prop states (the slot machines' damaged logo, win
screen, far copy), and finds each material's colour choices in the shader bank. A look
is plain text (`head=2 shirt=3 colour.jersey=4`) and converts to the game's hide mask and
back. DR2 Studio has a Variants panel beside the 3D view (parts hide at once, colours
re-bake), the Library pictures show the default look, and each zombie is one Library
item with its three detail levels inside (index schema 5). Exports: *as shown* (only the
look) or *everything, organised* (group collections in Blender with the other parts
hidden, colour choices in Blender's glTF Variants tab), `textures/colours/`, variants in
`info.txt`; `dr2 variants`, `--variant`, `--variants`, `dr2 census --variants`.
**Why:** the user saw zombies wearing every head and shirt at once and asked to choose a
look, see it, and export it that way or with everything.
**Learned:**
- **Retraction:** the table's records are `{u64 mask, u32 pattern, u32 0}` from CZ
  `0x829DF718` (CW `0x829F25D0`). Read 8 bytes late (the research), each pattern got the
  mask of the record before it: that was the "halved bits" and the "unreadable" tall-boots
  mask (`0x10000000000000`). The classifier's own loads (`ld r29,0(r6)`, `lwz r11,8(r6)`)
  settle it; the CZ recomp's measured values are the table's own.
- The matcher (`sub_82795420`) is a case-sensitive prefix test per comma alternative;
  `*` ends one; the `*` record counts only when nothing else matched.
- A slot table (CZ `0x8208A2E0`) lists the 7 numbered slots; the recomp's measured mask
  hides every number but one per slot, numbers the model lacks included (no hat).
- The name rule `<own>N.pdv` / `<own>_varN.pdv` reproduces CZ's colour list exactly and
  also gives the `_3` models (unlisted) and CW (empty list: 289 choices for 81 materials).
- Misplaced digits: CZ `zombie_soldier_3` ×2, CW `zombie_security_2` and `_3` ×2 each.
- The research's prop-state counts (70 models…) matched `window`/`wings`; by twin shapes
  only the two slot machines keep states as shapes (retracted in `formats.md`).
- The in-game capture save starts in the safehouse bathroom: no zombies to check there.
**Docs updated:** `formats.md` §Variants (layout, matcher, slot table, mask decode, colour
rule, retractions), `modding/17-variants.md` (new), `modding/README.md`,
`modding/16-library.md`, `modding/13-blender-addon.md`, `modding/12-troubleshooting.md`,
`modding/asset-catalogue.md`, `modding/context.toml`, `glossary.md` (look, slot, on/off
part, hide mask, colour choice, prop state; detail level), `ARCHITECTURE.md`,
`roadmap.md`, `phase9-kickoff.md` §Status, `dev/code-tour.md`, `dev/gltf-mapping.md`,
`dev/blender-addon.md`, `dev/testing.md` §Phase 9 results, `docs/README.md`, `CLAUDE.md`.
**Next:** the in-game check (a save outside the safehouse, or the user playing), and the
game code that rolls each zombie's look, so Default and Random follow the game.

## 2026-10-10 — Research for phase 9: variants
**Done:** the user asked for a phase so zombies (and items, buildings) show one look
instead of every part at once, with export as shown or with everything. Researched and
wrote `phase9-kickoff.md`. Not built yet.
**Learned:** the zombie part groups are a 64-bit mask table of shape-name patterns in the
executable (heads 1-5, shirts 1-6, trousers 1-7, feet 1-7, headwear 1-5, burnt, gas,
tumours, wound caps), the same in CW. CZ's `zombie_pdv_variations.txt` lists 129 colour
choices, all found by name in `shaders/deadrisingprologue-sc.big`; CW's list is empty but
265 such value sets ship. The Library's "variant 2/3/4" are detail levels. Blender reads
`KHR_materials_variants` but not `KHR_node_visibility` (checked in 5.2's add-on).
**Docs updated:** `phase9-kickoff.md` (new), `formats.md` §Variants, `roadmap.md`,
`glossary.md` (variant, detail level, wound cap), `docs/README.md`, `CLAUDE.md`, this devlog.
The user then shared the CZ recomp's measurements: mesh names become variant bits at load
(half the table's stored values, checked here against its live mask), each zombie has a
64-bit hide mask from its spawn record, and misplaced digits in names lose the bit (CZ
`zombie_soldier_3`; also CW `zombie_security_2`, found in the shape census here). Added to
`formats.md` §Variants and the phase plan.
Buildings dropped from the goals (the user isn't sure they have variants); the census only
reports them. Wrote phase 9's handoff (§Start here: how the research was done, since the
scripts were deleted) for a fresh conversation; release test builds listed as owed in
`phase8-kickoff.md` §Status.
**Next:** phase 9 step 0: what writes the mask (the per-slot roll) and picks the colours.

## 2026-10-10 — The Windows build's 3D view stayed at "loading…"
**Done:** the user's next Windows test: clicking a model now got as far as the 3D view,
which said "loading…" forever. three.js's `vendor/three/build/` had never been committed:
the root `.gitignore` rule `build/` matched it. The Linux release is built from the working
folder (files present), the Windows one from a git clone (files absent). Fixed: the rule is
`/build/`, `three.module.js` and `three.core.js` are committed; `model_view.viewer_files`
follows the page's imports, `test_3d_view_has_all_its_files_in_git` checks they are all
tracked, the release gate checks the bundle has them, and `viewer.html` says when a file
is missing instead of staying at "loading…" (checked in a real web view with a copy
missing `three.core.js`). The rebuild also showed the release venv's installed dr2kit
can lag the checkout (PyInstaller packs the checkout, but the gate imported the old copy):
`check_environment` now refuses a stale install.
**Learned:** an ignore rule for the top-level build folder needs the leading `/`; a build
from a clean clone catches files that only exist in my working folder.
**Docs updated:** `dev/packaging.md`, `modding/12-troubleshooting.md`, this devlog.
**Next:** the user retests the rebuilt Windows release.

## 2026-10-10 — Release builds had no help, so Studio showed no model
**Done:** the user's Windows test: games found, the Library listed, but clicking a model
left "No game data found yet" in the middle. The bundle had no `dr2kit/help/` (PyInstaller
collected data from the source checkout, where the guides are in `docs/modding/`);
`show_asset` raised `FileNotFoundError` from the "How to mod this" box before switching
to the 3D view, and a windowed program shows no traceback. The Linux AppImage had the same
fault. Fixed: the spec adds the guides; the release gate runs the bundled `dr2 help`;
missing help no longer stops an asset; `install_error_hook` puts any unexpected error in
the log, an error box and `studio-errors.log`. Test: `test_errors_are_shown_and_…`.
**Learned:** my bundle checks ran `dr2` commands, never Studio's click path or `dr2 help`;
the gate now covers the help, and errors can no longer vanish silently.
**Docs updated:** `dev/packaging.md`, `devlog.md`.

## 2026-10-10 — Test builds for Linux and Windows
**Done:** at the user's request, release builds to test: Linux (this machine: AppImage
263 MB, `tar.zst` 222 MB, add-on) and, for the first time, **Windows** on the recomps'
build laptop (`czwin`): `DR2Studio-windows-x86_64.zip` 276 MB. Both pass the licence gate;
both bundles' `dr2` export a model, a sound, a CW movie, build an index with model
pictures, pass `dr2 library --check` and export a group, on real game data.
**Learned (Windows):** MSVC crashes compiling ffmpeg's `libavformat/cbs.c` when its table
of bitstream readers is empty (fixed by enabling one AV1 filter for MSVC builds); an MSVC
ffmpeg puts its `.lib` files in `bin\`; Windows Python doesn't find DLLs on `PATH`, so
PyInstaller dropped PyAV until its ffmpeg DLLs were placed next to it (the licence gate
caught it); a git checkout with `autocrlf` breaks bash scripts. The Linux LGPL ffmpeg
has no x86 assembly here (no `nasm`), which changes the MP4 encoder's bitrate.
**Docs updated:** `dev/packaging.md` (§Building one on Windows, MP4 bitrate), `devlog.md`.
**Next:** the user tries both builds (GUI, Play, Open in Blender on Windows); a real
release still needs the GitHub remote and CI (Ubuntu 22.04 for the glibc floor).

## 2026-10-10 — Rigid parts placed by their node (Zombrex box, cameras, vehicles…)
**Done:** the user saw the Zombrex box's lid flap sticking out of its side. Our bug: an
unskinned shape's vertices are relative to its node (shape word 1, which every draw's
palette start repeats), and the exporter, the 3D view and the Library's pictures put them
at the model's origin. Counted first: CZ 369 and CW 665 models (props, vehicles, cutscene
props, level pieces) have such parts on a node away from the origin. Now `.glb` exports
hang each rigid shape under its node (`Scene.rigid_node`), the importer removes the
node's rest pose on the way back, and the renderer places them (thumbnail version 6).
Checked: drawn both ways, only the placed version is right (Zombrex lids close the box,
the security camera's base joins it, the canyon vista lies flat); `dr2 census --reimport`
on both games: every model byte-identical after export and re-import (CZ 1,397, CW
1,495; a first version that removed the node with a matrix inverse failed 3 CW sky
domes and a roof by float noise on their scaled nodes, so the importer now reads the
offset from the mesh's own node when it still hangs under its game node); Blender 5.2
puts the Zombrex lids at the box's end, parented to their nodes; unit test
`test_rigid_part_hangs_under_its_node_…`.
**Learned:** phase 3's capture gate compared characters (skinned), where rigid draws sit
on nodes at the origin, so it couldn't see this. `formats.md` §Rigid parts.
**Docs updated:** `formats.md`, `dev/gltf-mapping.md`, `devlog.md`.

## 2026-10-10 — Striped faces on Chuck's hat heads (open question)
**Done:** investigated the user's report of green/purple bands on `head_White_Cowboy_Hat`
(and the mohawk head). The bands are in the shipped texture (all mip levels; shared by
both cowboy-hat heads and the mohawk head), the headwear doesn't cover them (rendered
together), the shader doesn't replace them, and no other head of either game has them.
Recorded as ❓ in `formats.md` and in the asset catalogue; nothing changed in the code.
**Next:** check in game what Chuck's face looks like with the mohawk or a cowboy hat
(and which texture the recomp binds for that draw).

## 2026-10-10 — In the help: seeing textures and hiding bones in Blender
**Done:** at the user's request, how to see a model's textures in Blender (**`Z` →
Material Preview**) and how to hide the bones (Viewport Overlays → untick Bones; hide
`Armature` in the Outliner; Stick/Wire, not In Front) is now a section of
`07-blender-setup.md` ("Seeing the model clearly: textures and bones"), with the manual
import's *Disable Bone Shape* option. Pointed to from `08`, `13`, `16`,
`12-troubleshooting.md` (rows for grey models, balls, bones in the way). In the app:
the model's "How to mod this" box gives the two shortcuts with a link straight to that
section (context steps may now carry `[text](guide.md#section)` links, opened in the
help window), Studio's log says them when Blender starts, and the help's search finds
them (F1). Test: `test_help.py::test_context_links_reach_a_section`.
**Why:** the user asked for it to be documented and easy to reach from the app.
**Docs updated:** the guides above, `context.toml`, `devlog.md`.

## 2026-10-10 — Blender: no spheres on the bones, textures shown
**Done:** the user opened `boss_mechanic` in Blender and asked whether the balls all over
him and the grey look were normal. The balls are Blender's glTF importer drawing every
bone with its `Icosphere` shape; the grey is Blender's Solid view. Studio's Open in
Blender and the add-on's Import now pass `disable_bone_shape=True` (when the importer
has the option: Blender 4.2+), and Open in Blender switches the 3D views to Material
Preview. Checked in a windowed Blender 5.2 on the mechanic: armature and meshes, no
sphere, Material Preview. `test_open_in_blender_script` now also checks no Icosphere is
made.
**Docs updated:** `dev/studio.md`, `modding/12-troubleshooting.md`, `devlog.md`.

## 2026-10-10 — Open in Blender imported only an Icosphere
**Done:** the user opened `cine_backpack_sc710` with Studio's **Open in Blender** and got
only an Icosphere. The `.glb` was complete (5 meshes, 11 bones), and the same script
imported everything in background Blender, with factory settings and with the user's own.
Run in a real Blender window, it failed: the glTF importer raised `'Context' object has
no attribute 'object'` because the script ran from `--python` before the window was up,
right after `read_homefile`; the importer's bone-shape Icosphere had already been
created, the armature was left in no scene. Every model was affected, not only this one.
The script now empties the start-up scene through `bpy.data` and imports from a
`bpy.app.timers` callback (directly when Blender runs in the background). Checked in a
windowed Blender 5.2 on the same file: armature + 5 meshes in the tagged collection.
**Why:** the user's report.
**Learned:** the phase 7 check of this script ran Blender with `-b`, which doesn't take
the windowed path. New test `test_studio.py::test_open_in_blender_script` (compiles the
script, checks the timer, imports a synthetic model in Blender when installed); the
windowed path needs a display and was checked by hand.
**Docs updated:** `dev/studio.md`, `modding/12-troubleshooting.md`, `devlog.md`.
**Next:** as before.

## 2026-10-10 — Play started source builds without their renderer
**Done:** the user saw Play (Studio, `dr2 play`) start the game with no picture. The CZ
recomp's log said it: `[vk] renderer OFF (set CZ_VKDRAW=1 to enable it)`. A release ships
`cz_defaults.env` / `cw_defaults.env` next to its program with `CZ_VKDRAW=1` /
`CW_VKDRAW=1`; a source build (`runtime/build/cz_runtime`, which Play picks when there is
no release beside `assets/`) has none, and the recomps keep the renderer off by default
for headless test runs. Play now adds the profile's new `play_defaults` (the renderer
switch) when the program has no defaults file beside it; a variable already set wins,
like the recomp's own loader. Test: `test_library.py` (source build gets it, a release's
file and the user's own setting are respected).
**Why:** the user's report.
**Learned:** the phase 7 Play gate (`tools/newcomer_gate.py`) set `CZ_VKDRAW=1` itself
for its frame dumps, so it never saw Play's own environment.
**Docs updated:** `modding/12-troubleshooting.md` (§Playing), `dev/code-tour.md`,
`devlog.md`; profile comments.
**Next:** as before.

## 2026-10-09 — Model colours: zombie clothing, glasses, eyelashes, see-through hair and foliage
**Done:** fixes from the user looking at the Library's pictures, each counted over both
games before fixing:
- **Zombie clothing** red/green/purple (the issue fixed earlier for the 3D view and the
  `.glb`): the thumbnail renderer used the weight map as a colour. It now bakes such
  materials with `convert.material`, fed with the index's 128-px thumbnails. 131 models
  (CZ 83, CW 48).
- **Bright green glasses**: `ProtoSkinnedLens` (21 materials) takes its colour from
  `gLensColour`; the texture is channels. New **lens** bake (`1595db80.po` read with
  XenosRecomp): colour `1.4·B²·gLensColour`, opacity `G²·gLensColour.a`.
- **Katey's red eyes** were her eyelashes: pure red cards drawn opaque. The lash shader
  `ProtoSkinnedHair` colours by `R²·gDiffuseColourControl` with opacity
  `A·gHairTransparencyScale` (`ca7f0160.po`), and so do the zombie hair shaders. New
  **hair** bake (66 materials).
- **Transparency in general**: the `.glb` (so Blender and Studio's 3D view) and the
  pictures drew every material opaque. Measured which shaders use alpha as transparency
  over every colour map of both games: `…OM…` (opacity map) and hair shaders; cloth and
  skin use it as a mask. Those materials now export as `alphaMode: MASK` (lenses
  `BLEND`) and the renderer alpha-tests them; clear glass that vanished entirely
  (20 models: shop windows, truck windows, shards) is drawn solid so it keeps a picture.
- The renderer handled pictures only up to 128 px (16 key bits for the pixel, 400 lattice
  steps); found while making 512-px close-ups, now sized from the picture.
A thumbnail version (`THUMB_VERSION`, meta `thumbs:<game>`, now 5) makes a build redraw
every picture without re-reading the archives (CZ ~140 s, CW ~200 s). Checked by
looking at every character and zombie of both games and close-ups of Katey, the pawnshop
owner, a pair of CW sunglasses, a tree and zombie hair.
**Why:** the user's reports; the phase 8 contact sheets showed the first one and I missed it.
**Learned:** a texture's look in a file says little: lens textures and lash textures are
channel weights, and alpha is transparency only on some shaders. Read the pixel shader
before trusting a `_cm`. Recorded in `formats.md` (§Materials: lens and hair families,
retraction of "gLensColour / gDiffuseColourControl don't replace the colour map";
§Texture conventions: the rule by shader).
**Docs updated:** `formats.md`, `dev/gltf-mapping.md`, `dev/code-tour.md`,
`dev/testing.md`, `ARCHITECTURE.md`, `devlog.md`; module docstrings of
`convert/material.py`, `convert/render.py`, `convert/gltf.py`.
**Next:** as before.

## 2026-10-09 — Phase 8: the Library, model pictures, rigs, export everything at once
**Done:** DR2 Studio opens on a new **Library** tab that sorts both games by what things
are (Models: characters, zombies, items, cutscene props, crowd, environments; Skeletons;
Sounds: music, voices, cutscene audio, ambience, footsteps, zombie sounds, effects;
Textures by use and role; Text; Movies), from a rules file (`dr2kit/catalog/groups.toml`)
applied when the index is built (schema 4: tables `scene` and `library_item`, relation
`model-rig`). Every model gets a picture drawn by a new numpy software renderer
(`convert/render.py`). A model shows its textures with pictures, the rig it matches, and
its counts against the limits; **Export all…**, the Library's **Export…** and
`dr2 export` write one folder per model (`.glb`, PNGs, rig, `info.txt`) or WAV / MP4 /
JSON / PNG files, with progress, cancel and resume. `dr2 library` lists the groups;
`--check` is the count gate.
**Why:** the user's direction for phase 8 ("only show models with their texture, bones and
all, and export all of this at once; just show audio, etc.").
**Learned:**
- The 98-bone rig families (player, female, large, child, cutscene twins) have **the same
  bone names**; only the rest pose tells them apart (every character matched within 1 mm
  of one family). First version matched names only and put everyone on the child rig.
- On the cloth and skin shaders a DXT5 colour map's alpha is a mask (97% of texels under
  0.5 on drawn-solid clothes), not transparency; only hair uses it as see-through. The
  first thumbnails alpha-tested and drew zombies naked. `formats.md` corrected (old claim
  struck through), `15-limits.md` now says to keep that alpha.
- GASP voice tables: concepts named by hash, 2 of 41 resolved, no subtitle link.
- A software renderer is fast enough: rasterising by a lattice of points per triangle
  and one sort of packed (pixel, depth, point) keys, shading only the winners: 0.03-0.07 s
  a model; the first version (shade every point, argsort floats) took 0.1-0.45 s.
- A line edit matched `[names]` inside a comment of the TOML and cut the label rules; the
  orphaned keys attached silently to the last group. The loader now refuses unknown keys.
**Docs updated:** `modding/16-library.md` (new), `modding/README.md`, `03-browsing.md`,
`04-extracting.md`, `12-troubleshooting.md`, `15-limits.md`, `asset-catalogue.md`,
`formats.md` (§Rig matching, §Voice lines and the GASP tables, alpha note),
`ARCHITECTURE.md` (§The Library, index tables, Studio), `roadmap.md`, `glossary.md`,
`dev/code-tour.md`, `dev/studio.md`, `dev/testing.md` (§Phase 8 results),
`phase8-kickoff.md` (§Status), `docs/README.md`, `README.md`, `CLAUDE.md`.
**Next:** what phase 7 and 8 still owe (kickoffs' §Status); the stretch list in
`roadmap.md` (in-game identify, animations, environments as scenes).

## 2026-10-09 — Phase 8 planned
**Done:** wrote `phase8-kickoff.md` from the user's direction ("only show models with
their texture, bones and all, and export all of this at once; just show audio, etc."),
with categories measured from the index paths, and recorded the user's three decisions:
3D-rendered model thumbnails, exports as one folder per asset, Studio opening on the new
Library tab.

**Docs updated:** `phase8-kickoff.md` (new), `roadmap.md`, `docs/README.md`,
`CLAUDE.md`.

**Next:** phase 8.

## 2026-10-09 — Texturing programs (Substance Painter…) and the game's limits
**Done:** at the user's request, a guide for texturing in Substance Painter and other
programs and exporting back (`14-texturing-tools.md`), a limits page (`15-limits.md`),
and the tool that makes the export step work: `mods/texture_import.py`
(`dr2 mod import-textures`, Studio's *Import textures…*, dropping a folder on a model):
exported pictures are matched to the model's textures by texture set + channel or by
name, resized to the game's size, normal maps' green direction measured and fixed, and
metal/roughness converted to DR2's colour + specular.

**Why:** "how to export from Substance Painter so it works" needs the game's
conventions, which nobody had measured, and an import that applies them; the user also
asked for the engine's limits ("the 65k vertex limit and stuff like that").

**Learned (measured over both games):** DR2 normal maps are OpenGL-style (green up):
an integrability test votes 323 vs 31 (CZ) and 300 vs 56 (CW), matching the earlier
tangent analysis. Colour maps carry alpha only when DXT5 (hair, lashes). Specular maps
are coloured. Indices are always 16-bit: 65,536 vertices per character part (the
importer checks per shape, since the parts of a shape share its buffer). UV set 0 is
always float; character UVs stay in 0-1 except two CW hats. Largest shipped character
18,593 vertices (CZ mechanic boss). Painter's default export names put the mesh name
first; the matcher accepts that.

**Docs updated:** `modding/14-texturing-tools.md`, `15-limits.md` (new),
`context.toml`, `modding/README.md`, `asset-catalogue.md`, `formats.md` (§Texture
conventions, §Engine limits), `glossary.md`, `dev/code-tour.md`, `dev/studio.md`,
`dev/testing.md`, `roadmap.md`, `CLAUDE.md`.

**Next:** follow the Painter guide in Painter itself; masks and the other lighting maps
(what each channel means) are still unknown.

## 2026-10-09 — Phase 7: help inside the app, Play, Share and Install
**Done:** the user's three choices first (Play starts the recomp; mods are shared as
`.dr2mod`; help in English, laid out for translations). Then:
- **Help inside DR2 Studio**: the modding guides *are* the help (`dr2kit/help`; a built
  package carries them through a `setup.py` hook), in a searchable window (F1), a "How
  to mod this" box per asset kind (`docs/modding/context.toml`), a Help button on every
  error that opens the matching troubleshooting row, a Welcome checklist, and
  `dr2 help` in the terminal.
- **The shortest editing loop**: *Edit in image editor…* (each save goes into the mod
  and shows in Studio as the game will get it), *Open in Blender* (the model arrives
  tagged for the add-on), drag and drop, the mod's changes listed with problems marked,
  only the buttons that apply shown, *New mod…* when an action needs one.
- **Share and install**: *Share…* (name, preview, readme, a check per game, one
  `.dr2mod`); *Install mod…* / drop / `dr2 studio file.dr2mod` shows the mod before
  installing; updates list what changed; mod sets.
- **Play** (`mods/play.py`, `dr2 play`): deploy the switched-on mods and start the
  recomp; *Play without mods*; *Remove mods from game*; the status bar says what is in
  the game. New mods live in the library; opened folders are linked.
- Guides 01, 05, 06, 08-11, 13 and the guides index rewritten for these buttons.
- **Gate, scripted in game in both games** (`tools/newcomer_gate.py`): make, share,
  install on an empty second library, Play: the new title text and a red shirt/jacket.

**Why:** the user's phase 7 direction: modding as easy as possible, documentation in
the app, packaging and installing easy.

**Learned:** `closeEvent` isn't called for a window never shown, and waiting on a job's
thread with `wait()` deadlocks (it quits through a queued signal): `wait_for_jobs()`
keeps the event loop turning. The Studio tests linked test mods into the real mod
library once the open mod joined the library: every test now gets its own user folders
(conftest). A one-liner `open(p,'w').write(open(p).read())` empties the file (the write
open truncates first): `app.py` had to be restored from git and re-patched. The CZ
recomp's `build-release` is a month older than `build`, so Play takes the newest
source build. `pkill -f` with a pattern that matches its own command kills the shell.

**Docs updated:** `modding/README.md` (start here), `01-install.md`,
`05-first-mod-texture.md`, `06-mod-packages.md`, `08`-`11`, `13-blender-addon.md`,
`context.toml` (new), `dev/studio.md`, `dev/code-tour.md`, `dev/testing.md`,
`ARCHITECTURE.md`, `roadmap.md`, `phase7-kickoff.md` (decisions), `glossary.md`,
`CLAUDE.md`.

**Next:** a person runs the gate from the in-app help on a clean profile; `.dr2mod`
file associations in releases; the carried-over items (first release on all OSes,
in-game gates owed, value-set colours, longer sounds, keyboard prompts with string mods).

## 2026-10-09 — Phase 7 set by the user; the app icon
**Done:** the user set phase 7's direction: the easiest possible modding, the help inside
DR2 Studio, easy packaging and installing of mods, and an app icon
(`phase7-kickoff.md`, `roadmap.md` rewritten; earlier proposals kept as "carried over").
Made the icon: `dr2kit/studio/icon/dr2studio.svg` (a combination wrench on a blood-red
tile with drips, our own drawing), set as Studio's window icon, rendered for releases by
`tools/release/make_icons.py` (PNG, `.ico`, `.icns`) and used by the executables, the
macOS app and the AppImage. The first wrench was a rough shape the user found weird; the
second is drawn from exact geometry (open jaw, hexagonal ring, tapered handle, shadow)
and checked at 16-256 px.

**Docs updated:** `phase7-kickoff.md`, `roadmap.md`, `dev/packaging.md` (§The icon),
`dev/studio.md`, `dev/code-tour.md`, `CLAUDE.md`.

**Next:** settle phase 7's open questions (starting the recomp from Studio, `.zip` or
`.dr2mod` packages, help language), then the in-app help.

## 2026-10-09 — Clean-up, phase 6 closed, phase 7 proposed
**Done:** deleted 17 finished sessions' scratch folders from `/tmp/claude-1000` (25 GB
→ 4.9 GB used; what is left belongs to running sessions), this phase's test captures,
test mods and the local Linux release build. Marked phase 6 done; wrote a proposed
phase 7 (`phase7-kickoff.md`, `roadmap.md`) from what phases 4-6 left open.

**Why:** the user found `/tmp` (RAM-backed) full and asked for clean-up, and for it to
become a habit: now a rule in `CLAUDE.md` (§Clean up after yourself).

**Docs updated:** `CLAUDE.md`, `roadmap.md`, `phase7-kickoff.md` (new),
`docs/README.md`, `README.md`.

**Next:** the user decides on phase 7; the first step needs the GitHub remote.

## 2026-10-09 — Phase 6, part 2: Blender add-on, release builds, game folders
**Done:** the Blender add-on `blender/io_dr2` (a Blender 4.2+ extension: search the
index, import a model or skeleton in one click into its own collection, **Check rig**
with the report in the Text editor, **Export to mod**), scripted end to end in Blender
5.2 (`tools/blender_addon_gate.py`). Release packaging: `tools/build_release.py`
(PyInstaller bundle with DR2Studio + dr2, add-on zip, toolkit sources for Blender,
licences; tar.zst, zip, AppImage, `.sha256`), `tools/release/build_ffmpeg_lgpl.sh`,
`.github/workflows/release.yml`. DR2 Studio's **Game folders…** window (choose a folder,
unpack the package), opened when no game is found. `dr2kit/userdirs.py` (works without
platformdirs), `dr2 doctor` reports PyAV's ffmpeg and its licence.

**Why:** phase 6 scope: the add-on and installers are what let people mod without a
terminal or a Python setup.

**Learned:** Blender treats add-ons as GPL, so the user chose a GPL add-on that imports
dr2kit from a folder instead of bundling it. PyPI's PyAV links GPL x264/x265 into
libavcodec: releases need an own LGPL ffmpeg (as the CZ recomp found), and PyAV builds
from source against it in under 2 minutes. The licence gate caught PyInstaller
collecting Fedora's GPL codec libraries through the system `libavcodec` (ffmpeg's
libraries have no RUNPATH); fixed with `LD_LIBRARY_PATH`. ffmpeg's configure calls the
Bink video decoder `bink` (the codec is `binkvideo`); buffer filters are always built.
An installed (non-checkout) toolkit doesn't see sibling recomps, hence the Game folders
window. Blender's manifest validator limits `tagline` and permission texts to 64
characters.

**Docs updated:** `modding/01-install.md` and `13-blender-addon.md` (new),
`dev/packaging.md` and `dev/blender-addon.md` (new), `02-game-data.md`,
`07-blender-setup.md`, `12-troubleshooting.md`, `modding/README.md`, `dev/code-tour.md`,
`dev/studio.md`, `dev/setup.md`, `dev/testing.md`, `ARCHITECTURE.md`, `roadmap.md`,
`THIRD_PARTY.md` (add-on GPL, what a release bundles), `glossary.md`, `README.md`,
`docs/README.md`, `CLAUDE.md`.

**Next:** push to a GitHub remote and let the release workflow run on Windows and macOS
(the Windows ffmpeg step is the least certain); try a release build on a real game on
each OS; the items in `phase6-kickoff.md` §Left open.

## 2026-10-09 — Phase 6, part 1: strings, text editing, movies, the mod manager
**Done:** string banks (`formats/bcs.py`: read, write byte-identically, JSON, apply
changes with notes) and `dr2 strings search/show/export/set/unset`; mods change strings
with `replace/…/str_<lang>.bcs.json` (only the listed ids; several mods merge per id).
DR2 Studio got a strings table (edit a cell → the mod), a text editor that saves a text
file into the mod with a coloured diff, a Bink movie player and *Export MP4…*
(`convert/video.py`, `dr2 extract --mp4`). The mod manager (`mods/library.py`, `dr2 mod
list/install/remove/enable/disable/move/conflicts/library/pack`, Studio's **Mod
manager…**) keeps installed mods in a library with a load order. The files the
executables digest-check were read from both XEXs (`tools/xex_digests.py`) into the
profiles; the build refuses them. In game: a changed `IDS_PRESS_START` shows on the
title screen of both recomps.

**Why:** phase 6 scope (roadmap): text and translations are the most asked-for mods after
textures, and several mods at once need an order and a conflict report, not an error.

**Learned:** every bank of a game has the same ids and the same size (zero-padded to the
largest, `str_lg`); `str_id.bcs` is the label bank (`IDS_…`); every string with colour
or icon markup starts with `@`; CZ's last string is the developers' joke-reminder
`IDS_LAST_LETTER_OF_LAST_STRING_IS_ALWAYS_MISSING`. The XEX `Digest` resource is
`count, {name hash, SHA-1(file + be32 length)}`: Case West checks six files, including
`padmap.txt` and `zombie_pdv_variations.txt`. Bink 5.1 is four tracks (FL/FR, C, LFE,
SL/SR). PyAV's wheels carry GPL x264/x265 next to an LGPLv3 ffmpeg (matters for
packaging). Frame dumps of a 3440×1440 window filled the RAM-backed `/tmp`: put them
on disk. The Blender add-on raised a license question; the user chose a GPL add-on that
doesn't bundle dr2kit.

**Docs updated:** `formats.md` (§Strings, §Digest-checked files, §Movies, table, the CW
digest sentence superseded), `modding/11-text.md` (new), `06-mod-packages.md` (mod
manager, string files, pack), `04-extracting.md` (movies), `asset-catalogue.md` (text,
movies), `12-troubleshooting.md`, `modding/README.md`, `glossary.md`,
`dev/code-tour.md`, `dev/studio.md`, `dev/testing.md` (phase 6 results),
`dev/recomp-integration.md` (§Phase 6), `ARCHITECTURE.md`, `roadmap.md`,
`THIRD_PARTY.md` (PyAV licences).

**Next:** the Blender add-on, packaging and CI, `01-install.md`.

## 2026-10-09 — White models: colour textures named `_dm` or `_cm<hex>`, packs on disk
**Done:** the user found Case West's final boss (`boss_commander_epi`) white in DR2
Studio. His colour maps are `_dm` ("diffuse map"); the role rule only knew `_cm`. A
check of every material of both games found two more gaps: environment colour maps with
a hex tag (`glass_cmda77`, 1,000+ slots) and loose models whose `.tex` pack is a
separate file in the same folder. `formats/scene.texture_role` now knows `_dm` and hex
tags, `Material.texture("colour")` falls back to the first plain-named texture (never a
lightmap or reflection map), and `TextureFinder` searches the model's folder on disk.
Left without a colour texture: 25 / 30 materials that really have none (lights, glass).

**Why:** a white model in a preview looks like a broken model.

**Learned:** count over every asset instead of fixing the one reported: the reported
case (`_dm`) was 6 slots; the hex-tag case it led to was over a thousand.

**Docs updated:** `formats.md` (§Materials, role rule), `dev/code-tour.md`,
`modding/12-troubleshooting.md`.

## 2026-10-09 — Zombie clothing colours: value sets and baked colours
**Done:** the user saw zombies with red/green/purple clothes in DR2 Studio (skin was
right). Their `_cm1` texture is a weight map; the colours are pixel-shader constants in
each material's value set (`valuesets.big/<hash>.scv`). Added `formats/shader.py`
(shader constant tables, value sets) and `convert/material.py` (bakes the pattern,
body-part and channel families with the shaders' own formulas, read from the shaders
translated with XenosRecomp); the `.glb` export (CLI, Studio) uses the baked texture.
All 674 / 819 value sets parse; all 297 / 212 affected materials bake; checked visually
on seven models.

**Why:** previews and Blender exports must show what the game shows; the phase 3 export
had used the `_cm1` weight map as the colour.

**Learned:**
- A texture suffix doesn't say it's a colour: `_cm1` on zombie clothing is a weight
  map. Even Chuck's DR2 t-shirt under the jacket (`chest_default_mtl_tshirt`) uses one.
- Value-set records hold the pixel-shader **register**; the shader's D3DX constant table
  names it. The 32-bit "name hash" next to it isn't any hash we know.
- XenosRecomp (sibling repo, built) turns a game `.po` into readable HLSL: the fastest
  way to learn what a material does.
- Cutscene zombies tile their pattern (scale 10 × 20) and some use scale 0 (one flat
  colour): the bake follows the shader's UV transform.

**Docs updated:** `formats.md` (§Materials: value sets, with the correction; status
rows), `dev/gltf-mapping.md`, `dev/code-tour.md`, `glossary.md`,
`modding/12-troubleshooting.md`.

**Next:** compare with an in-game capture; let mods change these colours (value-set
overrides).

## 2026-10-09 — Phase 5: audio (listen, export, replace through the recomps)
**Done:**
- Sound formats (`formats/xma.py`): `.xma` comes in two shapes, RIFF XMA2 files in the
  sound-effect banks and raw packets in the streamed banks; the raw ones are described by
  `data/audio/cache.big`'s `$GIB` stream tables (rate, channels, loop), cracked this
  session. Packet headers, multi-stream (5.1) layout, the FNV-1a packet fingerprint.
- Decoding (`convert/audio.py`) through PyAV (ffmpeg's `xma2`, the recomps' decoder):
  `dr2 extract --wav`, `dr2 info` on sounds, `dr2 census --audio` (every sound of both
  games decodes to its stored length: 8,916 + 11,735).
- `.sfx` and audio scene scripts (`formats/audioscript.py`); the index links sounds to
  the `.sfx` that play them and to scene-script events (`audio`, `sound_ref` tables;
  schema version 2).
- DR2 Studio's audio view (`studio/audio_view.py`): waveform per channel, play, seek,
  loop, *Export WAV…*, *Replace with audio…*.
- Sound mods: `replace/<sound>.xma.wav|ogg|flac|mp3` (`mods/audio.py`) build into
  `dr2kit_audio/` (fitted WAV per stream + a table of every packet's fingerprint and
  output position); **PCM substitution in both recomps** (`runtime/kernel/audio.cpp`,
  `CZ_NO_AUDIO_MODS` / `CW_NO_AUDIO_MODS`, CZ gotcha 635, CW gotcha 331; commits CZ
  `54b5283` on master, CW `dea8734` on xlive-integration).
- In-game gate in both games: the title music replaced by another track, recorded
  through SDL's disk driver, follows the replacement; the off switch plays the original.

**Why:** phase 5 of the roadmap: hear a sound before extracting it, and replace music,
voices and effects, although no XMA encoder can be shipped.

**Learned:**
- **Phase 0's "no RIFF header" was wrong for most sounds**: it held for the streamed
  banks it looked at. 7,647 / 9,190 sounds are complete RIFF files. Retraction in
  `formats.md`.
- The stream tables hash the entry name **with its case**, unlike the `.big` index.
- A decode is always 384 samples shorter than the frames encoded; loop points count
  those samples. With that, every length rule holds over both games (`formats.md`
  §Lengths); a few looping effects carry a tail past the loop end.
- Decoding packet by packet (as the recomps do) gives the same samples as a whole-file
  decode, so a packet's output position is fixed. That replaced the planned design
  (map guest buffers to `.big` entries through VFS read tracking) with one where every
  packet identifies itself: no VFS state, and loops, streaming and reused contexts need
  no special cases.
- **Case Zero digest-checks `data/audio/Prologue.txt`**: an edited copy crashes the game
  (checked in game). The planned "easy path" (script remap, as on PC) is ruled out; the
  guide shows the substitution way to make an event play another track.
- The 5.1 prologue cinematic decodes to 316.45 s, as the CZ recomp measured from its
  packet headers (316.5 s): two independent readings agree.
- Both recomps' playback drifts about 1% slow against the source in the disk recordings,
  modded or not (runtime pacing, not substitution). One CW run ignored SIGTERM at exit
  (substitution off): use `timeout -s KILL`.
- The first schema bump (index version 2) failed on a real index: dropping the old
  tables with foreign keys on gives "no such table: main.source_file". Fixed (keys off
  while dropping) with a test; found when building the index to launch Studio.
- Qt Multimedia aborts at exit if a widget using it outlives the test's QApplication
  ("shared QObject was deleted directly"): delete it first.

**Docs updated:** `formats.md` (§Audio rewritten: shapes, stream tables, lengths,
packet-by-packet decoding, `.sfx`, scene scripts and the digest, substitution, census,
in-game check; status rows), `dev/recomp-integration.md` (§Audio substitution, test
procedure, the remap result), `dev/code-tour.md`, `dev/studio.md`, `dev/testing.md`,
`dev/setup.md`, `ARCHITECTURE.md` (index, Studio, audio pipeline, recomp integration
design change), `roadmap.md`, `modding/10-audio.md` (new), `modding/03`, `04`, `06`, `12`,
`asset-catalogue.md`, `modding/README.md`, `glossary.md`, `THIRD_PARTY.md`,
`prior-art.md`, `phase6-kickoff.md` (new), `docs/README.md`, `README.md`, `CLAUDE.md`;
in the recomps: CZ `docs/gotchas.md` #635 and `docs/instruments.md`, CW
`docs/gotchas.md` #331.

**Next:** phase 6, polish and distribution (`phase6-kickoff.md`). Open from phase 5: a
5.1 cinematic and an fx sound replaced in game, longer replacements, voice-line names
(GASP tables), Case West's digest list.

## 2026-10-09 — Docs: phase 4 sweep
**Done:** pages written before phase 4 stopped calling model import future work:
`modding/04-extracting.md` and `07-blender-setup.md` link the new guides 08 and 09,
`docs/README.md` lists them in the reading path, and `prior-art.md` records which limits
of the old MaxScript and the community import workflow phase 4 now covers.
**Why:** the user asked for memory and documentation to be brought up to date after
phase 4.
**Docs updated:** the four files above, this devlog.
**Next:** phase 5 (`phase5-kickoff.md`).

## 2026-10-08 — Phase 4: model replacement (Blender → game), rig validator, in-game check
**Done:**
- The scene writer (`formats/scene_write.py`): serialisers for every chunk the reader
  interprets (`rewrite_problems`: every scene of both games rewrites identically),
  triangles → strips, and `SceneEditor.replace_mesh`, which writes new geometry for a
  shape by copying a template draw of the same material: own buffers rewritten, combined
  buffers appended to, packets cloned, `RenderStrip`, shape words, bounds,
  `_BOUNDINGBOX_`.
- Exact vertex encoders (`formats/vertex.py`: `encode_element`, `encode_value`).
- `.glb` → model (`convert/model_import.py`): parts by object name, bones by name,
  materials by exported name, skinned back to the rest pose with the file's own
  matrices, 4 influences quantised to 255, palettes split at 61 nodes; unchanged shapes
  kept byte for byte. The same code is the **rig validator**: `dr2 model check`,
  `dr2 model import`, Studio's *Replace with .glb…*, and `.glb` overrides in mods
  (`replace/<model vpath>.glb`).
- Census gates: `dr2 census` checks the rewrite; `--models` the vertex re-encode;
  `--reimport` the `.glb` round trip and a rebuild of every shape.
- In-game gate on Case Zero (`tools/blender_gate_model.py` + `tools/capture_gate.py
  --root`): shirt rebuilt through Blender, arms inflated, the watch replaced by spheres
  on every face and finger bone (split into two draws). The game drew all of it from the
  mod's bytes, with the same bone matrices as Chuck's own head and hands.

**Why:** phase 4 of the roadmap: put edited and new rigged models back into the games,
the part the old community tools never got right (fingers and face).

**Learned:**
- **The games store −1.0 as the lowest signed code** (−512 in 10 bits) on most packed
  fields, so phase 3's clamping decoder had two codes for one value and no exact
  inverse. Decoding without the clamp makes every element of both games re-encode to
  its bytes. Retraction recorded in `formats.md`.
- `RenderStrip` word 5 is the packet's byte offset in the command buffer and word 6 its
  length up to the draw command; 106 packets have no `0x04` end, so word 5, not the
  end marker, says where packets start.
- Every skinned shape of both games has exactly one draw; a split palette (several draws
  in one skinned shape) is new to the games, and the game takes it (in-game gate).
- The skin shader uses tangent w as the bitangent's sign, but the shipped w values don't
  follow the UV handedness, and half are 0. New tangents use a chosen convention, not yet
  checked on a normal map (`formats.md` §Tangent w).
- Blender re-orders vertices and bones and adds float noise (≤ 1 µm here): matching must
  go by names, and an "unchanged" shape can only be detected in our own files.
- Importing Chuck's chest `.glb` into the mechanic "worked" at first (same shape names);
  the validator now warns when a file comes from another model and no longer guesses
  materials by number.
- The user asked about the dark blobs on Chuck's face in the gate capture: they are the
  test mesh (spheres on face bones, using the shirt material), as intended. Gate pictures
  need that said next to them.

**Docs updated:** `formats.md` (§Writing scenes, §Tangent w, snorm retraction,
RenderStrip/shape rows, census, in-game check), `dev/gltf-mapping.md`, `dev/code-tour.md`,
`dev/testing.md`, `dev/studio.md`, `dev/recomp-integration.md`, `modding/08`, `09`, `06`,
`12`, `README`, `glossary.md`, `roadmap.md`, `ARCHITECTURE.md`, `phase4-kickoff.md`
(historical), `phase5-kickoff.md`, `CLAUDE.md`, `README.md`.

**Next:** phase 5, audio (`phase5-kickoff.md`). Open from phase 4: a CW in-game run, a
combined-buffer prop in game, tangents on normal maps, adding shapes/materials/bones,
the Blender add-on.

## 2026-10-08 — Phase 3: models and skeletons → Blender, 3D view, in-game check
**Done:**
- The scene reader (`formats/scene.py`, `formats/vertex.py`): skeleton, materials,
  meshes, draws, vertex declarations, triangle strips, bone palettes, both buffer
  families, vertex animation. Every scene of both games parses; every draw decodes
  (`dr2 census --models`, also run by a slow game-data test).
- `.glb` export (`convert/gltf.py`, `convert/model.py`): armature with the game records in
  `extras`, skinned meshes, materials with their PNG textures; `skeleton_from_glb` reads
  records back. `dr2 extract --glb [--skeleton] [--no-textures]`; `dr2 info` explains a
  model (materials, draws, bones per draw).
- DR2 Studio: a 3D view (three.js 0.186.1 vendored, in `QWebEngineView`, fed over a
  `dr2:` URL scheme), *Export .glb…*, scene details.
- Gates as tools: `tools/blender_skeleton_gate.py`, `tools/capture_gate.py`.

**Why:** phase 3 of the roadmap: get every model and rig into Blender correctly, the
base for putting edited models back (phase 4).

**Learned:**
- **Each model carries its own vertex declarations** (`persistent.big`,
  `<shape> D3DVertexDesc N`, the 360's `D3DVERTEXELEMENT9` as is) next to a recorded
  **command buffer** per shape that says which buffers, ranges and declaration each draw
  uses. The shader banks were not needed (phase 0 thought they were).
- **The bone palette, where the old community tools stopped, is a run of consecutive
  skeleton nodes** (first node, count in `RenderStrip`). Proven in game: in a captured
  frame, Chuck's draws sharing a bone get identical matrices under this mapping and
  never under a shifted one.
- Skinning read from the game's own shader (translated with XenosRecomp): 4 influences,
  weight k with index k, index = 3 × slot, at most 61 bones per draw.
- `Combined Vertices 12` is named by its **stride**, not a counter (retracted in
  formats.md). Indices are strips (the GPU state in the capture agrees: primitive 6).
- The games' axes, units and winding are glTF's own: nothing is converted.
- **Materials are named by id, not position.** The first export gave the mechanic boss
  the wrong textures (his apron wore the shoes'); the user spotted it in the Studio
  screenshot taken to check the 3D view, which had been looked at and judged fine.
  `RenderStrip` word 0 is the material id − 1, and `MatArray` isn't in id order. Chuck's
  parts happen to be, which is why they looked right. The census now checks every draw
  finds its material. Lesson: the numeric gates checked geometry, not material binding;
  look at more than one model.
- Blender keeps bone custom properties through import/export; its float noise grows with
  distance from the origin (1.4e-4 at 400 m), so the snap tolerance is relative.
- Studio's `run_job` delivered results in the worker thread (a phase 2 bug: a lambda
  slot runs where the signal is emitted); harmless for text, fatal for Chromium. Fixed
  with a GUI-thread relay.
- The recomp's widescreen patch is applied after the dumped constants: projection row 1
  × 9W/16H.

**Side effects on the user's machine (reported):** the first capture run's F9 also
triggered the CZ recomp's bug-report capture, which pruned the oldest capture in
`~/.config/XenonLive/captures/` (`20261007-052710-93d0`, over the 256 MB cap). The
capture that run added was removed again; later runs used `CZ_BUG_REPORTS=0` (now in
`dev/recomp-integration.md`). A frame-dump run filled the temporary folder's quota; its
files were deleted. The recomps' code and `game_mods/` were not touched; saves were
copies.

**Docs updated:** `formats.md` (§Scene container rewritten, retractions, status table),
`dev/gltf-mapping.md` (new), `dev/code-tour.md`, `dev/studio.md`, `dev/testing.md`,
`dev/recomp-integration.md`, `modding/04-extracting.md`, `modding/07-blender-setup.md`
(new), `modding/asset-catalogue.md`, `modding/12-troubleshooting.md`, `modding/README.md`,
`glossary.md`, `ARCHITECTURE.md`, `roadmap.md`, `README.md`, `docs/README.md`,
`THIRD_PARTY.md`, `CLAUDE.md`, `phase3-kickoff.md` (historical), `phase4-kickoff.md` (new).

**Next:** phase 4 from `phase4-kickoff.md`: a byte-identical scene writer, then
`.glb` → draws, then the in-game gates.
**Follow-up (same evening):** a sweep for docs still describing phase 3 as future work:
`prior-art.md` (bone palette solved; 360 has both buffer families), `ARCHITECTURE.md`
(Studio's model/skeleton views marked built), `dev/README.md` (index rows for
`studio.md`, `gltf-mapping.md`, `recomp-integration.md`), `dev/setup.md` (every gate
command), `modding/03-browsing.md` (the 3D view), `dev/adding-a-format.md` (lessons
from scenes).

---

## 2026-10-08 — Phase 2: textures, index, DR2 Studio, mods, in-game gate
**Done:**
- `.bct` textures decoded: `formats/bct.py` (header, layout, tiling),
  `convert/dxt.py` (DXT1/DXT5/DXN encode + decode, numpy and pure Python),
  `convert/png.py` (pure-Python PNG), `convert/texture.py` (texture ⇄ image, replace).
- Census of every texture in both games, with a re-encode gate (`dr2 census --textures`).
- The SQLite asset index (`index/`, `dr2 index …`): every asset, texture thumbnails,
  model→texture links.
- DR2 Studio v0 (`studio/`, `dr2 studio`).
- Mod packages (`mods/`, `dr2 mod new|check|build|deploy|undeploy`).
- `dr2 extract --png`, `dr2 info`.
- The `game_mods/` VFS layer in both recomps (CZ `057d45b`, CW `ebf0bb2`), each with an
  off switch, a log line per served file and a gotcha entry.

**Why:** phase 2 of the roadmap: see and replace textures, the first thing modders
want, and prove end to end that a toolkit-built archive loads in the game.

**Learned:**
- **The `.bct` header is not a fetch constant** (retracting the phase 0 plan). It is
  the engine's own description: format code (08 DXT1, 0A DXT5, 1B DXN, 00 A8R8G8B8,
  21 L8), mip count, bits per pixel, a flags byte (0x08 = cube map, verified), a
  version byte (0x23 CZ / 0x24 CW). The layout (4 KB-aligned levels, packed mip tail
  including small bases, six faces per level) was confirmed by where real data sits,
  by mip chains, and by a payload-size model that matches 99.6% of textures (the rest
  are larger, never smaller).
- Every one of 12,237 + 23,139 textures decodes and re-encodes to its exact bytes.
  Keeping reference blocks makes PNG round trips lossless where pixels are unchanged.
- **The game accepts our LZX encoder's output.** Chuck's shirt (CZ,
  `chest_young_chuck.tex/young_cr_shirt_cm`) and jacket (CW, `chest_default.tex/cr_jacket_cm`),
  both inside compressed `.tex` entries of `npcs.big`, turned green in game and are back
  to normal with `CZ_NO_MODS=1` / `CW_NO_MODS=1`. The user pointed out that CZ's default
  outfit is the orange "04" shirt, not the IJIEK jacket (DR2's); the first run had
  recoloured the jacket, which this save doesn't wear. `dr2 index textures-of` on
  `chest_young_chuck.big` then found the right texture at once.
- Headless recomp runs play the save (START,A,A = Continue): use a copy of the save
  folder (`CZ_SAVE_DIR`). The user's save was checked unchanged.
- SQLite without statistics planned the relation join as two nested 125k-row scans
  (10 minutes); a `CROSS JOIN` order plus `ANALYZE` made it 0.4 s.
- Normal maps aren't all DXN (583 DXT1 `_nm` in CZ). `MatTextureInfoArray` is 100-byte
  records, name at +4; its hash at +0x38 is not the engine hash.

**Decisions:** the runtime layer only swaps whole files and is checked first; the
toolkit builds mod files on top of `game_patched` and warns about the toggle layers
(`dev/recomp-integration.md`). Studio lives in `dr2kit/studio/` so `pip install` ships
it. No DDS round trip: reference blocks make PNG lossless enough. No game imagery in the
repository, screenshots included.

**Docs updated:** `formats.md` (§Textures rewritten, with the retraction), `ARCHITECTURE.md`,
`roadmap.md`, `glossary.md`, `dev/code-tour.md`, `dev/testing.md`, `dev/setup.md`,
`dev/adding-a-format.md`, `dev/studio.md` (new), `dev/recomp-integration.md` (new),
`modding/03`, `04`, `05`, `06`, `asset-catalogue.md` (new), `12-troubleshooting.md`,
`modding/README.md`, `README.md`, `docs/README.md`, `CLAUDE.md`, `THIRD_PARTY.md`,
`phase2-kickoff.md` (marked historical), `phase3-kickoff.md` (new); in the recomps:
`docs/gotchas.md` (CZ 634, CW 330), CZ `docs/instruments.md`.

**Next:** phase 3 from `phase3-kickoff.md`: skeletons → `.glb`, then vertex streams
and bone palettes.
**Follow-up (same evening):** a `cz_runtime` the user had left running for ~5 h (started
before this session, so on the pre-`game_mods` binary) was stopped at the user's request
with a normal SIGTERM. Their save was checked unchanged. Both recomps' `game_mods/`
folders were removed after the gate, so the next launch of either recomp runs the new
binary with an empty mods layer: identical to before unless a mod is deployed.

## 2026-10-08 — Phase 1: container, LZX, census, `dr2` CLI
**Done:**
- `dr2kit` package (`pyproject.toml`, `dr2` entry point, `python -m dr2kit`), CI on
  Windows / Linux x64+arm64 / macOS with Python 3.11 and 3.13.
- `.big` reader/writer (`container/big.py`), virtual paths (`container/vpath.py`, with
  `name#N` and `@N`), compressed-entry framing (`container/xcompress.py`).
- LZX: libmspack's `lzxd.c` in a separate `dr2lzx` library loaded by ctypes, a pure-Python
  decoder written from the format description, and the CZ recomp's encoder ported.
- Game profiles (`cz.toml`, `cw.toml`), discovery (env var, user config, sibling recomp),
  STFS package unpacking (`dr2 unpack`).
- `dr2 doctor | games | ls | find | extract | census | unpack`.
- 78 unit tests (synthetic data) + 6 game-data tests; `THIRD_PARTY.md`.

**Why:** everything later (textures, models, audio, mods) reads and writes through the
container. The gate demanded byte-identical round trips over both games before anything
is built on it.

**Learned** (all now in `formats.md`):
- The census counts **7,413 archives in CZ and 8,017 in CW** once nested and
  *compressed* nested archives are opened (the recomp counted the 146 top-level files).
  All round-trip byte-identically; all 10,754 + 21,354 compressed entries decode; two
  independent decoders agree; our encoder re-encodes every one (streams 7% larger than
  the game's).
- Every gap between payloads is zero padding to some power of two. Each entry's
  alignment can therefore be recovered from its offset, so the writer stores no offsets
  at all and still reproduces every archive.
- The index hash is the engine hash of the **lower-cased** name, for every entry.
- New `flags` values: `0x10` (textures in `.tex`), `0x20` (scene chunks), `0x100`
  (nested `.big`), besides `0x4`, `0x80`, `0x800`.
- An empty compressed entry is `00 00 00 00`. CW's `preload4.big` has 27 of them. The
  first CW census flagged them as unparseable, which is how they were found.
- The game's encoder writes **uncompressed LZX blocks** (type 3) for small or
  hard-to-compress chunks, in archives it reads at boot. The recomp had believed the
  game's decoder lacked type 3. Our encoder now uses type 3 too, but only when a chunk
  would otherwise grow.
- **Retracted:** "`.bct` magic `05 01 01 E2`". The 4th byte varies (13 values over
  35,350 textures, all with bit `0x02` set).
- **Retracted:** the duplicate-name example "several `Combined Vertices`". Those are
  numbered. Real duplicates are rare (`zonelist.big` ×7/×19).
- 9 of 11 CZ `.bcf` fonts (6 of 11 in CW) are `.big` archives; the rest use an unknown
  `04 03 02 01` container.
- PyAV 19.0.1 on Linux has `xma1`, `xma2` and the Bink decoders; CI checks the other OSes.
- Unpacking each XBLA package gives files byte-identical to the recomp's data.

**Decisions:** `dr2 extract` decompresses by default (`--raw` keeps the stored stream);
the CLI lives in `dr2kit/cli/` (`ARCHITECTURE.md`).
**Docs updated:** `formats.md`, `ARCHITECTURE.md`, `roadmap.md`, `glossary.md`,
`dev/setup.md`, `dev/code-tour.md`, `dev/testing.md`, `dev/adding-a-format.md`,
`dev/README.md`, `modding/02-game-data.md`, `modding/12-troubleshooting.md`,
`modding/README.md`, `README.md`, `docs/README.md`, `CLAUDE.md`, `THIRD_PARTY.md`,
`native/lzx/README.md`, `phase2-kickoff.md` (new).
**Docs follow-up:** `CLAUDE.md` (CW title ID, package paths, dev environment notes), `phase1-kickoff.md` marked historical.
**Next:** phase 2 from `phase2-kickoff.md`: `.bct` decode, texture census, the index,
Studio v0, texture replacement, the recomps' `game_mods/` layer. The in-game gate there
is also the first proof that the game accepts our LZX streams.

## 2026-10-08 — Phase 1 handoff
**Done:** wrote `phase1-kickoff.md` (order of work, exact files and lines to port, test-data
policy). Checked the licenses of the code we will reuse.
**Learned:** the LZX decoder behind XenonRecomp's `lzxDecompress` is libmspack's `lzxd.c`
(**LGPL-2.1**). It's fine as a separate shared library loaded through ctypes, but a
line-by-line Python translation would also be LGPL. The recomp tools are the user's own
(PolyForm Noncommercial), so they can be re-licensed here.
**Docs updated:** `phase1-kickoff.md`, `CLAUDE.md`, `docs/README.md`, this devlog.
**Next:** phase 1, in a fresh conversation.

## 2026-10-08 — Documentation rules
**Done:** set up the documentation layout: `docs/README.md` (index), `glossary.md`, this
devlog, `modding/` (modder guides), `dev/` (contributor guides), `CONTRIBUTING.md`, and a
"Documentation rules" section in `CLAUDE.md`.
**Why:** the project must be easy to understand both for people who want to mod and
for people who want to work on the code. Documentation is part of "done" for every change.
**Docs updated:** all of the above.
**Next:** phase 1 (archive container + census).

## 2026-10-08 — Decisions: license, platforms, recomp integration
**Done:** added a free non-commercial `LICENSE` (no selling the toolkit, no selling or
paywalling mods). Committed to Windows/Linux/macOS support for PySide6 Studio. Approved a
`game_mods/` VFS layer and PCM audio substitution for both recomps (not implemented yet).
**Why:** user decisions (see `roadmap.md` §Decisions).
**Docs updated:** `LICENSE`, `README.md`, `CLAUDE.md`, `ARCHITECTURE.md` (§Platforms,
§Recomp integration), `roadmap.md`.

## 2026-10-08 — Phase 0: planning
**Done:** surveyed both games' data and the Case Zero recomp's existing tools, and wrote
`CLAUDE.md`, `ARCHITECTURE.md`, `formats.md`, `prior-art.md` and `roadmap.md`.
**Learned:**
- The 52-byte bone record layout, verified on all 3,474 bones in both games.
- Skeleton files share the model layout.
- Models list their textures by name in `MatTextureInfoArray`.
- Audio is raw XMA without a header.
- Case West adds Bink movies.
- The old community tools (Gibbed, mariokart64n's MaxScript, Chrrox) are PC- and 3ds
  Max-only, and stalled on bone palettes and on finger and face weights.

**Docs updated:** all initial docs (commit `0fa498f`).

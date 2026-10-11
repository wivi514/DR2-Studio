# Phase 10 kickoff: Maps (see a whole level, extract it, see your mods in it)

**Direction (user, 2026-10-11):** "Prepare for next phase which will be much bigger it's
a tab to see the maps be able to extract them and all these kind of things and also be
able to see them with our change to texture/model, whatever the player modded so we can
see our change without even launching the game."

So, three goals:

1. **A Maps tab** in DR2 Studio: pick a level (Case Zero's Fortune City street, the
   bowling alley, Case West's labs…) and fly through it in 3D, with its buildings, its
   placed items and doors, and what else the level files hold (spawn points, the in-game
   map's areas, trigger zones).
2. **Extract it**: a zone or a whole level as one `.glb` for Blender, every piece in its
   place, organised by zone; the level's text files and textures alongside.
3. **See your mods without the game**: the same views (Maps, but also the Library and
   the model and texture viewers) drawn **with the switched-on mods applied**, exactly
   as the game would load them, with one switch to compare against the original.

The research (2026-10-11) is below, then the plan. The facts are also in
[`formats.md`](formats.md) §Levels, with how each was found.

## Status (2026-10-11): planned and approved, nothing built

The user approved the plan and every decision below (2026-10-11), stressing: show the
switched-on mods, and make switching to **without mods** easy. Editing levels moves to a
possible **phase 11** (below); phase 10 only shows and extracts.

## Start here (handoff, 2026-10-11)

- Read this file, then `formats.md` §Levels, then `dev/code-tour.md` for
  `convert/model.py`, `convert/gltf.py`, `mods/build.py` and `studio/model_view.py`
  (the three.js viewer the Maps tab builds on).
- **Decisions:** §Decisions, approved by the user on 2026-10-11.
  The user called this phase "much bigger" than phase 9: build it in the steps below,
  each one usable on its own and committed with its docs.
- **How the research was done** (the throwaway scripts were deleted; redo them like this):
  - *Zones and pieces:* `AssetTree.for_game(g).open_archive(level_zone_vpath)` lists a
    zone's entries; a piece is `<zone>/<name>.big/_COMP_<name>.big` and
    `convert.model.read_scene` reads it as it is (the 1,573 pieces of the five main levels
    read, 0 failures, ~5 s in all).
  - *Placements:* `ZONE_ORGANIZATION.big/ModelInstanceArray` is `NumModelInstance`
    records of 208 bytes; decode with `struct.unpack(">36f", rec[64:208])` after the two
    32-byte names (layout in `formats.md` §Levels).
  - *Level text files:* `data/datafile.big/<level>.txt`, `waypoint_<level>.txt`,
    `nm_<level>.txt`, `fe_map_*.csv`; count the object classes with
    `re.findall(r"^(c[A-Z]\w+) ", text, re.M)`.
  - *Item → model:* `items.txt` blocks name the model in `AssetFilename` (or CW's
    `MergedFilename`); the file is `<basename>.big` in `data/streamedassets.big`.
- **Pitfalls met during the research:**
  - `dr2 extract <zone>/ZONE_ORGANIZATION.big` writes the nested archive as one file, not
    its entries: read entries in Python with `tree.resolve(vpath).data()`.
  - `read_scene` on `<piece>.big` fails ("no SceneHeader"): the scene is the inner
    `_COMP_<piece>.big` entry.
  - `model_glb(..., stats=)` takes a `convert.gltf.ExportStats`, not a dict.
  - `read_scene` on `MERGED_COLLISION.big` returns no meshes: the collision geometry is
    not in the form the scene reader knows (❓, stretch).
- **First task (step 1):** `formats/level.py` reading `zonelist.big` and
  `ZONE_ORGANIZATION.big`; assemble CZ `prologue_z05` (the bowling alley) into one `.glb`
  with the existing piece export, open it, and look at whether the pieces meet. That
  settles the placement maths (`world = rotation × (scale × local) + position`) before
  anything else is built on it.
- **Still owed from phase 9 (not part of this phase):** the user started testing the
  Variants panel in Studio on 2026-10-11 and has not reported findings yet; ask. The
  in-game zombie capture also needs a Case Zero save outside the safehouse, the same
  save phase 10's gate needs for recomp frames of the street.

## What the research found

### The levels and their zones (both games)

A level is a folder `data/models/environment/<level>/` with a `zonelist.big` and one
archive per **zone** (`<level>_z00.big` … `_z11.big`). A zone is an area the game streams
in and out as the player moves (the bowling alley is CZ `prologue_z05`).

| Game | Levels (folders) | Zones | Pieces | Placements (all levels) | Triangles |
|---|---|---|---|---|---|
| Case Zero | `prologue` (Fortune City street, 11 zones), `prologue_menu`, `prologue_menu2` (the title screen) | 11 + 5 + 1 | 662 in `prologue` | 922 | 1.26 M (`prologue`) |
| Case West | `living_research`, `storage_pens`, `secure_laboratory`, `safehouse`, `main_menu`, 4 cutscene sets (`cine_*`) | 10 per main level | 911 in the 4 main levels | 972 | 1.21 M / 0.93 M / 0.56 M / 0.06 M |

Plus `skybox.big` and Case Zero's `fortune_exterior_sky` / `_canyon` (the distant
backdrop, outside the zones).

**The Library already lists every piece** (*Models → Environments*, 851 in CZ) and shows
each one alone, at the origin. What is missing is putting them **in their places**.

### What a zone archive holds

| Entry | What it is | Status |
|---|---|---|
| `<piece>.big` (→ `_COMP_<piece>.big`) | One building part, floor, sign, set of lights…: an ordinary scene. Read today, textures included | ✅ |
| `<piece>.tex` / `<piece>_LOD.tex` | Its textures, full size and small (the small set is for when the zone is far away) | ✅ (textures) |
| `ZONE_ORGANIZATION.big/ModelInstanceArray` | **Where each piece goes**: 208-byte records: name, scale, rotation (quaternion), position, bounds, a draw distance | ✅ mostly (layout below) |
| `ZONE_ORGANIZATION.big/_ZONEINFO_` | The zone's bounds (10 floats) | ⚠ |
| `MERGED_COLLISION.big` | The zone's collision (walls the player can't pass): a scene with no drawable meshes; its geometry is in a form we don't read | ❓ |
| `COMMON_TEXTURE.tex` | Empty in every zone checked | — |

`zonelist.big/ZoneList` gives each zone its name, bounds, centre and radius (132-byte
records), so a viewer can load the zones near the camera first.

The placement record, measured on all zones of both games (every record 208 bytes;
`ModelInstanceArray_Dynamic` is empty everywhere):

```
+0    char name[32]          piece name (z05_bowling_struc)
+32   char name2[32]         the same name in every record seen
+64   f32 scale[3]           1,1,1 in every record seen
+76   f32 rotation[4]        quaternion x,y,z,w (z05_glass08: 0,0.7071,0,-0.7071)
+92   f32 position[3]        world position = the piece's bounds centre
+104  f32 bounds_min[3], bounds_max[3], centre[3], radius   (world space)
+144  f32 0, draw_distance (110, 80, 60…), 0, 0, u32 0xFFFFFFFF, 0, f32 lod_distance (5…20)…
+200  u32 index (the piece's number in the zone), 0, 0  [the rest of the tail: unknown]
```

A piece's mesh is stored around its own centre (`z05_bowling_struc`'s bounds are ±18.8 m,
its placement at x −162): **world = rotate(scale × local) + position**. To confirm:
assembled pieces must meet without gaps (step 1's gate).

### What the level text files hold (`data/datafile.big`, plain text)

The rest of a level is plain text, in the engine's `cClass Name { Key = "value" }`
blocks (positions `"x,y,z"`, rotations as quaternions `"x,y,z,w"`):

| File | Holds (counts: CZ `prologue` / CW `living_research`) |
|---|---|
| `<level>.txt` | `cItemPlacement` (886 / 902: every weapon, box, bench… lying in the level), `cDoorPlacement` (38 / 51), `cItemWithAttachedPropsPlacement` (CW 21), `cSpawnPoint` (18 / 9: where Chuck appears), `cZombieWarehouse` (24 / 11: zombie spawn areas, polygons), `cPolygonSmall` (map areas with their names: `PR102` = string 1712), `cPolygonLarge`, `cLightContextVolume` (which lighting applies where) |
| `waypoint_<level>.txt` | `cTriggerVolume` (doors to other levels: `Level = "LEVEL_PROLOGUE_SAFEHOUSE"`), `cEnvironmentVolume` / `cEnvironmentAcoustics` (sound areas), `cWaypoint` |
| `nm_<level>.txt` | The **navigation mesh** (where zombies and survivors can walk): vertices and polygons |
| `fe_map_points*.csv`, `fe_map_*_f1.csv` | The in-game map: each level's map rectangle, named rooms and points (safehouse, workbenches, save points); `frontend/map.tex` holds CW's map pictures (`map_b1`, `map_2f`) |
| `<level>.csv` (CZ `prologue.csv`, CW `epilogue_*.csv`) | Lighting by hour of day (24 columns of spherical-harmonic light) |
| `zombiesets.txt` | Which zombie types a level loads, by time of day |

**Placed items find their model:** `ItemName` names a block in `items.txt`, whose
`AssetFilename` (`data/models/weapons/scissors`) or, in CW, `MergedFilename`
(`data/dynamicprops/gascanister`) names the model; the file is `<basename>.big` in
`data/streamedassets.big`. Case West: all 1,822 placements of its 4 main levels found.
Case Zero: 577 of 1,059 found; 163 name a block with no file (`CardboardBox`) and 319
a path whose file isn't in `streamedassets.big` (`data/models/interactables/beerbottle`): to find in step 2 (other archives, a default model, or simply absent from the
demo).

**These files are not digest-checked** (`formats.md` §Digest-checked files), so moving an
item or a spawn point is moddable later through the existing whole-file overrides.

### What makes a level look like the game (beyond placing pieces)

- **Colour textures** export today. Each level material also names an **AO map**
  (`AO_z05_bowling_struc`: baked shadows, on the second UV set, both sets are in the
  vertex data) and many floors **blend two textures through a mask**
  (`sand_pebbles_brown_cm` + `gravel_dirty_gray_cm` through `page_grass_patch_mask_cm`).
  Without them a level looks flat and repetitive; reading the level pixel shaders
  (memory: "read the shader first", `reference-xenosrecomp-shaders`) gives the exact mix.
- **Lighting by hour** (`prologue.csv`) and the sky: a fixed time of day is enough at first.

### Seeing mods without the game: what exists

`mods/build.py` already turns a mod's overrides into the exact bytes the game will get
(`plan_mods` → `new_bytes` per overridden vpath: a `.png` re-encoded and re-tiled as the
game's texture, a `.glb` rebuilt into the model, strings merged), and `verify` reads
them back. Nothing yet **draws** those bytes: Studio and the exports always read the
game's own files. Because every override is addressed by vpath, a view of the game
**with mods** is one layer between the viewers and `AssetTree`: "is this vpath
overridden? then the built bytes, else the game's".

## Plan

Each step ends usable and committed with its docs.

### 1. Read a level (`dr2kit/formats/level.py`, `dr2kit/convert/level.py`)

- Read `zonelist.big`, `ZONE_ORGANIZATION.big` (`ModelInstanceArray`, `_ZONEINFO_`) and
  list a level's zones, pieces and placements; name every byte not understood (the
  record's tail), CLAUDE.md rule 6.
- `dr2 level list -g cz` (levels and zones), `dr2 level info <level> [zone]`.
- **Census `--levels`**: every zone of both games: every record 208 bytes, every
  placement names a piece in its zone, every piece placed (or named as unplaced),
  rotation quaternions of unit length, world bounds = rotated local bounds + position.
- Gate: pieces assembled from placements meet without gaps (a picture of the bowling
  alley and a CW lab, looked at), and agree with a recomp frame from the same spot.

### 2. Placed things (`dr2kit/formats/levelscript.py`)

- A reader for the `cClass Name { Key = "value" }` text (nested blocks, `//` comments)
  shared by the level, waypoint and items files; it reports unknown classes.
- Resolve items and doors to models (`items.txt`, `streamedassets.big`); find where Case
  Zero's missing 482 live, or list them.
- Markers: spawn points, zombie areas, map areas (with their names from the string
  banks), triggers to other levels, the navigation mesh (as a see-through overlay).

### 3. The Maps tab (Studio)

- A tab after the Library: the levels on the left (by game, then zone), the 3D view in
  the middle, a **Layers** panel on the right: buildings, items & doors, spawn points,
  zombie areas, map areas, triggers, navigation mesh, collision (later), sky.
- **Fly camera** (WASD + mouse, speed on the wheel) as well as the orbit one; *Go to*
  a spawn point or a map area by name; the in-game map picture (CW) as a corner overview.
- Zones load **near the camera first** (`ZoneList` centres and radii), far ones with
  their small `_LOD` textures, so a 1.2 M-triangle level opens fast; each zone is
  converted once and cached on disk (like the model pictures).
- Click a piece or an item: its name, its file, *Show in Library*, *Open in Blender*,
  *Export*. Items use their model's default look (phase 9).
- Level materials: AO maps and two-texture blends (from the level shaders), so it looks
  like the game.

### 4. Extract (`catalog/export.py`, `dr2 export`)

- **Export zone / Export level…**: one `.glb` per zone (a whole level is ~1.2 M
  triangles: fine for Blender, too big for some tools), pieces placed, one mesh per
  piece shared by its placements (glTF instancing), a Blender collection per zone and
  per layer; items as placed models (optional); markers as named empties; the original
  `.txt` / `.csv` files and an `info.txt` next to it.
- `dr2 export <level> [--zone z05] [--items] [--markers] -g cz -o out`; the Library's
  *Environments* group gets *Export as level* too.
- The add-on's import puts each zone in its collection (`blender/io_dr2`).

### 5. See your mods (`dr2kit/mods/preview.py`) — Studio-wide

- `ModdedTree`: wraps `AssetTree`; for every vpath an active mod overrides it returns
  the bytes `mods.build` would write (`new_bytes`), cached by the mod files' dates.
  Everything that reads through a tree (textures, models, the Library pictures, the
  Maps tab, exports) then shows the mods without new code in each viewer.
- **A "With my mods" switch** in Studio's toolbar (on by default once a mod is switched
  on), using the same mods and order as **Play** (the mod library's switched-on mods;
  later, optionally, what is deployed in the recomp's `game_mods/`). Overridden assets
  carry a marker in the Library and the Maps tab ("changed by *My mod*"), and a
  **Compare** toggle flips between original and modded in place.
- Edits refresh live: saving a `.png` or a Blender export into a mod redraws the asset
  wherever it is shown (the mod folder is watched).
- A mod that fails its checks (`dr2 mod check`) is drawn as the original, with the
  error shown, not as a broken model.

### 6. Stretch (if time allows)

- The collision mesh (`MERGED_COLLISION`) as a layer.
- Time of day from the lighting table; the sky and backdrop.
- Zombies standing in their spawn areas (phase 9 looks).

### Not in phase 10: editing levels (a possible phase 11, user 2026-10-11)

The user may add later: modify zombie spawns, move placed objects, add more objects
("phase 11 if we do it"). Phase 10 keeps the way open: zombie spawn areas and
placements are **shown** as layers that can be switched on and off (step 2, step 3),
and the level text reader (step 2) should be able to write a file back byte-identical
when nothing changed, so a phase 11 editor can save changes as a whole-file mod (the
level `.txt` files are not digest-checked).

## Decisions (approved by the user, 2026-10-11)

- **Tab name "Maps"** (the user's word), the second tab after the Library.
- **Load by zone, near the camera first**, with the game's own small textures far away;
  never the whole level at full resolution at once.
- **Mods shown = Play's mods** (the mod library's switched-on mods, in their order), so
  "what I see is what Play deploys". **Switching to "without mods" must be one click**
  (a toolbar switch, also a keyboard shortcut) and works in every view (user, 2026-10-11).
- **Exact bytes, not a shortcut**: a modded texture is shown as the game will get it
  (after DXT compression and tiling), so compression artefacts show up in Studio first.
  Slower on the first view of a big texture; cached after that.
- **Extract per zone by default**, a whole level on request.
- **Editing the level** (zombie spawns, moving or adding objects) is **not** in phase 10:
  a possible phase 11.

## Gate

In both games:

- **Maps:** CZ's `prologue` and CW's `living_research` open in the Maps tab with every
  piece in place (pictures looked at from several spots, compared with recomp frames from
  the same spots), items and doors at their places, spawn points and map areas named.
- **Census `--levels`:** every placement of every zone parsed and matched to its piece,
  every level text file parsed with no unknown class left unnamed, every item resolved
  or listed.
- **Extract:** a zone exported and opened in Blender with the add-on: pieces placed,
  one collection per zone, items and markers where Studio shows them.
- **Mods:** with a texture mod and a model mod switched on, the Library, the model view
  and the Maps tab show the change; the Compare switch shows the original; the bytes
  shown are byte-identical to what `dr2 play --deploy-only` writes (checked by a test);
  then in game, the same spot looks the same (one recomp capture per game).

## Facts to keep in mind

- **Size:** a level is ~200 MB of archives and ~1.2 M triangles; convert per zone, cache
  on disk, and never hold every full-size texture of a level in memory.
- The Library's environment pieces stay as they are (one item per piece); the Maps tab
  is a new view of the same files, not a replacement.
- Case Zero is a demo: some of `items.txt` points at models it does not ship.
- The index is a cache: level data in it bumps `SCHEMA_VERSION`.
- Clean up after yourself (CLAUDE.md); recomp captures go on disk, with a copy of the
  save, `CZ_BUG_REPORTS=0` and `timeout -s KILL` (`dev/recomp-integration.md`). The CZ
  capture save starts in the safehouse bathroom: a capture of the street needs a save
  outside (also owed by phase 9).

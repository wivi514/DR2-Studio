# Phase 9 kickoff: variants (choose what a model wears, see it, export it that way)

**Direction (user, 2026-10-10):** "multiple zombies, items and buildings got variants and
for now a zombie got all his variants of clothing at the same time. Is there a way to
change that so we apply what we want on it and export it how we want, or can export with
all, and can show in viewer with some things or just with all. Whatever is best. Prepare a
phase for this and do your research first."

The research (2026-10-10) is below, then the plan. The facts are also in
[`formats.md`](formats.md) §Variants, with how each was found.

## Status (2026-10-10): done, except the in-game check

Built the same day (guide [`modding/17-variants.md`](modding/17-variants.md); results in
[`dev/testing.md`](dev/testing.md) §Phase 9 results; facts in `formats.md` §Variants):

- **Step 1** `dr2kit/convert/variants.py`: the game's table as profile data (`[variants]`,
  copied and checked by `tools/variant_table.py`), the game's prefix matcher, slots,
  on/off parts, prop states, looks as text, the hide mask both ways, colour choices by
  the name rule (it reproduces CZ's list exactly). `dr2 census --variants`: 0 problems in
  both games.
- **Step 2** Studio: the Variants panel (slots, on/off parts, prop states, colours with
  swatches, Detail, Default / Random / Show everything); parts hide at once, colours
  re-bake keeping the camera; Library pictures show the default look; one Library item
  per zombie with its detail levels inside (`library_item.detail_of`, schema 5).
- **Step 3** exports: *as shown* (Export .glb, `--variants shown`) and *everything,
  organised* (Export all, Open in Blender, groups: group collections, hidden parts,
  `KHR_materials_variants`), `textures/colours/`, variants in `info.txt`; `dr2 variants`,
  `--variant`, `--variants`.
- **Step 4** mods: organised and one-look exports import back byte-identical; the add-on
  exports the visible parts and keeps the hidden ones; `dr2 model check` notes a one-look
  file and warns on replaced misplaced-digit parts.

**Corrections found while building:** the table records are `{u64 mask, pattern}` from
CZ `0x829DF718`: the "halved bits" and the unreadable tall-boots mask were an 8-byte
misreading (`formats.md`, retraction); the prop-state counts in the research matched
`window`/`wings` (only the two slot machines keep states as shapes).

**Changed from the plan:** the default look is "the first of each slot", not "the game's
default" (unknown); look-alike files (`chair_1…9`) are **not** folded into one Library
item (they are different objects with their own pictures; folding would hide them); the
"new shirt as `chest_shirt5`" guide is not written, because the importer still only
replaces existing shapes (17-variants.md says so); a "new shape matches no group"
warning is moot for the same reason.

**Owed:**
- **Step 0 / the in-game gate:** a captured frame whose zombies each draw one choice
  per slot. The capture save starts in the safehouse bathroom (no zombies; tried
  2026-10-10); needs a save outside, or the user playing with a capture key.
- How the game picks a look (the writer of the spawn record's mask, `formats.md` ❓), so
  **Default** and **Random** can follow it; whether CW uses its colour choices; whether
  CZ varies `_3`'s colours (its list has no `_3` sections).
- Stretch goals not started: colour-choice mods; Chuck's outfits from `outfits.csv`
  (step 5, a phase 10 candidate).
- The CW recomp has no misplaced-digit fix for `zombie_security_2`/`_3` (a finding for
  the CW recomp, not this repo).

## Start here (handoff, 2026-10-10)

Status (at handoff): **planned, nothing built.** Built since: §Status above.

- Read this file, then `formats.md` §Variants (the table, the hide mask, colour choices,
  the misplaced-digit meshes), then `dev/code-tour.md` for `convert/gltf.py`,
  `convert/model.py`, `convert/material.py`, `catalog/` and `studio/model_view.py`.
- **Decisions made:** the defaults under §Proposed decisions (user: "whatever is best",
  not objected to); buildings are not a goal (user unsure they have variants; the census
  only reports them).
- **How the research was done** (the throwaway scripts were deleted; redo them like this):
  - *Shape names of every model:* the index's `scene` table lists the model vpaths
    (`meshes > 0`); `Scene.parse(tree.resolve(vp).data(), vp).meshes` gives each shape's
    `name` (both games, ~10 s).
  - *Value sets and their `.pdv` names:* walk every `.big` (nested too) for `.scv`
    entries; the name is `u32 n` then `n` bytes at the start (`formats.md` §Materials:
    value sets).
  - *The executable's table:* the recomps' `assets/game/default_image.bin` is the image
    mapped at `0x82000000` (file offset = address − `0x82000000`). Find the string
    `head1_*,chestupper_neck1*`, then its address as a big-endian u32: the 16-byte records
    `{pattern, 0, mask hi, mask lo}` sit around it (CZ `0x829DF720…`, CW pointer at file
    offset `0x9F26D8`). The game's per-mesh bits are the masks shifted right by one.
  - *Game code:* the recomps' `ppc/ppc_recomp.*.cpp` keep the PowerPC instructions as
    comments (`// lis r11,-32248` + `// addi r3,r11,28364`); addresses are split that way.
    The CZ recomp's `runtime/cpu/zombie_variant_names.cpp` documents the classifier and
    the hide mask.
- The recomps are read-only references for this phase (CLAUDE.md). The CW
  `zombie_security_2` misplaced-digit meshes are a finding for the CW recomp, not ours to
  fix; tell the user if it matters.

## What the research found

Today the toolkit draws **every shape of a model at once**. For a zombie that means
every head, every shirt, every pair of trousers, the burnt version, and the wound caps
the game only shows when a limb comes off, all on top of each other. The game never
does that. Five separate things are called "variants" in this data:

| Kind | Where | Example | How the game picks |
|---|---|---|---|
| **1. Clothing / body choices inside one model** | Shape names, plus a table in the game's code | `zombie_skinny_2`: `head1…4`, `shirt1…4`, `pants1…3`, `headwear2/3`, a burnt `_black` set | A 64-bit mask per zombie: one bit per group (below) |
| **2. Colour choices for a material** | `zombie_pdv_variations.txt` + value sets (`.scv`) in the shader bank | `zombie_skinny_mtl_jersey.pdv` → `jersey1…5.pdv` | One alternative value set per material |
| **3. Detail levels** (LOD) | Separate models `_2` (high), `_3` (medium), `_4` (low) | `zombie_cop_2/3/4.big` (214 / 102 / 19 KB) | By distance. **The Library wrongly calls them "variant 2/3/4"** |
| **4. States of a prop** | Shape names inside one model, or separate files | slot machine: `slot_logo` / `slot_logo_dmg`, `slot_screen_staticWin/Off`, `LOD_slot_machine`; `cashregister_dmg.big`, `military_hummwv_stage2/3.big` | By game events (damaged, won, off) |
| **5. Look-alike models** | Separate files with a number | `chair_1…9`, `pottedplant_1…7`, `garbagecan_1…4` | Placed by the level files |

Chuck's clothes are a sixth, already-understood system: `outfits.csv` lists which part
model goes in each slot for each outfit (`OUTFIT_BOWLING_SHIRT_JEANS` → chest
`Bowling_Shirt_Jeans`…), and `clothingdatabase.csv` says which body slots a part covers.

### 1. The shape-group table (in the game's code, both games)

The executable holds a table of **shape-name patterns, each with one bit of a 64-bit
mask** (CZ `0x829DF720`, CW at the same layout; read from the recomps'
`assets/game/default_image.bin`). Shapes whose name matches a pattern belong to that
group. The groups:

| Bits | Group | Patterns (abridged) |
|---|---|---|
| `0x2`…`0x100` | **Body regions** (for cutting limbs off) | `head*`, `chest*`, `pants_*`, `larm_*`, `rarm_*`, `lleg_*`, `rleg_*` (each with its `cap_…` wound caps) |
| `0x4` | All wound caps | `cap_*` |
| `0x200`…`0x1000` | Accessories | `headwear*`, `eyewear_acc*`, `chest_acc*`, `chest_acc_bkpc` |
| `0x4000` | Bare arms | `larm_arm*,rarm_arm*` |
| `0x8000` | Gas look (CW) | `head_gas*`, `chestupper_gas*`… |
| `0x10000` | Burnt look | `head_black*`, `pants_black*`… |
| `0x20000`…`0x200000` | **Head 1-5** | `head1_*,chestupper_neck1*,cap_neckchest1,cap_chestneck1` |
| `0x400000`…`0x2000000` | Head tumours 1-4 (CW gas zombie) | `head1_head_tumour1*`… |
| `0x4000000`…`0x40000000` | **Headwear 1-5** | `headwear1*,geo_head1*` |
| `0x80000000`…`0x1000000000` | **Shirt 1-6** | `chest_shirt1*,rarm_shirt1*,larm_shirt1*,chest_tshirt1*,…,cap_chestrarm1…` |
| `0x2000000000` | Shirt tumours | `chest_shirt1_tumour1*`… |
| `0x4000000000`…`0x100000000000` | **Trousers 1-7** | `pants_pants1*,rleg_pants1*,lleg_pants1*,…` |
| `0x200000000000` | Skirt | `skirt_skirt1*`… |
| `0x400000000000`…`0x10000000000000` | **Feet 1-7** | `lleg_lfoot1*,rleg_rfoot1*` |
| ? | Tall boots | `lleg_tallboot1*,rleg_tallboot1*` (its mask word didn't read cleanly ❓) |

Shapes in no numbered group (`head_eyes`, `head_mouth`, `rarm_arm`) are always drawn.
The groups and the shape names agree on every zombie of both games: `zombie_cop_2` has
heads 1-3, `zombie_skinny_2` heads 1-4, shirts 1-4, trousers 1-3 and the burnt set;
CW's `zombie_fat_female_2` names its pieces `shirt5_loose`, `pants4_pantskhakis`…

**How the game uses it (measured in the CZ recomp; `formats.md` §Variants):** each mesh
gets bits from its name when the model loads (the table values shifted right by one);
**each zombie carries a 64-bit hide mask**, and a mesh is skipped when its bits and the
mask share a bit. The mask comes from the spawn record (`spawn+0x30`). Detail levels
`_2` and `_3` honour it; `_4` (one baked texture) only roughly follows. A misplaced digit
in a mesh name (`headwearShape2Deformed`) loses the variant bit: CZ `zombie_soldier_3`
(fixed in the CZ recomp) and CW `zombie_security_2` (not fixed there).

**Not known yet:** what writes `spawn+0x30` (probably rolled per slot from the
zombie-spawn seed), and how a colour set is chosen per zombie.

### 2. Colour variants

- **CZ:** `data/datafile.big/zombie_pdv_variations.txt` lists 8 models, 36 materials and
  **129 colour choices**, for example
  `zombie_skinny_mtl_jersey.pdv=zombie_skinny_mtl_jersey1.pdv,…jersey5.pdv`.
  The material's own value set carries the base name inside it; the choices are value
  sets in `shaders/deadrisingprologue-sc.big` (149 `.scv` there, the same 149 in
  `preload4.big`), found by the name each carries. **All 129 are found.**
- **CW:** the list file is **empty** (0 bytes), yet `shaders/deadrisingepilogue-sc.big`
  carries 265 value sets, 490 zombie-named in all, including DR2 types (`zombie_showgirl_mtl_caps1…4`).
  The executable still names the list (`data/datafile/tofix/zombie_pdv_variations.txt`)
  and has `shaderconstantvariationmap.cpp`. The names follow a rule that reproduces CZ's
  list (`<base>.pdv` → `<base>1.pdv…`, `<base>_var1.pdv…`), so CW probably picks by
  name, or not at all. **To check in game.**
- A colour choice only changes shader constants, so it re-uses the bakes we already do
  (`convert/material.py`): no new shading code.

### 3-5. Detail levels, prop states, look-alikes

- Detail levels are whole files. The Library should show **one zombie with a Detail
  choice** (high / medium / low), not three "variants".
- Props: across both games, 70 models have on/off/win/open-style shape names, 11 have
  damaged/broken shapes, 9 have `LOD_` shapes. They need a small rule list by name
  (`_dmg`, `LOD_`, `Off`/`Win`), shown off by default, each a switch.
- Look-alikes and damaged copies in separate files (`chair_1…9`, `cashregister_dmg`)
  can be **grouped in the Library as one item with choices**.
- Buildings (`models/environment`): pieces are separate files per zone; 65 have `lod` in
  their names (lower-detail copies of other pieces), and a few have `_black` (burnt)
  shapes. The user isn't sure buildings have variants (2026-10-10), so buildings are
  **not a goal of this phase**. The census in step 1 covers every model anyway, and
  reports environment pieces with variant-like shapes (overlapping alternatives, burnt or
  damaged copies). Anything real it finds becomes a follow-up, not part of the gate.

### Formats and tools

- **glTF colour variants:** `KHR_materials_variants` is the standard. Blender reads it
  (since 3.3; checked in Blender 5.2's `io_scene_gltf2`: `imp/material.py`,
  `imp/mesh.py`) and shows a **glTF Variants** tab to switch.
- **glTF hidden parts:** `KHR_node_visibility` exists, but Blender 5.2 doesn't read it
  (checked: no mention in its glTF add-on). Instead each shape node gets
  `extras` (`{"dr2_group": "Head 2", "dr2_shown": false}`); Blender keeps extras as
  custom properties, and our **Open in Blender** script and the `io_dr2` add-on put the
  parts in collections (*Head 1, Head 2…*) with the unchosen ones hidden. Other
  programs (Painter) get the "as shown" export, which has only the chosen parts.
- **three.js** (Studio's 3D view) has no built-in variant switch; the page toggles
  `visible` per node by group (instant) and asks Python for a re-baked `.glb` when a
  colour choice changes.

## Plan

### 0. Before building: confirm in game (both games)

- Already measured in the CZ recomp: names → bits, the per-zombie hide mask, where it is
  read. Still to find: the code that writes `spawn+0x30` (how each slot's number is
  rolled), and how a colour set is picked.
- Capture a frame with several zombies in the CZ and CW recomps (`tools/capture_gate.py`
  procedure, `dev/recomp-integration.md`): each zombie's drawn shapes must be one
  choice per slot, no caps, and its clothing constants must equal one listed colour
  choice. In CW, this tells whether colour choices are used at all.
- Note which prop states a placed prop shows (slot machine, cash register).

### 1. The variant model (`dr2kit/convert/variants.py`, profile data)

- The group table as **data in the game profiles** (`cz.toml`, `cw.toml`): patterns,
  slots and bits, as read from the executable. The toolkit never needs the executable.
- `variants(scene)` → the slots a model really has (`Head: 1 2 3`, `Shirt: 1 2`,
  `Burnt: off/on`), each shape's group, the always-drawn shapes, the caps; and the
  colour choices per material (CZ from the list, CW by the name rule if step 0 says so).
- The classifier works like the game's: same patterns, same bits, so a choice converts to
  **the game's hide mask** and back (shown in Studio and `info.txt`; useful to compare
  with the recomp). Misplaced digits (`<part>Shape<N>Deformed`) are read as the artist
  meant, the way the CZ recomp's fix does, and reported by the census.
- A **choice** is plain text: `head=2 shirt=1 pants=3 headwear=none colour.jersey=4`.
  The **default** is what the game would show (the first of each slot until step 0 says
  otherwise, no caps, not burnt), never "everything".
- Prop states by name rules (`groups.toml`-style rules file), off by default.
- A census: every shape of every model in both games is in a group, always drawn, or a
  cap; every listed colour choice is found; detail levels agree on their slots.

### 2. Studio: see it

- A **Variants** panel beside the 3D view for any model with choices: one drop-down per
  slot, colour choices per material with a swatch, **Random** (like the game), **Game
  default**, and **Show everything** (today's view, for looking at all the parts).
- The 3D view hides and shows parts instantly; colour changes re-bake in the background.
- Library pictures use the game default (fixes "all clothes at once" in the grid).
- The Library shows a zombie **once**, with a **Detail** choice (high/medium/low) instead
  of three "variant" items; look-alike files (`chair_1…9`) as one item with choices.

### 3. Export it how you want

- **As shown**: only the chosen parts and colours. For Substance Painter, a quick look,
  or a mod based on one look.
- **Everything, organized** (default for *Export all* and groups): every part, grouped
  and named, the unchosen ones marked hidden; colour choices as
  `KHR_materials_variants`. In Blender (Open in Blender or the add-on), parts land in
  collections per slot with the chosen ones visible, and the glTF Variants tab switches
  colours.
- `textures/` also gets each colour choice's baked colour map
  (`zombie_skinny_mtl_jersey_3.png`), and `info.txt` lists the slots and the choice used.
- CLI: `dr2 variants <model>` lists slots and colour choices; `dr2 extract --glb` and
  `dr2 export` take `--variant head=2,shirt=1` and `--variants shown|all`.

### 4. Put it back (mods)

- Re-importing an "Everything, organized" `.glb` keeps every shape by name, so the game's
  groups still work (a check in `dr2 model check`: a new shape whose name matches no
  group is always drawn; warn when that's probably not meant).
- A guide: adding a new shirt as `chest_shirt5`, and what the game will do with it
  (after step 0 says how numbers are picked).
- `dr2 model check` warns about a mesh name the game would classify without its variant
  bit (the misplaced-digit case).
- **Colour choice mods** (change `jersey3`'s colours) are a small step from here, since
  value sets are read already: a stretch goal, decided after step 0.

### 5. Chuck's outfits (if time allows, or phase 10)

- An **Outfits** group in the Library from `outfits.csv`: Chuck wearing a whole outfit
  (its part models assembled on one rig), exported as one `.glb` or part by part.

## Proposed decisions (the user said "whatever is best"; change any)

- **Default view and pictures: the game's default look**, one choice per slot, no
  caps, not burnt. "Show everything" stays one click away.
- **Default export from the viewer: as shown. Default for Export all and groups:
  everything, organized** (nothing lost, nothing on top of each other in Blender).
- **Detail levels shown as one item** with a Detail choice, high by default.
- The group table lives in the profiles as data, copied from the executable once, with
  the address it came from.

## Gate

In both games:

- From the Library: choose a zombie's head, shirt, trousers and a colour; the 3D view
  and the picture show only those; **Export (as shown)** opens in Blender with only those
  parts and colours; **Export all (everything, organized)** opens in Blender with every
  part in its slot collection, only the chosen ones visible, and the glTF Variants tab
  switching colours.
- Census: every shape of every model is grouped, always drawn or a cap; every colour
  choice is found.
- In game: a captured frame's zombies each draw one choice per slot, matching the model
  (step 0).

## Facts to keep in mind

- Shape names are cut to 31 characters (`cap_black_chestneckShapeDeforme`) and some end
  in `ShapeDeformed`; the patterns are prefix wildcards, so they still match.
- The index is a cache: new variant data bumps `SCHEMA_VERSION`; the pictures redraw
  (`THUMB_VERSION`).
- The executable's table is a fact to copy (names and bits), not code to ship.
- Clean up after yourself (CLAUDE.md); recomp captures go on disk, with a copy of the
  save and `CZ_BUG_REPORTS=0` (`dev/recomp-integration.md`).

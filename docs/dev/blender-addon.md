# The Blender add-on (`blender/io_dr2`): how it is built

A Blender 4.2+ **extension** (`blender_manifest.toml`, not the old `bl_info`) that puts
the toolkit's model workflow in a sidebar tab. Modder guide:
[`../modding/13-blender-addon.md`](../modding/13-blender-addon.md).

## Licence: why the add-on doesn't contain dr2kit

Blender's position is that Python add-ons using `bpy` are GPL works. The toolkit's
licence (`LICENSE`, free and non-commercial) is not GPL-compatible. Decision (user,
2026-10-09):

- everything under `blender/io_dr2/` is **GPL-3.0-or-later** (its own `LICENSE`, an
  SPDX header in each file, `license = ["SPDX:GPL-3.0-or-later"]` in the manifest;
  `tests/test_blender_addon.py` checks all three);
- the add-on **does not bundle dr2kit**. `toolkit.load()` imports it at run time:
  `import dr2kit` as is (installed in Blender's Python), else from the folder set in the
  add-on's preferences (the folder containing `dr2kit/`, or its `python/` or `src/`
  subfolder). A release puts the toolkit's sources in a `python/` folder for this
  (`dev/packaging.md`).

Keep it that way: no dr2kit code copied into `blender/io_dr2/`, no add-on code in
`dr2kit/`.

## Files

```
blender/io_dr2/
  blender_manifest.toml   extension manifest (id io_dr2, Blender >= 4.2, GPL, files permission)
  LICENSE                 GPL-3.0 text
  __init__.py             bpy: preferences, scene settings, operators, the DR2 panel
  toolkit.py              find and import dr2kit (no bpy: testable outside Blender)
  core.py                 what the buttons do: search, export, check, write to mod (no bpy)
```

- `__init__.py`: `DR2Preferences` (**Toolkit folder**), `DR2Settings` on
  `Scene.dr2` (game, query, kind, results, textures, skeleton only, mod folder, last
  check), operators `dr2.search`, `dr2.import_asset`, `dr2.check_rig`,
  `dr2.export_to_mod`, the list `DR2_UL_results` and the panel `DR2_PT_main`
  (View3D sidebar, tab **DR2**).
- **Import** makes a collection named after the asset with custom properties
  `dr2_game` / `dr2_vpath`, makes it the active collection, then runs
  `bpy.ops.import_scene.gltf` on the bytes from `core.export_glb`
  (`dr2kit.convert.model.export_glb`, like `dr2 extract --glb`). Phase 9:
  `organise_variants(coll)` then moves each part with a `dr2_group` custom property
  into a child collection of that name and hides the ones whose `dr2_shown` is false
  (DR2 Studio's *Open in Blender* script does the same), so a zombie arrives in its
  default look with every other part one eye-click away.
- **Check rig** finds that collection from the active object (or its parent; or, for a
  part in a variant group's collection, the model collection holding it), selects
  its visible objects, runs `bpy.ops.export_scene.gltf(export_format="GLB",
  use_selection=True, export_extras=True)` (custom properties carry the bones' game
  records, `gltf-mapping.md`), and `core.check` runs
  `dr2kit.convert.model_import.plan_import` against the game's model. The report
  (`format_plan`) goes to the Text datablock `DR2 rig check`.
- **Export to mod** = check, then `core.write_to_mod`: `replace/<vpath>.glb` in the mod
  folder (a new mod via `dr2kit.mods.manifest.create`, `games` set to that game, when
  the folder has no `mod.toml`).

- **Import zone** (phase 10, `dr2.import_level`; settings `level`, `zone` (enums filled
  from `core.levels`, cached per game; the callback loads the toolkit first), `level_items`,
  `level_markers`, `level_lightmaps`): `core.export_level_zone` builds the zone with
  `dr2kit.catalog.level_export.level_glb`, the glTF importer brings it into a collection
  `<level> <zone>` (custom properties `dr2_game`, `dr2_level`, `dr2_zone`), then
  `organise_level` makes one collection per node with a `dr2_layer` property (zone →
  Buildings / Items and doors / Markers → a kind), nested the same way, and moves each
  object into the collection of its nearest such node (parenting kept); the navigation
  mesh starts hidden. `wire_lightmaps` finds, per material, the image on the glTF
  output group's *Occlusion* socket (the lightmap, on its own UV map), reads it as sRGB
  and puts a *Mix (Multiply)* between the base colour and the BSDF.

## Testing

- `tests/test_blender_addon.py`: `toolkit` and `core` loaded from their files (no bpy),
  the whole flow on a synthetic game and index, the licence markers.
- `tools/blender_addon_gate.py`: the flow inside Blender, headless, with a throwaway
  `BLENDER_USER_RESOURCES` so a developer's Blender setup isn't touched: install the
  built zip, enable it, set the toolkit folder, search Case Zero's
  `chest_young_chuck`, import, check (unchanged: OK), push both arms out 2 cm, check
  (OK, every shape rebuilt), export to a mod; then `dr2 mod check` accepts the mod.
  Result 2026-10-09 (Blender 5.2.1): passes in about 6 s. Phase 10 adds **Import zone**
  of Case Zero's `prologue_z05` (19 pieces where the game puts them, 113 items, markers
  by kind, lightmaps wired: 66 materials); the whole gate takes about 30 s.
- `blender --command extension validate blender/io_dr2` checks the manifest (it caught
  a tagline over 64 characters).

## Not done yet

Deploying from Blender (it writes the mod; deploy is Studio's or the CLI's), building
the index from Blender (it takes minutes and would block the UI), and showing the rig
check's problems on the bones in the viewport.

"""Phase 6 gate for the Blender add-on (``blender/io_dr2``): its whole flow, scripted.

Run inside Blender, with a throwaway Blender user folder so nothing touches your own
Blender setup (the add-on is installed into it)::

    blender --command extension build --source-dir blender/io_dr2 --output-dir build/addon
    BLENDER_USER_RESOURCES=/tmp/dr2-blender-user blender -b --factory-startup \\
        --python tools/blender_addon_gate.py -- build/addon/io_dr2-0.1.0.zip . out_mod

It installs and enables the add-on, points its preferences at the toolkit folder, then
presses its buttons as a user would: search the index for Case Zero's
``chest_young_chuck`` model, **Import** it, **Check rig** (an unchanged import must pass),
push both arms out 2 cm, **Check rig** again (must still pass: the shapes are rebuilt),
and **Export to mod** into ``out_mod``. Phase 9 adds a zombie with variants
(``zombie_skinny_2``): **Import** must sort its parts into group collections with the
parts of other looks hidden; after a visible shirt is pushed out 2 cm, **Check rig** must
pass (the hidden parts are left as they are) and **Export to mod** must write it. Each step prints a ``DR2GATE`` line; the script
exits non-zero on the first failure. Afterwards ``dr2 mod check out_mod -g cz`` must
accept the mod (docs/dev/testing.md §Phase 6 results).
"""
import sys

import bpy

VPATH = "data/models/npcs.big/chest_young_chuck.big"


def fail(msg):
    print("DR2GATE FAIL", msg, flush=True)
    sys.exit(1)


def main():
    zip_path, toolkit, mod = sys.argv[sys.argv.index("--") + 1:][:3]
    bpy.ops.extensions.package_install_files(filepath=zip_path, repo="user_default",
                                             enable_on_install=True)
    pkg = next((k for k in bpy.context.preferences.addons.keys() if k.endswith("io_dr2")), None)
    if pkg is None:
        fail("add-on not enabled after install")
    bpy.context.preferences.addons[pkg].preferences.toolkit_path = toolkit
    print("DR2GATE installed", pkg, flush=True)

    s = bpy.context.scene.dr2
    s.game, s.query, s.kind = "cz", "chest_young_chuck", "model"
    if bpy.ops.dr2.search() != {"FINISHED"}:
        fail("search")
    idx = next((i for i, r in enumerate(s.results) if r.vpath == VPATH), None)
    if idx is None:
        fail(f"{VPATH} not among {[r.vpath for r in s.results]}")
    s.index = idx
    print("DR2GATE search", len(s.results), "result(s)", flush=True)

    if bpy.ops.dr2.import_asset() != {"FINISHED"}:
        fail("import")
    coll = next(c for c in bpy.data.collections if c.get("dr2_vpath") == VPATH)
    arm = next(o for o in coll.objects if o.type == "ARMATURE")
    meshes = [o for o in coll.all_objects if o.type == "MESH"]
    print("DR2GATE import", coll.name, len(arm.data.bones), "bones", len(meshes), "meshes",
          flush=True)
    bpy.context.view_layer.objects.active = arm

    if bpy.ops.dr2.check_rig() != {"FINISHED"} or not s.last.startswith("OK"):
        fail(f"check of the unchanged import: {s.last}\n"
             + bpy.data.texts["DR2 rig check"].as_string())
    print("DR2GATE check unchanged", s.last, flush=True)

    for name in ("geo_larmShape", "geo_rarmShape"):
        me = bpy.data.objects[name].data
        for v in me.vertices:
            v.co += v.normal * 0.02
    bpy.context.view_layer.objects.active = bpy.data.objects["geo_larmShape"]
    if bpy.ops.dr2.check_rig() != {"FINISHED"} or not s.last.startswith("OK"):
        fail(f"check after the edit: {s.last}\n" + bpy.data.texts["DR2 rig check"].as_string())
    report = bpy.data.texts["DR2 rig check"].as_string()
    print("DR2GATE check edited", s.last, flush=True)
    print(report, flush=True)

    s.mod_folder = mod
    if bpy.ops.dr2.export_to_mod() != {"FINISHED"}:
        fail("export to mod")
    print("DR2GATE exported to", mod, flush=True)
    zombie(s)


ZOMBIE = "data/models/zombies.big/zombie_skinny.big/zombie_skinny_2.big"


def zombie(s):
    """Phase 9: a model with variants imports organised; a part of the look exports."""
    s.query = "zombie_skinny_2"
    if bpy.ops.dr2.search() != {"FINISHED"}:
        fail("zombie search")
    s.index = next((i for i, r in enumerate(s.results) if r.vpath == ZOMBIE), -1)
    if s.index < 0 or bpy.ops.dr2.import_asset() != {"FINISHED"}:
        fail("zombie import")
    coll = next(c for c in bpy.data.collections if c.get("dr2_vpath") == ZOMBIE)
    groups = {c.name for c in coll.children}
    hidden = [o.name for o in coll.all_objects if o.type == "MESH" and not o.visible_get()]
    if not {"Head 1", "Head 2", "Shirt 1", "Wound caps", "Always shown"} <= groups or not hidden:
        fail(f"zombie groups {sorted(groups)}, {len(hidden)} hidden")
    print("DR2GATE zombie import", len(groups), "group collections,", len(hidden),
          "parts hidden", flush=True)
    shirt = next(o for o in coll.all_objects if o.name.startswith("chest_shirt1Shape"))
    if not shirt.visible_get():
        fail("shirt 1 (the default look) is hidden")
    for v in shirt.data.vertices:
        v.co += v.normal * 0.02
    bpy.context.view_layer.objects.active = shirt     # in a group collection: still found
    if bpy.ops.dr2.check_rig() != {"FINISHED"} or not s.last.startswith("OK"):
        fail(f"zombie check: {s.last}\n" + bpy.data.texts["DR2 rig check"].as_string())
    report = bpy.data.texts["DR2 rig check"].as_string()
    if "replace chest_shirt1Shape" not in report or "kept as they are" not in report:
        fail("zombie report:\n" + report)
    print("DR2GATE zombie check edited", s.last, flush=True)
    if bpy.ops.dr2.export_to_mod() != {"FINISHED"}:
        fail("zombie export to mod")
    print("DR2GATE zombie exported", flush=True)


main()

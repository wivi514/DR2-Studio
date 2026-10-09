"""Phase 4 in-game gate, Blender side: build the test model from an exported character.

Run inside Blender (no add-on needed):

    dr2 extract --glb data/models/npcs.big/chest_young_chuck.big -o out
    blender -b --factory-startup --python tools/blender_gate_model.py -- \
        out/data/models/npcs.big/chest_young_chuck.big.glb gate.glb

It imports the ``.glb``, then makes the three changes the roadmap's phase 4 gate asks for
(docs/roadmap.md, docs/formats.md §"In-game check (phase 4)"):

(a) the shirt shapes go through Blender untouched (so they are rebuilt, not kept);
(b) both arms are pushed out 2 cm along their normals (moved vertices);
(c) the watch is replaced by a **new mesh**: a small sphere on every face and finger
    bone, each weighted 100 % to its bone, and a blob on the left wrist weighted 50/50
    between the forearm twist bone and the hand. Its bones span nodes 25-91, more than
    one 61-bone palette, so the importer splits it into two draws.

Then it exports ``gate.glb`` with custom properties. Put that file in a mod as
``replace/data/models/npcs.big/chest_young_chuck.big.glb``, deploy, and capture
(docs/dev/recomp-integration.md §Phase 4).
"""
import sys
import bmesh
import bpy
from mathutils import Matrix

src, out = sys.argv[sys.argv.index("--") + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")

# (b) moved vertices: push both arms out along their normals by 2 cm
for name in ("geo_larmShape", "geo_rarmShape"):
    me = bpy.data.objects[name].data
    for v in me.vertices:
        v.co += v.normal * 0.02

# (c) a new mesh replacing the watch: one sphere on every face and finger bone, each
# weighted 100 % to its bone, plus a blob at the left wrist split 50/50 between the
# forearm twist bone and the hand
old = bpy.data.objects["geo_watchShape"]
mat = next(m for m in bpy.data.materials if m.name.startswith("00_"))
bpy.data.objects.remove(old, do_unlink=True)
face = ("eyebrow", "eyelid", "lip", "nostril", "cheek", "eye", "jaw", "tongue")
finger = ("thumb", "index", "middle", "ring", "pinky")
bm = bmesh.new()
bm.loops.layers.uv.new("UVMap")
groups = []
for bone in arm.data.bones:
    short = bone.name.split(".")[-1]
    if any(k in short for k in finger):
        r = 0.012
    elif any(k in short for k in face):
        r = 0.015
    else:
        continue
    head = arm.matrix_world @ bone.head_local
    before = len(bm.verts)
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=r, matrix=Matrix.Translation(head),
                               calc_uvs=True)
    groups.append(([(bone.name, 1.0)], range(before, len(bm.verts))))
hand = arm.data.bones["dummy01.l_hand"]
before = len(bm.verts)
bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.04,
                           matrix=Matrix.Translation(arm.matrix_world @ hand.head_local),
                           calc_uvs=True)
groups.append(([("dummy01.l_farm_twist", 0.5), ("dummy01.l_hand", 0.5)],
               range(before, len(bm.verts))))
me = bpy.data.meshes.new("geo_watchShape")
bm.to_mesh(me)
bm.free()
me.materials.append(mat)
ob = bpy.data.objects.new("geo_watchShape", me)
bpy.context.scene.collection.objects.link(ob)
ob.parent = arm
ob.matrix_parent_inverse = arm.matrix_world.inverted()
ob.modifiers.new("Armature", "ARMATURE").object = arm
for weights, verts in groups:
    for bname, w in weights:
        vg = ob.vertex_groups.get(bname) or ob.vertex_groups.new(name=bname)
        vg.add(list(verts), w, "REPLACE")
print("gate model: spheres", len(groups))
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_extras=True)

# SPDX-License-Identifier: GPL-3.0-or-later
"""DR2 Modding Toolkit for Blender (``io_dr2``): game models in and out of Blender.

A sidebar tab (**View3D > Sidebar > DR2**) over the DR2 toolkit:

* **Find**: search the toolkit's asset index for models and skeletons of Case Zero or
  Case West, by name (``chuck``, ``mechanic``, ``*fullbody``).
* **Import**: one click exports the asset with dr2kit (``dr2 extract --glb``: meshes,
  skeleton, skin, textures) and imports it with Blender's glTF importer, into a new
  collection that remembers which game asset it came from (custom properties
  ``dr2_game`` and ``dr2_vpath`` on the collection).
* **Check rig**: exports that collection with Blender's glTF exporter (custom properties
  on) and runs the toolkit's rig validator (``dr2 model check``) against the original
  model: bone names, weights, materials, bone palettes. The report goes to the Text
  editor (``DR2 rig check``).
* **Export to mod**: the same check, and when it passes, the ``.glb`` goes into a mod
  folder as ``replace/<model vpath>.glb``, ready for ``dr2 mod deploy`` or DR2 Studio.
* **Import level** (dr2kit phase 10): one zone of a level with its pieces placed, its
  items and doors and its markers (spawn points, areas, the navigation mesh), sorted into
  collections (the zone, then Buildings, Items and doors, Markers by kind); *Lightmaps*
  multiplies each level material's baked light into its colour, as the game draws it.

Licence: this add-on is GPL-3.0-or-later (``LICENSE``). It does **not** include dr2kit,
which has its own licence; `toolkit.load` imports it from the folder set in the
preferences. The guide: docs/modding/13-blender-addon.md in the toolkit.
"""

from __future__ import annotations

import os
import tempfile

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, IntProperty,
                       PointerProperty, StringProperty)

from . import toolkit

GAMES = [("cz", "Case Zero", "Dead Rising 2: Case Zero"),
         ("cw", "Case West", "Dead Rising 2: Case West")]
REPORT_TEXT = "DR2 rig check"


# ---- preferences and properties --------------------------------------------------------

class DR2Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    toolkit_path: StringProperty(
        name="Toolkit folder", subtype="DIR_PATH",
        description="The DR2 toolkit's folder: the one that contains 'dr2kit' (a git "
                    "checkout, or the 'python' folder of a DR2 Studio release). Leave "
                    "empty if dr2kit is installed in Blender's Python")

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "toolkit_path")
        try:
            col.label(text=toolkit.describe(toolkit.load(self.toolkit_path)), icon="CHECKMARK")
        except toolkit.ToolkitMissing as e:
            col.label(text=str(e)[:160], icon="ERROR")


def prefs(context) -> DR2Preferences:
    return context.preferences.addons[__package__].preferences


def dr2(context):
    """dr2kit, or raise `toolkit.ToolkitMissing` with what to do."""
    return toolkit.load(prefs(context).toolkit_path)


class DR2Result(bpy.types.PropertyGroup):
    vpath: StringProperty()
    kind: StringProperty()
    size: IntProperty()


_LEVELS: dict[str, list] = {}       # game -> [(level, [zones])]: Blender keeps enum strings


def _levels(game: str) -> list:
    if game not in _LEVELS:
        try:
            dr2(bpy.context)                      # puts dr2kit on the path first
            from . import core
            _LEVELS[game] = core.levels(game)
        except Exception:  # noqa: BLE001 - no toolkit or no game: an empty list
            return []
    return _LEVELS[game]


def _level_items(s, context=None):
    out = [(n, n, f"{len(z)} zones") for n, z in _levels(s.game)]
    _LEVEL_ENUM[s.game] = out or [("", "(no levels: set the toolkit and game)", "")]
    return _LEVEL_ENUM[s.game]


def _zone_items(s, context=None):
    zones = next((z for n, z in _levels(s.game) if n == s.level), [])
    key = (s.game, s.level)
    _ZONE_ENUM[key] = [(z, z, "") for z in zones] or [("", "(pick a level)", "")]
    return _ZONE_ENUM[key]


_LEVEL_ENUM: dict = {}
_ZONE_ENUM: dict = {}


class DR2Settings(bpy.types.PropertyGroup):
    game: EnumProperty(name="Game", items=GAMES, default="cz")
    query: StringProperty(name="Search", description="Words of the name; * and ? work",
                          default="")
    kind: EnumProperty(name="Kind", items=[("", "Models + skeletons", ""),
                                           ("model", "Models", ""),
                                           ("skeleton", "Skeletons", "")], default="")
    results: CollectionProperty(type=DR2Result)
    index: IntProperty(name="Result", default=0)
    textures: BoolProperty(name="Textures", default=True,
                           description="Embed the model's textures (slower)")
    skeleton_only: BoolProperty(name="Skeleton only", default=False,
                                description="Import only the armature")
    mod_folder: StringProperty(name="Mod folder", subtype="DIR_PATH",
                               description="Where Export to mod writes (a mod folder, "
                                           "made if it has no mod.toml)")
    last: StringProperty(name="Last check", default="")
    level: EnumProperty(name="Level", items=_level_items,
                        description="A level of the game (its buildings are its zones)")
    zone: EnumProperty(name="Zone", items=_zone_items,
                       description="A zone: the part of the level the game loads at once")
    level_items: BoolProperty(name="Items", default=True,
                              description="The items and doors placed in the zone")
    level_markers: BoolProperty(name="Markers", default=True,
                                description="Spawn points, areas, triggers, the navigation mesh")
    level_lightmaps: BoolProperty(name="Lightmaps", default=True,
                                  description="Multiply each level material's baked light "
                                              "(its lightmap) into its colour, as the game does")




def dr2_collection(context):
    """The collection an imported asset lives in (from the active object), or None."""
    obj = context.active_object
    if obj is None:
        return None
    owners = list(obj.users_collection)
    if obj.parent is not None:
        owners += obj.parent.users_collection
    for coll in owners:
        if coll.get("dr2_vpath"):
            return coll
    for coll in owners:          # a variant group's collection (Head 2…) inside the model's
        for top in bpy.data.collections:
            if top.get("dr2_vpath") and coll.name in top.children:
                return top
    return None


# ---- operators -------------------------------------------------------------------------

class DR2_OT_search(bpy.types.Operator):
    bl_idname = "dr2.search"
    bl_label = "Search"
    bl_description = "Search the toolkit's asset index for models and skeletons"

    def execute(self, context):
        s = context.scene.dr2
        try:
            dr2(context)
            from . import core
            found = core.search(s.game, s.query, s.kind)
        except (toolkit.ToolkitMissing, RuntimeError) as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        s.results.clear()
        for f in found:
            r = s.results.add()
            r.name, r.vpath, r.kind, r.size = f.name, f.vpath, f.kind, f.size
        s.index = 0
        self.report({"INFO"}, f"{len(found)} result(s)")
        return {"FINISHED"}


class DR2_OT_import(bpy.types.Operator):
    bl_idname = "dr2.import_asset"
    bl_label = "Import"
    bl_description = ("Export the selected game asset with the toolkit and import it with "
                      "Blender's glTF importer, into its own collection")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.dr2
        if not (0 <= s.index < len(s.results)):
            self.report({"ERROR"}, "Search and pick an asset first")
            return {"CANCELLED"}
        r = s.results[s.index]
        try:
            dr2(context)
            from . import core
            glb, summary, notes = core.export_glb(s.game, r.vpath, s.skeleton_only, s.textures)
        except Exception as e:  # noqa: BLE001 - dr2kit errors, shown to the user
            self.report({"ERROR"}, f"{r.vpath}: {e}")
            return {"CANCELLED"}
        coll = bpy.data.collections.new(r.name)
        context.scene.collection.children.link(coll)
        coll["dr2_game"], coll["dr2_vpath"] = s.game, r.vpath
        layer = context.view_layer.layer_collection.children[coll.name]
        context.view_layer.active_layer_collection = layer
        path = _temp_glb(glb)
        # no sphere drawn on every bone (the importer's bone shapes; Blender 4.2+)
        props = bpy.ops.import_scene.gltf.get_rna_type().properties
        extra = {"disable_bone_shape": True} if "disable_bone_shape" in props else {}
        try:
            bpy.ops.import_scene.gltf(filepath=path, **extra)
        finally:
            os.unlink(path)
        arm = next((o for o in coll.objects if o.type == "ARMATURE"), None)
        if arm is not None:
            context.view_layer.objects.active = arm
        organise_variants(coll)
        for n in notes:
            self.report({"WARNING"}, n)
        self.report({"INFO"}, f"imported {r.vpath}: {summary}")
        return {"FINISHED"}


class DR2_OT_import_level(bpy.types.Operator):
    bl_idname = "dr2.import_level"
    bl_label = "Import zone"
    bl_description = ("Build the chosen zone with the toolkit (pieces placed, items, markers) "
                      "and import it into collections by zone and layer")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.dr2
        if not s.level or not s.zone:
            self.report({"ERROR"}, "Pick a level and a zone first")
            return {"CANCELLED"}
        try:
            dr2(context)
            from . import core
            glb, summary, notes = core.export_level_zone(
                s.game, s.level, s.zone, items=s.level_items, markers=s.level_markers)
        except Exception as e:  # noqa: BLE001 - dr2kit errors, shown to the user
            self.report({"ERROR"}, f"{s.level} {s.zone}: {e}")
            return {"CANCELLED"}
        coll = bpy.data.collections.new(f"{s.level} {s.zone}")
        context.scene.collection.children.link(coll)
        coll["dr2_game"], coll["dr2_level"], coll["dr2_zone"] = s.game, s.level, s.zone
        layer = context.view_layer.layer_collection.children[coll.name]
        context.view_layer.active_layer_collection = layer
        path = _temp_glb(glb)
        try:
            bpy.ops.import_scene.gltf(filepath=path)
        finally:
            os.unlink(path)
        n = organise_level(coll)
        wired = wire_lightmaps(coll) if s.level_lightmaps else 0
        for note in notes[:10]:
            self.report({"WARNING"}, note)
        self.report({"INFO"}, f"imported {s.level} {s.zone}: {summary}; {n} collections, "
                              f"{wired} materials with their lightmap")
        return {"FINISHED"}


def organise_level(coll) -> int:
    """Levels (dr2kit phase 10): the zone's group objects say what they hold
    (``dr2_layer``: zone, pieces, items, markers, or a marker kind); make one collection
    per group, nested like the groups, and put every object in the collection of its
    nearest group. Parenting is kept, so everything stays where the game puts it. The
    navigation mesh starts hidden (it lies over every floor). Returns how many
    collections were made."""
    made = {}

    def coll_of(obj):
        if obj is None:
            return coll
        if obj.name in made:
            return made[obj.name]
        if obj.get("dr2_layer") is not None:
            parent = coll_of(obj.parent)
            c = bpy.data.collections.new(obj.name)
            parent.children.link(c)
            made[obj.name] = c
            return c
        return coll_of(obj.parent)
    for obj in list(coll.objects):
        target = coll_of(obj)
        if target is not coll:
            target.objects.link(obj)
            coll.objects.unlink(obj)
        if obj.get("dr2_kind") == "navmesh":     # it covers every floor: hidden at first
            obj.hide_set(True)
            obj.hide_render = True
    return len(made)


def wire_lightmaps(coll) -> int:
    """Multiply each level material's lightmap (the importer puts it on the glTF
    occlusion socket, on its own UV map) into the base colour, read as sRGB like the
    game's shaders do (docs/formats.md §Levels, materials). Returns materials changed."""
    done, seen = 0, set()
    for obj in coll.all_objects:
        for slot in getattr(obj, "material_slots", []):
            mat = slot.material
            if mat is None or mat.name in seen or not mat.use_nodes:
                continue
            seen.add(mat.name)
            nt = mat.node_tree
            bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
            occ = None
            for n in nt.nodes:
                if n.type == "GROUP" and "Occlusion" in n.inputs and n.inputs["Occlusion"].is_linked:
                    occ = n.inputs["Occlusion"].links[0].from_node
                    break
            if bsdf is None or occ is None:
                continue
            while occ.type == "SEPARATE_COLOR" or occ.type == "SEPRGB":   # the R channel split
                occ = occ.inputs[0].links[0].from_node if occ.inputs[0].is_linked else None
                if occ is None:
                    break
            if occ is None or occ.type != "TEX_IMAGE" or occ.image is None:
                continue
            occ.image.colorspace_settings.name = "sRGB"
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            base = bsdf.inputs["Base Color"]
            if base.is_linked:
                nt.links.new(base.links[0].from_socket, mix.inputs[6])
            else:
                mix.inputs[6].default_value = base.default_value
            nt.links.new(occ.outputs["Color"], mix.inputs[7])
            nt.links.new(mix.outputs[2], base)
            mix.location = (bsdf.location.x - 200, bsdf.location.y + 200)
            done += 1
    return done


def organise_variants(coll) -> int:
    """Variants (dr2kit phase 9): put each part in a collection named after its group
    (``dr2_group``: Head 1, Head 2, Shirt 1…) inside ``coll``, and hide the parts the
    chosen look doesn't show (``dr2_shown``). Returns how many parts were hidden.
    Hidden parts are left out of Export to mod, and the toolkit keeps them as they are."""
    groups, hidden = {}, 0
    for obj in list(coll.objects):
        group = obj.get("dr2_group")
        if group is None:
            continue
        sub = groups.get(group)
        if sub is None:
            sub = groups[group] = bpy.data.collections.new(group)
            coll.children.link(sub)
        sub.objects.link(obj)
        coll.objects.unlink(obj)
        if not obj.get("dr2_shown", True):
            obj.hide_set(True)
            obj.hide_render = True
            hidden += 1
    return hidden


def _temp_glb(data: bytes | None = None) -> str:
    fd, path = tempfile.mkstemp(prefix="dr2-", suffix=".glb")
    with os.fdopen(fd, "wb") as f:
        if data:
            f.write(data)
    return path


def export_collection(context, coll) -> bytes:
    """The collection's objects as ``.glb`` bytes, with custom properties (the bones'
    game records ride in them, docs/dev/gltf-mapping.md)."""
    for o in context.view_layer.objects:
        o.select_set(False)
    objs = [o for o in coll.all_objects if o.visible_get()]
    for o in objs:
        o.select_set(True)
    path = _temp_glb()
    try:
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True,
                                  export_extras=True)
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.unlink(path)


def _run_check(op, context):
    """Export the active DR2 collection and run the rig validator. Returns (coll, glb,
    Check) or None after reporting why not."""
    coll = dr2_collection(context)
    if coll is None:
        op.report({"ERROR"}, "Select an object of a model imported with the DR2 tab")
        return None
    try:
        dr2(context)
        from . import core
        glb = export_collection(context, coll)
        result = core.check(coll["dr2_game"], coll["dr2_vpath"], glb, coll.name)
    except Exception as e:  # noqa: BLE001
        op.report({"ERROR"}, str(e))
        return None
    text = bpy.data.texts.get(REPORT_TEXT) or bpy.data.texts.new(REPORT_TEXT)
    text.clear()
    text.write(f"{coll['dr2_vpath']} ({coll['dr2_game']})\n\n{result.report}\n")
    context.scene.dr2.last = (f"{'OK' if result.ok else 'FAILED'}: {result.errors} "
                              f"error(s), {result.warnings} warning(s)")
    return coll, glb, result


class DR2_OT_check(bpy.types.Operator):
    bl_idname = "dr2.check_rig"
    bl_label = "Check rig"
    bl_description = ("Export the selected model's collection and check it against the "
                      "game's model (bones, weights, materials); report in the Text editor "
                      f"('{REPORT_TEXT}')")

    def execute(self, context):
        out = _run_check(self, context)
        if out is None:
            return {"CANCELLED"}
        _, _, result = out
        self.report({"INFO"} if result.ok else {"ERROR"},
                    f"rig check: {context.scene.dr2.last} (details in the Text editor, "
                    f"'{REPORT_TEXT}')")
        return {"FINISHED"}


class DR2_OT_export_mod(bpy.types.Operator):
    bl_idname = "dr2.export_to_mod"
    bl_label = "Export to mod"
    bl_description = ("Check the rig, then write the model into the mod folder as "
                      "replace/<model>.glb")

    def execute(self, context):
        s = context.scene.dr2
        if not s.mod_folder:
            self.report({"ERROR"}, "Choose a mod folder first")
            return {"CANCELLED"}
        out = _run_check(self, context)
        if out is None:
            return {"CANCELLED"}
        coll, glb, result = out
        if not result.ok:
            self.report({"ERROR"}, f"not written: {s.last} (see '{REPORT_TEXT}')")
            return {"CANCELLED"}
        from . import core
        try:
            dest = core.write_to_mod(bpy.path.abspath(s.mod_folder), coll["dr2_game"],
                                     coll["dr2_vpath"], glb)
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        self.report({"INFO"}, f"wrote {dest}; deploy the mod with DR2 Studio or "
                              f"`dr2 mod deploy`")
        return {"FINISHED"}


# ---- the panel -------------------------------------------------------------------------

class DR2_UL_results(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop):
        layout.label(text=item.name, icon="ARMATURE_DATA" if item.kind == "skeleton"
                     else "MESH_DATA")
        layout.label(text=item.vpath.rsplit("/", 2)[-2] if "/" in item.vpath else "")


class DR2_PT_main(bpy.types.Panel):
    bl_label = "Dead Rising 2"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "DR2"

    def draw(self, context):
        s = context.scene.dr2
        lay = self.layout
        try:
            dr2(context)
        except toolkit.ToolkitMissing as e:
            box = lay.box()
            box.label(text="Toolkit not found", icon="ERROR")
            for line in _wrap(str(e), 40):
                box.label(text=line)
            box.operator("preferences.addon_show", text="Open preferences").module = __package__
            return
        col = lay.column(align=True)
        col.prop(s, "game", expand=True)
        row = col.row(align=True)
        row.prop(s, "query", text="")
        row.operator(DR2_OT_search.bl_idname, text="", icon="VIEWZOOM")
        col.prop(s, "kind", text="")
        lay.template_list("DR2_UL_results", "", s, "results", s, "index", rows=6)
        if 0 <= s.index < len(s.results):
            lay.label(text=s.results[s.index].vpath)
        row = lay.row(align=True)
        row.prop(s, "textures")
        row.prop(s, "skeleton_only")
        lay.operator(DR2_OT_import.bl_idname, icon="IMPORT")

        box = lay.box()
        coll = dr2_collection(context)
        box.label(text=f"Selected: {coll['dr2_vpath'].rsplit('/', 1)[-1]}" if coll
                  else "Select an imported model", icon="OBJECT_DATA")
        box.operator(DR2_OT_check.bl_idname, icon="CHECKMARK")
        if s.last:
            box.label(text=s.last, icon="INFO")
        box.prop(s, "mod_folder")
        box.operator(DR2_OT_export_mod.bl_idname, icon="EXPORT")

        box = lay.box()
        box.label(text="Levels", icon="WORLD")
        box.prop(s, "level")
        box.prop(s, "zone")
        row = box.row(align=True)
        row.prop(s, "level_items")
        row.prop(s, "level_markers")
        row.prop(s, "level_lightmaps")
        box.operator(DR2_OT_import_level.bl_idname, icon="IMPORT")


def _wrap(text: str, width: int) -> list[str]:
    out, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > width and line:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return out + ([line] if line else [])


CLASSES = (DR2Preferences, DR2Result, DR2Settings, DR2_OT_search, DR2_OT_import,
           DR2_OT_import_level,
           DR2_OT_check, DR2_OT_export_mod, DR2_UL_results, DR2_PT_main)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.dr2 = PointerProperty(type=DR2Settings)


def unregister():
    del bpy.types.Scene.dr2
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)

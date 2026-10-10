"""Model import: a ``.glb`` from Blender (or `dr2kit.convert.gltf`) → a game model.

Phase 4. The modder exports a model with ``dr2 extract --glb``, edits it in Blender (moves
vertices, or builds a new mesh rigged to the exported armature) and exports a ``.glb``
again. This module puts it back into the original model file:

1. **Match.** Each glTF mesh node is matched to a shape of the model by name (the
   exporter names nodes after shapes, and Blender keeps object names; a trailing
   ``.001`` is ignored). Shapes the file doesn't mention are left as they are; nodes
   that match no shape are reported and ignored (new shapes are not supported yet).
2. **Bones by name.** The glTF skin's joints are matched to the model's skeleton by
   name (``extras.dr2.index`` as a fallback), because Blender re-orders bones. A vertex
   weighted to a bone the game skeleton lacks is an error.
3. **Back to the game's space.** Each vertex is skinned to its rest-pose position with
   the file's own joint matrices (glTF rule: joint world × inverse bind), so the mesh
   lands where Blender showed it, whatever bind matrices Blender wrote. The armature
   must sit where the game's does (its joints are compared with the game's rest pose).
4. **Materials** by the exported name (``NN_<colour texture>``, which Blender keeps),
   else by a texture name inside the material's name. A part's new draw copies the original draw that uses that material
   (shader, textures, vertex layout): `dr2kit.formats.scene_write`.
5. **Weights**: up to 4 influences per vertex (the strongest are kept), normalised and
   quantised to bytes that sum to 255; palettes are runs of at most 61 nodes, and a part
   that needs more is split into several draws.

Unchanged shapes stay byte-identical: a shape whose parts decode to exactly what the
model already holds (vertex for vertex, as in a file straight from ``dr2 extract
--glb``) is not rewritten. So exporting and importing without edits gives back the
model's exact bytes (``dr2 census --models`` checks this for every model).

`plan_import` does all the checks and returns an `ImportPlan` with every problem found
(the **rig validator**: ``dr2 model check``, Studio); `import_glb` writes the model.
Mapping details: docs/dev/gltf-mapping.md §"Coming back: models".
"""

from __future__ import annotations

import json
import math
import re
import struct
from dataclasses import dataclass, field

from ..errors import Dr2Error, FormatError
from ..formats import vertex as vx
from ..formats.scene import Mesh, Scene, mat_inverse_affine, mat_mul, trs_matrix
from ..formats.scene_write import (MAX_PALETTE, DrawGeometry, SceneEditor, find_template,
                                   own_buffers, quantize_weights, split_by_palette)
from .gltf import Glb

# A joint of the file is "where the game's is" within this distance (metres). Blender
# brings back float noise far below this (docs/dev/gltf-mapping.md).
JOINT_TOLERANCE = 1e-3
# Normals count as unchanged within this angle (the exporter normalised them).
NORMAL_TOLERANCE = 1e-3
MAX_INFLUENCES = 4


class ModelImportError(Dr2Error):
    """The ``.glb`` can't be put into this model; the message lists every problem."""


@dataclass
class Issue:
    """One finding of the validator. ``level``: ``error`` (nothing is written),
    ``warning`` (written, but probably not what you meant) or ``info``."""
    level: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level}: {self.where}: {self.message}"


@dataclass
class ImportPlan:
    """What an import would do, and every problem found on the way."""
    scene: Scene
    shapes: dict[str, list[DrawGeometry]] = field(default_factory=dict)   # to rewrite
    unchanged: list[str] = field(default_factory=list)
    untouched: list[str] = field(default_factory=list)      # shapes the file doesn't have
    draws: dict[str, int] = field(default_factory=dict)     # shape -> draws after splitting
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, level: str, where: str, message: str) -> None:
        self.issues.append(Issue(level, where, message))


# --- small matrix helpers (row-major 4×4) -------------------------------------------------

def _node_local(node: dict) -> list[list[float]]:
    if "matrix" in node:
        m = node["matrix"]                       # column-major
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    return trs_matrix(node.get("translation", (0.0, 0.0, 0.0)),
                      node.get("rotation", (0.0, 0.0, 0.0, 1.0)),
                      node.get("scale", (1.0, 1.0, 1.0)))


def _globals(gltf: dict) -> list[list[list[float]]]:
    nodes = gltf.get("nodes", [])
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    out: list = [None] * len(nodes)

    def go(i: int, depth: int = 0):
        if out[i] is None:
            if depth > len(nodes):
                raise FormatError("glTF node hierarchy has a cycle")
            local = _node_local(nodes[i])
            out[i] = mat_mul(go(parent[i], depth + 1), local) if i in parent else local
        return out[i]

    for i in range(len(nodes)):
        go(i)
    return out


IDENTITY = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]]


def _snap_identity(m, tol: float = 1e-5):
    """`IDENTITY` itself when ``m`` is within float noise of it (a joint × its inverse
    bind matrix at rest): the positions then pass through untouched, bit for bit."""
    if all(abs(m[r][c] - IDENTITY[r][c]) <= tol for r in range(4) for c in range(4)):
        return IDENTITY
    return m


def _col_major_to_rows(m) -> list[list[float]]:
    return [[m[c * 4 + r] for c in range(4)] for r in range(4)]


def _xform(m, p) -> tuple[float, float, float]:
    return tuple(m[r][0] * p[0] + m[r][1] * p[1] + m[r][2] * p[2] + m[r][3] for r in range(3))


def _xform_dir(m, d) -> tuple[float, float, float]:
    return tuple(m[r][0] * d[0] + m[r][1] * d[1] + m[r][2] * d[2] for r in range(3))


def _normalise(v) -> tuple[float, float, float]:
    ln = math.sqrt(sum(c * c for c in v))
    return (0.0, 0.0, 1.0) if ln < 1e-12 else tuple(c / ln for c in v)


def _base_name(name: str) -> str:
    """Blender appends ``.001`` to a duplicate name; ignore that when matching."""
    return re.sub(r"\.\d{3}$", "", name).lower()


def _extras(obj: dict) -> dict:
    meta = (obj.get("extras") or {}).get("dr2")
    if isinstance(meta, str):              # Blender may store a dict property as JSON
        try:
            meta = json.loads(meta)
        except ValueError:
            meta = None
    return meta if isinstance(meta, dict) else {}


# --- the plan -------------------------------------------------------------------------------

def plan_import(scene: Scene, glb_bytes: bytes, source: str = "<glb>") -> ImportPlan:
    """Read the ``.glb``, match it to ``scene`` and check everything; write nothing."""
    plan = ImportPlan(scene)
    if not scene.meshes:
        plan.add("error", scene.source, "this is a skeleton, not a model: nothing to import into")
        return plan
    try:
        glb = Glb.parse(glb_bytes, source)
    except (FormatError, ValueError) as e:
        plan.add("error", source, str(e))
        return plan
    gltf = glb.gltf
    nodes = gltf.get("nodes", [])
    try:
        G = _globals(gltf)
    except FormatError as e:
        plan.add("error", source, str(e))
        return plan

    src = (_extras(gltf.get("asset", {})).get("source")
           or next((_extras(sc).get("source") for sc in gltf.get("scenes", [])
                    if _extras(sc).get("source")), None))
    if src and src.lower() != scene.source.lower():
        plan.add("warning", source, f"this file was exported from {src}, not from "
                                    f"{scene.source}")

    # bones: glTF node -> game node index
    skel = scene.skeleton
    by_name = {n.name.lower(): n.index for n in skel.nodes}
    rest = skel.world_matrices() if skel.nodes else []
    node_map: dict[int, int] = {}
    for i, n in enumerate(nodes):
        name = n.get("name", "")
        idx = by_name.get(name.lower(), by_name.get(_base_name(name)))
        if idx is None:
            meta = _extras(n)
            if "index" in meta and "mesh" not in n and 0 <= meta["index"] < len(skel.nodes) \
                    and "record" in meta:
                idx = meta["index"]
        if idx is not None:
            node_map[i] = idx

    # where the file's armature sits relative to the game's: compare joint origins
    skins = gltf.get("skins", [])
    joint_nodes = {j for s in skins for j in s.get("joints", [])}
    moved = []
    for j in joint_nodes:
        if j in node_map:
            g, w = G[j], rest[node_map[j]]
            d = math.dist([g[r][3] for r in range(3)], [w[r][3] for r in range(3)])
            if d > JOINT_TOLERANCE:
                moved.append((d, nodes[j].get("name", "?")))
    if moved:
        moved.sort(reverse=True)
        plan.add("warning", "armature",
                 f"{len(moved)} bone(s) are not where the game's skeleton has them (largest "
                 f"{moved[0][0] * 100:.1f} cm: {moved[0][1]}). Bone edits are not written: "
                 f"the mesh is placed as Blender shows it and the game animates it with its "
                 f"own bones, so check the result in game")

    # shapes
    shapes = {m.name.lower(): m for m in scene.meshes}
    found: dict[str, list[tuple[int, dict]]] = {}
    for i, n in enumerate(nodes):
        if "mesh" not in n:
            continue
        meta = _extras(n)
        cands = [n.get("name", ""), meta.get("shape", ""),
                 gltf["meshes"][n["mesh"]].get("name", "")]
        key = next((c.lower() for c in cands if c and c.lower() in shapes), None)
        if key is None:
            key = next((_base_name(c) for c in cands if c and _base_name(c) in shapes), None)
        if key is None:
            plan.add("warning", f"object {n.get('name', i)!r}",
                     "matches no shape of the model (name it like the part it replaces, "
                     "e.g. geo_tshirtShape); ignored")
            continue
        found.setdefault(key, []).append((i, n))

    for m in scene.meshes:
        if m.name.lower() not in found:
            plan.untouched.append(m.name)
    for key, items in found.items():
        mesh = shapes[key]
        parts = []
        for i, n in items:
            parts += _read_parts(plan, glb, G, i, n, mesh, node_map)
        if any(p is None for p in parts):
            continue
        if _same_as_original(scene, mesh, parts):
            plan.unchanged.append(mesh.name)
            continue
        if _check_parts(plan, scene, mesh, parts):
            plan.shapes[mesh.name] = parts
    if not plan.shapes and not plan.unchanged and plan.ok:
        plan.add("error", source, "no object of the file matches a shape of the model")
    return plan


def _read_parts(plan: ImportPlan, glb: Glb, G, ni: int, node: dict, mesh: Mesh,
                node_map: dict[int, int]) -> list[DrawGeometry | None]:
    """The primitives of one glTF mesh node as `DrawGeometry` in game model space."""
    gltf = glb.gltf
    where = f"{mesh.name}"
    skin = gltf["skins"][node["skin"]] if "skin" in node and gltf.get("skins") else None
    out: list[DrawGeometry | None] = []
    for pi, prim in enumerate(gltf["meshes"][node["mesh"]].get("primitives", [])):
        pw = f"{where} part {pi}"
        if prim.get("mode", 4) != 4:
            plan.add("error", pw, f"primitive mode {prim.get('mode')} (only triangles are "
                                  f"supported; triangulate the mesh)")
            out.append(None)
            continue
        attrs = prim.get("attributes", {})
        if "POSITION" not in attrs:
            plan.add("error", pw, "no POSITION")
            out.append(None)
            continue
        if any("sparse" in gltf["accessors"][a] for a in attrs.values()):
            plan.add("error", pw, "sparse accessors are not supported (apply shape keys)")
            out.append(None)
            continue
        pos = glb.accessor(attrs["POSITION"])
        n = len(pos)
        nrm = glb.accessor(attrs["NORMAL"]) if "NORMAL" in attrs else None
        uvs = []
        k = 0
        while f"TEXCOORD_{k}" in attrs:
            uvs.append([tuple(t[:2]) for t in glb.accessor(attrs[f"TEXCOORD_{k}"])])
            k += 1
        colors = None
        if "COLOR_0" in attrs:
            colors = [tuple(c) + (1.0,) * (4 - len(c)) for c in glb.accessor(attrs["COLOR_0"])]
        if "indices" in prim:
            flat = glb.accessor(prim["indices"])
        else:
            flat = list(range(n))
        if len(flat) % 3:
            plan.add("error", pw, f"{len(flat)} indices: not whole triangles")
            out.append(None)
            continue
        tris = [tuple(flat[i:i + 3]) for i in range(0, len(flat), 3)]
        tris = [t for t in tris if t[0] != t[1] and t[1] != t[2] and t[0] != t[2]]

        # influences: (glTF joint slot, weight) per vertex, sets 0 and 1
        joints = weights = None
        if skin is not None and "JOINTS_0" in attrs and "WEIGHTS_0" in attrs:
            jl = [glb.accessor(attrs["JOINTS_0"])]
            wl = [glb.accessor(attrs["WEIGHTS_0"])]
            if "JOINTS_1" in attrs and "WEIGHTS_1" in attrs:
                jl.append(glb.accessor(attrs["JOINTS_1"]))
                wl.append(glb.accessor(attrs["WEIGHTS_1"]))
            sj = skin["joints"]
            ibm = [_col_major_to_rows(m) for m in glb.accessor(skin["inverseBindMatrices"])] \
                if "inverseBindMatrices" in skin else [[[float(r == c) for c in range(4)]
                                                        for r in range(4)]] * len(sj)
            joint_m = [_snap_identity(mat_mul(G[j], b)) for j, b in zip(sj, ibm)]
            joints, weights = [], []
            missing: dict[str, int] = {}
            too_many = unweighted = 0
            new_pos, new_nrm = [], []
            for v in range(n):
                acc: dict[int, float] = {}
                skin_m = [[0.0] * 4 for _ in range(4)]
                total = 0.0
                for js, ws in zip(jl, wl):
                    for slot, w in zip(js[v], ws[v]):
                        if w <= 0:
                            continue
                        total += w
                        for r in range(4):
                            for c in range(4):
                                skin_m[r][c] += w * joint_m[slot][r][c]
                        gnode = sj[slot]
                        game = node_map.get(gnode)
                        if game is None:
                            nm = gltf["nodes"][gnode].get("name", str(gnode))
                            missing[nm] = missing.get(nm, 0) + 1
                            continue
                        acc[game] = acc.get(game, 0.0) + w
                if total <= 0:
                    unweighted += 1
                    new_pos.append(tuple(pos[v]))
                    new_nrm.append(_normalise(nrm[v]) if nrm else None)
                    joints.append(())
                    weights.append(())
                    continue
                skin_m = _snap_identity([[x / total for x in row] for row in skin_m])
                if skin_m is IDENTITY:
                    new_pos.append(tuple(pos[v]))
                    new_nrm.append(tuple(nrm[v]) if nrm else None)
                else:
                    new_pos.append(_xform(skin_m, pos[v]))
                    new_nrm.append(_normalise(_xform_dir(skin_m, nrm[v])) if nrm else None)
                inf = sorted(acc.items(), key=lambda t: -t[1])
                if len(inf) > MAX_INFLUENCES:
                    too_many += 1
                    inf = inf[:MAX_INFLUENCES]
                joints.append(tuple(j for j, _ in inf))
                weights.append(tuple(w for _, w in inf))
            pos, nrm = new_pos, (new_nrm if nrm else None)
            for nm, cnt in sorted(missing.items()):
                plan.add("error", pw, f"{cnt} vertices are weighted to bone {nm!r}, which "
                                      f"the game skeleton doesn't have (rename it to a game "
                                      f"bone or move the weights)")
            if unweighted:
                plan.add("error", pw, f"{unweighted} of {n} vertices have no bone weight "
                                      f"(in Blender: select them and assign them to a bone)")
            if too_many:
                plan.add("warning", pw, f"{too_many} vertices have more than "
                                        f"{MAX_INFLUENCES} bone weights; the "
                                        f"{MAX_INFLUENCES} strongest are kept (Blender: "
                                        f"Weights → Limit Total, 4)")
        else:
            # a rigid shape is stored relative to its node: take the node's rest pose
            # back off (identity for an unedited export: the bytes stay the same)
            m = G[ni]
            rn = plan.scene.rigid_node(mesh)
            if rn is not None:
                parent = next((i for i, n in enumerate(gltf.get("nodes", []))
                               if ni in n.get("children", [])), None)
                if parent is not None and node_map.get(parent) == rn:
                    # still under its node (our export, Blender's re-export): its own
                    # transform is the offset from the node, exact (sky domes carry
                    # scaled nodes whose inverse adds float noise)
                    m = _node_local(node)
                else:
                    m = mat_mul(mat_inverse_affine(plan.scene.skeleton.world_matrices()[rn]), m)
            m = _snap_identity(m)
            if m is not IDENTITY:
                pos = [_xform(m, p) for p in pos]
                nrm = [_normalise(_xform_dir(m, d)) for d in nrm] if nrm else None

        material = _material(plan, gltf, prim, mesh, pw)
        out.append(DrawGeometry(material, [tuple(p) for p in pos], tris,
                                [tuple(x) for x in nrm] if nrm else None, uvs, colors,
                                joints, weights))
    return out


def material_names(scene: Scene) -> list[str]:
    """The names the exporter gives the model's materials: ``NN_<colour texture>``."""
    return [f"{i:02d}_{m.texture('colour') or 'material'}" for i, m in enumerate(scene.materials)]


def _material(plan: ImportPlan, gltf: dict, prim: dict, mesh: Mesh, where: str) -> int:
    """The game material (index into scene.materials) a primitive uses: by the exported
    name (``NN_<colour texture>``), else by a texture name inside it, else the shape's
    own material (with a warning)."""
    scene = plan.scene
    names = [n.lower() for n in material_names(scene)]
    fallback = mesh.draws[0].material
    if "material" not in prim:
        plan.add("warning", where, f"no material; using the shape's own ({names[fallback]})")
        return fallback
    gm = gltf.get("materials", [])[prim["material"]]
    name = _base_name(gm.get("name", ""))
    if name in names:
        return names.index(name)
    for i, m in enumerate(scene.materials):
        if any(not t.engine and t.name.lower() in name for t in m.slots):
            return i
    plan.add("warning", where, f"material {gm.get('name')!r} is not one of this model's "
                               f"(keep the exported materials, named NN_texture); using the "
                               f"shape's own ({material_names(scene)[fallback]})")
    return fallback


def _same_as_original(scene: Scene, mesh: Mesh, parts: list[DrawGeometry]) -> bool:
    """True when ``parts`` are the shape's draws as the exporter wrote them, untouched:
    same vertices in the same order, same triangles, same material, and values that
    encode to the stored ones."""
    if len(parts) != len(mesh.draws):
        return False
    for g, d in zip(parts, mesh.draws):
        dd = scene.draw_data(d, mesh.name)
        if g.material != d.material or len(g.positions) != len(dd.positions) \
                or g.triangles != dd.triangles:
            return False
        f32 = struct.Struct(">3f")
        if any(f32.pack(*a) != f32.pack(*b) for a, b in zip(g.positions, dd.positions)):
            return False
        if dd.normals:
            if not g.normals:
                return False
            for a, b in zip(g.normals, dd.normals):
                if sum(c * c for c in b) > 1e-12 and \
                        math.dist(a, _normalise(b)) > NORMAL_TOLERANCE:
                    return False
        if len(g.uvs) < len(dd.uvs):
            return False
        for ga, da in zip(g.uvs, dd.uvs):
            if any(abs(x[0] - y[0]) > 1e-6 or abs(x[1] - y[1]) > 1e-6 for x, y in zip(ga, da)):
                return False
        if dd.joints:
            if not g.joints:
                return False
            for gj, gw, dj, dw in zip(g.joints, g.weights, dd.joints, dd.weights):
                want: dict[int, int] = {}
                for j, w in zip(dj, dw):
                    if w > 0:
                        want[j] = want.get(j, 0) + round(w * 255)
                got = dict(zip(gj, quantize_weights(gw))) if gw else {}
                got = {j: q for j, q in got.items() if q}
                if got != want:
                    return False
    return True


def _check_parts(plan: ImportPlan, scene: Scene, mesh: Mesh, parts: list[DrawGeometry]) -> bool:
    """Check what the writer needs; record the number of draws after splitting."""
    ok = True
    try:
        own = own_buffers(mesh)
    except FormatError as e:
        plan.add("error", mesh.name, str(e))
        return False
    total_v = 0
    n_draws = 0
    for k, g in enumerate(parts):
        where = f"{mesh.name} part {k}"
        try:
            tmpl, _ = find_template(scene, mesh, g.material)
        except FormatError as e:
            plan.add("error", where, str(e))
            ok = False
            continue
        tex = [e for e in tmpl.declaration if e.usage == vx.TEXCOORD]
        if len(g.uvs) < len(tex):
            plan.add("warning", where, f"the material's shader reads {len(tex)} UV sets, the "
                                       f"part has {len(g.uvs)}; the missing ones copy UV 0"
                     if g.uvs else "no UVs: textures will not map (unwrap it in Blender)")
        if not g.normals:
            plan.add("warning", where, "no normals; lighting will be flat (export normals)")
        if tmpl.skinned:
            if g.joints is None:
                plan.add("error", where, "the material's shader is skinned, but the part has "
                                         "no bone weights (parent it to the armature with "
                                         "weights)")
                ok = False
                continue
            try:
                groups = split_by_palette(g)
            except FormatError as e:
                plan.add("error", where, str(e))
                ok = False
                continue
            if len(groups) > 1:
                spans = ", ".join(f"{s}-{s + c - 1}" for _, s, c in groups)
                plan.add("info", where, f"uses bones over more than {MAX_PALETTE} node "
                                        f"numbers: split into {len(groups)} draws ({spans})")
            n_draws += len(groups)
        else:
            nodes = {j for js, ws in zip(g.joints or [], g.weights or [])
                     for j, w in zip(js, ws) if w > 0}
            if len(nodes) > 1:
                names = sorted(scene.skeleton.nodes[j].name for j in nodes)[:6]
                plan.add("error", where, f"the material's shader is rigid (no bone weights in "
                                         f"its vertex layout): weight every vertex of this part "
                                         f"to one bone; it uses {len(nodes)} ({', '.join(names)}"
                                         f"{', …' if len(nodes) > 6 else ''})")
                ok = False
            n_draws += 1
        total_v += len(g.positions)
    if own and total_v > 0x10000:
        plan.add("error", mesh.name, f"{total_v} vertices; a shape holds at most 65,536 "
                                     f"(16-bit indices). Split it or decimate")
        ok = False
    plan.draws[mesh.name] = n_draws
    return ok


# --- writing ----------------------------------------------------------------------------

def import_glb(scene: Scene, glb_bytes: bytes, source: str = "<glb>"
               ) -> tuple[bytes, ImportPlan]:
    """Put the ``.glb``'s meshes into ``scene``; return the new scene bytes and the plan.

    Raises `ModelImportError` (listing every error) if the plan has errors. The result is
    read back and each rewritten draw decoded, so a model that the reader can't read is
    never returned.
    """
    plan = plan_import(scene, glb_bytes, source)
    if not plan.ok:
        raise ModelImportError(f"{source} can't go into {scene.source}:\n  "
                               + "\n  ".join(str(i) for i in plan.errors))
    if not plan.shapes:
        return scene.archive.to_bytes(), plan
    ed = SceneEditor(scene)
    try:
        for name, parts in plan.shapes.items():
            ed.replace_mesh(name, parts)
    except FormatError as e:
        raise ModelImportError(f"{source} → {scene.source}: {e}") from None
    for note in ed.notes:
        plan.add("info", scene.source, note)
    out = ed.to_bytes()
    check = Scene.parse(out, scene.source)
    for m in check.meshes:
        if m.name in plan.shapes:
            for d in m.draws:
                check.draw_data(d, m.name)
    return out, plan


def format_plan(plan: ImportPlan) -> str:
    """A readable report of a plan (``dr2 model check``)."""
    lines = []
    for name, parts in plan.shapes.items():
        v = sum(len(g.positions) for g in parts)
        t = sum(len(g.triangles) for g in parts)
        lines.append(f"replace {name}: {len(parts)} part(s) → {plan.draws.get(name, '?')} "
                     f"draw(s), {v:,} vertices, {t:,} triangles")
    for name in plan.unchanged:
        lines.append(f"keep    {name} (unchanged)")
    if plan.untouched:
        lines.append(f"not in the file (kept as they are): {', '.join(plan.untouched)}")
    for i in plan.issues:
        lines.append(str(i))
    lines.append("OK" if plan.ok else f"{len(plan.errors)} error(s): nothing would be written")
    return "\n".join(lines)

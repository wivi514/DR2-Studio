"""Scenes ⇄ glTF 2.0 binary (``.glb``): skeletons and models for Blender and DR2 Studio.

A ``.glb`` is one JSON document plus one binary buffer in a small container; no library
is needed to write or read one, so this module is pure Python and also runs inside
Blender's own Python.

What goes in (docs/dev/gltf-mapping.md has the full table):

* **Skeleton**: one glTF node per game node, named as in the game, with its rest pose
  (translation, rotation, scale) relative to its parent. Each node's ``extras.dr2``
  keeps the original index, parent, flag and the exact 52-byte record (hex), so the
  rig can be put back bit for bit (`skeleton_from_glb`).
* **Rigid parts** (models without skinning: props, vehicles, level pieces): a shape's
  vertices are relative to its node (`Scene.rigid_node`), so its mesh node is a child of
  that node; positions stay exactly as stored.
* **Meshes**: one glTF mesh per game shape, one primitive per draw call, with
  positions, normals, every UV set, vertex colours, and (for skinned draws) joints and
  weights. One glTF skin covers the whole skeleton, so ``JOINTS_0`` holds game node
  indices directly. ``extras.dr2`` on each primitive keeps what phase 4 needs to write
  the draw back (material, palette, shader, vertex declaration).
* **Materials**: one per game material, named after its colour texture, with the colour
  and normal textures embedded as PNG when a ``texture_png`` callback provides them.
  Hair and opacity-map materials are alpha-tested (``alphaMode: MASK``), glass lenses
  blended; every other material is opaque, because their colour maps' alpha is a mask
  (`convert.material.alpha_mode`).

* **Variants** (phase 9, `convert.variants`, optional): each shape's node can carry its
  group and whether the chosen look shows it (``extras.dr2_group`` / ``dr2_shown``), a
  look can leave shapes out ("as shown"), and colour choices become
  ``KHR_materials_variants`` (Blender's glTF Variants tab). `convert.model.model_glb`
  decides all three.

Conventions: the games are Y-up, characters face +Z with their left side at +X, and
the triangle strips give counter-clockwise front faces that agree with the stored
normals on 99.4% of triangles (checked over every draw of both games). That is
exactly glTF's convention, so nothing is flipped or rotated. Units are metres.

Tangents are **not** exported: their 4th component (the bitangent sign) decodes to 0
on half the vertices, which glTF forbids; Blender recomputes tangents anyway.
"""

from __future__ import annotations

import json
import math
import struct
from collections.abc import Callable
from dataclasses import dataclass

from ..errors import FormatError
from ..formats.scene import Node, Scene, Skeleton, mat_inverse_affine

GLB_MAGIC = 0x46546C67      # "glTF"
CHUNK_JSON = 0x4E4F534A     # "JSON"
CHUNK_BIN = 0x004E4942      # "BIN\0"

FLOAT, UINT, USHORT, UBYTE = 5126, 5125, 5123, 5121
ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963
_FMT = {FLOAT: "f", UINT: "I", USHORT: "H", UBYTE: "B"}
_SIZE = {FLOAT: 4, UINT: 4, USHORT: 2, UBYTE: 1}
_COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

# How close a value read back from a glTF must be to the original record's value to
# count as "unchanged". Blender stores bones as float32 matrices in armature space, so a
# round trip brings back float noise that grows with the bone's distance from the
# origin: up to 1.5e-6 on rigs at the origin, 1.4e-4 on the cinematic tiger rig placed
# ~400 m away (tools/blender_skeleton_gate.py). Tolerance = absolute + relative × that
# distance (at least 1 m). Anything further is an edit and is kept as is.
SNAP_TOLERANCE = 1e-5
SNAP_RELATIVE = 2e-6


class GlbBuilder:
    """Accumulates glTF JSON and one binary buffer, then writes a ``.glb``."""

    def __init__(self, generator: str = "dr2kit"):
        self.gltf: dict = {"asset": {"version": "2.0", "generator": generator},
                           "scene": 0, "scenes": [{"nodes": []}], "nodes": [],
                           "buffers": [{"byteLength": 0}], "bufferViews": [],
                           "accessors": []}
        self.bin = bytearray()

    def _list(self, key: str) -> list:
        return self.gltf.setdefault(key, [])

    def view(self, data: bytes, target: int | None = None) -> int:
        """Append bytes as a bufferView (4-byte aligned); return its index."""
        while len(self.bin) % 4:
            self.bin.append(0)
        v = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data)}
        if target:
            v["target"] = target
        self.bin += data
        self._list("bufferViews").append(v)
        return len(self.gltf["bufferViews"]) - 1

    def accessor(self, rows: list, type_: str, ctype: int = FLOAT, *,
                 normalized: bool = False, minmax: bool = False,
                 target: int | None = ARRAY_BUFFER) -> int:
        """Append an accessor for ``rows`` (tuples, or numbers for SCALAR)."""
        n = _COMPONENTS[type_]
        flat = [x for r in rows for x in r] if n > 1 else list(rows)
        data = struct.pack(f"<{len(flat)}{_FMT[ctype]}", *flat)
        a = {"bufferView": self.view(data, target), "componentType": ctype,
             "count": len(rows), "type": type_}
        if normalized:
            a["normalized"] = True
        if minmax and rows:
            cols = list(zip(*rows)) if n > 1 else [rows]
            a["min"] = [min(c) for c in cols]
            a["max"] = [max(c) for c in cols]
        self._list("accessors").append(a)
        return len(self.gltf["accessors"]) - 1

    def add(self, key: str, obj: dict) -> int:
        lst = self._list(key)
        lst.append(obj)
        return len(lst) - 1

    def to_bytes(self) -> bytes:
        while len(self.bin) % 4:
            self.bin.append(0)
        self.gltf["buffers"][0]["byteLength"] = len(self.bin)
        for k in [k for k, v in self.gltf.items() if v == [] and k != "nodes"]:
            del self.gltf[k]
        js = json.dumps(self.gltf, separators=(",", ":")).encode("utf-8")
        js += b" " * (-len(js) % 4)
        total = 12 + 8 + len(js) + 8 + len(self.bin)
        return (struct.pack("<III", GLB_MAGIC, 2, total)
                + struct.pack("<II", len(js), CHUNK_JSON) + js
                + struct.pack("<II", len(self.bin), CHUNK_BIN) + bytes(self.bin))


# --- reading ----------------------------------------------------------------------------

@dataclass
class Glb:
    """A parsed ``.glb``: the JSON document and the binary chunk."""
    gltf: dict
    bin: bytes

    @classmethod
    def parse(cls, data: bytes, source: str = "<glb>") -> "Glb":
        if len(data) < 20 or struct.unpack_from("<I", data)[0] != GLB_MAGIC:
            raise FormatError(f"{source}: not a .glb file")
        _, version, total = struct.unpack_from("<III", data)
        if version != 2:
            raise FormatError(f"{source}: glTF version {version}, expected 2")
        off, gltf, binary = 12, None, b""
        while off + 8 <= min(total, len(data)):
            length, kind = struct.unpack_from("<II", data, off)
            body = data[off + 8:off + 8 + length]
            if kind == CHUNK_JSON:
                gltf = json.loads(body.decode("utf-8"))
            elif kind == CHUNK_BIN and not binary:
                binary = body
            off += 8 + length
        if gltf is None:
            raise FormatError(f"{source}: no JSON chunk")
        return cls(gltf, binary)

    def accessor(self, index: int) -> list:
        """An accessor's values as a list of tuples (or numbers for SCALAR)."""
        a = self.gltf["accessors"][index]
        n = _COMPONENTS[a["type"]]
        ct = a["componentType"]
        if "bufferView" not in a:
            return [(0,) * n if n > 1 else 0] * a["count"]
        v = self.gltf["bufferViews"][a["bufferView"]]
        base = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = v.get("byteStride") or n * _SIZE[ct]
        fmt = f"<{n}{_FMT[ct]}"
        rows = [struct.unpack_from(fmt, self.bin, base + i * stride) for i in range(a["count"])]
        if a.get("normalized"):
            scale = {UBYTE: 255.0, USHORT: 65535.0}.get(ct, 1.0)
            rows = [tuple(x / scale for x in r) for r in rows]
        return rows if n > 1 else [r[0] for r in rows]


# --- skeleton ---------------------------------------------------------------------------

def _f32(x: float) -> float:
    """Round to the nearest float32 (the value the game stores)."""
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _unit(q) -> tuple[float, float, float, float]:
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return tuple(c / n for c in q)


def add_skeleton(b: GlbBuilder, skel: Skeleton) -> list[int]:
    """Add the skeleton's nodes; return the glTF node index of each game node."""
    first = len(b.gltf["nodes"])
    for n in skel.nodes:
        node = {"name": n.name, "translation": list(n.translation),
                "rotation": list(_unit(n.rotation)),
                "extras": {"dr2": {"index": n.index, "parent": n.parent, "flag": n.flag,
                                   "record": n.to_bytes().hex()}}}
        if any(abs(s - 1.0) > 0 for s in n.scale):
            node["scale"] = list(n.scale)
        b.gltf["nodes"].append(node)
    for n in skel.nodes:
        if n.is_root:
            b.gltf["scenes"][0]["nodes"].append(first + n.index)
        else:
            b.gltf["nodes"][first + n.parent].setdefault("children", []).append(first + n.index)
    return [first + i for i in range(len(skel.nodes))]


def skeleton_to_glb(scene: Scene) -> bytes:
    """A ``.glb`` holding only the scene's skeleton (an armature in Blender)."""
    if not scene.skeleton.nodes:
        raise FormatError(f"{scene.source}: no skeleton")
    b = GlbBuilder()
    joints = add_skeleton(b, scene.skeleton)
    add_skin(b, scene.skeleton, joints)     # Blender makes an armature only from a skin
    b.gltf["asset"]["extras"] = {"dr2": {"source": scene.source}}
    b.gltf["scenes"][0]["extras"] = {"dr2": {"source": scene.source}}   # Blender keeps this one
    return b.to_bytes()


def add_skin(b: GlbBuilder, skel: Skeleton, joints: list[int]) -> int:
    """One skin whose joints are every skeleton node, in game order (so a vertex's
    ``JOINTS_0`` value is the game's node index)."""
    inv = [_col_major(mat_inverse_affine(w)) for w in skel.world_matrices()]
    root = next(n.index for n in skel.nodes if n.is_root)
    return b.add("skins", {"joints": joints,
                           "inverseBindMatrices": b.accessor(inv, "MAT4", target=None),
                           "skeleton": joints[root]})


def _close(a, b, tol: float = SNAP_TOLERANCE) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def skeleton_from_glb(data: bytes, source: str = "<glb>") -> list[Node]:
    """Read back game node records from a ``.glb`` made by `skeleton_to_glb` (or by
    Blender after importing one).

    Each node that carries ``extras.dr2`` (directly, or as Blender's custom properties)
    becomes a `Node`. Values within `SNAP_TOLERANCE` of the original record are taken
    from the record, so float noise from Blender doesn't change a single bit; anything
    further away is an edit and is written as the new value.
    """
    glb = Glb.parse(data, source)
    tagged = []
    for node in glb.gltf.get("nodes", []):
        meta = (node.get("extras") or {}).get("dr2")
        if isinstance(meta, str):          # Blender may store a dict property as JSON
            meta = json.loads(meta)
        if meta and "index" in meta:
            tagged.append((node, meta))
    originals = {m["index"]: Node.parse(n.get("name", "?"), bytes.fromhex(m["record"]), source)
                 for n, m in tagged if "record" in m}
    distance = _origin_distances(originals)
    out: dict[int, Node] = {}
    for node, meta in tagged:
        orig = originals.get(meta["index"])
        tol = SNAP_TOLERANCE + SNAP_RELATIVE * max(1.0, distance.get(meta["index"], 0.0))
        t = tuple(node.get("translation", (0.0, 0.0, 0.0)))
        r = tuple(node.get("rotation", (0.0, 0.0, 0.0, 1.0)))
        s = tuple(node.get("scale", (1.0, 1.0, 1.0)))
        if orig is not None:
            if _close(t, orig.translation, tol):
                t = orig.translation
            # q and -q are the same rotation; compare with the stored sign
            ou = _unit(orig.rotation)
            if _close(r, ou, tol) or _close(tuple(-c for c in r), ou, tol):
                r = orig.rotation
            if _close(s, orig.scale, tol):
                s = orig.scale
            name = orig.name
        else:
            name = node.get("name", "?")
        out[meta["index"]] = Node(name, meta["index"], meta.get("parent", -1),
                                  meta.get("flag", 1), tuple(map(_f32, s)),
                                  tuple(map(_f32, t)), tuple(map(_f32, r)))
    if not out:
        raise FormatError(f"{source}: no node carries dr2 extras (was it exported by dr2kit?)")
    return [out[i] for i in sorted(out)]


def _origin_distances(nodes: dict[int, Node]) -> dict[int, float]:
    """Each original node's rest-pose distance from the origin (for the snap tolerance)."""
    if not nodes or sorted(nodes) != list(range(len(nodes))):
        return {}
    try:
        pos = Skeleton([nodes[i] for i in range(len(nodes))]).world_positions()
    except FormatError:
        return {}
    return {i: math.sqrt(sum(c * c for c in p)) for i, p in enumerate(pos)}


# --- models -----------------------------------------------------------------------------

def _col_major(m) -> list[float]:
    return [m[r][c] for c in range(4) for r in range(4)]


def _safe_normal(n) -> tuple[float, float, float]:
    length = math.sqrt(sum(c * c for c in n))
    return (0.0, 0.0, 1.0) if length < 1e-6 else tuple(c / length for c in n)


@dataclass
class ExportStats:
    meshes: int = 0
    primitives: int = 0
    vertices: int = 0
    triangles: int = 0
    textures: int = 0
    baked: int = 0                 # materials whose colour was baked (convert.material)
    missing_textures: list = None
    zero_normals: int = 0


def model_to_glb(scene: Scene, texture_png: Callable[[str], bytes | None] | None = None,
                 *, stats: ExportStats | None = None, base_colour=None,
                 parts: list[dict] | None = None, include=None,
                 colour_variants: list | None = None, extras: dict | None = None) -> bytes:
    """A ``.glb`` with the scene's skeleton, meshes, skin and materials.

    ``texture_png(name)`` returns a texture's PNG bytes (or None if it can't be found);
    without it, materials carry texture names only (in ``extras``). ``base_colour(m)``
    may return ``(name, png bytes, family)`` for a material whose colour comes from
    shader constants (`convert.material`; `model.TextureFinder.baker`): that PNG is used
    as the base colour, and ``extras.dr2.baked`` says so.

    Variants (`convert.variants`, phase 9), all optional:

    * ``parts[i]``: extras for mesh ``i``'s node, kept by Blender as custom properties
      (``{"dr2_group": "Head 2", "dr2_shown": False}``).
    * ``include``: the mesh indices to write (the others are left out: "as shown").
    * ``colour_variants``: ``[(name, {material index: (image name, png, family)})]``,
      written as ``KHR_materials_variants`` (Blender's glTF Variants panel switches them).
    * ``extras``: merged into the scene's ``extras`` (the choice used, for example).
    """
    st = stats if stats is not None else ExportStats()
    st.missing_textures = st.missing_textures or []
    b = GlbBuilder()
    joint_nodes = add_skeleton(b, scene.skeleton) if scene.skeleton.nodes else []

    # materials
    images: dict[str, int] = {}

    def texture(name: str | None) -> int | None:
        if not name or texture_png is None:
            return None
        if name not in images:
            png_bytes = texture_png(name)
            if png_bytes is None:
                st.missing_textures.append(name)
                images[name] = -1
            else:
                img = b.add("images", {"name": name, "mimeType": "image/png",
                                       "bufferView": b.view(png_bytes)})
                images[name] = b.add("textures", {"source": img})
                st.textures += 1
        return None if images[name] < 0 else images[name]

    from .material import ALPHA_CUTOFF, alpha_mode, material_shaders
    used_by = material_shaders(scene)
    used = None if include is None else {d.material for k, mesh in enumerate(scene.meshes)
                                         if k in include for d in mesh.draws}
    for i, m in enumerate(scene.materials):
        colour, normal = m.texture("colour"), m.texture("normal")
        mat = {"name": f"{i:02d}_{colour or 'material'}",
               "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 0.8},
               "extras": {"dr2": {"id": m.id, "hash": f"{m.hash:08X}",
                                  "valueset": f"{m.valueset:08x}",
                                  "params": list(m.params),
                                  "textures": [s.name for s in m.slots if not s.engine]}}}
        if used is not None and i not in used:     # a left-out part's: no textures
            b.add("materials", mat)
            continue
        baked = base_colour(m) if base_colour is not None and texture_png is not None else None
        if baked is not None:
            bname, png_bytes, family = baked
            img = b.add("images", {"name": bname, "mimeType": "image/png",
                                   "bufferView": b.view(png_bytes)})
            t = b.add("textures", {"source": img})
            st.textures += 1
            st.baked += 1
            mat["extras"]["dr2"]["baked"] = family
            if family == "lens":                 # glasses: opacity from the lens shader
                mat["alphaMode"] = "BLEND"
            elif family == "hair":               # lashes, hair cards: cut-out
                mat["alphaMode"] = "MASK"
                mat["alphaCutoff"] = ALPHA_CUTOFF
        else:
            t = texture(colour)
            # hair and opacity-map shaders use the colour map's alpha as transparency;
            # on the other shaders it is a mask and must not cut holes (convert.material)
            if t is not None and any(alpha_mode(s) == "MASK" for s in used_by.get(i, ())):
                mat["alphaMode"] = "MASK"
                mat["alphaCutoff"] = ALPHA_CUTOFF
        if t is not None:
            mat["pbrMetallicRoughness"]["baseColorTexture"] = {"index": t}
        t = texture(normal)
        if t is not None:
            mat["normalTexture"] = {"index": t}
        b.add("materials", mat)

    # colour choices: one material copy per (choice, material), mapped per primitive
    variant_maps: dict[int, list[dict]] = {}
    if colour_variants:
        names = []
        for vi, (vname, mats) in enumerate(colour_variants):
            names.append({"name": vname})
            for i, (bname, png_bytes, family) in sorted(mats.items()):
                base = json.loads(json.dumps(b.gltf["materials"][i]))
                img = b.add("images", {"name": bname, "mimeType": "image/png",
                                       "bufferView": b.view(png_bytes)})
                base["pbrMetallicRoughness"]["baseColorTexture"] = {
                    "index": b.add("textures", {"source": img})}
                base["name"] = f"{base['name']} ({vname})"
                base["extras"]["dr2"]["baked"] = family
                base["extras"]["dr2"]["colour_choice"] = vname
                st.textures += 1
                variant_maps.setdefault(i, []).append({"material": b.add("materials", base),
                                                       "variants": [vi]})
        b.gltf.setdefault("extensionsUsed", []).append("KHR_materials_variants")
        b.gltf.setdefault("extensions", {})["KHR_materials_variants"] = {"variants": names}

    # one skin over the whole skeleton
    skin = None
    if joint_nodes and any(d.skinned for m in scene.meshes for d in m.draws):
        skin = add_skin(b, scene.skeleton, joint_nodes)

    for mesh_index, mesh in enumerate(scene.meshes):
        if include is not None and mesh_index not in include:
            continue
        prims = []
        for d in mesh.draws:
            dd = scene.draw_data(d, mesh.name)
            attrs = {"POSITION": b.accessor(dd.positions, "VEC3", minmax=True)}
            if dd.normals:
                st.zero_normals += sum(1 for n in dd.normals
                                       if sum(c * c for c in n) < 1e-12)
                attrs["NORMAL"] = b.accessor([_safe_normal(n) for n in dd.normals], "VEC3")
            for k, uv in enumerate(dd.uvs):
                attrs[f"TEXCOORD_{k}"] = b.accessor(uv, "VEC2")
            if dd.colors:
                attrs["COLOR_0"] = b.accessor(dd.colors, "VEC4")
            if skin is not None:
                if dd.joints:
                    ws = [tuple(w / (sum(wv) or 1.0) for w in wv) for wv in dd.weights]
                    js = dd.joints
                else:   # an unskinned draw in a skinned model: follow its first palette node
                    js = [(d.palette_start, 0, 0, 0)] * len(dd.positions)
                    ws = [(1.0, 0.0, 0.0, 0.0)] * len(dd.positions)
                attrs["JOINTS_0"] = b.accessor(js, "VEC4", USHORT)
                attrs["WEIGHTS_0"] = b.accessor(ws, "VEC4")
            flat = [i for t in dd.triangles for i in t]
            ictype = USHORT if len(dd.positions) <= 0xFFFF else UINT
            prim = {"attributes": attrs,
                    "indices": b.accessor(flat, "SCALAR", ictype, target=ELEMENT_ARRAY_BUFFER),
                    "extras": {"dr2": {
                        "draw": d.number, "material": d.material,
                        "palette": [d.palette_start, d.palette_count],
                        "shader": f"{d.shader:08X}",
                        "shader_name": scene.shaders.get(d.shader, ""),
                        "declaration": [e.describe() for e in d.declaration]}}}
            if d.material >= 0:
                prim["material"] = d.material
                if d.material in variant_maps:
                    prim["extensions"] = {"KHR_materials_variants": {
                        "mappings": variant_maps[d.material]}}
            prims.append(prim)
            st.primitives += 1
            st.vertices += len(dd.positions)
            st.triangles += len(dd.triangles)
        mi = b.add("meshes", {"name": mesh.name, "primitives": prims})
        node = {"name": mesh.name, "mesh": mi,
                "extras": {"dr2": {"shape": mesh.name, "words": list(mesh.words)}}}
        if parts is not None and mesh_index < len(parts):
            node["extras"].update(parts[mesh_index])
        if skin is not None:
            node["skin"] = skin
        index = b.add("nodes", node)
        # a rigid shape's vertices are relative to its node: hang it there (no skin),
        # so Blender and the 3D view place it as the game does
        rigid = scene.rigid_node(mesh) if skin is None and joint_nodes else None
        if rigid is not None:
            b.gltf["nodes"][joint_nodes[rigid]].setdefault("children", []).append(index)
        else:
            b.gltf["scenes"][0]["nodes"].append(index)
        st.meshes += 1
    b.gltf["asset"]["extras"] = {"dr2": {"source": scene.source}}
    b.gltf["scenes"][0]["extras"] = {"dr2": {"source": scene.source}}   # Blender keeps this one
    if extras:
        b.gltf["scenes"][0]["extras"].update(extras)
    return b.to_bytes()

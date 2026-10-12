"""Fit any model into a game weapon: a ``.glb`` laid where the game's weapon lies (phase 13).

Why: a weapon of one's own is a game weapon's pack with a new shape (`mods.newitem`), and
the shape import (`convert.model_import`) only takes a ``.glb`` that names its object and
material like the game model's and sits in its space. A model from Blender, Sketchfab or
another game does neither: it is upright or lying along any axis, at any size, in parts
with several materials. This module does what phase 12 did by hand for Frostmourne
(`docs/formats.md` §Weapons, "A weapon of one's own on a carrier item"):

1. **Read** every mesh of the file (`read_glb`): positions placed by their nodes, normals
   (made when missing), the first UV set, and each material's colour (its base-colour
   picture, or its flat colour).
2. **Find the weapon's line** (`weapon_frame`): the longest direction of the game model
   (principal axes of its vertices), its two ends, and which end is the **handle**: the
   end away from its "business end" nodes (``Loc_blood``, ``FX``, ``LOC_slice``…), else
   the end nearer its hand nodes (``LOC_rhand``, ``IK_lhand``, ``LOC_WEP_<x>_R``…). The
   hands follow those nodes, measured in game (phase 12): the shape has to come to them.
3. **Lay the new model on it** (`fit`): its longest direction on the game weapon's, its
   flat side on the game weapon's flat side, its handle end on the handle end, at the
   game weapon's length (or the length asked for). Which end of the new model is its
   handle: ``handle="auto"`` takes the end nearer the file's origin (where modelling
   programs usually put a weapon's pivot, at the grip), ``"min"`` / ``"max"`` choose.
   ``turn`` spins it about its length (degrees), ``slide`` moves it along (metres; +
   toward the tip), ``scale`` multiplies its size.
4. **Write a ``.glb`` the import takes** (`fitted_glb`): the game model's own ``.glb``
   (`convert.model.model_glb`, no pictures) with its first shape's geometry replaced by
   the new model's (in that shape's node space) and every other shape shrunk to nothing
   (shapes can't be removed: `model_import`); one material, the game shape's.
5. **One colour picture** (`atlas`): the materials' pictures side by side in one image of
   the game texture's size, UVs moved into each one's cell (a UV outside 0-1 is clamped:
   tiling across a cell can't be kept; `Fitted.notes` says so).

Needs numpy. Nothing here touches the game's bytes: the result is the modder's own model.
"""

from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass, field

try:
    import numpy as np
except ImportError:  # pragma: no cover - numpy is optional for the toolkit
    np = None

from ..errors import Dr2Error
from .gltf import Glb

GRIP_RIGHT = ("loc_rhand", "loc_wep_", "loc_grip")      # right-hand grip node names start so
HAND_NODES = ("rhand", "lhand", "loc_wep_", "grip")       # a hand's node (name contains)
TIP_NODES = ("blood", "fx", "slice", "stuck", "particle", "eff_", "collision")
CLAMP_NOTE = 0.01                    # note clamped UVs when this fraction of them is outside


def _need_numpy() -> None:
    if np is None:
        raise Dr2Error("fitting a model needs numpy (pip install numpy)")


@dataclass
class Geometry:
    """Triangles with one UV set, and per triangle the material (a colour picture)."""
    positions: "np.ndarray"            # (n, 3) float64
    normals: "np.ndarray"              # (n, 3)
    uvs: "np.ndarray"                  # (n, 2), glTF convention (v down)
    triangles: "np.ndarray"            # (t, 3) int64
    material: "np.ndarray"             # (t,) int: index into images
    images: list = field(default_factory=list)   # per material: (h, w, 4) uint8 RGBA


@dataclass
class Frame:
    """A weapon's line: ``handle`` end point, unit ``axis`` toward the tip, its
    ``length``, and the two other principal axes (``side``: widest across, ``thin``)."""
    handle: "np.ndarray"
    axis: "np.ndarray"
    side: "np.ndarray"
    thin: "np.ndarray"
    length: float
    grip: "np.ndarray | None" = None    # the right-hand grip node, when the model has one


@dataclass
class Fitted:
    geometry: Geometry
    frame: Frame                       # the game weapon's
    notes: list[str] = field(default_factory=list)


# --- reading --------------------------------------------------------------------------

def _node_matrices(gltf: dict) -> list:
    from .model_import import _globals
    return [np.array(m, dtype=np.float64) for m in _globals(gltf)]


def _image_bytes(glb: Glb, image: dict) -> bytes | None:
    if "bufferView" in image:
        v = glb.gltf["bufferViews"][image["bufferView"]]
        off = v.get("byteOffset", 0)
        return glb.bin[off:off + v["byteLength"]]
    uri = image.get("uri", "")
    if uri.startswith("data:") and ";base64," in uri:
        import base64
        return base64.b64decode(uri.split(",", 1)[1])
    return None


def _material_image(glb: Glb, mat: dict, source: str) -> "np.ndarray":
    """A material's colour as RGBA: its base-colour picture times its factor, or a 4×4
    tile of its flat colour."""
    from ..mods.texture_import import load_image
    pbr = mat.get("pbrMetallicRoughness", {})
    factor = np.array(pbr.get("baseColorFactor", [1, 1, 1, 1]), dtype=np.float64)
    tex = pbr.get("baseColorTexture")
    if tex is not None:
        g = glb.gltf
        src = g["textures"][tex["index"]].get("source")
        data = _image_bytes(glb, g["images"][src]) if src is not None else None
        if data:
            img = load_image(data, f"{source}: {mat.get('name', 'material')}")
            a = np.frombuffer(img.rgba, np.uint8).reshape(img.height, img.width, 4)
            if np.allclose(factor, 1):
                return a.copy()
            return np.clip(a * factor[None, None, :], 0, 255).astype(np.uint8)
    rgb = np.clip(np.round(factor * 255), 0, 255).astype(np.uint8)
    return np.broadcast_to(rgb, (4, 4, 4)).copy()


def read_glb(data: bytes, source: str = "<glb>") -> Geometry:
    """Every mesh of a ``.glb`` as one `Geometry` (nodes' transforms applied)."""
    _need_numpy()
    glb = Glb.parse(data, source)
    g = glb.gltf
    G = _node_matrices(g)
    mats = g.get("materials", [])
    images = [_material_image(glb, m, source) for m in mats] or []
    default_mat = None
    P, N, U, T, M = [], [], [], [], []
    count = 0
    for ni, node in enumerate(g.get("nodes", [])):
        if "mesh" not in node:
            continue
        m = G[ni]
        for prim in g["meshes"][node["mesh"]].get("primitives", []):
            if prim.get("mode", 4) != 4 or "POSITION" not in prim["attributes"]:
                continue
            a = prim["attributes"]
            pos = np.array(glb.accessor(a["POSITION"]), dtype=np.float64)
            pos = pos @ m[:3, :3].T + m[:3, 3]
            if "indices" in prim:
                idx = np.array(glb.accessor(prim["indices"]), dtype=np.int64).reshape(-1, 3)
            else:
                idx = np.arange(len(pos), dtype=np.int64).reshape(-1, 3)
            if "NORMAL" in a:
                nrm = np.array(glb.accessor(a["NORMAL"]), dtype=np.float64)
                nrm = nrm @ np.linalg.inv(m[:3, :3]).T
            else:
                nrm = _vertex_normals(pos, idx)
            nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
            uv = (np.array(glb.accessor(a["TEXCOORD_0"]), dtype=np.float64)
                  if "TEXCOORD_0" in a else np.zeros((len(pos), 2)))
            mi = prim.get("material")
            if mi is None:
                if default_mat is None:
                    default_mat = len(images)
                    images.append(np.full((4, 4, 4), 200, np.uint8))
                mi = default_mat
            if np.linalg.det(m[:3, :3]) < 0:              # mirrored node: keep faces out
                idx = idx[:, ::-1]
            P.append(pos); N.append(nrm); U.append(uv); T.append(idx + count)
            M.append(np.full(len(idx), mi, np.int64))
            count += len(pos)
    if not P:
        raise Dr2Error(f"{source}: no triangles in this file")
    return Geometry(np.concatenate(P), np.concatenate(N), np.concatenate(U),
                    np.concatenate(T), np.concatenate(M), images)


def _vertex_normals(pos, tri):
    n = np.zeros_like(pos)
    f = np.cross(pos[tri[:, 1]] - pos[tri[:, 0]], pos[tri[:, 2]] - pos[tri[:, 0]])
    for k in range(3):
        np.add.at(n, tri[:, k], f)
    return n


# --- the weapon's line ----------------------------------------------------------------

def _axes(points: "np.ndarray"):
    """Principal axes of a point cloud, longest first (unit rows), and its centre."""
    c = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - c, full_matrices=False)
    return vt, c


def model_points(scene) -> "np.ndarray":
    """A game model's vertices in model space (rigid parts placed by their nodes)."""
    from .render import scene_parts
    parts = scene_parts(scene)
    if not parts:
        raise Dr2Error(f"{scene.source}: no shape to fit to")
    return np.concatenate([p.positions.astype(np.float64) for p in parts])


def grip_node(scene) -> "np.ndarray | None":
    """Where the model's right-hand grip node is (model space), or None."""
    nodes = scene.skeleton.nodes
    if not nodes:
        return None
    world = scene.skeleton.world_matrices()
    for n in nodes:
        last = n.name.rsplit(".", 1)[-1].lower()
        if last.startswith(GRIP_RIGHT) and not last.endswith("_l"):
            m = world[n.index]
            return np.array([m[0][3], m[1][3], m[2][3]], dtype=np.float64)
    return None


def _node_points(scene, words) -> list:
    nodes = scene.skeleton.nodes
    if not nodes:
        return []
    world = scene.skeleton.world_matrices()
    out = []
    for n in nodes[1:]:
        last = n.name.rsplit(".", 1)[-1].lower()
        if any(w in last for w in words):
            m = world[n.index]
            out.append(np.array([m[0][3], m[1][3], m[2][3]], dtype=np.float64))
    return out


def weapon_frame(scene) -> Frame:
    """The game weapon's line (module docstring, step 2). Which end is the handle: the
    end away from the model's "business end" nodes (``blood``, ``FX``, ``slice``,
    ``stuck``, ``particle``: where the game draws blood and effects), else the end nearer
    the hand nodes' middle (the right hand alone misleads: on a sledgehammer it sits
    mid-shaft, nearer the head), else nearer the model's origin. Checked on 18 game
    weapons of both games (docs/formats.md §Weapons)."""
    _need_numpy()
    pts = model_points(scene)
    vt, c = _axes(pts)
    axis, side = vt[0], vt[1]
    t = (pts - c) @ axis
    lo, hi = float(t.min()), float(t.max())
    mid = (lo + hi) / 2
    tips = _node_points(scene, TIP_NODES)
    hands = _node_points(scene, HAND_NODES)
    if tips:
        handle_hi = float(np.mean([(p - c) @ axis for p in tips])) < mid
    elif hands:
        handle_hi = float(np.mean([(p - c) @ axis for p in hands])) > mid
    else:
        handle_hi = float((np.zeros(3) - c) @ axis) > mid
    if handle_hi:
        axis, lo, hi = -axis, -hi, -lo
        side = -side
    return Frame(c + axis * lo, axis, side, np.cross(axis, side), hi - lo, grip_node(scene))


# --- fitting ------------------------------------------------------------------------

def fit(geom: Geometry, frame: Frame, *, handle: str = "auto", length: float | None = None,
        turn: float = 0.0, slide: float = 0.0, scale: float = 1.0) -> Geometry:
    """``geom`` laid on the weapon line ``frame`` (module docstring, step 3)."""
    _need_numpy()
    if handle not in ("auto", "min", "max"):
        raise Dr2Error(f"handle {handle!r}: auto, min or max")
    pts = geom.positions
    vt, c = _axes(pts)
    axis, side = vt[0], vt[1]
    t = (pts - c) @ axis
    lo, hi = float(t.min()), float(t.max())
    if hi - lo < 1e-9:
        raise Dr2Error("the model has no length")
    if handle == "auto":
        handle = "min" if float((np.zeros(3) - c) @ axis) <= (lo + hi) / 2 else "max"
    if handle == "max":
        axis, lo, hi = -axis, -hi, -lo
        side = -side
    thin = np.cross(axis, side)
    own = np.stack([axis, side, thin])                 # rows: the model's own frame
    a = math.radians(turn)
    spin = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    game = np.stack([frame.axis, frame.side, frame.thin])
    rot = game.T @ spin @ own                          # own frame -> game frame
    s = (length if length else frame.length) / (hi - lo) * scale
    start = c + axis * lo                              # the handle end of the model
    out_p = ((pts - start) @ rot.T) * s + frame.handle + frame.axis * slide
    out_n = geom.normals @ rot.T
    return Geometry(out_p, out_n, geom.uvs.copy(), geom.triangles.copy(),
                    geom.material.copy(), geom.images)


# --- one picture --------------------------------------------------------------------

def _resize(img: "np.ndarray", w: int, h: int) -> "np.ndarray":
    from . import png
    from ..mods.texture_import import resize
    r = resize(png.Image(img.shape[1], img.shape[0], np.ascontiguousarray(img).tobytes()), w, h)
    return np.frombuffer(r.rgba, np.uint8).reshape(h, w, 4)


def atlas(geom: Geometry, width: int, height: int, notes: list | None = None
          ) -> tuple["np.ndarray", "np.ndarray"]:
    """(one ``height``×``width`` RGBA picture, the UVs moved into it) for ``geom``'s
    materials (module docstring, step 5). Materials no triangle uses take no cell."""
    _need_numpy()
    used = sorted(set(int(m) for m in np.unique(geom.material)))
    uv = geom.uvs.copy()
    if len(used) == 1:
        img = _resize(geom.images[used[0]], width, height)
        return img, uv
    cols = math.ceil(math.sqrt(len(used)))
    rows = math.ceil(len(used) / cols)
    cw, ch = width // cols, height // rows
    out = np.zeros((height, width, 4), np.uint8)
    out[..., 3] = 255
    new_uv = uv.copy()
    outside = 0
    for k, mi in enumerate(used):
        cx, cy = k % cols, k // cols
        out[cy * ch:(cy + 1) * ch, cx * cw:(cx + 1) * cw] = _resize(geom.images[mi], cw, ch)
        verts = np.unique(geom.triangles[geom.material == mi])
        u, v = uv[verts, 0], uv[verts, 1]
        outside += int(((u < -1e-4) | (u > 1 + 1e-4) | (v < -1e-4) | (v > 1 + 1e-4)).sum())
        # half a texel in from the cell's edge, so filtering doesn't bleed
        pu, pv = 0.5 / cw, 0.5 / ch
        u = np.clip(u, pu, 1 - pu)
        v = np.clip(v, pv, 1 - pv)
        new_uv[verts, 0] = (cx + u) * cw / width
        new_uv[verts, 1] = (cy + v) * ch / height
    if notes is not None and outside > CLAMP_NOTE * len(uv):
        notes.append(f"{outside} UV(s) were outside 0-1 (a repeating texture): with several "
                     f"materials in one picture they were clamped, so those parts may look "
                     f"stretched; one material per model keeps them")
    return out, new_uv


# --- the .glb for the import --------------------------------------------------------

def fitted_glb(template_glb: bytes, scene, geom: Geometry, uvs: "np.ndarray") -> bytes:
    """The game model's ``.glb`` (``template_glb``: `convert.model.model_glb`, without
    pictures) with its first shape's geometry replaced by ``geom`` (model space, ``uvs``
    from `atlas`) and the other shapes shrunk to one empty triangle."""
    _need_numpy()
    glb = Glb.parse(template_glb, "template")
    g = glb.gltf
    G = _node_matrices(g)
    shapes = [m.name.lower() for m in scene.meshes]
    first = scene.meshes[0].name.lower()
    blob = bytearray()
    views, accs = [], []

    def add(arr, comp, typ, target, minmax=False):
        data = np.ascontiguousarray(arr).tobytes()
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data),
                      "target": target})
        blob.extend(data)
        a = {"bufferView": len(views) - 1, "componentType": comp, "count": len(arr),
             "type": typ}
        if minmax:
            a["min"] = arr.min(axis=0).tolist()
            a["max"] = arr.max(axis=0).tolist()
        accs.append(a)
        return len(accs) - 1

    for ni, node in enumerate(g.get("nodes", [])):
        if "mesh" not in node:
            continue
        name = node.get("name", "").lower()
        mesh = g["meshes"][node["mesh"]]
        prim0 = mesh["primitives"][0]
        material = prim0.get("material", 0)
        uv_sets = [k for k in prim0["attributes"] if k.startswith("TEXCOORD")] or ["TEXCOORD_0"]
        if name == first or (name not in shapes and mesh.get("name", "").lower() == first):
            inv = np.linalg.inv(G[ni])
            p = geom.positions @ inv[:3, :3].T + inv[:3, 3]
            n = geom.normals @ np.linalg.inv(inv[:3, :3]).T
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
            tri = geom.triangles
            if len(p) > 65535:
                raise Dr2Error(f"the model has {len(p):,} vertices; a weapon shape takes at "
                               f"most 65,535 (docs/formats.md §Engine limits): simplify it "
                               f"in Blender (Decimate)")
            uvv = uvs
        else:                                             # hidden: one empty triangle
            p = np.zeros((3, 3))
            n = np.tile([0.0, 1.0, 0.0], (3, 1))
            tri = np.array([[0, 1, 2]])
            uvv = np.zeros((3, 2))
        attrs = {"POSITION": add(p.astype("<f4"), 5126, "VEC3", 34962, True),
                 "NORMAL": add(n.astype("<f4"), 5126, "VEC3", 34962)}
        for k in uv_sets:
            attrs[k] = add(uvv.astype("<f4"), 5126, "VEC2", 34962)
        ind = add(tri.astype("<u2").ravel(), 5123, "SCALAR", 34963)
        mesh["primitives"] = [{"attributes": attrs, "indices": ind, "material": material,
                               "mode": 4}]
        node.pop("skin", None)
    for k in ("images", "textures", "samplers"):
        g.pop(k, None)
    for m in g.get("materials", []):
        pbr = m.get("pbrMetallicRoughness", {})
        pbr.pop("baseColorTexture", None)
        m.pop("normalTexture", None)
        m.pop("emissiveTexture", None)
        m.pop("occlusionTexture", None)
        pbr.pop("metallicRoughnessTexture", None)
    g.pop("extensionsUsed", None)
    g.pop("extensions", None)
    for m in g.get("materials", []):
        m.pop("extensions", None)
    if not g.get("skins"):
        g.pop("skins", None)
    while len(blob) % 4:
        blob.append(0)
    g["bufferViews"] = views
    g["accessors"] = accs
    g["buffers"] = [{"byteLength": len(blob)}]
    # skins referred to accessors of the old binary: keep their joints, drop the matrices
    for s in g.get("skins", []):
        s.pop("inverseBindMatrices", None)
    js = json.dumps(g, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob))
    out += struct.pack("<II", len(js), 0x4E4F534A) + js
    out += struct.pack("<II", len(blob), 0x004E4942) + bytes(blob)
    return out


def fit_model(tree, scene, glb_bytes: bytes, source: str = "<glb>", *, texture_size=None,
              **placement) -> tuple[bytes, "np.ndarray", Fitted]:
    """The whole fit: (``.glb`` for the import, its colour picture as RGBA, `Fitted`).
    ``texture_size``: (width, height) of the picture, default the game shape's colour
    texture's; ``placement``: `fit`'s keywords."""
    from .model import model_glb
    geom = read_glb(glb_bytes, source)
    frame = weapon_frame(scene)
    placed = fit(geom, frame, **placement)
    notes: list[str] = []
    w, h = texture_size or (256, 256)
    img, uvs = atlas(placed, w, h, notes)
    template = model_glb(tree, scene, textures=False)
    out = fitted_glb(template, scene, placed, uvs)
    return out, img, Fitted(placed, frame, notes)

"""A small software renderer: a model's picture for the Library's thumbnails.

Why our own renderer: thumbnails are made while the index is built (``dr2 index
build``), which runs without a window, a GPU or Qt, on every OS. Rendering DR2 Studio's
3D page offscreen would tie the index to QtWebEngine; a few dozen lines of numpy draw a
128-pixel picture of a model in milliseconds (measured: docs/devlog.md, 2026-10-09).

How it draws (no triangle-by-triangle Python loop):

* **Camera**: orthographic, looking at the model from the front, a little from its
  right and above (characters face +Z, Y is up: docs/dev/gltf-mapping.md), framed on
  the model's projected bounds.
* **Rasterising by sampling**: every triangle is covered by a lattice of points fine
  enough that no pixel between them is missed (``k`` steps per edge, ``k`` ≥ the
  longest edge in pixels), numbered with plain numpy arrays (`_lattice`). One sort of
  packed integer keys (pixel, nearness, point) keeps the nearest point per pixel (a
  z-buffer); only those winners are shaded.
* **Colour**: the material's colour texture sampled at the point's UV, or for
  materials whose colour is shader constants (zombie clothing) the colour
  `convert.material` bakes, as the ``.glb`` export does (the index's
  128-pixel texture thumbnails are plenty for a 128-pixel picture), or grey without
  one; lit by a light from the camera's side (two-sided: a few game meshes have flipped
  normals). Only hair, opacity-map and lens materials are see-through (alpha under
  ``ALPHA_CUTOFF`` dropped), the same rule as the ``.glb`` export
  (`convert.material.alpha_mode`): on cloth and skin shaders a colour map's alpha is a
  mask, and a first version that alpha-tested everything erased the zombies' clothes.
* **Anti-aliasing**: drawn at ``SUPERSAMPLE``× the size and averaged down.

Needs numpy (optional for the toolkit): `available` says whether it is there.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

try:
    import numpy as np
except ImportError:  # pragma: no cover - numpy is optional
    np = None

SUPERSAMPLE = 2
ALPHA_CUTOFF = 0.5              # as convert.material.ALPHA_CUTOFF (the .glb's alphaCutoff)
VIEW = (0.55, 0.35, 1.0)        # direction from the model towards the camera
GREY = (0.62, 0.62, 0.64)


def available() -> bool:
    return np is not None


@dataclass
class Part:
    """One draw's geometry for the renderer (numpy arrays, model space)."""
    positions: "np.ndarray"            # (n, 3) float32
    triangles: "np.ndarray"            # (t, 3) int32
    normals: "np.ndarray | None"       # (n, 3)
    uvs: "np.ndarray | None"           # (n, 2)
    texture: "np.ndarray | None"       # (h, w, 4) float32 0..1, or None (grey)
    alpha_test: bool = False           # drop points whose texture alpha < ALPHA_CUTOFF


def _basis():
    d = np.array(VIEW, dtype=np.float64)
    d /= np.linalg.norm(d)
    right = np.cross(np.array([0.0, 1.0, 0.0]), d)
    right /= np.linalg.norm(right)
    up = np.cross(d, right)
    return right, up, d


def _lattice(k: "np.ndarray"):
    """For triangles with ``k`` steps per edge: the triangle number of each lattice
    point and its barycentric ``(u, v)``. Row ``a`` of a triangle holds ``k + 1 - a``
    points (``b`` = 0 … k - a), so a triangle has (k + 1)(k + 2) / 2 points; a point's
    row comes from its number within the triangle by solving the quadratic."""
    m = (k + 1) * (k + 2) // 2
    total = int(m.sum())
    ti = np.repeat(np.arange(len(k)), m)
    j = np.arange(total) - np.repeat(np.cumsum(m) - m, m)
    kk = k[ti]
    q = 2 * kk + 3
    a = np.floor((q - np.sqrt(np.maximum(q * q - 8 * j, 0))) / 2).astype(np.int64)
    start = a * (kk + 1) - a * (a - 1) // 2
    over = j < start                                    # float rounding: one row too far
    a = np.where(over, a - 1, a)
    start = np.where(over, a * (kk + 1) - a * (a - 1) // 2, start)
    b = j - start
    under = b > kk - a                                  # one row short
    a = np.where(under, a + 1, a)
    b = np.where(under, j - (a * (kk + 1) - a * (a - 1) // 2), b)
    return ti, a / kk, b / kk


def render(parts: list[Part], size: int = 128) -> "np.ndarray | None":
    """Draw the parts; return an (size, size, 4) uint8 RGBA picture (transparent
    background), or None when there is nothing to draw."""
    parts = [p for p in parts if len(p.triangles) and len(p.positions)]
    if not parts:
        return None
    right, up, d = _basis()
    proj = np.stack([right, up, d], axis=1)                    # (3, 3)
    screen = [p.positions.astype(np.float64) @ proj for p in parts]
    allpts = np.concatenate([s[:, :2] for s in screen])
    finite = np.isfinite(allpts).all(axis=1)
    if not finite.any():
        return None
    lo, hi = allpts[finite].min(axis=0), allpts[finite].max(axis=0)
    span = float(max(hi[0] - lo[0], hi[1] - lo[1], 1e-6))
    big = size * SUPERSAMPLE
    scale = big * 0.92 / span
    centre = (lo + hi) / 2
    zs = np.concatenate([s[:, 2] for s in screen])
    zlo, zspan = float(np.nanmin(zs)), float(np.nanmax(zs) - np.nanmin(zs)) or 1.0
    light = d * 0.8 + up * 0.45 + right * 0.25
    light /= np.linalg.norm(light)

    # 1. every part's lattice points: pixel and depth. Kept per part, to colour only the
    #    winners afterwards.
    keys, kept = [], []
    offset = 0
    # one 64-bit sort key per point: pixel | nearness | point number, each field as wide
    # as this picture needs (a 128-px picture: 16 + 24 + 24 bits)
    pix_bits = max(1, (big * big - 1).bit_length())
    pt_bits = 24
    near_bits = 64 - pix_bits - pt_bits
    if near_bits < 12:
        raise ValueError(f"render: {size} px is too large a picture")
    near_max = (1 << near_bits) - 1
    for pi, (p, s) in enumerate(zip(parts, screen)):
        xy = (s[:, :2] - centre) * scale + big / 2
        xy[:, 1] = big - xy[:, 1]                               # image rows go down
        tri = p.triangles[np.isfinite(xy[p.triangles]).all(axis=(1, 2))]
        if not len(tri):
            continue
        a, b, c = xy[tri[:, 0]], xy[tri[:, 1]], xy[tri[:, 2]]
        edge = np.maximum.reduce([np.hypot(*(a - b).T), np.hypot(*(b - c).T),
                                  np.hypot(*(c - a).T)])
        k = np.clip(np.ceil(edge).astype(np.int64), 1, 2 * big)   # off-frame edges capped
        if int(((k + 1) * (k + 2) // 2).sum()) > 20_000_000:   # absurd geometry: skip
            continue
        ti, u, v = _lattice(k)
        w = 1.0 - u - v
        i0, i1, i2 = tri[ti, 0], tri[ti, 1], tri[ti, 2]
        px = w * xy[i0, 0] + u * xy[i1, 0] + v * xy[i2, 0]
        py = w * xy[i0, 1] + u * xy[i1, 1] + v * xy[i2, 1]
        ix, iy = px.astype(np.int64), py.astype(np.int64)
        inside = (ix >= 0) & (ix < big) & (iy >= 0) & (iy < big)
        if p.alpha_test and p.texture is not None and p.uvs is not None \
                and len(p.uvs) == len(p.positions):
            inside &= _sample(p.texture, p.uvs, i0, i1, i2, u, v, w)[:, 3] >= ALPHA_CUTOFF
        sel = np.nonzero(inside)[0]
        if not len(sel):
            continue
        z = (w[sel] * s[i0[sel], 2] + u[sel] * s[i1[sel], 2] + v[sel] * s[i2[sel], 2])
        near = np.clip(((zlo + zspan - z) / zspan) * near_max, 0, near_max).astype(np.uint64)
        pix = (iy[sel] * big + ix[sel]).astype(np.uint64)
        keys.append((pix << np.uint64(near_bits + pt_bits)) | (near << np.uint64(pt_bits))
                    | (np.arange(len(sel), dtype=np.uint64) + np.uint64(offset)))
        kept.append((pi, tri, ti[sel], u[sel], v[sel], w[sel], offset))
        offset += len(sel)
        if offset >= 0xFFFFFF:
            break
    if not keys:
        return None
    key = np.sort(np.concatenate(keys))
    pix = key >> np.uint64(near_bits + pt_bits)
    first = np.ones(len(key), dtype=bool)
    first[1:] = pix[1:] != pix[:-1]
    win_pix = pix[first].astype(np.int64)
    win_pt = (key[first] & np.uint64(0xFFFFFF)).astype(np.int64)

    # 2. colour the winners, part by part
    img = np.zeros((big * big, 4), dtype=np.float64)
    for pi, tri, ti, u, v, w, off in kept:
        mine = (win_pt >= off) & (win_pt < off + len(ti))
        if not mine.any():
            continue
        q = win_pt[mine] - off
        p = parts[pi]
        t, uu, vv, ww = ti[q], u[q], v[q], w[q]
        i0, i1, i2 = tri[t, 0], tri[t, 1], tri[t, 2]
        if p.normals is not None and len(p.normals) == len(p.positions):
            nrm = (ww[:, None] * p.normals[i0] + uu[:, None] * p.normals[i1]
                   + vv[:, None] * p.normals[i2]).astype(np.float64)
        else:
            pos = p.positions.astype(np.float64)
            nrm = np.cross(pos[i1] - pos[i0], pos[i2] - pos[i0])
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
        shade = 0.35 + 0.65 * np.abs(nrm @ light)
        if p.texture is not None and p.uvs is not None and len(p.uvs) == len(p.positions):
            rgb = _sample(p.texture, p.uvs, i0, i1, i2, uu, vv, ww)[:, :3]
        else:
            rgb = np.broadcast_to(np.array(GREY), (len(q), 3))
        img[win_pix[mine], :3] = np.clip(rgb * shade[:, None], 0.0, 1.0)
        img[win_pix[mine], 3] = 1.0
    img = img.reshape(big, big, 4)
    if SUPERSAMPLE > 1:
        f = SUPERSAMPLE
        img = img.reshape(size, f, size, f, 4)
        cover = img[..., 3].sum(axis=(1, 3))
        rgb = (img[..., :3] * img[..., 3:4]).sum(axis=(1, 3)) / np.maximum(cover, 1e-9)[..., None]
        img = np.concatenate([rgb, (cover / (f * f))[..., None]], axis=2)
    return np.clip(np.rint(img * 255), 0, 255).astype(np.uint8)


def _sample(tex, uvs, i0, i1, i2, u, v, w):
    """Nearest texel of ``tex`` at the interpolated UV (wrapping, like the game)."""
    th, tw = tex.shape[:2]
    uu = w * uvs[i0, 0] + u * uvs[i1, 0] + v * uvs[i2, 0]
    vv = w * uvs[i0, 1] + u * uvs[i1, 1] + v * uvs[i2, 1]
    tx = np.floor(np.mod(uu, 1.0) * tw).astype(np.int64) % tw
    ty = np.floor(np.mod(vv, 1.0) * th).astype(np.int64) % th
    return tex[ty, tx]


def scene_parts(scene, texture_for: Callable[[str], "np.ndarray | None"] | None = None,
                problems: list | None = None,
                material_colour: Callable[[object], "np.ndarray | None"] | None = None
                ) -> list[Part]:
    """A parsed `Scene`'s draws as renderer parts (rest pose).

    ``texture_for(name)`` gives a colour texture as an (h, w, 4) float array, or None.
    ``material_colour(material)``, tried first, gives the colour of a material whose
    colour is not a texture (zombie clothing: `convert.material` bakes it from shader
    constants, as the ``.glb`` export does), or None to use its texture.
    A draw that can't be decoded is skipped and named in ``problems``."""
    parts = []
    cache: dict[str, object] = {}
    baked: dict[int, object] = {}
    for mesh in scene.meshes:
        for dr in mesh.draws:
            try:
                dd = scene.draw_data(dr, mesh.name)
            except Exception as ex:  # noqa: BLE001 - reported by the caller
                if problems is not None:
                    problems.append(f"{mesh.name} draw {dr.number}: {ex}")
                continue
            if not dd.triangles:
                continue
            tex = None
            see_through = False
            if material_colour is not None and 0 <= dr.material < len(scene.materials):
                if dr.material not in baked:
                    baked[dr.material] = material_colour(scene.materials[dr.material])
                tex = baked[dr.material]
                # a baked colour carries alpha only where it means opacity (lenses)
                see_through = tex is not None and float(tex[..., 3].min()) < 1.0
            if tex is None and texture_for is not None and 0 <= dr.material < len(scene.materials):
                name = scene.materials[dr.material].texture("colour")
                if name:
                    if name not in cache:
                        cache[name] = texture_for(name)
                    tex = cache[name]
            if not see_through and tex is not None:
                from .material import alpha_mode
                see_through = alpha_mode(scene.shaders.get(dr.shader, "")) == "MASK"
            parts.append(Part(
                np.asarray(dd.positions, dtype=np.float32),
                np.asarray(dd.triangles, dtype=np.int32),
                np.asarray(dd.normals, dtype=np.float32) if dd.normals else None,
                np.asarray(dd.uvs[0], dtype=np.float32) if dd.uvs else None,
                tex, see_through))
    return parts


def rgba_to_float(rgba: bytes, width: int, height: int) -> "np.ndarray":
    """RGBA bytes → an (h, w, 4) float array for `Part.texture`."""
    return np.frombuffer(rgba, dtype=np.uint8).reshape(height, width, 4).astype(np.float32) / 255


def to_png(img: "np.ndarray") -> bytes:
    """A rendered picture as PNG bytes (RGBA)."""
    from . import png
    h, w = img.shape[:2]
    return png.encode(png.Image(w, h, img.tobytes()), "RGBA", level=6)


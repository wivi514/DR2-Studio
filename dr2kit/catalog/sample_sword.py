"""A sample sword model made by code: something to try the weapon wizard with (phase 13).

Why: a newcomer trying *New weapon…* may not have a model of their own yet, and the
toolkit's tests need a model that is not game data (CLAUDE.md: never put game assets in
tests). `sample_sword_glb` builds one from boxes: a tapered steel blade with a painted
fuller (a picture made here, so the texture path is exercised too), a gold guard, a
leather grip and a pommel, three materials in all. It stands upright (+Y, glTF's up) with
its origin in the middle of the grip, as modelling programs usually place a weapon's
pivot, so `convert.weapon_fit` finds the handle end on its own. 1.05 m long.

``dr2 mod new-weapon … --glb sample`` uses it; *New weapon…* offers it as "the sample sword".
"""

from __future__ import annotations


from ..convert import png
from ..convert.gltf import ELEMENT_ARRAY_BUFFER, FLOAT, UINT, GlbBuilder

SAMPLE = "sample"          # the name the CLI and Studio take for this model


def _box(x0, x1, y0, y1, z0, z1, top_scale=1.0):
    """A box's 24 vertices (4 per face, own normals), UVs 0-1 per face, 12 triangles.
    ``top_scale`` narrows the top face (x and z) toward the box's centre line: a tip."""
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2

    def top(x, z):
        return cx + (x - cx) * top_scale, cz + (z - cz) * top_scale

    c = {}
    for xi, x in enumerate((x0, x1)):
        for yi, y in enumerate((y0, y1)):
            for zi, z in enumerate((z0, z1)):
                if yi:
                    tx, tz = top(x, z)
                    c[xi, yi, zi] = (tx, y, tz)
                else:
                    c[xi, yi, zi] = (x, y, z)
    faces = [((1, 0, 0), [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)]),
             ((-1, 0, 0), [(0, 0, 1), (0, 1, 1), (0, 1, 0), (0, 0, 0)]),
             ((0, 1, 0), [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)]),
             ((0, -1, 0), [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]),
             ((0, 0, 1), [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]),
             ((0, 0, -1), [(1, 0, 0), (0, 0, 0), (0, 1, 0), (1, 1, 0)])]
    pos, nrm, uv, tri = [], [], [], []
    for n, quad in faces:
        b = len(pos)
        for k, q in enumerate(quad):
            pos.append(c[q])
            nrm.append(n)
            uv.append(((0, 1), (0, 0), (1, 0), (1, 1))[k])
        tri += [(b, b + 1, b + 2), (b, b + 2, b + 3)]
    return pos, nrm, uv, tri


def _blade_picture(w: int = 64, h: int = 256) -> bytes:
    """Polished steel with a dark fuller down the middle and an icy edge (PNG bytes)."""
    rows = []
    for y in range(h):
        row = bytearray()
        for x in range(w):
            d = abs(x - w / 2) / (w / 2)
            base = 170 + int(50 * (1 - d)) - (y * 30) // h
            if d < 0.12:
                r = g = b = base - 70                    # the fuller
            elif d > 0.85:
                r, g, b = base - 20, base + 10, min(255, base + 50)   # the edge
            else:
                r = g = b = base
            row += bytes((max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)), 255))
        rows.append(bytes(row))
    return png.encode(png.Image(w, h, b"".join(rows)), "RGBA")


def sample_sword_glb() -> bytes:
    """The sample sword as ``.glb`` bytes (module docstring)."""
    b = GlbBuilder("dr2kit sample sword")
    img = b.add("images", {"bufferView": b.view(_blade_picture()), "mimeType": "image/png"})
    tex = b.add("textures", {"source": img})
    mats = {
        "steel": b.add("materials", {"name": "steel", "pbrMetallicRoughness": {
            "baseColorTexture": {"index": tex}, "metallicFactor": 0.8}}),
        "gold": b.add("materials", {"name": "gold", "pbrMetallicRoughness": {
            "baseColorFactor": [0.85, 0.65, 0.2, 1.0], "metallicFactor": 1.0}}),
        "leather": b.add("materials", {"name": "leather", "pbrMetallicRoughness": {
            "baseColorFactor": [0.32, 0.18, 0.1, 1.0], "metallicFactor": 0.0}}),
    }
    parts = [  # (name, material, box): grip centred on the origin
        ("blade", "steel", _box(-0.025, 0.025, 0.12, 0.88, -0.004, 0.004, top_scale=0.05)),
        ("guard", "gold", _box(-0.09, 0.09, 0.09, 0.12, -0.018, 0.018)),
        ("grip", "leather", _box(-0.016, 0.016, -0.11, 0.09, -0.016, 0.016)),
        ("pommel", "gold", _box(-0.026, 0.026, -0.17, -0.11, -0.022, 0.022)),
    ]
    for name, mat, (pos, nrm, uv, tri) in parts:
        prim = {"attributes": {
            "POSITION": b.accessor(pos, "VEC3", FLOAT, minmax=True),
            "NORMAL": b.accessor(nrm, "VEC3", FLOAT),
            "TEXCOORD_0": b.accessor(uv, "VEC2", FLOAT)},
            "indices": b.accessor([i for t in tri for i in t], "SCALAR", UINT,
                                  target=ELEMENT_ARRAY_BUFFER),
            "material": mats[mat]}
        mesh = b.add("meshes", {"name": name, "primitives": [prim]})
        node = b.add("nodes", {"name": name, "mesh": mesh})
        b.gltf["scenes"][0]["nodes"].append(node)
    return b.to_bytes()



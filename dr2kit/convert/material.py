"""Bake the colour of materials whose colour comes from shader constants.

Why: zombie clothing (and some other clothing) doesn't store its colour in a texture.
Its ``_cm1`` texture is a **weight map** and the colours are shader constants in the
material's value set (`dr2kit.formats.shader`). Shown as a plain colour map, the
clothes come out red, green and purple. This module computes what the game's pixel
shader computes before lighting, and gives a normal colour texture for previews and
Blender (`convert.gltf.model_to_glb`'s ``base_colour`` hook).

Formulas, read from the pixel shaders translated with XenosRecomp (docs/formats.md
§Materials: value sets; ``21b5af40.po`` zombie cloth, ``8a1baf60.po`` NPC cloth,
``6608df60.po`` LOD zombies). ``d`` is the diffuse texture (``_cm*``) sampled at the
transformed UV, ``m`` the ``_mask`` texture at the mesh UV; the shader squares texture
values (a cheap sRGB → linear), and so does the bake; the result goes back with a
square root:

* **Pattern** (``gBaseTextureColour``, ``gPattern1-3Colour``):
  ``linear = Σ colourᵢ.rgb × weightᵢ × dᵢ²`` over (base, pattern 1, 2, 3) and the
  channels (R, G, B, A) of ``d``. ``weightᵢ`` is the colour's 4th value (zombie
  variant) or ``gBaseTextureScale`` / ``gPatternNScale`` (NPC variant). Weight UV:
  ``((u + so.z) × so.x, (v + so.w) × so.y)`` with ``so = gUVScaleOffset``, or
  ``((u + gUVOffset.x) × gUVScale.x, …)``. Blood (zombie variant, ``gBloodColour``):
  ``a = m.A² × m.B² × gPackedBumpAmbBloodvis.z``;
  ``linear += a × blood.w × (a × blood.rgb × linear − linear)``.
* **Body part** (``gBodyPart1-4Colour``, LOD zombies): by ``d.A``: above 0.875 none
  (white), (0.75, 0.875] part 1, (0.625, 0.75] part 2, (0.5, 0.625] part 3, ≤ 0.5
  part 4; ``linear = d.rgb² × colour``.

* **Channel** (``gRedChannelColour``, green, blue, ``gDiffuseTint``, with a
  saturation each; ``2fbf2f00.po``, Sharon's zombie dress): each colour is first
  desaturated, ``c' = lum + (c − lum) × saturation`` (lum with weights 0.2125, 0.7154,
  0.0721), then layered: start from ``a² × tint``, blend towards ``g² × green'`` by
  ``g² × green.w``, then towards ``b² × blue'`` by ``b² × blue.w``, then towards
  ``r² × red'`` by ``r² × red.w`` (``d`` sampled at the mesh UV).

* **Lens** (``gLensColour``, ``ProtoSkinnedLens``, ``1595db80.po``: glasses frames and
  lenses): ``t`` is the texture, which is *not* a colour (cyan/blue/green channels);
  ``linear = 1.4 × t.b² × gLensColour.rgb`` (before lighting and the environment
  reflection the shader adds), opacity ``= t.g² × gLensColour.a``. The bake keeps that
  opacity in alpha; the export marks the material as blended.

* **Hair** (``gDiffuseColourControl``, ``ProtoSkinnedHair``, ``ca7f0160.po``: eyelashes,
  some hair): the texture's red channel is a weight, not a colour (Katey's lashes are
  pure red in the file); ``linear = t.r² × gDiffuseColourControl.rgb``, opacity
  ``= t.a × gHairTransparencyScale``. (``ProtoSkinnedHairRGB`` uses its texture's colour.)

**Which colour maps are see-through** (`alpha_mode`, measured 2026-10-09 over every
model's colour maps in both games, docs/formats.md §Texture conventions): shaders with
an ``OM`` (opacity map) part in their name (``CM_OM_LM``, ``LIT_CM_OM_RMX``: foliage,
fences, decals; 65-97% see-through texels) and the hair shaders (``ProtoSkinnedHair*``,
``ZombieHair*``: hair, eyelashes) use alpha as transparency. On cloth and skin shaders
(``ProtoSkinnedCloth``, ``ZombieCloth``…: 85-97% "see-through" texels on clothes that
are drawn solid) and ``ZombieDiffuse`` (far-away zombies: alpha picks the body part)
alpha is something else, so they are opaque.

Needs numpy; without it `bake` returns None and the export uses the plain texture.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..container.vpath import AssetTree
from ..errors import Dr2Error
from ..formats.shader import ValueSet, constant_table
from .png import Image

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

MAX_BAKE = 1024          # longest side of a baked texture
PATTERN = ("gBaseTextureColour", "gPattern1Colour", "gPattern2Colour", "gPattern3Colour")
PATTERN_SCALE = ("gBaseTextureScale", "gPattern1Scale", "gPattern2Scale", "gPattern3Scale")
BODY = ("gBodyPart1Colour", "gBodyPart2Colour", "gBodyPart3Colour", "gBodyPart4Colour")
LUMA = (0.2125, 0.7154, 0.0721)    # the shaders' luminance weights (literal c255.xyz)
LENS_GAIN = 1.4                    # the lens shader's literal c255.w
ALPHA_CUTOFF = 0.5                 # alpha-tested materials: see-through below this


def alpha_mode(shader_name: str) -> str:
    """``"MASK"`` when a shader uses its colour map's alpha as transparency (opacity-map
    shaders and hair), else ``"OPAQUE"`` (see the module docstring for the measurement)."""
    name = shader_name or ""
    if "Hair" in name and "LOD2" not in name:
        return "MASK"
    return "MASK" if "OM" in name.split("_") else "OPAQUE"


def material_shaders(scene) -> dict[int, set[str]]:
    """Material index → names of the shaders its draws use."""
    out: dict[int, set[str]] = {}
    for m in scene.meshes:
        for d in m.draws:
            if d.material >= 0:
                out.setdefault(d.material, set()).add(scene.shaders.get(d.shader, ""))
    return out


class ShaderLibrary:
    """Pixel-shader constant tables of one game, by shader hash (read on demand)."""

    def __init__(self, tree: AssetTree):
        self.tree = tree
        self._index: dict[int, tuple[str, str]] | None = None
        self._tables: dict[int, dict] = {}

    def _scan(self) -> dict[int, tuple[str, str]]:
        if self._index is None:
            self._index = {}
            folder = self.tree.root / "data" / "shaders"
            for f in sorted(folder.glob("*-ps.big")) if folder.is_dir() else []:
                vp = f"data/shaders/{f.name}"
                for e in self.tree.open_archive(vp).entries:
                    if e.name.lower().endswith(".po"):
                        try:
                            self._index.setdefault(int(e.name[:-3], 16), (vp, e.name))
                        except ValueError:
                            pass
        return self._index

    def table(self, shader: int) -> dict | None:
        if shader not in self._tables:
            where = self._scan().get(shader)
            if where is None:
                return None
            self._tables[shader] = constant_table(
                self.tree.resolve(f"{where[0]}/{where[1]}").data(), where[1])
        return self._tables[shader]


@dataclass
class Recipe:
    """What a material needs baked: the family, its named constants, and textures."""
    family: str                      # "pattern", "bodypart" or "channel"
    values: dict
    diffuse: str                     # texture name sampled as d
    mask: str | None


def recipe(scene, material, shaders: ShaderLibrary) -> Recipe | None:
    """The bake recipe of ``material``, or None when its colour map is a real colour."""
    if material.valueset in (0, 0xFFFFFFFF) or scene.archive is None:
        return None
    vsets = next((e for e in scene.archive.entries if e.name.lower() == "valuesets.big"), None)
    if vsets is None:
        return None
    from ..container.big import BigArchive
    try:
        arc = BigArchive.parse(vsets.data(), "valuesets.big")
        entry = next((e for e in arc.entries
                      if e.name.lower() == f"{material.valueset:08x}.scv"), None)
        if entry is None:
            return None
        vs = ValueSet.parse(entry.data(), entry.name)
        table = shaders.table(vs.pixel_shader)
    except Dr2Error:
        return None
    if table is None:
        return None
    values = vs.named(table)
    diffuse = material.texture("colour")
    mask = material.texture("mask")
    if diffuse is None:
        return None
    if PATTERN[0] in values:
        return Recipe("pattern", values, diffuse, mask)
    if BODY[0] in values:
        return Recipe("bodypart", values, diffuse, mask)
    if "gRedChannelColour" in values and "gDiffuseTint" in values:
        return Recipe("channel", values, diffuse, mask)
    if "gLensColour" in values:
        return Recipe("lens", values, diffuse, mask)
    if "gDiffuseColourControl" in values:
        return Recipe("hair", values, diffuse, mask)
    return None


def _array(img: Image):
    return np.frombuffer(img.rgba, np.uint8).reshape(img.height, img.width, 4) / 255.0


def _sample(a, u, v):
    """Nearest sample of image ``a`` at UV grids ``u``, ``v`` with wrapping."""
    h, w = a.shape[:2]
    x = np.floor(np.mod(u, 1.0) * w).astype(int) % w
    y = np.floor(np.mod(v, 1.0) * h).astype(int) % h
    return a[y, x]


def bake(rec: Recipe, image) -> Image | None:
    """The baked colour texture. ``image(name)`` → `png.Image` or None."""
    if np is None:
        return None
    d_img = image(rec.diffuse)
    if d_img is None:
        return None
    m_img = image(rec.mask) if rec.mask else None
    d = _array(d_img)
    v = rec.values
    # weight-texture UV transform (identity for most materials)
    if "gUVScaleOffset" in v:
        sx, sy, ox, oy = (list(v["gUVScaleOffset"]) + [1, 1, 0, 0][len(v["gUVScaleOffset"]):])[:4]
    else:
        sx, sy = (list(v.get("gUVScale", (1.0, 1.0))) + [1.0, 1.0])[:2]
        ox, oy = (list(v.get("gUVOffset", (0.0, 0.0))) + [0.0, 0.0])[:2]
    ref = m_img or d_img
    w, h = ref.width, ref.height
    if (sx, sy) != (1.0, 1.0):
        w, h = max(w, d_img.width * min(8, max(1, round(abs(sx))))), \
               max(h, d_img.height * min(8, max(1, round(abs(sy)))))
    k = max(w, h) / MAX_BAKE
    if k > 1:
        w, h = max(1, int(w / k)), max(1, int(h / k))
    u, vv = np.meshgrid((np.arange(w) + 0.5) / w, (np.arange(h) + 0.5) / h)
    if (sx, sy, ox, oy) == (1.0, 1.0, 0.0, 0.0) and (w, h) == (d_img.width, d_img.height):
        ds = d
    else:
        ds = _sample(d, (u + ox) * sx, (vv + oy) * sy)
    if rec.family == "pattern":
        lin = np.zeros((h, w, 3))
        for c, (cname, sname) in enumerate(zip(PATTERN, PATTERN_SCALE)):
            col = list(v.get(cname, (0.0, 0.0, 0.0)))
            weight = v[sname][0] if sname in v else (col[3] if len(col) > 3 else 1.0)
            lin += np.asarray(col[:3]) * weight * (ds[..., c:c + 1] ** 2)
        if "gBloodColour" in v and m_img is not None:
            m = _sample(_array(m_img), u, vv) if (w, h) != (m_img.width, m_img.height) \
                else _array(m_img)
            vis = v.get("gPackedBumpAmbBloodvis", (0, 0, 1.0))
            amount = (m[..., 3:4] ** 2) * (m[..., 2:3] ** 2) * (vis[2] if len(vis) > 2 else 1.0)
            blood = list(v["gBloodColour"]) + [1.0]
            lin = lin + amount * blood[3] * (amount * np.asarray(blood[:3]) * lin - lin)
    elif rec.family == "lens":
        lens = (list(v["gLensColour"]) + [1.0, 1.0, 1.0, 1.0])[:4]
        lin = LENS_GAIN * (ds[..., 2:3] ** 2) * np.asarray(lens[:3])
        alpha = np.clip((ds[..., 1:2] ** 2) * lens[3], 0.0, 1.0)
        out = np.sqrt(np.clip(lin, 0.0, 1.0))
        rgba = np.concatenate([out, alpha], axis=2)
        return Image(w, h, (rgba * 255.0 + 0.5).astype(np.uint8).tobytes())
    elif rec.family == "hair":
        tint = (list(v["gDiffuseColourControl"]) + [1.0, 1.0, 1.0])[:3]
        scale = v.get("gHairTransparencyScale", (1.0,))[0]
        lin = (ds[..., 0:1] ** 2) * np.asarray(tint)
        alpha = np.clip(ds[..., 3:4] * scale, 0.0, 1.0)
        out = np.sqrt(np.clip(lin, 0.0, 1.0))
        rgba = np.concatenate([out, alpha], axis=2)
        return Image(w, h, (rgba * 255.0 + 0.5).astype(np.uint8).tobytes())
    elif rec.family == "channel":
        def adjusted(name):
            c = list(v.get(name + "Colour", (0.0, 0.0, 0.0, 0.0))) + [0.0]
            rgb = np.asarray(c[:3])
            lum = float(np.dot(rgb, LUMA))
            sat = v.get(name + "Saturation", (1.0,))[0]
            return lum + (rgb - lum) * sat, c[3]
        lin = (ds[..., 3:4] ** 2) * np.asarray(list(v["gDiffuseTint"])[:3])
        for ch, name in ((1, "gGreenChannel"), (2, "gBlueChannel"), (0, "gRedChannel")):
            col, wgt = adjusted(name)
            x = ds[..., ch:ch + 1] ** 2
            t = x * wgt
            lin = lin * (1 - t) + x * col * t
    else:
        a = ds[..., 3]
        part = np.ones((h, w, 3))
        for lo, hi, name in ((0.75, 0.875, BODY[0]), (0.625, 0.75, BODY[1]),
                             (0.5, 0.625, BODY[2]), (-1.0, 0.5, BODY[3])):
            sel = (a > lo) & (a <= hi)
            part[sel] = np.asarray(list(v.get(name, (1.0, 1.0, 1.0)))[:3])
        lin = (ds[..., :3] ** 2) * part
    out = np.sqrt(np.clip(lin, 0.0, 1.0))
    rgba = np.concatenate([out, np.ones((h, w, 1))], axis=2)
    return Image(w, h, (rgba * 255.0 + 0.5).astype(np.uint8).tobytes())

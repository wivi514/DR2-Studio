"""Textures from Substance Painter, Blender or any program → the game textures they replace.

Why: texturing programs export one file per texture set and channel
(``00_young_cr_shirt_cm_BaseColor.png``, ``…_Normal.png``), at their own size, with
their own conventions; a mod needs one PNG per *game* texture, at the game's size, named
after its virtual path. Doing that by hand is where texture mods go wrong. `plan`
works out, for each exported file, which texture of the model it replaces, and `apply`
writes the PNGs into the mod, ready for the build (docs/modding/14-texturing-tools.md).

How a file is matched (first rule that applies):

1. **Its name is a game texture's name** (``young_cr_shirt_cm.png``): that texture.
2. **Painter / Blender style** ``<texture set>_<channel>``: the texture set is a
   material of the model, the name our ``.glb`` export gives it (``00_young_cr_shirt_cm``:
   material number + its colour texture), or just the number (``00``) or the colour
   texture's name, possibly after a prefix (Painter's default ``$mesh_$textureSet_…``
   puts the mesh name first); the channel picks the material's slot by role:

   ========================================  ===================================
   channel words                             goes to
   ========================================  ===================================
   BaseColor, Base_Color, Diffuse, Albedo,   the colour map (``_cm``)
   Color, Colour
   Normal, Normal_OpenGL, NormalGL           the normal map (``_nm``)
   Normal_DirectX, NormalDX                  the normal map, green flipped
   Specular, Spec                            the specular map (``_sm``)
   Metallic, Metalness (with a BaseColor)    used to make colour + specular (below)
   Roughness, Glossiness, Height, AO, …      nothing: DR2 has no such map (named)
   ========================================  ===================================

What `apply` does to each picture (measured rules, docs/formats.md §Texture conventions):

* **Size**: resized to the game texture's size (same aspect ratio required): the
  game's sizes are fixed (v1 rule), and programs export at 2048 by default.
* **Normal maps**: DR2's are OpenGL-style (green up; ~90 % of character normal maps by
  an integrability test, matching the tangent analysis). The green direction of the
  file is measured the same way and compared with the original's; if they disagree,
  green is flipped. A ``…DirectX`` name flips it too.
* **Metal/roughness exports** (BaseColor + Metallic, no Specular): DR2 is a
  diffuse + specular engine, so the colour map becomes ``BaseColor × (1 − metallic)``
  and the specular map ``mix(0.04, BaseColor, metallic)`` (the standard conversion).
* **Alpha**: kept for colour maps stored as DXT5 (hair, eyelashes use it); a DXT1
  target keeps only on/off alpha, and a note says so.

Sources: PNG files always; JPEG/TGA/TIFF when Pillow is installed; a ``.glb`` (from
Blender) gives the images its materials use (base colour, normal).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..convert import png
from ..convert.model import TextureFinder, read_scene
from ..errors import Dr2Error
from ..formats.bct import Bct
from .manifest import REPLACE_DIR

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

CHANNELS = {
    "colour": ("basecolor", "base_color", "diffuse", "albedo", "color", "colour", "cm"),
    "normal": ("normal_opengl", "normalgl", "normal_gl", "normal", "nm"),
    "normal-dx": ("normal_directx", "normaldx", "normal_dx"),
    "specular": ("specular", "spec", "sm"),
    "metallic": ("metallic", "metalness", "metal"),
}
IGNORED = ("roughness", "glossiness", "gloss", "height", "ao", "ambientocclusion",
           "ambient_occlusion", "mixed_ao", "emissive", "displacement", "opacity",
           "occlusionroughnessmetallic", "orm")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff")


@dataclass
class TextureItem:
    """One game texture that gets a new picture."""
    texture: str              # game texture name (young_cr_shirt_cm)
    vpath: str                # where it lives
    role: str                 # colour / normal / specular
    size: tuple[int, int]     # the game texture's width, height
    fmt: str                  # DXT1 / DXT5 / DXN …
    source: str               # the file (or file + image) it comes from
    image: object = None      # png.Image, loaded
    flip_green: bool = False
    derived: str = ""         # "from BaseColor + Metallic"
    notes: list[str] = field(default_factory=list)


@dataclass
class TexturePlan:
    model: str
    items: list[TextureItem] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)   # (file, why)

    def report(self) -> str:
        lines = [f"textures for {self.model}:"]
        for it in self.items:
            extra = "; ".join(([it.derived] if it.derived else []) + it.notes)
            lines.append(f"  {it.role:<8} {it.texture:<32} ← {it.source}"
                         + (f"  ({extra})" if extra else ""))
        for f, why in self.skipped:
            lines.append(f"  skipped  {f}: {why}")
        if not self.items:
            lines.append("  nothing matched (see docs/modding/14-texturing-tools.md for the names)")
        return "\n".join(lines)


def load_image(data: bytes, name: str) -> png.Image:
    """Any picture as RGBA (PNG always; other formats need Pillow)."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return png.decode(data)
    try:
        from PIL import Image
    except ImportError:
        raise Dr2Error(f"{name}: not a PNG; save it as PNG, or install Pillow to read "
                       f"JPEG/TGA/TIFF") from None
    with Image.open(io.BytesIO(data)) as im:
        im = im.convert("RGBA")
        return png.Image(im.width, im.height, im.tobytes())


def resize(img: png.Image, w: int, h: int) -> png.Image:
    """``img`` at ``w``×``h`` (Pillow's Lanczos if present, else area/bilinear)."""
    if (img.width, img.height) == (w, h):
        return img
    try:
        from PIL import Image
        im = Image.frombytes("RGBA", (img.width, img.height), img.rgba)
        return png.Image(w, h, im.resize((w, h), Image.LANCZOS).tobytes())
    except ImportError:
        pass
    if np is None:
        raise Dr2Error("resizing a picture needs numpy or Pillow (pip install numpy)")
    a = np.frombuffer(img.rgba, np.uint8).reshape(img.height, img.width, 4).astype(np.float32)
    if img.width % w == 0 and img.height % h == 0:          # exact factor: area average
        fy, fx = img.height // h, img.width // w
        out = a.reshape(h, fy, w, fx, 4).mean(axis=(1, 3))
    else:                                                    # bilinear
        ys = (np.arange(h) + 0.5) * img.height / h - 0.5
        xs = (np.arange(w) + 0.5) * img.width / w - 0.5
        y0 = np.clip(np.floor(ys).astype(int), 0, img.height - 1)
        x0 = np.clip(np.floor(xs).astype(int), 0, img.width - 1)
        y1, x1 = np.minimum(y0 + 1, img.height - 1), np.minimum(x0 + 1, img.width - 1)
        wy, wx = (ys - y0)[:, None, None], (xs - x0)[None, :, None]
        out = (a[y0][:, x0] * (1 - wy) * (1 - wx) + a[y0][:, x1] * (1 - wy) * wx
               + a[y1][:, x0] * wy * (1 - wx) + a[y1][:, x1] * wy * wx)
    return png.Image(w, h, np.clip(out + 0.5, 0, 255).astype(np.uint8).tobytes())


def green_convention(img: png.Image) -> float:
    """> 0: DirectX-style (green down), < 0: OpenGL-style (green up), ~0: unclear.

    A normal map comes from a height field, so its slopes must be consistent: the
    change of x-slope going down the rows equals the change of y-slope going across,
    with one sign for each convention (the correlation of the two is returned)."""
    if np is None:
        return 0.0
    a = np.frombuffer(img.rgba, np.uint8).reshape(img.height, img.width, 4)[..., :2]
    a = a.astype(np.float64) / 255 * 2 - 1
    nx, ny = a[..., 0], a[..., 1]
    nz = np.sqrt(np.clip(1 - nx ** 2 - ny ** 2, 0.05, 1))
    p, q = nx / nz, ny / nz
    if p.shape[0] < 3 or p.shape[1] < 3:
        return 0.0
    x = ((p[2:, 1:-1] - p[:-2, 1:-1]) / 2).ravel()
    y = ((q[1:-1, 2:] - q[1:-1, :-2]) / 2).ravel()
    if x.std() < 1e-6 or y.std() < 1e-6:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def _split(stem: str) -> tuple[str, str] | None:
    """``"00_young_cr_shirt_cm_BaseColor"`` → (texture set, channel role or "ignored")."""
    low = stem.lower()
    for role, words in list(CHANNELS.items()) + [("ignored", IGNORED)]:
        for w in sorted(words, key=len, reverse=True):
            for sep in ("_", "-", " ", "."):
                if low.endswith(sep + w):
                    return stem[:-(len(w) + 1)], role
    return None


def _images_from_glb(data: bytes, name: str) -> list[tuple[str, bytes]]:
    """``(<material>_<channel>, image bytes)`` for the images a ``.glb``'s materials use."""
    from ..convert.gltf import Glb
    glb = Glb.parse(data, name)
    g = glb.gltf
    out = []

    def image(tex_index):
        img = g["images"][g["textures"][tex_index]["source"]]
        view = g["bufferViews"][img["bufferView"]]
        off = view.get("byteOffset", 0)
        return glb.bin[off:off + view["byteLength"]]

    for m in g.get("materials", []):
        pbr = m.get("pbrMetallicRoughness", {})
        if "baseColorTexture" in pbr:
            out.append((f"{m.get('name', '')}_BaseColor", image(pbr["baseColorTexture"]["index"])))
        if "normalTexture" in m:
            out.append((f"{m.get('name', '')}_Normal", image(m["normalTexture"]["index"])))
    return out


def plan(tree, model_vpath: str, sources: list[str | Path], game: str | None = None) -> TexturePlan:
    """Match pictures (files, folders, or a ``.glb``) to the model's textures."""
    scene = read_scene(tree, model_vpath)
    finder = TextureFinder(tree, scene.source, game)
    tp = TexturePlan(scene.source)
    names = {s.name.lower(): s.name for m in scene.materials for s in m.slots if not s.engine}
    by_set: dict[str, object] = {}
    for i, m in enumerate(scene.materials):
        colour = m.texture("colour")
        for key in (f"{i:02d}_{colour or 'material'}", f"{i:02d}", str(i), colour or ""):
            if key:
                by_set.setdefault(key.lower(), m)

    files: list[tuple[str, bytes]] = []           # (stem, bytes); label for the report
    labels: dict[str, str] = {}
    for src in sources:
        p = Path(src)
        found = sorted(p.iterdir()) if p.is_dir() else [p]
        for f in found:
            if f.suffix.lower() == ".glb":
                for stem, data in _images_from_glb(f.read_bytes(), f.name):
                    files.append((stem, data))
                    labels[stem] = f"{f.name}: {stem}"
            elif f.suffix.lower() in IMAGE_EXTS and f.is_file():
                files.append((f.stem, f.read_bytes()))
                labels[f.stem] = f.name

    groups: dict[object, dict[str, tuple[str, bytes]]] = {}
    for stem, data in files:
        if stem.lower() in names:                                  # rule 1
            tname = names[stem.lower()]
            from ..formats.scene import texture_role
            _add(tp, finder, tname, texture_role(tname), labels[stem], data, stem)
            continue
        split = _split(stem)                                       # rule 2
        if split is None:
            tp.skipped.append((labels[stem], "neither a texture of this model nor "
                                             "<texture set>_<channel>"))
            continue
        tset, role = split
        if role == "ignored":
            tp.skipped.append((labels[stem], "DR2 has no map for this channel"))
            continue
        mat = by_set.get(tset.lower())
        if mat is None:            # Painter's default names start with the mesh name:
            low = tset.lower()     # chest_young_chuck_00_young_cr_shirt_cm → 00_young…
            ends = [k for k in by_set if low.endswith("_" + k) or low.endswith("-" + k)]
            if ends:
                mat = by_set[max(ends, key=len)]
        if mat is None:
            tp.skipped.append((labels[stem], f"no material of this model is called "
                                             f"{tset!r} (texture sets: "
                                             f"{', '.join(sorted(k for k in by_set if '_' in k))})"))
            continue
        groups.setdefault(id(mat), {"_mat": mat})[role] = (labels[stem], data)

    for g in groups.values():
        mat = g.pop("_mat")
        if "metallic" in g and "colour" in g and "specular" not in g:
            _metal_rough(tp, finder, mat, g)
            continue
        if "metallic" in g:
            tp.skipped.append((g["metallic"][0], "Metallic without BaseColor: nothing to "
                                                 "convert"))
        for role, (label, data) in g.items():
            if role == "metallic":
                continue
            base_role = "normal" if role == "normal-dx" else role
            tname = mat.texture(base_role)
            if tname is None:
                tp.skipped.append((label, f"this material has no {base_role} map"))
                continue
            _add(tp, finder, tname, base_role, label, data, label,
                 directx=(role == "normal-dx"))
    return tp


def _add(tp, finder, tname, role, label, data, stem, directx=False, image=None,
         derived="") -> TextureItem | None:
    hit = finder.bct(tname)
    if hit is None:
        tp.skipped.append((label, f"texture {tname} not found (build the index)"))
        return None
    vpath, raw = hit
    tex = Bct.parse(raw, vpath)
    h = tex.header
    size = (h.width * h.faces, h.height)
    try:
        img = image or load_image(data, label)
    except Dr2Error as e:
        tp.skipped.append((label, str(e)))
        return None
    item = TextureItem(tname, vpath, role, size, tex.format.name, label, img, directx, derived)
    if img.width * size[1] != img.height * size[0]:
        tp.skipped.append((label, f"{img.width}×{img.height} doesn't have the shape of "
                                  f"{tname} ({size[0]}×{size[1]})"))
        return None
    if (img.width, img.height) != size:
        item.notes.append(f"resized {img.width}×{img.height} → {size[0]}×{size[1]}")
    if role == "normal":
        from ..convert.texture import to_image
        theirs, ours = green_convention(resize(img, *size)), green_convention(to_image(tex))
        if not directx and theirs * ours < 0 and abs(theirs) > 0.2 and abs(ours) > 0.2:
            item.flip_green = True
            item.notes.append("green flipped to match the game (your file is "
                              + ("DirectX" if theirs > 0 else "OpenGL") + "-style)")
        elif directx:
            item.notes.append("green flipped (DirectX → OpenGL, as the game uses)")
    if role == "colour" and tex.format.name == "DXT1" and np is not None:
        a = np.frombuffer(img.rgba, np.uint8)[3::4]
        if a.min() < 250 and len(np.unique(a)) > 2:
            item.notes.append("soft alpha can't be kept: this texture is DXT1 (on/off alpha "
                              "at most)")
    tp.items = [x for x in tp.items if x.vpath != vpath] + [item]
    return item


def _metal_rough(tp, finder, mat, g) -> None:
    """BaseColor + Metallic → DR2's colour map and specular map."""
    if np is None:
        tp.skipped.append((g["colour"][0], "converting metal/roughness needs numpy"))
        return
    label_c, data_c = g["colour"]
    label_m, data_m = g["metallic"]
    try:
        base, metal = load_image(data_c, label_c), load_image(data_m, label_m)
    except Dr2Error as e:
        tp.skipped.append((label_c, str(e)))
        return
    if (metal.width, metal.height) != (base.width, base.height):
        metal = resize(metal, base.width, base.height)
    b = np.frombuffer(base.rgba, np.uint8).reshape(-1, 4).astype(np.float32) / 255
    m = np.frombuffer(metal.rgba, np.uint8).reshape(-1, 4)[:, :1].astype(np.float32) / 255
    diffuse = b.copy()
    diffuse[:, :3] = b[:, :3] * (1 - m)
    spec = np.ones_like(b)
    spec[:, :3] = 0.04 * (1 - m) + b[:, :3] * m

    def img(arr):
        return png.Image(base.width, base.height,
                         (np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())
    how = "from BaseColor + Metallic (metal/roughness → diffuse/specular)"
    for role, arr in (("colour", diffuse), ("specular", spec)):
        tname = mat.texture(role)
        if tname is None:
            tp.skipped.append((label_m, f"this material has no {role} map for the converted "
                                        f"{role}"))
            continue
        _add(tp, finder, tname, role, f"{label_c} + {label_m}", b"", "", image=img(arr),
             derived=how)


def apply(tp: TexturePlan, mod_dir: str | Path) -> list[Path]:
    """Write each matched picture into the mod as ``replace/<texture vpath>.png``."""
    out = []
    for it in tp.items:
        img = resize(it.image, *it.size)
        if it.flip_green:
            px = bytearray(img.rgba)
            px[1::4] = bytes(255 - v for v in px[1::4])
            img = png.Image(img.width, img.height, bytes(px))
        dest = Path(mod_dir) / REPLACE_DIR / (it.vpath + ".png")
        dest.parent.mkdir(parents=True, exist_ok=True)
        png.write(dest, img)
        out.append(dest)
    return out

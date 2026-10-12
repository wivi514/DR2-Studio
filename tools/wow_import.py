"""Bring a model or its particle effects in from World of Warcraft (3.3.5, Wrath of the
Lich King) into a mod, **on your own computer only** (phase 13 steps 6.5 and 8).

Why: the user asked to "grab the effects of WoW and put them in" (Frostmourne's frost
mist on a DR2 sword). WoW's files are Blizzard's, so this is a **local tool**: it reads
your own install, writes into a mod marked ``local_only = true``, and such a mod can't be
shared (`mods.library.pack` refuses it; LICENSE, phase 13 decision 3). It is not part of
DR2 Studio; guide 22 (``docs/modding/22-from-other-games.md``) explains it.

Three commands:

```
python tools/wow_import.py extract "<WoW>/Data" Item\\ObjectComponents\\Weapon\\Sword_2H_Frostmourne_D_01.m2 … -o wow/
python tools/wow_import.py model wow/Sword_2H_Frostmourne_D_01.m2 -o frostmourne.glb
python tools/wow_import.py effect wow/Sword_2H_Frostmourne_D_01.m2 <mod> -g cz [--length 1.1]
```

* ``extract`` reads files out of the MPQ archives (needs ``pip install mpyq``; patches
  win over the base archives, as in the game). ``model`` and ``effect`` also find a
  missing ``.skin`` / ``.blp`` there with ``--wow <Data folder>``.
* ``model``: the ``.m2`` and its ``.skin`` (``<name>00.skin``) → a ``.glb`` (one mesh
  per submesh, each with its texture as a PNG). Give it to the weapon wizard (*New
  weapon…* → *Model file*), which fits any ``.glb`` into the weapon's hands.
* ``effect``: the model's particle emitters → one effect of your own in a free slot of
  the effect table (`mods.neweffect.new_effect`), each WoW emitter one DR2 emitter
  (``layout`` of copies of a base emitter, then its fields), each particle picture a
  picture of your own (`mods.neweffect.new_particle_texture`). Prints the effect's
  number for the wizard's *while held* box.

**How a WoW emitter becomes a DR2 emitter** (WoW's ``M2Particle``, 0x1DC bytes in 3.3.5,
read by `read_m2`; DR2's fields: `dr2kit.formats.effect`, docs/formats.md §Particle
effects): its colour and opacity keys (three, over its life) → the five colour keys;
its lifespan → the colour key times (their last is the life, measured); its rate → how many
particles (``count_20``, measured); its scale keys → the size keys; its place on the
model and its emission area → the emitter's offset and box; gravity → gravity (WoW pulls
down with a positive value, DR2 pushes up); its picture → a picture of your own (alpha
from brightness, since WoW draws these added onto the scene). Lengths are scaled so the
model's length becomes ``--length`` metres (the DR2 weapon's), measured from the model's
lowest point along its length, which is where DR2's weapon effects start. Fields with no
WoW match keep the base emitter's values. The match is approximate: see docs/formats.md
§Particle effects for what each DR2 field was measured to do.
"""

from __future__ import annotations

import argparse
import io
import json
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PARTICLE_SIZE = 0x1DC            # M2Particle in 3.3.5 (version 264)
VERSION_WOTLK = 264


class WowError(Exception):
    """A WoW file this tool can't read (says why)."""


# ---- reading .m2 / .skin ------------------------------------------------------------------

def _arr(b: bytes, at: int) -> tuple[int, int]:
    return struct.unpack_from("<II", b, at)


@dataclass
class Track:
    """A WoW value over time: the first animation's (times, values)."""
    times: list[int]
    values: list

    def first(self, default=0.0):
        return self.values[0] if self.values else default


@dataclass
class Particle:
    """One WoW particle emitter (the fields this tool uses; `read_m2`)."""
    flags: int
    position: tuple[float, float, float]
    bone: int
    texture: str                       # its picture's file in the MPQs ('' if replaceable)
    blend: int                         # 0 opaque, 1 alpha key, 2 alpha, 4 add…
    kind: int                          # 1 plane, 2 sphere, 3 spline
    speed: float
    speed_vary: float
    vertical_range: float
    horizontal_range: float
    gravity: float
    lifespan: float
    rate: float
    area_length: float
    area_width: float
    colours: list[tuple[float, float, float]]     # 0-255, at colour_times
    colour_times: list[float]                     # 0-1 of the life
    alphas: list[float]                           # 0-1
    alpha_times: list[float]
    scales: list[float]                           # model units
    scale_times: list[float]
    drag: float = 0.0
    spin: float = 0.0


@dataclass
class Submesh:
    first: int                          # first index of the skin's triangle list
    count: int
    texture: str


@dataclass
class M2:
    """What this tool reads of an ``.m2`` (3.3.5)."""
    name: str
    vertices: list                      # (position, normal, uv)
    textures: list[tuple[int, str]]
    texture_lookup: list[int]
    particles: list[Particle] = field(default_factory=list)


def read_m2(data: bytes) -> M2:
    """An ``.m2``'s vertices, textures and particle emitters (module docstring)."""
    if data[:4] != b"MD20":
        raise WowError("not an .m2 (MD20) file; a Cataclysm or later MD21 file is not "
                       "supported")
    version = struct.unpack_from("<I", data, 4)[0]
    if version != VERSION_WOTLK:
        raise WowError(f".m2 version {version}: only 3.3.5's ({VERSION_WOTLK}) is known")
    n, o = _arr(data, 0x08)
    name = data[o:o + n].split(b"\0")[0].decode("latin-1")
    nv, ov = _arr(data, 0x3C)
    verts = []
    for i in range(nv):
        at = ov + 48 * i
        p = struct.unpack_from("<3f", data, at)
        nrm = struct.unpack_from("<3f", data, at + 20)
        uv = struct.unpack_from("<2f", data, at + 32)
        verts.append((p, nrm, uv))
    nt, ot = _arr(data, 0x50)
    textures = []
    for i in range(nt):
        kind, _flags, ln, lo = struct.unpack_from("<IIII", data, ot + 16 * i)
        textures.append((kind, data[lo:lo + ln].split(b"\0")[0].decode("latin-1")))
    nl, ol = _arr(data, 0x80)
    lookup = list(struct.unpack_from(f"<{nl}H", data, ol))
    m2 = M2(name, verts, textures, lookup)
    npart, opart = _arr(data, 0x128)
    for i in range(npart):
        m2.particles.append(_particle(data, opart + PARTICLE_SIZE * i, textures))
    return m2


def _track(b: bytes, at: int, fmt: str = "<f") -> Track:
    nts, ots = _arr(b, at + 4)
    nvs, ovs = _arr(b, at + 12)
    if not nvs:
        return Track([], [])
    tc, to = _arr(b, ots)
    vc, vo = _arr(b, ovs)
    size = struct.calcsize(fmt)
    times = list(struct.unpack_from(f"<{tc}I", b, to))
    values = [struct.unpack_from(fmt, b, vo + size * j)[0] for j in range(vc)]
    return Track(times, values)


def _fblock(b: bytes, at: int, fmt: str) -> tuple[list[float], list]:
    nt, ot = _arr(b, at)
    nv, ov = _arr(b, at + 8)
    size = struct.calcsize(fmt)
    times = [t / 32767.0 for t in struct.unpack_from(f"<{nt}h", b, ot)]
    values = [struct.unpack_from(fmt, b, ov + size * j) for j in range(nv)]
    return times, values


def _particle(b: bytes, at: int, textures) -> Particle:
    flags = struct.unpack_from("<I", b, at + 4)[0]
    pos = struct.unpack_from("<3f", b, at + 8)
    bone, tex = struct.unpack_from("<HH", b, at + 0x14)
    blend, kind = struct.unpack_from("<BB", b, at + 0x28)
    o = at + 0x34
    tracks = []
    for _ in range(6):                  # speed, its variation, vertical, horizontal, gravity, life
        tracks.append(_track(b, o).first())
        o += 20
    o += 4                              # lifespan variation
    rate = _track(b, o).first()
    o += 20 + 4                         # rate, rate variation
    length = _track(b, o).first()
    width = _track(b, o + 20).first()
    o += 60                             # length, width, z source
    ct, cv = _fblock(b, o, "<3f")
    at_, av = _fblock(b, o + 16, "<h")
    st, sv = _fblock(b, o + 32, "<2f")
    o += 48 + 8 + 32 + 12 + 8           # + scale variation, head/tail cells, tail/twinkle, twinkle scale
    _burst, drag, _spin0, _spin0v, spin, _spinv = struct.unpack_from("<6f", b, o)
    texture = ""
    if tex < len(textures) and textures[tex][0] == 0:
        texture = textures[tex][1]
    return Particle(flags, pos, bone, texture, blend, kind, *tracks[:5], tracks[5], rate,
                    length, width, [tuple(c) for c in cv], ct,
                    [a[0] / 32767.0 for a in av], at_, [s[0] for s in sv], st, drag, spin)


def read_skin(data: bytes) -> tuple[list[int], list[Submesh], list[tuple[int, int]]]:
    """A ``.skin``: the triangle list (vertex numbers, 3 per triangle), its submeshes,
    and (submesh, texture lookup number) per texture unit."""
    if data[:4] != b"SKIN":
        raise WowError("not a .skin file")
    (ni, oi), (nt, ot), _p, (ns, os_), (nb, ob) = (_arr(data, 4 + 8 * k) for k in range(5))
    look = struct.unpack_from(f"<{ni}H", data, oi)
    tris = [look[i] for i in struct.unpack_from(f"<{nt}H", data, ot)]
    subs = []
    for k in range(ns):
        _id, _lvl, _vs, _vc, istart, icount = struct.unpack_from("<6H", data, os_ + 48 * k)
        subs.append(Submesh(istart, icount, ""))
    units = []
    for k in range(nb):
        u = struct.unpack_from("<BbHHHhHHHH", data, ob + 24 * k)
        units.append((u[3], u[9]))      # skin section, texture combo (lookup) index
    return tris, subs, units


# ---- pictures --------------------------------------------------------------------------

def blp_to_png(data: bytes, particle: bool = False) -> bytes:
    """A ``.blp`` (Pillow reads BLP1/BLP2) as PNG bytes. ``particle``: alpha from the
    brightness and the colour brought to full brightness (WoW adds particles onto the
    scene; DR2 needs the see-through part in the alpha)."""
    from PIL import Image
    import numpy as np
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    if particle:
        a = np.asarray(im).astype(np.float32) / 255
        lum = a[..., :3].max(axis=2)
        if a[..., 3].min() > 0.99:                     # no alpha of its own: additive
            rgb = a[..., :3] / np.maximum(lum[..., None], 1e-3)
            a = np.dstack([np.clip(rgb, 0, 1), lum])
        im = Image.fromarray((a * 255 + 0.5).astype("uint8"), "RGBA")
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


class Source:
    """Finds WoW files: next to the ``.m2`` first, then (with ``wow``) in the MPQs."""

    def __init__(self, near: Path, wow: Path | None = None):
        self.near = near
        self.wow = wow
        self._archives = None

    def _mpqs(self):
        if self._archives is None:
            try:
                import mpyq
            except ImportError:
                raise WowError("reading WoW's MPQ archives needs mpyq (pip install mpyq)") \
                    from None
            files = sorted(self.wow.glob("*.MPQ")) + sorted(self.wow.glob("*/*.MPQ"))
            files.sort(key=lambda p: ("patch" in p.name.lower(), p.name.lower()))
            self._archives = []
            for f in reversed(files):          # patches first: they win
                try:
                    self._archives.append(mpyq.MPQArchive(str(f), listfile=False))
                except Exception:              # noqa: BLE001 (a damaged or odd archive)
                    continue
        return self._archives

    def read(self, wow_path: str) -> bytes:
        name = wow_path.replace("\\", "/").split("/")[-1]
        for cand in (self.near / name, *self.near.glob("*")):
            if cand.is_file() and cand.name.lower() == name.lower():
                return cand.read_bytes()
        if self.wow is not None:
            for a in self._mpqs():
                try:
                    d = a.read_file(wow_path.replace("/", "\\"))
                except Exception:              # noqa: BLE001 (not in this archive)
                    d = None
                if d:
                    return d
        raise WowError(f"{wow_path}: not next to the .m2"
                       + ("" if self.wow else " (give --wow <WoW>/Data to look in the MPQs)"))


# ---- model → .glb ------------------------------------------------------------------------

def skin_texture(m2: M2, override: str | None = None) -> str:
    """The file of a *replaceable* texture (kind 2, an item's own skin, named by the
    game's item tables): ``override``, else ``<model name>.blp`` in the folder of the
    model's other textures (how WoW's weapons are named)."""
    if override:
        return override
    folder = next((p.replace("/", "\\").rsplit("\\", 1)[0] for k, p in m2.textures
                   if k == 0 and "\\" in p.replace("/", "\\")), "")
    return (folder + "\\" if folder else "") + m2.name + ".blp"


def model_glb(m2: M2, skin: bytes, source: Source, texture: str | None = None) -> bytes:
    """The model as a ``.glb``: one mesh per submesh with its texture (module docstring).
    WoW is Z-up; glTF is Y-up, so (x, y, z) → (y, z, x). ``texture``: the file for the
    model's replaceable texture (`skin_texture`)."""
    tris, subs, units = read_skin(skin)
    tex_of = {}
    for sub, combo in units:
        if sub < len(subs) and sub not in tex_of and combo < len(m2.texture_lookup):
            kind, path = m2.textures[m2.texture_lookup[combo]]
            tex_of[sub] = path if kind == 0 else skin_texture(m2, texture) if kind == 2 else ""
    blob = bytearray()
    g = {"asset": {"version": "2.0", "generator": "dr2kit tools/wow_import.py"},
         "scene": 0, "scenes": [{"nodes": []}], "nodes": [], "meshes": [], "materials": [],
         "textures": [], "images": [], "samplers": [{}], "accessors": [], "bufferViews": []}

    def add(data: bytes, **acc) -> int:
        while len(blob) % 4:
            blob.append(0)
        g["bufferViews"].append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)})
        blob.extend(data)
        if not acc:
            return len(g["bufferViews"]) - 1
        g["accessors"].append({"bufferView": len(g["bufferViews"]) - 1, **acc})
        return len(g["accessors"]) - 1

    images = {}
    for k, sub in enumerate(subs):
        idx = tris[sub.first:sub.first + sub.count]
        if not idx:
            continue
        used = sorted(set(idx))
        remap = {v: i for i, v in enumerate(used)}
        P = [(m2.vertices[v][0][1], m2.vertices[v][0][2], m2.vertices[v][0][0]) for v in used]
        N = [(m2.vertices[v][1][1], m2.vertices[v][1][2], m2.vertices[v][1][0]) for v in used]
        T = [m2.vertices[v][2] for v in used]
        lo = [min(p[i] for p in P) for i in range(3)]
        hi = [max(p[i] for p in P) for i in range(3)]
        attrs = {"POSITION": add(struct.pack(f"<{3 * len(P)}f", *sum(P, ())), componentType=5126,
                                 count=len(P), type="VEC3", min=lo, max=hi),
                 "NORMAL": add(struct.pack(f"<{3 * len(N)}f", *sum(N, ())), componentType=5126,
                               count=len(N), type="VEC3"),
                 "TEXCOORD_0": add(struct.pack(f"<{2 * len(T)}f", *sum(T, ())),
                                   componentType=5126, count=len(T), type="VEC2")}
        ind = add(struct.pack(f"<{len(idx)}H", *(remap[v] for v in idx)), componentType=5123,
                  count=len(idx), type="SCALAR")
        prim = {"attributes": attrs, "indices": ind, "mode": 4}
        path = tex_of.get(k, "")
        if path:
            if path not in images:
                try:
                    png = blp_to_png(source.read(path))
                except WowError as e:
                    print(f"  {e}: submesh {k} without a texture")
                    png = None
                if png is not None:
                    g["images"].append({"bufferView": add(png), "mimeType": "image/png",
                                        "name": Path(path.replace("\\", "/")).stem})
                    g["textures"].append({"source": len(g["images"]) - 1, "sampler": 0})
                    g["materials"].append({"name": Path(path.replace("\\", "/")).stem,
                                           "pbrMetallicRoughness": {
                                               "baseColorTexture": {"index": len(g["textures"]) - 1},
                                               "metallicFactor": 0.0}})
                    images[path] = len(g["materials"]) - 1
                else:
                    images[path] = None
            if images[path] is not None:
                prim["material"] = images[path]
        g["meshes"].append({"name": f"{m2.name}_{k}", "primitives": [prim]})
        g["nodes"].append({"name": f"{m2.name}_{k}", "mesh": len(g["meshes"]) - 1})
        g["scenes"][0]["nodes"].append(len(g["nodes"]) - 1)
    for key in ("materials", "textures", "images"):
        if not g[key]:
            del g[key]
    if "textures" not in g:
        del g["samplers"]
    while len(blob) % 4:
        blob.append(0)
    g["buffers"] = [{"byteLength": len(blob)}]
    js = json.dumps(g, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    return (struct.pack("<III", 0x46546C67, 2, 28 + len(js) + len(blob))
            + struct.pack("<II", len(js), 0x4E4F534A) + js
            + struct.pack("<II", len(blob), 0x004E4942) + bytes(blob))


# ---- particles → a DR2 effect -------------------------------------------------------------

def _sample(times: list[float], values: list[float], t: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1 or not times:
        return values[0]
    for k in range(len(times) - 1):
        if times[k] <= t <= times[k + 1]:
            f = (t - times[k]) / max(times[k + 1] - times[k], 1e-9)
            return values[k] + f * (values[k + 1] - values[k])
    return values[0] if t < times[0] else values[-1]


KEY_AT = (0.0, 0.25, 0.5, 0.75, 1.0)          # where DR2's five keys sample a WoW life


def model_frame(m2: M2, length_m: float) -> tuple[int, float, float]:
    """(axis, start, scale): the model's longest axis, its lowest value along it, and the
    factor that makes its length ``length_m`` metres."""
    P = [v[0] for v in m2.vertices]
    span = [max(p[i] for p in P) - min(p[i] for p in P) for i in range(3)]
    axis = span.index(max(span))
    start = min(p[axis] for p in P)
    return axis, start, length_m / max(span[axis], 1e-9)


def emitter_changes(p: Particle, axis: int, start: float, scale: float,
                    picture: str | None) -> dict:
    """The DR2 field values for one WoW emitter (module docstring)."""
    others = [i for i in range(3) if i != axis]
    cols = []
    for t in KEY_AT:
        rgb = [_sample(p.colour_times, [c[i] for c in p.colours], t) / 255.0 for i in range(3)]
        a = _sample(p.alpha_times, p.alphas, t)
        cols += [min(1.0, max(0.0, v)) for v in rgb] + [min(1.0, max(0.0, a))]
    life = max(p.lifespan, 0.05)
    sizes = [max(0.0, _sample(p.scale_times, p.scales, t)) * scale for t in KEY_AT]
    # DR2: y along the weapon (the Flaming Sword's box runs 0 → 0.7 m in y), x / z across
    offset = [(p.position[others[0]]) * scale, (p.position[axis] - start) * scale,
              (p.position[others[1]]) * scale]
    hl, hw = 0.5 * p.area_length * scale, 0.5 * p.area_width * scale
    ch = {"colours": cols,
          "colour_times": [k * life for k in KEY_AT[1:]],
          "sizes": sizes,
          "offset": offset,
          "shape_values": [hl, hw, hw, -hl, -hw, -hw],
          "gravity": [0.0, -p.gravity * scale, 0.0],
          "count_20": max(1, min(30, round(p.rate)))}   # how many particles (measured)
    if picture:
        ch["texture"] = picture
    return ch


BASE_EFFECT = "flamingsword_wpn_c_3_unq"     # its emitters are boxes along the blade
BASE_EMITTER = 0                             # the slow smoke: a steady stream


def import_effect(m2: M2, source: Source, tree, game: str, mod_dir: Path, length_m: float,
                  slot=None, size: float = 1.0) -> tuple[int, list[str]]:
    """Make the model's particle emitters one effect of your own in ``mod_dir`` (module
    docstring), ``size`` × every particle's size. Returns (its number, notes)."""
    from dr2kit.mods import neweffect
    from dr2kit.mods.manifest import Mod
    if not m2.particles:
        raise WowError(f"{m2.name} has no particle emitters")
    mod = Mod.load(mod_dir)
    if not mod.local_only:
        mod.extra["local_only"] = True
        mod.save()
    notes = [f"{mod.id} is now local only (local_only = true): it holds WoW's pictures and "
             f"can't be shared"]
    axis, start, scale = model_frame(m2, length_m)
    pictures: dict[str, str] = {}
    have = {n.lower() for n in _own_pictures(mod_dir)}
    emitters = {}
    for k, p in enumerate(m2.particles):
        pic = None
        if p.texture:
            stem = "wow_" + "".join(c for c in Path(p.texture.replace("\\", "/")).stem.lower()
                                    if c.isalnum() or c == "_")[:24]
            if stem not in pictures:
                if stem not in have:
                    png = mod_dir / "sources" / f"{stem}_wow.png"
                    png.parent.mkdir(parents=True, exist_ok=True)
                    png.write_bytes(blp_to_png(source.read(p.texture), particle=True))
                    neweffect.new_particle_texture(tree, mod_dir, stem, png)
                    png.unlink()
                pictures[stem] = stem
            pic = stem
        else:
            notes.append(f"emitter {k}: its picture is replaceable in WoW; the base's is kept")
        emitters[str(k)] = emitter_changes(p, axis, start, scale, pic)
    changes = {"layout": [BASE_EMITTER] * len(m2.particles), "emitters": emitters}
    if size != 1.0:
        changes["size"] = size
    number, _ = neweffect.new_effect(tree, game, mod_dir, BASE_EFFECT, changes, slot)
    return number, notes


def _own_pictures(mod_dir: Path) -> list[str]:
    folder = mod_dir / "add" / "data" / "models" / "effects.tex"
    return [f.name[:-len(".copy.json")] for f in folder.glob("*.copy.json")] \
        if folder.is_dir() else []


# ---- command line ------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract", help="copy files out of WoW's MPQ archives (needs mpyq)")
    p.add_argument("data", help="WoW's Data folder")
    p.add_argument("files", nargs="+", help="paths inside the archives (Item\\…\\x.m2)")
    p.add_argument("-o", "--out", default=".", help="folder to write them to")
    p = sub.add_parser("model", help=".m2 + .skin → .glb for the weapon wizard")
    p.add_argument("m2")
    p.add_argument("--skin", help="its .skin (default: <name>00.skin next to it)")
    p.add_argument("--wow", help="WoW's Data folder, to find .skin / .blp files in the MPQs")
    p.add_argument("--texture", help="the item's own texture (.blp), when it isn't "
                   "<model name>.blp")
    p.add_argument("-o", "--out", required=True)
    p = sub.add_parser("effect", help="the .m2's particle emitters → an effect of your own")
    p.add_argument("m2")
    p.add_argument("mod", help="the mod folder (made local only)")
    p.add_argument("-g", "--game", required=True, choices=("cz", "cw"))
    p.add_argument("--length", type=float, default=1.1,
                   help="the model's length in metres (the DR2 weapon's; default 1.1)")
    p.add_argument("--slot", help="which free slot (dr2 effects --free)")
    p.add_argument("--size", type=float, default=1.0, help="× every particle's size")
    p.add_argument("--wow", help="WoW's Data folder, to find .blp pictures in the MPQs")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "extract":
            src = Source(Path(a.out), Path(a.data))
            out = Path(a.out)
            out.mkdir(parents=True, exist_ok=True)
            for f in a.files:
                data = src.read(f)
                dest = out / f.replace("\\", "/").split("/")[-1]
                dest.write_bytes(data)
                print(f"wrote {dest} ({len(data)} bytes)")
            return 0
        m2p = Path(a.m2)
        src = Source(m2p.parent, Path(a.wow) if a.wow else None)
        m2 = read_m2(m2p.read_bytes())
        if a.cmd == "model":
            skin = Path(a.skin) if a.skin else m2p.with_name(m2p.stem + "00.skin")
            sk = skin.read_bytes() if skin.is_file() else src.read(skin.name)
            Path(a.out).write_bytes(model_glb(m2, sk, src, a.texture))
            print(f"wrote {a.out}: give it to New weapon… → Model file (.glb)")
            return 0
        from dr2kit.container.vpath import AssetTree
        from dr2kit.profiles import locate
        tree = AssetTree(locate(a.game).root)
        num, notes = import_effect(m2, src, tree, a.game, Path(a.mod), a.length, a.slot,
                                   a.size)
        for n in notes:
            print(n)
        print(f"{len(m2.particles)} emitter(s) → your effect number {num}: choose it in New "
              f"weapon… (while held), or dr2 mod new-weapon … --held {num}")
        return 0
    except (WowError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

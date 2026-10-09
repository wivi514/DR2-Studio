"""Writing scenes back: chunk serialisers, the no-op check, and new geometry for a shape.

Phase 4 puts edited and new models back into the game. A model is a `.big` of chunks
(`dr2kit.formats.scene`), so writing one means rebuilding the chunks that changed and
leaving every other byte alone. This module does three things:

1. **Serialisers**, the inverse of each chunk the reader interprets: command buffers,
   ``RenderStrip`` records, the 72-byte shape chunk, buffer headers. `rewrite_problems`
   rebuilds every one of them from the parsed `Scene` and compares with the stored
   bytes; ``dr2 census --models`` runs it over every scene of both games (the no-op
   gate: zero differences).
2. **Triangles → strip** (`triangles_to_strip`): the games draw one triangle strip per
   draw, joined by repeated indices; `scene.strip_to_triangles` is the reference.
3. **New geometry for a shape** (`replace_mesh`): one `DrawGeometry` per part (already in
   the game's model space, joints as skeleton node indices) becomes vertex streams,
   indices, ``RenderStrip`` records, command packets and bounds. Every new draw copies a
   **template**: an original draw with the same material, whose vertex declaration,
   command packet (shader, textures, render state) and flag words it keeps.

Facts this relies on (docs/formats.md §"Writing scenes", each measured over every scene
of both games):

* ``RenderStrip`` word 5 = the byte offset of the draw's packet in the command buffer;
  word 6 = how many words of the packet come before the end of the draw command (it
  depends only on the packet's shape, so a cloned packet keeps its word 6).
* A command buffer is one packet per draw, in draw order, starting at word 5's offset.
* Shape words: 3 = number of declarations, 5 = number of draws, 6-7 = the first draw's
  palette (start, count); 2 / 4 = own vertex / index buffers. The last 12 bytes vary on a
  few shapes and are kept.
* Bounds: radius = the largest distance of a vertex from the origin; box = the exact
  min / max of the positions (float32).
* Every skinned shape of both games has a single draw. Own-buffer shapes (characters)
  lay their draws out back to back in ``<shape> Vertices k`` / ``Indices 0``; combined
  shapes (props) bind each draw at its first vertex (``0x28``) and first index
  (``0x47``) with zeros in the draw arguments. New combined draws are appended to the
  shared buffers, so other shapes are untouched.
* A draw's palette is at most 61 consecutive nodes (shader constants c8…c190); a part
  that needs more is split into several draws.
"""

from __future__ import annotations

import math
import struct
from collections import defaultdict
from dataclasses import dataclass, field

from ..errors import FormatError
from . import vertex as vx
from .scene import (BUFFER_RECORD, Command, Draw, Mesh, Scene, parse_buffer_header,
                    parse_command_buffer)

MAX_PALETTE = 61            # bones per draw: gWorldMatrix[183] = 61 × 3 rows
MAX_INDEX = 0xFFFF          # 16-bit indices


# --- serialisers ------------------------------------------------------------------------

def command_buffer_bytes(cmds: list[Command]) -> bytes:
    """A ``CommandBuffer`` chunk from its commands (inverse of `parse_command_buffer`)."""
    words = []
    for c in cmds:
        words.append(c.word)
        words.extend(c.args)
    return struct.pack(f">{len(words)}I", *words)


def strip_bytes(records: list[tuple[int, ...]]) -> bytes:
    """A ``RenderStrip`` chunk: 7 words per draw."""
    return b"".join(struct.pack(">7I", *r) for r in records)


def shape_bytes(words, radius: float, bmin, bmax, tail: bytes) -> bytes:
    """The 72-byte shape chunk: 8 words, radius, box min, box max, then ``tail`` (12)."""
    return struct.pack(">8I7f", *words, radius, *bmin, *bmax) + tail


def buffer_record(raw: bytes, count: int, stride: int | None = None) -> bytes:
    """A 56-byte ``VBHeader`` / ``IBHeader`` record with a new count (and stride)."""
    out = bytearray(raw)
    struct.pack_into(">I", out, 0x28, count)
    if stride is not None:
        struct.pack_into(">I", out, 0x2C, stride)
    return bytes(out)


def split_packets(cmds: list[Command], offsets: list[int]) -> list[list[Command]]:
    """A command buffer → one packet per draw, cut at the draws' ``RenderStrip`` word 5
    (the byte offset of each packet). Raises `FormatError` if an offset doesn't fall on
    a command or the packets don't hold one draw command each.

    (Most packets also end with an ``0x04`` word, but 28 shapes of the two games chain
    packets without one, so the offsets are the authority.)"""
    starts, pos = {}, 0
    for i, c in enumerate(cmds):
        starts[pos * 4] = i
        pos += 1 + len(c.args)
    try:
        cuts = [starts[o] for o in offsets] + [len(cmds)]
    except KeyError:
        raise FormatError(f"a RenderStrip packet offset ({offsets}) is not on a command") from None
    if cuts[0] != 0 or any(b <= a for a, b in zip(cuts, cuts[1:])):
        raise FormatError(f"RenderStrip packet offsets {offsets} are not increasing from 0")
    packets = [cmds[a:b] for a, b in zip(cuts, cuts[1:])]
    if any(sum(c.op == 0x08 for c in pk) != 1 for pk in packets):
        raise FormatError("a command packet does not hold exactly one draw")
    return packets


def packet_words(packet: list[Command]) -> int:
    return sum(1 + len(c.args) for c in packet)


def _chunk(arc, name: str):
    for e in arc.entries:
        if e.name.lower() == name.lower():
            return e
    return None


def rewrite_problems(scene: Scene) -> list[str]:
    """Rebuild every chunk the reader interprets from the parsed scene; name each one
    whose bytes differ from the stored chunk. Empty = the writer is exact for this scene.
    """
    out: list[str] = []

    def cmp(arc, name: str, ours: bytes) -> None:
        e = _chunk(arc, name)
        if e is None:
            out.append(f"{name}: missing")
        elif e.data() != ours:
            out.append(f"{name}: rewritten chunk differs")

    a = scene.archive
    cmp(a, "SceneHeader", struct.pack(">5I", *scene.header))
    if _chunk(a, "SceneDescription") is not None:
        cmp(a, "SceneDescription", b"".join(n.encode("latin-1").ljust(32, b"\0")[:32]
                                            + struct.pack(">I", k)
                                            for n, k in scene.description))
    for n in scene.skeleton.nodes:
        cmp(a, n.name, n.to_bytes())
    if scene.hierarchy:
        cmp(a, "_BONEHIERARCHY_", b"".join(struct.pack(">Ii", i, p) for i, p in scene.hierarchy))
    if _chunk(a, "MatArray") is not None:
        cmp(a, "MatArray", b"".join(
            struct.pack(">4I4fI", m.id, m.hash, m.slot_count, m.slot_offset, *m.params,
                        m.valueset) for m in scene.materials))
        slots = _chunk(a, "MatTextureInfoArray")
        if slots is not None:
            buf = bytearray(slots.data())
            for m in scene.materials:
                for k, s in enumerate(m.slots):
                    o = m.slot_offset + k * 100
                    buf[o:o + 100] = s.raw
            cmp(a, "MatTextureInfoArray", bytes(buf))
    p = scene.persistent
    if p is not None:
        for m in scene.meshes:
            shape = _chunk(p, m.name).data()
            cmp(p, m.name, shape_bytes(m.words, m.radius, m.bounds_min, m.bounds_max,
                                       shape[60:]))
            cmp(p, f"{m.name} RenderStrip", strip_bytes([d.strip for d in m.draws]))
            cb = _chunk(p, f"{m.name} CommandBuffer").data()
            cmds = parse_command_buffer(cb)
            cmp(p, f"{m.name} CommandBuffer", command_buffer_bytes(cmds))
            try:
                split_packets(cmds, [d.strip[5] for d in m.draws])
            except FormatError as e:
                out.append(f"{m.name} CommandBuffer: {e}")
            for d in m.draws:
                cmp(p, f"{m.name} D3DVertexDesc {d.declaration_number}",
                    vx.declaration_bytes(d.declaration))
        if p.to_bytes() != _chunk(a, "persistent.big").data():
            out.append("persistent.big: re-written archive differs")
    return out


# --- strips -----------------------------------------------------------------------------

def triangles_to_strip(tris: list[tuple[int, int, int]]) -> list[int]:
    """Counter-clockwise triangles → one strip with the games' winding rule.

    Strip triangle *i* is ``(s[i], s[i+1], s[i+2])`` when *i* is even and
    ``(s[i+1], s[i], s[i+2])`` when odd (`scene.strip_to_triangles`). The builder grows a
    run while some unused triangle continues the last edge with the right parity, then
    joins runs with repeated indices (degenerate triangles), padding one more repeat
    when needed so the next run starts on an even position. Degenerate input triangles
    are dropped.
    """
    tris = [t for t in tris if t[0] != t[1] and t[1] != t[2] and t[0] != t[2]]
    by_edge: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for k, (a, b, c) in enumerate(tris):
        by_edge[(a, b)].append((k, c))
        by_edge[(b, c)].append((k, a))
        by_edge[(c, a)].append((k, b))
    used = [False] * len(tris)

    def take(edge) -> int | None:
        lst = by_edge.get(edge)
        while lst:
            k, third = lst[-1]
            if used[k]:
                lst.pop()
                continue
            used[k] = True
            return third
        return None

    strip: list[int] = []
    for k, (a, b, c) in enumerate(tris):
        if used[k]:
            continue
        used[k] = True
        run = [a, b, c]
        while True:
            i = len(run) - 2                     # index of the next strip triangle
            edge = (run[-2], run[-1]) if i % 2 == 0 else (run[-1], run[-2])
            z = take(edge)
            if z is None:
                break
            run.append(z)
        if strip:
            strip.append(strip[-1])
            strip.append(run[0])
            if len(strip) % 2:
                strip.append(run[0])
        strip.extend(run)
    return strip


# --- new geometry -----------------------------------------------------------------------

@dataclass
class DrawGeometry:
    """New geometry for one part of a shape, in the game's model space (metres, Y up).

    ``joints`` are skeleton node indices (up to 4 per vertex), ``weights`` any
    non-negative numbers (normalised and quantised when written). ``uvs`` holds one list
    per UV set, in the order the declaration's ``TEXCOORD`` elements come (by usage
    index). ``tangents`` are computed from the first UV set when None.
    """
    material: int                                       # index into Scene.materials
    positions: list[tuple[float, float, float]]
    triangles: list[tuple[int, int, int]]
    normals: list[tuple[float, float, float]] | None = None
    uvs: list[list[tuple[float, float]]] = field(default_factory=list)
    colors: list[tuple[float, float, float, float]] | None = None
    joints: list[tuple[int, ...]] | None = None
    weights: list[tuple[float, ...]] | None = None
    tangents: list[tuple[float, float, float, float]] | None = None


def quantize_weights(ws) -> list[int]:
    """Weights → 4 bytes summing to exactly 255 (largest remainders get the leftovers).

    Every skinned vertex of both games sums to 255; a smaller sum pulls the vertex
    toward the world origin in the shader (formats.md §Skinning)."""
    ws = [max(0.0, float(w)) for w in list(ws)[:4]] + [0.0] * (4 - len(list(ws)[:4]))
    total = sum(ws)
    if total <= 0:
        raise FormatError("a skinned vertex has no weight")
    scaled = [w * 255.0 / total for w in ws]
    q = [int(math.floor(s)) for s in scaled]
    for i in sorted(range(4), key=lambda i: q[i] - scaled[i])[:255 - sum(q)]:
        q[i] += 1
    return q


def compute_tangents(positions, normals, uv, triangles) -> list[tuple[float, float, float, float]]:
    """Per-vertex tangents from the UV layout (summed per triangle, made perpendicular to
    the normal). ``w`` is +1 where the UV layout is mirrored relative to the shared
    convention of the games' data and -1 otherwise (see formats.md §"Tangent w": the
    stored w does not follow the UV handedness, so this choice is not verified ❓)."""
    n = len(positions)
    t_acc = [[0.0, 0.0, 0.0] for _ in range(n)]
    b_acc = [[0.0, 0.0, 0.0] for _ in range(n)]
    for a, b, c in triangles:
        pa, pb, pc = positions[a], positions[b], positions[c]
        e1 = [pb[i] - pa[i] for i in range(3)]
        e2 = [pc[i] - pa[i] for i in range(3)]
        du1, dv1 = uv[b][0] - uv[a][0], uv[b][1] - uv[a][1]
        du2, dv2 = uv[c][0] - uv[a][0], uv[c][1] - uv[a][1]
        r = du1 * dv2 - du2 * dv1
        if abs(r) < 1e-20:
            continue
        t = [(e1[i] * dv2 - e2[i] * dv1) / r for i in range(3)]
        bt = [(e2[i] * du1 - e1[i] * du2) / r for i in range(3)]
        for v in (a, b, c):
            for i in range(3):
                t_acc[v][i] += t[i]
                b_acc[v][i] += bt[i]
    out = []
    for v in range(n):
        nv = normals[v] if normals else (0.0, 0.0, 1.0)
        t = t_acc[v]
        d = sum(t[i] * nv[i] for i in range(3))
        t = [t[i] - nv[i] * d for i in range(3)]
        ln = math.sqrt(sum(x * x for x in t))
        if ln < 1e-12:                         # no UV gradient: any perpendicular axis
            ax = (1.0, 0.0, 0.0) if abs(nv[0]) < 0.9 else (0.0, 1.0, 0.0)
            d = sum(ax[i] * nv[i] for i in range(3))
            t = [ax[i] - nv[i] * d for i in range(3)]
            ln = math.sqrt(sum(x * x for x in t)) or 1.0
        t = [x / ln for x in t]
        cr = (nv[1] * t[2] - nv[2] * t[1], nv[2] * t[0] - nv[0] * t[2],
              nv[0] * t[1] - nv[1] * t[0])
        h = sum(cr[i] * b_acc[v][i] for i in range(3))
        out.append((t[0], t[1], t[2], 1.0 if h < 0 else -1.0))
    return out


@dataclass
class _Sub:
    """One draw to write: a slice of a `DrawGeometry` with its palette."""
    geom: DrawGeometry
    template: Draw
    template_mesh: Mesh
    vertices: list[int]                  # indices into geom's lists
    triangles: list[tuple[int, int, int]]   # local to `vertices`
    palette_start: int
    palette_count: int


def _vertex_nodes(g: DrawGeometry, v: int) -> list[int]:
    return [j for j, w in zip(g.joints[v], g.weights[v]) if w > 0]


def split_by_palette(g: DrawGeometry, max_count: int = MAX_PALETTE
                     ) -> list[tuple[list[tuple[int, int, int]], int, int]]:
    """Group a skinned part's triangles so each group's nodes fit one palette run.

    Returns ``(triangles, palette_start, palette_count)`` per group. Triangles are
    sorted by the nodes they use, then packed greedily. Raises `FormatError` if one
    triangle alone spans more than ``max_count`` nodes.
    """
    span = []
    for t in g.triangles:
        nodes = [j for v in t for j in _vertex_nodes(g, v)]
        if not nodes:
            raise FormatError("a triangle has vertices without any bone weight")
        lo, hi = min(nodes), max(nodes)
        if hi - lo + 1 > max_count:
            raise FormatError(f"a triangle uses nodes {lo}..{hi}, more than {max_count} "
                              f"apart: no palette can hold it")
        span.append((lo, hi, t))
    span.sort(key=lambda s: (s[0], s[1]))
    groups: list[list] = []
    for lo, hi, t in span:
        if groups:
            g_lo, g_hi, ts = groups[-1]
            n_lo, n_hi = min(g_lo, lo), max(g_hi, hi)
            if n_hi - n_lo + 1 <= max_count:
                groups[-1] = [n_lo, n_hi, ts + [t]]
                continue
        groups.append([lo, hi, [t]])
    return [(ts, lo, hi - lo + 1) for lo, hi, ts in groups]


def _subset(tris) -> tuple[list[int], list[tuple[int, int, int]]]:
    order: dict[int, int] = {}
    local = []
    for t in tris:
        local.append(tuple(order.setdefault(v, len(order)) for v in t))
    return list(order), local


def _f32(x: float) -> float:
    return struct.unpack(">f", struct.pack(">f", x))[0]


def own_buffers(mesh: Mesh) -> bool:
    """True for a shape with its own buffers (characters), False for one reading the
    shared ``Combined …`` buffers (props, environments). Raises `FormatError` for a
    vertex-animated shape (a stream filled at run time), which can't be replaced."""
    refs = [s.buffer for d in mesh.draws for s in d.streams.values()]
    if any(b is None for b in refs):
        raise FormatError(f"{mesh.name}: vertex-animated (run-time stream); "
                          f"replacing it is not supported")
    return all(not b.startswith("Combined") for b in refs)


def find_template(scene: Scene, mesh: Mesh, material: int) -> tuple[Draw, Mesh]:
    """The original draw a new part of ``mesh`` with ``material`` copies (shader,
    textures, vertex layout): one of this shape with that material, else one of another
    shape with the same buffer family. Raises `FormatError` when there is none."""
    for d in mesh.draws:
        if d.material == material:
            return d, mesh
    own = own_buffers(mesh)
    for m in scene.meshes:
        if m is mesh:
            continue
        try:
            fam = own_buffers(m)
        except FormatError:
            continue
        for d in m.draws:
            if d.material == material and fam == own:
                return d, m
    mat = scene.materials[material] if 0 <= material < len(scene.materials) else None
    raise FormatError(f"{mesh.name}: no draw of this model uses material {material} "
                      f"({mat.texture('colour') if mat else '?'}) with "
                      f"{'own' if own else 'combined'} buffers, so there is nothing to copy "
                      f"its shader and textures from")


class SceneEditor:
    """Collects shape replacements on a parsed `Scene`, then writes the scene bytes.

    The scene object is modified in place (its archives' entries); parse the result
    again (`Scene.parse(editor.to_bytes())`) to read what was written.
    """

    def __init__(self, scene: Scene):
        if scene.persistent is None:
            raise FormatError(f"{scene.source}: no persistent.big (a skeleton, not a model)")
        self.scene = scene
        self.notes: list[str] = []
        self._new_boxes: dict[str, tuple] = {}      # shape name -> (min, max)
        self._dirty_persistent = False

    # -- helpers --
    def _p(self, name: str):
        e = _chunk(self.scene.persistent, name)
        if e is None:
            raise FormatError(f"{self.scene.source}: persistent.big has no {name!r}")
        return e

    def _a(self, name: str):
        e = _chunk(self.scene.archive, name)
        if e is None:
            raise FormatError(f"{self.scene.source}: no entry {name!r}")
        return e

    def mesh(self, name: str) -> Mesh:
        for m in self.scene.meshes:
            if m.name.lower() == name.lower():
                return m
        raise FormatError(f"{self.scene.source}: no shape {name!r}")

    # -- the edit --
    def replace_mesh(self, name: str, parts: list[DrawGeometry]) -> list[tuple[int, int]]:
        """Replace every draw of shape ``name`` with ``parts``. Returns the palette
        (start, count) of each draw written, in order."""
        mesh = self.mesh(name)
        own = own_buffers(mesh)
        if not parts:
            raise FormatError(f"{name}: no geometry to write (a shape needs at least one draw)")
        subs: list[_Sub] = []
        for g in parts:
            n = len(g.positions)
            for t in g.triangles:
                if not all(0 <= v < n for v in t):
                    raise FormatError(f"{name}: a triangle points past the {n} vertices")
            tmpl, tmesh = find_template(self.scene, mesh, g.material)
            if tmpl.skinned:
                if g.joints is None or g.weights is None:
                    raise FormatError(f"{name}: material {g.material}'s shader is skinned; "
                                      f"the part needs bone weights")
                groups = split_by_palette(g)
            else:
                if g.joints is not None and g.weights is not None:
                    nodes = {j for v in range(n) for j in _vertex_nodes(g, v)}
                    if len(nodes) > 1:
                        raise FormatError(
                            f"{name}: material {g.material}'s shader is rigid (no bone "
                            f"weights in its vertex layout); weight every vertex of this "
                            f"part to one bone (it uses {len(nodes)})")
                    start = nodes.pop() if nodes else tmpl.palette_start
                else:
                    start = tmpl.palette_start
                groups = [(g.triangles, start, 1 if tmpl.palette_count else 0)]
            for tris, start, count in groups:
                verts, local = _subset(tris)
                subs.append(_Sub(g, tmpl, tmesh, verts, local, start, count))
        if own:
            self._write_own(mesh, subs)
        else:
            self._write_combined(mesh, subs)
        self._dirty_persistent = True
        return [(s.palette_start, s.palette_count) for s in subs]

    # -- vertex encoding --
    def _encode(self, sub: _Sub, decl: list[vx.VertexElement], strides: dict[int, int]
                ) -> dict[int, bytes]:
        g, n = sub.geom, len(sub.vertices)
        vs = sub.vertices
        pos = [g.positions[v] for v in vs]
        nrm = [g.normals[v] for v in vs] if g.normals else [(0.0, 0.0, 1.0)] * n
        tex_els = sorted((e for e in decl if e.usage == vx.TEXCOORD), key=lambda e: e.usage_index)
        uv_rank = {e.usage_index: r for r, e in enumerate(tex_els)}
        out = {s: bytearray(n * st) for s, st in strides.items()}
        tangents = None
        for el in decl:
            buf, st = out[el.stream], strides[el.stream]
            u = el.usage
            if u == vx.POSITION:
                vals = pos
            elif u == vx.NORMAL:
                vals = nrm
            elif u == vx.TEXCOORD:
                r = uv_rank[el.usage_index]
                src = g.uvs[r] if r < len(g.uvs) else (g.uvs[0] if g.uvs else None)
                vals = [src[v] for v in vs] if src else [(0.0, 0.0)] * n
            elif u == vx.TANGENT:
                if tangents is None:
                    if g.tangents is not None:
                        tangents = [g.tangents[v] for v in vs]
                    else:
                        uv0 = [g.uvs[0][v] for v in vs] if g.uvs else [(0.0, 0.0)] * n
                        tangents = compute_tangents(pos, nrm, uv0, sub.triangles)
                vals = tangents
            elif u == vx.COLOR:
                vals = [g.colors[v] for v in vs] if g.colors else [(1.0, 1.0, 1.0, 1.0)] * n
            elif u == vx.BLENDWEIGHT:
                vals = [[q / 255.0 for q in quantize_weights(g.weights[v])] for v in vs]
            elif u == vx.BLENDINDICES:
                vals = []
                for v in vs:
                    row = []
                    for j, w in list(zip(g.joints[v], g.weights[v]))[:4]:
                        slot = j - sub.palette_start if w > 0 else 0
                        if not 0 <= slot < max(sub.palette_count, 1):
                            raise FormatError(f"node {j} is outside palette "
                                              f"{sub.palette_start}+{sub.palette_count}")
                        row.append(3 * slot)
                    vals.append(row + [0] * (4 - len(row)))
            else:
                self.notes.append(f"{vx.USAGE_NAMES.get(u, u)} element written as zeros")
                continue
            vx.encode_element(el, vals, buf, st)
        return {s: bytes(b) for s, b in out.items()}

    # -- own buffers (characters) --
    def _write_own(self, mesh: Mesh, subs: list[_Sub]) -> None:
        """Rewrite the shape's own buffers. Each draw writes into the buffer numbers its
        template's packet binds (``<shape> Vertices k`` per stream, ``Indices k``), back
        to back; a draw whose streams sit in buffers of different lengths starts after
        the longest one (the others are padded), since one first-vertex serves them all."""
        name = mesh.name
        vb: dict[int, bytearray] = {}
        strides: dict[int, int] = {}
        ib: dict[int, bytearray] = {}
        draws = []
        for s in subs:
            lay = {st: (int(sr.buffer.rsplit(" ", 1)[1]), sr.stride)
                   for st, sr in s.template.streams.items()}
            for k, stride in lay.values():
                if strides.setdefault(k, stride) != stride:
                    raise FormatError(f"{name}: two parts' materials put vertex buffer {k} "
                                      f"at strides {strides[k]} and {stride}")
                vb.setdefault(k, bytearray())
            first_v = max(len(vb[k]) // strides[k] for k, _ in lay.values())
            for k, _ in lay.values():
                vb[k] += bytes(first_v * strides[k] - len(vb[k]))
            decl_no, decl = self._declaration(mesh, s)
            data = self._encode(s, decl, {st: stride for st, (_, stride) in lay.items()})
            for st, (k, _) in lay.items():
                vb[k] += data[st]
            if first_v + len(s.vertices) - 1 > MAX_INDEX:
                raise FormatError(f"{name}: {first_v + len(s.vertices)} vertices; 16-bit "
                                  f"indices hold {MAX_INDEX + 1}")
            ib_no = int(s.template.index_buffer.rsplit(" ", 1)[1])
            buf = ib.setdefault(ib_no, bytearray())
            first_i = len(buf) // 2
            strip = [first_v + i for i in triangles_to_strip(s.triangles)]
            buf += struct.pack(f">{len(strip)}H", *strip)
            draws.append((s, decl_no, (0, first_v, len(s.vertices), first_i, len(strip), 1),
                          None, None))
        self._own_header(name, "VBHeader", "Vertices", vb, strides)
        self._own_header(name, "IBHeader", "Indices", ib, {k: 2 for k in ib})
        self._finish(mesh, draws)

    def _own_header(self, name: str, header: str, kind: str, bufs: dict[int, bytearray],
                    strides: dict[int, int]) -> None:
        """Write ``<shape> <kind> k`` and the matching ``<shape> <header>`` records.
        Buffers the new draws don't use keep their bytes and record."""
        e = self._p(f"{name} {header}")
        recs = [r.raw for r in parse_buffer_header(e.data(), f"{name} {header}")]
        for k in sorted(bufs):
            if k >= len(recs):
                raise FormatError(f"{name}: {kind.lower()} buffer {k} has no {header} record")
            self._a(f"{name} {kind} {k}").set_data(bytes(bufs[k]))
            recs[k] = buffer_record(recs[k], len(bufs[k]) // strides[k], strides[k])
        for k in range(len(recs)):
            if k not in bufs:
                self.notes.append(f"{name}: {kind.lower()} buffer {k} is not used by the "
                                  f"new draws; left as it was")
        e.set_data(b"".join(recs))

    # -- combined buffers (props, environments) --
    def _write_combined(self, mesh: Mesh, subs: list[_Sub]) -> None:
        vbh = {b.name.lower(): b for b in parse_buffer_header(
            self._p("Combined_VBHeader").data(), "Combined_VBHeader")}
        ibh = {b.name.lower(): b for b in parse_buffer_header(
            self._p("Combined_IBHeader").data(), "Combined_IBHeader")}
        counts = {k: b.count for k, b in {**vbh, **ibh}.items()}
        grown: dict[str, bytearray] = {}

        def buf(name: str) -> bytearray:
            if name.lower() not in grown:
                grown[name.lower()] = bytearray(self._a(name).data())
            return grown[name.lower()]

        draws = []
        for s in subs:
            decl_no, decl = self._declaration(mesh, s)
            strides = {k: sr.stride for k, sr in s.template.streams.items()}
            data = self._encode(s, decl, strides)
            binds = {}
            for k, sr in s.template.streams.items():
                b = buf(sr.buffer)
                first = counts[sr.buffer.lower()]
                if len(b) != first * sr.stride:
                    raise FormatError(f"{sr.buffer}: {len(b)} bytes, header says "
                                      f"{first} × {sr.stride}")
                b += data[k]
                counts[sr.buffer.lower()] = first + len(s.vertices)
                binds[k] = first
            strip = triangles_to_strip(s.triangles)
            ibuf = buf(s.template.index_buffer)
            first_i = counts[s.template.index_buffer.lower()]
            ibuf += struct.pack(f">{len(strip)}H", *strip)
            counts[s.template.index_buffer.lower()] = first_i + len(strip)
            draws.append((s, decl_no, (0, 0, len(s.vertices), 0, len(strip), 1), binds, first_i))
        for lname, b in grown.items():
            e = next(e for e in self.scene.archive.entries if e.name.lower() == lname)
            e.set_data(bytes(b))
        self._p("Combined_VBHeader").set_data(b"".join(
            buffer_record(b.raw, counts[k]) for k, b in vbh.items()))
        self._p("Combined_IBHeader").set_data(b"".join(
            buffer_record(b.raw, counts[k]) for k, b in ibh.items()))
        self._finish(mesh, draws)

    def _declaration(self, mesh: Mesh, s: _Sub) -> tuple[int, list[vx.VertexElement]]:
        """The declaration number in ``mesh`` for the template's layout (copied into the
        shape as a new ``D3DVertexDesc N`` when it comes from another shape)."""
        tdecl = s.template.declaration
        if s.template_mesh is mesh:
            return s.template.declaration_number, tdecl
        want = vx.declaration_bytes(tdecl)
        n = 0
        while True:
            e = _chunk(self.scene.persistent, f"{mesh.name} D3DVertexDesc {n}")
            if e is None:
                break
            if e.data() == want:
                return n, tdecl
            n += 1
        self.scene.persistent.add(f"{mesh.name} D3DVertexDesc {n}", want, alignment=4)
        vd = self._p(f"{mesh.name} VDHeader")
        vd.set_data(vd.data() + struct.pack(">Ii", 0, -1))
        self.notes.append(f"{mesh.name}: copied vertex declaration {n} from "
                          f"{s.template_mesh.name}")
        return n, tdecl

    def _finish(self, mesh: Mesh, draws) -> None:
        """Command buffer, RenderStrip and shape chunk for the new draws of ``mesh``."""
        cmds: list[Command] = []
        records = []
        for s, decl_no, args, binds, first_i in draws:
            t, tm = s.template, s.template_mesh
            tcmds = parse_command_buffer(self._p(f"{tm.name} CommandBuffer").data())
            packet = split_packets(tcmds, [d.strip[5] for d in tm.draws])[t.number]
            offset = packet_words(cmds) * 4
            for c in packet:
                op, w, a = c.op, c.word, c.args
                if op == 0x0A:
                    w = (w & ~0xFF00) | (decl_no << 8)
                elif op == 0x28 and binds is not None and w & 0x80000000:
                    a = (binds[(w >> 8) & 0xFF],)
                elif op == 0x47 and first_i is not None:
                    a = (first_i,)
                elif op == 0x08:
                    a = tuple(args)
                cmds.append(Command(w, a))
            mat_id = self.scene.materials[s.geom.material].id
            records.append((mat_id - 1, t.strip[1], t.strip[2], s.palette_start,
                            s.palette_count, offset, t.strip[6]))
        name = mesh.name
        self._p(f"{name} CommandBuffer").set_data(command_buffer_bytes(cmds))
        self._p(f"{name} RenderStrip").set_data(strip_bytes(records))
        pts = [tuple(_f32(c) for c in s.geom.positions[v]) for s, *_ in draws
               for v in s.vertices]
        radius = _f32(max(math.sqrt(sum(c * c for c in p)) for p in pts))
        bmin = tuple(min(p[i] for p in pts) for i in range(3))
        bmax = tuple(max(p[i] for p in pts) for i in range(3))
        n_decls = 0
        while _chunk(self.scene.persistent, f"{name} D3DVertexDesc {n_decls}") is not None:
            n_decls += 1
        words = list(mesh.words)
        words[3], words[5] = n_decls, len(records)
        words[6], words[7] = records[0][3], records[0][4]
        shape = self._p(name)
        shape.set_data(shape_bytes(words, radius, bmin, bmax, shape.data()[60:]))
        self._new_boxes[name.lower()] = (bmin, bmax)

    # -- output --
    def to_bytes(self) -> bytes:
        """The scene archive with every edit applied."""
        if self._dirty_persistent:
            self._update_model_box()
            self._a("persistent.big").set_data(self.scene.persistent.to_bytes())
        return self.scene.archive.to_bytes()

    def _update_model_box(self) -> None:
        """``_BOUNDINGBOX_`` (the whole model): recomputed as the union of the shapes'
        boxes when it was that union (most models), else grown to hold the new shapes."""
        e = _chunk(self.scene.persistent, "_BOUNDINGBOX_")
        if e is None or not self._new_boxes:
            return
        old = struct.unpack(">6f", e.data())
        shapes = [(m.bounds_min, m.bounds_max) for m in self.scene.meshes]
        union = [min(b[0][i] for b in shapes) for i in range(3)] + \
                [max(b[1][i] for b in shapes) for i in range(3)]
        new_shapes = [self._new_boxes.get(m.name.lower(), (m.bounds_min, m.bounds_max))
                      for m in self.scene.meshes]
        new_union = [min(b[0][i] for b in new_shapes) for i in range(3)] + \
                    [max(b[1][i] for b in new_shapes) for i in range(3)]
        if [_f32(x) for x in union] == list(old):
            box = new_union
        else:
            box = [min(old[i], new_union[i]) for i in range(3)] + \
                  [max(old[3 + i], new_union[3 + i]) for i in range(3)]
        e.set_data(struct.pack(">6f", *box))


__all__ = ["BUFFER_RECORD", "DrawGeometry", "MAX_PALETTE", "SceneEditor", "find_template",
           "own_buffers",
           "command_buffer_bytes", "compute_tangents", "quantize_weights",
           "rewrite_problems", "shape_bytes", "split_by_palette", "split_packets",
           "strip_bytes", "triangles_to_strip"]

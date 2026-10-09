"""Scenes: the models and skeletons of both games (a ``.big`` of named chunks).

A model (``npcs.big/chest_young_chuck.big``) or a skeleton (``skeleton/player_fullbody.big``)
is a ``.big`` whose entries are *chunks*. Everything is **big-endian**. This module reads
them into a `Scene`: the node tree (skeleton), the materials and their texture slots,
and the meshes with every draw call they make, then decodes a draw's vertices and
triangles (`Scene.draw_data`).

Where things are (docs/formats.md §"Scene container", all verified by
``dr2 census --models`` over every scene of both games):

* ``SceneHeader``: 5 words. Word 3 is the number of `SceneDescription` records.
* ``SceneDescription``: 36-byte records, a 32-byte name + a u32 kind
  (2 = transform node, 0 = shape).
* ``_BONENAMES_``: the skeleton's node names, 31 bytes each, NUL-padded. Each name is
  also an entry holding that node's **52-byte record** (`Node`): index, parent, a flag,
  scale, translation, rotation quaternion (x, y, z, w), relative to the parent.
  ``_BONEHIERARCHY_`` repeats (index, parent) as pairs.
* ``MatArray``: 36 bytes per material: id, a hash, the number of texture slots and the
  byte offset of the first one in ``MatTextureInfoArray`` (100-byte slots, texture
  name at +4), four floats and the name of the material's value set (``valuesets.big``).
* ``UsedShaders.txt``: ``0xHASH : ShaderName`` lines.
* ``persistent.big`` holds the **mesh descriptions**, one group per shape ``<shape>``:

  - ``<shape>`` (72 bytes): 8 words, then the bounds: radius, box min, box max.
  - ``<shape> RenderStrip``: 28 bytes per draw: material number, two flag words, the
    **bone palette** (first node, node count), and two more words. The material number
    *n* means the ``MatArray`` record whose **id is n + 1**; records are not stored in id
    order (``boss_mechanic.big``), so it is not a position.
  - ``<shape> D3DVertexDesc N``: draw N's vertex declaration (`dr2kit.formats.vertex`).
  - ``<shape> CommandBuffer``: the recorded draw calls (`parse_command_buffer`): which
    vertex and index buffers, where each draw starts, and how many vertices and
    indices it uses.
  - ``<shape> VBHeader`` / ``IBHeader``: the shape's own buffers (56-byte records: name,
    count, stride), *or* ``Combined_VBHeader`` / ``Combined_IBHeader`` at the archive
    level: buffers shared by every shape, named by stride (``Combined Vertices 12``).

* The buffers themselves sit in the scene archive: ``<shape> Vertices N`` /
  ``<shape> Indices N`` (characters), or ``Combined Vertices <stride>`` /
  ``Combined Indices 2`` (props and environments).

Two facts that the old community tools stalled on:

* **Indices are one triangle strip per draw**, joined by repeated indices (degenerate
  triangles). No restart markers occur.
* **The bone palette is a contiguous run of skeleton nodes**: palette slot *k* is node
  ``palette_start + k``. Vertex blend indices are palette *rows* (3 × slot). Verified
  geometrically: every skinned vertex sits next to the bones it is weighted to.

Unknown chunks and unparsed words are kept (`Scene.unknown`, raw fields), never dropped.
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass, field

from ..container.big import BigArchive, BigEntry, is_big
from ..errors import FormatError
from . import vertex as vx

NODE_RECORD = 52
BONE_NAME = 31
DESC_RECORD = 36
MAT_RECORD = 36
SLOT_RECORD = 100
STRIP_RECORD = 28
BUFFER_RECORD = 56

NODE_FMT = ">IiI3f3f4f"


# --- skeleton ---------------------------------------------------------------------------

@dataclass
class Node:
    """One 52-byte node record: a bone (or dummy) of the skeleton, relative to its parent."""
    name: str
    index: int
    parent: int                                   # -1 = root; == index: root of a split rig
    flag: int                                     # 1 on most records, 0 on some; meaning unknown
    scale: tuple[float, float, float]
    translation: tuple[float, float, float]
    rotation: tuple[float, float, float, float]   # quaternion x, y, z, w

    @classmethod
    def parse(cls, name: str, data: bytes, source: str = "<memory>") -> "Node":
        if len(data) != NODE_RECORD:
            raise FormatError(f"{source}: node record is {len(data)} bytes, not {NODE_RECORD}")
        v = struct.unpack(NODE_FMT, data)
        return cls(name, v[0], v[1], v[2], v[3:6], v[6:9], v[9:13])

    def to_bytes(self) -> bytes:
        return struct.pack(NODE_FMT, self.index, self.parent, self.flag, *self.scale,
                           *self.translation, *self.rotation)

    @property
    def is_root(self) -> bool:
        """True for a root: parent -1, or (in the split rig files such as
        ``preload4.big/femaleroot.big``) a parent equal to the node's own index."""
        return self.parent < 0 or self.parent == self.index


def quat_mul(a, b):
    """Hamilton product a·b of (x, y, z, w) quaternions."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def quat_rotate(q, v):
    """Rotate vector v by unit quaternion q."""
    x, y, z, w = q
    vx_, vy, vz = v
    tx, ty, tz = 2 * (y * vz - z * vy), 2 * (z * vx_ - x * vz), 2 * (x * vy - y * vx_)
    return (vx_ + w * tx + y * tz - z * ty,
            vy + w * ty + z * tx - x * tz,
            vz + w * tz + x * ty - y * tx)


def trs_matrix(t, q, s) -> list[list[float]]:
    """A 4×4 row-major matrix from translation, rotation (x, y, z, w) and scale."""
    x, y, z, w = q
    r = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return [[r[i][0] * s[0], r[i][1] * s[1], r[i][2] * s[2], t[i]] for i in range(3)] + \
        [[0.0, 0.0, 0.0, 1.0]]


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def mat_inverse_affine(m):
    """Inverse of an affine 4×4 (rotation × scale + translation)."""
    a = [row[:3] for row in m[:3]]
    det = (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
           - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
           + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    if abs(det) < 1e-20:
        raise FormatError("singular bone matrix (zero scale?)")
    inv = [[(a[(j + 1) % 3][(i + 1) % 3] * a[(j + 2) % 3][(i + 2) % 3]
             - a[(j + 1) % 3][(i + 2) % 3] * a[(j + 2) % 3][(i + 1) % 3]) / det
            for j in range(3)] for i in range(3)]
    t = [m[0][3], m[1][3], m[2][3]]
    it = [-sum(inv[i][k] * t[k] for k in range(3)) for i in range(3)]
    return [inv[0] + [it[0]], inv[1] + [it[1]], inv[2] + [it[2]], [0.0, 0.0, 0.0, 1.0]]


@dataclass
class Skeleton:
    """The node tree: `Node` records in index order."""
    nodes: list[Node]

    def __len__(self) -> int:
        return len(self.nodes)

    def by_name(self, name: str) -> Node | None:
        key = name.lower()
        return next((n for n in self.nodes if n.name.lower() == key), None)

    def children(self, index: int) -> list[Node]:
        return [n for n in self.nodes if n.parent == index and not n.is_root]

    def world_matrices(self) -> list[list[list[float]]]:
        """Each node's rest-pose matrix in model space (parent × local, root first)."""
        out: list = [None] * len(self.nodes)

        def go(i: int, depth: int = 0):
            if out[i] is not None:
                return out[i]
            if depth > len(self.nodes):
                raise FormatError("skeleton has a parent cycle")
            n = self.nodes[i]
            local = trs_matrix(n.translation, n.rotation, n.scale)
            out[i] = local if n.is_root else mat_mul(go(n.parent, depth + 1), local)
            return out[i]

        for i in range(len(self.nodes)):
            go(i)
        return out

    def world_positions(self) -> list[tuple[float, float, float]]:
        return [(m[0][3], m[1][3], m[2][3]) for m in self.world_matrices()]


# --- materials --------------------------------------------------------------------------

@dataclass
class TextureSlot:
    """One 100-byte ``MatTextureInfoArray`` record."""
    number: int              # u32 at +0 (1 on every slot seen)
    name: str                # texture name, or an engine sampler (gExposureTexture, …)
    raw: bytes               # the whole record, kept for writing back

    @property
    def hash(self) -> int:
        """Word at +0x38: matches the command buffer's sampler hashes (not the name hash)."""
        return struct.unpack_from(">I", self.raw, 0x38)[0]

    @property
    def engine(self) -> bool:
        """True for the engine's own samplers (``gName…``), which no model ships."""
        return len(self.name) > 1 and self.name[0] == "g" and self.name[1].isupper()

    @property
    def role(self) -> str:
        """The texture's role from its suffix: ``colour``, ``normal``, ``specular``, …"""
        return texture_role(self.name)


ROLE_SUFFIXES = {"cm": "colour", "nm": "normal", "sm": "specular", "mask": "mask",
                 "det": "detail", "ne": "normal", "rm": "reflection", "si": "self-illum",
                 "om": "opacity", "ig": "glow", "no": "normal"}


def texture_role(name: str) -> str:
    m = re.search(r"_([a-z]+)\d*$", name.lower())      # mech_eye_cm1 is a colour map too
    return ROLE_SUFFIXES.get(m.group(1), "other") if m else "other"


@dataclass
class Material:
    """One 36-byte ``MatArray`` record and the texture slots it owns."""
    id: int
    hash: int
    slot_count: int
    slot_offset: int                         # bytes into MatTextureInfoArray
    params: tuple[float, float, float, float]
    valueset: int                            # name of its .scv in valuesets.big (hex)
    slots: list[TextureSlot] = field(default_factory=list)

    def texture(self, role: str) -> str | None:
        """The first non-engine texture with this role (``colour``, ``normal``, …)."""
        return next((s.name for s in self.slots if not s.engine and s.role == role), None)


# --- meshes -----------------------------------------------------------------------------

@dataclass(frozen=True)
class BufferInfo:
    """A 56-byte VBHeader / IBHeader record: buffer name, element count, stride."""
    name: str
    count: int
    stride: int
    raw: bytes


def parse_buffer_header(data: bytes, source: str) -> list[BufferInfo]:
    if len(data) % BUFFER_RECORD:
        raise FormatError(f"{source}: {len(data)} bytes, not a multiple of {BUFFER_RECORD}")
    out = []
    for off in range(0, len(data), BUFFER_RECORD):
        r = data[off:off + BUFFER_RECORD]
        name = r[:0x24].split(b"\0", 1)[0].decode("latin-1")
        count, stride = struct.unpack_from(">II", r, 0x28)
        out.append(BufferInfo(name, count, stride, r))
    return out


# CommandBuffer opcodes (low byte of a word) and how many argument words follow.
# Measured on every command buffer of both games (dr2 census --models); an opcode not in
# this table stops the parse with a named error.
CMD_ARGS = {
    0x04: 0,   # end of a draw packet (upper bits vary: fffff004 / fffff404 / fffff604)
    0x08: 6,   # draw: (base, first vertex, vertex count, first index, index count, 1)
    0x0A: 0,   # start of a draw packet; byte 1 = which D3DVertexDesc it uses
    0x0B: 0,   # bind the shape's own vertex buffer (byte 1 = stream, byte 2 = buffer)
    0x0C: 0,   # bind the shape's own index buffer (byte 1 = which one)
    0x0D: 0, 0x0E: 0, 0x0F: 0,   # sampler / render state (byte 1 = slot)
    0x16: 2,   # a hash and a float (-0.1 seen); a shader constant? (fence poles)
    0x28: 1,   # bind a combined vertex buffer: bits 16-23 = stride, byte 1 = stream; arg = first vertex
    0x33: 1,   # set an engine sampler (arg = its hash, as in MatTextureInfoArray +0x38)
    0x3B: 1,   # set a texture by hash (byte 1 = sampler slot)
    0x3C: 1,   # set the shader (arg = hash in UsedShaders.txt)
    0x3F: 1,   # shader hash again (end of packet)
    0x47: 1,   # bind the combined index buffer (byte 1 = index size); arg = first index
    0x41: 0, 0x43: 0, 0x71: 0, 0x73: 0,   # render state around the draw
}

# Bit 31 of a 0x28 word: the stream is a real combined buffer. Without it (stride 0)
# the stream is filled by the engine at run time: vertex-animated meshes (larvae) get
# their positions from ``ANIM_<a>_FRAME_<f>_`` chunks that way.
BIND_STATIC = 0x80000000


@dataclass
class Command:
    word: int
    args: tuple[int, ...]

    @property
    def op(self) -> int:
        return self.word & 0xFF


def parse_command_buffer(data: bytes, source: str = "<memory>") -> list[Command]:
    """Split a ``CommandBuffer`` chunk into commands (see `CMD_ARGS`)."""
    if len(data) % 4:
        raise FormatError(f"{source}: command buffer is {len(data)} bytes, not whole words")
    words = struct.unpack(f">{len(data) // 4}I", data)
    out, i = [], 0
    while i < len(words):
        w = words[i]
        n = CMD_ARGS.get(w & 0xFF)
        if n is None:
            raise FormatError(f"{source}: unknown command 0x{w:08X} at word {i}")
        if i + 1 + n > len(words):
            raise FormatError(f"{source}: command 0x{w:08X} at word {i} is cut short")
        out.append(Command(w, tuple(words[i + 1:i + 1 + n])))
        i += 1 + n
    return out


@dataclass
class StreamRef:
    """Where one vertex stream of a draw comes from."""
    stream: int
    buffer: str | None    # entry name in the scene archive; None = filled at run time
    stride: int
    first: int            # vertex the stream is bound at (combined buffers), else 0


@dataclass
class Draw:
    """One draw call of a shape: one RenderStrip record + one command-buffer packet."""
    number: int
    material: int                        # index into Scene.materials (-1: none has that id)
    palette_start: int                   # first skeleton node of the bone palette
    palette_count: int
    strip: tuple[int, ...]               # the 7 RenderStrip words, raw
    declaration: list[vx.VertexElement]
    declaration_number: int              # which "D3DVertexDesc N" (several draws may share one)
    streams: dict[int, StreamRef]
    index_buffer: str
    index_bind: int                      # first index the index buffer is bound at
    base_vertex: int                     # draw args, in order
    first_vertex: int
    vertex_count: int
    first_index: int
    index_count: int
    draw_word: int                       # the raw draw command word (0x408 / 0x308 …)
    shader: int                          # shader hash bound for this draw (0 if none)

    @property
    def skinned(self) -> bool:
        return any(e.usage == vx.BLENDINDICES for e in self.declaration)

    def palette(self) -> list[int]:
        """Palette slot → skeleton node index."""
        return list(range(self.palette_start, self.palette_start + self.palette_count))


@dataclass
class Mesh:
    """One shape (``<shape>`` in persistent.big) and its draws."""
    name: str
    words: tuple[int, ...]               # the shape chunk's 8 leading words, raw
    radius: float
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    draws: list[Draw]


@dataclass
class DrawData:
    """A draw decoded into plain lists (model space, rest pose)."""
    positions: list[tuple[float, float, float]]
    normals: list[tuple[float, float, float]] | None
    tangents: list[tuple[float, float, float, float]] | None
    uvs: list[list[tuple[float, float]]]            # one list per TEXCOORD set, in usage order
    colors: list[tuple[float, float, float, float]] | None
    joints: list[tuple[int, int, int, int]] | None  # skeleton node indices
    weights: list[tuple[float, float, float, float]] | None
    triangles: list[tuple[int, int, int]]           # indices into the lists above
    degenerate: int                                  # strip triangles dropped (repeated index)


def strip_to_triangles(indices: list[int]) -> tuple[list[tuple[int, int, int]], int]:
    """A triangle strip → triangles with consistent winding; degenerate ones dropped."""
    tris, dropped = [], 0
    for i in range(len(indices) - 2):
        a, b, c = indices[i], indices[i + 1], indices[i + 2]
        if a == b or b == c or a == c:
            dropped += 1
            continue
        tris.append((a, b, c) if i % 2 == 0 else (b, a, c))
    return tris, dropped


# --- the scene --------------------------------------------------------------------------

def _cstr(b: bytes) -> str:
    return b.split(b"\0", 1)[0].decode("latin-1")


@dataclass
class Scene:
    """A parsed model or skeleton. `source` is its vpath (for messages)."""
    source: str
    archive: BigArchive
    header: tuple[int, ...]
    description: list[tuple[str, int]]
    skeleton: Skeleton
    hierarchy: list[tuple[int, int]]
    materials: list[Material]
    shaders: dict[int, str]
    meshes: list[Mesh]
    unknown: list[str]                                # chunk names this reader doesn't use
    persistent: BigArchive | None = None

    # -- reading --
    @classmethod
    def parse(cls, data: bytes, source: str = "<memory>") -> "Scene":
        return cls.from_archive(BigArchive.parse(data, source), source)

    @classmethod
    def from_archive(cls, arc: BigArchive, source: str = "<memory>") -> "Scene":
        by = {e.name.lower(): e for e in reversed(arc.entries)}   # first wins
        def chunk(name: str) -> bytes | None:
            e = by.get(name.lower())
            return e.data() if e is not None else None

        hdr = chunk("SceneHeader")
        if hdr is None:
            raise FormatError(f"{source}: not a scene (no SceneHeader)")
        if len(hdr) != 20:
            raise FormatError(f"{source}: SceneHeader is {len(hdr)} bytes, not 20")
        header = struct.unpack(">5I", hdr)

        description = []
        d = chunk("SceneDescription")
        if d is not None:
            if len(d) % DESC_RECORD:
                raise FormatError(f"{source}: SceneDescription is {len(d)} bytes, "
                                  f"not a multiple of {DESC_RECORD}")
            description = [(_cstr(d[o:o + 32]), struct.unpack_from(">I", d, o + 32)[0])
                           for o in range(0, len(d), DESC_RECORD)]

        used = {"sceneheader", "scenedescription", "_bonenames_", "_bonehierarchy_",
                "matarray", "mattextureinfoarray", "usedshaders.txt", "persistent.big"}
        skeleton = cls._read_skeleton(chunk("_BONENAMES_"), by, used, source)

        hierarchy = []
        h = chunk("_BONEHIERARCHY_")
        if h is not None:
            if len(h) % 8:
                raise FormatError(f"{source}: _BONEHIERARCHY_ is {len(h)} bytes, not pairs")
            hierarchy = [struct.unpack_from(">Ii", h, o) for o in range(0, len(h), 8)]

        materials = cls._read_materials(chunk("MatArray"), chunk("MatTextureInfoArray"), source)
        shaders = {}
        t = chunk("UsedShaders.txt")
        if t is not None:
            for line in t.decode("latin-1").splitlines():
                m = re.match(r"\s*0x([0-9A-Fa-f]{1,8})\s*:\s*(\S+)", line)
                if m:
                    shaders[int(m.group(1), 16)] = m.group(2)

        persistent, meshes = None, []
        p = chunk("persistent.big")
        if p is not None and is_big(p):
            persistent = BigArchive.parse(p, f"{source}/persistent.big")
            meshes = cls._read_meshes(persistent, arc, f"{source}/persistent.big")
            for m in meshes:
                for dr in m.draws:
                    used.update(s.buffer.lower() for s in dr.streams.values() if s.buffer)
                    used.add(dr.index_buffer.lower())

        # RenderStrip word 0 = material id - 1; turn it into a position in `materials`
        by_id = {m.id: i for i, m in enumerate(materials)}
        for m in meshes:
            for dr in m.draws:
                dr.material = by_id.get(dr.strip[0] + 1, -1)
        unknown = [e.name for e in arc.entries if e.name.lower() not in used]
        return cls(source, arc, header, description, skeleton, hierarchy, materials,
                   shaders, meshes, unknown, persistent)

    @staticmethod
    def _read_skeleton(names_chunk, by, used, source) -> Skeleton:
        if names_chunk is None:
            return Skeleton([])
        if len(names_chunk) % BONE_NAME:
            raise FormatError(f"{source}: _BONENAMES_ is {len(names_chunk)} bytes, "
                              f"not a multiple of {BONE_NAME}")
        # _BONENAMES_ keeps at most 30 characters of a name; the node's entry has the
        # whole name. So match by prefix among 52-byte entries, and settle collisions
        # (``…geo_carrier`` vs ``…geo_carrier1``) by the index inside the record.
        records = [e for e in by.values() if e.size2 == NODE_RECORD]
        nodes = []
        for i, o in enumerate(range(0, len(names_chunk), BONE_NAME)):
            short = _cstr(names_chunk[o:o + BONE_NAME]).lower()
            if len(short) >= BONE_NAME - 1:
                cands = [e for e in records if e.name.lower().startswith(short)]
            else:
                cands = [e for e in records if e.name.lower() == short]
            parsed = [Node.parse(e.name, e.data(), f"{source}/{e.name}") for e in cands]
            match = [n for n in parsed if n.index == i]
            if len(match) != 1:
                raise FormatError(f"{source}: bone {i} {short!r} has "
                                  f"{'no' if not match else len(match)} node record(s) "
                                  f"with index {i}")
            used.add(match[0].name.lower())
            nodes.append(match[0])
        for i, n in enumerate(nodes):
            if not (-1 <= n.parent < len(nodes)):
                raise FormatError(f"{source}: node {n.name!r} has parent {n.parent}")
        return Skeleton(nodes)

    @staticmethod
    def _read_materials(mat, slots, source) -> list[Material]:
        if mat is None:
            return []
        if len(mat) % MAT_RECORD:
            raise FormatError(f"{source}: MatArray is {len(mat)} bytes, not a multiple of "
                              f"{MAT_RECORD}")
        slots = slots or b""
        out = []
        for o in range(0, len(mat), MAT_RECORD):
            mid, h, count, off = struct.unpack_from(">4I", mat, o)
            params = struct.unpack_from(">4f", mat, o + 16)
            vs = struct.unpack_from(">I", mat, o + 32)[0]
            if off % SLOT_RECORD or off + count * SLOT_RECORD > len(slots):
                raise FormatError(f"{source}: material {mid} points at slots "
                                  f"{off}+{count}×{SLOT_RECORD}, past MatTextureInfoArray "
                                  f"({len(slots)} bytes)")
            ss = []
            for k in range(count):
                r = slots[off + k * SLOT_RECORD: off + (k + 1) * SLOT_RECORD]
                ss.append(TextureSlot(struct.unpack_from(">I", r)[0], _cstr(r[4:56]), r))
            out.append(Material(mid, h, count, off, params, vs, ss))
        return out

    @staticmethod
    def _read_meshes(p: BigArchive, arc: BigArchive, source: str) -> list[Mesh]:
        pby = {e.name.lower(): e for e in reversed(p.entries)}
        names = {e.name.lower() for e in arc.entries}
        combined_vb = {b.stride: b for b in parse_buffer_header(
            pby["combined_vbheader"].data(), f"{source}/Combined_VBHeader")} \
            if "combined_vbheader" in pby else {}
        combined_ib = parse_buffer_header(pby["combined_ibheader"].data(),
                                          f"{source}/Combined_IBHeader") \
            if "combined_ibheader" in pby else []
        meshes = []
        for e in p.entries:
            if not e.name.endswith(" RenderStrip"):
                continue
            shape = e.name[:-len(" RenderStrip")]
            src = f"{source}/{shape}"
            sd = pby.get(shape.lower())
            if sd is None:
                raise FormatError(f"{src}: RenderStrip without a shape chunk")
            sdata = sd.data()
            if len(sdata) < 60:
                raise FormatError(f"{src}: shape chunk is {len(sdata)} bytes")
            words = struct.unpack_from(">8I", sdata)
            radius, *box = struct.unpack_from(">7f", sdata, 32)
            strips = e.data()
            if len(strips) % STRIP_RECORD:
                raise FormatError(f"{src} RenderStrip: {len(strips)} bytes, not a multiple "
                                  f"of {STRIP_RECORD}")
            strip_words = [struct.unpack_from(">7I", strips, o)
                           for o in range(0, len(strips), STRIP_RECORD)]
            cb = pby.get(f"{shape} commandbuffer".lower())
            if cb is None:
                raise FormatError(f"{src}: no CommandBuffer")
            cmds = parse_command_buffer(cb.data(), f"{src} CommandBuffer")
            own_vb = parse_buffer_header(pby[f"{shape} vbheader".lower()].data(),
                                         f"{src} VBHeader") \
                if f"{shape} vbheader".lower() in pby else []
            own_ib = parse_buffer_header(pby[f"{shape} ibheader".lower()].data(),
                                         f"{src} IBHeader") \
                if f"{shape} ibheader".lower() in pby else []

            n_decls = sum(1 for k in pby if k.startswith(f"{shape} d3dvertexdesc ".lower()))
            if not n_decls:
                raise FormatError(f"{src}: no D3DVertexDesc")
            draws = []
            streams: dict[int, StreamRef] = {}
            ib_name, ib_bind, shader, decl_no = None, 0, 0, 0
            for c in cmds:
                op = c.op
                if op == 0x0A:
                    decl_no = (c.word >> 8) & 0xFF
                elif op == 0x3C:
                    shader = c.args[0]
                elif op == 0x0B:
                    stream, buf = (c.word >> 8) & 0xFF, (c.word >> 16) & 0xFF
                    if buf >= len(own_vb):
                        raise FormatError(f"{src}: binds vertex buffer {buf} of {len(own_vb)}")
                    streams[stream] = StreamRef(stream, f"{shape} Vertices {buf}",
                                                own_vb[buf].stride, 0)
                elif op == 0x28:
                    stream, stride = (c.word >> 8) & 0xFF, (c.word >> 16) & 0xFF
                    if not c.word & BIND_STATIC:
                        streams[stream] = StreamRef(stream, None, stride, c.args[0])
                        continue
                    if stride not in combined_vb:
                        raise FormatError(f"{src}: binds a combined stride-{stride} buffer, "
                                          f"which Combined_VBHeader doesn't list")
                    streams[stream] = StreamRef(stream, combined_vb[stride].name, stride,
                                                c.args[0])
                elif op == 0x0C:
                    k = (c.word >> 8) & 0xFF
                    if k >= len(own_ib):
                        raise FormatError(f"{src}: binds index buffer {k} of {len(own_ib)}")
                    ib_name, ib_bind = f"{shape} Indices {k}", 0
                elif op == 0x47:
                    size = (c.word >> 8) & 0xFF
                    match = [b for b in combined_ib if b.stride == size]
                    if not match:
                        raise FormatError(f"{src}: binds a combined {size}-byte index buffer, "
                                          f"which Combined_IBHeader doesn't list")
                    ib_name, ib_bind = match[0].name, c.args[0]
                elif op == 0x08:
                    n = len(draws)
                    if n >= len(strip_words):
                        raise FormatError(f"{src}: more draws than RenderStrip records")
                    if ib_name is None or not streams:
                        raise FormatError(f"{src}: draw {n} has no buffers bound")
                    for s in list(streams.values()) + [StreamRef(-1, ib_name, 0, 0)]:
                        if s.buffer is not None and s.buffer.lower() not in names:
                            raise FormatError(f"{src}: buffer {s.buffer!r} is not in the scene")
                    # Draws that share a layout share a declaration: the packet's 0x0A
                    # word names it (formats.md).
                    dd = pby.get(f"{shape} d3dvertexdesc {decl_no}".lower())
                    if dd is None:
                        raise FormatError(f"{src}: draw {n} uses D3DVertexDesc {decl_no}, "
                                          f"which is missing ({n_decls} declarations)")
                    decl = vx.parse_declaration(dd.data(), f"{src} D3DVertexDesc {decl_no}")
                    sw = strip_words[n]
                    draws.append(Draw(n, sw[0], sw[3], sw[4], sw, decl, decl_no, dict(streams),
                                      ib_name, ib_bind, *c.args[:5], c.word, shader))
            if len(draws) != len(strip_words):
                raise FormatError(f"{src}: {len(draws)} draw commands for "
                                  f"{len(strip_words)} RenderStrip records")
            meshes.append(Mesh(shape, words, radius, tuple(box[:3]), tuple(box[3:]), draws))
        return meshes

    # -- convenience --
    @property
    def kind(self) -> str:
        return "model" if self.meshes else "skeleton"

    def entry(self, name: str) -> BigEntry:
        key = name.lower()
        for e in self.archive.entries:
            if e.name.lower() == key:
                return e
        raise FormatError(f"{self.source}: no entry {name!r}")

    def draw_data(self, draw: Draw, mesh_name: str = "?") -> DrawData:
        """Decode one draw: attributes for its vertex range, and its strip as triangles.

        Vertex *v* of the draw (0-based) is stream vertex ``bind + first_vertex + v``;
        an index *i* addresses ``i - first_vertex``. Joints are mapped through the bone
        palette to skeleton node indices. Raises `FormatError` if an index falls outside
        the draw's vertex range.
        """
        src = f"{self.source}/{mesh_name} draw {draw.number}"
        buffers: dict[str, bytes] = {}

        def buf(name: str) -> bytes:
            if name not in buffers:
                buffers[name] = self.entry(name).data()
            return buffers[name]

        n = draw.vertex_count
        positions = normals = tangents = colors = joints = weights = None
        uvs: list[tuple[int, list]] = []
        raw_idx = raw_w = None
        for el in draw.declaration:
            s = draw.streams.get(el.stream)
            if s is None or s.buffer is None:
                raise FormatError(f"{src}: element {el.describe()} uses an unbound stream")
            first = s.first + draw.base_vertex + draw.first_vertex
            vals = vx.decode_element(el, buf(s.buffer), s.stride, first, n, src)
            if el.usage == vx.POSITION and el.usage_index == 0:
                positions = [v[:3] for v in vals]
            elif el.usage == vx.NORMAL and el.usage_index == 0:
                normals = [v[:3] for v in vals]
            elif el.usage == vx.TANGENT and el.usage_index == 0:
                tangents = [tuple(v) + (1.0,) * (4 - len(v)) for v in vals]
            elif el.usage == vx.TEXCOORD:
                uvs.append((el.usage_index, [v[:2] for v in vals]))
            elif el.usage == vx.COLOR and el.usage_index == 0:
                colors = [tuple(v) for v in vals]
            elif el.usage == vx.BLENDINDICES:
                raw_idx = vals
            elif el.usage == vx.BLENDWEIGHT:
                raw_w = vals
        if positions is None:
            positions = self._animated_positions(draw, src)
        if raw_idx is not None and raw_w is not None:
            pal = draw.palette()
            joints, weights = [], []
            for iv, wv in zip(raw_idx, raw_w):
                js, ws = [], []
                for k in range(4):
                    row = int(iv[k])
                    slot = row // 3
                    if row % 3 or slot >= len(pal):
                        if wv[k] == 0:
                            js.append(pal[0] if pal else 0)
                            ws.append(0.0)
                            continue
                        raise FormatError(f"{src}: blend index {row} is not a palette row "
                                          f"(palette of {len(pal)})")
                    js.append(pal[slot])
                    ws.append(wv[k])
                joints.append(tuple(js))
                weights.append(tuple(ws))

        ib = buf(draw.index_buffer)
        start = draw.index_bind + draw.first_index
        if (start + draw.index_count) * 2 > len(ib):
            raise FormatError(f"{src}: indices {start}+{draw.index_count} run past "
                              f"{draw.index_buffer} ({len(ib)} bytes)")
        idx = list(struct.unpack_from(f">{draw.index_count}H", ib, start * 2))
        rel = [i - draw.first_vertex for i in idx]
        if rel and (min(rel) < 0 or max(rel) >= n):
            raise FormatError(f"{src}: index {min(idx)}..{max(idx)} outside vertices "
                              f"{draw.first_vertex}..{draw.first_vertex + n - 1}")
        tris, dropped = strip_to_triangles(rel)
        return DrawData(positions, normals, tangents,
                        [v for _, v in sorted(uvs, key=lambda t: t[0])], colors, joints,
                        weights, tris, dropped)


    def _animated_positions(self, draw: Draw, src: str, frame: int = 0):
        """Positions of a vertex-animated draw: frame ``frame`` of ``ANIM_0_FRAME_<f>_``.

        Such a draw binds a run-time stream (`StreamRef.buffer` None) instead of a
        POSITION element. A frame chunk is 4 words (1, 1, 1, vertex count), then one
        FLOAT3 per vertex (measured on ``streamedassets.big/Larvae.big``).
        """
        if not any(s.buffer is None for s in draw.streams.values()):
            raise FormatError(f"{src}: no POSITION element")
        try:
            data = self.entry(f"ANIM_0_FRAME_{frame}_").data()
        except FormatError:
            raise FormatError(f"{src}: no POSITION element and no ANIM_0_FRAME_{frame}_") from None
        count = struct.unpack_from(">I", data, 12)[0]
        if len(data) != 16 + 12 * count:
            raise FormatError(f"{src}: ANIM_0_FRAME_{frame}_ is {len(data)} bytes for "
                              f"{count} vertices")
        first = draw.base_vertex + draw.first_vertex
        if first + draw.vertex_count > count:
            raise FormatError(f"{src}: animation frame has {count} vertices, draw needs "
                              f"{first + draw.vertex_count}")
        return [struct.unpack_from(">3f", data, 16 + 12 * (first + v))
                for v in range(draw.vertex_count)]


def is_scene(arc: BigArchive) -> bool:
    """True if an archive is a scene (it has a ``SceneHeader`` entry)."""
    return any(e.name.lower() == "sceneheader" for e in arc.entries)


def unit_norm(q) -> float:
    return math.sqrt(sum(c * c for c in q))

"""Level collision: the walls and floors the player and zombies bump into (phase 10,
stretch).

Each zone archive holds ``MERGED_COLLISION.big``, a scene (`dr2kit.formats.scene`: a
skeleton of nodes, one per piece that needed its own) whose ``persistent.big`` holds
**Havok triangle meshes**, one group of entries per collision shape ``mesh<name>``. Most
names are ``COL_<node>``, the shape of the piece with node ``<node>`` (``meshCOL_z05_glass08``);
others name what they are for (``z03_COL_camera_only02``, ``z04_floor_COL_loco``: what
the camera, or only walkers, bump into ❓). A group is found by its Havok part, never by
the prefix (41 of CW's 1,049 shapes have no ``COL_``):

=============================== =============================================================
``mesh<name>`` (60 bytes)         8 big-endian words, then radius, bounds min, bounds max;
                                  word 1 (= word 6) is a node number of the collision scene
                                  (0: none), word 7 is 1, the rest 0 (placement:
                                  `convert.level.zone_collision`)
``… hkCollisionShapeMesh`` (44)   word 0: vertex count, word 1: triangle count, the rest kept
``… CollisionVertices``           vertex count × 3 big-endian floats
``… CollisionIndices``            triangle count × 3 indices, **1 byte each when the shape
                                  has at most 256 vertices, else 2** (big-endian)
``… CollisionMaterials``          one u32 per triangle (a surface type ❓; 0 on glass)
``… hkpMoppCode``, ``Welding*``   Havok's search tree and edge welding: kept, not read
=============================== =============================================================

``_COLLISIONLIST_`` lists the shapes (a 32-byte name, a hash, a word). Checked on every
zone of both games by ``dr2 census --levels`` (counts agree with the data sizes, every
index inside its shape). How the layout was found: docs/formats.md §Levels.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from ..container.big import BigArchive
from ..errors import FormatError

HEADER_SIZE = 60
SHAPE_SIZE = 44


@dataclass
class CollisionShape:
    """One collision mesh: its name without ``mesh`` and ``COL_``, vertices (relative to
    the piece node of that name, else world), triangles, surface values."""
    name: str
    vertices: list[tuple[float, float, float]]
    triangles: list[tuple[int, int, int]]
    materials: list[int] = field(default_factory=list)
    index_size: int = 2
    words: tuple = ()


def read_collision(arc: BigArchive, source: str = "MERGED_COLLISION.big") -> list[CollisionShape]:
    """Every collision shape of a ``MERGED_COLLISION.big`` archive (parsed)."""
    pers = next((e for e in arc.entries if e.name.lower() == "persistent.big"), None)
    if pers is None:
        raise FormatError(f"{source}: no persistent.big")
    p = BigArchive.parse(pers.data(), f"{source}/persistent.big")
    by = {e.name.lower(): e for e in p.entries}
    out = []
    for e in p.entries:
        if not e.name.endswith(" hkCollisionShapeMesh"):
            continue
        n = e.name[:-len(" hkCollisionShapeMesh")]
        src = f"{source}/{n}"
        if n.lower() not in by or not n.lower().startswith("mesh"):
            raise FormatError(f"{src}: a collision mesh without its header")
        head = by[n.lower()].data()
        if len(head) != HEADER_SIZE:
            raise FormatError(f"{src}: header is {len(head)} bytes, not {HEADER_SIZE}")
        words = struct.unpack_from(">8I", head)

        def part(name):
            x = by.get(f"{n} {name}".lower())
            if x is None:
                raise FormatError(f"{src}: no {name}")
            return x.data()
        shape = part("hkCollisionShapeMesh")
        if len(shape) != SHAPE_SIZE:
            raise FormatError(f"{src}: hkCollisionShapeMesh is {len(shape)} bytes")
        nv, nt = struct.unpack_from(">2I", shape)
        vdata, idata, mdata = part("CollisionVertices"), part("CollisionIndices"), \
            part("CollisionMaterials")
        if len(vdata) != nv * 12:
            raise FormatError(f"{src}: {len(vdata)} vertex bytes for {nv} vertices")
        if nt and len(idata) % (nt * 3):
            raise FormatError(f"{src}: {len(idata)} index bytes for {nt} triangles")
        size = len(idata) // (nt * 3) if nt else 1
        if size not in (1, 2):
            raise FormatError(f"{src}: {size}-byte indices")
        fmt = ">" + ("B" if size == 1 else "H") * (nt * 3)
        idx = struct.unpack_from(fmt, idata)
        if idx and max(idx) >= nv:
            raise FormatError(f"{src}: index {max(idx)} past the {nv} vertices")
        if len(mdata) != nt * 4:
            raise FormatError(f"{src}: {len(mdata)} material bytes for {nt} triangles")
        verts = [struct.unpack_from(">3f", vdata, i * 12) for i in range(nv)]
        name = n[len("mesh"):]
        if name.lower().startswith("col_"):
            name = name[len("col_"):]
        out.append(CollisionShape(name, verts,
                                  [tuple(idx[i:i + 3]) for i in range(0, len(idx), 3)],
                                  list(struct.unpack_from(f">{nt}I", mdata)), size, words))
    return out

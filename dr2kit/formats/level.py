"""Levels: the zone list and the placement table of each zone (phase 10).

A level is a folder ``data/models/environment/<level>/`` holding ``zonelist.big`` and
one archive per **zone** (``<level>_z05.big``: an area the game streams in and out as the
player moves). A zone holds its **pieces** (building parts, floors, signs: ordinary
scenes) and ``ZONE_ORGANIZATION.big``, whose ``ModelInstanceArray`` says **where each
piece goes**. This module reads those two binary tables; `dr2kit.convert.level` puts the
pieces in their places. Layouts, and how each field was checked: docs/formats.md §Levels.

Both tables are big-endian, like every payload (CLAUDE.md, hard-won rule 1). Every byte
that is not understood is kept (`Placement.tail`, `Zone.extra`) and written back, so
``to_bytes`` gives back the stored bytes (the census checks it), and the census names
any value of those bytes it has not seen before (rule 6).

The placement maths, checked on every placement of both games by the census (world
bounds = the piece's rotated local bounds + position)::

    world = rotation × (scale × local) + position
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field

from ..errors import FormatError

ZONE_RECORD = 132          # zonelist.big/ZoneList
PLACEMENT_RECORD = 208     # ZONE_ORGANIZATION.big/ModelInstanceArray
ZONEINFO_SIZE = 40


def _name(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("latin-1")


def _pad(name: str, size: int, source: str) -> bytes:
    b = name.encode("latin-1")
    if len(b) >= size:
        raise FormatError(f"{source}: name {name!r} is longer than {size - 1} bytes")
    return b + b"\0" * (size - len(b))


@dataclass
class Zone:
    """One record of ``zonelist.big/ZoneList``.

    ``name`` is ``<level>/<zone>`` as stored (Case West writes a backslash:
    ``living_research\\living_research_z01``); `zone` is the zone part only.
    ``flag`` is −1 for most zones (Case Zero's ``prologue_z10`` / ``_z11``, two small
    interiors, have 1 and 2; meaning unknown ❓). ``extra`` is the record's tail (zeros
    in every record of both games).
    """
    name: str
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    centre: tuple[float, float, float]
    radius: float
    flag: int
    extra: bytes = b"\0" * 24
    raw_name: bytes = b""

    @property
    def zone(self) -> str:
        return self.name.replace("\\", "/").rsplit("/", 1)[-1]

    @classmethod
    def parse(cls, rec: bytes, source: str = "<zone>") -> "Zone":
        if len(rec) != ZONE_RECORD:
            raise FormatError(f"{source}: zone record is {len(rec)} bytes, not {ZONE_RECORD}")
        f = struct.unpack_from(">10f", rec, 64)
        flag, = struct.unpack_from(">i", rec, 104)
        return cls(_name(rec[:64]), f[0:3], f[3:6], f[6:9], f[9], flag, bytes(rec[108:]),
                   bytes(rec[:64]))

    def to_bytes(self) -> bytes:
        name = self.raw_name if _name(self.raw_name) == self.name else _pad(self.name, 64, "zone")
        return (name + struct.pack(">10f", *self.bounds_min, *self.bounds_max, *self.centre,
                                   self.radius)
                + struct.pack(">i", self.flag) + self.extra)


def read_zone_list(num_zones: bytes, zone_list: bytes, source: str = "zonelist.big") -> list[Zone]:
    """The zones of ``zonelist.big`` from its ``NumZones`` and ``ZoneList`` entries."""
    if len(num_zones) != 4:
        raise FormatError(f"{source}: NumZones is {len(num_zones)} bytes, not 4")
    n, = struct.unpack(">I", num_zones)
    if len(zone_list) != n * ZONE_RECORD:
        raise FormatError(f"{source}: ZoneList is {len(zone_list)} bytes; {n} zones of "
                          f"{ZONE_RECORD} would be {n * ZONE_RECORD}")
    return [Zone.parse(zone_list[i * ZONE_RECORD:(i + 1) * ZONE_RECORD], f"{source}[{i}]")
            for i in range(n)]


@dataclass
class Placement:
    """One piece put in the world: a record of ``ModelInstanceArray``.

    ``piece`` names the piece's archive in the zone (``z05_bowling_struc`` →
    ``z05_bowling_struc.big``); ``name2`` equals it in every record seen. Bounds,
    centre and radius are in world space. ``draw_distance`` (20…110 m) and
    ``lod_distance`` (5…20 m) are what their values suggest, not proven ❓. ``index`` is
    the piece's number in the zone. ``flags`` (+144) is 0, or 0x20 on 71 placements of
    both games: trees, foliage, spinning fans, some lights and ceiling beams (meaning
    unknown ❓; things that move?). ``tail`` keeps the bytes whose meaning is unknown
    (+152…+167, +172…+195, +200…+207: see `UNKNOWN_TAIL`).
    """
    piece: str
    name2: str
    scale: tuple[float, float, float]
    rotation: tuple[float, float, float, float]       # quaternion x, y, z, w
    position: tuple[float, float, float]
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    centre: tuple[float, float, float]
    radius: float
    draw_distance: float
    lod_distance: float
    index: int
    flags: int
    tail: bytes
    raw_names: bytes = b""

    @classmethod
    def parse(cls, rec: bytes, source: str = "<placement>") -> "Placement":
        if len(rec) != PLACEMENT_RECORD:
            raise FormatError(f"{source}: placement record is {len(rec)} bytes, "
                              f"not {PLACEMENT_RECORD}")
        f = struct.unpack_from(">20f", rec, 64)
        draw, = struct.unpack_from(">f", rec, 148)
        lod, = struct.unpack_from(">f", rec, 168)
        index, = struct.unpack_from(">I", rec, 196)
        flags, = struct.unpack_from(">I", rec, 144)
        return cls(_name(rec[:32]), _name(rec[32:64]), f[0:3], f[3:7], f[7:10], f[10:13],
                   f[13:16], f[16:19], f[19], draw, lod, index, flags, _tail(rec),
                   bytes(rec[:64]))

    def to_bytes(self) -> bytes:
        names = self.raw_names
        if _name(names[:32]) != self.piece or _name(names[32:64]) != self.name2:
            names = _pad(self.piece, 32, "placement") + _pad(self.name2, 32, "placement")
        rec = bytearray(names + struct.pack(">20f", *self.scale, *self.rotation, *self.position,
                                            *self.bounds_min, *self.bounds_max, *self.centre,
                                            self.radius) + bytes(PLACEMENT_RECORD - 144))
        k = 0
        for start, end in UNKNOWN_TAIL:
            rec[start:end] = self.tail[k:k + end - start]
            k += end - start
        struct.pack_into(">f", rec, 148, self.draw_distance)
        struct.pack_into(">f", rec, 168, self.lod_distance)
        struct.pack_into(">I", rec, 196, self.index)
        struct.pack_into(">I", rec, 144, self.flags)
        return bytes(rec)

    def matrix(self) -> list[list[float]]:
        """The 4×4 world matrix (rows): rotation × scale, then position."""
        r = quat_matrix(self.rotation)
        s = self.scale
        return [[r[i][0] * s[0], r[i][1] * s[1], r[i][2] * s[2], self.position[i]]
                for i in range(3)] + [[0.0, 0.0, 0.0, 1.0]]

    def to_world(self, p) -> tuple[float, float, float]:
        """A point of the piece (its own coordinates) in the world."""
        m = self.matrix()
        return tuple(m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + m[i][3]
                     for i in range(3))


# Byte ranges of the record whose meaning is unknown: kept as they are (rule 6).
# +152…+167 are 0, 0, 0xFFFFFFFF, 0 in every record of both games; +172…+195 and
# +200…+207 are zeros (the census counts any other value).
UNKNOWN_TAIL = ((152, 168), (172, 196), (200, 208))
EXPECTED_TAIL = b"\0" * 8 + b"\xff" * 4 + b"\0" * 4 + b"\0" * 24 + b"\0" * 8
FLAG_VALUES = (0, 0x20)            # +144 values seen (census)


def _tail(rec: bytes) -> bytes:
    return b"".join(rec[s:e] for s, e in UNKNOWN_TAIL)


def quat_matrix(q) -> list[list[float]]:
    """A unit quaternion ``(x, y, z, w)`` as a 3×3 rotation matrix (rows)."""
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


@dataclass
class ZoneOrganization:
    """``ZONE_ORGANIZATION.big``: the zone's placements and bounds.

    ``dynamic`` holds the raw ``ModelInstanceArray_Dynamic`` (empty in every zone of
    both games). ``info`` is ``_ZONEINFO_``: min, max, centre, radius, the same values
    as the zone's `Zone` record (checked by the census).
    """
    placements: list[Placement] = field(default_factory=list)
    dynamic: bytes = b""
    info: tuple[float, ...] | None = None

    @classmethod
    def from_entries(cls, entries: dict[str, bytes], source: str = "ZONE_ORGANIZATION.big"
                     ) -> "ZoneOrganization":
        """Parse from the archive's entries, by name (``ModelInstanceArray``, …)."""
        def get(name):
            for k, v in entries.items():
                if k.lower() == name.lower():
                    return v
            raise FormatError(f"{source}: no {name} entry")
        n, = struct.unpack(">I", get("NumModelInstance"))
        arr = get("ModelInstanceArray")
        if len(arr) != n * PLACEMENT_RECORD:
            raise FormatError(f"{source}: ModelInstanceArray is {len(arr)} bytes; {n} "
                              f"records of {PLACEMENT_RECORD} would be {n * PLACEMENT_RECORD}")
        out = cls([Placement.parse(arr[i * PLACEMENT_RECORD:(i + 1) * PLACEMENT_RECORD],
                                   f"{source}[{i}]") for i in range(n)])
        nd, = struct.unpack(">I", get("NumModelInstance_Dynamic"))
        out.dynamic = get("ModelInstanceArray_Dynamic")
        if nd and len(out.dynamic) != nd * PLACEMENT_RECORD:
            raise FormatError(f"{source}: {nd} dynamic placements in {len(out.dynamic)} bytes")
        info = get("_ZONEINFO_")
        if len(info) != ZONEINFO_SIZE:
            raise FormatError(f"{source}: _ZONEINFO_ is {len(info)} bytes, not {ZONEINFO_SIZE}")
        out.info = struct.unpack(">10f", info)
        return out

    def placements_bytes(self) -> bytes:
        """``ModelInstanceArray`` written back."""
        return b"".join(p.to_bytes() for p in self.placements)

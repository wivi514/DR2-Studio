"""Animations: the ``.anm`` files of ``data/anim/**`` and the weapon banks (phases 13.2, 14).

Why: to show Chuck holding a weapon the way the game does (frozen in the idle animation
of that kind of item, phase 13.2), then **swinging** it and every other move playing in
Studio and in Blender (phase 14): every key of every ``.anm`` is read the way the game
reads it (docs/formats.md §Animations).

Where they are: ``data/anim/default.big`` holds one archive per skeleton part,
``fullbody.big``, ``root.big``, ``hand.big``, ``upperbody.big``, ``facial.big``; each holds
one ``.anm`` per move, by name (``male_idle_combat.anm``). The track numbers are node
indices of the matching skeleton file (`SKELETONS`: ``fullbody`` →
``data/skeleton/playerfullbody.big``; ``hand`` → ``playerhand.big``…), so a track is
applied to a model's node **by name**. A weapon's moves are ``anm_<bank>.big`` in
``streamedassets.big`` (``AnimBankName``), with the same two parts ``root`` / ``fullbody``.

Layout (big-endian; every ``.anm`` of both games, `census`):

```
0x00 u32   skeleton id     one value per skeleton part (fullbody 0x24F628C0, root
                           0xAD2B0240, hand 0x70CB2D80…); the game refuses an animation
                           whose id differs from the skeleton's ("the anim data does not
                           match the skeleton that it is being played on!")
0x04 f32   length          seconds (frames - 1) / rate
0x08 f32   rate            frames per second (30, 60)
0x0C u16   mask offset     = 0x16 + 2 × tracks (right after the table and ``FF 00``)
0x0E u16   data offset     the first keys: the mask's end rounded up to 4 bytes; **0**
                           when that is past 0xFFFF (26 long cutscenes of both games)
0x10 u16   frames
0x12 u16   tracks
0x14       tracks × (u8 node, u8 kind)   in the order of `ORDER`
           FF 00
mask       frames × ceil(tracks / 8) bytes: bit t of frame f set = track t has a key
           at frame f (every track has keys at the first two and last two frames)
data       the first key of every track, in track order; then the later keys (below)
```

Track kinds (`KINDS`), first key / later keys:

* ``0x01`` rotation, animated. **8-byte key** (the first key, and a later key whose top
  bit is 0): one 64-bit number, x = bits 62-47 (16 bits, /32767), y = bits 46-32 (15
  bits, /16383), z = bits 31-16 and w = bits 15-0 (/32767). **4-byte key** (top bit 1):
  a change from the track's previous key, x = bits 30-23 and z, w = the two low bytes
  (signed, /12700), y = bits 22-16 (7 bits, /6300). Either way the game then scales the
  result by 1.5 − |q|²/2 (one Newton step to unit length).
* ``0x02`` translation, animated. First key: three floats (metres). Later key: **8
  bytes** (top bit 1), three 21-bit signed numbers (bits 62-42, 41-21, 20-0) × 300 /
  (2²⁰ − 1), the position itself (not a change); or, top bit 0, three floats.
* ``0x12`` translation, fixed: three floats. ``0x31`` rotation, fixed: four signed
  16-bit numbers (/32767), then normalised.
* ``0x05`` a camera (``…~cameras.anm``): 32 bytes per key (a float quaternion, a position
  and one float, field of view ❓). ``0x22``: three floats per key (cutscenes, ❓).
  ``0x11``: four floats, then later keys of one signed 16-bit number (× 9.5877e-05,
  the fourth value; none in either game).

**Which key comes next** (`Animation.decode`): the game steps through the frames; at
frame f, for every track (in table order) with a key at f, it reads that track's *next*
key (the next frame whose mask bit is set), 4-aligned (2 for ``0x11``). So the later
keys are stored in the order they are needed, not frame by frame. Between keys a track
is interpolated (`Clip.pose`).

How it was found (2026-10-12/13): the first-key layout from the hand poses
(``male_hand_hold_2x4_pose.anm``) and rest values; the later keys from the game's own
decoder in the executable (CZ ``0x827B5090`` steps a frame, ``0x8279AB98`` reads a
rotation key, ``0x8279AF68`` a translation key, ``0x8279B0B0`` the first keys; the scales
are floats at ``0x820B28C4``-``0x820B28D4``). Checked: every ``.anm`` of both games is
read to its last byte, and every rotation key is within 0.0002 of unit length before the
game's rescale (`census`).
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field

from ..errors import FormatError

HEADER = struct.Struct(">IffHHHH")
HEADER_SIZE = 0x14

ROT = 0x01
TRANS = 0x02
FIXED_TRANS = 0x12
FIXED_ROT = 0x31
CAMERA = 0x05
TRANS_22 = 0x22
SCALAR_11 = 0x11
KINDS = {                    # kind -> (what, size of the first key in bytes)
    ROT: ("rotation", 8),
    TRANS: ("translation", 12),
    FIXED_TRANS: ("translation", 12),
    FIXED_ROT: ("rotation", 8),
    CAMERA: ("camera", 32),
    TRANS_22: ("translation", 12),
    SCALAR_11: ("values", 16),
}
# The order the game's decoder walks the tracks in (each kind's tracks together).
ORDER = (TRANS_22, TRANS, ROT, CAMERA, SCALAR_11, FIXED_TRANS, FIXED_ROT)

# The executable's scales (module docstring).
DELTA_XZW = 1 / 12700
DELTA_Y = 1 / 6300
TRANS_SCALE = 300 / 1048575
SCALAR_SCALE = 9.5876726845745e-05

# The skeleton file each part's track numbers refer to (data/anim/default.big/<part>.big).
SKELETONS = {
    "fullbody": "data/skeleton/playerfullbody.big",
    "root": "data/skeleton/playerroot.big",
    "hand": "data/skeleton/playerhand.big",
    "upperbody": "data/skeleton/playerupperbdy.big",
    "facial": "data/skeleton/playerface.big",
}
UNIT_TOLERANCE = 0.003

Quat = tuple[float, float, float, float]


def _signed(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def _rescale(q) -> Quat:
    """The game's one Newton step towards unit length: × (1.5 − |q|²/2)."""
    f = 1.5 - 0.5 * sum(c * c for c in q)
    return tuple(c * f for c in q)


def packed_rotation(data: bytes, at: int = 0) -> Quat:
    """An 8-byte rotation key (module docstring) as (x, y, z, w), not rescaled."""
    v = int.from_bytes(data[at:at + 8], "big")
    return (_signed(v >> 47, 16) / 32767, _signed(v >> 32, 15) / 16383,
            _signed(v >> 16, 16) / 32767, _signed(v, 16) / 32767)


def delta_rotation(prev: Quat, word: int) -> Quat:
    """A 4-byte rotation key (top bit set): ``prev`` plus the change it holds, not
    rescaled."""
    return (prev[0] + _signed(word >> 23, 8) * DELTA_XZW, prev[1] + _signed(word >> 16, 7) * DELTA_Y,
            prev[2] + _signed(word >> 8, 8) * DELTA_XZW, prev[3] + _signed(word, 8) * DELTA_XZW)


def packed_translation(data: bytes, at: int = 0) -> tuple[float, float, float]:
    """An 8-byte translation key (top bit set): three 21-bit numbers, metres."""
    v = int.from_bytes(data[at:at + 8], "big")
    return tuple(_signed(v >> sh, 21) * TRANS_SCALE for sh in (42, 21, 0))


def short_rotation(data: bytes, at: int = 0) -> Quat:
    """A fixed rotation (four signed 16-bit numbers / 32767) as (x, y, z, w)."""
    return tuple(v / 32767 for v in struct.unpack_from(">4h", data, at))


def nlerp(a: Quat, b: Quat, t: float) -> Quat:
    """Rotation between ``a`` and ``b`` (the shorter way round), normalised."""
    if sum(x * y for x, y in zip(a, b)) < 0:
        b = tuple(-c for c in b)
    q = tuple(x + (y - x) * t for x, y in zip(a, b))
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return tuple(c / n for c in q)


@dataclass
class Track:
    """One track: the skeleton node it moves (an index into the part's skeleton file)
    and its kind (`KINDS`)."""
    node: int
    kind: int

    @property
    def what(self) -> str:
        return KINDS[self.kind][0] if self.kind in KINDS else "unknown"

    @property
    def animated(self) -> bool:
        return self.kind in (ROT, TRANS, CAMERA, TRANS_22, SCALAR_11)


@dataclass
class Pose:
    """Local transforms by skeleton node index: what the animation sets at one frame.
    A node missing from both keeps its rest value."""
    rotations: dict[int, Quat] = field(default_factory=dict)
    translations: dict[int, tuple[float, float, float]] = field(default_factory=dict)


@dataclass
class Channel:
    """Every key of one track: the frames it has keys at and the values there
    (rotations (x, y, z, w), translations (x, y, z); a camera 8 numbers)."""
    track: Track
    frames: list[int]
    values: list[tuple]

    def at(self, frame: float) -> tuple:
        """The value at ``frame`` (a float): the keys either side, interpolated."""
        fr = self.frames
        if len(fr) == 1 or frame <= fr[0]:
            return self.values[0]
        if frame >= fr[-1]:
            return self.values[-1]
        lo, hi = 0, len(fr) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if fr[mid] <= frame:
                lo = mid
            else:
                hi = mid
        t = (frame - fr[lo]) / (fr[hi] - fr[lo])
        a, b = self.values[lo], self.values[hi]
        if self.track.what == "rotation":
            return nlerp(a, b, t)
        return tuple(x + (y - x) * t for x, y in zip(a, b))


@dataclass
class Clip:
    """A whole animation (`Animation.decode`): one `Channel` per track."""
    rate: float
    frames: int
    channels: list[Channel]

    @property
    def length(self) -> float:
        return (self.frames - 1) / self.rate if self.rate else 0.0

    def pose(self, frame: float) -> Pose:
        """The pose at ``frame`` (0 … frames − 1, fractions interpolate)."""
        out = Pose()
        for ch in self.channels:
            what = ch.track.what
            if what == "rotation":
                out.rotations[ch.track.node] = ch.at(frame)
            elif what == "translation":
                out.translations[ch.track.node] = ch.at(frame)
        return out


@dataclass
class Animation:
    """One ``.anm`` (module docstring). ``data`` is kept whole; `decode` reads every key,
    `first_pose` only the first ones."""
    skeleton_id: int
    length: float
    rate: float
    frames: int
    tracks: list[Track]
    mask_offset: int
    data_offset: int
    data: bytes
    source: str = "<anm>"

    @classmethod
    def parse(cls, data: bytes, source: str = "<anm>") -> "Animation":
        if len(data) < HEADER_SIZE:
            raise FormatError(f"{source}: {len(data)} bytes, too short for an animation")
        sid, length, rate, mask_off, data_off, frames, count = HEADER.unpack_from(data)
        end = HEADER_SIZE + 2 * count
        if end + 2 > len(data):
            raise FormatError(f"{source}: {count} tracks run past the end")
        tracks = [Track(data[HEADER_SIZE + 2 * i], data[HEADER_SIZE + 2 * i + 1])
                  for i in range(count)]
        if data[end:end + 2] != b"\xff\x00":
            raise FormatError(f"{source}: no FF 00 after the track table "
                              f"(found {data[end:end + 2].hex()})")
        if mask_off != end + 2:
            raise FormatError(f"{source}: key mask at {mask_off:#x}, expected {end + 2:#x}")
        keys_at = (mask_off + frames * ((count + 7) // 8) + 3) // 4 * 4
        if data_off not in (keys_at, 0) or keys_at > len(data):
            raise FormatError(f"{source}: first keys at {data_off:#x}, expected {keys_at:#x} "
                              f"(the key mask's end, 4-aligned)")
        data_off = keys_at              # stored as 0 when it doesn't fit 16 bits
        unknown = sorted({t.kind for t in tracks if t.kind not in KINDS})
        if unknown:
            raise FormatError(f"{source}: unknown track kind(s) "
                              + ", ".join(f"{k:#04x}" for k in unknown))
        order = [ORDER.index(t.kind) for t in tracks]
        if order != sorted(order):
            raise FormatError(f"{source}: tracks not in the game's kind order "
                              f"({', '.join(f'{k:#04x}' for k in ORDER)})")
        return cls(sid, length, rate, frames, tracks, mask_off, data_off, data, source)

    @property
    def _width(self) -> int:
        return (len(self.tracks) + 7) // 8

    def keys(self, track: int) -> list[int]:
        """The frames at which track number ``track`` has a key (the mask)."""
        width = self._width
        byte, bit = divmod(track, 8)
        return [f for f in range(self.frames)
                if self.data[self.mask_offset + f * width + byte] >> bit & 1]

    def _first_keys(self) -> tuple[list[tuple], int]:
        """Every track's first key (not rescaled) and where the later keys start."""
        d, at, out = self.data, self.data_offset, []
        for i, t in enumerate(self.tracks):
            size = KINDS[t.kind][1]
            if at + size > len(d):
                raise FormatError(f"{self.source}: the first keys run past the end "
                                  f"(track {i})")
            if t.kind == ROT:
                out.append(packed_rotation(d, at))
            elif t.kind == FIXED_ROT:
                out.append(short_rotation(d, at))
            else:
                out.append(struct.unpack_from(f">{size // 4}f", d, at))
            at += size
        return out, at

    def _unit(self, i: int, q, frame: int) -> Quat:
        n = sum(c * c for c in q)
        if abs(n - 1) > UNIT_TOLERANCE:
            raise FormatError(f"{self.source}: track {i} (node {self.tracks[i].node}) "
                              f"rotation at frame {frame} is not a unit quaternion "
                              f"(|q|² = {n:.3f}): this animation's layout is not read")
        return q

    def first_pose(self) -> Pose:
        """Every track's first key (frame 0) as a `Pose`. Raises `FormatError` when a
        rotation does not come out a unit quaternion or the keys run past the end."""
        first, _ = self._first_keys()
        pose = Pose()
        for i, (t, v) in enumerate(zip(self.tracks, first)):
            if t.what == "rotation":
                q = self._unit(i, v, 0)
                n = math.sqrt(sum(c * c for c in q))
                pose.rotations[t.node] = tuple(c / n for c in q)
            elif t.what == "translation":
                pose.translations[t.node] = tuple(v)
        return pose

    def decode(self) -> Clip:
        """Every key of every track (module docstring: the game's own order), checked:
        the keys must end at the file's last byte and every rotation must be close to
        unit length before the rescale (`FormatError` otherwise)."""
        d = self.data
        first, at = self._first_keys()
        n = len(self.tracks)
        width, mask = self._width, self.mask_offset
        channels = []
        for i, (t, v) in enumerate(zip(self.tracks, first)):
            if t.what == "rotation":
                v = _rescale(self._unit(i, v, 0))
                if t.kind == FIXED_ROT:
                    m = math.sqrt(sum(c * c for c in v)) or 1.0
                    v = tuple(c / m for c in v)
            channels.append(Channel(t, [0], [tuple(v)]))
        bits = [[d[mask + f * width + (i >> 3)] >> (i & 7) & 1 for i in range(n)]
                for f in range(self.frames)]
        for f in range(self.frames - 1):
            row = bits[f]
            for i, t in enumerate(self.tracks):
                if not row[i] or t.kind in (FIXED_TRANS, FIXED_ROT):
                    continue
                g = f + 1
                while g < self.frames and not bits[g][i]:
                    g += 1
                if g >= self.frames:
                    raise FormatError(f"{self.source}: track {i} has a key at frame {f} "
                                      f"and none after it")
                ch = channels[i]
                if t.kind == SCALAR_11:
                    at = (at + 1) & ~1
                    if at + 2 > len(d):
                        raise FormatError(f"{self.source}: keys run past the end (frame {f})")
                    prev = ch.values[-1]
                    value = (*prev[:3], struct.unpack_from(">h", d, at)[0] * SCALAR_SCALE)
                    at += 2
                else:
                    at = (at + 3) & ~3
                    if at + 4 > len(d):
                        raise FormatError(f"{self.source}: keys run past the end (frame {f})")
                    top = d[at] >> 7
                    if t.kind == ROT:
                        if top:
                            q = delta_rotation(ch.values[-1],
                                               int.from_bytes(d[at:at + 4], "big"))
                            at += 4
                        else:
                            q = packed_rotation(d, at)
                            at += 8
                        value = _rescale(self._unit(i, q, g))
                    elif t.kind == TRANS and top:
                        value = packed_translation(d, at)
                        at += 8
                    else:
                        size = KINDS[t.kind][1]
                        value = struct.unpack_from(f">{size // 4}f", d, at)
                        at += size
                    if at > len(d):
                        raise FormatError(f"{self.source}: keys run past the end (frame {f})")
                ch.frames.append(g)
                ch.values.append(tuple(value))
        if at != len(d):
            raise FormatError(f"{self.source}: the keys end at {at:#x}, the file at "
                              f"{len(d):#x}: this animation's layout is not read")
        return Clip(self.rate, self.frames, channels)


def part_of(vpath: str) -> str | None:
    """Which skeleton part an animation's vpath belongs to (``…/hand.big/x.anm`` →
    ``hand``), from the archive that holds it."""
    parts = vpath.replace("\\", "/").lower().split("/")
    for p in reversed(parts[:-1]):
        name = p.removesuffix(".big")
        if name in SKELETONS:
            return name
    return None


def census(tree) -> dict:
    """Every ``.anm`` of a game: counts by track kind and keys, and every file whose
    header or keys don't read (named). A gate: every key of every animation must read,
    to the file's last byte."""
    from ..container.vpath import entry_components
    files = frames = keys = 0
    kinds: dict[int, int] = {}
    unread: list[str] = []
    problems: list[str] = []
    for vp, arc, _depth in tree.walk_archives(on_error=lambda v, e: problems.append(
            f"{v}: {e}")):
        for comp, e in zip(entry_components(arc), arc.entries):
            if not comp.lower().endswith(".anm"):
                continue
            path = f"{vp}/{comp}"
            data = e.data()
            if not data:                  # a few empty entries (helicopter props)
                unread.append(f"{path}: empty")
                continue
            files += 1
            try:
                a = Animation.parse(data, path)
                frames += a.frames
                for t in a.tracks:
                    kinds[t.kind] = kinds.get(t.kind, 0) + 1
                keys += sum(len(c.frames) for c in a.decode().channels)
            except FormatError as ex:
                problems.append(str(ex))
    return {"files": files, "frames": frames, "keys": keys, "kinds": kinds,
            "unread": unread, "problems": problems}

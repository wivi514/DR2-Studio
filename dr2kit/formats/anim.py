"""Animations: the ``.anm`` files of ``data/anim/**`` and the weapon banks (phase 13.2).

Why: to show Chuck holding a weapon the way the game does, frozen in the idle animation
of that kind of item (a box held in both arms, a spear across the body, a sword at the
side), so a modder can line a new weapon up with his hands before going in game
(docs/phase13-kickoff.md §Phase 13.2). Full playback (Chuck swinging) needs the later
keys, which are packed and not read yet; the **first frame** of every gameplay animation
is read, and that is the frozen pose.

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
                           0xAD2B0240, hand 0x70CB2D80…) ❓ how it is made
0x04 f32   length          seconds (frames - 1) / rate
0x08 f32   rate            frames per second (30, 60)
0x0C u16   mask offset     = 0x16 + 2 × tracks (right after the table and ``FF 00``)
0x0E u16   data offset     the first keys: the mask's end rounded up to 4 bytes; **0**
                           when that is past 0xFFFF (26 long cutscenes of both games)
0x10 u16   frames
0x12 u16   tracks
0x14       tracks × (u8 node, u8 kind)
           FF 00
mask       frames × ceil(tracks / 8) bytes: bit t of frame f set = track t has a key
           at frame f (every track has keys at the first two and last two frames)
data       the first key of every track, in track order (`KINDS`), then the later keys
           of the animated tracks, packed ❓ (not read)
```

Track kinds (`KINDS`; tracks are sorted by kind: animated rotations, animated
translations, fixed translations, fixed rotations):

* ``0x01`` rotation, animated. First key **8 bytes**: x and y as 15-bit signed numbers
  (/16384) in the low bits of two 16-bit words (each word's top bit is a flag ❓), z and
  w as signed 16-bit (/32767). Checked: every first key of both games (CZ 74,738, CW
  80,894) comes out a unit quaternion (`census`).
* ``0x02`` translation, animated. First key: three floats (metres).
* ``0x12`` translation, fixed: three floats.
* ``0x31`` rotation, fixed: four signed 16-bit numbers (/32767), x y z w.
* ``0x05`` a camera (``…~cameras.anm``): 32 bytes per frame, a float quaternion, a
  position and one float (field of view ❓).
* ``0x22`` (65 tracks of CZ cutscenes, ❓): taken as three floats (the rotations after
  it then read as unit quaternions in every one).

How it was found (2026-10-12): the hand poses (``male_hand_hold_2x4_pose.anm``: 30
fixed rotations) end exactly after 30 × 8 bytes; a fixed rotation equals the skeleton's
rest rotation on nodes that don't move (``jiggle`` = (-½, -½, -½, ½)); a fixed
translation equals the node's rest offset; the animated rotations' first keys became
unit quaternions only with x and y read as 15 bits. **Not read:** the later keys (an
animated translation's are 8 bytes, three 21-bit numbers; a rotation's 4 bytes, packed;
their order follows when each key is needed, not the frame order).
"""

from __future__ import annotations

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
KINDS = {                    # kind -> (what, size of the first key in bytes)
    ROT: ("rotation", 8),
    TRANS: ("translation", 12),
    FIXED_TRANS: ("translation", 12),
    FIXED_ROT: ("rotation", 8),
    CAMERA: ("camera", 32),
    TRANS_22: ("translation", 12),
}

# The skeleton file each part's track numbers refer to (data/anim/default.big/<part>.big).
SKELETONS = {
    "fullbody": "data/skeleton/playerfullbody.big",
    "root": "data/skeleton/playerroot.big",
    "hand": "data/skeleton/playerhand.big",
    "upperbody": "data/skeleton/playerupperbdy.big",
    "facial": "data/skeleton/playerface.big",
}
UNIT_TOLERANCE = 0.003


def _s15(v: int) -> int:
    v &= 0x7FFF
    return v - 0x8000 if v & 0x4000 else v


def packed_rotation(data: bytes, at: int = 0) -> tuple[float, float, float, float]:
    """An animated rotation's first key (8 bytes, module docstring) as (x, y, z, w)."""
    a, b, c, w = struct.unpack_from(">HHhh", data, at)
    return (_s15(a) / 16384, _s15(b) / 16384, c / 32767, w / 32767)


def short_rotation(data: bytes, at: int = 0) -> tuple[float, float, float, float]:
    """A fixed rotation (four signed 16-bit numbers / 32767) as (x, y, z, w)."""
    return tuple(v / 32767 for v in struct.unpack_from(">4h", data, at))


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
        return self.kind in (ROT, TRANS)


@dataclass
class Pose:
    """Local transforms by skeleton node index: what the animation sets at one frame.
    A node missing from both keeps its rest value."""
    rotations: dict[int, tuple[float, float, float, float]] = field(default_factory=dict)
    translations: dict[int, tuple[float, float, float]] = field(default_factory=dict)


@dataclass
class Animation:
    """One ``.anm`` (module docstring). ``data`` is kept whole; only the header, the
    track table, the key mask and the first keys are read."""
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
        return cls(sid, length, rate, frames, tracks, mask_off, data_off, data, source)

    def keys(self, track: int) -> list[int]:
        """The frames at which track number ``track`` has a key (the mask)."""
        width = (len(self.tracks) + 7) // 8
        byte, bit = divmod(track, 8)
        return [f for f in range(self.frames)
                if self.data[self.mask_offset + f * width + byte] >> bit & 1]

    def first_pose(self) -> Pose:
        """Every track's first key (frame 0) as a `Pose`. Raises `FormatError` when a
        rotation does not come out a unit quaternion (the long cutscenes) or the keys run
        past the end."""
        pose = Pose()
        at = self.data_offset
        for i, t in enumerate(self.tracks):
            size = KINDS[t.kind][1]
            if at + size > len(self.data):
                raise FormatError(f"{self.source}: the first keys run past the end "
                                  f"(track {i})")
            if t.kind == ROT:
                q = packed_rotation(self.data, at)
            elif t.kind == FIXED_ROT:
                q = short_rotation(self.data, at)
            else:
                q = None
            if q is not None:
                n = sum(c * c for c in q)
                if abs(n - 1) > UNIT_TOLERANCE:
                    raise FormatError(f"{self.source}: track {i} (node {t.node}) first "
                                      f"rotation is not a unit quaternion (|q|² = {n:.3f}): "
                                      f"this animation's layout is not read")
                n = n ** 0.5
                pose.rotations[t.node] = tuple(c / n for c in q)
            elif t.kind in (TRANS, FIXED_TRANS, TRANS_22):
                pose.translations[t.node] = struct.unpack_from(">3f", self.data, at)
            at += size
        return pose


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
    """Every ``.anm`` of a game: counts by track kind, and every file whose header or
    first keys don't read (named). A gate: gameplay animations must all read."""
    from ..container.vpath import entry_components
    files = frames = 0
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
                a.first_pose()
            except FormatError as ex:
                problems.append(str(ex))
    return {"files": files, "frames": frames, "kinds": kinds, "unread": unread,
            "problems": problems}

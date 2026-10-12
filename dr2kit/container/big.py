"""The `.big` archive: the game's container format. Read, edit and write it back.

Almost every asset of both games lives in a `.big`, and a `.big` entry can itself be a
`.big` (a model inside a pack, a ``persistent.big`` inside a model). Full layout and how
each fact was verified: docs/formats.md, "`.big` container".

Key facts (all measured over every archive of Case Zero and Case West, nested ones too):

* The header and index are **little-endian**; everything inside an entry is
  **big-endian** (CLAUDE.md, hard-won rule 1).
* Names are **variable-length**, NUL-terminated, read from each entry's own
  ``name_offset`` (rule 2). In every shipped archive they sit back to back in index
  order, and the payload region starts right after the last NUL.
* ``size`` is the **stored** length, ``size2`` the **uncompressed** length; the last
  index word (``compression`` here, ``resv`` in the recomp's tools) is 2 for an
  LZX-compressed entry and 0 for a stored one (rule 3).
* The ``hash`` is the engine's string hash of the **lower-cased** name
  (`dr2kit.hashing.name_hash`).
* Payloads are in index order. Every gap between payloads is zero bytes of alignment
  padding: each payload starts at the next multiple of some power of two (2 to 0x800)
  that depends on the archive and the entry. No archive has bytes after its last payload.
* Names repeat inside one archive (a scene has several ``Combined Vertices``), so
  entries are addressed by **position** first; names are a convenience.

Round trip: ``BigArchive.parse(data).to_bytes() == data`` for every archive of both
games (the phase 1 gate, ``dr2 roundtrip``). The writer gets there without storing the
original offsets: it lays payloads out in order, and starts each one at the next multiple
of its *alignment*, the largest power of two (at most 0x800) that divided its original
offset. The true requirement always divides the original offset, so this is never
smaller than what the game needs, and on an unedited archive it lands every payload
exactly where it was. Edited entries keep their alignment, so a payload after a resized
one stays aligned.

Origin: ported from the CZ recomp's ``tools/big_list.py`` (listing, parse checks) and
``tools/gen_pc_options.py`` (``read_big``/``write_big``), same author.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import FormatError, LzxError
from ..hashing import entry_hash
from . import xcompress

MAGIC = b"\x06\x05\x04\x03"
HEADER = struct.Struct("<6I")       # magic, data_start, total_size, count, header_size, names_offset
INDEX_ENTRY = struct.Struct("<7I")  # name_offset, hash, size, size2, data_offset, flags, compression
HEADER_SIZE = 0x18                  # in every archive of both games
MAX_ALIGNMENT = 0x800               # the largest payload alignment seen in either game

# Values of the index's last word.
STORED = 0
ZLIB = 1    # PC releases only, per mariokart64n's MaxScript; never seen on 360 (census)
LZX = 2


def _lowbit(n: int) -> int:
    return n & -n if n else MAX_ALIGNMENT


def _align_up(n: int, a: int) -> int:
    return (n + a - 1) // a * a


@dataclass(eq=False)
class BigEntry:
    """One entry of a `.big` archive.

    ``stored`` holds the bytes exactly as they sit in the archive: for a compressed entry
    that is the compressed stream, not the asset. Use `data()` to get the asset and
    `set_data()` to replace it (both handle compression).

    ``hash`` keeps the value read from the file so writes are byte-identical. If you
    change ``name``, set ``hash = None`` so the writer computes the new one.
    """

    name: str
    stored: bytes
    size2: int
    flags: int = 0
    compression: int = STORED
    hash: int | None = None   # None means "compute from the name when writing"
    alignment: int = 4
    # As read from the file; informational (the writer recomputes offsets).
    index: int = -1
    data_offset: int = 0

    @property
    def size(self) -> int:
        """Stored length in bytes (the index's ``size``)."""
        return len(self.stored)

    @property
    def compressed(self) -> bool:
        return self.compression != STORED

    @property
    def ext(self) -> str:
        """Lower-case extension without the dot (``"bct"``), or ``""`` for none.

        Only 1-3 letters or digits count: scene node names contain dots too
        (``dummy01.l_thigh``), and every real extension in both games is that short.
        """
        stem, dot, ext = self.name.rpartition(".")
        if dot and stem and 1 <= len(ext) <= 3 and ext.isascii() and ext.isalnum():
            return ext.lower()
        return ""

    def data(self, python_lzx: bool = False) -> bytes:
        """The asset itself: decompressed if the entry is compressed.

        Raises `FormatError` (`LzxError`) if the stream can't be decoded or decodes to
        the wrong length.
        """
        if self.compression == STORED:
            return self.stored
        if self.compression == LZX:
            return xcompress.decompress_entry(self.stored, self.size2, self.name,
                                              python=python_lzx)
        if self.compression == ZLIB:
            try:
                out = zlib.decompress(self.stored)
            except zlib.error as e:
                raise FormatError(f"{self.name}: zlib: {e}") from None
            if len(out) != self.size2:
                raise FormatError(f"{self.name}: zlib gave {len(out)} bytes, "
                                  f"index says {self.size2}")
            return out
        raise FormatError(f"{self.name}: unknown compression marker {self.compression}")

    def set_data(self, data: bytes, compression: int | None = None) -> None:
        """Replace the asset. Keeps the entry's compression unless told otherwise.

        Compressed entries are re-encoded with the toolkit's LZX encoder and verified by
        decoding (the game crashes on a stored replacement for a compressed entry, so we
        never silently store one).
        """
        mode = self.compression if compression is None else compression
        if mode == STORED:
            self.stored = bytes(data)
        elif mode == LZX:
            self.stored = xcompress.compress_entry(bytes(data))
        elif mode == ZLIB:
            self.stored = zlib.compress(bytes(data))
        else:
            raise ValueError(f"unknown compression {mode}")
        self.compression = mode
        self.size2 = len(data)

    def computed_hash(self) -> int:
        """The hash the engine expects for this name."""
        return entry_hash(self.name)


@dataclass(eq=False)
class BigArchive:
    """A parsed `.big` archive: an ordered list of `BigEntry`.

    Build one with `parse` (from bytes) or `open` (from a file); write it with
    `to_bytes` or `save`. ``source`` names where it came from, for error messages.
    """

    entries: list[BigEntry] = field(default_factory=list)
    source: str = "<memory>"

    # ---- reading -------------------------------------------------------------

    @classmethod
    def open(cls, path: str | Path) -> "BigArchive":
        path = Path(path)
        return cls.parse(path.read_bytes(), str(path))

    @classmethod
    def parse(cls, data: bytes, source: str = "<memory>") -> "BigArchive":
        """Parse an archive, checking the header before trusting anything.

        Raises `FormatError` naming ``source`` and the failed check. Never returns a
        half-read archive.
        """
        if len(data) < HEADER.size:
            raise FormatError(f"{source}: {len(data)} bytes, shorter than a .big header")
        if data[:4] != MAGIC:
            raise FormatError(f"{source}: magic is {data[:4].hex(' ')}, not 06 05 04 03")
        _, data_start, total, count, header_size, names_offset = HEADER.unpack_from(data)
        # The checks from the CZ recomp's docs/big-archive-format.md, before anything else.
        if header_size != HEADER_SIZE:
            raise FormatError(f"{source}: header size {header_size:#x}, expected 0x18")
        if names_offset != HEADER_SIZE + count * INDEX_ENTRY.size:
            raise FormatError(f"{source}: names_offset {names_offset:#x} != 0x18 + "
                              f"{count}*28")
        if total != len(data):
            raise FormatError(f"{source}: header says {total} bytes, data is {len(data)}")
        if not names_offset <= data_start <= total:
            raise FormatError(f"{source}: data_start {data_start:#x} outside the file")

        entries = []
        expect_name = names_offset
        payload_end = data_start
        for i in range(count):
            no, h, size, size2, off, flags, comp = INDEX_ENTRY.unpack_from(
                data, HEADER_SIZE + i * INDEX_ENTRY.size)
            if not names_offset <= no < data_start:
                raise FormatError(f"{source}: entry {i} name offset {no:#x} outside the "
                                  f"name table")
            end = data.find(b"\0", no, data_start)
            if end < 0:
                raise FormatError(f"{source}: entry {i} name has no NUL before the data")
            name = data[no:end].decode("latin-1")
            if off < payload_end or off + size > total:
                raise FormatError(f"{source}: entry {i} ({name!r}) payload "
                                  f"{off:#x}+{size:#x} overlaps another or the file end")
            if no != expect_name:
                raise FormatError(f"{source}: entry {i} ({name!r}) name is not right after "
                                  f"the previous one; this layout has never been seen "
                                  f"and the writer would not reproduce it")
            if any(data[payload_end:off]):
                raise FormatError(f"{source}: non-zero bytes between payloads before "
                                  f"entry {i} ({name!r})")
            entries.append(BigEntry(
                name=name, stored=data[off:off + size], size2=size2, flags=flags,
                compression=comp, hash=h, alignment=min(_lowbit(off), MAX_ALIGNMENT),
                index=i, data_offset=off))
            expect_name = end + 1
            payload_end = off + size
        if expect_name != data_start:
            raise FormatError(f"{source}: {data_start - expect_name} bytes between the "
                              f"names and the data; never seen, not reproducible")
        if payload_end != total:
            raise FormatError(f"{source}: {total - payload_end} bytes after the last "
                              f"payload; never seen, not reproducible")
        return cls(entries, source)

    # ---- looking things up ------------------------------------------------------

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)

    def find(self, name: str) -> list[BigEntry]:
        """All entries with this name, ignoring case, in index order."""
        key = name.lower()
        return [e for e in self.entries if e.name.lower() == key]

    def get(self, name: str, occurrence: int = 0) -> BigEntry:
        """The ``occurrence``-th entry (0 = first) named ``name``, ignoring case.

        Raises KeyError if there is no such entry.
        """
        found = self.find(name)
        if occurrence >= len(found):
            raise KeyError(f"{self.source}: no entry {name!r}"
                           + (f" #{occurrence}" if occurrence else ""))
        return found[occurrence]

    def sibling_flags(self, name: str) -> int:
        """The declared alignment (``flags``) a new entry called ``name`` gets: the most
        common among entries with its extension, else among all, else 4."""
        from collections import Counter
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        same = Counter(e.flags for e in self.entries
                       if (e.name.rsplit(".", 1)[-1].lower() if "." in e.name else "") == ext)
        every = Counter(e.flags for e in self.entries)
        for c in (same, every):
            if c:
                return c.most_common(1)[0][0]
        return 4

    def default_alignment(self) -> int:
        """Alignment for a new entry: the largest one among the archive's entries."""
        return max((e.alignment for e in self.entries if e.size), default=4)

    # ---- editing ------------------------------------------------------------------

    def add(self, name: str, data: bytes, *, compression: int = STORED,
            flags: int | None = None, alignment: int | None = None) -> BigEntry:
        """Append a new entry (its hash is computed from the name when writing).

        ``flags`` is the entry's **declared alignment** (every payload of both games
        starts at a multiple of it; the game hangs reading a new entry declared 0, CZ
        2026-10-11): by default the one its siblings of the same extension use, else the
        archive's most common, else 4. The payload is laid out at least that aligned."""
        if flags is None:
            flags = self.sibling_flags(name)
        e = BigEntry(name=name, stored=b"", size2=0, flags=flags,
                     alignment=max(alignment or self.default_alignment(), flags))
        e.set_data(data, compression)
        self.entries.append(e)
        return e

    # ---- writing ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        """Serialise the archive. Unedited, this gives back the original bytes."""
        count = len(self.entries)
        names_offset = HEADER_SIZE + count * INDEX_ENTRY.size
        names = bytearray()
        name_offsets = []
        for e in self.entries:
            name_offsets.append(names_offset + len(names))
            names += e.name.encode("latin-1") + b"\0"
        data_start = names_offset + len(names)

        offsets = []
        pos = data_start
        for e in self.entries:
            pos = _align_up(pos, e.alignment)
            offsets.append(pos)
            pos += e.size
        total = pos

        out = bytearray(total)
        HEADER.pack_into(out, 0, int.from_bytes(MAGIC, "little"), data_start, total,
                         count, HEADER_SIZE, names_offset)
        for i, e in enumerate(self.entries):
            h = e.computed_hash() if e.hash is None else e.hash
            INDEX_ENTRY.pack_into(out, HEADER_SIZE + i * INDEX_ENTRY.size, name_offsets[i],
                                  h, e.size, e.size2, offsets[i], e.flags, e.compression)
        out[names_offset:data_start] = names
        for e, off in zip(self.entries, offsets):
            out[off:off + e.size] = e.stored
        return bytes(out)

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_bytes())


def is_big(data: bytes) -> bool:
    """True if ``data`` starts with the `.big` magic."""
    return data[:4] == MAGIC


__all__ = ["BigArchive", "BigEntry", "is_big", "MAGIC", "STORED", "LZX", "ZLIB",
           "FormatError", "LzxError"]

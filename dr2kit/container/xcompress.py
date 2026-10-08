"""Compressed `.big` entries: the XMemCompress chunk framing around LZX streams.

An entry whose index ``compression`` word is 2 holds this stream instead of its data
(docs/formats.md, "Compressed entry stream"). Everything here is **big-endian**, while
the archive index around it is little-endian (CLAUDE.md, hard-won rule 1)::

    u32  uncompressed size (== the index entry's size2)
    u32  window size (0x8000)
    repeat until the entry ends:
        u32  chunk length (everything after this word, up to the next chunk)
        u8   0xFF
        u16  uncompressed length of this chunk (<= 0x8000)
        u16  compressed length of the LZX data
        ...  LZX data (one independent stream; see dr2kit/container/lzx/)
        ...  padding up to the chunk length (5 zero bytes in shipped data)

An **empty** compressed entry is just ``00 00 00 00``: the size word, with no window
word and no chunks (27 such entries in Case West's ``preload4.big``, all with
``size2 == 0``; Case Zero ships the same 27 files with content). `compress_entry` writes
that form for empty data.

The trailing zero bytes matter: the game's decoder reads ahead of what it consumes, and
without slack it reads whatever follows the chunk (the CZ recomp spent a dozen probe runs
on that; see ``encode.py``'s origin note). `compress_entry` writes exactly 5, like the
shipped chunks, and checks every result by decoding it again.

Origin: framing established in the CZ recomp (``tools/big_decompress.cpp`` and
``docs/big-archive-format.md``, parsed exactly on ``cc_03.bct``); writer ported from
``tools/gen_pc_options.py``. Verified over every compressed entry of both games by
``dr2 census``.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from ..errors import LzxError
from . import lzx

STREAM_HEADER = struct.Struct(">II")       # uncompressed size, window size
CHUNK_HEADER = struct.Struct(">IBHH")      # chunk length, 0xFF, unc len, comp len
CHUNK_MARKER = 0xFF
WINDOW_SIZE = 0x8000
WINDOW_BITS = 15
CHUNK_TRAILER = 5                          # zero bytes after the LZX data, as shipped


@dataclass(frozen=True)
class Chunk:
    """One chunk of a compressed entry: where its LZX data is, and its two lengths."""
    offset: int             # of the LZX data inside the entry's stored bytes
    uncompressed: int
    compressed: int
    padding: int            # bytes after the LZX data inside the chunk


@dataclass(frozen=True)
class StreamInfo:
    """The parsed framing of a compressed entry (no decoding done)."""
    uncompressed_size: int
    window_size: int
    chunks: tuple[Chunk, ...]


def parse_stream(stored: bytes, where: str = "entry") -> StreamInfo:
    """Read the chunk framing of a compressed entry, checking every length.

    Raises `LzxError` (naming ``where``) if the framing doesn't add up exactly: a chunk
    running past the end, a missing ``0xFF`` marker, chunk sizes that don't sum to the
    declared uncompressed size, or bytes left over after the last chunk.
    """
    if len(stored) == 4 and stored == b"\0\0\0\0":
        return StreamInfo(0, 0, ())          # an empty entry (see the module docstring)
    if len(stored) < STREAM_HEADER.size:
        raise LzxError(f"{where}: {len(stored)} bytes, too short for a compressed stream")
    size, window = STREAM_HEADER.unpack_from(stored, 0)
    if window != WINDOW_SIZE:
        raise LzxError(f"{where}: window size {window:#x}, expected {WINDOW_SIZE:#x}")
    pos = STREAM_HEADER.size
    chunks = []
    total = 0
    while pos < len(stored):
        if pos + CHUNK_HEADER.size > len(stored):
            raise LzxError(f"{where}: {len(stored) - pos} stray bytes after the last chunk")
        length, marker, unc, comp = CHUNK_HEADER.unpack_from(stored, pos)
        if marker != CHUNK_MARKER:
            raise LzxError(f"{where}: chunk at {pos:#x} starts {marker:#04x}, not 0xFF")
        body = pos + 4 + 5
        end = pos + 4 + length
        if end > len(stored) or comp > length - 5 or unc == 0 or unc > WINDOW_SIZE:
            raise LzxError(f"{where}: chunk at {pos:#x} has impossible lengths "
                           f"(chunk {length}, unc {unc}, comp {comp})")
        chunks.append(Chunk(body, unc, comp, length - 5 - comp))
        total += unc
        pos = end
    if total != size:
        raise LzxError(f"{where}: chunks hold {total} bytes, header says {size}")
    return StreamInfo(size, window, tuple(chunks))


def decompress_entry(stored: bytes, size2: int | None = None, where: str = "entry",
                     python: bool = False) -> bytes:
    """Decode a compressed entry's stored bytes into the asset.

    ``size2`` (the index's uncompressed size) is checked against the stream header when
    given. ``python=True`` forces the pure-Python decoder (for cross-checks).
    """
    info = parse_stream(stored, where)
    if size2 is not None and info.uncompressed_size != size2:
        raise LzxError(f"{where}: stream says {info.uncompressed_size} bytes, "
                       f"index says {size2}")
    decode = lzx.decompress_python if python else lzx.decompress
    parts = []
    for c in info.chunks:
        try:
            parts.append(decode(stored[c.offset:c.offset + c.compressed], c.uncompressed,
                                WINDOW_BITS))
        except LzxError as e:
            raise LzxError(f"{where}: chunk at {c.offset - 9:#x}: {e}") from None
    return b"".join(parts)


def compress_entry(data: bytes, verify: bool = True) -> bytes:
    """Encode ``data`` as a compressed entry's stored bytes (the game's framing).

    With ``verify`` (the default) the whole result is decoded again and compared, and
    `LzxError` is raised on any difference. Chunks that don't compress are stored as LZX
    uncompressed blocks, as the game's own encoder does (see ``lzx/encode.py``).
    """
    if not data:
        return b"\0\0\0\0"                    # the shipped form of an empty entry
    out = bytearray(STREAM_HEADER.pack(len(data), WINDOW_SIZE))
    for start in range(0, len(data), WINDOW_SIZE):
        chunk = data[start:start + WINDOW_SIZE]
        payload = lzx.encode_chunk(chunk)
        length = 5 + len(payload) + CHUNK_TRAILER
        out += CHUNK_HEADER.pack(length, CHUNK_MARKER, len(chunk), len(payload))
        out += payload
        out += b"\0" * CHUNK_TRAILER
    result = bytes(out)
    if verify:
        back = decompress_entry(result, len(data), "re-encoded entry")
        if back != data:
            raise LzxError("re-encoded entry decodes to different bytes")
    return result

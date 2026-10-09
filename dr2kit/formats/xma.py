"""`.xma` audio: RIFF XMA2 files, the `$GIB` stream tables, XMA packet headers.

The games keep every sound as XMA2, the Xbox 360's hardware audio codec (a cut-down
WMA Pro, decoded in 2 KB packets of 512-sample frames). It comes in **two shapes**:

* **RIFF XMA2** (every `.xma` inside the ``fx_*.big`` banks of ``streamedassets.big``;
  7,647 in Case Zero): a complete ``RIFF``/``WAVE`` file with a ``fmt `` chunk
  (``XMA2WAVEFORMATEX``, format tag 0x166, **little-endian**), a ``seek`` chunk (one
  **big-endian** dword per 64 KB block: samples decoded by the end of that block) and a
  ``data`` chunk of packets. ``fmt``'s ``dwPlayLength`` is the sound's exact length in
  samples (the census checks every decode against it).
* **Raw packets** (every `.xma` in the streamed banks ``data/audio/*.big``: music,
  voices, cinematics; 1,269 in Case Zero): packets only, no header, 0x800-aligned. Their
  channels and rate live in ``data/audio/cache.big``: one ``<bank>.$$$`` table per bank
  (`StreamTable`), one 24-byte record per sound, keyed by the engine hash of the entry
  name **with its case kept** (``name_hash("HB_Indemnify.xma")``, unlike the `.big` index,
  which hashes the lower-cased name).

Decoding (ffmpeg's ``xma2`` decoder through PyAV) is `dr2kit.convert.audio`'s job; it
wraps raw packets in a RIFF header built by `riff_wrap` so both shapes take one path.

Key facts (docs/formats.md §Audio; measured over every `.xma` of both games by
``dr2 census --audio``):

* `$GIB` table: ``"$GIB"``, version 2, 3, record count (big-endian), then records of
  ``hash, offset, size, format, loop_begin, loop_length``. ``offset``/``size`` are the
  entry's place in its bank; ``format`` packs ``rate << 5 | channels << 2 | 1``. The
  loop fields mean what the RIFF ``fmt`` fields of the same name mean.
* **Lengths.** A decode always drops 384 samples of lead-in (`DECODER_DELAY`). Loop
  points count those samples, so a loop covers decoded samples
  ``[loop_begin − 384, loop_begin + loop_length − 384)``. A one-shot RIFF decodes to
  exactly ``dwPlayLength``; a looping raw stream to exactly its loop end; any sound to
  ``frames × 512 − 384`` less under one frame per stream (the encoder marks the padding
  of the last frame). Looping RIFF files have no exact stored length: most end at the
  loop end (±1 sample), 4 (CZ) / 2 (CW) carry a tail after it.
* Rates are 48000 Hz, give or take a few hertz (47,866 to 48,530): the encoder stored
  each sound's measured source rate. Channels: 1, 2, or 6 (the 5.1 cinematics, stored as
  three stereo streams).
* XMA2 packet header (big-endian dword): frame count (6 bits), first-frame bit offset
  (15), metadata (3), packet skip (8). Frames span packets, so the sum of frame counts
  over a stream's packets is its frame total (512 samples each).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from ..errors import FormatError
from ..hashing import name_hash

FORMAT_TAG_XMA2 = 0x166
PACKET = 2048                  # one XMA packet
FRAME_SAMPLES = 512            # samples per channel in one XMA frame
BLOCK = 0x10000                # the 64 KB block a `seek` entry covers (shipped files)
CACHE_MAGIC = b"$GIB"
CACHE_RECORD = 24
CACHE_ARCHIVE = "data/audio/cache.big"
# Samples of lead-in the decoder drops: a decode is always 384 samples shorter than the
# frames encoded (every `.xma` of both games). Loop points include them, and most loops
# begin at exactly 384, the first decoded sample.
DECODER_DELAY = 384

# dwChannelMask by channel count: what the shipped RIFF files and the recomps use
# (mono = front centre, stereo = L|R, 5.1 = L R C LFE Ls Rs).
CHANNEL_MASK = {1: 0x4, 2: 0x3, 6: 0x3F}


@dataclass
class Xma2Format:
    """``XMA2WAVEFORMATEX``: the 18-byte ``WAVEFORMATEX`` plus the 34-byte XMA2 tail."""
    channels: int
    rate: int
    avg_bytes_per_sec: int = 0
    block_align: int = 2048
    bits_per_sample: int = 16
    streams: int = 1
    channel_mask: int = 0
    samples_encoded: int = 0
    bytes_per_block: int = BLOCK
    play_begin: int = 0
    play_length: int = 0
    loop_begin: int = 0
    loop_length: int = 0
    loop_count: int = 0
    encoder_version: int = 4
    block_count: int = 1

    _STRUCT = struct.Struct("<HHIIHHH" "HIIIIIIIBBH")

    @classmethod
    def parse(cls, b: bytes, source: str = "<memory>") -> "Xma2Format":
        """Read a ``fmt `` chunk body (52 bytes)."""
        if len(b) < cls._STRUCT.size:
            raise FormatError(f"{source}: fmt chunk is {len(b)} bytes, XMA2 needs 52")
        (tag, ch, rate, avg, align, bits, cb, streams, mask, enc, bpb, pb, pl, lb, ll,
         lc, ver, blocks) = cls._STRUCT.unpack_from(b)
        if tag != FORMAT_TAG_XMA2 or cb != 34:
            raise FormatError(f"{source}: fmt tag {tag:#x} / cbSize {cb}, expected XMA2 "
                              f"({FORMAT_TAG_XMA2:#x} / 34)")
        return cls(ch, rate, avg, align, bits, streams, mask, enc, bpb, pb, pl, lb, ll,
                   lc, ver, blocks)

    def to_bytes(self) -> bytes:
        """The ``fmt `` chunk body, as `parse` reads it."""
        return self._STRUCT.pack(
            FORMAT_TAG_XMA2, self.channels, self.rate, self.avg_bytes_per_sec,
            self.block_align, self.bits_per_sample, 34, self.streams, self.channel_mask,
            self.samples_encoded, self.bytes_per_block, self.play_begin, self.play_length,
            self.loop_begin, self.loop_length, self.loop_count, self.encoder_version,
            self.block_count)

    def extradata(self) -> bytes:
        """The 34-byte tail alone: what ffmpeg's ``xma2`` decoder takes as extradata."""
        return self.to_bytes()[18:]


@dataclass
class XmaRiff:
    """A RIFF XMA2 file: format, seek table, and where the packets are."""
    fmt: Xma2Format
    seek: list[int]
    data_offset: int
    data_size: int
    chunks: list[str] = field(default_factory=list)     # chunk ids, in file order
    leftover: int = 0                                    # bytes after the RIFF body

    @classmethod
    def parse(cls, data: bytes, source: str = "<memory>") -> "XmaRiff":
        """Parse a RIFF XMA2 file. Raises `FormatError` on anything it can't account for."""
        if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
            raise FormatError(f"{source}: not a RIFF/WAVE file")
        riff_end = 8 + struct.unpack_from("<I", data, 4)[0]
        if riff_end > len(data):
            raise FormatError(f"{source}: RIFF says {riff_end} bytes, file has {len(data)}")
        fmt = None
        seek: list[int] = []
        data_at = data_size = -1
        chunks = []
        o = 12
        while o + 8 <= riff_end:
            cid = data[o:o + 4]
            size = struct.unpack_from("<I", data, o + 4)[0]
            body = o + 8
            if body + size > riff_end:
                raise FormatError(f"{source}: chunk {cid!r} at {o:#x} runs past the end")
            chunks.append(cid.decode("latin-1"))
            if cid == b"fmt ":
                fmt = Xma2Format.parse(data[body:body + size], source)
            elif cid == b"seek":
                seek = list(struct.unpack_from(f">{size // 4}I", data, body))
            elif cid == b"data":
                data_at, data_size = body, size
            o = body + size + (size & 1)
        if fmt is None or data_at < 0:
            raise FormatError(f"{source}: RIFF without {'fmt ' if fmt is None else 'data'} chunk")
        unknown = [c for c in chunks if c not in ("fmt ", "seek", "data")]
        if unknown:
            raise FormatError(f"{source}: unknown RIFF chunks {unknown}")
        return cls(fmt, seek, data_at, data_size, chunks, len(data) - riff_end)

    def packets(self, data: bytes) -> bytes:
        """The ``data`` chunk (the XMA packets) of ``data``, the bytes this was parsed from."""
        return data[self.data_offset:self.data_offset + self.data_size]


def is_riff(data: bytes) -> bool:
    """True when ``data`` starts like a RIFF/WAVE file (vs. raw XMA packets)."""
    return data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def riff_wrap(packets: bytes, channels: int, rate: int, *, play_length: int = 0,
              loop_begin: int = 0, loop_length: int = 0) -> bytes:
    """A RIFF XMA2 file around raw packets, so ffmpeg can open them like a shipped file.

    Channels > 2 are split into stereo streams (plus one mono stream for an odd count),
    as XMA2 stores them. No ``seek`` chunk: ffmpeg doesn't need one to decode from the
    start.
    """
    fmt = Xma2Format(channels=channels, rate=rate, streams=(channels + 1) // 2,
                     channel_mask=CHANNEL_MASK.get(channels, 0),
                     play_length=play_length, loop_begin=loop_begin,
                     loop_length=loop_length,
                     block_count=max(1, -(-len(packets) // BLOCK)))
    body = fmt.to_bytes()
    out = bytearray(b"RIFF\0\0\0\0WAVE")
    out += b"fmt " + struct.pack("<I", len(body)) + body
    out += b"data" + struct.pack("<I", len(packets)) + packets
    struct.pack_into("<I", out, 4, len(out) - 8)
    return bytes(out)


# --- XMA2 packets ------------------------------------------------------------------------

@dataclass(frozen=True)
class PacketHeader:
    """The 32-bit big-endian header at the start of each 2 KB XMA2 packet."""
    frames: int          # frames that *start* in this packet
    frame_offset: int    # bit offset of the first frame start, after the 32-bit header
    metadata: int
    skip: int            # packets of other streams to skip after this one

    @classmethod
    def parse(cls, word: int) -> "PacketHeader":
        return cls(word >> 26, (word >> 11) & 0x7FFF, (word >> 8) & 7, word & 0xFF)


def packet_headers(packets: bytes) -> list[PacketHeader]:
    """Every packet header of a run of packets (a trailing partial packet is ignored)."""
    n = len(packets) // PACKET
    return [PacketHeader.parse(struct.unpack_from(">I", packets, i * PACKET)[0])
            for i in range(n)]


def frame_count(packets: bytes, streams: int = 1) -> int:
    """Frames per stream (sum of packet frame counts over all streams, / streams).

    The length check for sounds with no stored length: they decode to
    ``frames × 512 − DECODER_DELAY`` minus less than one frame per stream (the encoder
    marks how much of the last frame is padding).
    """
    total = sum(h.frames for h in packet_headers(packets))
    return total // max(1, streams)


def stream_starts(packets: bytes, streams: int) -> list[int]:
    """The packet index where each stream begins (``[0]`` for mono/stereo; ``[0, 1, 2]``
    for the 5.1 cinematics).

    Streams interleave packet by packet; each header's ``skip`` says how many packets of
    other streams follow before this stream's next one. Stream *k* starts at the first
    packet not reached by following streams 0..k-1 from their starts.
    """
    hs = packet_headers(packets)
    owned = [False] * len(hs)
    starts: list[int] = []
    for _ in range(streams):
        i = next((j for j, o in enumerate(owned) if not o), None)
        if i is None:
            break
        starts.append(i)
        while i < len(hs):
            owned[i] = True
            i += hs[i].skip + 1
    return starts


def fingerprint(packet: bytes) -> int:
    """64-bit FNV-1a of one 2 KB packet: how the recomps recognise a sound's first packet.

    The runtime computes the same hash over each packet it decodes
    (docs/dev/recomp-integration.md §Audio substitution); keep both in step.
    """
    h = 0xCBF29CE484222325
    for b in packet:
        h = ((h ^ b) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


# --- cache.big stream tables -------------------------------------------------------------

@dataclass(frozen=True)
class StreamRecord:
    """One sound of a streamed bank, from its ``cache.big/<bank>.$$$`` table."""
    hash: int            # name_hash of the entry name, case kept
    offset: int          # where the entry sits in the bank file
    size: int
    rate: int
    channels: int
    flags: int           # low 2 bits of the format word; 1 on every record of both games
    loop_begin: int      # like the RIFF fields: encoded samples, lead-in included
    loop_length: int     # 0: not a loop

    @property
    def looped(self) -> bool:
        return bool(self.loop_length)


@dataclass
class StreamTable:
    """A ``$GIB`` table: the records of one streamed bank."""
    version: int
    unknown: int
    records: list[StreamRecord]

    @classmethod
    def parse(cls, data: bytes, source: str = "<memory>") -> "StreamTable":
        if data[:4] != CACHE_MAGIC:
            raise FormatError(f"{source}: not a $GIB stream table")
        version, unknown, n = struct.unpack_from(">III", data, 4)
        if len(data) != 16 + n * CACHE_RECORD:
            raise FormatError(f"{source}: {n} records need {16 + n * CACHE_RECORD} bytes, "
                              f"table has {len(data)}")
        recs = []
        for i in range(n):
            h, off, size, fmt, l0, l1 = struct.unpack_from(">6I", data, 16 + i * CACHE_RECORD)
            recs.append(StreamRecord(h, off, size, fmt >> 5, (fmt >> 2) & 7, fmt & 3, l0, l1))
        return cls(version, unknown, recs)

    def by_name(self) -> dict[int, StreamRecord]:
        return {r.hash: r for r in self.records}

    def find(self, entry_name: str) -> StreamRecord | None:
        """The record of the entry called ``entry_name`` (hash of the name, case kept)."""
        h = name_hash(entry_name)
        for r in self.records:
            if r.hash == h:
                return r
        return None


# --- one answer for any .xma -------------------------------------------------------------

@dataclass(frozen=True)
class AudioInfo:
    """What a decoder needs to know about one `.xma`, and what its length should be.

    ``loop_begin``/``loop_length`` are as stored (lead-in included); `loop` gives the
    range in decoded samples.
    """
    channels: int
    rate: int
    shape: str                 # "riff" or "raw"
    packets_offset: int        # where the packets start in the entry's bytes
    packets_size: int
    expected_samples: int      # exact decoded length, 0 when nothing stores one
    loop_begin: int = 0
    loop_length: int = 0
    source: str = ""           # where the metadata came from (for `dr2 info`)

    @property
    def streams(self) -> int:
        return (self.channels + 1) // 2

    @property
    def loop(self) -> tuple[int, int] | None:
        """``(start, end)`` of the loop in decoded samples, or None for a one-shot."""
        if not self.loop_length:
            return None
        start = max(0, self.loop_begin - DECODER_DELAY)
        return start, self.loop_begin + self.loop_length - DECODER_DELAY


def bank_of(vpath: str) -> str | None:
    """``data/audio/music.big/X.xma`` → ``music``; None for sounds not in a streamed bank."""
    parts = vpath.replace("\\", "/").split("/")
    if len(parts) == 4 and parts[0].lower() == "data" and parts[1].lower() == "audio" \
            and parts[2].lower().endswith(".big"):
        return parts[2][:-4].lower()
    return None


def info_from_riff(data: bytes, source: str = "<memory>") -> AudioInfo:
    """Metadata of a RIFF XMA2 file (exact length for one-shots only: see the module)."""
    r = XmaRiff.parse(data, source)
    f = r.fmt
    return AudioInfo(f.channels, f.rate, "riff", r.data_offset, r.data_size,
                     0 if f.loop_length else f.play_length, f.loop_begin, f.loop_length,
                     "RIFF fmt chunk")


def info_from_record(data: bytes, rec: StreamRecord, bank: str) -> AudioInfo:
    """Metadata of a raw stream from its table record (exact length for loops only)."""
    expected = rec.loop_begin + rec.loop_length - DECODER_DELAY if rec.looped else 0
    return AudioInfo(rec.channels, rec.rate, "raw", 0, len(data), expected,
                     rec.loop_begin, rec.loop_length, f"{CACHE_ARCHIVE}/{bank}.$$$")

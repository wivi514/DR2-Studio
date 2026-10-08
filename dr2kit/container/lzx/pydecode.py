"""Pure-Python LZX decoder: the fallback when the native `dr2lzx` library is missing.

Why it exists: dr2kit must work everywhere, including inside Blender (no compiler, no
pip) and on a Mac that blocks an unsigned library. This decoder needs nothing but the
standard library. It runs at about 3-4 MB/s, roughly 30x slower than the native one: fine for
opening a few entries and too slow for a whole-game census (use the native library for
that; ``dr2 doctor`` says which one is active).

Licensing note: this module was written from the published description of the LZX
format (Microsoft's LZX DELTA specification and the CAB format documents), **not**
translated from libmspack's ``lzxd.c``, so it carries the toolkit's own license
(docs/phase1-kickoff.md, "Licensing of reused code").

The format in brief (what the code below implements):

* The input is read as **16-bit little-endian words**, and bits are taken from each word
  starting at its most significant bit.
* A stream starts with 1 bit: Intel E8 call translation on/off. The game never turns it
  on (checked on every compressed entry of both games); we refuse streams that do.
* Then blocks, each with a 3-bit type (1 verbatim, 2 aligned offset, 3 uncompressed) and
  a 24-bit uncompressed length.
* Verbatim and aligned blocks carry Huffman trees: the *main* tree (256 literals, then
  8 match headers per position slot), the *length* tree (249 extra lengths) and, for
  aligned blocks, an 8-symbol *aligned offset* tree. Code lengths are sent as differences
  from the previous block's lengths (mod 17), through a 20-symbol *pretree*, with run
  codes 17/18 (zeros) and 19 (a repeated value).
* Matches refer back into the output; the three most recent offsets (R0, R1, R2) have
  their own short codes.
* Uncompressed blocks re-align to a 16-bit word, store R0-R2 as raw little-endian u32s,
  then the bytes, plus one padding byte when the length is odd.

The game uses a 32 KB window (``window_bits = 15``) and decodes every XMemCompress
chunk as a fresh stream (docs/formats.md, "Compressed entry stream").
"""

from __future__ import annotations

import struct

from ...errors import LzxError

FRAME_SIZE = 32768  # output bytes per LZX frame; the bit stream re-aligns after each

# Number of position slots for each window size (LZX specification).
_POSITION_SLOTS = {15: 30, 16: 32, 17: 34, 18: 36, 19: 38, 20: 42, 21: 50}

# Extra bits and base offset for each position slot. Extra bits go 0,0,0,0,1,1,2,2,…
# capped at 17; each base is the previous base plus 2**previous extra bits.
EXTRA_BITS = [min(max(0, (s - 2) // 2), 17) for s in range(50)]
POSITION_BASE = []
_base = 0
for _e in EXTRA_BITS:
    POSITION_BASE.append(_base)
    _base += 1 << _e
del _base, _e

NUM_CHARS = 256
PRETREE_SYMBOLS = 20
LENGTH_SYMBOLS = 249
ALIGNED_SYMBOLS = 8
MIN_MATCH = 2

BLOCK_VERBATIM = 1
BLOCK_ALIGNED = 2
BLOCK_UNCOMPRESSED = 3


def build_table(lengths: list[int], what: str) -> tuple[list[int] | None, int]:
    """Build a direct lookup table for a canonical Huffman code.

    Returns ``(table, bits)``: index the table with the next ``bits`` input bits to get
    ``symbol << 5 | code_length``, or -1 for a bit pattern no code starts with (only
    possible for an incomplete code, which then must not be used). An all-zero length
    list gives ``(None, 0)``: an empty tree, legal as long as nothing is decoded with it.

    Canonical assignment: shorter codes first; equal lengths in increasing symbol order.
    """
    max_len = max(lengths, default=0)
    if max_len == 0:
        return None, 0
    if max_len > 16:
        raise LzxError(f"{what} tree: code length {max_len} > 16")
    size = 1 << max_len
    table = [-1] * size
    code = 0  # next code, left-aligned to max_len bits
    for length in range(1, max_len + 1):
        step = 1 << (max_len - length)
        for sym, sl in enumerate(lengths):
            if sl == length:
                end = code + step
                if end > size:
                    raise LzxError(f"{what} tree: over-subscribed code lengths")
                table[code:end] = [(sym << 5) | length] * step
                code = end
    return table, max_len


class _Bits:
    """MSB-first reader over 16-bit little-endian words (kept simple; hot paths inline)."""

    __slots__ = ("words", "wi", "buf", "nbits")

    def __init__(self, src: bytes, start: int = 0):
        body = bytes(src[start:])
        if len(body) & 1:
            body += b"\0"
        # Two zero words of slack: a decoder may peek a little past the end of the data.
        self.words = list(struct.unpack(f"<{len(body) // 2}H", body)) + [0, 0]
        self.wi = 0
        self.buf = 0
        self.nbits = 0

    def read(self, n: int) -> int:
        if n == 0:
            return 0
        while self.nbits < n:
            try:
                self.buf = (self.buf << 16) | self.words[self.wi]
            except IndexError:
                raise LzxError("LZX stream ended early") from None
            self.wi += 1
            self.nbits += 16
        self.nbits -= n
        v = self.buf >> self.nbits
        self.buf &= (1 << self.nbits) - 1
        return v

    def decode(self, table: list[int] | None, bits: int, what: str) -> int:
        if table is None:
            raise LzxError(f"LZX stream uses the empty {what} tree")
        while self.nbits < bits:
            try:
                self.buf = (self.buf << 16) | self.words[self.wi]
            except IndexError:
                raise LzxError("LZX stream ended early") from None
            self.wi += 1
            self.nbits += 16
        e = table[self.buf >> (self.nbits - bits)]
        if e < 0:
            raise LzxError(f"LZX stream: invalid {what} code")
        self.nbits -= e & 31
        self.buf &= (1 << self.nbits) - 1
        return e >> 5

    def align_word(self) -> None:
        """Drop the rest of the current 16-bit word."""
        self.nbits = 0
        self.buf = 0


def _read_lengths(bits: _Bits, lens: list[int], first: int, last: int) -> None:
    """Update ``lens[first:last]`` from a pretree-coded delta run (see module docstring)."""
    pre = [bits.read(4) for _ in range(PRETREE_SYMBOLS)]
    table, tbits = build_table(pre, "pretree")
    x = first
    while x < last:
        z = bits.decode(table, tbits, "pretree")
        if z == 17:
            run, value = bits.read(4) + 4, 0
        elif z == 18:
            run, value = bits.read(5) + 20, 0
        elif z == 19:
            run = bits.read(1) + 4
            z = bits.decode(table, tbits, "pretree")
            value = (lens[x] - z) % 17
        else:
            lens[x] = (lens[x] - z) % 17
            x += 1
            continue
        if x + run > last:
            raise LzxError("LZX stream: code-length run past the end of the tree")
        lens[x:x + run] = [value] * run
        x += run


def decompress(src: bytes, out_len: int, window_bits: int = 15) -> bytes:
    """Decode one LZX stream to exactly ``out_len`` bytes.

    ``src`` is one XMemCompress chunk's LZX data (after its 5-byte ``0xFF`` header).
    Raises `LzxError` on anything malformed, including a stream that would produce more
    or fewer than ``out_len`` bytes.
    """
    if window_bits not in _POSITION_SLOTS:
        raise LzxError(f"unsupported LZX window of 2**{window_bits} bytes")
    window_size = 1 << window_bits
    main_elements = NUM_CHARS + _POSITION_SLOTS[window_bits] * 8
    main_lens = [0] * main_elements
    length_lens = [0] * LENGTH_SYMBOLS
    bits = _Bits(src)
    out = bytearray()
    r0 = r1 = r2 = 1

    if out_len == 0:
        return b""
    if bits.read(1):
        raise LzxError("LZX stream uses Intel E8 translation (never seen in DR2 data; "
                       "not supported)")

    frame_end = FRAME_SIZE
    while len(out) < out_len:
        if len(out) >= frame_end:
            bits.align_word()  # a frame ended exactly at the end of a block
            frame_end += FRAME_SIZE
        btype = bits.read(3)
        remaining = (bits.read(16) << 8) | bits.read(8)
        if remaining == 0:
            raise LzxError("LZX stream: zero-length block")

        if btype == BLOCK_UNCOMPRESSED:
            # Re-align: skip to the next word, or a whole word if already aligned.
            if bits.nbits == 0:
                bits.read(16)
            bits.align_word()
            raw = struct.pack(f"<{len(bits.words)}H", *bits.words)
            pos = bits.wi * 2
            if pos + 12 + remaining > len(raw):
                raise LzxError("LZX stream ended inside an uncompressed block")
            r0, r1, r2 = struct.unpack_from("<3I", raw, pos)
            pos += 12
            out += raw[pos:pos + remaining]
            pos += remaining + (remaining & 1)
            bits.wi = pos // 2  # 12 + len + pad is even, so this stays word-aligned
            if len(out) > out_len:
                raise LzxError("LZX stream produces more bytes than expected")
            continue

        if btype not in (BLOCK_VERBATIM, BLOCK_ALIGNED):
            raise LzxError(f"LZX stream: invalid block type {btype}")

        aligned_table = None
        aligned_bits = 0
        if btype == BLOCK_ALIGNED:
            aligned = [bits.read(3) for _ in range(ALIGNED_SYMBOLS)]
            aligned_table, aligned_bits = build_table(aligned, "aligned offset")
        _read_lengths(bits, main_lens, 0, NUM_CHARS)
        _read_lengths(bits, main_lens, NUM_CHARS, main_elements)
        main_table, main_bits = build_table(main_lens, "main")
        _read_lengths(bits, length_lens, 0, LENGTH_SYMBOLS)
        length_table, length_bits = build_table(length_lens, "length")

        # Hot loop. Bit-reader state is copied into locals for speed and written back
        # when the block ends.
        words, wi, buf, nbits = bits.words, bits.wi, bits.buf, bits.nbits
        nwords = len(words)
        if main_table is None:
            raise LzxError("LZX stream: empty main tree")
        try:
            while remaining > 0:
                if len(out) >= frame_end:
                    nbits = 0  # frame boundary: the bit stream re-aligns to a word
                    buf = 0
                    frame_end += FRAME_SIZE
                while nbits < main_bits:
                    buf = (buf << 16) | words[wi]
                    wi += 1
                    nbits += 16
                e = main_table[buf >> (nbits - main_bits)]
                if e < 0:
                    raise LzxError("LZX stream: invalid main code")
                nbits -= e & 31
                buf &= (1 << nbits) - 1
                sym = e >> 5
                if sym < NUM_CHARS:
                    out.append(sym)
                    remaining -= 1
                    continue

                sym -= NUM_CHARS
                length = sym & 7
                slot = sym >> 3
                if length == 7:
                    if length_table is None:
                        raise LzxError("LZX stream uses the empty length tree")
                    while nbits < length_bits:
                        buf = (buf << 16) | words[wi]
                        wi += 1
                        nbits += 16
                    e = length_table[buf >> (nbits - length_bits)]
                    if e < 0:
                        raise LzxError("LZX stream: invalid length code")
                    nbits -= e & 31
                    buf &= (1 << nbits) - 1
                    length += e >> 5
                length += MIN_MATCH

                if slot == 0:
                    offset = r0
                elif slot == 1:
                    offset = r1
                    r1 = r0
                    r0 = offset
                elif slot == 2:
                    offset = r2
                    r2 = r0
                    r0 = offset
                else:
                    extra = EXTRA_BITS[slot]
                    offset = POSITION_BASE[slot] - 2
                    if aligned_table is not None and extra >= 3:
                        verbatim_bits = extra - 3
                        if verbatim_bits:
                            while nbits < verbatim_bits:
                                buf = (buf << 16) | words[wi]
                                wi += 1
                                nbits += 16
                            nbits -= verbatim_bits
                            offset += (buf >> nbits) << 3
                            buf &= (1 << nbits) - 1
                        while nbits < aligned_bits:
                            buf = (buf << 16) | words[wi]
                            wi += 1
                            nbits += 16
                        e = aligned_table[buf >> (nbits - aligned_bits)]
                        if e < 0:
                            raise LzxError("LZX stream: invalid aligned offset code")
                        nbits -= e & 31
                        buf &= (1 << nbits) - 1
                        offset += e >> 5
                    elif extra:
                        while nbits < extra:
                            buf = (buf << 16) | words[wi]
                            wi += 1
                            nbits += 16
                        nbits -= extra
                        offset += buf >> nbits
                        buf &= (1 << nbits) - 1
                    r2 = r1
                    r1 = r0
                    r0 = offset

                start = len(out) - offset
                if start < 0 or offset > window_size:
                    raise LzxError("LZX stream: match reaches before the start of the data")
                if offset >= length:
                    out += out[start:start + length]
                else:  # overlapping copy repeats the last `offset` bytes
                    pattern = out[start:]
                    out += (pattern * (length // offset + 1))[:length]
                remaining -= length
        except IndexError:
            if wi >= nwords:
                raise LzxError("LZX stream ended early") from None
            raise
        bits.wi, bits.buf, bits.nbits = wi, buf, nbits
        if remaining < 0:
            raise LzxError("LZX stream: a match runs past the end of its block")
        if len(out) > out_len:
            raise LzxError("LZX stream produces more bytes than expected")

    return bytes(out)

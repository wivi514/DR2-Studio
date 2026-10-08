"""A small, real LZX compressor (pure Python), for putting edited entries back.

Why we need an encoder at all: the game refuses an uncompressed replacement for an entry
it expects compressed (it asserts and crashes), and the CZ recomp saw it crash on
*degenerate* LZX streams that other decoders accept (literal-only blocks, and an
uncompressed-block stream that also lacked the chunk padding). So an edited entry is
re-encoded into an LZX stream that looks like the ones the game ships: real Huffman
trees, real matches, the same chunk padding. This module does that.

Origin: ported from the Case Zero recomp's ``tools/gen_pc_options.py``
(``lzx_encode_stream``, ``huffman_lengths``, ``canonical_codes``; same author, re-licensed
into this project). An earlier version of that encoder's output was accepted by the game
(``tools/patch_coop_ending_bike.py`` replaced ``datafile.big`` text that way). The history
of what the game rejected, and why, is in that file's docstrings.

Changes from the original, none of which change the bit-stream format:

* It encodes **one chunk** (≤ 32 KB). The XMemCompress framing around chunks (sizes,
  the ``0xFF`` header, the 5-byte trailer) lives in ``dr2kit/container/xcompress.py``.
* Bits are packed through an integer accumulator instead of a list of single bits
  (much faster, same output).
* Match search compares runs of bytes with slices; slot lookup uses bisect. Same output.
* A chunk whose verbatim block would be at least as large as storing it is written as an
  LZX *uncompressed* block (type 3) instead. The game's own encoder uses type 3 too, for
  small and hard-to-compress chunks, and somewhat more readily than this (its threshold
  is unknown; docs/formats.md, "Compressed entry stream"). Everything else is a verbatim
  block, as before.
* A tree with only one used symbol gets a second, unused code of the same length, so
  every tree is complete (Kraft sum 1). The original did this for the pretree and left
  a one-code *length* tree; a complete tree is what shipped streams always have.

The output is checked by decoding it again (``xcompress.compress_entry`` does this for
every entry it writes). The decoder is the oracle precisely because we did not write it.
"""

from __future__ import annotations

from bisect import bisect_right

from .pydecode import EXTRA_BITS as _EXTRA_ALL, POSITION_BASE as _BASE_ALL

WINDOW_SIZE = 0x8000          # the game's 32 KB window
NUM_POSITION_SLOTS = 30       # for a 32 KB window
LZX_EXTRA = _EXTRA_ALL[:NUM_POSITION_SLOTS]
LZX_BASE = _BASE_ALL[:NUM_POSITION_SLOTS]
MAIN_ELEMENTS = 256 + NUM_POSITION_SLOTS * 8
LENGTH_SYMBOLS = 249
MAX_MATCH = 257
MIN_MATCH = 3                 # we only emit matches of 3+ bytes (LZX allows 2)
CHAIN_LIMIT = 64              # positions tried per 3-byte prefix (speed vs ratio)
GOOD_ENOUGH = 128             # stop searching once a match is this long


def huffman_lengths(freqs: list[int], maxlen: int) -> list[int]:
    """Length-limited Huffman code lengths (package-merge) for symbol frequencies.

    Unused symbols get length 0. With two or more used symbols the code is complete
    (Kraft sum exactly 1). With exactly one used symbol, that symbol and a neighbour both
    get length 1, so the tree is still complete; the neighbour is simply never sent.
    """
    used = [s for s, f in enumerate(freqs) if f]
    out = [0] * len(freqs)
    if not used:
        return out
    if len(used) == 1:
        out[used[0]] = 1
        out[(used[0] + 1) % len(freqs)] = 1
        return out
    single = [(freqs[s], (s,)) for s in used]
    packages = sorted(single)
    for _ in range(maxlen - 1):
        merged = [(packages[i][0] + packages[i + 1][0], packages[i][1] + packages[i + 1][1])
                  for i in range(0, len(packages) - 1, 2)]
        packages = sorted(merged + single)
    for _, syms in packages[:2 * len(used) - 2]:
        for s in syms:
            out[s] += 1
    assert sum(2.0 ** -n for n in out if n) == 1.0, "package-merge broke Kraft"
    return out


def canonical_codes(lengths: list[int]) -> dict[int, tuple[int, int]]:
    """Canonical codes ``{symbol: (code, length)}``: shorter first, then by symbol."""
    codes = {}
    code = 0
    prev_len = 0
    for length, sym in sorted((n, s) for s, n in enumerate(lengths) if n):
        code <<= length - prev_len
        codes[sym] = (code, length)
        code += 1
        prev_len = length
    return codes


def _slot(formatted_offset: int) -> int:
    return bisect_right(LZX_BASE, formatted_offset) - 1


def _find_matches(chunk: bytes) -> list[tuple]:
    """Greedy LZ77: ``('lit', byte)`` or ``('m', offset, length)`` operations."""
    n = len(chunk)
    ops = []
    last: dict[bytes, list[int]] = {}
    i = 0
    while i < n:
        best_len = 0
        best_off = 0
        if i + 3 <= n:
            key = chunk[i:i + 3]
            limit = min(MAX_MATCH, n - i)
            for j in reversed(last.get(key, [])[-CHAIN_LIMIT:]):
                off = i - j
                if off > WINDOW_SIZE - 2:
                    break
                length = 3
                # Extend 16 bytes at a time while equal, then byte by byte.
                while length + 16 <= limit and chunk[j + length:j + length + 16] == \
                        chunk[i + length:i + length + 16]:
                    length += 16
                while length < limit and chunk[j + length] == chunk[i + length]:
                    length += 1
                if length > best_len:
                    best_len, best_off = length, off
                    if length >= GOOD_ENOUGH:
                        break
        if best_len >= MIN_MATCH:
            ops.append(("m", best_off, best_len))
            for p in range(i, min(i + best_len, n - 2)):
                last.setdefault(chunk[p:p + 3], []).append(p)
            i += best_len
        else:
            ops.append(("lit", chunk[i]))
            if i + 3 <= n:
                last.setdefault(chunk[i:i + 3], []).append(i)
            i += 1
    return ops


def _resolve_repeats(ops: list[tuple]) -> list[tuple]:
    """Replace offsets with LZX "formatted offsets", using the R0/R1/R2 repeat codes."""
    r = [1, 1, 1]
    out = []
    for op in ops:
        if op[0] == "lit":
            out.append(op)
            continue
        _, off, length = op
        if off == r[0]:
            fmt = 0
        elif off == r[1]:
            fmt = 1
            r[1] = r[0]
            r[0] = off
        elif off == r[2]:
            fmt = 2
            r[2] = r[0]
            r[0] = off
        else:
            fmt = off + 2
            r[2] = r[1]
            r[1] = r[0]
            r[0] = off
        out.append(("m", fmt, length))
    return out


class _BitWriter:
    """Packs bits MSB-first into 16-bit little-endian words (the LZX bit order)."""

    def __init__(self) -> None:
        self.out = bytearray()
        self.acc = 0
        self.n = 0

    def put(self, value: int, nbits: int) -> None:
        self.acc = (self.acc << nbits) | value
        self.n += nbits
        while self.n >= 16:
            self.n -= 16
            w = self.acc >> self.n
            self.out += bytes((w & 0xFF, (w >> 8) & 0xFF))
            self.acc &= (1 << self.n) - 1

    def finish(self) -> bytes:
        if self.n:
            self.put(0, 16 - self.n)
        return bytes(self.out)


def _write_lengths(w: _BitWriter, lens: list[int], prev: list[int]) -> None:
    """Write one pretree-coded run of code lengths (deltas from ``prev``, mod 17)."""
    ops = []  # (pretree symbol, (extra value, extra bits) or None)
    x = 0
    while x < len(lens):
        if lens[x] == 0:
            run = 0
            while x + run < len(lens) and lens[x + run] == 0:
                run += 1
            while run >= 20:
                take = min(run, 51)
                ops.append((18, (take - 20, 5)))
                run -= take
                x += take
            while run >= 4:
                take = min(run, 19)
                ops.append((17, (take - 4, 4)))
                run -= take
                x += take
            for _ in range(run):
                ops.append((prev[x] % 17, None))
                x += 1
        else:
            ops.append(((prev[x] - lens[x]) % 17, None))
            x += 1
    freq = [0] * 20
    for s, _ in ops:
        freq[s] += 1
    plens = huffman_lengths(freq, 15)
    pcodes = canonical_codes(plens)
    for s in range(20):
        w.put(plens[s], 4)
    for s, extra in ops:
        code, length = pcodes[s]
        w.put(code, length)
        if extra:
            w.put(extra[0], extra[1])


def encode_uncompressed_chunk(chunk: bytes) -> bytes:
    """One LZX stream holding ``chunk`` as an *uncompressed* block (type 3).

    Layout, as in the shipped chunks: the 28 header bits padded to a 16-bit word, the
    repeat offsets R0, R1, R2 as little-endian u32s (1, 1, 1: a fresh stream), the bytes,
    and a padding byte when the length is odd.
    """
    w = _BitWriter()
    w.put(0, 1)        # no Intel E8 translation
    w.put(3, 3)        # block type 3: uncompressed
    w.put(len(chunk), 24)
    head = w.finish()  # 28 bits -> 2 words; never word-aligned, so no extra word
    pad = b"\0" if len(chunk) & 1 else b""
    return head + (1).to_bytes(4, "little") * 3 + bytes(chunk) + pad


def encode_chunk(chunk: bytes) -> bytes:
    """Compress up to 32 KB into one independent LZX stream.

    Normally one verbatim block; an uncompressed block when that would be smaller (see
    the module docstring). The result is the bare LZX bit stream. Wrap it with
    ``xcompress.compress_entry``, which adds the chunk framing and checks the result by
    decoding it.
    """
    verbatim = encode_verbatim_chunk(chunk)
    if len(verbatim) >= 16 + len(chunk) + (len(chunk) & 1):
        return encode_uncompressed_chunk(chunk)
    return verbatim


def encode_verbatim_chunk(chunk: bytes) -> bytes:
    """Compress up to 32 KB into one LZX stream made of a single verbatim block."""
    n = len(chunk)
    if not 0 < n <= WINDOW_SIZE:
        raise ValueError(f"an LZX chunk holds 1..{WINDOW_SIZE} bytes, not {n}")
    rops = _resolve_repeats(_find_matches(chunk))

    main_freq = [0] * MAIN_ELEMENTS
    len_freq = [0] * LENGTH_SYMBOLS
    for op in rops:
        if op[0] == "lit":
            main_freq[op[1]] += 1
        else:
            _, fmt, length = op
            header = min(length - 2, 7)
            main_freq[256 + _slot(fmt) * 8 + header] += 1
            if header == 7:
                len_freq[length - 2 - 7] += 1
    main_len = huffman_lengths(main_freq, 16)
    length_len = huffman_lengths(len_freq, 16)
    if not any(length_len):
        # No long matches: the length tree would be empty. Shipped streams never have
        # an empty length tree, so write a harmless two-code one.
        length_len[0] = length_len[1] = 1
    main_codes = canonical_codes(main_len)
    length_codes = canonical_codes(length_len)

    w = _BitWriter()
    w.put(0, 1)        # no Intel E8 translation
    w.put(1, 3)        # block type 1: verbatim
    w.put(n, 24)       # block length
    _write_lengths(w, main_len[:256], [0] * 256)
    _write_lengths(w, main_len[256:], [0] * (MAIN_ELEMENTS - 256))
    _write_lengths(w, length_len, [0] * LENGTH_SYMBOLS)
    for op in rops:
        if op[0] == "lit":
            code, length = main_codes[op[1]]
            w.put(code, length)
            continue
        _, fmt, mlen = op
        slot = _slot(fmt)
        header = min(mlen - 2, 7)
        code, length = main_codes[256 + slot * 8 + header]
        w.put(code, length)
        if header == 7:
            code, length = length_codes[mlen - 2 - 7]
            w.put(code, length)
        extra = LZX_EXTRA[slot]
        if extra:
            w.put(fmt - LZX_BASE[slot], extra)
    return w.finish()

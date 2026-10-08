"""Unit tests for LZX decode/encode and the XMemCompress chunk framing.

The decoders are checked against streams built independently of them:

* `literal_only_stream`: the CZ recomp's "every byte codes as itself" trick (a main tree
  whose 256 literals all have length 8), written bit by bit here;
* `aligned_stream`: an *aligned offset* block (type 2), which the toolkit's encoder never
  writes but 36,090 shipped chunks start with;
* the encoder's own verbatim (type 1) and uncompressed (type 3) blocks.

Both decoders (native when it is built, and pure Python) must give the same bytes.
"""

import os
import random

import pytest

from dr2kit.container import lzx, xcompress
from dr2kit.container.lzx import encode, native, pydecode
from dr2kit.errors import LzxError

NATIVE = native.load()
DECODERS = [pytest.param(pydecode.decompress, id="python")]
DECODERS.append(pytest.param(
    NATIVE.decompress if NATIVE else None, id="native",
    marks=pytest.mark.skipif(NATIVE is None, reason=f"native LZX library not built: "
                                                     f"{native.load_error()}")))


class Bits:
    """Test-only bit writer (MSB-first into 16-bit LE words), deliberately simple."""

    def __init__(self):
        self.bits = []

    def put(self, value, n):
        self.bits += [(value >> i) & 1 for range_i in [range(n - 1, -1, -1)] for i in range_i]

    def bytes(self):
        bits = self.bits + [0] * (-len(self.bits) % 16)
        out = bytearray()
        for k in range(0, len(bits), 16):
            v = int("".join(map(str, bits[k:k + 16])), 2)
            out += v.to_bytes(2, "little")
        return bytes(out)


def literal_only_stream(data: bytes) -> bytes:
    """A verbatim block in which every byte is a literal with code == byte (8 bits)."""
    b = Bits()
    b.put(0, 1)
    b.put(1, 3)
    b.put(len(data), 24)
    # main tree, first 256: pretree {9:1, 17:1} -> symbol 9 = code 0 = "(0 - 9) mod 17 = 8"
    for s in range(20):
        b.put(1 if s in (9, 17) else 0, 4)
    for _ in range(256):
        b.put(0, 1)
    # main tree, 240 match symbols: zeros as 18-runs; pretree {17:1, 18:1}: 18 -> code 1
    for s in range(20):
        b.put(1 if s in (17, 18) else 0, 4)
    for run in (51, 51, 51, 51, 36):
        b.put(1, 1)
        b.put(run - 20, 5)
    # length tree: 249 zeros
    for s in range(20):
        b.put(1 if s in (17, 18) else 0, 4)
    for run in (51, 51, 51, 51, 45):
        b.put(1, 1)
        b.put(run - 20, 5)
    for byte in data:
        b.put(byte, 8)
    return b.bytes()


def aligned_stream(data: bytes) -> bytes:
    """An aligned-offset block (type 2) for ``data``, built from the encoder's matches."""
    rops = encode._resolve_repeats(encode._find_matches(data))
    main_freq = [0] * encode.MAIN_ELEMENTS
    len_freq = [0] * encode.LENGTH_SYMBOLS
    for op in rops:
        if op[0] == "lit":
            main_freq[op[1]] += 1
        else:
            h = min(op[2] - 2, 7)
            main_freq[256 + encode._slot(op[1]) * 8 + h] += 1
            if h == 7:
                len_freq[op[2] - 9] += 1
    main_len = encode.huffman_lengths(main_freq, 16)
    length_len = encode.huffman_lengths(len_freq, 16)
    if not any(length_len):
        length_len[0] = length_len[1] = 1
    mc, lc = encode.canonical_codes(main_len), encode.canonical_codes(length_len)
    w = encode._BitWriter()
    w.put(0, 1)
    w.put(2, 3)                      # aligned offset block
    w.put(len(data), 24)
    for _ in range(8):
        w.put(3, 3)                  # aligned tree: 8 codes of 3 bits, symbol i = code i
    encode._write_lengths(w, main_len[:256], [0] * 256)
    encode._write_lengths(w, main_len[256:], [0] * 240)
    encode._write_lengths(w, length_len, [0] * 249)
    for op in rops:
        if op[0] == "lit":
            w.put(*mc[op[1]])
            continue
        _, fmt, mlen = op
        slot = encode._slot(fmt)
        h = min(mlen - 2, 7)
        w.put(*mc[256 + slot * 8 + h])
        if h == 7:
            w.put(*lc[mlen - 9])
        extra = encode.LZX_EXTRA[slot]
        value = fmt - encode.LZX_BASE[slot]
        if extra >= 3:
            w.put(value >> 3, extra - 3)  # verbatim high bits
            w.put(value & 7, 3)           # aligned symbol, code == symbol
        elif extra:
            w.put(value, extra)
    return w.finish()


def sample(kind: str, n: int) -> bytes:
    rnd = random.Random(n)
    if kind == "text":
        words = [b"zombie", b"chuck", b"katey", b"zombrex", b"motorcycle", b"\n", b" "]
        out = bytearray()
        while len(out) < n:
            out += rnd.choice(words)
        return bytes(out[:n])
    if kind == "zeros":
        return bytes(n)
    if kind == "random":
        return rnd.randbytes(n)
    if kind == "far":  # matches with large offsets (high position slots)
        block = rnd.randbytes(9000)
        return (block + bytes(15000) + block)[:n]
    raise ValueError(kind)


@pytest.mark.parametrize("decode", DECODERS)
def test_literal_only_stream(decode):
    data = sample("random", 3000)
    assert decode(literal_only_stream(data), len(data)) == data


@pytest.mark.parametrize("decode", DECODERS)
@pytest.mark.parametrize("kind", ["text", "far", "zeros"])
def test_aligned_block(decode, kind):
    data = sample(kind, 32768)
    assert decode(aligned_stream(data), len(data)) == data


@pytest.mark.parametrize("decode", DECODERS)
@pytest.mark.parametrize("kind,n", [("text", 1), ("text", 32768), ("zeros", 32768),
                                    ("random", 5000), ("random", 47), ("far", 32768)])
def test_encoder_round_trip(decode, kind, n):
    data = sample(kind, n)
    stream = encode.encode_chunk(data)
    assert decode(stream, len(data)) == data


def test_incompressible_chunk_uses_uncompressed_block():
    data = sample("random", 4001)       # odd length: exercises the padding byte
    stream = encode.encode_chunk(data)
    assert len(stream) == 4 + 12 + 4001 + 1
    assert pydecode.decompress(stream, len(data)) == data


def test_decoder_rejects_garbage():
    with pytest.raises(LzxError):
        pydecode.decompress(b"\xff" * 64, 1000)
    good = encode.encode_chunk(sample("text", 2000))
    with pytest.raises(LzxError):
        pydecode.decompress(good[:20], 2000)


@pytest.mark.parametrize("kind,n", [("text", 100000), ("random", 40000), ("zeros", 32769)])
def test_compress_entry_round_trip(kind, n):
    data = sample(kind, n)
    stored = xcompress.compress_entry(data)
    info = xcompress.parse_stream(stored)
    assert info.uncompressed_size == n
    assert [c.uncompressed for c in info.chunks][:-1] == [0x8000] * (len(info.chunks) - 1)
    assert all(c.padding == 5 for c in info.chunks)
    assert xcompress.decompress_entry(stored, n) == data
    assert xcompress.decompress_entry(stored, n, python=True) == data


def test_empty_entry_form():
    assert xcompress.compress_entry(b"") == b"\0\0\0\0"
    assert xcompress.decompress_entry(b"\0\0\0\0", 0) == b""


@pytest.mark.parametrize("damage, message", [
    (lambda s: s[:12] + b"\xfe" + s[13:], "not 0xFF"),
    (lambda s: s + b"\0\0", "stray bytes"),
    (lambda s: (5).to_bytes(4, "big") + s[4:], "header says"),
    (lambda s: s[:4] + (0x10000).to_bytes(4, "big") + s[8:], "window size"),
])
def test_framing_errors_are_named(damage, message):
    stored = xcompress.compress_entry(sample("text", 1000))
    with pytest.raises(LzxError, match=message):
        xcompress.parse_stream(damage(stored), "t")


def test_size2_mismatch():
    stored = xcompress.compress_entry(sample("text", 1000))
    with pytest.raises(LzxError, match="index says"):
        xcompress.decompress_entry(stored, 999)


def test_backend_is_reported():
    assert lzx.backend() in ("native", "python")
    assert lzx.backend() in lzx.backend_detail()


def test_huffman_lengths_complete():
    for freqs in ([0, 5, 0], [1, 1], [10, 1, 1, 1, 0, 3], list(range(1, 300))):
        lens = encode.huffman_lengths(freqs, 16)
        assert sum(2.0 ** -n for n in lens if n) == 1.0
        assert max(lens) <= 16


@pytest.mark.skipif(os.environ.get("DR2KIT_LZX", "").lower() == "python",
                    reason="native decoder disabled by DR2KIT_LZX=python")
def test_native_and_python_agree_when_native_present():
    if NATIVE is None:
        pytest.skip(f"native LZX library not built: {native.load_error()}")
    data = sample("text", 30000)
    s = encode.encode_chunk(data)
    assert NATIVE.decompress(s, len(data)) == pydecode.decompress(s, len(data)) == data

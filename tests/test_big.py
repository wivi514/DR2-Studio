"""Unit tests for dr2kit.container.big (synthetic archives only)."""

import struct

import pytest

from dr2kit.container.big import BigArchive, BigEntry, HEADER_SIZE, LZX, MAGIC, STORED, is_big
from dr2kit.errors import FormatError
from dr2kit.hashing import entry_hash

from conftest import make_archive


def hand_built() -> bytes:
    """An archive laid out by hand from the spec in docs/formats.md, not by the writer.

    Two entries, "a.txt" (5 bytes at 0x40) and "B.bin" (3 bytes at 0x48, 8-aligned),
    so the parser is checked against the format, not against itself.
    """
    count = 2
    names_offset = HEADER_SIZE + count * 28           # 0x18 + 56 = 0x50
    names = b"a.txt\0B.bin\0"
    data_start = names_offset + len(names)            # 0x5C
    off_a = data_start                                 # 0x5C, lowbit 4
    off_b = 0x68                                       # 8-aligned, after 0x5C + 5 = 0x61
    total = off_b + 3
    out = bytearray(total)
    struct.pack_into("<6I", out, 0, 0x03040506, data_start, total, count, 0x18, names_offset)
    struct.pack_into("<7I", out, 0x18, names_offset, entry_hash("a.txt"), 5, 5, off_a, 0x4, 0)
    struct.pack_into("<7I", out, 0x18 + 28, names_offset + 6, entry_hash("B.bin"), 3, 3,
                     off_b, 0x800, 0)
    out[names_offset:data_start] = names
    out[off_a:off_a + 5] = b"hello"
    out[off_b:off_b + 3] = b"xyz"
    return bytes(out)


def test_parse_hand_built_archive():
    raw = hand_built()
    arc = BigArchive.parse(raw, "hand")
    assert [e.name for e in arc] == ["a.txt", "B.bin"]
    a, b = arc.entries
    assert a.stored == b"hello" and a.size == 5 and a.size2 == 5 and a.flags == 0x4
    assert b.stored == b"xyz" and b.flags == 0x800 and b.data_offset == 0x68
    assert b.alignment == 8
    assert a.ext == "txt" and b.ext == "bin"


def test_round_trip_is_byte_identical():
    raw = hand_built()
    assert BigArchive.parse(raw).to_bytes() == raw


def test_written_archive_reads_back():
    arc = make_archive(("one.txt", b"1" * 10), ("two", b""), ("three.bct", b"\x05\x01\x01\xe2"))
    raw = arc.to_bytes()
    back = BigArchive.parse(raw)
    assert [(e.name, e.stored) for e in back] == [(e.name, e.stored) for e in arc]
    assert all(e.hash == entry_hash(e.name) for e in back)
    assert back.to_bytes() == raw
    assert is_big(raw) and raw[:4] == MAGIC


def test_payloads_keep_alignment_after_resize():
    arc = make_archive(("a", b"x"), ("b", b"y" * 7), alignment=0x800)
    arc.entries[0].set_data(b"longer than before")
    back = BigArchive.parse(arc.to_bytes())
    assert all(e.data_offset % 0x800 == 0 for e in back)
    assert back.get("a").stored == b"longer than before"


def test_compressed_entry_round_trip():
    text = b"the quick brown fox jumps over the lazy dog\n" * 2000
    arc = make_archive(("story.txt", text, LZX), ("raw.bin", b"\x00\x01"))
    back = BigArchive.parse(arc.to_bytes())
    e = back.get("STORY.TXT")
    assert e.compressed and e.compression == LZX
    assert e.size < e.size2 == len(text)
    assert e.data() == text
    assert e.data(python_lzx=True) == text


def test_set_data_keeps_compression():
    arc = make_archive(("t.txt", b"abc" * 100, LZX))
    e = arc.entries[0]
    e.set_data(b"new text " * 50)
    assert e.compression == LZX and e.data() == b"new text " * 50
    e.set_data(b"plain", compression=STORED)
    assert e.compression == STORED and e.stored == b"plain" and e.size2 == 5


def test_duplicate_names_by_position_and_occurrence():
    arc = make_archive(("Combined Vertices", b"1"), ("x", b"2"), ("combined vertices", b"3"))
    assert [e.stored for e in arc.find("COMBINED VERTICES")] == [b"1", b"3"]
    assert arc.get("Combined Vertices", 1).stored == b"3"
    with pytest.raises(KeyError):
        arc.get("Combined Vertices", 2)


@pytest.mark.parametrize("damage, message", [
    (lambda b: b"\x00" + b[1:], "magic"),
    (lambda b: b + b"\x00", "header says"),
    (lambda b: b[:0x14] + struct.pack("<I", 0x99) + b[0x18:], "names_offset"),
    (lambda b: b[:0x10] + struct.pack("<I", 0x20) + b[0x14:], "header size"),
    (lambda b: b[:0x5C + 5] + b"\x01" + b[0x5C + 6:], "non-zero bytes"),
])
def test_damaged_archives_are_named_not_skipped(damage, message):
    with pytest.raises(FormatError, match=message):
        BigArchive.parse(damage(hand_built()), "broken.big")


def test_short_input():
    with pytest.raises(FormatError, match="shorter than"):
        BigArchive.parse(b"\x06\x05", "tiny")


def test_ext_ignores_node_names():
    def ext(name):
        return BigEntry(name=name, stored=b"", size2=0).ext
    assert ext("chest_default.tex") == "tex"
    assert ext("dummy01.l_thigh") == ""
    assert ext("Combined Vertices") == ""
    assert ext("pc_options.TXT") == "txt"

"""The engine string hash (dr2kit.hashing)."""

from dr2kit.hashing import entry_hash, name_hash


def test_known_value():
    # Index hash of the entry "mech_apron_cm" in Case Zero (data/models/npcs.big/
    # boss_mechanic.tex). A number from the index, not game content.
    assert entry_hash("mech_apron_cm") == 0x98D7360F


def test_formula():
    assert name_hash("") == 0
    assert name_hash("a") == 0x61
    assert name_hash("ab") == (0x61 * 33) ^ 0x62
    assert name_hash(b"ab\0cd") == name_hash("ab")          # stops at NUL


def test_signed_char():
    # Bytes >= 0x80 are sign-extended before the XOR (the engine uses a signed char).
    assert name_hash(b"\xe9") == 0xFFFFFFE9


def test_entry_hash_lowercases():
    assert entry_hash("Prologue.TXT") == name_hash("prologue.txt") != name_hash("Prologue.TXT")

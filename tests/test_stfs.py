"""STFS block arithmetic (dr2kit.container.stfs). Real packages: test_gamedata.py."""

import pytest

from dr2kit.container import stfs
from dr2kit.errors import FormatError


def test_block_offsets_skip_hash_tables():
    """Layout: [L0 table 0][data 0..169][L1 table][L0 table 1][data 170..339]…"""
    base = 0xA000
    assert stfs.block_index_to_offset(base, 0) == base + (1 << 12)      # behind L0 #0
    assert stfs.block_index_to_offset(base, 169) == base + (170 << 12)  # end of group 0
    assert stfs.block_index_to_offset(base, 170) == base + (173 << 12)  # behind L1, L0 #1


def test_not_a_package(tmp_path):
    p = tmp_path / "x"
    p.write_bytes(b"NOPE" + bytes(0x2000))
    with pytest.raises(FormatError, match="not an XContent package"):
        stfs.Package(p)

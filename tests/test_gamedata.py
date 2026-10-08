"""Tests on the real games. Each one SKIPS, saying why, when the game isn't installed.

These are the phase 1 gates in test form (docs/roadmap.md, docs/dev/testing.md):
every archive round-trips byte-identically, every compressed entry decodes to its size2,
nothing is left unparsed, and unpacking the XBLA package gives the recomp's files.
Nothing here copies game data into the repository.

The slow LZX gates (re-encode every compressed entry, pure-Python decode of every
compressed entry) are not tests; run them with
``dr2 census --reencode --python-lzx`` (minutes, all CPUs).
"""

import random

import pytest

from dr2kit.census import run_census
from dr2kit.container.stfs import Package
from dr2kit.container.vpath import AssetTree
from dr2kit.profiles import find_packages, load_profile

pytestmark = pytest.mark.gamedata


@pytest.mark.slow
@pytest.mark.parametrize("game", ["cz", "cw"])
def test_census_gates(game, game_root):
    root = game_root(game)
    rep = run_census(game, AssetTree(root))
    assert rep.problems == [], f"{len(rep.problems)} problems, e.g. {rep.problems[:5]}"
    assert rep.roundtrip_ok == rep.archives
    assert rep.decoded_ok == rep.compression.get(2, 0)
    assert rep.hash_ok == rep.entries
    assert rep.unsafe_names == []
    expected = load_profile(game).census
    assert rep.archive_files == expected["archive_files"]
    assert rep.archives == expected["archives"]
    assert rep.entries == expected["entries"]


@pytest.mark.parametrize("game", ["cz", "cw"])
def test_python_decoder_on_a_sample(game, game_root):
    """Fast cross-check of the pure-Python decoder on a few real compressed entries."""
    tree = AssetTree(game_root(game))
    arc = tree.open_archive("data/datafile.big")
    entries = [e for e in arc.entries if e.compressed][:5]
    assert entries, "datafile.big has compressed entries in both games"
    for e in entries:
        assert e.data(python_lzx=True) == e.data()


@pytest.mark.parametrize("game", ["cz", "cw"])
def test_stfs_matches_unpacked_data(game, game_root):
    root = game_root(game)
    packages = find_packages(game)
    if not packages:
        pytest.skip(f"no {game} XBLA package next to the recomp")
    with Package(packages[0]) as pkg:
        assert f"{pkg.title_id:08X}" == load_profile(game).title_id
        data_files = sorted(p for p in pkg.files if p.lower().startswith("data/"))
        on_disk = {vp.lower() for vp, _ in AssetTree(root).files()}
        assert {p.lower() for p in data_files} == on_disk
        # Byte-compare a sample (all of them takes a while; `dr2 unpack` + diff does that).
        for name in random.Random(0).sample(data_files, 12) + ["data/datafile.big"]:
            assert pkg.read(name) == (root / name).read_bytes(), name

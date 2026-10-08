"""Unit tests for virtual paths over a synthetic game folder."""

import pytest

from dr2kit.container.big import LZX
from dr2kit.container.vpath import AssetTree, split
from dr2kit.errors import VPathError

from conftest import make_archive


@pytest.fixture
def tree(tmp_path):
    """data/models/Pack.big holds a stored nested archive and a compressed one."""
    inner = make_archive(("chest_cm", b"\x05\x01\x01\xe2colour"), ("chest_nm", b"normal"))
    deep = make_archive(("persistent.big", make_archive(("leaf", b"deep!")).to_bytes()))
    pack = make_archive(
        ("chest.tex", inner.to_bytes()),
        ("model.big", deep.to_bytes(), LZX),
        ("Combined Vertices", b"v0"),
        ("Combined Vertices", b"v1"),
    )
    d = tmp_path / "data" / "models"
    d.mkdir(parents=True)
    (d / "Pack.big").write_bytes(pack.to_bytes())
    (tmp_path / "data" / "loose.txt").write_bytes(b"hi")
    return AssetTree(tmp_path)


def test_split_normalises():
    assert split("\\data\\models//x.big/") == ["data", "models", "x.big"]
    with pytest.raises(VPathError):
        split("data/../secret")


def test_resolve_is_case_insensitive_and_returns_real_case(tree):
    n = tree.resolve("DATA/MODELS/pack.BIG/CHEST.TEX/Chest_CM")
    assert n.kind == "entry"
    assert n.vpath == "data/models/Pack.big/chest.tex/chest_cm"
    assert n.data() == b"\x05\x01\x01\xe2colour"


def test_compressed_nested_archive_is_opened(tree):
    n = tree.resolve("data/models/pack.big/model.big/persistent.big/leaf")
    assert n.data() == b"deep!"


def test_duplicates_by_occurrence_and_position(tree):
    assert tree.resolve("data/models/pack.big/combined vertices").data() == b"v0"
    n = tree.resolve("data/models/pack.big/Combined Vertices#1")
    assert n.data() == b"v1" and n.vpath.endswith("Combined Vertices#1")
    assert tree.resolve("data/models/pack.big/@3").data() == b"v1"


def test_dirs_and_files(tree):
    assert tree.resolve("data").kind == "dir"
    f = tree.resolve("data/LOOSE.txt")
    assert f.kind == "file" and f.data() == b"hi"


@pytest.mark.parametrize("bad, message", [
    ("data/nope", "no such file"),
    ("data/models/pack.big/missing", "no entry named"),
    ("data/models/pack.big/@99", "no entry at position"),
    ("data/loose.txt/inside", "not an archive"),
    ("data/models/pack.big/combined vertices/x", "not an archive"),
])
def test_errors_name_the_problem(tree, bad, message):
    with pytest.raises(VPathError, match=message):
        tree.resolve(bad)


def test_walk_archives_finds_every_level(tree):
    found = {(vp, depth) for vp, _, depth in tree.walk_archives()}
    assert found == {
        ("data/models/Pack.big", 0),
        ("data/models/Pack.big/chest.tex", 1),
        ("data/models/Pack.big/model.big", 1),
        ("data/models/Pack.big/model.big/persistent.big", 2),
    }

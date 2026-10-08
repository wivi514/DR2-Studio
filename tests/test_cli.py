"""The dr2 command on a synthetic game folder (via DR2_CZ_DATA)."""

import json

import pytest

from dr2kit.cli.main import main
from dr2kit.container.big import LZX

from conftest import make_archive


@pytest.fixture
def game(tmp_path, monkeypatch):
    nested = make_archive(("leaf.txt", b"leaf text " * 50, LZX))
    pack = make_archive(("tex_cm", b"\x05\x01\x01\xe2" + bytes(60)),
                        ("model.big", nested.to_bytes()),
                        ("notes.txt", b"hello zombies " * 100, LZX))
    (tmp_path / "game" / "data").mkdir(parents=True)
    (tmp_path / "game" / "data" / "pack.big").write_bytes(pack.to_bytes())
    monkeypatch.setenv("DR2_CZ_DATA", str(tmp_path / "game"))
    return tmp_path


def test_ls(game, capsys):
    assert main(["ls", "data/pack.big", "-l"]) == 0
    out = capsys.readouterr().out
    assert "notes.txt" in out and "model.big" in out and "3 entries" in out


def test_find(game, capsys):
    assert main(["find", "LEAF"]) == 0
    assert "data/pack.big/model.big/leaf.txt" in capsys.readouterr().out


def test_extract_decompresses_by_default(game):
    out = game / "out"
    assert main(["extract", "data/pack.big/notes.txt", "-o", str(out), "-q"]) == 0
    assert (out / "data/pack.big/notes.txt").read_bytes() == b"hello zombies " * 100


def test_extract_raw_keeps_stream(game, capsys):
    out = game / "raw"
    assert main(["extract", "data/pack.big/notes.txt", "--raw", "-o", str(out), "-q"]) == 0
    assert (out / "data/pack.big/notes.txt").read_bytes()[:4] == (1400).to_bytes(4, "big")
    assert "LZX stream" in capsys.readouterr().err


def test_extract_recursive(game):
    out = game / "all"
    assert main(["extract", "data/pack.big", "-r", "-o", str(out), "-q"]) == 0
    assert (out / "data/pack.big/model.big/leaf.txt").read_bytes() == b"leaf text " * 50
    assert (out / "data/pack.big/tex_cm").is_file()


def test_census_clean(game, capsys, tmp_path):
    report = tmp_path / "c.json"
    assert main(["census", "cz", "-q", "--python-lzx", "--json", str(report)]) == 0
    out = capsys.readouterr().out
    assert "round trip identical: 2/2 archives" in out
    assert "PROBLEMS (unparsed or failed): 0" in out
    data = json.loads(report.read_text())
    assert data[0]["archives"] == 2 and data[0]["decoded_ok"] == 2


def test_census_reports_broken_archive(game, capsys):
    (game / "game" / "data" / "broken.big").write_bytes(b"\x06\x05\x04\x03" + bytes(30))
    assert main(["census", "cz", "-q"]) == 1
    assert "data/broken.big: parse:" in capsys.readouterr().out


def test_missing_game_is_an_error_not_a_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DR2_CZ_DATA", str(tmp_path / "nowhere"))
    assert main(["ls"]) == 1
    assert capsys.readouterr().err.startswith("error:")

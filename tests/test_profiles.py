"""Game profiles and data discovery (dr2kit.profiles)."""

import pytest

from dr2kit import profiles
from dr2kit.errors import GameNotFoundError

from conftest import make_archive


def fake_game(root):
    (root / "data").mkdir(parents=True)
    (root / "data" / "datafile.big").write_bytes(make_archive(("a.txt", b"x")).to_bytes())
    return root


def test_builtin_profiles():
    cz, cw = profiles.load_profile("cz"), profiles.load_profile("CW")
    assert (cz.id, cz.title_id) == ("cz", "58410A8D")
    assert (cw.id, cw.title_id) == ("cw", "58410B00")
    with pytest.raises(GameNotFoundError):
        profiles.load_profile("otr")


def test_normalise_root_accepts_both_levels(tmp_path):
    root = fake_game(tmp_path / "game")
    assert profiles.normalise_root(root) == root.resolve()
    assert profiles.normalise_root(root / "data") == root.resolve()
    assert profiles.normalise_root(tmp_path) is None


def test_environment_override(tmp_path, monkeypatch):
    root = fake_game(tmp_path / "g")
    monkeypatch.setenv("DR2_CW_DATA", str(root))
    loc = profiles.locate("cw")
    assert loc.how == "environment" and loc.root == root.resolve()
    monkeypatch.setenv("DR2_CW_DATA", str(tmp_path / "nothing"))
    with pytest.raises(GameNotFoundError):
        profiles.locate("cw")


def test_set_game_root_is_remembered(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg" / "config.toml"
    monkeypatch.setattr(profiles, "config_path", lambda: cfg)
    monkeypatch.delenv("DR2_CZ_DATA", raising=False)
    root = fake_game(tmp_path / 'odd "name" \\ here')
    profiles.set_game_root("cz", root / "data")
    loc = profiles.locate("cz")
    assert loc.how == "config" and loc.root == root.resolve()
    with pytest.raises(GameNotFoundError):
        profiles.set_game_root("cz", tmp_path / "empty")


def test_missing_game_says_how_to_fix(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "config_path", lambda: tmp_path / "none.toml")
    monkeypatch.setattr(profiles, "_CHECKOUT", tmp_path)
    monkeypatch.delenv("DR2_CZ_DATA", raising=False)
    with pytest.raises(GameNotFoundError, match="dr2 games set cz"):
        profiles.locate("cz")

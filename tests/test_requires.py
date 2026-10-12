"""What a mod needs (`dr2kit.mods.requires`, phase 15): inferred, written, checked."""

import json
import zipfile

import pytest

from dr2kit.cli.main import main
from dr2kit.container.vpath import AssetTree
from dr2kit.mods import requires
from dr2kit.mods.build import plan_mods
from dr2kit.mods.library import ModLibrary, pack
from dr2kit.mods.manifest import Mod, ModError, create

from conftest import make_archive


@pytest.fixture
def game(tmp_path, monkeypatch):
    root = tmp_path / "assets" / "game"
    (root / "data").mkdir(parents=True)
    (root / "data" / "datafile.big").write_bytes(
        make_archive(("a.txt", b"a"), ("b.txt", b"b")).to_bytes())
    monkeypatch.setenv("DR2_CZ_DATA", str(root))
    monkeypatch.setenv("DR2_CW_DATA", str(tmp_path / "nowhere"))
    return root


def mod_with(tmp_path, name, replace=None, add=None, requires_toml=""):
    root = create(tmp_path / name, name)
    if requires_toml:
        with open(root / "mod.toml", "a") as f:
            f.write("\n[requires]\n" + requires_toml)
    for base, files in (("replace", replace or {}), ("add", add or {})):
        for vp, data in files.items():
            f = root / base / vp
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data if isinstance(data, bytes) else data.encode())
    return Mod.load(root)


def test_looks_only_mod_is_local_and_safe(tmp_path):
    m = mod_with(tmp_path, "skin", {"data/x.big/a_cm.png": b"png"})
    r = requires.infer(m)
    assert (r.saves, r.coop, r.sources, r.play) == ("safe", "local", [], ["cz", "cw"])


def test_added_things_need_the_mod_and_every_player(tmp_path):
    recipe = json.dumps({"format": "dr2kit-copy/1", "from": "cw",
                         "copy": "data/streamedassets.big/Laser_Sword.big"})
    m = mod_with(tmp_path, "laser", add={"data/streamedassets.big/LS.big.copy.json": recipe})
    r = requires.infer(m)
    assert (r.saves, r.coop, r.sources) == ("needs-mod", "all-players", ["cw"])
    assert r.games == ["cz", "cw"]
    j = r.to_json()
    assert j["games"] == {"cz": "58410A8D", "cw": "58410B00"} and j["built_from"] == ["cw"]
    assert "Case West" in r.to_text()


def test_written_keys_win(tmp_path):
    m = mod_with(tmp_path, "w", {"data/x.big/a_cm.png": b"png"},
                 requires_toml='play = "cz"\nmods = ["other>=1.2"]\ncoop = "host-only"\n')
    r = requires.infer(m)
    assert r.play == ["cz"] and r.coop == "host-only" and r.mods == [("other", ">=1.2")]
    assert set(r.written) == {"play", "mods", "coop"}
    m.save()                                     # [requires] survives a save
    assert Mod.load(m.root).requires["mods"] == ["other>=1.2"]


def test_bad_requires_is_refused(tmp_path):
    with pytest.raises(ModError, match="unknown key"):
        mod_with(tmp_path, "bad", requires_toml='colour = "red"\n')


def test_versions():
    assert requires.version_ok("1.2.0", ">=1.2") and not requires.version_ok("1.1", ">=1.2")
    assert requires.version_ok("2", "") and requires.version_ok("0.1.0.dev0", ">=0.1.0")
    assert requires.parse_spec("Other_Mod >= 1.0") == ("other_mod", ">=1.0")
    assert requires.parse_spec("x=2") == ("x", "==2")


def test_build_refuses_missing_game_and_mod(tmp_path, game):
    recipe = json.dumps({"format": "dr2kit-copy/1", "from": "cw", "copy": "data/x.big"})
    m = mod_with(tmp_path, "needscw", add={"data/datafile.big/n.txt.copy.json": recipe})
    with pytest.raises(ModError, match="Case West's game data"):
        plan_mods([m], "cz", AssetTree(game))
    n = mod_with(tmp_path, "needsmod", {"data/datafile.big/a.txt": b"A"},
                 requires_toml='mods = ["base>=2"]\n')
    with pytest.raises(ModError, match="needs the mod base"):
        plan_mods([n], "cz", AssetTree(game))
    base = mod_with(tmp_path, "base", {"data/datafile.big/b.txt": b"B"})
    with pytest.raises(ModError, match="needs base >=2"):
        plan_mods([n, base], "cz", AssetTree(game))            # base is 1.0.0
    t = (base.root / "mod.toml").read_text().replace('"1.0.0"', '"2.1"')
    (base.root / "mod.toml").write_text(t)
    assert len(plan_mods([n, Mod.load(base.root)], "cz", AssetTree(game)).planned) == 2


def test_pack_writes_requirements_and_info(tmp_path, game, capsys):
    m = mod_with(tmp_path, "shared", {"data/datafile.big/a.txt": b"A"})
    z = pack(m.root, tmp_path)
    with zipfile.ZipFile(z) as f:
        j = json.loads(f.read("shared/requirements.json"))
        assert "Plays in" in f.read("shared/REQUIRES.txt").decode()
    assert j["format"] == requires.FORMAT and j["content_hash"] == requires.content_hash(m.root)
    lib = ModLibrary(tmp_path / "lib")
    inst = lib.install(z)                       # the hash ignores the generated files
    assert requires.content_hash(inst.root) == j["content_hash"]
    code = main(["mod", "info", str(m.root), "--library", str(tmp_path / "lib")])
    out = capsys.readouterr().out
    assert code == 1 and "Case West's game data" in out    # plays in both, CW not here

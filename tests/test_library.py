"""The mod manager (`dr2kit.mods.library`): order, switches, install, pack, deploy."""

import zipfile

import pytest

from dr2kit.cli.main import main
from dr2kit.container.vpath import AssetTree
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
    return root


def raw_mod(tmp_path, name, files: dict, priority=0):
    root = create(tmp_path / "src" / name, name)
    if priority:
        t = (root / "mod.toml").read_text().replace("priority = 0", f"priority = {priority}")
        (root / "mod.toml").write_text(t)
    for vp, data in files.items():
        f = root / "replace" / vp
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    return root


def test_install_order_switches(tmp_path, game):
    lib = ModLibrary(tmp_path / "lib")
    a = raw_mod(tmp_path, "a", {"data/datafile.big/a.txt": b"A"})
    b = raw_mod(tmp_path, "b", {"data/datafile.big/a.txt": b"B"})
    lib.install(a)
    lib.install(b)
    assert [e.mod.id for e in lib.entries()] == ["a", "b"]
    assert all(e.enabled for e in lib.entries())
    # b is later, so it wins; the plan names what lost
    plan = lib.plan("cz", AssetTree(game))
    assert [p.mod.id for p in plan.planned] == ["b"]
    assert plan.shadowed == [("data/datafile.big/a.txt", "a", "b")]
    assert lib.move("b", "bottom") == 1
    assert lib.plan("cz", AssetTree(game)).planned[0].mod.id == "a"
    lib.enable("a", False)
    assert [m.id for m in lib.active("cz")] == ["b"]
    with pytest.raises(ModError, match="already installed"):
        lib.install(a)
    lib.install(a, replace=True)                    # keeps its place and switch
    assert [(e.mod.id, e.enabled) for e in lib.entries()] == [("b", True), ("a", False)]
    lib.remove("a")
    assert [e.mod.id for e in lib.entries()] == ["b"]


def test_priority_places_a_new_install(tmp_path):
    lib = ModLibrary(tmp_path / "lib")
    lib.install(raw_mod(tmp_path, "high", {}, priority=10))
    lib.install(raw_mod(tmp_path, "low", {}))
    assert [e.mod.id for e in lib.entries()] == ["low", "high"]


def test_hand_copied_folder_is_new_and_off(tmp_path):
    lib = ModLibrary(tmp_path / "lib")
    create(tmp_path / "lib" / "dropped", "dropped")
    (e,) = lib.entries()
    assert e.new and not e.enabled
    lib.enable("dropped")
    (e,) = lib.entries()
    assert e.enabled and not e.new


def test_pack_and_install_zip(tmp_path):
    src = raw_mod(tmp_path, "zipme", {"data/x.txt": b"x"})
    (src / ".git").mkdir()
    (src / ".git" / "junk").write_text("no")
    z = pack(src, tmp_path)
    assert z.name == "zipme-1.0.0.zip"
    names = zipfile.ZipFile(z).namelist()
    assert "zipme/mod.toml" in names and "zipme/replace/data/x.txt" in names
    assert not any(".git" in n for n in names)
    lib = ModLibrary(tmp_path / "lib")
    mod = lib.install(z)
    assert (mod.root / "replace/data/x.txt").read_bytes() == b"x"


def test_zip_slip_is_refused(tmp_path):
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("mod.toml", '[mod]\nid = "evil"\n')
        f.writestr("../outside.txt", "x")
    with pytest.raises(ModError, match="outside"):
        ModLibrary(tmp_path / "lib").install(z)
    assert not (tmp_path / "outside.txt").exists()


def test_cli_library_deploy(tmp_path, game, capsys):
    lib = str(tmp_path / "lib")
    a = raw_mod(tmp_path, "a", {"data/datafile.big/a.txt": b"A"})
    b = raw_mod(tmp_path, "b", {"data/datafile.big/b.txt": b"B"}, priority=3)
    assert main(["mod", "install", str(a), str(b), "--library", lib]) == 0
    assert main(["mod", "list", "--library", lib]) == 0
    out = capsys.readouterr().out
    assert out.index(" a ") < out.index(" b ")
    assert main(["mod", "disable", "b", "--library", lib]) == 0
    assert main(["mod", "deploy", "-g", "cz", "-q", "--library", lib]) == 0
    deployed = tmp_path / "assets/game_mods/data/datafile.big"
    tree = AssetTree(tmp_path / "assets/game_mods")
    assert tree.resolve("data/datafile.big/a.txt").data() == b"A"
    assert tree.resolve("data/datafile.big/b.txt").data() == b"b"      # b is off
    assert deployed.is_file()
    assert main(["mod", "conflicts", "-g", "cz", "--library", lib]) == 0
    assert main(["mod", "pack", str(a), "-o", str(tmp_path)]) == 0
    assert (tmp_path / "a-1.0.0.zip").is_file()

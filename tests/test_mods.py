"""Mod packages end to end on a synthetic game folder (no real game data)."""

import json

import pytest

from dr2kit.cli.main import main
from dr2kit.container.big import LZX, BigArchive
from dr2kit.container.vpath import AssetTree
from dr2kit.convert import png
from dr2kit.convert.png import Image
from dr2kit.convert.texture import to_image
from dr2kit.formats.bct import Bct
from dr2kit.mods import build as mbuild
from dr2kit.mods import deploy as mdeploy
from dr2kit.mods.manifest import Mod, ModError, create

from conftest import make_archive, make_bct

TEX_VP = "data/models/npcs.big/hero.tex/hero_cm"


@pytest.fixture
def game(tmp_path, monkeypatch):
    """assets/game/data/models/npcs.big, holding a *compressed* hero.tex with a texture,
    laid out like a recomp so deploy targets assets/game_mods."""
    tex_pack = make_archive(("hero_cm", make_bct("DXT1", 32, 32, 3)),
                            ("hero_nm", make_bct("DXN", 16, 16, 1)))
    npcs = make_archive(("hero.big", b"model bytes " * 20, LZX),
                        ("hero.tex", tex_pack.to_bytes(), LZX))
    root = tmp_path / "assets" / "game"
    (root / "data" / "models").mkdir(parents=True)
    (root / "data" / "models" / "npcs.big").write_bytes(npcs.to_bytes())
    (root / "data" / "notes.txt").write_bytes(b"original notes")
    (root / "data" / "datafile.big").write_bytes(make_archive(("a.txt", b"a")).to_bytes())
    monkeypatch.setenv("DR2_CZ_DATA", str(root))
    return root


def red_png(path, w=32, h=32):
    path.parent.mkdir(parents=True, exist_ok=True)
    png.write(path, Image(w, h, bytes((255, 0, 0, 255)) * w * h))


def make_mod(tmp_path, name="red", priority=0):
    root = create(tmp_path / name, name)
    if priority:
        text = (root / "mod.toml").read_text().replace("priority = 0", f"priority = {priority}")
        (root / "mod.toml").write_text(text)
    return root


def test_manifest_template_loads(tmp_path):
    mod = Mod.load(make_mod(tmp_path))
    assert mod.id == "red" and mod.games == ("cz", "cw") and mod.priority == 0


def test_bad_manifest(tmp_path):
    (tmp_path / "m").mkdir()
    (tmp_path / "m" / "mod.toml").write_text('[mod]\nid = "Bad Id"\n')
    with pytest.raises(ModError, match="lower-case"):
        Mod.load(tmp_path / "m")


def test_build_texture_mod_recompresses_and_verifies(game, tmp_path):
    mod = make_mod(tmp_path)
    red_png(mod / "replace" / (TEX_VP + ".png"))
    out = tmp_path / "out"
    res = mbuild.build([Mod.load(mod)], "cz", AssetTree(game), out)
    assert res.files == ["data/models/npcs.big"]
    arc = BigArchive.open(out / "data/models/npcs.big")
    packed = arc.get("hero.tex")
    assert packed.compressed                               # still LZX, as shipped
    assert arc.get("hero.big").stored == BigArchive.open(
        game / "data/models/npcs.big").get("hero.big").stored   # untouched entry kept as is
    tex = Bct.parse(AssetTree(out).resolve(TEX_VP).data())
    assert to_image(tex).rgba[:4] == bytes((255, 0, 0, 255))
    info = json.loads((out / mbuild.BUILD_INFO).read_text())
    assert info["overrides"][0]["vpath"] == TEX_VP


def test_raw_override_of_a_loose_file(game, tmp_path):
    mod = make_mod(tmp_path)
    (mod / "replace" / "data").mkdir(parents=True)
    (mod / "replace" / "data" / "NOTES.TXT").write_bytes(b"new notes")   # case-insensitive
    res = mbuild.build([Mod.load(mod)], "cz", AssetTree(game), tmp_path / "out")
    assert res.files == ["data/notes.txt"]
    assert (tmp_path / "out" / "data" / "notes.txt").read_bytes() == b"new notes"


def test_problems_are_reported_together(game, tmp_path):
    mod = make_mod(tmp_path)
    red_png(mod / "replace" / "data/models/npcs.big/hero.tex/nothing_here.png")
    red_png(mod / "replace" / "data/models/npcs.big/hero.big.png")          # not a texture
    with pytest.raises(ModError) as e:
        mbuild.classify([Mod.load(mod)], "cz", AssetTree(game))
    assert "nothing_here" in str(e.value) and "not a texture" in str(e.value)


def test_wrong_png_size_is_refused(game, tmp_path):
    mod = make_mod(tmp_path)
    red_png(mod / "replace" / (TEX_VP + ".png"), 16, 16)
    with pytest.raises(ModError, match="needs exactly 32x32"):
        mbuild.build([Mod.load(mod)], "cz", AssetTree(game), tmp_path / "out")


def test_conflicts(game, tmp_path):
    a, b = make_mod(tmp_path, "a"), make_mod(tmp_path, "b")
    for m in (a, b):
        red_png(m / "replace" / (TEX_VP + ".png"))
    with pytest.raises(ModError, match="same priority"):
        mbuild.classify([Mod.load(a), Mod.load(b)], "cz", AssetTree(game))
    c = make_mod(tmp_path, "c", priority=5)
    red_png(c / "replace" / (TEX_VP + ".png"))
    plan = mbuild.classify([Mod.load(a), Mod.load(c)], "cz", AssetTree(game))
    assert [p.mod.id for p in plan] == ["c"]
    # Whole archive in one mod, an entry inside it in another: refused.
    d = make_mod(tmp_path, "d", priority=1)
    (d / "replace/data/models/npcs.big").mkdir(parents=True)
    (d / "replace/data/models/npcs.big/hero.tex").write_bytes(b"x")
    with pytest.raises(ModError, match="inside it"):
        mbuild.classify([Mod.load(a), Mod.load(d)], "cz", AssetTree(game))


def test_base_dir_is_patched_instead_of_the_shipped_file(game, tmp_path):
    base = tmp_path / "assets" / "game_patched"
    (base / "data").mkdir(parents=True)
    patched = make_archive(("hero.tex", BigArchive.open(game / "data/models/npcs.big")
                            .get("hero.tex").data(), LZX), ("extra.txt", b"recomp patch"))
    (base / "data" / "models").mkdir()
    (base / "data/models/npcs.big").write_bytes(patched.to_bytes())
    mod = make_mod(tmp_path)
    red_png(mod / "replace" / (TEX_VP + ".png"))
    res = mbuild.build([Mod.load(mod)], "cz", AssetTree(game), tmp_path / "out", [base])
    assert res.base_used == {"data/models/npcs.big": str(base)}
    assert BigArchive.open(tmp_path / "out/data/models/npcs.big").get("extra.txt").data() \
        == b"recomp patch"


def test_deploy_and_undeploy_touch_only_their_files(game, tmp_path):
    mod = make_mod(tmp_path)
    red_png(mod / "replace" / (TEX_VP + ".png"))
    res = mbuild.build([Mod.load(mod)], "cz", AssetTree(game), tmp_path / "out")
    target = mdeploy.recomp_folders(game)["mods"]
    assert target == tmp_path / "assets" / "game_mods"
    (target / "data").mkdir(parents=True)
    (target / "data" / "mine.txt").write_bytes(b"put here by hand")
    assert mdeploy.deploy(res, target) == ["data/models/npcs.big"]
    assert (target / "data/models/npcs.big").is_file()
    assert mdeploy.undeploy(target) == ["data/models/npcs.big"]
    assert not (target / "data/models").exists()
    assert (target / "data" / "mine.txt").read_bytes() == b"put here by hand"


def test_cli_mod_workflow(game, tmp_path, capsys):
    mod = tmp_path / "cli_mod"
    assert main(["mod", "new", str(mod)]) == 0
    red_png(mod / "replace" / (TEX_VP + ".png"))
    assert main(["mod", "check", str(mod), "-g", "cz"]) == 0
    assert "1 override OK" in capsys.readouterr().out
    assert main(["mod", "deploy", str(mod), "-g", "cz", "-q"]) == 0
    out = capsys.readouterr().out
    assert "CZ_NO_MODS=1" in out
    assert (tmp_path / "assets/game_mods/data/models/npcs.big").is_file()
    assert main(["mod", "undeploy", "-g", "cz"]) == 0
    assert not (tmp_path / "assets/game_mods/data/models/npcs.big").exists()


def test_layout_bin_is_repinned_when_a_file_grows(game, tmp_path):
    """Phase 13: layout.bin pins every file's size (152-byte records, BE size at +132);
    a build whose file changed size carries a re-pinned copy, the others are left."""
    def record(name, size):
        return name.encode().ljust(128, b"\0") + b"\x12\x34\x56\x78" + size.to_bytes(4, "big") \
            + bytes(16)
    notes = game / "data" / "notes.txt"
    npcs = game / "data" / "models" / "npcs.big"
    layout = record("data/notes.txt", notes.stat().st_size) + \
        record("data/models/npcs.big", npcs.stat().st_size)
    (game / "layout.bin").write_bytes(layout)
    mod = make_mod(tmp_path)
    (mod / "replace" / "data").mkdir(parents=True)
    (mod / "replace" / "data" / "notes.txt").write_bytes(b"longer notes than before " * 4)
    res = mbuild.build([Mod.load(mod)], "cz", AssetTree(game), tmp_path / "out")
    assert "layout.bin" in res.files
    new = (tmp_path / "out" / "layout.bin").read_bytes()
    assert len(new) == len(layout)
    assert int.from_bytes(new[132:136], "big") == 100                   # re-pinned
    assert new[152:] == layout[152:] and new[128:132] == layout[128:132]   # the rest kept
    same = make_mod(tmp_path, "same")
    (same / "replace" / "data").mkdir(parents=True)
    (same / "replace" / "data" / "notes.txt").write_bytes(b"x" * notes.stat().st_size)
    res = mbuild.build([Mod.load(same)], "cz", AssetTree(game), tmp_path / "out2")
    assert "layout.bin" not in res.files                                 # nothing to pin

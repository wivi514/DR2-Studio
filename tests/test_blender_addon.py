"""The Blender add-on's logic outside Blender (`blender/io_dr2/toolkit.py`, `core.py`).

The add-on's `__init__.py` needs bpy; its buttons call `core`, which only calls dr2kit,
so the same flow runs here on a synthetic game. The scripted run inside Blender is
``tools/blender_addon_gate.py``.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from dr2kit.container.vpath import AssetTree
from dr2kit.convert.gltf import model_to_glb
from dr2kit.formats.scene import Scene
from dr2kit.index.build import build_index
from dr2kit.mods.manifest import Mod

from conftest import make_archive, make_scene

ADDON = Path(__file__).resolve().parents[1] / "blender" / "io_dr2"


def load(name):
    spec = importlib.util.spec_from_file_location(f"io_dr2_{name}", ADDON / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod          # dataclasses look their module up there
    spec.loader.exec_module(mod)
    return mod


def test_toolkit_finds_dr2kit(tmp_path):
    toolkit = load("toolkit")
    repo = Path(__file__).resolve().parents[1]
    assert toolkit.find_package_root(repo) == repo
    assert toolkit.find_package_root(repo / "dr2kit") == repo
    (tmp_path / "python" / "dr2kit").mkdir(parents=True)
    (tmp_path / "python" / "dr2kit" / "__init__.py").write_text("")
    assert toolkit.find_package_root(tmp_path) == (tmp_path / "python").resolve()
    assert toolkit.find_package_root(tmp_path / "nothing") is None
    with pytest.raises(toolkit.ToolkitMissing, match="No dr2kit"):
        toolkit.load(str(tmp_path / "nothing"))
    assert "dr2kit" in toolkit.describe(toolkit.load(""))


@pytest.fixture
def game(tmp_path, monkeypatch):
    root = tmp_path / "game"
    (root / "data").mkdir(parents=True)
    (root / "data" / "pack.big").write_bytes(make_archive(("box.big", make_scene())).to_bytes())
    monkeypatch.setenv("DR2_CZ_DATA", str(root))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return root


def test_core_flow(game, tmp_path, monkeypatch):
    core = load("core")
    with pytest.raises(RuntimeError, match="No asset index"):
        core.search("cz", "box")
    monkeypatch.setattr(core, "index_path", lambda: tmp_path / "i.sqlite")
    build_index("cz", AssetTree(game), tmp_path / "i.sqlite")
    found = core.search("cz", "box")
    assert [(f.vpath, f.kind) for f in found] == [("data/pack.big/box.big", "model")]
    glb, summary, notes = core.export_glb("cz", "data/pack.big/box.big", textures=False)
    assert glb[:4] == b"glTF" and "3 bones" in summary and notes == []
    skel, summary, _ = core.export_glb("cz", "data/pack.big/box.big", skeleton_only=True)
    assert summary == "3 bones"
    ok = core.check("cz", "data/pack.big/box.big", model_to_glb(Scene.parse(make_scene())))
    assert ok.ok and ok.errors == 0
    bad = core.check("cz", "data/pack.big/box.big", b"not a glb")
    assert not bad.ok
    dest = core.write_to_mod(str(tmp_path / "mod"), "cz", "data/pack.big/box.big", glb)
    assert dest.read_bytes() == glb
    assert Mod.load(tmp_path / "mod").games == ("cz",)
    with pytest.raises(RuntimeError, match="not for cw"):
        core.write_to_mod(str(tmp_path / "mod"), "cw", "data/pack.big/box.big", glb)


def test_addon_files_carry_the_gpl_header():
    for f in ADDON.glob("*.py"):
        assert f.read_text().startswith("# SPDX-License-Identifier: GPL-3.0-or-later"), f
    assert "GNU GENERAL PUBLIC LICENSE" in (ADDON / "LICENSE").read_text()
    assert 'license = ["SPDX:GPL-3.0-or-later"]' in (ADDON / "blender_manifest.toml").read_text()

"""The release builder's pure parts (`tools/build_release.py`); the bundle itself is
built and gated by the script (docs/dev/packaging.md)."""

import importlib.util
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location("build_release", ROOT / "tools" / "build_release.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_addon_zip_is_deterministic(tmp_path, monkeypatch):
    br = load()
    monkeypatch.setattr(br, "OUT", tmp_path)
    a = br.build_addon().read_bytes()
    b = br.build_addon().read_bytes()
    assert a == b
    names = zipfile.ZipFile(br.OUT / f"io_dr2-{br.addon_version()}.zip").namelist()
    assert "blender_manifest.toml" in names and "__init__.py" in names and "LICENSE" in names
    assert not any("__pycache__" in n for n in names)


def test_licence_gate_names_and_platform_tag():
    br = load()
    for bad in ("libx264.so.165", "libx265.so.215", "libxvidcore.so.4", "libvvenc.so.1.13",
                "x264-164.dll"):
        assert br.GPL_LIBS.search(bad), bad
    for ok in ("libavcodec.so.62", "libopus.so.0", "Qt6Core.dll"):
        assert not br.GPL_LIBS.search(ok), ok
    osname, arch = br.platform_tag().split("-", 1)
    assert osname in ("linux", "windows", "macos") and arch


def test_icon_is_a_png():
    assert load().make_icon(32)[:8] == b"\x89PNG\r\n\x1a\n"

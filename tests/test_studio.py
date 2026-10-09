"""DR2 Studio smoke test: open the window on a synthetic index, show a texture."""

import os

import pytest

pytest.importorskip("PySide6", reason="DR2 Studio needs PySide6 (pip install -e '.[studio]')")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# The 3D view (QtWebEngine) is exercised by hand and by tools/; here Studio uses its
# no-WebEngine fallback so the test runs the same on every CI machine.
os.environ.setdefault("DR2_STUDIO_NO_3D", "1")

from dr2kit.container.vpath import AssetTree  # noqa: E402
from dr2kit.index import query  # noqa: E402
from dr2kit.index.build import build_index  # noqa: E402

from conftest import make_archive, make_bct, make_scene  # noqa: E402


def test_window_shows_a_texture(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from dr2kit.studio.app import MainWindow
    root = tmp_path / "game"
    (root / "data").mkdir(parents=True)
    pack = make_archive(("hero_cm", make_bct("DXT1", 32, 32, 3)), ("notes.txt", b"hello"),
                        ("box.big", make_scene()))
    (root / "data" / "pack.big").write_bytes(pack.to_bytes())
    monkeypatch.setenv("DR2_CZ_DATA", str(root))
    db = tmp_path / "i.sqlite"
    build_index("cz", AssetTree(root), db)
    app = QApplication.instance() or QApplication([])
    win = MainWindow(db)
    assert win.tree_model.rowCount() == 1                     # the data/ folder
    win.search_box.setText("hero")
    win.search()
    assert win.results.count() == 1
    tex = query.get(win.con, "cz", "data/pack.big/hero_cm")
    win.show_asset(tex["id"])
    assert win.centre.currentWidget() is win.tex_view
    assert win.tex_view.level.maximum() == 2
    win.show_asset(query.get(win.con, "cz", "data/pack.big/notes.txt")["id"])
    assert win.plain_view.toPlainText() == "hello"
    model = query.get(win.con, "cz", "data/pack.big/box.big")
    assert model["kind"] == "model"
    win.show_asset(model["id"])
    assert win.centre.currentWidget() is win.model_view
    assert win.btn_glb.isEnabled() and not win.btn_png.isEnabled()
    assert "3 bones, 1 meshes, 1 draws" in win.details.toPlainText()
    win.close()
    del app


def test_3d_view_serves_only_its_own_files():
    from dr2kit.studio.model_view import MODEL_PATH, resource
    mime, html = resource("/viewer.html", None)
    assert mime == b"text/html" and b"importmap" in html
    assert resource("/vendor/three/build/three.module.js", None)[0] == b"text/javascript"
    assert resource(MODEL_PATH, b"glTF...") == (b"model/gltf-binary", b"glTF...")
    assert resource(MODEL_PATH, None) is None
    assert resource("/../model_view.py", None) is None          # nothing outside web/
    assert resource("/nope.js", None) is None

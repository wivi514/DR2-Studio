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
    assert win.text_view.edit.toPlainText() == "hello"          # text opens in the editor
    model = query.get(win.con, "cz", "data/pack.big/box.big")
    assert model["kind"] == "model"
    win.show_asset(model["id"])
    assert win.centre.currentWidget() is win.model_view
    assert win.btn_glb.isEnabled() and not win.btn_png.isEnabled()
    assert "3 bones, 1 meshes, 1 draws" in win.details.toPlainText()
    # the rig validator: our own export passes and lands in the open mod
    from dr2kit.convert.gltf import model_to_glb
    from dr2kit.formats.scene import Scene
    from dr2kit.mods.manifest import create
    assert win.btn_glb_in.isEnabled()
    glb = tmp_path / "box.glb"
    glb.write_bytes(model_to_glb(Scene.parse(make_scene())))
    assert win.check_glb(str(glb)).ok
    win._set_mod(create(tmp_path / "mod", "boxmod"))
    win.replace_glb(str(glb))
    assert (tmp_path / "mod" / "replace" / "data" / "pack.big" / "box.big.glb").is_file()
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


def test_audio_view_shows_a_sound():
    np = pytest.importorskip("numpy")
    from PySide6.QtWidgets import QApplication
    from dr2kit.convert.audio import Pcm
    from dr2kit.studio.audio_view import AudioViewer, envelope, playback_bytes
    app = QApplication.instance() or QApplication([])
    six = Pcm(6, 48000, (np.ones((480, 6)) * [1000, 2000, 100, 0, 10, 20]).astype("<i2").tobytes())
    data, ch = playback_bytes(six)                       # 5.1 is mixed to stereo to listen
    assert ch == 2 and np.frombuffer(data, "<i2")[:2].tolist() == [1077, 2084]
    env = envelope(Pcm(1, 48000, np.array([0, 16384, -16384, 0], "<i2").tobytes()), 2)
    assert env == [[(0.0, 0.5), (-0.5, 0.0)]]
    v = AudioViewer()
    v.show_sound(six, (0, 240), "test.xma")
    assert "5.1" in v.title.text() and v.loop_box.isChecked()
    v.clear()
    v.deleteLater()
    app.processEvents()


def test_text_strings_and_mod_manager(tmp_path, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from dr2kit.formats import bcs
    from dr2kit.mods.library import ModLibrary
    from dr2kit.mods.manifest import create
    from dr2kit.studio.app import MainWindow
    from dr2kit.studio.mod_manager import ModManager
    from dr2kit.studio.text_view import diff_html
    from test_bcs import EN, LABELS, bank_bytes
    root = tmp_path / "game"
    (root / "data" / "frontend").mkdir(parents=True)
    (root / "data" / "pack.big").write_bytes(
        make_archive(("rules.txt", b"speed = 1\r\nlives = 3\r\n")).to_bytes())
    (root / "data" / "frontend" / "str_en.bcs").write_bytes(bank_bytes(EN, 400))
    (root / "data" / "frontend" / "str_id.bcs").write_bytes(bank_bytes(LABELS, 400))
    monkeypatch.setenv("DR2_CZ_DATA", str(root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    db = tmp_path / "i.sqlite"
    build_index("cz", AssetTree(root), db)
    app = QApplication.instance() or QApplication([])
    win = MainWindow(db)
    # text: read-only without a mod; edited, saved with CRLF kept, diffed, reverted
    txt = query.get(win.con, "cz", "data/pack.big/rules.txt")
    win.show_asset(txt["id"])
    assert win.centre.currentWidget() is win.text_view
    assert win.text_view.edit.isReadOnly()
    mod = create(tmp_path / "mod", "textmod")
    win._set_mod(mod)
    win.show_asset(txt["id"])
    assert not win.text_view.edit.isReadOnly()
    win.text_view.edit.setPlainText("speed = 2\nlives = 3\n")
    win.text_view.save()
    saved = mod / "replace" / "data" / "pack.big" / "rules.txt"
    assert saved.read_bytes() == b"speed = 2\r\nlives = 3\r\n"
    win.text_view.btn_diff.setChecked(True)
    assert "speed = 2" in win.text_view.diff.toPlainText()
    win.text_view.revert()
    assert not saved.exists()
    assert "No changes" in diff_html("a\n", "a\n", "x")
    # strings: edit a cell, the mod gets a .bcs.json
    bank = query.get(win.con, "cz", "data/frontend/str_en.bcs")
    assert bank["kind"] == "strings"
    win.show_asset(bank["id"])
    assert win.centre.currentWidget() is win.strings_view
    view = win.strings_view
    assert view.table.rowCount() == len(EN)
    row = list(EN).index(3)
    view.table.item(row, 2).setText("GO")
    doc = (mod / "replace/data/frontend/str_en.bcs.json").read_text()
    assert '"3": "GO"' in doc
    view.filter.setText("IDS_SKIP")
    assert sum(not view.table.isRowHidden(r) for r in range(view.table.rowCount())) == 1
    # mod manager: install the mod, it shows up switched on
    lib = ModLibrary(tmp_path / "lib")
    lib.install(mod)
    mm = ModManager(win, tmp_path / "lib")
    assert mm.list.count() == 1 and "textmod" in mm.list.item(0).text()
    mm.list.item(0).setCheckState(Qt.Unchecked)
    assert not ModLibrary(tmp_path / "lib").entries()[0].enabled
    mm.close()
    win.close()
    del app

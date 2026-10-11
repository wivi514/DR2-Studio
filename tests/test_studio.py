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
    assert not win.btn_glb.isHidden() and win.btn_png.isHidden()   # only what applies
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
    assert win.wait_for_jobs()
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


def test_3d_view_has_all_its_files_in_git(tmp_path):
    """Every module the page imports exists and is tracked by git (a `.gitignore` rule
    once kept three.js out, so builds from a clone stayed at "loading…")."""
    import shutil
    import subprocess
    from pathlib import Path
    from dr2kit.studio.model_view import WEB_DIR, viewer_files
    found, missing = viewer_files()
    maps, maps_missing = viewer_files(page="maps.html")          # the Maps tab (phase 10)
    assert not missing and not maps_missing
    found = list(dict.fromkeys(found + maps))
    names = {p.relative_to(WEB_DIR).as_posix() for p in found}
    assert {"viewer.js", "maps.js", "levelmaterials.js", "vendor/three/build/three.module.js",
            "vendor/three/build/three.core.js",
            "vendor/three/examples/jsm/loaders/GLTFLoader.js"} <= names
    git = shutil.which("git")
    root = WEB_DIR.parents[2]
    if git is None or not (root / ".git").exists():
        pytest.skip("not a git checkout")
    tracked = subprocess.run([git, "ls-files", "--", *[str(p) for p in found]], cwd=root,
                             capture_output=True, text=True).stdout.split()
    assert len(tracked) == len(found), set(names) - {Path(t).relative_to(
        WEB_DIR.relative_to(root)).as_posix() for t in tracked}
    # and a copy without one of them is reported
    shutil.copytree(WEB_DIR, tmp_path / "web")
    (tmp_path / "web/vendor/three/build/three.core.js").unlink()
    assert viewer_files(tmp_path / "web")[1] == ["vendor/three/build/three.core.js"]


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
    # game folders: cz found through the environment, cw not
    from dr2kit.studio.setup_dialog import GameSetup
    gs = GameSetup(win)
    assert gs.status["cz"].text().startswith("✔") and "environment" in gs.status["cz"].text()
    gs.close()
    assert win.wait_for_jobs()
    win.close()
    del app


def test_library_tab_shows_groups_and_exports(tmp_path, monkeypatch):
    """Studio opens on the Library; a group lists its items with pictures; a model shows
    its rig and textures; Export… writes the folders (phase 8)."""
    from PySide6.QtWidgets import QApplication
    from dr2kit.index import build as ibuild
    from dr2kit.studio.app import MainWindow
    from test_catalog import make_skeleton, variant
    monkeypatch.setattr(ibuild, "MIN_RIG_BONES", 2)
    root = tmp_path / "game"
    (root / "data" / "models").mkdir(parents=True)
    (root / "data" / "skeleton").mkdir()
    npcs = make_archive(("chest_hero.big", make_scene()),
                        ("srv_bob.big", variant(make_scene(), "bob")),
                        ("chest_hero.tex", make_archive(("box_cm", make_bct("DXT1", 32, 32))).to_bytes()))
    (root / "data" / "models" / "npcs.big").write_bytes(npcs.to_bytes())
    (root / "data" / "skeleton" / "herofullbody.big").write_bytes(make_skeleton())
    (root / "data" / "pack.big").write_bytes(make_archive(("notes.txt", b"hi")).to_bytes())
    monkeypatch.setenv("DR2_CZ_DATA", str(root))
    db = tmp_path / "i.sqlite"
    build_index("cz", AssetTree(root), db)
    app = QApplication.instance() or QApplication([])
    win = MainWindow(db)
    assert win.left.tabText(win.left.currentIndex()) == "Library"
    lv = win.library_view
    assert lv.select_group("characters")
    assert {r["name"] for r in lv.model.rows} == {"chest_hero.big", "srv_bob.big"}
    assert "Hero (chest)" in lv.model.data(lv.model.index(0))
    lv.filter.setText("bob")
    assert [r["name"] for r in lv.model.rows] == ["srv_bob.big"]
    lv.filter.setText("")
    assert lv.select_group("characters", "Outfit parts") and lv.model.rowCount() == 1
    lv.items.setCurrentIndex(lv.model.index(0))                # shows the model
    assert win.current["name"] == "chest_hero.big"
    related = [win.relations.item(i).text() for i in range(win.relations.count())]
    assert any(t.startswith("rig: herofullbody.big") for t in related)
    assert any(t.startswith("colour: box_cm") for t in related)
    assert "Library: Models › Characters › Outfit parts" in win.details.toPlainText()
    assert not win.btn_export_all.isHidden()
    win.export_all(str(tmp_path / "one"))
    assert win.wait_for_jobs()
    assert (tmp_path / "one" / "chest_hero" / "textures" / "box_cm.png").is_file()
    assert lv.select_group("rigs")
    lv.export(str(tmp_path / "many"))
    assert win.wait_for_jobs()
    assert (tmp_path / "many" / "cz" / "rigs" / "herofullbody" / "herofullbody.glb").is_file()
    win.close()
    del app


def test_open_in_blender_script(tmp_path):
    """The script Studio starts Blender with: valid Python; imports from a timer in a
    windowed Blender (run straight from --python there, the glTF importer failed and
    left only its Icosphere, 2026-10-10); in Blender (if installed, background) it
    imports the model's armature and meshes into a tagged collection."""
    import json
    import shutil
    import subprocess
    from dr2kit.convert.gltf import model_to_glb
    from dr2kit.formats.scene import Scene
    from dr2kit.studio.edit_tools import BLENDER_SCRIPT
    glb = tmp_path / "box.glb"
    glb.write_bytes(model_to_glb(Scene.parse(make_scene())))
    job = json.dumps({"game": "cz", "vpath": "data/x.big/box.big", "glb": str(glb),
                      "name": "box.big", "mod": ""})
    script = BLENDER_SCRIPT.format(job=job)
    compile(script, "open_in_blender.py", "exec")
    assert "bpy.app.timers.register(run" in script and "ops.wm.read_homefile" not in script
    assert "disable_bone_shape" in script                  # no sphere on every bone
    blender = shutil.which("blender")
    if blender is None:
        pytest.skip("Blender not installed: the script was only compiled")
    (tmp_path / "s.py").write_text(script)
    probe = tmp_path / "probe.py"
    probe.write_text("import bpy, runpy, sys\nrunpy.run_path(sys.argv[-1])\n"
                     "c = bpy.data.collections['box.big']\n"
                     "print('TYPES', sorted(o.type for o in c.objects), c['dr2_vpath'])\n"
                     "print('SPHERES', sum(o.name.startswith('Icosphere') for o in bpy.data.objects))\n")
    env = dict(os.environ, BLENDER_USER_RESOURCES=str(tmp_path / "bl"))
    out = subprocess.run([blender, "-b", "--factory-startup", "--python", str(probe), "--",
                          str(tmp_path / "s.py")], capture_output=True, text=True, timeout=120,
                         env=env).stdout
    assert "TYPES ['ARMATURE', 'MESH'] data/x.big/box.big" in out, out[-2000:]
    assert "SPHERES 0" in out, out[-2000:]


def test_errors_are_shown_and_missing_help_doesnt_block(tmp_path, monkeypatch):
    """Studio on Windows has no console: an unexpected error goes to the log and
    studio-errors.log; missing help files don't stop an asset from showing (a release
    without them showed no model, 2026-10-10)."""
    import sys
    from PySide6.QtWidgets import QApplication
    from dr2kit import help as dhelp
    from dr2kit.studio import app as sapp
    from dr2kit.userdirs import cache_dir
    root = tmp_path / "game"
    (root / "data").mkdir(parents=True)
    (root / "data" / "pack.big").write_bytes(make_archive(("box.big", make_scene())).to_bytes())
    monkeypatch.setenv("DR2_CZ_DATA", str(root))
    db = tmp_path / "i.sqlite"
    build_index("cz", AssetTree(root), db)
    app = QApplication.instance() or QApplication([])
    win = sapp.MainWindow(db)
    old = sys.excepthook
    try:
        sapp.install_error_hook(win)
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())
        assert "RuntimeError: boom" in win.log.toPlainText()
        assert "boom" in (cache_dir() / "studio-errors.log").read_text()
    finally:
        sys.excepthook = old

    def missing(kind, lang="en"):
        raise FileNotFoundError("the help files are missing")
    monkeypatch.setattr(dhelp, "context", missing)
    win.show_asset(query.get(win.con, "cz", "data/pack.big/box.big")["id"])
    assert win.centre.currentWidget() is win.model_view
    assert "help is missing" in win.howto.text()
    assert win.wait_for_jobs()
    win.close()
    del app


def test_variant_panel_edits_a_choice():
    """Phase 9: the Variants panel shows a model's slots and reports the choice."""
    from types import SimpleNamespace

    from PySide6.QtWidgets import QApplication

    from dr2kit.convert import variants as cv
    from dr2kit.studio.variant_panel import VariantPanel
    QApplication.instance() or QApplication([])
    names = ["head1_headShape", "head2_headShape", "chest_shirt1Shape", "chest_shirt2Shape",
             "cap_neckchest1Shape", "head_eyesShape"]
    mv = cv.model_variants(SimpleNamespace(
        meshes=[SimpleNamespace(name=n) for n in names],
        source="data/models/zombies.big/z.big/z_2.big", materials=[]), "cz")
    panel = VariantPanel()
    seen = []
    panel.changed.connect(lambda c, colours: seen.append((c, colours)))
    panel.set_model(mv, mv.default(), [{"id": 7, "detail": "high"}, {"id": 8, "detail": "low"}], 7)
    assert panel.choice() == mv.default()
    panel._slots["head"].setCurrentIndex(panel._slots["head"].findData(2))
    assert seen and seen[-1][0].slots["head"] == 2 and seen[-1][1] is False
    details = []
    panel.detail.connect(details.append)
    panel._detail.setCurrentIndex(1)
    assert details == [8]
    panel.btn_default.click()
    assert seen[-1][0].slots["head"] == 1
    panel.everything.setChecked(True)
    assert seen[-1][0].everything and "6 of 6" in panel.mask.text()


def test_maps_tab_on_a_synthetic_level(tmp_path, monkeypatch):
    """The Maps tab (phase 10): it lists the levels, opens one (zones, markers, Go to),
    builds a zone file when the page asks, and describes what was clicked. Without
    QtWebEngine here: the page's messages are fed in as the page would send them."""
    import json
    from PySide6.QtWidgets import QApplication
    from dr2kit.studio.app import MainWindow
    from test_level import make_datafile, make_level
    root = tmp_path / "game"
    root.mkdir()
    make_datafile(root)
    make_level(root)
    monkeypatch.setenv("DR2_CZ_DATA", str(root))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    db = tmp_path / "i.sqlite"
    build_index("cz", AssetTree(root), db, thumbs=False)
    app = QApplication.instance() or QApplication([])
    win = MainWindow(db)
    mv = win.maps_view
    assert win.maps_list.tree.topLevelItemCount() == 1             # the level "town"
    win.left.setCurrentWidget(win.maps_list)
    assert win.centre.currentWidget() is mv and win.right_panel.isHidden()
    win._map_chosen("town", "")
    assert mv.level == "town" and mv.meta["start"]["name"] == "Start"
    goto = [mv.goto_box.itemText(i) for i in range(mv.goto_box.count())]
    assert "Spawn point: Start" in goto and "Map area: Main Street" not in goto  # no strings
    assert any(t.startswith("Zone: town_z01") for t in goto)
    built = []
    mv._built = lambda req, path, err: built.append((req, path, err))
    for w in mv._workers:                       # let the builders' answers reach us
        w[1].built.disconnect()
        w[1].built.connect(lambda req, path, err: built.append((req, path, err)))
    mv._message("want " + json.dumps({"zone": "town_z01", "part": "pieces",
                                      "detail": "full", "script": "town"}))
    import time
    deadline = time.time() + 30
    while not built and time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
    (req, path, err), = built
    assert err == "" and path.endswith(".glb") and os.path.isfile(path)
    mv._message("pick " + json.dumps({"type": "item", "name": "HotDog3", "item": "HotDog",
                                      "vpath": "data/streamedassets.big/HotDog.big/hotdog.big",
                                      "file": "town.txt", "line": 1}))
    assert "HotDog" in mv.info.toPlainText() and mv.btn_library.isEnabled()
    win.left.setCurrentWidget(win.library_view)
    assert not win.right_panel.isHidden() and win.centre.currentWidget() is not mv
    assert win.wait_for_jobs()
    win.close()

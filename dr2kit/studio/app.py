"""DR2 Studio's main window: browse, search, view, extract, and make a texture mod.

Layout (docs/dev/studio.md has the diagram):

* **Left**, two tabs. *Browse*: the game's folders and archives as a tree, expanded on
  demand from the index (`dr2kit.index.query.children`). *Search*: words matched against
  asset names, filtered by kind; results show texture thumbnails, as a list or a grid.
* **Centre**: a viewer for the selected asset (`viewers.TextureViewer`,
  `model_view.ModelViewer` for models and skeletons, `audio_view.AudioViewer` for sounds,
  `text_view.TextEditor` for text and `.sfx` (edit into the open mod, with a diff),
  `text_view.StringsViewer` for string banks, `video_view.VideoViewer` for Bink movies,
  or `viewers.PlainViewer` (hex) for everything else).
* **Right**: details (sizes, compression, texture facts), relations (the models that use
  a texture, the textures a model names; double-click to jump), and the actions:
  *Extract…*, *Export PNG…*, *Export .glb…* (models and skeletons, for Blender),
  *Replace with PNG…* (copies the PNG into the open mod's ``replace/`` folder under the
  asset's vpath), *Replace with .glb…* (models: runs the rig validator on a ``.glb``
  from Blender, `dr2kit.convert.model_import.plan_import`, shows its report, and copies
  the file into the open mod when it passes; with no mod open it only checks),
  *Export WAV…* and *Replace with audio…* (sounds: copies a WAV/OGG/FLAC/MP3 into the
  open mod as ``<vpath>.<ext>``; the build fits it to the sound, `dr2kit.mods.build`).
  For sounds the relations list the ``.sfx`` and the scene-script events that play them.
  *Export MP4…* for movies.
* **Bottom**: the mod bar (open/new mod folder, its overrides, *Build && deploy*) and a log.
* **Toolbar**: game switcher, *Build / refresh index*, *Mod manager…*
  (`mod_manager.ModManager`: the mod library, load order, conflicts, deploy), *Game
  folders…* (`setup_dialog.GameSetup`: where each game's data is; opened at start when
  no game is found, e.g. the first start of a release).

Long jobs (building the index, building a mod, exporting a model for the 3D view) run
in a `QThread` so the window stays
responsive. Asset bytes come from `AssetTree` (the real files), the tree and search from
the index; Studio holds no format knowledge of its own.
"""

from __future__ import annotations

import os
import shutil
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QIcon, QImage, QPixmap, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QListView, QListWidget, QListWidgetItem,
                               QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
                               QSplitter, QStackedWidget, QTabWidget, QTextBrowser,
                               QTreeView, QVBoxLayout, QWidget)

from .. import __version__
from ..container.vpath import AssetTree
from ..errors import Dr2Error
from ..index import query
from ..index.build import build_index, connect, default_db_path, format_stats
from ..profiles import GAME_IDS, locate
from . import model_view
from .audio_view import AudioViewer
from .text_view import StringsViewer, TextEditor
from .video_view import VideoViewer
from .viewers import PlainViewer, TextureViewer

# The 3D view's URL scheme must be declared before the QApplication exists (Qt's rule);
# importing this module is early enough for `main()` and for the tests.
model_view.register_scheme()

ROLE_ID = Qt.UserRole + 1        # asset id (None for folder nodes)
ROLE_VPATH = Qt.UserRole + 2
ROLE_LOADED = Qt.UserRole + 3
CONTAINER_KINDS = {"archive", "texture-pack", "model", "skeleton", "scene"}
KINDS = ["all kinds", "texture", "model", "skeleton", "texture-pack", "archive", "audio",
         "sfx", "anim", "text", "strings", "shader", "binary", "video", "empty"]
TEXT_KINDS = {"text", "sfx"}


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


class Job(QObject):
    """Runs ``fn(progress)`` in a worker thread; reports text lines and the result."""
    line = Signal(str)
    done = Signal(object, object)       # result, error text (None on success)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            result = self.fn(self.line.emit)
            self.done.emit(result, None)
        except Dr2Error as e:
            self.done.emit(None, str(e))
        except Exception:  # noqa: BLE001 - shown to the user, never swallowed
            self.done.emit(None, traceback.format_exc())


class _Relay(QObject):
    """Calls a job's ``on_done`` in the GUI thread.

    A signal connected to a plain function or lambda runs it in the *emitting* thread
    (the worker), and widgets must only be touched from the GUI thread: the 3D view's
    Chromium aborts when they are. Connecting to a slot of a QObject that lives in the
    GUI thread makes Qt queue the call there."""
    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    @Slot(object, object)
    def deliver(self, result, err):
        self.fn(result, err)


class MainWindow(QMainWindow):
    def __init__(self, db_path: Path | None = None):
        super().__init__()
        self.setWindowTitle(f"DR2 Studio {__version__}")
        self.resize(1500, 900)
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.con = connect(self.db_path)
        self.game = GAME_IDS[0]
        self.trees: dict[str, AssetTree] = {}
        self.current: dict | None = None
        self.mod_dir: Path | None = None
        self._threads: list = []

        # --- toolbar
        tb = self.addToolBar("main")
        tb.setMovable(False)
        self.game_box = QComboBox()
        for g in GAME_IDS:
            self.game_box.addItem({"cz": "Case Zero", "cw": "Case West"}.get(g, g), g)
        tb.addWidget(QLabel(" Game "))
        tb.addWidget(self.game_box)
        act = QAction("Build / refresh index", self)
        act.triggered.connect(self.build_index)
        tb.addAction(act)
        act = QAction("Mod manager…", self)
        act.triggered.connect(self.open_mod_manager)
        tb.addAction(act)
        act = QAction("Game folders…", self)
        act.triggered.connect(self.open_game_setup)
        tb.addAction(act)

        # --- left: browse + search
        self.tree_model = QStandardItemModel()
        self.tree_model.setHorizontalHeaderLabels(["Name", "Kind", "Size"])
        self.tree = QTreeView()
        self.tree.setModel(self.tree_model)
        self.tree.setUniformRowHeights(True)
        self.tree.expanded.connect(self._expand)
        self.tree.selectionModel().currentChanged.connect(
            lambda cur, _prev: self._select_item(self.tree_model.itemFromIndex(cur.siblingAtColumn(0))))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("search names: words, * and ?  (e.g. apron _cm)")
        self.kind_box = QComboBox()
        self.kind_box.addItems(KINDS)
        self.grid_btn = QPushButton("Grid")
        self.grid_btn.setCheckable(True)
        self.results = QListWidget()
        self.results.setIconSize(QSize(48, 48))
        self.results.setUniformItemSizes(True)
        self.results.currentItemChanged.connect(lambda cur, _p: self._select_result(cur))
        self.result_count = QLabel()
        sw = QWidget()
        sl = QVBoxLayout(sw)
        row = QHBoxLayout()
        row.addWidget(self.search_box, 1)
        row.addWidget(self.kind_box)
        row.addWidget(self.grid_btn)
        sl.addLayout(row)
        sl.addWidget(self.results, 1)
        sl.addWidget(self.result_count)
        self.left = QTabWidget()
        self.left.addTab(self.tree, "Browse")
        self.left.addTab(sw, "Search")
        self.search_box.returnPressed.connect(self.search)
        self.kind_box.currentTextChanged.connect(lambda _t: self.search())
        self.grid_btn.toggled.connect(self._grid)

        # --- centre: viewers
        self.tex_view = TextureViewer()
        self.plain_view = PlainViewer()
        self.audio_view = AudioViewer()
        self.text_view = TextEditor()
        self.strings_view = StringsViewer()
        self.video_view = VideoViewer()
        self.model_view = model_view.ModelViewer()
        self.model_view.status.connect(lambda t: self.say(f"3D view: {t}"))
        self.empty = QLabel("Select an asset on the left.\n\nNo index yet? Use “Build / refresh "
                            "index” (about a minute per game).")
        self.empty.setAlignment(Qt.AlignCenter)
        self.centre = QStackedWidget()
        for w in (self.empty, self.tex_view, self.plain_view, self.model_view, self.audio_view,
                  self.text_view, self.strings_view, self.video_view):
            self.centre.addWidget(w)

        # --- right: details, relations, actions
        self.details = QTextBrowser()
        self.relations = QListWidget()
        self.relations.itemDoubleClicked.connect(self._jump)
        self.btn_extract = QPushButton("Extract…")
        self.btn_png = QPushButton("Export PNG…")
        self.btn_glb = QPushButton("Export .glb…")
        self.btn_glb.setToolTip("The model (meshes, skeleton, skin, textures) or skeleton as "
                                "glTF binary, for Blender")
        self.btn_replace = QPushButton("Replace with PNG…")
        self.btn_glb_in = QPushButton("Replace with .glb…")
        self.btn_glb_in.setToolTip("Check a .glb edited in Blender against this model (bones, "
                                   "weights, materials) and add it to the open mod")
        self.btn_glb_in.clicked.connect(self.replace_glb)
        self.btn_wav = QPushButton("Export WAV…")
        self.btn_wav.clicked.connect(self.export_wav)
        self.btn_audio_in = QPushButton("Replace with audio…")
        self.btn_audio_in.setToolTip("Put a WAV/OGG/FLAC/MP3 in the open mod in place of this "
                                     "sound (the recomp plays it instead)")
        self.btn_audio_in.clicked.connect(self.replace_audio)
        self.btn_mp4 = QPushButton("Export MP4…")
        self.btn_mp4.setToolTip("The movie as .mp4 (MPEG-4 video, AAC stereo sound)")
        self.btn_mp4.clicked.connect(self.export_mp4)
        self.btn_extract.clicked.connect(self.extract)
        self.btn_png.clicked.connect(self.export_png)
        self.btn_glb.clicked.connect(self.export_glb)
        self.btn_replace.clicked.connect(self.replace_png)
        rw = QWidget()
        rl = QVBoxLayout(rw)
        rl.addWidget(QLabel("<b>Details</b>"))
        rl.addWidget(self.details, 2)
        rl.addWidget(QLabel("<b>Related</b> (double-click to open)"))
        rl.addWidget(self.relations, 1)
        for b in (self.btn_extract, self.btn_png, self.btn_glb, self.btn_replace,
                  self.btn_glb_in, self.btn_wav, self.btn_audio_in, self.btn_mp4):
            rl.addWidget(b)

        # --- bottom: mod bar + log
        self.mod_label = QLabel("No mod open.")
        self.mod_files = QListWidget()
        self.mod_files.setMaximumHeight(90)
        b_open = QPushButton("Open mod…")
        b_new = QPushButton("New mod…")
        b_deploy = QPushButton("Build && deploy")
        b_undeploy = QPushButton("Undeploy")
        b_open.clicked.connect(self.open_mod)
        b_new.clicked.connect(self.new_mod)
        b_deploy.clicked.connect(self.deploy_mod)
        b_undeploy.clicked.connect(self.undeploy_mod)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        bw = QWidget()
        bl = QVBoxLayout(bw)
        mrow = QHBoxLayout()
        mrow.addWidget(self.mod_label, 1)
        for b in (b_open, b_new, b_deploy, b_undeploy):
            mrow.addWidget(b)
        bl.addLayout(mrow)
        brow = QHBoxLayout()
        brow.addWidget(self.mod_files, 1)
        brow.addWidget(self.log, 2)
        bl.addLayout(brow)

        top = QSplitter(Qt.Horizontal)
        top.addWidget(self.left)
        top.addWidget(self.centre)
        top.addWidget(rw)
        top.setSizes([430, 750, 320])
        main = QSplitter(Qt.Vertical)
        main.addWidget(top)
        main.addWidget(bw)
        main.setSizes([700, 180])
        self.setCentralWidget(main)

        self.game_box.currentIndexChanged.connect(lambda _i: self.set_game(self.game_box.currentData()))
        self._update_buttons()
        self.set_game(self.game)
        from .setup_dialog import game_status
        if not any(game_status(g)[0] for g in GAME_IDS) and \
                not os.environ.get("DR2_STUDIO_NO_SETUP"):
            self.empty.setText("No game data found yet.\n\nUse “Game folders…” in the "
                               "toolbar to point DR2 Studio at Case Zero and Case West.")
            QTimer.singleShot(0, self.open_game_setup)

    # ---- helpers -----------------------------------------------------------------------

    def say(self, text: str) -> None:
        self.log.appendPlainText(text)

    def error(self, text: str) -> None:
        self.say("error: " + text)
        QMessageBox.warning(self, "DR2 Studio", text[:2000])

    def asset_tree(self) -> AssetTree:
        if self.game not in self.trees:
            self.trees[self.game] = AssetTree(locate(self.game).root, cache_size=16)
        return self.trees[self.game]

    def run_job(self, fn, on_done) -> None:
        """Run ``fn(progress)`` in a worker thread; ``on_done(result, error)`` runs in the
        GUI thread afterwards (through `_Relay`)."""
        th = QThread(self)
        job = Job(fn)
        relay = _Relay(on_done)
        job.moveToThread(th)
        th.started.connect(job.run)
        job.line.connect(self.say)                    # a MainWindow slot: queued to the GUI
        job.done.connect(relay.deliver)
        job.done.connect(th.quit)
        entry = (th, job, relay)
        th.finished.connect(lambda: self._threads.remove(entry))
        self._threads.append(entry)
        th.start()

    def _update_buttons(self) -> None:
        a = self.current
        self.btn_extract.setEnabled(a is not None)
        is_tex = bool(a) and a["kind"] == "texture"
        self.btn_png.setEnabled(is_tex)
        self.btn_glb.setEnabled(bool(a) and a["kind"] in ("model", "skeleton"))
        self.btn_replace.setEnabled(is_tex and self.mod_dir is not None)
        self.btn_replace.setToolTip("" if self.mod_dir else "Open or create a mod first")
        self.btn_glb_in.setEnabled(bool(a) and a["kind"] == "model")
        is_audio = bool(a) and a["kind"] == "audio"
        self.btn_wav.setEnabled(is_audio)
        self.btn_mp4.setEnabled(bool(a) and a["kind"] == "video")
        self.btn_audio_in.setEnabled(is_audio and self.mod_dir is not None)
        self.btn_audio_in.setToolTip("" if self.mod_dir else "Open or create a mod first")

    # ---- game, tree ----------------------------------------------------------------------

    def set_game(self, game: str) -> None:
        self.game = game
        self.tree_model.removeRows(0, self.tree_model.rowCount())
        try:
            self.say(f"{game}: data at {locate(game).root}")
        except Dr2Error as e:
            self.say(f"{game}: {e}")
            return
        rows = query.files(self.con, game)
        if not rows:
            self.say(f"{game}: not indexed yet; use “Build / refresh index”.")
            return
        folders: dict[str, QStandardItem] = {}
        root = self.tree_model.invisibleRootItem()

        def folder(path: str) -> QStandardItem:
            if not path:
                return root
            if path not in folders:
                parent_path, _, name = path.rpartition("/")
                it = QStandardItem(name)
                it.setData(None, ROLE_ID)
                it.setData(path, ROLE_VPATH)
                it.setEditable(False)
                folder(parent_path).appendRow([it, QStandardItem("folder"), QStandardItem("")])
                folders[path] = it
            return folders[path]

        for r in rows:
            parent_path = r["vpath"].rpartition("/")[0]
            folder(parent_path).appendRow(self._row(r))
        self.tree.expandToDepth(0)
        self.tree.resizeColumnToContents(0)

    def _row(self, r) -> list[QStandardItem]:
        it = QStandardItem(r["name"])
        it.setEditable(False)
        it.setData(r["id"], ROLE_ID)
        it.setData(r["vpath"], ROLE_VPATH)
        if r["kind"] in CONTAINER_KINDS:
            it.appendRow(QStandardItem("…"))       # placeholder until expanded
            it.setData(False, ROLE_LOADED)
        kind = QStandardItem(r["kind"] + (" (compressed)" if r["compressed"] else ""))
        size = QStandardItem(_human(r["size"]))
        for x in (kind, size):
            x.setEditable(False)
        return [it, kind, size]

    def _expand(self, index) -> None:
        it = self.tree_model.itemFromIndex(index.siblingAtColumn(0))
        if it is None or it.data(ROLE_LOADED) is not False:
            return
        it.removeRows(0, it.rowCount())
        for r in query.children(self.con, it.data(ROLE_ID)):
            it.appendRow(self._row(r))
        it.setData(True, ROLE_LOADED)

    # ---- search ------------------------------------------------------------------------

    def search(self) -> None:
        text = self.search_box.text().strip()
        self.results.clear()
        if not text:
            return
        kind = self.kind_box.currentText()
        rows = query.search(self.con, text, game=self.game,
                            kind=None if kind == "all kinds" else kind, limit=2000)
        for r in rows:
            item = QListWidgetItem(r["vpath"] if not self.grid_btn.isChecked() else r["name"])
            item.setData(ROLE_ID, r["id"])
            item.setToolTip(f"{r['vpath']}\n{r['kind']}, {_human(r['size'])}")
            if r["kind"] == "texture":
                png = query.thumbnail(self.con, r["id"])
                if png:
                    item.setIcon(QIcon(QPixmap.fromImage(QImage.fromData(png))))
            self.results.addItem(item)
        self.result_count.setText(f"{len(rows)} result{'s' if len(rows) != 1 else ''}"
                                  + (" (first 2000)" if len(rows) == 2000 else ""))
        self.left.setCurrentIndex(1)

    def _grid(self, on: bool) -> None:
        self.results.setViewMode(QListView.IconMode if on else QListView.ListMode)
        self.results.setIconSize(QSize(128, 128) if on else QSize(48, 48))
        self.results.setGridSize(QSize(150, 160) if on else QSize())
        self.results.setResizeMode(QListView.Adjust)
        self.results.setWordWrap(on)
        self.search()

    def _select_result(self, item) -> None:
        if item is not None:
            self.show_asset(item.data(ROLE_ID))

    def _select_item(self, item) -> None:
        if item is not None and item.data(ROLE_ID) is not None:
            self.show_asset(item.data(ROLE_ID))

    def _jump(self, item) -> None:
        aid = item.data(ROLE_ID)
        if aid:
            self.show_asset(aid)

    # ---- showing an asset -----------------------------------------------------------------

    def show_asset(self, asset_id: int) -> None:
        row = query.by_id(self.con, asset_id)
        if row is None:
            return
        self.current = dict(row)
        self._update_buttons()
        try:
            data = self.asset_tree().resolve(row["vpath"]).data()
        except Dr2Error as e:
            self.error(f"{row['vpath']}: {e}\n(The index may be out of date: rebuild it.)")
            return
        lines = [f"<b>{row['name']}</b>", f"<small>{row['vpath']}</small>", "",
                 f"kind: {row['kind']}", f"size: {row['size']:,} bytes"]
        if row["depth"]:
            lines.append(f"stored: {row['stored_size']:,} bytes"
                         + (" (LZX-compressed)" if row["compressed"] else ""))
            lines.append(f"index flags: {row['flags']:#x}")
        self.relations.clear()
        if self.centre.currentWidget() is self.audio_view:
            self.audio_view.stop()
        if self.centre.currentWidget() is self.video_view:
            self.video_view.stop()
        if row["kind"] == "audio":
            lines += self._show_sound(row, data)
        elif row["kind"] == "video":
            lines += self._show_movie(row, data)
        elif row["kind"] == "strings":
            lines += self._show_strings(row, data)
        elif row["kind"] in TEXT_KINDS:
            self._show_text(row, data)
            for r in query.sound_targets(self.con, asset_id)[:500]:
                where = r["vpath"] or "not in the game data"
                ctx = f"  [{r['context']}]" if r["rel_kind"] == "script-asset" else ""
                self._relation(f"plays {r['dst_name']}  →  {where}{ctx}", r["id"])
            if row["kind"] == "sfx":
                for r in query.sound_users(self.con, asset_id):
                    label = (f"event: {r['context']}" if r["rel_kind"] == "script-asset"
                             else f"part of {r['name']} ({r['context']})")
                    self._relation(f"{label}  ({r['vpath']})", r["id"])
        elif row["kind"] == "texture":
            from ..formats.bct import Bct
            try:
                tex = Bct.parse(data, row["vpath"])
            except Dr2Error as e:
                self.error(str(e))
                return
            h = tex.header
            lines += [f"texture: {h.width}×{h.height} {tex.format.name} ({tex.format.channels})",
                      f"mip levels: {h.levels}" + ("; cube map, 6 faces" if h.is_cube else ""),
                      f"header flags: {h.flags:#04x}"]
            self.tex_view.show_texture(tex)
            self.centre.setCurrentWidget(self.tex_view)
            for r in query.used_by(self.con, asset_id):
                self._relation(f"used by {r['vpath']}" + ("" if r["rank"] == 0 else "  (elsewhere)"),
                               r["id"])
            for r in query.same_content(self.con, asset_id)[:50]:
                self._relation(f"same bytes: {r['game']} {r['vpath']}", r["id"] if r["game"] == self.game else None)
        elif row["kind"] in ("model", "skeleton"):
            lines += self._show_scene(row, data)
            if row["kind"] == "model":
                for r in query.textures_of(self.con, asset_id):
                    self._relation(f"slot {r['slot']}: {r['dst_name']}  →  {r['vpath'] or 'not found'}",
                                   r["id"])
        else:
            from ..census import content_kind
            self.plain_view.show_bytes(data, content_kind(data) == "text")
            self.centre.setCurrentWidget(self.plain_view)
        dup = query.same_content(self.con, asset_id)
        if dup:
            lines.append(f"identical copies elsewhere: {len(dup)}")
        self.details.setHtml("<br>".join(lines))

    def _show_scene(self, row, data: bytes) -> list[str]:
        """Show a model or skeleton in the 3D view; return its detail lines."""
        from ..formats.scene import Scene
        try:
            sc = Scene.parse(data, row["vpath"])
        except Dr2Error as e:
            self.error(str(e))
            return []
        draws = sum(len(m.draws) for m in sc.meshes)
        verts = sum(d.vertex_count for m in sc.meshes for d in m.draws)
        lines = [f"scene: {len(sc.skeleton)} bones, {len(sc.meshes)} meshes, {draws} draws, "
                 f"{verts:,} vertices, {len(sc.materials)} materials"]
        shaders = sorted({sc.shaders.get(d.shader, f"{d.shader:08X}")
                          for m in sc.meshes for d in m.draws})
        if shaders:
            lines.append("shaders: " + ", ".join(shaders))
        self.centre.setCurrentWidget(self.model_view)
        if not self.model_view.available:
            self.model_view.set_title(row["name"])
            return lines
        self.model_view.set_title(f"{row['name']}: exporting…")
        game, vpath, db = self.game, row["vpath"], self.db_path

        def work(progress):
            from ..convert import gltf
            from ..convert.model import TextureFinder
            tree = AssetTree(locate(game).root)      # the worker's own (not thread-shared)
            if not sc.meshes:
                return gltf.skeleton_to_glb(sc), []
            st = gltf.ExportStats()
            finder = TextureFinder(tree, vpath, game, db)
            glb = gltf.model_to_glb(sc, finder, stats=st, base_colour=finder.baker(sc))
            return glb, st.missing_textures

        def done(result, err):
            if err:
                self.error(err)
                return
            if self.current is None or self.current["vpath"] != vpath:
                return                                  # the user moved on
            glb, missing = result
            self.model_view.show_glb(glb, row["name"])
            for name in missing:
                self.say(f"{row['name']}: texture {name!r} not found")
        self.run_job(work, done)
        return lines

    def _show_sound(self, row, data: bytes) -> list[str]:
        """Decode a sound in the background for the audio view; return its detail lines."""
        from ..convert.audio import AudioLookup, have_decoder
        try:
            info = AudioLookup(self.asset_tree()).info(row["vpath"], data)
        except Dr2Error as e:
            self.error(str(e))
            return []
        layout = {1: "mono", 2: "stereo", 6: "5.1"}.get(info.channels, f"{info.channels} ch")
        lines = [f"sound: XMA2 {layout}, {info.rate} Hz",
                 f"stored as: {'RIFF file' if info.shape == 'riff' else 'raw packets'} "
                 f"({info.source})"]
        if info.loop:
            lines.append(f"loops: samples {info.loop[0]:,}–{info.loop[1]:,}")
        for r in query.sound_users(self.con, row["id"]):
            label = (f"event: {r['context']}" if r["rel_kind"] == "script-asset"
                     else f"played by {r['name']}")
            self._relation(f"{label}  ({r['vpath']})", r["id"])
        self.centre.setCurrentWidget(self.audio_view)
        self.audio_view.clear()
        if not have_decoder():
            self.audio_view.title.setText("Install PyAV to hear sounds: pip install av")
            return lines
        self.audio_view.title.setText(f"{row['name']}: decoding…")
        vpath = row["vpath"]

        def work(progress):
            from ..convert.audio import decode
            return decode(data, info)

        def done(pcm, err):
            if err:
                self.error(err)
                return
            if self.current is None or self.current["vpath"] != vpath:
                return
            self.audio_view.show_sound(pcm, info.loop, row["name"])
        self.run_job(work, done)
        return lines

    def _show_movie(self, row, data: bytes) -> list[str]:
        """Show a Bink movie; its sound is decoded in the background."""
        from ..convert import video
        self.centre.setCurrentWidget(self.video_view)
        self.video_view.clear()
        if not video.have_bink():
            self.video_view.title.setText("Install PyAV to play movies: pip install av")
            return []
        try:
            info = video.probe(data)
        except Dr2Error as e:
            self.error(str(e))
            return []
        vpath = row["vpath"]
        self.video_view.title.setText(f"{row['name']}: decoding the sound…")

        def work(progress):
            return video.audio(data) if info.audio_tracks else None

        def done(pcm, err):
            if err:
                self.error(err)
                return
            if self.current is None or self.current["vpath"] != vpath:
                return
            self.video_view.show_movie(data, info, pcm, row["name"])
        self.run_job(work, done)
        return [f"movie: {info.describe()}",
                "replacing a movie needs a Bink encoder (not available)"]

    # ---- text and strings ------------------------------------------------------------------

    def _locked_reason(self, vpath: str) -> str:
        """Why a mod can't change ``vpath`` ('' if it can)."""
        from ..profiles import load_profile
        low = vpath.lower()
        for d in load_profile(self.game).digest_checked:
            if low == d.lower():
                return (f"The game checks {d} against a digest and crashes on an edited "
                        f"copy, so it can't be modded.")
        return ""

    def _show_text(self, row, data: bytes) -> None:
        vpath = row["vpath"]
        locked = self._locked_reason(vpath)
        mod_file = self.mod_dir / "replace" / vpath if self.mod_dir else None
        current = mod_file.read_bytes() if mod_file and mod_file.is_file() else None
        reason = locked or ("" if self.mod_dir else "Open or create a mod to edit this text.")

        def save(new: bytes) -> None:
            if new == data:
                revert()
                return
            mod_file.parent.mkdir(parents=True, exist_ok=True)
            mod_file.write_bytes(new)
            self.say(f"{self.mod_dir.name}: saved {vpath} (the build re-packs it)")
            self._refresh_mod()
            self.text_view.title.setText(f"<b>{row['name']}</b>  (changed by the open mod)")

        def revert() -> None:
            if mod_file and mod_file.is_file():
                mod_file.unlink()
                self.say(f"{self.mod_dir.name}: {vpath} back to the game's text")
                self._refresh_mod()
            self.text_view.load(vpath, data, None, editable=bool(self.mod_dir) and not locked,
                                reason=reason, save=save, revert=revert)

        self.text_view.load(vpath, data, current, editable=bool(self.mod_dir) and not locked,
                            reason=reason, save=save, revert=revert)
        self.centre.setCurrentWidget(self.text_view)

    def _show_strings(self, row, data: bytes) -> list[str]:
        from ..convert import strings as cstr
        from ..formats import bcs
        try:
            bank = bcs.StringBank.parse(data, row["vpath"])
        except Dr2Error as e:
            self.error(str(e))
            return []
        lang = bcs.bank_name(row["vpath"])[4:]
        labels = cstr.load_labels(self.asset_tree())
        changes = cstr.read_mod_strings(self.mod_dir, lang) if self.mod_dir else {}
        mod_dir = self.mod_dir

        def set_string(i: int, text):
            notes = bcs.apply(bank, {i: text})[1] if text is not None else []
            cstr.set_mod_strings(mod_dir, lang, {i: text}, labels, bank.strings)
            self.say(f"{mod_dir.name}: {lang} string {i} "
                     + ("back to the game's" if text is None else f"→ {text!r}"))
            self._refresh_mod()
            return notes

        self.strings_view.load(row["name"], bank, labels, changes, bool(mod_dir),
                               set_string if mod_dir else None)
        self.centre.setCurrentWidget(self.strings_view)
        return [f"strings: {len(bank.strings):,}", f"language: {lang}"]

    def _relation(self, text: str, asset_id) -> None:
        it = QListWidgetItem(text)
        it.setData(ROLE_ID, asset_id)
        self.relations.addItem(it)

    # ---- actions ---------------------------------------------------------------------------

    def extract(self) -> None:
        a = self.current
        if not a:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Extract asset", a["name"])
        if path:
            Path(path).write_bytes(self.asset_tree().resolve(a["vpath"]).data())
            self.say(f"extracted {a['vpath']} -> {path}")

    def export_png(self) -> None:
        a = self.current
        if not a or a["kind"] != "texture":
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", a["name"] + ".png", "PNG (*.png)")
        if not path:
            return
        from ..convert import png
        from ..convert.texture import png_mode, to_image
        from ..formats.bct import Bct
        tex = Bct.parse(self.asset_tree().resolve(a["vpath"]).data(), a["vpath"])
        img = to_image(tex)
        png.write(path, img, png_mode(tex, img))
        self.say(f"exported {a['vpath']} -> {path} ({img.width}×{img.height})")

    def export_glb(self) -> None:
        a = self.current
        if not a or a["kind"] not in ("model", "skeleton"):
            return
        stem = a["name"].rsplit(".", 1)[0]
        path, _ = QFileDialog.getSaveFileName(self, "Export glTF binary", stem + ".glb",
                                              "glTF binary (*.glb)")
        if not path:
            return
        from ..convert import gltf
        from ..convert.model import TextureFinder
        from ..formats.scene import Scene
        sc = Scene.parse(self.asset_tree().resolve(a["vpath"]).data(), a["vpath"])
        if sc.meshes:
            st = gltf.ExportStats()
            finder = TextureFinder(self.asset_tree(), a["vpath"], self.game, self.db_path)
            data = gltf.model_to_glb(sc, finder, stats=st, base_colour=finder.baker(sc))
            what = f"{st.primitives} draws, {st.textures} textures"
        else:
            data, what = gltf.skeleton_to_glb(sc), f"{len(sc.skeleton)} bones"
        Path(path).write_bytes(data)
        self.say(f"exported {a['vpath']} -> {path} ({what})")

    def replace_png(self) -> None:
        a = self.current
        if not a or not self.mod_dir:
            return
        src, _ = QFileDialog.getOpenFileName(self, f"PNG to replace {a['name']}", "", "PNG (*.png)")
        if not src:
            return
        from ..convert import png
        from ..formats.bct import Bct
        tex = Bct.parse(self.asset_tree().resolve(a["vpath"]).data(), a["vpath"])
        img = png.read(src)
        want = (tex.header.width * tex.header.faces, tex.header.height)
        if (img.width, img.height) != want:
            self.error(f"The PNG is {img.width}×{img.height}; this texture needs exactly "
                       f"{want[0]}×{want[1]}.")
            return
        dest = self.mod_dir / "replace" / (a["vpath"] + ".png")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        self.say(f"{self.mod_dir.name}: {a['vpath']} will be replaced by {Path(src).name}")
        self._refresh_mod()

    def export_mp4(self) -> None:
        a = self.current
        if not a or a["kind"] != "video":
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export MP4", a["name"] + ".mp4",
                                              "MP4 (*.mp4)")
        if not path:
            return
        data = self.asset_tree().resolve(a["vpath"]).data()
        self.say(f"exporting {a['vpath']}…")

        def work(progress):
            from ..convert.video import to_mp4
            return to_mp4(data, path, progress)

        def done(info, err):
            if err:
                self.error(err)
                return
            self.say(f"exported {a['vpath']} -> {path} ({info.seconds:.1f} s)")
        self.run_job(work, done)

    def export_wav(self) -> None:
        a = self.current
        if not a or a["kind"] != "audio":
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export WAV", a["name"] + ".wav",
                                              "WAV (*.wav)")
        if not path:
            return
        from ..convert.audio import decode_vpath, write_wav
        pcm, _ = decode_vpath(self.asset_tree(), a["vpath"])
        write_wav(pcm, path)
        self.say(f"exported {a['vpath']} -> {path} ({pcm.seconds:.2f} s)")

    def replace_audio(self, src: str | None = None) -> None:
        a = self.current
        if not a or a["kind"] != "audio" or not self.mod_dir:
            return
        if not src:
            src, _ = QFileDialog.getOpenFileName(self, f"Audio to play instead of {a['name']}",
                                                 "", "Audio (*.wav *.ogg *.flac *.mp3)")
        if not src:
            return
        from ..mods.manifest import AUDIO_EXTS
        ext = Path(src).suffix.lower()
        if ext not in AUDIO_EXTS:
            self.error(f"{Path(src).name}: use one of {', '.join(AUDIO_EXTS)}")
            return
        dest = self.mod_dir / "replace" / (a["vpath"] + ext)
        dest.parent.mkdir(parents=True, exist_ok=True)
        for other in AUDIO_EXTS:                 # one replacement per sound
            old = dest.with_suffix(other)
            if other != ext and old.is_file():
                old.unlink()
        if Path(src).resolve() != dest.resolve():
            shutil.copyfile(src, dest)
        self.say(f"{self.mod_dir.name}: {a['vpath']} will play {Path(src).name} "
                 f"(the build fits it to the sound's channels, rate and length)")
        self._refresh_mod()

    def check_glb(self, glb_path: str):
        """Run the rig validator on a .glb against the selected model; return the plan."""
        from ..convert.model_import import plan_import
        from ..formats.scene import Scene
        a = self.current
        sc = Scene.parse(self.asset_tree().resolve(a["vpath"]).data(), a["vpath"])
        return plan_import(sc, Path(glb_path).read_bytes(), Path(glb_path).name)

    def replace_glb(self, glb_path: str | None = None) -> None:
        a = self.current
        if not a or a["kind"] != "model":
            return
        if not glb_path:
            glb_path, _ = QFileDialog.getOpenFileName(self, f".glb to put into {a['name']}", "",
                                                      "glTF binary (*.glb)")
        if not glb_path:
            return
        from ..convert.model_import import format_plan
        try:
            plan = self.check_glb(glb_path)
        except Dr2Error as e:
            self.error(str(e))
            return
        report = format_plan(plan)
        self.say(f"check {Path(glb_path).name} → {a['vpath']}:\n{report}")
        if not plan.ok:
            self.error(f"This .glb can't go into {a['name']}:\n\n{report}")
            return
        if not self.mod_dir:
            QMessageBox.information(self, "Model check passed",
                                    f"{report}\n\nOpen or create a mod to add it.")
            return
        dest = self.mod_dir / "replace" / (a["vpath"] + ".glb")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if Path(glb_path).resolve() != dest.resolve():
            shutil.copyfile(glb_path, dest)
        self.say(f"{self.mod_dir.name}: {a['vpath']} will get the meshes of {Path(glb_path).name}")
        self._refresh_mod()

    # ---- mods ---------------------------------------------------------------------------

    def open_mod(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Open mod folder (with mod.toml)")
        if d:
            self._set_mod(Path(d))

    def new_mod(self) -> None:
        from ..mods.manifest import create
        d = QFileDialog.getExistingDirectory(self, "Choose an empty folder for the new mod")
        if not d:
            return
        try:
            create(d)
        except Dr2Error as e:
            self.error(str(e))
            return
        self._set_mod(Path(d))

    def _set_mod(self, folder: Path) -> None:
        from ..mods.manifest import Mod
        try:
            mod = Mod.load(folder)
        except Dr2Error as e:
            self.error(str(e))
            return
        self.mod_dir = folder
        self.mod_label.setText(f"Mod: <b>{mod.name}</b> ({mod.id}) for {', '.join(mod.games)} — {folder}")
        self._refresh_mod()
        self._update_buttons()

    def _refresh_mod(self) -> None:
        from ..mods.manifest import Mod
        self.mod_files.clear()
        if self.mod_dir:
            for rel, _ in Mod.load(self.mod_dir).files():
                self.mod_files.addItem(rel)

    def deploy_mod(self) -> None:
        if not self.mod_dir:
            self.error("Open or create a mod first.")
            return
        from ..mods.manifest import Mod
        try:
            mod = Mod.load(self.mod_dir)
        except Dr2Error as e:
            self.error(str(e))
            return
        self.deploy_mods([mod])

    def deploy_mods(self, mods: list, report=None) -> None:
        """Build ``mods`` for the current game and deploy them to the recomp's
        ``game_mods/`` (on top of ``game_patched``); ``report(line)`` also gets the log."""
        game = self.game
        say = (lambda t: (self.say(t), report(t))) if report else self.say

        def work(progress):
            from ..mods import build as mbuild
            from ..mods import deploy as mdeploy
            import tempfile
            loc = locate(game)
            if not mdeploy.is_recomp_root(loc.root):
                raise Dr2Error(f"{game}'s data is not in a recomp; use `dr2 mod deploy --to`")
            dirs = mdeploy.recomp_folders(loc.root)
            base = [dirs["patched"]] if dirs["patched"].is_dir() else []
            with tempfile.TemporaryDirectory(prefix="dr2mod-") as tmp:
                res = mbuild.build(mods, game, AssetTree(loc.root), tmp, base,
                                   progress=lambda vp: progress(f"built {vp}"))
                written = mdeploy.deploy(res, dirs["mods"])
            lines = [f"{what}: {won} wins over {lost}" for what, lost, won in res.shadowed]
            lines += ["note: " + w for w in res.warnings]
            lines += ["warning: " + w for w in mdeploy.shadowed_layers(loc.root, written)]
            return written, dirs["mods"], lines

        say(f"building {', '.join(m.id for m in mods)} for {game}…")

        def done(result, err):
            if err:
                if report:
                    report("error: " + err)
                self.error(err)
                return
            written, target, lines = result
            for ln in lines:
                say(ln)
            env = "CZ_NO_MODS" if game == "cz" else "CW_NO_MODS"
            say(f"deployed {len(written)} file(s) to {target}. Start the recomp; "
                f"{env}=1 turns mods off.")
        self.run_job(work, done)

    def open_game_setup(self) -> None:
        from .setup_dialog import GameSetup
        GameSetup(self).show()

    def open_mod_manager(self) -> None:
        from .mod_manager import ModManager
        ModManager(self).show()

    def undeploy_mod(self) -> None:
        from ..mods.deploy import recomp_folders, undeploy
        target = recomp_folders(locate(self.game).root)["mods"]
        removed = undeploy(target)
        self.say(f"removed {len(removed)} file(s) from {target}")

    # ---- index --------------------------------------------------------------------------

    def build_index(self) -> None:
        game, db = self.game, self.db_path
        self.say(f"indexing {game} (about a minute; only changed files are re-read)…")

        def work(progress):
            con_tree = AssetTree(locate(game).root)
            return build_index(game, con_tree, db, progress=lambda vp: progress(f"  {vp}"))

        def done(stats, err):
            if err:
                self.error(err)
                return
            self.say(format_stats(stats))
            self.con.close()
            self.con = connect(self.db_path)
            self.set_game(self.game)
        self.run_job(work, done)


def main(argv: list[str] | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1] + list(argv or []))
    app.setApplicationName("DR2 Studio")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

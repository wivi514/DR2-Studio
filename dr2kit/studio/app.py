"""DR2 Studio's main window: browse, search, view, extract, and make a texture mod.

Layout (docs/dev/studio.md has the diagram):

* **Left**, three tabs. *Library* (first, phase 8: `library_view.LibraryView`): the
  assets by what they are (characters, zombies, music, rigs…), as a grid of pictures,
  with *Export…* for a selection or a whole group. *Files*: the game's folders and
  archives as a tree, expanded on demand from the index (`dr2kit.index.query.children`).
  *Search*: words matched against asset names, filtered by kind; results show texture
  thumbnails and model pictures, as a list or a grid.
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
  *Export MP4…* for movies. For a model the relations show its textures with pictures
  (by material and role) and the rig it matches; *Export all…* writes its folder (the
  ``.glb``, every texture as PNG, the rig, ``info.txt``: `dr2kit.catalog.export`).
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
                               QScrollArea, QStackedWidget, QTabWidget,
                               QTextBrowser, QToolButton, QTreeView, QVBoxLayout, QWidget)

from .. import __version__
from ..container.vpath import AssetTree
from ..errors import Dr2Error
from ..index import query
from ..index.build import build_index, connect, default_db_path, format_stats
from ..profiles import GAME_IDS, locate
from . import model_view
from .audio_view import AudioViewer
from .library_view import LibraryView, run_export
from .maps_view import MapsList, MapsView
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


def _swatches(tree, game: str, mv) -> dict:
    """Colour key → the main colour (rgb) of each option, own first, for the Variants
    panel's drop-downs: a value set's ``gBaseTextureColour`` (or first pattern/body
    colour); None when it has none."""
    if mv is None or not mv.colours:
        return {}
    from ..convert import material as cmat
    from ..convert import variants as cvar
    from ..convert.model import read_scene
    shaders = cmat.ShaderLibrary(tree)
    bank = cvar.ColourBank(tree, game)
    sc = read_scene(tree, mv.source)
    out = {}
    for col in mv.colours:
        row = []
        for name in [None] + col.options:
            vs = bank.valueset(name) if name else cmat.material_valueset(
                sc, sc.materials[col.materials[0]])
            rgb = None
            try:
                table = shaders.table(vs.pixel_shader) if vs is not None else None
                values = vs.named(table) if table else {}
            except Dr2Error:
                values = {}
            for k in ("gBaseTextureColour", "gPattern1Colour", "gBodyPart1Colour"):
                if k in values:
                    v = list(values[k]) + [0.0, 0.0, 0.0]
                    rgb = tuple(c ** 0.5 for c in v[:3])     # linear → screen, roughly
                    break
            row.append(rgb)
        out[col.key] = row
    return out


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
        # variants (phase 9): the look chosen per model this session, as choice text
        # (convert/variants.py), used by the 3D view, Export .glb, Export all and Blender
        self.looks: dict[tuple[str, str], str] = {}
        self._variants = None              # the shown model's ModelVariants

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
        act = QAction("▶ Play", self)
        act.setToolTip("Put the switched-on mods into the game and start it")
        act.triggered.connect(lambda: self.play())
        tb.addAction(act)
        act = QAction("Play without mods", self)
        act.triggered.connect(lambda: self.play(mods=False))
        tb.addAction(act)
        # phase 10: see the switched-on mods (Play's) in every view, one click to compare
        self.mods_action = QAction("With my mods", self)
        self.mods_action.setCheckable(True)
        self.mods_action.setShortcut("Ctrl+M")
        self.mods_action.setToolTip("Show every asset, the Library and the Maps with the "
                                    "switched-on mods (what Play puts in the game). "
                                    "Off: the game as shipped. Ctrl+M switches, to compare.")
        self.mods_action.toggled.connect(self._mods_toggled)
        tb.addAction(self.mods_action)
        self.preview = None                # mods.preview.Preview of the switched-on mods
        self._mods_wanted: dict[str, bool] = {}    # per game: the user's choice
        tb.addSeparator()
        act = QAction("Mod manager…", self)
        act.triggered.connect(self.open_mod_manager)
        tb.addAction(act)
        act = QAction("Game folders…", self)
        act.triggered.connect(self.open_game_setup)
        tb.addAction(act)
        act = QAction("Help", self)
        act.setShortcut("F1")
        act.triggered.connect(lambda: self.open_help())
        tb.addAction(act)
        act = QAction("Welcome", self)
        act.setToolTip("The first steps, as a checklist")
        act.triggered.connect(self.open_welcome)
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
        self.library_view = LibraryView(self)
        self.library_view.selected.connect(self.show_asset)
        self.maps_list = MapsList()
        self.left = QTabWidget()
        self.left.addTab(self.library_view, "Library")
        self.left.addTab(self.maps_list, "Maps")
        self.left.addTab(self.tree, "Files")
        self.left.addTab(sw, "Search")
        self.search_tab = sw
        self.left.setTabToolTip(0, "The games' assets by what they are: characters, music, "
                                   "rigs… Export a whole group in one go.")
        self.left.setTabToolTip(1, "The game's levels in 3D: buildings, items, doors, spawn "
                                   "points; fly around, click to see what is what")
        self.left.setTabToolTip(2, "The game's folders and archives as they are stored "
                                   "(for advanced use)")
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
        self.model_view.variants.changed.connect(self._look_changed)
        self.model_view.variants.detail.connect(self._detail_chosen)
        self.maps_view = MapsView(self)
        self.maps_view.status.connect(lambda t: self.statusBar().showMessage(t, 8000))
        self.maps_view.open_asset.connect(self._open_from_map)
        self.maps_list.chosen.connect(self._map_chosen)
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
        self.relations.setIconSize(QSize(40, 40))
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
        self.btn_edit_tex = QPushButton("Edit in image editor…")
        self.btn_edit_tex.setToolTip("Opens the texture in your image editor; each time you "
                                     "save, it goes into the open mod")
        self.btn_edit_tex.clicked.connect(self.edit_texture)
        self.btn_blender = QPushButton("Open in Blender")
        self.btn_blender.setToolTip("Starts Blender with this model, ready for the DR2 tab's "
                                    "Check rig and Export to mod")
        self.btn_blender.clicked.connect(self.open_blender)
        self.btn_tex_in = QPushButton("Import textures…")
        self.btn_tex_in.setToolTip("Textures exported from Substance Painter, Blender or any "
                                   "program: matched to this model's textures, resized, "
                                   "and put in the open mod")
        self.btn_tex_in.clicked.connect(self.import_textures)
        self.btn_mp4 = QPushButton("Export MP4…")
        self.btn_mp4.setToolTip("The movie as .mp4 (MPEG-4 video, AAC stereo sound)")
        self.btn_mp4.clicked.connect(self.export_mp4)
        self.btn_export_all = QPushButton("Export all…")
        self.btn_export_all.setToolTip("A folder with everything: the .glb (textures and bones "
                                       "inside), every texture as PNG, the rig alone, and "
                                       "info.txt — ready for Blender or Substance Painter")
        self.btn_export_all.clicked.connect(self.export_all)
        self.btn_extract.clicked.connect(self.extract)
        self.btn_png.clicked.connect(self.export_png)
        self.btn_glb.clicked.connect(self.export_glb)
        self.btn_replace.clicked.connect(self.replace_png)
        # "How to mod this": the context help for the selected asset's kind.
        self.howto = QLabel()
        self.howto.setWordWrap(True)
        self.howto.setTextFormat(Qt.RichText)
        self.howto.setStyleSheet("QLabel { background: palette(alternate-base); "
                                 "padding: 6px; border-radius: 4px; }")
        self.howto.linkActivated.connect(self._howto_link)   # [text](guide#section) in steps
        self.howto_btn = QPushButton("Open the guide")
        self.howto_btn.clicked.connect(lambda: self.open_help(self._howto_guide))
        self._howto_guide = "README.md"
        rw = QWidget()
        rl = QVBoxLayout(rw)
        rl.addWidget(self.howto)
        rl.addWidget(self.howto_btn)
        rl.addWidget(QLabel("<b>Details</b>"))
        rl.addWidget(self.details, 2)
        rl.addWidget(QLabel("<b>Related</b> (double-click to open)"))
        rl.addWidget(self.relations, 1)
        for b in (self.btn_export_all, self.btn_edit_tex, self.btn_blender, self.btn_tex_in,
                  self.btn_extract,
                  self.btn_png,
                  self.btn_glb, self.btn_replace, self.btn_glb_in, self.btn_wav,
                  self.btn_audio_in, self.btn_mp4):
            rl.addWidget(b)

        # --- bottom: mod bar + log
        self.mod_label = QLabel("No mod open: New mod… to start one.")
        self.mod_label.setWordWrap(True)          # a long folder path never widens the window
        self.mod_label.setMinimumWidth(120)
        self.mod_files = QListWidget()
        self.mod_files.setMaximumHeight(110)
        self.mod_files.setToolTip("The open mod's changes. Double-click to see the asset; "
                                  "select and press Delete to remove a change.")
        self.mod_files.itemDoubleClicked.connect(self._mod_item_jump)
        self.mod_files.installEventFilter(self)
        b_open = QPushButton("Open mod…")
        b_new = QPushButton("New mod…")
        b_share = QPushButton("Share…")
        b_share.setToolTip("Name, preview and readme, a check, then one .dr2mod file to share")
        b_install = QPushButton("Install mod…")
        b_install.setToolTip("Install a .dr2mod (or .zip) someone shared; dropping it on "
                             "this window works too")
        b_deploy = QPushButton("Deploy")
        b_deploy.setToolTip("Put the switched-on mods into the game without starting it")
        b_undeploy = QPushButton("Remove mods from game")
        b_open.clicked.connect(self.open_mod)
        b_new.clicked.connect(self.new_mod)
        b_share.clicked.connect(self.share_mod)
        b_install.clicked.connect(lambda: self.install_mod())
        b_deploy.clicked.connect(lambda: self.play(start=False))
        b_undeploy.clicked.connect(self.undeploy_mod)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        bw = QWidget()
        bl = QVBoxLayout(bw)
        mrow = QHBoxLayout()
        mrow.addWidget(self.mod_label, 1)
        for b in (b_new, b_open, b_share, b_install, b_deploy, b_undeploy):
            mrow.addWidget(b)
        bl.addLayout(mrow)
        brow = QHBoxLayout()
        brow.addWidget(self.mod_files, 1)
        brow.addWidget(self.log, 2)
        bl.addLayout(brow)

        self.right_panel = rw
        self.left.currentChanged.connect(self._left_tab_changed)
        # --- every panel is a dock window: resized, moved, tabbed, or its own window
        from .docks import Layout
        self.panels = P = Layout(self)
        mv = self.maps_view
        P.add("browse", "Browse", self.left,
              tip="The Library, the Maps, the files and the search")
        P.add("viewer", "Viewer", self.centre, mode="assets", stage=True,
              tip="The selected asset: a picture, a model in 3D, a sound, a text…")
        P.add("details", "Details", _scrolled(rw), mode="assets",
              tip="What the selected asset is, what uses it, and what you can do with it")
        P.add("map", "Level (3D)", mv, mode="maps", stage=True, tip="The open level in 3D")
        P.add("map_tools", "Map", _scrolled(mv.tools_panel), mode="maps",
              tip="Layers, time of day, go to, what you clicked, exports")
        P.add("inspector", "Inspector", _scrolled(mv.inspector), mode="maps",
              tip="Edit the selected item, door, zombie or building")
        P.add("hierarchy", "Hierarchy", mv.hierarchy, mode="maps",
              tip="Everything in the open level: click one to fly to it")
        P.add("place", "Place", mv.palette, mode="maps",
              tip="Prefabs, items, zombies and buildings to drag into the level")
        P.add("mod", "Mod and log", bw, tip="The mod you are making, and what Studio did")
        P.arrange()
        P.restore()
        windows = QToolButton()
        windows.setText("Windows")
        windows.setToolTip("Show or hide each panel; put every window back; reset the layout")
        windows.setMenu(P.menu())
        windows.setPopupMode(QToolButton.InstantPopup)
        tb.addWidget(windows)

        self.deploy_status = QLabel()
        self.statusBar().addPermanentWidget(self.deploy_status)
        self.setAcceptDrops(True)
        self.game_box.currentIndexChanged.connect(lambda _i: self.set_game(self.game_box.currentData()))
        self._update_buttons()
        self._show_howto(None)
        self.set_game(self.game)
        from .setup_dialog import game_status
        from .welcome import show_at_start
        if not any(game_status(g)[0] for g in GAME_IDS):
            self.empty.setText("No game data found yet.\n\nUse “Game folders…” in the "
                               "toolbar to point DR2 Studio at Case Zero and Case West.")
        if not os.environ.get("DR2_STUDIO_NO_SETUP") and \
                (show_at_start() or not any(game_status(g)[0] for g in GAME_IDS)):
            QTimer.singleShot(0, self.open_welcome)

    # ---- helpers -----------------------------------------------------------------------

    def say(self, text: str) -> None:
        self.log.appendPlainText(text)

    def error(self, text: str) -> None:
        """Show an error, with a *Help* button that opens the help section about it."""
        self.say("error: " + text)
        if os.environ.get("DR2_STUDIO_NO_DIALOGS"):          # scripted runs and tests
            return
        box = QMessageBox(QMessageBox.Warning, "DR2 Studio", text[:2000], parent=self)
        help_btn = box.addButton("Help", QMessageBox.HelpRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is help_btn:
            self.open_help(*help_for_error(text))

    def open_help(self, page: str = "README.md", section: str = "") -> None:
        """Open the help window at ``page`` (a guide's file name), ``section``."""
        from .help_view import HelpWindow
        if getattr(self, "_help", None) is None:
            self._help = HelpWindow(self)
        self._help.show_page(page, section)

    def _howto_link(self, href: str) -> None:
        page, _, section = href.partition("#")
        self.open_help(page, section)

    def _show_howto(self, kind: str | None) -> None:
        from .. import help as dhelp
        try:
            ctx = dhelp.context(kind) if kind else None
        except OSError as e:            # help files missing: say so, show the asset anyway
            self.howto.setText(f"<b>How to mod this</b><br>The help is missing from this "
                               f"installation ({e}).")
            return
        if ctx is None:
            self.howto.setText("<b>How to mod this</b><br>Select an asset on the left. "
                               "Press F1 for the help.")
            self._howto_guide = "README.md"
        else:
            steps = "".join(f"<li>{_help_links(s)}</li>" for s in ctx.steps)
            self.howto.setText(f"<b>{ctx.title}</b><ol style='margin-left:-20px'>{steps}</ol>")
            self._howto_guide = ctx.guide

    def asset_tree(self) -> AssetTree:
        """The tree every view and export reads (GUI thread): the game with the
        switched-on mods when *With my mods* is on (`mods.preview`), else the game."""
        modded = self.preview is not None and self.mods_action.isChecked()
        key = (self.game, modded)
        if key not in self.trees:
            self.trees[key] = self.preview.tree() if modded else \
                AssetTree(locate(self.game).root, cache_size=16)
        return self.trees[key]

    def plain_tree(self) -> AssetTree:
        """The game as shipped (checks of a mod against the game read this)."""
        key = (self.game, False)
        if key not in self.trees:
            self.trees[key] = AssetTree(locate(self.game).root, cache_size=16)
        return self.trees[key]

    def worker_tree(self) -> AssetTree:
        """A new tree like `asset_tree` for a worker thread (trees aren't shared)."""
        if self.preview is not None and self.mods_action.isChecked():
            return self.preview.tree()
        return AssetTree(locate(self.game).root)

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
        """Show only the actions that apply to the selected asset (fewer buttons to read
        for a newcomer); an action that needs a mod offers to create one."""
        a = self.current
        kind = a["kind"] if a else None
        self.btn_extract.setEnabled(a is not None)
        shown = {
            self.btn_edit_tex: kind == "texture", self.btn_replace: kind == "texture",
            self.btn_png: kind == "texture",
            self.btn_blender: kind in ("model", "skeleton"),
            self.btn_tex_in: kind == "model",
            self.btn_glb_in: kind == "model", self.btn_glb: kind in ("model", "skeleton"),
            self.btn_audio_in: kind == "audio", self.btn_wav: kind == "audio",
            self.btn_mp4: kind == "video",
            self.btn_export_all: kind in ("model", "skeleton"),
        }
        for b, on in shown.items():
            b.setVisible(on)

    def ensure_mod(self) -> bool:
        """True when a mod is open; otherwise offer to create one (New mod…)."""
        if self.mod_dir is None:
            self.new_mod()
        return self.mod_dir is not None

    # ---- game, tree ----------------------------------------------------------------------

    def set_game(self, game: str) -> None:
        self.game = game
        if hasattr(self, "deploy_status"):
            self.update_deploy_status()
        self.tree_model.removeRows(0, self.tree_model.rowCount())
        try:
            self.say(f"{game}: data at {locate(game).root}")
        except Dr2Error as e:
            self.say(f"{game}: {e}")
            return
        self.library_view.set_game(game)
        try:
            self.maps_list.set_levels(self.maps_view.set_game(game, locate(game).root,
                                                              self.db_path))
        except Dr2Error as e:
            self.say(f"{game}: the Maps tab can't list the levels: {e}")
        self.refresh_mods(reshow=False)
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
            if r["kind"] in ("texture", "model"):
                png = query.picture(self.con, r["id"])
                if png:
                    item.setIcon(QIcon(QPixmap.fromImage(QImage.fromData(png))))
            self.results.addItem(item)
        self.result_count.setText(f"{len(rows)} result{'s' if len(rows) != 1 else ''}"
                                  + (" (first 2000)" if len(rows) == 2000 else ""))
        self.left.setCurrentWidget(self.search_tab)

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
        self._show_howto(row["kind"])
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
        if self.preview is not None:
            by = self.preview.changed(row["vpath"])
            if by:
                state = ("shown with" if self.mods_action.isChecked() else
                         "shown without (Ctrl+M shows it)")
                lines.insert(2, f"<b>changed by mod: {', '.join(by)}</b> ({state})")
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
            mine = self.mod_dir / "replace" / (row["vpath"] + ".png") if self.mod_dir else None
            shown_mods = {m.root.resolve() for m in self.preview.mods} \
                if self.preview is not None and self.mods_action.isChecked() else set()
            if mine is not None and mine.is_file() and self.mods_action.isChecked() and \
                    self.mod_dir.resolve() not in shown_mods:
                # Show what the game will get from the open mod (encoded as the build does).
                from ..convert import png
                from ..convert.texture import replace_image
                try:
                    tex = replace_image(tex, png.read(mine))
                    lines.append(f"<b>showing the open mod's version</b> "
                                 f"({self.mod_dir.name})")
                except Dr2Error as e:
                    lines.append(f"the open mod's PNG can't be used: {e}")
            self.tex_view.show_texture(tex)
            self.centre.setCurrentWidget(self.tex_view)
            for r in query.used_by(self.con, asset_id):
                self._relation(f"used by {r['vpath']}" + ("" if r["rank"] == 0 else "  (elsewhere)"),
                               r["id"])
            for r in query.same_content(self.con, asset_id)[:50]:
                self._relation(f"same bytes: {r['game']} {r['vpath']}", r["id"] if r["game"] == self.game else None)
        elif row["kind"] in ("model", "skeleton"):
            lines += self._show_scene(row, data)
            lines += self._scene_relations(row)
        else:
            from ..census import content_kind
            self.plain_view.show_bytes(data, content_kind(data) == "text")
            self.centre.setCurrentWidget(self.plain_view)
        dup = query.same_content(self.con, asset_id)
        if dup:
            lines.append(f"identical copies elsewhere: {len(dup)}")
        item = query.library_item(self.con, asset_id)
        if item is not None:
            from ..catalog.groups import catalog
            g = catalog().group(item["grp"])
            where = f"{g.section} › {g.title}" + (f" › {item['sub']}" if item["sub"] else "")
            lines.insert(1, (f"<b>{item['label']}</b><br>" if item["label"] else "")
                         + f"<small>Library: {where}</small>")
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
        self.model_view.variants.hide()
        self._variants = None
        keep, self._keep_view_once = getattr(self, "_keep_view_once", False), False
        self._load_model(row, sc, keep_view=keep)
        return lines

    def look(self, vpath: str | None = None) -> str | None:
        """The look chosen for a model this session (choice text), or None (default)."""
        a = self.current
        return self.looks.get((self.game, vpath or (a["vpath"] if a else "")))

    def _load_model(self, row, sc, keep_view: bool = False) -> None:
        """Bake the model in its chosen look (in the background) and show it, with the
        Variants panel when it has choices (`convert.variants`)."""
        game, vpath, db = self.game, row["vpath"], self.db_path
        look = self.looks.get((game, vpath))
        levels = [dict(r) for r in query.detail_levels(self.con, row["id"])]
        worker_tree = self.worker_tree

        def work(progress):
            from ..convert import gltf
            from ..convert import variants as cvar
            from ..convert.model import TextureFinder, model_glb
            tree = worker_tree()                     # the worker's own (not thread-shared)
            if not sc.meshes:
                return gltf.skeleton_to_glb(sc), [], None, None, {}
            st = gltf.ExportStats()
            finder = TextureFinder(tree, vpath, game, db)
            mv = cvar.read_variants(tree, sc, game)
            try:
                choice = mv.parse(look)
            except Dr2Error:
                choice = mv.default()                # a look of another detail level
            glb = model_glb(tree, sc, game=game, finder=finder, stats=st, variant=choice,
                            mode="all", colour_variants=False, variants=mv)
            return glb, st.missing_textures, mv, choice, _swatches(tree, game, mv)

        def done(result, err):
            if err:
                self.error(err)
                return
            if self.current is None or self.current["vpath"] != vpath:
                return                                  # the user moved on
            glb, missing, mv, choice, swatches = result
            shown = mv.shown(choice) if mv is not None and mv.has_choices else None
            self.model_view.show_glb(glb, row["name"], keep_view=keep_view, shown=shown)
            self._variants = mv
            if mv is not None and (mv.has_choices or len(levels) > 1):
                self.model_view.variants.set_model(mv, choice, levels, row["id"], swatches)
                self.model_view.variants.show()
            for name in missing:
                self.say(f"{row['name']}: texture {name!r} not found")
        self.run_job(work, done)

    def _look_changed(self, choice, colours_changed: bool) -> None:
        """The Variants panel changed: hide/show parts now; re-bake for a colour."""
        a, mv = self.current, self._variants
        if a is None or mv is None:
            return
        self.looks[(self.game, a["vpath"])] = choice.text()
        if colours_changed:
            from ..convert.model import read_scene
            self.model_view.set_title(f"{a['name']}: baking the colours…")
            self._load_model(a, read_scene(self.asset_tree(), a["vpath"]), keep_view=True)
        else:
            self.model_view.set_shown(mv.shown(choice))

    def _detail_chosen(self, asset_id: int) -> None:
        """Another detail level picked in the Variants panel: show that file, same look."""
        a = self.current
        if a is None or asset_id == a["id"]:
            return
        target = query.by_id(self.con, asset_id)
        if target is not None and (self.game, a["vpath"]) in self.looks:
            self.looks.setdefault((self.game, target["vpath"]),
                                  self.looks[(self.game, a["vpath"])])
        self.show_asset(asset_id)

    def _scene_relations(self, row) -> list[str]:
        """A model's textures (with pictures, by material and role) and rig, or the
        models that use a skeleton, in the Related list; returns detail lines."""
        from ..formats.scene import texture_role
        lines = []
        info = query.scene_info(self.con, row["id"])
        if info is not None and row["kind"] == "model":
            from ..catalog.export import LIMIT_DRAW_BONES, LIMIT_PART_VERTICES
            lines.append(f"largest part: {info['max_part_vertices']:,} vertices "
                         f"(limit {LIMIT_PART_VERTICES:,}); most bones in one draw: "
                         f"{info['max_draw_bones']} (limit {LIMIT_DRAW_BONES})")
        if row["kind"] == "model":
            rigs = query.rigs_of(self.con, row["id"])
            if rigs:
                r = rigs[0]
                how = {0: "same bones and pose", 1: "same bone names, other proportions"}.get(
                    r["rank"], f"+{r['extra']} bones")
                lines.append(f"rig: <b>{r['name']}</b> ({how})")
                self._relation(f"rig: {r['name']}  ({how})", r["id"])
            elif info is not None and info["bones"]:
                lines.append("rig: its own (no skeleton file has the same bones)")
            seen = set()
            for r in query.textures_of(self.con, row["id"]):
                if (r["slot"], r["dst_name"]) in seen:
                    continue                                 # one row per slot, best first
                seen.add((r["slot"], r["dst_name"]))
                it = self._relation(f"{texture_role(r['dst_name'])}: {r['dst_name']}"
                                    + ("" if r["vpath"] else "  (not found)"), r["id"])
                png = query.picture(self.con, r["id"]) if r["id"] else None
                if png:
                    it.setIcon(QIcon(QPixmap.fromImage(QImage.fromData(png))))
                if r["vpath"]:
                    it.setToolTip(r["vpath"])
            bank = query.search(self.con, f"fx_{row['name'].rsplit('.', 1)[0]}", game=self.game,
                                kind="archive", limit=5)
            for b in bank:
                if b["name"].lower() == f"fx_{row['name'].lower()}":
                    self._relation(f"sounds (same name): {b['name']}", b["id"])
        else:
            users = query.rig_users(self.con, row["id"])
            if users:
                lines.append(f"models on this rig: {len(users)}")
            for r in users[:300]:
                self._relation(f"used by {r['name']}"
                               + ("" if r["rank"] == 0 else "  (other proportions)"), r["id"])
        for c in query.copies(self.con, row["id"])[:20]:
            self._relation(f"also in: {c['vpath']}", c["id"])
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

    def _relation(self, text: str, asset_id) -> QListWidgetItem:
        it = QListWidgetItem(text)
        it.setData(ROLE_ID, asset_id)
        self.relations.addItem(it)
        return it

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
        from ..convert.model import TextureFinder, model_glb
        from ..formats.scene import Scene
        sc = Scene.parse(self.asset_tree().resolve(a["vpath"]).data(), a["vpath"])
        if sc.meshes:
            st = gltf.ExportStats()
            finder = TextureFinder(self.asset_tree(), a["vpath"], self.game, self.db_path)
            # variants: the look shown in the 3D view, only its parts (Export all… and
            # Open in Blender give every part, sorted into groups)
            data = model_glb(self.asset_tree(), sc, game=self.game, finder=finder, stats=st,
                             variant=self._look_choice(), mode="shown")
            what = f"{st.primitives} draws, {st.textures} textures"
            if self._variants is not None and self._variants.has_choices:
                what += "; the look shown, only its parts (Export all… has every part)"
        else:
            data, what = gltf.skeleton_to_glb(sc), f"{len(sc.skeleton)} bones"
        Path(path).write_bytes(data)
        self.say(f"exported {a['vpath']} -> {path} ({what})")

    def export_all(self, folder: str | None = None) -> None:
        """*Export all…*: the selected model's (or skeleton's) folder, with everything."""
        a = self.current
        if not a or a["kind"] not in ("model", "skeleton"):
            return
        if folder is None:
            folder = QFileDialog.getExistingDirectory(
                self, f"Export {a['name']} with everything into… (a folder named after it "
                      f"is made in it)")
        if folder:
            self.export_rows([a], Path(folder), by_group=False, variant=self.look())

    def export_rows(self, rows: list, out: Path, *, by_group: bool, on_done=None,
                    variant: str | None = None) -> None:
        """Export assets of this game in the background, with a progress bar and Cancel
        (`library_view.run_export`); ``variant``: the look (choice text) of a model."""
        run_export(self, rows, out, by_group=by_group, on_done=on_done, variant=variant)

    def _look_choice(self):
        """The current model's chosen look as a `Choice` (the panel's), or None."""
        mv = self._variants
        if mv is None or not mv.has_choices:
            return None
        try:
            return mv.parse(self.look())
        except Dr2Error:
            return None

    def replace_png(self, src: str | None = None, vpath: str | None = None,
                    quiet: bool = False) -> bool:
        """Put a PNG into the open mod in place of the selected texture (or ``vpath``).
        Returns True when it went in."""
        a = self.current
        vpath = vpath or (a["vpath"] if a else None)
        if not vpath or not self.ensure_mod():
            return False
        if not src:
            src, _ = QFileDialog.getOpenFileName(self, f"PNG to replace {vpath.rsplit('/', 1)[-1]}",
                                                 "", "PNG (*.png)")
        if not src:
            return False
        from ..convert import png
        from ..formats.bct import Bct
        tex = Bct.parse(self.asset_tree().resolve(vpath).data(), vpath)
        try:
            img = png.read(src)
        except Dr2Error as e:
            self.error(str(e))
            return False
        want = (tex.header.width * tex.header.faces, tex.header.height)
        if (img.width, img.height) != want:
            self.error(f"The picture is {img.width}×{img.height}; this texture needs exactly "
                       f"{want[0]}×{want[1]} (resize it in your editor).")
            return False
        dest = self.mod_dir / "replace" / (vpath + ".png")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if Path(src).resolve() != dest.resolve():
            shutil.copyfile(src, dest)
        self.say(f"{self.mod_dir.name}: {vpath} ← {Path(src).name}")
        self._refresh_mod()
        return True

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
        if not a or a["kind"] != "audio" or not self.ensure_mod():
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
    # The open mod is the one new changes go into. It is always in the mod library
    # (created there, or linked when it lives elsewhere), so Play includes it.

    def library(self):
        from ..mods.library import ModLibrary
        return ModLibrary()

    def open_mod(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Open mod folder (with mod.toml)")
        if d:
            self._set_mod(Path(d))

    def new_mod(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New mod", "Name of your mod (you can change "
                                        "it later):", text="My mod")
        if not ok or not name.strip():
            return
        try:
            mod = self.library().create(name)
        except Dr2Error as e:
            self.error(str(e))
            return
        self.say(f"new mod {mod.name} in {mod.root} (switched on in the mod library)")
        self._set_mod(mod.root)

    def _set_mod(self, folder: Path) -> None:
        from ..mods.manifest import Mod
        try:
            mod = Mod.load(folder)
            lib = self.library()
            if not any(e.mod.root.resolve() == mod.root.resolve() for e in lib.entries()):
                lib.link(folder)
                self.say(f"{mod.id}: added to the mod library (linked: it stays in {folder})")
        except Dr2Error as e:
            self.error(str(e))
            return
        self.mod_dir = Path(folder)
        self.mod_label.setText(f"Mod: <b>{mod.name}</b> ({mod.id}) for "
                               f"{', '.join(mod.games)} — {folder}")
        self._refresh_mod()
        self._update_buttons()
        self.maps_view._refresh_edit_panel()

    def _refresh_mod(self) -> None:
        """The open mod's changes, one row each: what kind, which asset, and whether the
        build accepts it for the current game (checked in the background)."""
        from ..mods.build import _kind_of
        from ..mods.manifest import Mod
        self.mod_files.clear()
        if not self.mod_dir:
            return
        try:
            mod = Mod.load(self.mod_dir)
        except Dr2Error as e:
            self.mod_files.addItem(str(e))
            return
        labels = {"texture-png": "texture", "model-glb": "model", "audio": "sound",
                  "strings": "strings", "edits": "level", "pieces": "buildings",
                  "raw": "file"}
        for rel, _src in mod.files():
            kind, target = _kind_of(rel)
            it = QListWidgetItem(f"{labels.get(kind, kind):<8}  {target}")
            it.setData(ROLE_VPATH, target)
            it.setData(Qt.UserRole + 4, rel)
            self.mod_files.addItem(it)
        for rel, _src in mod.added():
            it = QListWidgetItem(f"{'new':<8}  {rel}")
            it.setData(ROLE_VPATH, rel)
            self.mod_files.addItem(it)
        if not mod.files() and not mod.added():
            self.mod_files.addItem("(no changes yet: pick an asset and use the buttons on "
                                   "the right, or drop a file on this window)")
            return
        game, folder = self.game, self.mod_dir
        if game not in mod.games:
            return

        def work(progress):
            from ..mods.build import plan_mods
            try:
                plan_mods([Mod.load(folder)], game, self.plain_tree())
                return []
            except Dr2Error as e:
                return str(e).splitlines()[1:]

        def done(problems, err):
            if err or self.mod_dir != folder:
                return
            for i in range(self.mod_files.count()):
                it = self.mod_files.item(i)
                rel = it.data(Qt.UserRole + 4)
                bad = [p.strip() for p in problems if rel and rel.lower() in p.lower()]
                if bad:
                    it.setText("⚠ " + it.text())
                    it.setToolTip("\n".join(bad))
            if problems:
                self.say(f"{folder.name}: problems for {game}:\n  " + "\n  ".join(problems))
        self.run_job(work, done)

    def _mod_item_jump(self, item) -> None:
        vpath = item.data(ROLE_VPATH)
        row = query.get(self.con, self.game, vpath) if vpath else None
        if row is not None:
            self.show_asset(row["id"])

    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent
        if obj is self.mod_files and ev.type() == QEvent.KeyPress and \
                ev.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.remove_mod_item()
            return True
        return super().eventFilter(obj, ev)

    def remove_mod_item(self) -> None:
        """Take the selected change out of the open mod (the file goes, after asking)."""
        it = self.mod_files.currentItem()
        rel = it.data(Qt.UserRole + 4) if it else None
        if not rel or not self.mod_dir:
            return
        if QMessageBox.question(self, "Remove change",
                                f"Remove this change from the mod?\n{rel}") != QMessageBox.Yes:
            return
        f = self.mod_dir / "replace" / rel
        f.unlink(missing_ok=True)
        d = f.parent
        while d != self.mod_dir / "replace" and d.is_dir() and not any(d.iterdir()):
            d.rmdir()
            d = d.parent
        self.say(f"{self.mod_dir.name}: removed {rel}")
        self._refresh_mod()

    def share_mod(self) -> None:
        if not self.mod_dir:
            self.error("Open or create a mod first (New mod… / Open mod…).")
            return
        from .share_dialog import ShareDialog
        ShareDialog(self, self.mod_dir).exec()
        self._set_mod(self.mod_dir)

    def install_mod(self, path: str | None = None) -> None:
        """Install a shared mod (a .dr2mod, .zip or folder) into the library."""
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Mod to install", "",
                                                  "DR2 mods (*.dr2mod *.zip)")
        if not path:
            return
        from .share_dialog import InstallDialog
        InstallDialog(self, Path(path)).exec()

    def play(self, mods: bool = True, start: bool = True) -> None:
        """Deploy the switched-on mods (or, with ``mods=False``, nothing) and start the
        recomp: Studio's Play button (`dr2kit.mods.play`)."""
        from ..mods import play as mplay
        game = self.game
        try:
            exe = mplay.find_recomp(game) if start else None
        except Dr2Error as e:
            self.error(str(e))
            return
        if not mods:
            mplay.launch(game, mods=False)
            self.say(f"started {exe} with mods off")
            return

        def work(progress):
            files, res = mplay.deploy_library(game, progress=lambda vp: progress(f"built {vp}"))
            lines = [] if res is None else (
                [f"{w}: {b} wins over {a}" for w, a, b in res.shadowed]
                + ["note: " + n for n in res.warnings])
            return files, lines

        def done(result, err):
            if err:
                self.error(err)
                return
            files, lines = result
            for ln in lines:
                self.say(ln)
            self.update_deploy_status()
            if start:
                mplay.launch(game)
                self.say(f"started {exe}")
        self.say(f"{'deploying' if not start else 'Play'}: building the switched-on mods "
                 f"for {game}…")
        self.run_job(work, done)

    def update_deploy_status(self) -> None:
        from ..mods.play import deployed
        try:
            self.deploy_status.setText(f"{self.game}: {deployed(self.game).describe()}")
        except Dr2Error as e:
            self.deploy_status.setText(f"{self.game}: {str(e)[:80]}")

    def undeploy_mod(self) -> None:
        from ..mods.play import undeploy_all
        try:
            removed = undeploy_all(self.game)
        except Dr2Error as e:
            self.error(str(e))
            return
        self.say(f"removed {len(removed)} file(s) from the game: {self.game} runs as shipped")
        self.update_deploy_status()

    # ---- editing with other programs ---------------------------------------------------

    def edit_texture(self) -> None:
        a = self.current
        if not a or a["kind"] != "texture":
            return
        if not self.ensure_mod():
            return
        from ..convert import png
        from ..convert.texture import png_mode, to_image
        from ..formats.bct import Bct
        from .edit_tools import TextureEdit
        existing = self.mod_dir / "replace" / (a["vpath"] + ".png")
        if existing.is_file():
            data = existing.read_bytes()
        else:
            tex = Bct.parse(self.asset_tree().resolve(a["vpath"]).data(), a["vpath"])
            img = to_image(tex)
            data = png.encode(img, png_mode(tex, img))
        if getattr(self, "_tex_edit", None) is None:
            self._tex_edit = TextureEdit(self)
            self._tex_edit.saved.connect(self._texture_saved)
        self._tex_edit_target = (self.game, a["vpath"], a["id"])
        try:
            path = self._tex_edit.start(self.game, a["vpath"], data)
        except Dr2Error as e:
            self.error(str(e))
            return
        self.say(f"editing {a['name']} in your image editor ({path}). Every save goes "
                 f"into {self.mod_dir.name}.")

    def _texture_saved(self, path: str) -> None:
        game, vpath, aid = self._tex_edit_target
        if game != self.game or not self.mod_dir:
            return
        if self.replace_png(path, vpath=vpath, quiet=True) and self.current and \
                self.current["id"] == aid:
            self.show_asset(aid)

    def open_blender(self) -> None:
        a = self.current
        if not a or a["kind"] not in ("model", "skeleton"):
            return
        game, vpath, mod_dir = self.game, a["vpath"], self.mod_dir
        look = self._look_choice()
        mod_glb = mod_dir / "replace" / (vpath + ".glb") if mod_dir else None
        self.say(f"exporting {a['name']} for Blender…")

        def work(progress):
            if mod_glb and mod_glb.is_file():
                return mod_glb.read_bytes()
            from ..convert.model import export_glb, export_skeleton_glb
            tree = self.asset_tree()
            return export_glb(tree, vpath, game=game, variant=look) if a["kind"] == "model" \
                else export_skeleton_glb(tree, vpath)

        def done(glb, err):
            if err:
                self.error(err)
                return
            from .edit_tools import open_in_blender
            try:
                open_in_blender(game, vpath, glb, mod_dir)
            except Dr2Error as e:
                self.error(str(e))
                return
            self.say("Blender is starting with the model. In its DR2 tab (N key → DR2): "
                     "Check rig, then Export to mod" + ("" if mod_dir else " (choose a mod "
                                                         "folder there)") + ". "
                     "Textures: Z → Material Preview. Hide the bones: Viewport Overlays "
                     "(top right of the 3D view) → untick Bones. Help: F1 → Set up Blender.")
        self.run_job(work, done)

    def import_textures(self, sources: list[str] | None = None) -> None:
        """Textures from Substance Painter / Blender / any program → this model's
        textures in the open mod (`dr2kit.mods.texture_import`)."""
        a = self.current
        if not a or a["kind"] != "model" or not self.ensure_mod():
            return
        if not sources:
            d = QFileDialog.getExistingDirectory(self, "Folder with the exported textures "
                                                       "(or cancel to pick files)")
            if d:
                sources = [d]
            else:
                files, _ = QFileDialog.getOpenFileNames(
                    self, "Exported textures, or a .glb", "",
                    "Pictures or .glb (*.png *.jpg *.jpeg *.tga *.tif *.tiff *.glb)")
                sources = files
        if not sources:
            return
        from ..mods import texture_import as ti
        game, vpath, mod_dir = self.game, a["vpath"], self.mod_dir
        self.say(f"matching {len(sources)} source(s) to {a['name']}'s textures…")

        def work(progress):
            return ti.plan(self.plain_tree(), vpath, sources, game)

        def done(tp, err):
            if err:
                self.error(err)
                return
            report = tp.report()
            self.say(report)
            if not tp.items:
                self.error("No exported picture matched this model's textures. Name them "
                           "<texture set>_BaseColor / _Normal / _Specular, or like the game "
                           "texture (help: Texturing tools).")
                return
            if not os.environ.get("DR2_STUDIO_NO_DIALOGS") and QMessageBox.question(
                    self, "Import textures", report + "\n\nPut these into the mod?") \
                    != QMessageBox.Yes:
                return
            written = ti.apply(tp, mod_dir)
            self.say(f"{mod_dir.name}: {len(written)} texture(s) imported")
            self._refresh_mod()
        self.run_job(work, done)

    # ---- drag and drop -------------------------------------------------------------------

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        for url in ev.mimeData().urls():
            self.drop_file(Path(url.toLocalFile()))

    def drop_file(self, path: Path) -> None:
        """What dropping a file on Studio does: a mod package installs; a PNG / audio /
        .glb replaces the selected asset in the open mod."""
        from ..mods.manifest import AUDIO_EXTS, MANIFEST
        ext = path.suffix.lower()
        if ext in (".dr2mod", ".zip") or (path.is_dir() and (path / MANIFEST).is_file()):
            self.install_mod(str(path))
            return
        a = self.current
        if a is None:
            self.error(f"Select the asset that {path.name} should replace first.")
            return
        if not self.ensure_mod():
            return
        if ext == ".png" and a["kind"] == "texture":
            if self.replace_png(str(path)):
                self.show_asset(a["id"])
        elif ext in AUDIO_EXTS and a["kind"] == "audio":
            self.replace_audio(str(path))
        elif ext == ".glb" and a["kind"] == "model":
            self.replace_glb(str(path))
        elif (ext in (".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff") or path.is_dir()) \
                and a["kind"] == "model":
            self.import_textures([str(path)])           # Painter / Blender exports
        else:
            self.error(f"{path.name} can't replace {a['name']} (a {a['kind']}). Drop a PNG "
                       f"on a texture, a WAV/OGG/FLAC/MP3 on a sound, a .glb on a model, "
                       f"or a .dr2mod anywhere.")

    def wait_for_jobs(self, timeout: float = 30.0) -> bool:
        """Let background jobs finish (closing, tests). A job's thread quits through a
        queued signal, so the event loop keeps turning while waiting (a plain wait()
        would deadlock). Returns True when none is left."""
        import time
        deadline = time.monotonic() + timeout
        while self._threads and time.monotonic() < deadline:
            QApplication.processEvents()
            for th, _job, _relay in list(self._threads):
                th.wait(20)
        QApplication.processEvents()
        return not self._threads

    def showEvent(self, ev):  # noqa: N802 - Qt's name
        super().showEvent(ev)
        if self.panels.sizes_pending:                 # the default layout's sizes
            QTimer.singleShot(0, self.panels.fit)

    def closeEvent(self, ev):
        self.panels.save()
        self.wait_for_jobs()
        self.maps_view.shutdown()
        super().closeEvent(ev)

    # ---- seeing the mods (phase 10) -------------------------------------------------------

    def refresh_mods(self, reshow: bool = True) -> None:
        """Plan the switched-on mods again (the mod library changed, a mod's file was
        saved, another game) and show everything with or without them."""
        from ..mods.preview import Preview
        try:
            self.preview = Preview.for_play(self.game)
        except Dr2Error as e:
            self.preview = None
            self.say(f"{self.game}: the mods can't be shown: {e}")
        for p in (self.preview.problems if self.preview else []):
            self.say(f"not shown (it fails its check): {p}")
        has = self.preview is not None and self.preview.active
        want = self._mods_wanted.get(self.game, True)
        self.mods_action.blockSignals(True)
        self.mods_action.setChecked(has and want)
        self.mods_action.setEnabled(has)
        self.mods_action.blockSignals(False)
        self._mods_label()
        self.trees = {}
        self._watch_mods()
        self.maps_view.use_tree(self._maps_tree)
        self.library_view.items.viewport().update()          # the ✎ marks
        if reshow:
            self._reshow()

    def _maps_tree(self, root):
        if self.preview is not None and self.mods_action.isChecked():
            return self.preview.tree(24)
        return AssetTree(root, cache_size=24)

    def _mods_label(self) -> None:
        n = len(self.preview.mods) if self.preview else 0
        if not self.mods_action.isEnabled():
            self.mods_action.setText("With my mods (none on)")
        elif self.mods_action.isChecked():
            self.mods_action.setText(f"With my mods ({n}) ✓")
        else:
            self.mods_action.setText("Without mods (Ctrl+M: with)")

    def _mods_toggled(self, on: bool) -> None:
        self._mods_wanted[self.game] = on
        self._mods_label()
        self.trees = {}
        self.maps_view.use_tree(self._maps_tree)
        self.say("showing the game " + ("with the switched-on mods" if on else
                                        "without mods (as shipped)"))
        self._reshow()

    def _reshow(self) -> None:
        """Show the current asset again (the 3D view keeps its camera: a compare)."""
        if self.current is not None:
            self._keep_view_once = True
            self.show_asset(self.current["id"])

    def _watch_mods(self) -> None:
        """Watch the shown mods' files: a saved PNG or Blender export redraws (after
        a second of quiet, so a program writing a file in steps is seen once)."""
        from PySide6.QtCore import QFileSystemWatcher
        if getattr(self, "_watcher", None) is None:
            self._watcher = QFileSystemWatcher(self)
            self._watch_timer = QTimer(self)
            self._watch_timer.setSingleShot(True)
            self._watch_timer.setInterval(1000)
            self._watch_timer.timeout.connect(lambda: self.refresh_mods())
            self._watcher.fileChanged.connect(lambda _p: self._watch_timer.start())
            self._watcher.directoryChanged.connect(lambda _p: self._watch_timer.start())
        old = self._watcher.files() + self._watcher.directories()
        if old:
            self._watcher.removePaths(old)
        paths = []
        from ..mods.library import ModLibrary
        try:
            lib = ModLibrary()
            mods = [e.mod for e in lib.entries() if self.game in e.mod.games]
            paths += [str(lib.folder), str(lib.folder / "modlist.toml")]
        except Dr2Error:
            mods = []
        for m in mods:
            for d in [m.root] + [p for p in m.root.rglob("*") if p.is_dir()]:
                paths.append(str(d))
            paths += [str(p) for p in (m.root / "replace").rglob("*") if p.is_file()]
            paths.append(str(m.root / "mod.toml"))
        paths = [p for p in paths if Path(p).exists()][:4000]
        if paths:
            self._watcher.addPaths(paths)

    # ---- the Maps tab (phase 10) ---------------------------------------------------------

    def _left_tab_changed(self, index: int) -> None:
        """The Maps tab shows the Maps panels (the level in 3D, Map, Inspector, Hierarchy,
        Place); the other tabs the viewer and its details (`docks.Layout.mode`)."""
        self.panels.mode(self.left.widget(index) is self.maps_list)

    def _map_chosen(self, level: str, zone: str) -> None:
        self.panels.show_panel("map")
        if self.maps_view.level == level and zone:
            self.maps_view.go_to_zone(zone)
        else:
            self.say(f"Maps: opening {level}" + (f", zone {zone}" if zone else ""))
            self.maps_view.open_level(level, zone)

    def _open_from_map(self, vpath: str) -> None:
        """*Open in Library* on a clicked piece or item: show it in the model viewer."""
        row = query.get(self.con, self.game, vpath)
        if row is None:
            self.error(f"{vpath} is not in the index yet: use “Build / refresh index”.")
            return
        self.left.setCurrentWidget(self.library_view)
        self.show_asset(row["id"])

    def open_welcome(self) -> None:
        from .welcome import Welcome
        Welcome(self).show()

    def open_game_setup(self) -> None:
        from .setup_dialog import GameSetup
        GameSetup(self).show()

    def open_mod_manager(self) -> None:
        from .mod_manager import ModManager
        dlg = ModManager(self)
        dlg.finished.connect(lambda _r: self.refresh_mods())   # on/off, order: redraw
        dlg.show()

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


def _scrolled(w: QWidget) -> QScrollArea:
    """``w`` in a scroll area: a panel made short (docked under another) still shows all
    of it."""
    sa = QScrollArea()
    sa.setWidget(w)
    sa.setWidgetResizable(True)
    sa.setFrameShape(QScrollArea.NoFrame)
    return sa


def _help_links(step: str) -> str:
    """A context-help step with its Markdown links (``[how](07-blender-setup.md#…)``)
    turned into links the "How to mod this" box opens in the help window."""
    import re
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', step)


def help_for_error(text: str) -> tuple[str, str]:
    """The help page and section that explain an error message: the troubleshooting
    table row (or guide) sharing the most words with it."""
    import re
    from .. import help as dhelp
    from .help_view import slug
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", text.split("\n")[0])
             if w.lower() not in {"error", "with", "that", "this", "from", "have", "data"}]
    best, score = ("12-troubleshooting.md", ""), 0
    for t in dhelp.topics():
        heading = ""
        for line in dhelp.read(t.name).splitlines():
            if line.startswith("#"):
                heading = line.lstrip("#").strip()
            elif line.startswith("|"):
                low = line.lower()
                n = sum(1 for w in words if w.lower() in low)
                if n > score:
                    best, score = (t.name, slug(heading)), n
    return best if score >= 2 else ("12-troubleshooting.md", "")


def app_icon() -> QIcon:
    """DR2 Studio's icon (our own drawing, `icon/dr2studio.svg`; bitmaps for releases
    come from tools/release/make_icons.py)."""
    return QIcon(str(Path(__file__).with_name("icon") / "dr2studio.svg"))


def install_error_hook(win: "MainWindow") -> None:
    """Show unexpected Python errors instead of losing them.

    Studio on Windows has no console, and Qt drops an exception raised in a click
    handler after printing it there: a bug then looked like nothing happening (a model
    that never showed, 2026-10-10). Every such error now goes to the log, to
    ``studio-errors.log`` in the cache folder (for bug reports), and to an error box.
    """
    from ..userdirs import cache_dir
    previous = sys.excepthook

    def hook(kind, value, tb):
        text = "".join(traceback.format_exception(kind, value, tb))
        try:
            f = cache_dir() / "studio-errors.log"
            f.parent.mkdir(parents=True, exist_ok=True)
            with f.open("a", encoding="utf-8") as out:
                out.write(text + "\n")
            win.error(f"Something went wrong inside DR2 Studio (a bug). The details are in "
                      f"the log below and in {f}; please include them in a report.\n\n"
                      f"{kind.__name__}: {value}")
            win.say(text)
        except Exception:  # noqa: BLE001 - never fail inside the error handler
            previous(kind, value, tb)
    sys.excepthook = hook


def main(argv: list[str] | None = None, *, game: str | None = None,
         map_level: str | None = None, at: str | None = None) -> int:
    """Start DR2 Studio. ``game`` picks the game; ``map_level`` opens the Maps tab on
    that level (``dr2 studio --map living_research -g cw``), ``at`` (``"x,y,z"`` or
    ``"x,y,z,heading°"``) puts the camera there."""
    app = QApplication.instance() or QApplication(sys.argv[:1] + list(argv or []))
    app.setApplicationName("DR2 Studio")
    app.setWindowIcon(app_icon())
    win = MainWindow()
    install_error_hook(win)
    win.show()
    if game:
        i = win.game_box.findData(game)
        if i >= 0:
            win.game_box.setCurrentIndex(i)
    if map_level:
        def open_map():
            win.left.setCurrentWidget(win.maps_list)
            win._map_chosen(map_level, "")
            if at:
                v = [float(c) for c in at.split(",")]
                h = "null" if len(v) < 4 else repr(v[3] * 3.141592653589793 / 180)
                win.maps_view._js(f"dr2.goTo({v[0]}, {v[1]}, {v[2]}, {h})")
        QTimer.singleShot(0, open_map)
    for arg in argv or []:                  # `dr2 studio x.dr2mod`, or a double-click
        if Path(arg).suffix.lower() in (".dr2mod", ".zip") and Path(arg).is_file():
            QTimer.singleShot(0, lambda a=arg: win.install_mod(a))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

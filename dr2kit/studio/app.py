"""DR2 Studio's main window: browse, search, view, extract, and make a texture mod.

Layout (docs/dev/studio.md has the diagram):

* **Left**, two tabs. *Browse*: the game's folders and archives as a tree, expanded on
  demand from the index (`dr2kit.index.query.children`). *Search*: words matched against
  asset names, filtered by kind; results show texture thumbnails, as a list or a grid.
* **Centre**: a viewer for the selected asset (`viewers.TextureViewer`, or
  `viewers.PlainViewer` for text and everything else).
* **Right**: details (sizes, compression, texture facts), relations (the models that use
  a texture, the textures a model names; double-click to jump), and the actions:
  *Extract…*, *Export PNG…*, *Replace with PNG…* (copies the PNG into the open mod's
  ``replace/`` folder under the asset's vpath).
* **Bottom**: the mod bar (open/new mod folder, its overrides, *Build && deploy*) and a log.

Long jobs (building the index, building a mod) run in a `QThread` so the window stays
responsive. Asset bytes come from `AssetTree` (the real files), the tree and search from
the index; Studio holds no format knowledge of its own.
"""

from __future__ import annotations

import shutil
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal
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
from .viewers import PlainViewer, TextureViewer

ROLE_ID = Qt.UserRole + 1        # asset id (None for folder nodes)
ROLE_VPATH = Qt.UserRole + 2
ROLE_LOADED = Qt.UserRole + 3
CONTAINER_KINDS = {"archive", "texture-pack", "model", "skeleton", "scene"}
KINDS = ["all kinds", "texture", "model", "skeleton", "texture-pack", "archive", "audio",
         "anim", "text", "shader", "binary", "video", "empty"]


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
        self.empty = QLabel("Select an asset on the left.\n\nNo index yet? Use “Build / refresh "
                            "index” (about a minute per game).")
        self.empty.setAlignment(Qt.AlignCenter)
        self.centre = QStackedWidget()
        for w in (self.empty, self.tex_view, self.plain_view):
            self.centre.addWidget(w)

        # --- right: details, relations, actions
        self.details = QTextBrowser()
        self.relations = QListWidget()
        self.relations.itemDoubleClicked.connect(self._jump)
        self.btn_extract = QPushButton("Extract…")
        self.btn_png = QPushButton("Export PNG…")
        self.btn_replace = QPushButton("Replace with PNG…")
        self.btn_extract.clicked.connect(self.extract)
        self.btn_png.clicked.connect(self.export_png)
        self.btn_replace.clicked.connect(self.replace_png)
        rw = QWidget()
        rl = QVBoxLayout(rw)
        rl.addWidget(QLabel("<b>Details</b>"))
        rl.addWidget(self.details, 2)
        rl.addWidget(QLabel("<b>Related</b> (double-click to open)"))
        rl.addWidget(self.relations, 1)
        for b in (self.btn_extract, self.btn_png, self.btn_replace):
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
        th = QThread(self)
        job = Job(fn)
        job.moveToThread(th)
        th.started.connect(job.run)
        job.line.connect(self.say)
        job.done.connect(lambda r, err: (on_done(r, err), th.quit()))
        th.finished.connect(lambda: self._threads.remove((th, job)))
        self._threads.append((th, job))
        th.start()

    def _update_buttons(self) -> None:
        a = self.current
        self.btn_extract.setEnabled(a is not None)
        is_tex = bool(a) and a["kind"] == "texture"
        self.btn_png.setEnabled(is_tex)
        self.btn_replace.setEnabled(is_tex and self.mod_dir is not None)
        self.btn_replace.setToolTip("" if self.mod_dir else "Open or create a mod first")

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
        if row["kind"] == "texture":
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
        else:
            from ..census import content_kind
            self.plain_view.show_bytes(data, content_kind(data) == "text")
            self.centre.setCurrentWidget(self.plain_view)
            if row["kind"] == "model":
                for r in query.textures_of(self.con, asset_id):
                    self._relation(f"slot {r['slot']}: {r['dst_name']}  →  {r['vpath'] or 'not found'}",
                                   r["id"])
        dup = query.same_content(self.con, asset_id)
        if dup:
            lines.append(f"identical copies elsewhere: {len(dup)}")
        self.details.setHtml("<br>".join(lines))

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
        game, folder = self.game, self.mod_dir

        def work(progress):
            from ..mods import build as mbuild
            from ..mods import deploy as mdeploy
            from ..mods.manifest import Mod
            import tempfile
            loc = locate(game)
            if not mdeploy.is_recomp_root(loc.root):
                raise Dr2Error(f"{game}'s data is not in a recomp; use `dr2 mod deploy --to`")
            dirs = mdeploy.recomp_folders(loc.root)
            base = [dirs["patched"]] if dirs["patched"].is_dir() else []
            with tempfile.TemporaryDirectory(prefix="dr2mod-") as tmp:
                res = mbuild.build([Mod.load(folder)], game, AssetTree(loc.root), tmp, base,
                                   progress=lambda vp: progress(f"built {vp}"))
                written = mdeploy.deploy(res, dirs["mods"])
            for w in mdeploy.shadowed_layers(loc.root, written):
                progress("warning: " + w)
            return written, dirs["mods"]

        self.say(f"building {folder.name} for {game}…")

        def done(result, err):
            if err:
                self.error(err)
                return
            written, target = result
            env = "CZ_NO_MODS" if game == "cz" else "CW_NO_MODS"
            self.say(f"deployed {len(written)} file(s) to {target}. Start the recomp; "
                     f"{env}=1 turns mods off.")
        self.run_job(work, done)

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

"""DR2 Studio's Library tab: the games' assets by what they are, and export in one go.

The first tab Studio opens on (phase 8). Top: the sections and groups of
dr2kit/catalog/groups.toml (Models → Characters, Zombies…; Sounds → Music, Voices…)
with their counts, split into sub-groups where the rules say so. Below: the selected
group's description, a filter box, and its items as a grid of pictures (a model's
render, a texture's thumbnail, both made when the index is built) or a list; identical
copies are shown once. Selecting an item shows it in the centre as everywhere else
(the window's `show_asset`).

*Export…* writes the selected items, or the whole group / sub-group when none is
selected, with `dr2kit.catalog.export` in a worker thread: a progress bar, *Cancel*,
and existing files skipped (so an export can be resumed).

Pictures are loaded only when an item scrolls into view (`LibraryModel.data`), so a
group of 18,000 textures opens at once.
"""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, QSize, Qt, QThread, Signal, Slot
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QListView, QMessageBox, QProgressDialog, QPushButton,
                               QSplitter, QStyle, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from ..catalog.groups import catalog
from ..index import query

ROLE_ID = Qt.UserRole + 1
ROLE_KEY = Qt.UserRole + 2           # tree items: (group id, sub or None)
GRID_KINDS = {"model", "texture"}    # groups of these show as a grid of pictures


class LibraryModel(QAbstractListModel):
    """The items of one group for a QListView; pictures are read when first shown."""

    def __init__(self, con_getter, parent=None):
        super().__init__(parent)
        self._con = con_getter
        self.rows: list[dict] = []
        self._icons: dict[int, QIcon] = {}
        style = QApplication.style()
        self._kind_icons = {
            "audio": style.standardIcon(QStyle.SP_MediaVolume),
            "video": style.standardIcon(QStyle.SP_MediaPlay),
            "skeleton": style.standardIcon(QStyle.SP_DirIcon),
        }
        self._file_icon = style.standardIcon(QStyle.SP_FileIcon)

    def set_rows(self, rows) -> None:
        self.beginResetModel()
        self.rows = [dict(r) for r in rows]
        self._icons.clear()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r = self.rows[index.row()]
        if role == Qt.DisplayRole:
            return f"{r['label']}\n{r['name']}" if r["label"] else r["name"]
        if role == Qt.ToolTipRole:
            return f"{r['label'] or r['name']}\n{r['vpath']}\n{r['kind']}, {r['size']:,} bytes"
        if role == Qt.DecorationRole:
            return self._icon(r)
        if role == ROLE_ID:
            return r["id"]
        return None

    def _icon(self, r) -> QIcon:
        if r["kind"] not in GRID_KINDS:
            return self._kind_icons.get(r["kind"], self._file_icon)
        icon = self._icons.get(r["id"])
        if icon is None:
            png = query.picture(self._con(), r["id"])
            icon = QIcon(QPixmap.fromImage(QImage.fromData(png))) if png else self._file_icon
            self._icons[r["id"]] = icon
        return icon


class _ExportWorker(QObject):
    """Runs `dr2kit.catalog.export.Exporter` in a thread; reports each step."""
    step = Signal(int, int, str)
    finished = Signal(object, object)          # Result, error text

    def __init__(self, game, root, db_path, jobs, cancel: threading.Event):
        super().__init__()
        self.game, self.root, self.db_path, self.jobs, self.cancel = game, root, db_path, jobs, cancel

    @Slot()
    def run(self):
        from ..catalog.export import Exporter
        from ..container.vpath import AssetTree
        try:
            ex = Exporter(AssetTree(self.root, cache_size=32), self.game, self.db_path)
            try:
                res = ex.run(self.jobs, progress=self.step.emit, cancel=self.cancel.is_set)
            finally:
                ex.close()
            self.finished.emit(res, None)
        except Exception as e:  # noqa: BLE001 - shown to the user
            self.finished.emit(None, str(e))


class LibraryView(QWidget):
    """The Library tab. ``selected(asset id)`` when an item is picked; ``say(text)`` for
    the log."""
    selected = Signal(int)
    say = Signal(str)

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window                      # the MainWindow (con, game, db_path)
        self.game = None
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Group", "Items"])
        self.tree.setRootIsDecorated(True)
        self.tree.currentItemChanged.connect(lambda cur, _p: self._open(cur))
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setStyleSheet("QLabel { color: palette(placeholder-text); }")
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("filter: words in the name")
        self.filter.textChanged.connect(lambda _t: self._load())
        self.grid_btn = QPushButton("Grid")
        self.grid_btn.setCheckable(True)
        self.grid_btn.setChecked(True)
        self.grid_btn.toggled.connect(self._grid)
        self.model = LibraryModel(lambda: self.window.con, self)
        self.items = QListView()
        self.items.setModel(self.model)
        self.items.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.items.setUniformItemSizes(True)
        self.items.selectionModel().currentChanged.connect(
            lambda cur, _p: cur.isValid() and self.selected.emit(cur.data(ROLE_ID)))
        self.count = QLabel()
        self.export_btn = QPushButton("Export…")
        self.export_btn.setToolTip("Export the selected items, or the whole group when none is "
                                   "selected: models with their textures and rig, sounds as "
                                   "WAV, movies as MP4, text as JSON")
        self.export_btn.clicked.connect(self.export)

        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(self.tree)
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(self.description)
        row = QHBoxLayout()
        row.addWidget(self.filter, 1)
        row.addWidget(self.grid_btn)
        bl.addLayout(row)
        bl.addWidget(self.items, 1)
        row = QHBoxLayout()
        row.addWidget(self.count, 1)
        row.addWidget(self.export_btn)
        bl.addLayout(row)
        split = QSplitter(Qt.Vertical)
        split.addWidget(top)
        split.addWidget(bottom)
        split.setSizes([260, 520])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(split)
        self._key: tuple[str, str | None] | None = None
        self._grid(True)

    # ---- groups ----------------------------------------------------------------------

    def set_game(self, game: str) -> None:
        """Fill the group tree for ``game`` from the index."""
        self.game = game
        self.tree.clear()
        self.model.set_rows([])
        counts = query.library_counts(self.window.con, game)
        if not counts:
            self.description.setText("Nothing here yet: use “Build / refresh index” in the "
                                     "toolbar (a few minutes the first time).")
            self.count.setText("")
            return
        per: dict[str, dict[str, int]] = {}
        for r in counts:
            per.setdefault(r["grp"], {})[r["sub"]] = r["n"]
        cat = catalog()
        first = None
        for section in cat.sections():
            groups = [g for g in cat.groups if g.section == section and g.id in per]
            if not groups:
                continue
            sec = QTreeWidgetItem([section, str(sum(sum(per[g.id].values()) for g in groups))])
            sec.setFlags(sec.flags() & ~Qt.ItemIsSelectable)
            self.tree.addTopLevelItem(sec)
            for g in groups:
                subs = per[g.id]
                it = QTreeWidgetItem([g.title, str(sum(subs.values()))])
                it.setData(0, ROLE_KEY, (g.id, None))
                it.setToolTip(0, g.description)
                sec.addChild(it)
                if len(subs) > 1 or "" not in subs:
                    for s in sorted(subs):
                        si = QTreeWidgetItem([s or "(other)", str(subs[s])])
                        si.setData(0, ROLE_KEY, (g.id, s))
                        it.addChild(si)
                first = first or it
            sec.setExpanded(True)
        self.tree.resizeColumnToContents(0)
        if first is not None:
            self.tree.setCurrentItem(first)

    def select_group(self, group_id: str, sub: str | None = None) -> bool:
        """Show a group (for tests and links); True if it exists for this game."""
        for i in range(self.tree.topLevelItemCount()):
            sec = self.tree.topLevelItem(i)
            for j in range(sec.childCount()):
                it = sec.child(j)
                if it.data(0, ROLE_KEY) == (group_id, None):
                    if sub is not None:
                        for k in range(it.childCount()):
                            if it.child(k).data(0, ROLE_KEY) == (group_id, sub):
                                self.tree.setCurrentItem(it.child(k))
                                return True
                        return False
                    self.tree.setCurrentItem(it)
                    return True
        return False

    def _open(self, item) -> None:
        key = item.data(0, ROLE_KEY) if item is not None else None
        if not key:
            return
        self._key = tuple(key)
        g = catalog().group(key[0])
        self.description.setText(f"<b>{g.title}</b>" + (f" › {key[1] or '(other)'}" if key[1] is not None else "")
                                 + f"<br>{g.description}")
        kinds = set(g.kinds)
        self.grid_btn.setChecked(bool(kinds & GRID_KINDS))
        self._load()

    def _load(self) -> None:
        if not self._key or self.game is None:
            return
        grp, sub = self._key
        rows = query.library_items(self.window.con, self.game, grp, sub, self.filter.text())
        self.model.set_rows(rows)
        copies = self.window.con.execute(
            "SELECT count(*) FROM library_item WHERE game=? AND grp=? AND copy_of IS NOT NULL"
            + (" AND sub=?" if sub is not None else ""),
            (self.game, grp) + ((sub,) if sub is not None else ())).fetchone()[0]
        self.count.setText(f"{len(rows):,} item{'s' if len(rows) != 1 else ''}"
                           + (f" (+{copies:,} identical copies, shown once)" if copies else ""))

    def _grid(self, on: bool) -> None:
        v = self.items
        v.setViewMode(QListView.IconMode if on else QListView.ListMode)
        v.setIconSize(QSize(112, 112) if on else QSize(24, 24))
        v.setGridSize(QSize(136, 168) if on else QSize())
        v.setResizeMode(QListView.Adjust)
        v.setWordWrap(on)
        v.setMovement(QListView.Static)

    # ---- export ----------------------------------------------------------------------

    def chosen_rows(self) -> list[dict]:
        """The selected items, or every item shown when none is selected."""
        picked = sorted({i.row() for i in self.items.selectionModel().selectedIndexes()})
        return [self.model.rows[i] for i in picked] if picked else list(self.model.rows)

    def export(self, folder: str | None = None) -> None:
        rows = self.chosen_rows()
        if not rows:
            return
        if folder is None:
            folder = QFileDialog.getExistingDirectory(
                self, f"Export {len(rows)} item(s) into… (a {self.game} folder is made in it)")
        if not folder:
            return
        self.window.export_rows(rows, Path(folder), by_group=True)


def run_export(window, rows: list, out: Path, *, by_group: bool, on_done=None) -> None:
    """Export ``rows`` of the window's game into ``out`` with a progress dialog and
    *Cancel* (`dr2kit.catalog.export`)."""
    import os
    from ..catalog.export import plan
    from ..profiles import locate
    game = window.game
    jobs = plan(rows, out, game, by_group=by_group, con=window.con)
    cancel = threading.Event()
    dlg = None
    if not os.environ.get("DR2_STUDIO_NO_DIALOGS"):
        dlg = QProgressDialog(f"Exporting {len(jobs)} item(s)…", "Cancel", 0, len(jobs), window)
        dlg.setWindowTitle("Export")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(300)
        dlg.canceled.connect(cancel.set)
    th = QThread(window)
    worker = _ExportWorker(game, locate(game).root, window.db_path, jobs, cancel)
    worker.moveToThread(th)
    relay = _Relay(window, dlg, out, on_done, th)
    th.started.connect(worker.run)
    worker.step.connect(relay.step)
    worker.finished.connect(relay.finished)
    worker.finished.connect(th.quit)
    entry = (th, worker, relay)
    th.finished.connect(lambda: window._threads.remove(entry))
    window._threads.append(entry)
    window.say(f"exporting {len(jobs)} item(s) of {game} into {out}…")
    th.start()


class _Relay(QObject):
    """Brings the export worker's signals to the GUI thread (see app._Relay)."""

    def __init__(self, window, dlg, out, on_done, thread):
        super().__init__()
        self.window, self.dlg, self.out, self.on_done = window, dlg, out, on_done

    @Slot(int, int, str)
    def step(self, done, total, vpath):
        if self.dlg is not None:
            self.dlg.setMaximum(total)
            self.dlg.setValue(done)
            if vpath:
                self.dlg.setLabelText(f"{done + 1} of {total}: {vpath.rsplit('/', 1)[-1]}")

    @Slot(object, object)
    def finished(self, res, err):
        if self.dlg is not None:
            self.dlg.reset()
        if err:
            self.window.error(err)
        else:
            for vp, why in res.failed[:20]:
                self.window.say(f"  failed: {vp}: {why}")
            self.window.say(f"export into {self.out}: {res.summary()}")
            if res.failed and len(res.failed) > 20:
                self.window.say(f"  … and {len(res.failed) - 20} more failures")
            if not res.cancelled and self.dlg is not None and not res.failed:
                QMessageBox.information(self.window, "Export", f"Done: {res.summary()}.\n\n{self.out}")
        if self.on_done:
            self.on_done(res, err)

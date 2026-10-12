"""The Maps tab's editor panels, laid out like a game editor's (Unity, Unreal): the
**Hierarchy** (everything in the open level, as a list to find and select things) and
**Place** (things to put in the level: prefabs, items, zombies, buildings, dragged onto
the 3D view or double-clicked). `maps_view.MapsView` fills them and acts on their
signals; `app.MainWindow` puts each in its own dock window.

Why a list as well as the 3D view: a level holds hundreds of items and buildings, many
hidden inside others or far away; a filterable list finds one by name and flies the
camera to it (``dr2.focus``), the way an editor's hierarchy does.

Placing: a Place row is dragged onto the 3D view (its text is ``dr2place:`` + JSON of
what to place; the page itself takes the drop, so the point is exactly under the mouse,
and answers ``dr2:drop``), or **clicked** (``arm``: the page's ring follows the mouse and a
click on the view puts it there, Esc cancels), or double-clicked (``place``: where the
middle of the view meets the floor). Pictures are the Library's model pictures (made
when the index is built), read only when a row is shown.
"""

from __future__ import annotations

import json

from PySide6.QtCore import QAbstractListModel, QMimeData, QModelIndex, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QLabel, QLineEdit,
                               QListView, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

MIME = "application/x-dr2-place"
TEXT = "dr2place:"         # the drag's text: this, then the JSON (maps.js reads it)
ROLE = Qt.UserRole + 1

# Place's kinds, in the order of its list (key, label, tooltip)
KINDS = [("prefab", "Prefabs", "Things that work like the game's own: a save point, a "
          "workbench, a door to another level, a spawn point, a blocker, your own prefabs"),
         ("item", "Items", "Every item of items.txt whose model ships in this game: weapons, "
          "food, furniture, cars, barriers…"),
         ("zombie", "Zombies", "Zombie types (they go in your mod's own mission and appear "
          "in a new game)"),
         ("piece", "Buildings", "This level's buildings and other level pieces: a copy of one "
          "(stays with its zone; not checked in game yet)")]


class PlaceModel(QAbstractListModel):
    """The rows of one kind: ``{"kind", "name", "label", "tip", "vpath", …}``; a row's
    picture comes from ``picture(vpath)`` the first time it is shown."""

    def __init__(self, picture=None, parent=None):
        super().__init__(parent)
        self.rows: list[dict] = []
        self.picture = picture
        self._icons: dict[str, QIcon] = {}

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):  # noqa: N802 - Qt's name
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r = self.rows[index.row()]
        if role == Qt.DisplayRole:
            return r.get("label") or r["name"]
        if role == Qt.ToolTipRole:
            return r.get("tip") or r["name"]
        if role == ROLE:
            return r
        if role == Qt.DecorationRole and self.picture and r.get("vpath"):
            vp = r["vpath"]
            if vp not in self._icons:
                png = self.picture(vp)
                self._icons[vp] = QIcon(QPixmap.fromImage(QImage.fromData(png))) if png else QIcon()
            return self._icons[vp]
        return None

    def flags(self, index):
        f = super().flags(index)
        return f | Qt.ItemIsDragEnabled if index.isValid() else f

    def mimeTypes(self):  # noqa: N802
        return [MIME]

    def mimeData(self, indexes):  # noqa: N802
        md = QMimeData()
        if indexes:
            r = self.rows[indexes[0].row()]
            md.setData(MIME, json.dumps(place_spec(r)).encode())
            md.setText(TEXT + json.dumps(place_spec(r)))       # what the page reads
        return md


def place_spec(row: dict) -> dict:
    """What a Place row asks to put in the level (the drag's JSON)."""
    return {k: row[k] for k in ("kind", "name", "zone", "prefab", "group") if k in row}


class PlacePanel(QWidget):
    """Things to put in the level (module docstring). ``place(spec)``: double-clicked
    (put it where the middle of the view meets the floor)."""

    place = Signal(dict)
    arm = Signal(dict)        # clicked: place it with the next click in the 3D view

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        row = QHBoxLayout()
        self.kind_box = QComboBox()
        for key, label, tip in KINDS:
            self.kind_box.addItem(label, key)
            self.kind_box.setItemData(self.kind_box.count() - 1, tip, Qt.ToolTipRole)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("filter: katana, bench, save…")
        self.filter.setClearButtonEnabled(True)
        row.addWidget(self.kind_box)
        row.addWidget(self.filter, 1)
        lay.addLayout(row)
        self.model = PlaceModel()
        self.list = QListView()
        self.list.setModel(self.model)
        self.list.setViewMode(QListView.IconMode)
        self.list.setIconSize(QSize(64, 64))
        self.list.setGridSize(QSize(104, 100))
        self.list.setResizeMode(QListView.Adjust)
        self.list.setWordWrap(True)
        self.list.setUniformItemSizes(True)
        self.list.setMovement(QListView.Static)
        self.list.setDragEnabled(True)
        self.list.setDragDropMode(QAbstractItemView.DragOnly)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.clicked.connect(lambda i: self.arm.emit(place_spec(i.data(ROLE))))
        self.list.doubleClicked.connect(lambda i: self.place.emit(place_spec(i.data(ROLE))))
        lay.addWidget(self.list, 1)
        self.note = QLabel("Drag onto the 3D view, or click it and then click in the view "
                           "where it goes (Esc cancels). Double-click: the middle of the view.")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        self._all: dict[str, list[dict]] = {}
        self._source = None                  # kind -> rows, called when a kind is first shown
        self.kind_box.currentIndexChanged.connect(lambda _i: self._show())
        self.filter.textChanged.connect(lambda _t: self._show())

    def set_source(self, source, picture=None) -> None:
        """``source(kind)`` gives the rows of a kind (read when the kind is shown)."""
        self._source = source
        self.model.picture = picture
        self.model._icons.clear()
        self._all.clear()
        self._show()

    def forget(self, kind: str | None = None) -> None:
        """Read a kind's rows again next time (the level or the mod's items changed)."""
        if kind is None:
            self._all.clear()
        else:
            self._all.pop(kind, None)
        self._show()

    def _show(self) -> None:
        kind = self.kind_box.currentData()
        if kind not in self._all:
            try:
                self._all[kind] = self._source(kind) if self._source else []
            except Exception as e:  # noqa: BLE001 - shown in the panel, never a crash
                self._all[kind] = []
                self.note.setText(f"Could not list them: {e}")
        words = self.filter.text().lower().split()
        rows = [r for r in self._all[kind]
                if all(w in (r.get("label") or r["name"]).lower() or w in r["name"].lower()
                       for w in words)]
        self.model.set_rows(rows)


class HierarchyPanel(QWidget):
    """Everything placed in the open level, by group; ``chosen(target)`` when a row is
    clicked, with ``{"kind", "name", "zone"?, "position"?}`` (`MapsView` flies there)."""

    chosen = Signal(dict)

    GROUPS = [("item", "Items and doors"), ("piece", "Buildings (parts and collision inside)"),
              ("zombie", "Zombies"),
              ("marker", "Spawn points, save points, triggers")]

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("filter by name")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._apply_filter)
        lay.addWidget(self.filter)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "What"])
        self.tree.setUniformRowHeights(True)
        self.tree.setColumnWidth(0, 190)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.itemActivated.connect(self._clicked)
        lay.addWidget(self.tree, 1)
        self.count = QLabel("Open a level in the Maps tab.")
        self.count.setWordWrap(True)
        lay.addWidget(self.count)
        self._open: set[str] = {"item"}          # groups expanded (kept across refills)

    def fill(self, rows: dict[str, list[dict]]) -> None:
        """``rows``: group key → ``{"kind", "name", "what", "zone"?, "position"?,
        "hidden"?, "added"?}``."""
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            key = top.data(0, ROLE)
            if top.isExpanded():
                self._open.add(key)
            else:
                self._open.discard(key)
        self.tree.clear()
        total = 0
        for key, label in self.GROUPS:
            items = rows.get(key) or []
            top = QTreeWidgetItem([f"{label} ({len(items)})", ""])
            top.setData(0, ROLE, key)
            top.setFlags(Qt.ItemIsEnabled)
            for r in items:
                it = self._row(r)
                top.addChild(it)
                for kid in r.get("children") or []:
                    it.addChild(self._row(kid))
            self.tree.addTopLevelItem(top)
            top.setExpanded(key in self._open)
            total += len(items)
        self.count.setText(f"{total} things. Click one to fly to it and select it.")
        self._apply_filter(self.filter.text())

    @staticmethod
    def _row(r: dict) -> QTreeWidgetItem:
        it = QTreeWidgetItem([r.get("label") or r["name"], r.get("what") or ""])
        it.setData(0, ROLE, r)
        tip = r.get("what") or ""
        if r.get("zone"):
            tip += f" (zone {r['zone']})"
        if r.get("hidden"):
            it.setForeground(0, Qt.gray)
            it.setText(1, (r.get("what") or "") + " (hidden by your mod)")
        elif r.get("added"):
            it.setText(1, (r.get("what") or "") + " (added by your mod)")
        it.setToolTip(0, tip)
        return it

    def _apply_filter(self, text: str) -> None:
        words = text.lower().split()

        def match(it) -> bool:
            hay = (it.text(0) + " " + it.text(1)).lower()
            return all(w in hay for w in words)

        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            shown = 0
            for j in range(top.childCount()):
                it = top.child(j)
                kids = [it.child(k) for k in range(it.childCount())]
                kid_hit = False
                for k in kids:
                    hit = not words or match(k)
                    k.setHidden(not hit and not (words and match(it)))
                    kid_hit |= bool(words) and hit
                hide = bool(words) and not match(it) and not kid_hit
                it.setHidden(hide)
                if words and kid_hit:
                    it.setExpanded(True)
                shown += not hide
            if words:
                top.setExpanded(shown > 0)

    def _clicked(self, item, _col=0) -> None:
        r = item.data(0, ROLE)
        if isinstance(r, dict):
            self.chosen.emit(r)

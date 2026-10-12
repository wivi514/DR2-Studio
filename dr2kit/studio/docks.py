"""DR2 Studio's window layout: every panel is a **dock window** (user request, 2026-10-11:
"resize any window like maps, model and all, drag it and have it in a new window").

Each panel (`Dock`) can be resized by its edges, dragged to another side of the main
window, stacked with another panel as tabs, or dragged out as a window of its own (on a
second screen, say), and dragged back or double-clicked to return. The *Windows* menu
(`Layout.menu`) shows or hides each one, puts every floating window back, and resets the
layout. The layout is saved when Studio closes and restored when it starts
(`layout.ini` in the config folder, `dr2kit.userdirs`), unless ``DR2_STUDIO_NO_LAYOUT``
is set (the tests).

The middle of the window is a **stage** (a window inside the window) holding the two big
views, the viewer and the level in 3D: it takes whatever room the side panels leave, as a
game editor's scene view does. Those two can be tabbed, split side by side, or floated
as windows too, within the stage.

**Two sets of panels** share the window: the asset panels (the viewer and its details)
and the Maps panels (the level in 3D, Map, Inspector, Hierarchy, Place). `Layout.mode`
shows one set and hides the other, as the Maps tab did when it had one fixed side
panel; a panel dragged out as its own window stays open in both, and a panel the user
closed stays closed until the *Windows* menu opens it again.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QByteArray, QSettings, Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDockWidget, QMainWindow, QMenu, QWidget

from ..userdirs import config_dir

LAYOUT_VERSION = 1          # bump when the panels change: an older saved layout is dropped
SETTINGS_FILE = "layout.ini"
MIN_SIDE = 380              # the side column's width when a mode shows it narrower
MIN_WIDTH = {"inspector": 260, "map_tools": 220, "details": 240, "place": 300,
             "browse": 220, "hierarchy": 200}


class Dock(QDockWidget):
    """One panel of the window (module docstring). ``user_closed``: closed with its own
    close button (not hidden by a mode switch), so a mode switch leaves it closed."""

    def __init__(self, title: str, name: str, widget: QWidget, parent: QMainWindow,
                 tip: str = ""):
        super().__init__(title, parent)
        self.setObjectName(name)
        self.setWidget(widget)
        self.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
                         | QDockWidget.DockWidgetClosable)
        self.setToolTip(tip)
        self.user_closed = False
        self.toggleViewAction().setToolTip(tip)
        self.toggleViewAction().triggered.connect(self._chosen)
        self.topLevelChanged.connect(self._floating)

    def closeEvent(self, ev):  # noqa: N802 - Qt's name
        self.user_closed = True
        super().closeEvent(ev)

    def _chosen(self, on: bool) -> None:
        self.user_closed = not on
        if on:
            self.raise_()

    def _floating(self, floating: bool) -> None:
        if floating and self.width() < 320:           # a usable size for a window of its own
            self.resize(max(self.width(), 480), max(self.height(), 360))


class Layout:
    """The window's docks, the two modes, the *Windows* menu and the saved layout."""

    def __init__(self, win: QMainWindow):
        self.win = win
        self.stage = QMainWindow()               # the middle: the viewer, the level in 3D
        self.stage.setObjectName("stage")
        self.stage.setDockOptions(QMainWindow.AnimatedDocks | QMainWindow.AllowNestedDocks
                                  | QMainWindow.AllowTabbedDocks)
        win.setCentralWidget(self.stage)
        self.docks: dict[str, Dock] = {}
        self.asset_docks: list[str] = []
        self.map_docks: list[str] = []
        self.maps = False
        self.sizes_pending = False
        win.setDockOptions(QMainWindow.AnimatedDocks | QMainWindow.AllowNestedDocks
                           | QMainWindow.AllowTabbedDocks | QMainWindow.GroupedDragging)
        win.setDockNestingEnabled(True)
        win.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)
        win.setCorner(Qt.BottomRightCorner, Qt.RightDockWidgetArea)

    def add(self, name: str, title: str, widget: QWidget, *, mode: str | None = None,
            tip: str = "", stage: bool = False) -> Dock:
        """A panel; ``mode`` "assets" or "maps" ties it to one set, ``stage`` puts it in
        the middle (module docstring)."""
        d = Dock(title, name, widget, self.stage if stage else self.win, tip)
        d.on_stage = stage
        if name in MIN_WIDTH:                    # never squeezed to a sliver
            d.setMinimumWidth(MIN_WIDTH[name])
        self.docks[name] = d
        if mode == "assets":
            self.asset_docks.append(name)
        elif mode == "maps":
            self.map_docks.append(name)
        return d

    def arrange(self) -> None:
        """The default layout (first start, *Reset layout*): Browse on the left with the
        Hierarchy under it, the viewer and the level in 3D in the middle (as tabs),
        Details / Inspector and Map on the right, the mod bar and Place at the bottom."""
        w, d = self.win, self.docks
        for dock in d.values():
            dock.setFloating(False)
            dock.user_closed = False
            (self.stage if dock.on_stage else w).removeDockWidget(dock)
        self.stage.addDockWidget(Qt.TopDockWidgetArea, d["viewer"])
        self.stage.tabifyDockWidget(d["viewer"], d["map"])
        w.addDockWidget(Qt.LeftDockWidgetArea, d["browse"])
        w.splitDockWidget(d["browse"], d["hierarchy"], Qt.Vertical)
        w.addDockWidget(Qt.RightDockWidgetArea, d["details"])
        w.addDockWidget(Qt.RightDockWidgetArea, d["inspector"])
        w.splitDockWidget(d["inspector"], d["map_tools"], Qt.Vertical)
        w.addDockWidget(Qt.BottomDockWidgetArea, d["mod"])
        w.splitDockWidget(d["mod"], d["place"], Qt.Horizontal)
        for dock in d.values():
            dock.show()
        self.mode(self.maps, force=True)
        self.sizes_pending = True
        if w.isVisible():
            QTimer.singleShot(0, self.fit)

    def fit(self) -> None:
        """The default sizes, as parts of the window (Qt ignores dock sizes set before
        the window is shown, so the window calls this once it is: `MainWindow.showEvent`)."""
        self.sizes_pending = False
        w, d = self.win, self.docks
        W, H = max(w.width(), 800), max(w.height(), 600)
        w.resizeDocks([d["browse"], d["details"], d["inspector"]],
                      [int(W * 0.2), int(W * 0.24), int(W * 0.24)], Qt.Horizontal)
        w.resizeDocks([d["mod"]], [int(H * 0.22)], Qt.Vertical)
        w.resizeDocks([d["mod"], d["place"]], [int(W * 0.25), int(W * 0.29)], Qt.Horizontal)
        w.resizeDocks([d["inspector"], d["map_tools"]], [int(H * 0.45), int(H * 0.3)], Qt.Vertical)
        w.resizeDocks([d["browse"], d["hierarchy"]], [int(H * 0.45), int(H * 0.3)], Qt.Vertical)

    def mode(self, maps: bool, force: bool = False) -> None:
        """Show the Maps panels (``maps``) or the asset panels; hide the other set's
        docked panels (module docstring)."""
        if maps == self.maps and not force:
            return
        self.maps = maps
        show, hide = (self.map_docks, self.asset_docks) if maps else \
            (self.asset_docks, self.map_docks)
        for name in hide:
            dock = self.docks[name]
            if not dock.isFloating():
                dock.hide()
        for name in show:
            dock = self.docks[name]
            if not dock.user_closed:
                dock.show()
        main = self.docks["map" if maps else "viewer"]
        if not main.user_closed:
            main.raise_()
        side = [self.docks[n] for n in (("inspector", "map_tools") if maps else ("details",))
                if n in self.docks and not self.docks[n].isFloating()]
        if side and self.win.isVisible() and side[0].width() < MIN_SIDE:
            self.win.resizeDocks(side[:1], [max(MIN_SIDE, self.win.width() // 5)], Qt.Horizontal)

    def show_panel(self, name: str) -> None:
        """Show and raise one panel (it was asked for: an asset to see, a level opened)."""
        dock = self.docks[name]
        dock.user_closed = False
        dock.show()
        dock.raise_()

    def menu(self) -> QMenu:
        """The *Windows* menu: each panel, put windows back, reset the layout."""
        m = QMenu("Windows", self.win)
        for dock in self.docks.values():
            m.addAction(dock.toggleViewAction())
        m.addSeparator()
        act = QAction("Put every window back", m)
        act.setToolTip("Every panel dragged out as a window of its own goes back into the "
                       "main window")
        act.triggered.connect(self.dock_all)
        m.addAction(act)
        act = QAction("Reset layout", m)
        act.setToolTip("Every panel back where it was when DR2 Studio was new")
        act.triggered.connect(self.arrange)
        m.addAction(act)
        return m

    def dock_all(self) -> None:
        for dock in self.docks.values():
            if dock.isFloating():
                dock.setFloating(False)

    # ---- saved between sessions ---------------------------------------------------------

    @staticmethod
    def _settings() -> QSettings | None:
        if os.environ.get("DR2_STUDIO_NO_LAYOUT"):
            return None
        return QSettings(str(config_dir() / SETTINGS_FILE), QSettings.IniFormat)

    def restore(self) -> bool:
        """The layout of the last session (False: none, or an older layout's)."""
        st = self._settings()
        if st is None or st.value("version") != str(LAYOUT_VERSION):
            return False
        geo, state, stage = st.value("geometry"), st.value("state"), st.value("stage")
        if isinstance(geo, QByteArray):
            self.win.restoreGeometry(geo)
        if not isinstance(state, QByteArray) or not self.win.restoreState(state, LAYOUT_VERSION):
            return False
        if isinstance(stage, QByteArray):
            self.stage.restoreState(stage, LAYOUT_VERSION)
        closed = st.value("closed") or []
        for name in ([closed] if isinstance(closed, str) else closed):
            if name in self.docks:
                self.docks[name].user_closed = True
        self.sizes_pending = False
        self.mode(self.maps, force=True)
        return True

    def save(self) -> None:
        st = self._settings()
        if st is None:
            return
        try:
            config_dir().mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        st.setValue("version", str(LAYOUT_VERSION))
        st.setValue("geometry", self.win.saveGeometry())
        st.setValue("state", self.win.saveState(LAYOUT_VERSION))
        st.setValue("stage", self.stage.saveState(LAYOUT_VERSION))
        st.setValue("closed", [n for n, d in self.docks.items() if d.user_closed])
        st.sync()

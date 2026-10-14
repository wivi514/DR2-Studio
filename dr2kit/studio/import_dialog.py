"""*Other game's items…* and *Other game's levels…*: use a Case West item or level in Case
Zero, or the other way (phase 15). The levels window: `LevelImportDialog`.

The window lists the other game's items that this game lacks (with a filter), shows for the
picked one what the importer would do (`dr2kit.mods.importitem.plan`: what is brought,
renumbered or left out, and why), and **Add to mod** writes it into the open mod
(`importitem.import_item`). Guide: docs/modding/23-other-game.md.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QPlainTextEdit, QPushButton, QSplitter,
                               QVBoxLayout, QWidget)

from ..errors import Dr2Error

NAMES = {"cz": "Case Zero", "cw": "Case West"}


class ImportDialog(QDialog):
    """The window (module docstring). ``main`` is Studio's MainWindow."""

    def __init__(self, main, mod_dir: Path):
        super().__init__(main)
        from ..convert.crossgame import other, source_tree
        from ..mods import importitem
        self.main, self.mod_dir = main, Path(mod_dir)
        self.dst = main.game
        self.src = other(self.dst)
        self.setWindowTitle(f"{NAMES[self.src]}'s items in {NAMES[self.dst]}")
        self.resize(900, 600)
        lay = QVBoxLayout(self)
        try:
            self.src_tree = source_tree(self.src)
        except Dr2Error as e:
            lay.addWidget(QLabel(f"{e}\n\nThis window needs both games' data."))
            self.src_tree = None
            return
        self.dst_tree = main.plain_tree()
        a = importitem._game(self.src, self.src_tree)
        b = importitem._game(self.dst, self.dst_tree)
        self.names = sorted((blk.name for k, blk in a.models.blocks.items()
                             if k not in b.models.blocks), key=str.lower)
        intro = QLabel(f"{len(self.names)} items of {NAMES[self.src]} that {NAMES[self.dst]} "
                       f"doesn't have. Pick one to see what comes with it; <b>Add to mod</b> "
                       f"puts it in <i>{self.mod_dir.name}</i>. The mod is then built from your "
                       f"own copies of both games.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("filter: part of the name (Laser, Sword…)")
        self.filter.textChanged.connect(self._fill)
        self.list = QListWidget()
        self.list.currentTextChanged.connect(self._show)
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.filter)
        ll.addWidget(self.list, 1)
        split = QSplitter(Qt.Horizontal)
        split.addWidget(left)
        split.addWidget(self.report)
        split.setSizes([280, 620])
        lay.addWidget(split, 1)
        row = QHBoxLayout()
        self.status = QLabel()
        row.addWidget(self.status, 1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        self.add_btn = QPushButton("Add to mod")
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self.add)
        row.addWidget(close)
        row.addWidget(self.add_btn)
        lay.addLayout(row)
        self._fill()

    def _fill(self, *_a) -> None:
        words = self.filter.text().lower().split()
        self.list.clear()
        self.list.addItems([n for n in self.names if all(w in n.lower() for w in words)])

    def _show(self, name: str) -> None:
        from ..mods import importitem
        self.add_btn.setEnabled(False)
        if not name:
            self.report.setPlainText("")
            return
        try:
            p = importitem.plan(self.src_tree, self.dst_tree, self.src, self.dst, name)
        except Dr2Error as e:
            self.report.setPlainText(str(e))
            return
        self.report.setPlainText(p.report())
        self.add_btn.setEnabled(not p.unresolved)

    def add(self) -> None:
        """Write the picked item into the mod."""
        from ..mods import importitem
        from ..mods.deploy import recomp_folders
        from ..profiles import locate
        name = self.list.currentItem().text() if self.list.currentItem() else ""
        if not name:
            return
        patched = recomp_folders(locate(self.dst).root)["patched"]
        try:
            p, files = importitem.import_item(self.mod_dir, name, self.src, self.dst,
                                              self.dst_tree,
                                              [patched] if patched.is_dir() else [])
        except Dr2Error as e:
            self.main.error(str(e))
            return
        self.status.setText(f"{name} added ({len(files)} files). Place it from the Maps tab "
                            f"(Add item…).")
        self.main.say(f"{self.mod_dir.name}: {', '.join(p.items)} from {NAMES[self.src]}")
        if hasattr(self.main, "_refresh_mod"):
            self.main._refresh_mod()


class _Prebuild(QThread):
    """Builds a brought level's zones in the background (`importlevel.prebuild`)."""
    step = Signal(int, int, str)
    finished_ok = Signal(int)
    failed = Signal(str)

    def __init__(self, mod_dir: Path, tree):
        super().__init__()
        self.mod_dir, self.tree = mod_dir, tree

    def run(self) -> None:
        from ..mods import importlevel
        try:
            n = importlevel.prebuild(self.mod_dir, self.tree, workers=1,
                                     progress=lambda d, t, f: self.step.emit(d, t, f))
            self.finished_ok.emit(n)
        except Exception as e:                          # noqa: BLE001 - shown to the user
            self.failed.emit(str(e))


class LevelImportDialog(QDialog):
    """*Other game's levels…* (phase 15 maps): a whole level of the other game into a free
    level slot of this one, with a door to it (`dr2kit.mods.importlevel`). Lists the other
    game's levels, the free slots (`crossgame.free_level_slots`), the entry door's place
    (the profile's ``level_door`` by default), shows the importer's report, and **Add to
    mod** writes it, then builds the zones in the background (minutes, once: cached).
    Guide: docs/modding/23-other-game.md §A whole level."""

    def __init__(self, main, mod_dir: Path):
        super().__init__(main)
        from ..convert import crossgame
        from ..mods import importlevel
        from ..profiles import load_profile
        self.main, self.mod_dir = main, Path(mod_dir)
        self.dst = main.game
        self.src = crossgame.other(self.dst)
        self.setWindowTitle(f"{NAMES[self.src]}'s levels in {NAMES[self.dst]}")
        self.resize(950, 640)
        lay = QVBoxLayout(self)
        try:
            self.src_tree = crossgame.source_tree(self.src)
        except Dr2Error as e:
            lay.addWidget(QLabel(f"{e}\n\nThis window needs both games' data."))
            self.src_tree = None
            return
        self.dst_tree = main.plain_tree()
        self.thread = None
        taken = tuple(importlevel.mod_levels(self.mod_dir))
        levels = [s for s in crossgame.level_slot_list(self.src) if s.shipped
                  and "menu" not in s.script and not s.script.startswith("cine_")]
        self.free = crossgame.free_level_slots(self.dst, taken)
        intro = QLabel(
            f"A whole level of {NAMES[self.src]}: its buildings, items, zombies and doors, "
            f"into a free level slot of {NAMES[self.dst]}, with a door to it. Its zombies "
            f"come in a <b>new game</b>, and a save made with the mod needs it. The mod is "
            f"built from your own copies of both games; the first build of a level takes "
            f"a few minutes (then it is kept).")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        form = QHBoxLayout()
        self.level = QComboBox()
        for s in levels:
            self.level.addItem(s.script, s.level)
        self.slot = QComboBox()
        for s in self.free:
            self.slot.addItem(f"{s.level}  ({s.script}.txt)", s.level)
        door = load_profile(self.dst).level_door
        self.door = QLineEdit(door.get("location", ""))
        self.door.setToolTip(f"x,y,z of the entry door in {door.get('level', '?')}; Maps "
                             f"tab: right-click the floor, Copy position")
        for label, w in (("Level", self.level), ("Slot", self.slot),
                         (f"Door in {door.get('level', '?')}", self.door)):
            form.addWidget(QLabel(label))
            form.addWidget(w, 1)
        lay.addLayout(form)
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        lay.addWidget(self.report, 1)
        row = QHBoxLayout()
        self.status = QLabel()
        row.addWidget(self.status, 1)
        show = QPushButton("Show what it does")
        show.clicked.connect(self._show)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        self.add_btn = QPushButton("Add to mod")
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self.add)
        for b in (show, close, self.add_btn):
            row.addWidget(b)
        lay.addLayout(row)
        if not self.free:
            self.status.setText(f"{NAMES[self.dst]} has no free level slot left.")
            show.setEnabled(False)
        self.level.currentIndexChanged.connect(lambda *_: self.add_btn.setEnabled(False))
        self.slot.currentIndexChanged.connect(lambda *_: self.add_btn.setEnabled(False))

    def _show(self) -> None:
        from ..mods import importlevel
        self.add_btn.setEnabled(False)
        try:
            p = importlevel.plan(self.src_tree, self.dst_tree, self.src, self.dst,
                                 self.level.currentData(), self.slot.currentData(),
                                 self.door.text().strip() or None,
                                 taken_slots=tuple(importlevel.mod_levels(self.mod_dir)))
        except Dr2Error as e:
            self.report.setPlainText(str(e))
            return
        self.report.setPlainText(p.report())
        self.add_btn.setEnabled(not p.unresolved)

    def add(self) -> None:
        """Write the level into the mod, then build its zones in the background."""
        from ..mods import importlevel
        from ..mods.deploy import recomp_folders
        from ..profiles import locate
        patched = recomp_folders(locate(self.dst).root)["patched"]
        self.add_btn.setEnabled(False)
        self.status.setText("Writing the level into the mod (a minute or two)…")
        QApplication.processEvents()
        try:
            p, files = importlevel.import_level(self.mod_dir, self.level.currentData(),
                                                self.src, self.dst, self.dst_tree,
                                                self.slot.currentData(),
                                                self.door.text().strip() or None,
                                                [patched] if patched.is_dir() else [])
        except Dr2Error as e:
            self.main.error(str(e))
            self.status.setText("")
            return
        self.report.setPlainText(p.report())
        self.main.say(f"{self.mod_dir.name}: {p.level.script} from {NAMES[self.src]} in "
                      f"{p.slot.level}")
        if hasattr(self.main, "_refresh_mod"):
            self.main._refresh_mod()
        self.thread = _Prebuild(self.mod_dir, self.dst_tree)
        self.thread.step.connect(lambda d, t, f: self.status.setText(
            f"Building the zones: {d}/{t} ({f})…"))
        self.thread.finished_ok.connect(lambda n: self.status.setText(
            f"Done: {len(files)} files, {n} zones built. Go through the door to reach it "
            f"(Play)."))
        self.thread.failed.connect(lambda e: self.status.setText(f"Building failed: {e}"))
        self.thread.start()

    def reject(self) -> None:
        if self.thread is not None and self.thread.isRunning():
            self.status.setText("Still building the zones: wait for it (or Play builds "
                                "them, slower).")
            return
        super().reject()

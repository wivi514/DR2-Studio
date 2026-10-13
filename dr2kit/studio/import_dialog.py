"""*Other game's items…*: use a Case West item in Case Zero, or the other way (phase 15).

The window lists the other game's items that this game lacks (with a filter), shows for the
picked one what the importer would do (`dr2kit.mods.importitem.plan`: what is brought,
renumbered or left out, and why), and **Add to mod** writes it into the open mod
(`importitem.import_item`). Guide: docs/modding/23-other-game.md.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget)

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

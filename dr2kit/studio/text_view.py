"""DR2 Studio's text views: edit a text file into a mod, with a diff; edit strings.

Two widgets, both "edit here, the change goes into the open mod":

* `TextEditor`, for the game's text files (mission and data scripts in ``datafile.big``,
  ``.csv`` tables, layouts, ``.sfx``). The text is editable when a mod is open; *Save to
  mod* writes the whole file to ``replace/<vpath>`` (a raw override, re-compressed by the
  build if the entry was compressed), *Changes* shows a coloured diff against the game's
  text, *Revert* drops the mod's copy. Files the game checks against a digest
  (``digest_checked`` in the game profile) open read-only, with the reason.
  Bytes ↔ text is Latin-1, which keeps every byte as it is, and line ends are written
  back as the original had them (``\\r\\n`` or ``\\n``).
* `StringsViewer`, for a string bank (``str_en.bcs``): a filterable table of id, label
  and text. Editing a text cell changes that string in the open mod
  (``replace/…/str_<lang>.bcs.json``, `dr2kit.convert.strings.set_mod_strings`); changed
  rows are highlighted, *Revert string* removes the change. Notes about markup and
  ``%`` placeholders appear under the table (`dr2kit.formats.bcs.apply`).

Both get their data and a ``save`` callback from the main window; they hold no format
knowledge.
"""

from __future__ import annotations

import difflib
import html

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QStackedWidget, QTableWidget, QTableWidgetItem, QTextBrowser,
                               QVBoxLayout, QWidget, QHeaderView, QAbstractItemView)

from ..formats import bcs


def _mono() -> QFont:
    f = QFont("monospace")
    f.setStyleHint(QFont.Monospace)
    return f


def diff_html(old: str, new: str, name: str) -> str:
    """A unified diff of two texts as coloured HTML (empty diff → a sentence)."""
    lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(),
                                      f"game: {name}", f"mod: {name}", lineterm="", n=3))
    if not lines:
        return "<p>No changes: the text is the game's.</p>"
    out = []
    for ln in lines:
        colour = ("#1a7f37" if ln.startswith("+") else "#cf222e" if ln.startswith("-")
                  else "#8250df" if ln.startswith("@@") else None)
        text = html.escape(ln)
        out.append(f'<span style="color:{colour}">{text}</span>' if colour else text)
    return "<pre>" + "\n".join(out) + "</pre>"


class TextEditor(QWidget):
    """Edit one text asset into the open mod. ``load(...)`` shows it."""

    def __init__(self):
        super().__init__()
        self.vpath = ""
        self.original = ""
        self.newline = "\n"
        self.save_cb = None
        self.revert_cb = None
        self.title = QLabel()
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.edit = QPlainTextEdit()
        self.edit.setFont(_mono())
        self.edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.diff = QTextBrowser()
        self.diff.setFont(_mono())
        self.stack = QStackedWidget()
        self.stack.addWidget(self.edit)
        self.stack.addWidget(self.diff)
        self.btn_save = QPushButton("Save to mod")
        self.btn_diff = QPushButton("Changes")
        self.btn_diff.setCheckable(True)
        self.btn_revert = QPushButton("Revert to the game's")
        bar = QHBoxLayout()
        bar.addWidget(self.title, 1)
        for b in (self.btn_diff, self.btn_revert, self.btn_save):
            bar.addWidget(b)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addLayout(bar)
        lay.addWidget(self.stack, 1)
        lay.addWidget(self.status)
        self.btn_save.clicked.connect(self.save)
        self.btn_revert.clicked.connect(self.revert)
        self.btn_diff.toggled.connect(self._show_diff)
        self.edit.textChanged.connect(self._changed)

    def load(self, vpath: str, original: bytes, current: bytes | None, *, editable: bool,
             reason: str = "", save=None, revert=None) -> None:
        """Show ``vpath``: the game's bytes, the mod's copy (``current``) if it has one.
        ``save(bytes)`` / ``revert()`` are called by the buttons."""
        self.vpath, self.save_cb, self.revert_cb = vpath, save, revert
        self.original = original.decode("latin-1")
        self.newline = "\r\n" if original.count(b"\r\n") * 2 > original.count(b"\n") else "\n"
        text = (current if current is not None else original).decode("latin-1")
        self.edit.blockSignals(True)
        self.edit.setPlainText(text)
        self.edit.blockSignals(False)
        self.edit.setReadOnly(not editable)
        self.btn_diff.setChecked(False)
        self.title.setText(f"<b>{vpath.rsplit('/', 1)[-1]}</b>"
                           + ("  (changed by the open mod)" if current is not None else ""))
        self.status.setText(reason)
        self._editable = editable
        self._changed()

    def text_bytes(self) -> bytes:
        """The editor's text as the bytes a mod file holds."""
        return self.edit.toPlainText().replace("\n", self.newline).encode("latin-1", "replace")

    def is_changed(self) -> bool:
        return self.edit.toPlainText() != self.original.replace("\r\n", "\n")

    def save(self) -> None:
        if self.save_cb:
            self.save_cb(self.text_bytes())

    def revert(self) -> None:
        if self.revert_cb:
            self.revert_cb()

    def _show_diff(self, on: bool) -> None:
        if on:
            self.diff.setHtml(diff_html(self.original.replace("\r\n", "\n"),
                                        self.edit.toPlainText(), self.vpath))
        self.stack.setCurrentWidget(self.diff if on else self.edit)

    def _changed(self) -> None:
        editable = getattr(self, "_editable", False)
        self.btn_save.setEnabled(editable)
        self.btn_revert.setEnabled(editable and self.revert_cb is not None)


class StringsViewer(QWidget):
    """A string bank as a table; edits go into the open mod through ``set_cb``."""

    COLS = ("id", "label", "text")

    def __init__(self):
        super().__init__()
        self.bank: bcs.StringBank | None = None
        self.labels: dict[int, str] = {}
        self.changes: dict[int, str] = {}
        self.set_cb = None
        self.title = QLabel()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("filter: text, label or id")
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["id", "label", "text"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.btn_revert = QPushButton("Revert string")
        self.notes = QLabel()
        self.notes.setWordWrap(True)
        top = QHBoxLayout()
        top.addWidget(self.title, 1)
        top.addWidget(self.filter, 1)
        top.addWidget(self.btn_revert)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addLayout(top)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.notes)
        self.filter.textChanged.connect(self._filter)
        self.table.itemChanged.connect(self._edited)
        self.btn_revert.clicked.connect(self._revert)

    def load(self, title: str, bank: bcs.StringBank, labels: dict[int, str],
             changes: dict[int, str], editable: bool, set_cb=None) -> None:
        """Show ``bank``; ``changes`` are the open mod's (id → text); ``set_cb(id, text
        or None)`` stores an edit and returns notes."""
        self.bank, self.labels, self.changes, self.set_cb = bank, labels, dict(changes), set_cb
        self.title.setText(f"<b>{title}</b>  {len(bank.strings):,} strings"
                           + (f", {len(changes)} changed by the open mod" if changes else "")
                           + ("" if editable else "  (open a mod to edit)"))
        self.notes.setText("Double-click a text to change it. Markup: [RRGGBBAA,text] "
                           "colours, [@icon] draws an icon; a string using either must "
                           "start with @. Keep %s / %d placeholders." if editable else "")
        self._editable = editable
        self.btn_revert.setEnabled(editable)
        self.table.blockSignals(True)
        self.table.setRowCount(len(bank.strings))
        for row, (i, text) in enumerate(bank.strings.items()):
            a = QTableWidgetItem()
            a.setData(Qt.DisplayRole, i)
            b = QTableWidgetItem(labels.get(i, ""))
            c = QTableWidgetItem(self.changes.get(i, text))
            for it in (a, b):
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if not editable:
                c.setFlags(c.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, a)
            self.table.setItem(row, 1, b)
            self.table.setItem(row, 2, c)
            self._mark(row, i)
        self.table.blockSignals(False)
        self.table.resizeColumnToContents(0)
        self.table.setColumnWidth(1, 260)
        self._filter(self.filter.text())

    def _mark(self, row: int, i: int) -> None:
        item = self.table.item(row, 2)
        changed = i in self.changes
        item.setBackground(QBrush(QColor(255, 236, 179)) if changed else QBrush())
        item.setToolTip(f"game's text: {self.bank.strings[i]}" if changed else "")

    def _filter(self, text: str) -> None:
        needle = text.lower().strip()
        for row in range(self.table.rowCount()):
            hit = not needle or any(needle in (self.table.item(row, c).text().lower())
                                    for c in range(3))
            self.table.setRowHidden(row, not hit)

    def _edited(self, item) -> None:
        if item.column() != 2 or not self.set_cb:
            return
        row = item.row()
        i = int(self.table.item(row, 0).data(Qt.DisplayRole))
        text = item.text()
        new = None if text == self.bank.strings[i] else text
        notes = self.set_cb(i, new) or []
        if new is None:
            self.changes.pop(i, None)
        else:
            self.changes[i] = new
        self.table.blockSignals(True)
        self._mark(row, i)
        self.table.blockSignals(False)
        self.notes.setText("\n".join(notes) if notes else f"id {i}: saved in the mod.")

    def _revert(self) -> None:
        rows = {ix.row() for ix in self.table.selectedIndexes()}
        for row in rows:
            i = int(self.table.item(row, 0).data(Qt.DisplayRole))
            if i in self.changes:
                self.table.item(row, 2).setText(self.bank.strings[i])   # → _edited

"""DR2 Studio's help window: the modding guides, inside the app.

The pages are the modding guides themselves (`dr2kit.help`): a list of topics in
reading order on the left, a search box over every line of every guide, and the page
rendered on the right (Qt renders Markdown: headings, tables, code). Links between
guides open in the window (``#section`` links scroll there), links to the glossary too;
web links open in the browser; links to developer docs open the file when the toolkit's
source is there, and otherwise say where to find it. *Back* returns to the previous
page. `HelpWindow.show_page(name, section)` is how the rest of Studio points at help
(the "How to mod this" box, error messages, the welcome window).
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QTextDocument
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QSplitter, QTextBrowser, QVBoxLayout, QWidget)

from .. import help as dhelp

ROLE_PAGE = Qt.UserRole + 1
ROLE_SECTION = Qt.UserRole + 2


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation dropped, spaces → -."""
    s = re.sub(r"[`*_]", "", heading.strip().lower())
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")


class HelpWindow(QWidget):
    """The help: ``show_page("11-text.md", "rules-for-a-string")``."""

    def __init__(self, parent=None, lang: str = dhelp.DEFAULT_LANG):
        super().__init__(parent, Qt.Window)
        self.lang = lang
        self.setWindowTitle("DR2 Studio help")
        self.resize(1100, 760)
        self.history: list[tuple[str, str]] = []
        self.current = ("", "")
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("search the help (e.g. digest, colour, dr2mod)")
        self.list = QListWidget()
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(self._link)
        self.back = QPushButton("Back")
        self.back.clicked.connect(self.go_back)
        self.where = QLabel()
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.search_box)
        ll.addWidget(self.list, 1)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.addWidget(self.back)
        top.addWidget(self.where, 1)
        rl.addLayout(top)
        rl.addWidget(self.view, 1)
        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([380, 720])
        self.list.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addWidget(split)
        self.search_box.textChanged.connect(self._search)
        self.list.currentItemChanged.connect(self._picked)
        self._fill_topics()
        self.show_page("README.md")

    def _fill_topics(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for t in dhelp.topics(self.lang):
            it = QListWidgetItem(t.title)
            it.setData(ROLE_PAGE, t.name)
            it.setData(ROLE_SECTION, "")
            self.list.addItem(it)
        self.list.blockSignals(False)

    def _search(self, text: str) -> None:
        if not text.strip():
            self._fill_topics()
            return
        self.list.blockSignals(True)
        self.list.clear()
        hits = dhelp.search(text, self.lang)
        for h in hits:
            it = QListWidgetItem(f"{h.topic.title} › {h.heading}\n    {h.line}")
            it.setData(ROLE_PAGE, h.topic.name)
            it.setData(ROLE_SECTION, slug(h.heading) if h.heading != h.topic.title else "")
            it.setToolTip(h.line)
            self.list.addItem(it)
        if not hits:
            self.list.addItem(QListWidgetItem("Nothing found: try fewer or other words."))
        self.list.blockSignals(False)

    def _picked(self, item) -> None:
        if item is not None and item.data(ROLE_PAGE):
            self.show_page(item.data(ROLE_PAGE), item.data(ROLE_SECTION) or "",
                           highlight=self.search_box.text().strip())

    def show_page(self, name: str, section: str = "", remember: bool = True,
                  highlight: str = "") -> None:
        """Show page ``name``, scrolled to the heading whose anchor is ``section``."""
        try:
            text = dhelp.read(name, self.lang)
        except FileNotFoundError:
            self.view.setMarkdown(f"# Not found\n\nNo help page `{name}`.")
            return
        if remember and self.current[0]:
            self.history.append(self.current)
        self.current = (name, section)
        self.back.setEnabled(bool(self.history))
        self.view.document().setMarkdown(text, QTextDocument.MarkdownDialectGitHub)
        self.where.setText(f"<b>{dhelp.title_of(dhelp.page_path(name, self.lang))}</b>")
        self.show()
        self.raise_()
        self.view.moveCursor(self.view.textCursor().MoveOperation.Start)
        if section:
            heading = next((ln.lstrip("#").strip() for ln in text.splitlines()
                            if ln.startswith("#") and slug(ln.lstrip("#")) == section), "")
            if heading and self.view.find(re.sub(r"[`*]", "", heading)):
                self._to_top()
        elif highlight and self.view.find(highlight.split()[0]):
            self._to_top()

    def _to_top(self) -> None:
        """Scroll so the found text is at the top of the view, not at its bottom edge."""
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.view.ensureCursorVisible()

    def go_back(self) -> None:
        if self.history:
            name, section = self.history.pop()
            self.show_page(name, section, remember=False)

    def _link(self, url: QUrl) -> None:
        if url.scheme() in ("http", "https", "mailto"):
            QDesktopServices.openUrl(url)
            return
        target = url.path() or self.current[0]
        section = url.fragment()
        name = Path(target).name
        if target.startswith("../") and name == "glossary.md":
            target = name
        if "/" not in target and dhelp.page_path(name, self.lang):
            self.show_page(name, section)
            return
        # A developer doc (../formats.md, ../dev/…): open it if the source is here.
        here = dhelp.page_path(self.current[0], self.lang)
        path = (here.parent / target).resolve() if here else None
        if path is not None and path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self.where.setText(f"<i>{target} is developer documentation: it is in the "
                               f"toolkit's source code (docs/), not in the app.</i>")

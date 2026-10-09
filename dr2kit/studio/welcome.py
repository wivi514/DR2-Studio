"""DR2 Studio's welcome window: the first steps as a live checklist.

Shown at start (until *Show this at start* is unticked, saved as ``[studio] welcome =
"off"``) and from **Help → Welcome**. Each step has a button that does it and turns into
✔ when it is done, so a newcomer always sees what to do next:

1. tell Studio where the games are (*Game folders…*);
2. build the index for the chosen game;
3. start a mod (*New mod…*);
4. change something (the first-mod guide, texture editing);
5. *Play* (deploys and starts the recomp).

The checks read the same state the rest of Studio uses (game locations, the index, the
open mod, ``game_mods/``); *Refresh* happens whenever the window is shown or a step's
button is clicked.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QCheckBox, QDialog, QGridLayout, QLabel, QPushButton,
                               QVBoxLayout)

from ..errors import Dr2Error
from ..profiles import GAME_IDS, get_config, set_config


def show_at_start() -> bool:
    return get_config("studio", "welcome") != "off"


class Welcome(QDialog):
    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.setWindowTitle("Welcome to DR2 Studio")
        self.resize(640, 380)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "<h2>Welcome to DR2 Studio</h2>Mod Dead Rising 2: Case Zero and Case West. "
            "Five steps to your first mod in the game; each button does its step. "
            "Press <b>F1</b> any time for the help."))
        grid = QGridLayout()
        self.marks: list[QLabel] = []
        steps = [
            ("Tell DR2 Studio where your games are", "Game folders…", main.open_game_setup),
            ("Build the index of the game chosen in the toolbar (a minute or two)",
             "Build index", main.build_index),
            ("Start a mod: a folder for your changes", "New mod…", main.new_mod),
            ("Change something: pick a texture and click Edit in image editor… "
             "(the guide shows every step)", "Open the guide",
             lambda: main.open_help("05-first-mod-texture.md")),
            ("Play: your mods go into the game and it starts", "▶ Play", main.play),
        ]
        for i, (text, button, action) in enumerate(steps):
            mark = QLabel()
            label = QLabel(f"<b>{i + 1}.</b> {text}")
            label.setWordWrap(True)
            btn = QPushButton(button)
            btn.clicked.connect(lambda _c=False, a=action: (a(), QTimer.singleShot(500, self.refresh)))
            grid.addWidget(mark, i, 0)
            grid.addWidget(label, i, 1)
            grid.addWidget(btn, i, 2)
            self.marks.append(mark)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        self.again = QCheckBox("Show this at start")
        self.again.setChecked(show_at_start())
        self.again.toggled.connect(lambda on: set_config("studio", "welcome", None if on else "off"))
        lay.addWidget(self.again)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        lay.addWidget(close)
        self.refresh()

    def status(self) -> list[bool]:
        """Which of the five steps are done."""
        from ..index import query
        from ..mods.manifest import Mod
        from ..mods.play import deployed
        from .setup_dialog import game_status
        m = self.main
        games = any(game_status(g)[0] for g in GAME_IDS)
        indexed = bool(query.files(m.con, m.game))
        has_mod = m.mod_dir is not None
        try:
            changed = has_mod and bool(Mod.load(m.mod_dir).files())
        except Dr2Error:
            changed = False
        try:
            played = bool(deployed(m.game).files)
        except Dr2Error:
            played = False
        return [games, indexed, has_mod, changed, played]

    def refresh(self) -> None:
        for mark, done in zip(self.marks, self.status()):
            mark.setText("✔" if done else "○")

    def showEvent(self, ev):
        self.refresh()
        super().showEvent(ev)

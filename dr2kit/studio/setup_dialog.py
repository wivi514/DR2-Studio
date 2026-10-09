"""DR2 Studio's *Game folders…* window: tell the toolkit where each game's data is.

A recomp next to a git checkout of the toolkit is found by itself; a DR2 Studio
release, or a toolkit installed with pip, has to be told. The window shows, per game,
where the data was found (and how: a setting, an environment variable, a recomp next to
the checkout) and offers the two ways the CLI has (docs/modding/02-game-data.md):

* **Choose folder…**: a folder that contains ``data/`` (a recomp's ``assets/game``, or
  a folder unpacked earlier), saved with `dr2kit.profiles.set_game_root` (the same
  setting as ``dr2 games set``);
* **Unpack package…**: the game's XBLA package file (from a console or your own
  backup) is unpacked into a folder you pick (`dr2kit.container.stfs.unpack`, the same
  as ``dr2 unpack``), in a background job, and that folder is then saved as above.

The main window opens it at start when no game is found.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QDialog, QFileDialog, QGridLayout, QLabel, QMessageBox,
                               QPushButton, QVBoxLayout)

from ..errors import Dr2Error
from ..profiles import GAME_IDS, load_profile, locate, set_game_root


def game_status(game: str) -> tuple[bool, str]:
    """(found, one line saying where or why not) for ``game``."""
    try:
        loc = locate(game)
        how = {"config": "your setting", "environment": "an environment variable",
               "recomp": "a recomp next to the toolkit"}.get(loc.how, loc.how)
        return True, f"{loc.root}  (from {how})"
    except Dr2Error:
        return False, "not found"


class GameSetup(QDialog):
    """The game folders window. ``main`` is the `MainWindow` (jobs, log, refresh)."""

    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.setWindowTitle("Game folders")
        self.resize(820, 260)
        grid = QGridLayout()
        self.status: dict[str, QLabel] = {}
        for row, g in enumerate(GAME_IDS):
            name = QLabel(f"<b>{load_profile(g).name}</b>")
            st = QLabel()
            st.setWordWrap(True)
            choose = QPushButton("Choose folder…")
            unpack = QPushButton("Unpack package…")
            choose.clicked.connect(lambda _c=False, game=g: self.choose(game))
            unpack.clicked.connect(lambda _c=False, game=g: self.unpack(game))
            grid.addWidget(name, row, 0)
            grid.addWidget(st, row, 1)
            grid.addWidget(choose, row, 2)
            grid.addWidget(unpack, row, 3)
            self.status[g] = st
        grid.setColumnStretch(1, 1)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "Point DR2 Studio at each game's data: a folder that contains <i>data/</i> "
            "(a recomp's <i>assets/game</i>, or a folder you unpacked before), or unpack "
            "the game's Xbox 360 package file. You need your own copy of the games."))
        lay.addLayout(grid)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        lay.addWidget(close)
        self.refresh()

    def refresh(self) -> None:
        for g, label in self.status.items():
            ok, text = game_status(g)
            label.setText(("✔ " if ok else "✘ ") + text)

    def choose(self, game: str) -> None:
        d = QFileDialog.getExistingDirectory(self, f"{load_profile(game).name}: the folder "
                                                   f"that contains data/")
        if not d:
            return
        try:
            root = set_game_root(game, d)
        except Dr2Error as e:
            QMessageBox.warning(self, "Game folders", str(e))
            return
        self.main.say(f"{game}: using {root}")
        self._changed(game)

    def unpack(self, game: str) -> None:
        pkg, _ = QFileDialog.getOpenFileName(
            self, f"{load_profile(game).name}: the XBLA package file "
                  f"(in {load_profile(game).title_id}/000D0000/)")
        if not pkg:
            return
        out = QFileDialog.getExistingDirectory(self, "An empty folder to unpack into")
        if not out:
            return

        def work(progress):
            from ..container.stfs import unpack
            n, size = unpack(pkg, out, progress=lambda name, _s: progress(f"  {name}"))
            return set_game_root(game, out), n, size

        def done(result, err):
            if err:
                self.main.error(err)
                return
            root, n, size = result
            self.main.say(f"{game}: unpacked {n} files ({size / 1e6:.0f} MB); using {root}")
            self._changed(game)
        self.main.say(f"unpacking {Path(pkg).name} into {out}…")
        self.main.run_job(work, done)

    def _changed(self, game: str) -> None:
        self.refresh()
        self.main.trees.pop(game, None)
        if game == self.main.game:
            self.main.set_game(game)
        self.main.say("Next: Build / refresh index (once per game).")

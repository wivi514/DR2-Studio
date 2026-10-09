"""DR2 Studio's mod manager window: the mod library, its load order, conflicts, deploy.

The same library as ``dr2 mod list/install/enable/move/deploy``
(`dr2kit.mods.library.ModLibrary`): a folder of mods and a ``modlist.toml``. The window
lists the mods in load order, **later mods win** (the list's bottom has the highest
priority). Tick a mod to switch it on; *Up* / *Down* move it; *Install folder…* /
*Install .zip…* copy a mod in; *Pack .zip…* makes a zip to share; *Edit in Studio* opens
the mod in the main window's mod bar, so new overrides go into it. *Conflicts* lists, for
the game chosen in the main window, every asset or string two switched-on mods both
replace and which one wins; *Deploy* builds every switched-on mod for that game into the
recomp's ``game_mods/`` (on top of ``game_patched``, like ``dr2 mod deploy``).

Building runs through the main window's job runner, so the window stays responsive.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
                               QVBoxLayout)

from ..errors import Dr2Error
from ..mods.library import ModLibrary, default_library, pack, set_default_library


class ModManager(QDialog):
    """The mod library window. ``main`` is the `MainWindow` (game, jobs, log, mod bar)."""

    def __init__(self, main, folder: Path | None = None):
        super().__init__(main)
        self.main = main
        self.setWindowTitle("Mod manager")
        self.resize(760, 560)
        self.lib = ModLibrary(folder)
        self.where = QLabel()
        self.where.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.list = QListWidget()
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setMaximumHeight(150)
        b = {name: QPushButton(name) for name in (
            "Install folder…", "Install .zip…", "Remove", "Up", "Down", "Edit in Studio",
            "Pack .zip…", "Conflicts", "Deploy", "Library folder…")}
        self.buttons = b
        b["Install folder…"].clicked.connect(lambda: self._install(folder=True))
        b["Install .zip…"].clicked.connect(lambda: self._install(folder=False))
        b["Remove"].clicked.connect(self._remove)
        b["Up"].clicked.connect(lambda: self._move("down"))      # up the list = earlier
        b["Down"].clicked.connect(lambda: self._move("up"))
        b["Edit in Studio"].clicked.connect(self._edit)
        b["Pack .zip…"].clicked.connect(self._pack)
        b["Conflicts"].clicked.connect(self.conflicts)
        b["Deploy"].clicked.connect(self.deploy)
        b["Library folder…"].clicked.connect(self._change_folder)
        self.list.itemChanged.connect(self._toggled)
        row1, row2 = QHBoxLayout(), QHBoxLayout()
        for name in ("Install folder…", "Install .zip…", "Remove", "Up", "Down"):
            row1.addWidget(b[name])
        for name in ("Edit in Studio", "Pack .zip…", "Conflicts", "Deploy",
                     "Library folder…"):
            row2.addWidget(b[name])
        lay = QVBoxLayout(self)
        lay.addWidget(self.where)
        lay.addWidget(QLabel("Tick a mod to switch it on. Later mods (lower in the list) "
                             "win when two replace the same thing."))
        lay.addWidget(self.list, 1)
        lay.addLayout(row1)
        lay.addLayout(row2)
        lay.addWidget(self.report)
        self.refresh()

    # ---- list -------------------------------------------------------------------------

    def refresh(self, select: str | None = None) -> None:
        self.where.setText(f"Library: {self.lib.folder}")
        self.list.blockSignals(True)
        self.list.clear()
        try:
            entries = self.lib.entries()
        except Dr2Error as e:
            self.report.setPlainText(str(e))
            entries = []
        for e in entries:
            files = len(e.mod.files())
            it = QListWidgetItem(f"{e.position + 1}. {e.mod.name}  ({e.mod.id} "
                                 f"{e.mod.version}, {'/'.join(e.mod.games)}, {files} "
                                 f"file{'s' if files != 1 else ''})"
                                 + ("  — new, not on yet" if e.new else ""))
            it.setData(Qt.UserRole, e.mod.id)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if e.enabled else Qt.Unchecked)
            it.setToolTip(e.mod.description or str(e.mod.root))
            self.list.addItem(it)
            if e.mod.id == select:
                self.list.setCurrentItem(it)
        self.list.blockSignals(False)

    def _selected(self) -> str | None:
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _do(self, fn, *args, select=None) -> None:
        try:
            out = fn(*args)
        except Dr2Error as e:
            QMessageBox.warning(self, "Mod manager", str(e))
            return
        self.refresh(select)
        return out

    def _toggled(self, item) -> None:
        self._do(self.lib.enable, item.data(Qt.UserRole), item.checkState() == Qt.Checked,
                 select=item.data(Qt.UserRole))

    def _move(self, where: str) -> None:
        mid = self._selected()
        if mid:
            self._do(self.lib.move, mid, where, select=mid)

    def _install(self, folder: bool) -> None:
        if folder:
            src = QFileDialog.getExistingDirectory(self, "Mod folder to install (with mod.toml)")
        else:
            src, _ = QFileDialog.getOpenFileName(self, "Mod .zip to install", "", "Zip (*.zip)")
        if not src:
            return
        try:
            mod = self.lib.install(src)
        except Dr2Error as e:
            if "already installed" not in str(e):
                QMessageBox.warning(self, "Mod manager", str(e))
                return
            if QMessageBox.question(self, "Mod manager", f"{e}\n\nUpdate it?") != QMessageBox.Yes:
                return
            mod = self._do(self.lib.install, src, True)
            if mod is None:
                return
        self.main.say(f"installed {mod.id} {mod.version} into {self.lib.folder}")
        self.refresh(mod.id)

    def _remove(self) -> None:
        mid = self._selected()
        if mid and QMessageBox.question(
                self, "Mod manager", f"Delete {mid} from the library folder?") == QMessageBox.Yes:
            self._do(self.lib.remove, mid)

    def _edit(self) -> None:
        mid = self._selected()
        if mid:
            self.main._set_mod(self.lib.get(mid).mod.root)

    def _pack(self) -> None:
        mid = self._selected()
        if not mid:
            return
        mod = self.lib.get(mid).mod
        dest, _ = QFileDialog.getSaveFileName(self, "Save mod as", f"{mod.id}-{mod.version}.zip",
                                              "Zip (*.zip)")
        if dest:
            out = self._do(pack, mod.root, dest, select=mid)
            if out:
                self.main.say(f"packed {mid} into {out}")

    def _change_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Mod library folder", str(default_library()))
        if d:
            set_default_library(d)
            self.lib = ModLibrary(d)
            self.refresh()

    # ---- jobs -------------------------------------------------------------------------

    def conflicts(self) -> None:
        game, lib = self.main.game, self.lib

        def work(progress):
            from ..container.vpath import AssetTree
            from ..profiles import locate
            return lib.plan(game, AssetTree(locate(game).root))

        def done(plan, err):
            if err:
                self.report.setPlainText(err)
                return
            lines = [f"{game}: {len(plan.planned)} overrides from "
                     f"{len({p.mod.id for p in plan.planned})} mods"]
            lines += [f"{what}: {won} wins over {lost}" for what, lost, won in plan.shadowed]
            lines += [f"note: {n}" for n in plan.notes]
            if not plan.shadowed:
                lines.append("No conflicts.")
            self.report.setPlainText("\n".join(lines))
        self.report.setPlainText(f"checking the switched-on mods against {game}…")
        self.main.run_job(work, done)

    def deploy(self) -> None:
        mods = self.lib.active(self.main.game)
        if not mods:
            QMessageBox.information(self, "Mod manager",
                                    f"No switched-on mod is for {self.main.game}.")
            return
        self.report.setPlainText(f"building {', '.join(m.id for m in mods)} for "
                                 f"{self.main.game}…")
        self.main.deploy_mods(mods, report=self.report.appendPlainText)

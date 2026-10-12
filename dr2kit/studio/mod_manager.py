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
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
                               QPushButton, QTextBrowser, QVBoxLayout)

from ..errors import Dr2Error
from ..mods.library import ModLibrary, default_library, set_default_library


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
            "Install folder…", "Install mod file…", "Link folder…", "Remove", "Up", "Down",
            "Edit in Studio", "Share…", "Conflicts", "Deploy", "Library folder…")}
        self.buttons = b
        b["Install folder…"].clicked.connect(lambda: self._install(folder=True))
        b["Install mod file…"].clicked.connect(lambda: self._install(folder=False))
        b["Link folder…"].setToolTip("Add a mod folder that stays where it is (a mod you "
                                     "are making)")
        b["Link folder…"].clicked.connect(self._link)
        b["Remove"].clicked.connect(self._remove)
        b["Up"].clicked.connect(lambda: self._move("down"))      # up the list = earlier
        b["Down"].clicked.connect(lambda: self._move("up"))
        b["Edit in Studio"].clicked.connect(self._edit)
        b["Share…"].clicked.connect(self._share)
        b["Conflicts"].clicked.connect(self.conflicts)
        b["Deploy"].clicked.connect(self.deploy)
        b["Library folder…"].clicked.connect(self._change_folder)
        self.list.itemChanged.connect(self._toggled)
        row1, row2 = QHBoxLayout(), QHBoxLayout()
        for name in ("Install mod file…", "Install folder…", "Link folder…", "Remove", "Up",
                     "Down"):
            row1.addWidget(b[name])
        for name in ("Edit in Studio", "Share…", "Conflicts", "Deploy", "Library folder…"):
            row2.addWidget(b[name])
        # mod sets: save which mods are on, switch between saved sets
        self.sets = QComboBox()
        self.sets.setMinimumWidth(160)
        use = QPushButton("Use set")
        save = QPushButton("Save set as…")
        delete = QPushButton("Delete set")
        use.clicked.connect(self._use_set)
        save.clicked.connect(self._save_set)
        delete.clicked.connect(self._delete_set)
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Mod sets:"))
        row3.addWidget(self.sets, 1)
        for w in (use, save, delete):
            row3.addWidget(w)
        # the selected mod: preview, description, readme
        self.pic = QLabel()
        self.pic.setFixedSize(128, 128)
        self.pic.setAlignment(Qt.AlignCenter)
        self.about = QTextBrowser()
        self.about.setMaximumHeight(128)
        self.list.currentItemChanged.connect(lambda *_: self._show_selected())
        lay = QVBoxLayout(self)
        lay.addWidget(self.where)
        lay.addWidget(QLabel("Tick a mod to switch it on. Later mods (lower in the list) "
                             "win when two replace the same thing."))
        lay.addWidget(self.list, 1)
        detail = QHBoxLayout()
        detail.addWidget(self.pic)
        detail.addWidget(self.about, 1)
        lay.addLayout(detail)
        lay.addLayout(row1)
        lay.addLayout(row2)
        lay.addLayout(row3)
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
                                 + ("  — new, not on yet" if e.new else "")
                                 + ("  — linked folder" if e.linked else ""))
            it.setData(Qt.UserRole, e.mod.id)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if e.enabled else Qt.Unchecked)
            it.setToolTip(e.mod.description or str(e.mod.root))
            self.list.addItem(it)
            if e.mod.id == select:
                self.list.setCurrentItem(it)
        self.list.blockSignals(False)
        self.sets.clear()
        try:
            self.sets.addItems(sorted(self.lib.sets()))
        except Exception:  # noqa: BLE001 - a broken sets file shows as no sets
            pass
        self._show_selected()

    def _show_selected(self) -> None:
        mid = self._selected()
        self.pic.clear()
        if not mid:
            self.about.setMarkdown("")
            return
        try:
            e = self.lib.get(mid)
        except Dr2Error:
            return
        m = e.mod
        if m.preview_path:
            self.pic.setPixmap(QPixmap(str(m.preview_path)).scaled(
                128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.about.setMarkdown(f"**{m.name}** {m.version}"
                               + (f" by {m.author}" if m.author else "")
                               + (f"\n\n{m.description}" if m.description else "")
                               + (f"\n\n{needs}" if (needs := self._needs(m)) else "")
                               + (f"\n\n{m.readme}" if m.readme else "")
                               + f"\n\n`{m.root}`")

    def _needs(self, m) -> str:
        """What the mod needs (`mods.requires`), with what's missing in bold."""
        from ..mods.requires import summary
        return summary(m, {e.mod.id: e.mod.version for e in self.lib.entries() if e.enabled})

    def _link(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Mod folder to link (it stays where it is)")
        if d:
            mod = self._do(self.lib.link, d)
            if mod:
                self.refresh(mod.id)

    def _share(self) -> None:
        mid = self._selected()
        if mid:
            from .share_dialog import ShareDialog
            ShareDialog(self.main, self.lib.get(mid).mod.root).exec()
            self.refresh(mid)

    def _use_set(self) -> None:
        name = self.sets.currentText()
        if name:
            gone = self._do(self.lib.use_set, name)
            if gone:
                self.report.setPlainText(f"not installed any more: {', '.join(gone)}")

    def _save_set(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Save mod set", "Name of this set of mods:")
        if ok and name.strip():
            self._do(self.lib.save_set, name.strip())

    def _delete_set(self) -> None:
        name = self.sets.currentText()
        if name:
            self._do(self.lib.delete_set, name)

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
            src, _ = QFileDialog.getOpenFileName(self, "Mod to install", "",
                                                 "DR2 mods (*.dr2mod *.zip)")
        if not src:
            return
        if not folder:                      # a package: show it before installing
            from .share_dialog import InstallDialog
            InstallDialog(self.main, Path(src), self.lib).exec()
            self.refresh()
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
        """Deploy the switched-on mods for the main window's game (Studio's Deploy)."""
        if not self.lib.active(self.main.game):
            self.report.setPlainText(f"No switched-on mod is for {self.main.game}: deploying "
                                     f"removes the mods from the game.")
        else:
            self.report.setPlainText(f"deploying the switched-on mods for {self.main.game}… "
                                     f"(progress in the main window's log)")
        self.main.play(start=False)

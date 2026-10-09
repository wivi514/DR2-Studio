"""DR2 Studio's *Share mod…* and *Install mod…* windows.

Sharing (`ShareDialog`): everything a mod needs before someone else can use it, in one
window: its name, version, author, description, which games it is for, a preview
picture (any image, or one of the mod's own textures), and a readme. *Check* runs the
build's checks against each chosen game in the background (`mods.build.plan_mods`), so
a mod that wouldn't build on someone else's game is caught here. *Save .dr2mod…* writes
``mod.toml``, ``preview.png`` and ``README.md`` into the mod and packages it
(`mods.library.pack`): one ``.dr2mod`` file (a zip; user decision 2026-10-09) holding
only the modder's files, never game data.

Installing (`InstallDialog`): opened by *Install mod…*, by dropping a ``.dr2mod`` /
``.zip`` / mod folder on Studio, or by starting Studio with one (``dr2 studio
file.dr2mod``). It shows the mod before installing it (name, games, preview, readme,
how many files of each kind), then installs it into the library, switched on; an
update keeps the mod's place and lists what changed.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
                               QTextBrowser, QVBoxLayout)

from ..errors import Dr2Error
from ..mods.library import PACKAGE_EXT, ModLibrary, _unzip_mod, pack
from ..mods.manifest import Mod
from ..profiles import GAME_IDS, load_profile

PREVIEW_SIZE = 512


def kinds_summary(mod: Mod) -> str:
    """"3 textures, 1 model, 2 string files…" for a mod's files."""
    from collections import Counter
    from ..mods.build import _kind_of
    names = {"texture-png": "texture", "model-glb": "model", "audio": "sound",
             "strings": "string file", "raw": "other file"}
    c = Counter(names[_kind_of(rel)[0]] for rel, _ in mod.files())
    return ", ".join(f"{n} {k}{'s' if n != 1 else ''}" for k, n in c.items()) or "no files"


class ShareDialog(QDialog):
    """Fill in a mod's details, check it, save it as a ``.dr2mod``."""

    def __init__(self, main, mod_dir: Path):
        super().__init__(main)
        self.main = main
        self.mod = Mod.load(mod_dir)
        self.setWindowTitle(f"Share {self.mod.name}")
        self.resize(720, 640)
        m = self.mod
        self.name = QLineEdit(m.name)
        self.version = QLineEdit(m.version)
        self.author = QLineEdit(m.author)
        self.description = QPlainTextEdit(m.description)
        self.description.setMaximumHeight(70)
        self.games = {g: QCheckBox(load_profile(g).name) for g in GAME_IDS}
        for g, box in self.games.items():
            box.setChecked(g in m.games)
        self.preview = QLabel("(no preview picture)")
        self.preview.setFixedSize(200, 200)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("border: 1px solid palette(mid)")
        self._preview_src: Path | None = m.preview_path
        pick = QPushButton("Choose picture…")
        pick.clicked.connect(self._pick_preview)
        use_tex = QPushButton("Use one of the mod's textures")
        use_tex.clicked.connect(self._texture_preview)
        self.readme = QPlainTextEdit(m.readme or f"# {m.name}\n\nWhat this mod changes, "
                                                 f"and how to install it.\n")
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setMaximumHeight(110)
        check = QPushButton("Check")
        check.clicked.connect(self.check)
        save = QPushButton(f"Save {PACKAGE_EXT}…")
        save.clicked.connect(self.save)
        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("Version", self.version)
        form.addRow("Author", self.author)
        form.addRow("Description", self.description)
        gl = QHBoxLayout()
        for box in self.games.values():
            gl.addWidget(box)
        form.addRow("For", gl)
        pv = QHBoxLayout()
        pv.addWidget(self.preview)
        pb = QVBoxLayout()
        pb.addWidget(pick)
        pb.addWidget(use_tex)
        pb.addStretch(1)
        pv.addLayout(pb)
        pv.addStretch(1)
        form.addRow("Preview", pv)
        form.addRow("Readme", self.readme)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<b>{m.id}</b>: {kinds_summary(m)}. Mods must be free for "
                             f"everyone (the toolkit's licence)."))
        lay.addLayout(form)
        row = QHBoxLayout()
        row.addWidget(check)
        row.addStretch(1)
        row.addWidget(save)
        lay.addLayout(row)
        lay.addWidget(self.report)
        self._show_preview()

    def _show_preview(self) -> None:
        if self._preview_src and self._preview_src.is_file():
            pm = QPixmap(str(self._preview_src))
            self.preview.setPixmap(pm.scaled(200, 200, Qt.KeepAspectRatio,
                                             Qt.SmoothTransformation))

    def _pick_preview(self) -> None:
        src, _ = QFileDialog.getOpenFileName(self, "Preview picture", "",
                                             "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if src:
            self._preview_src = Path(src)
            self._show_preview()

    def _texture_preview(self) -> None:
        pngs = [p for rel, p in self.mod.files() if rel.lower().endswith(".png")]
        if not pngs:
            QMessageBox.information(self, "Share", "This mod has no texture to use.")
            return
        self._preview_src = pngs[0]
        self._show_preview()

    def _apply(self) -> Mod:
        """Write the form into the mod folder (mod.toml, preview.png, README.md)."""
        m = self.mod
        m.name = self.name.text().strip() or m.id
        m.version = self.version.text().strip() or "1.0.0"
        m.author = self.author.text().strip()
        m.description = self.description.toPlainText().strip()
        games = tuple(g for g, b in self.games.items() if b.isChecked())
        if not games:
            raise Dr2Error("tick at least one game")
        m.games = games
        if self._preview_src and self._preview_src.is_file():
            dest = m.root / "preview.png"
            if self._preview_src.resolve() != dest.resolve():
                pm = QPixmap(str(self._preview_src))
                if pm.width() > PREVIEW_SIZE or pm.height() > PREVIEW_SIZE:
                    pm = pm.scaled(PREVIEW_SIZE, PREVIEW_SIZE, Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
                if not pm.save(str(dest), "PNG"):
                    raise Dr2Error(f"{self._preview_src}: not a picture Qt can read")
            m.preview = "preview.png"
        (m.root / "README.md").write_text(self.readme.toPlainText().rstrip() + "\n", "utf-8")
        m.save()
        self.mod = Mod.load(m.root)
        return self.mod

    def check(self, then=None) -> None:
        try:
            mod = self._apply()
        except Dr2Error as e:
            self.report.setPlainText(str(e))
            return
        self.report.setPlainText("checking…")

        def work(progress):
            from ..container.vpath import AssetTree
            from ..mods.build import plan_mods
            from ..profiles import locate
            out = []
            for g in mod.games:
                try:
                    plan = plan_mods([mod], g, AssetTree(locate(g).root))
                    out.append(f"{g}: OK, {len(plan.planned)} change(s)")
                    out += [f"  note: {n}" for n in plan.notes]
                except Dr2Error as e:
                    out.append(f"{g}: PROBLEM\n  {e}")
            return out

        def done(lines, err):
            text = err or "\n".join(lines)
            self.report.setPlainText(text)
            if then and not err and not any("PROBLEM" in ln for ln in lines):
                then()
        self.main.run_job(work, done)

    def save(self) -> None:
        def write():
            m = self.mod
            dest, _ = QFileDialog.getSaveFileName(
                self, "Save the mod to share", f"{m.id}-{m.version}{PACKAGE_EXT}",
                f"DR2 mod (*{PACKAGE_EXT});;Zip (*.zip)")
            if not dest:
                return
            try:
                out = pack(m.root, dest)
            except Dr2Error as e:
                self.report.appendPlainText(str(e))
                return
            self.report.appendPlainText(f"saved {out} ({out.stat().st_size / 1e6:.1f} MB). "
                                        f"Share this file; others open it with DR2 Studio.")
            self.main.say(f"packaged {m.id} -> {out}")
        self.check(then=write)


class InstallDialog(QDialog):
    """Show a mod package (or folder) and install it into the library."""

    def __init__(self, main, source: Path, library: ModLibrary | None = None):
        super().__init__(main)
        self.main = main
        self.source = Path(source)
        self.lib = library or ModLibrary()
        self._tmp = tempfile.TemporaryDirectory(prefix="dr2mod-show-")
        self.setWindowTitle(f"Install {self.source.name}")
        self.resize(640, 560)
        lay = QVBoxLayout(self)
        try:
            folder = self.source if self.source.is_dir() else \
                _unzip_mod(self.source, Path(self._tmp.name))
            self.mod = Mod.load(folder)
        except Dr2Error as e:
            self.mod = None
            lay.addWidget(QLabel(f"This is not a mod DR2 Studio can install:\n{e}"))
            return
        m = self.mod
        installed = next((e for e in self.lib.entries() if e.mod.id == m.id), None)
        head = QHBoxLayout()
        pic = QLabel()
        if m.preview_path:
            pic.setPixmap(QPixmap(str(m.preview_path)).scaled(
                160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        head.addWidget(pic)
        info = QLabel(f"<h3>{m.name}</h3>version {m.version}"
                      + (f" by {m.author}" if m.author else "")
                      + f"<br>for {', '.join(load_profile(g).name for g in m.games)}"
                      + f"<br>{kinds_summary(m)}"
                      + (f"<br><br>{m.description}" if m.description else "")
                      + (f"<br><br><b>Installed already</b> (version "
                         f"{installed.mod.version}): installing updates it."
                         if installed else ""))
        info.setWordWrap(True)
        head.addWidget(info, 1)
        lay.addLayout(head)
        readme = QTextBrowser()
        readme.setMarkdown(m.readme or "*(no readme)*")
        lay.addWidget(readme, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Update" if installed else "Install")
        ok.setDefault(True)
        ok.clicked.connect(lambda: self.install(bool(installed)))
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def install(self, update: bool) -> Mod | None:
        try:
            mod = self.lib.install(self.source, replace=update)
        except Dr2Error as e:
            QMessageBox.warning(self, "Install", str(e))
            return None
        self.main.say(f"installed {mod.id} {mod.version} into the mod library, switched on"
                      + "".join(f"\n    {c}" for c in self.lib.last_changes))
        self.accept()
        return mod

    def done(self, r):
        self._tmp.cleanup()
        super().done(r)

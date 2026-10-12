"""DR2 Studio's *Effects…* window: browse the particle effects, change one, make your own
(phase 13 step 6).

Left, every effect of the game's effect table (`catalog.weapons`): its number, name,
group, ✓ when it was checked in game, and what the game uses it for; the open mod's own
effects and changed ones are marked. Right, the selected effect **playing on a game
weapon in Chuck's hand** (phase 13.2, `hold_view.HoldView`: the weapon kind and the
place, *while held* at the effect point or *on impact* at the tip, are chosen above it),
or the flat sketch (`convert.effect_preview`: its particle pictures, colours and sizes as
the data says, drawn in the background), its emitters in words, and the changes: a hue (0-360°,
or keep), saturation, brightness, opacity, size and lifetime (the colour keys' times), and a
swap of each particle picture (one of the game's, or a PNG of your own: `neweffect
.new_particle_texture`). The picture follows the sliders.

*Change in my mod* writes the changes over the game's effect (it changes it everywhere
the game uses it); *Make my own* copies it into a free slot of the effect table and
says its number, for the weapon wizard's effect boxes (`mods.neweffect`). Effects only
change what is seen. What was checked in game: docs/formats.md §Particle effects.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QSlider, QSplitter, QTabWidget, QTextBrowser,
                               QVBoxLayout, QWidget)

from ..catalog import weapons
from ..errors import Dr2Error
from ..mods import neweffect

KEEP = "(keep)"


def _pixmap(rgba) -> QPixmap:
    h, w = rgba.shape[:2]
    return QPixmap.fromImage(QImage(rgba.tobytes(), w, h, 4 * w,
                                    QImage.Format_RGBA8888).copy())


class EffectsDialog(QDialog):
    """The effects window (module docstring)."""

    SLIDERS = (("saturation", "Saturation", 0, 300, 100), ("brightness", "Brightness", 0, 300, 100),
               ("alpha", "Opacity", 0, 300, 100), ("size", "Size", 10, 500, 100),
               ("time", "Lifetime", 10, 500, 100))

    def __init__(self, main, mod_dir: Path | None):
        super().__init__(main)
        self.main = main
        self.mod_dir = Path(mod_dir) if mod_dir else None
        self.game = main.game
        self.setWindowTitle("Particle effects")
        self.resize(1100, 700)
        tree = main.plain_tree()
        from ..formats import effect as fx
        from ..formats.levelscript import Document
        self.effects = fx.read_all(tree)
        try:
            doc = Document.parse(tree.resolve("data/datafile.big/items.txt").data())
        except Dr2Error:
            doc = None
        self.table = weapons.effects(self.game, doc)
        arc = tree.open_archive(tree.resolve(neweffect.EFFECTS_TEX).vpath)
        self.pictures = sorted(e.name.removesuffix(".bct") for e in arc.entries)
        self.current = None          # the selected effect's name
        self._busy = self._again = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.refresh)

        self.search = QLineEdit()
        self.search.setPlaceholderText("search: snow, fire, spark, blood…")
        self.group = QComboBox()
        self.group.addItem("All groups", "")
        for gid, name in weapons.groups():
            self.group.addItem(name, gid)
        self.group.addItem("Yours (this mod)", "mine")
        self.list = QListWidget()
        self.list.currentItemChanged.connect(lambda cur, _p: self._select(cur))
        self.search.textChanged.connect(lambda _t: self._fill())
        self.group.currentIndexChanged.connect(lambda _i: self._fill())
        left = QWidget()
        ll = QVBoxLayout(left)
        row = QHBoxLayout()
        row.addWidget(self.search, 1)
        row.addWidget(self.group)
        ll.addLayout(row)
        ll.addWidget(self.list, 1)

        self.picture = QLabel("Select an effect")
        self.picture.setFixedSize(320, 320)
        self.picture.setAlignment(Qt.AlignCenter)
        self.picture.setStyleSheet("background:#121217;color:#aaa")
        # phase 13.2: the effect playing on a game weapon in Chuck's hand
        from .hold_view import HoldView
        self.hold = HoldView()
        self.hold.setMinimumSize(420, 360)
        self.on_kind = QComboBox()
        for k in weapons.kinds(self.game):
            self.on_kind.addItem(f"{k.name} ({k.template(self.game)})", k.id)
        self.on_slot = QComboBox()
        for sid, sl in weapons.slots().items():
            self.on_slot.addItem(sl["name"], sid)
        self.on_slot.setCurrentIndex(max(self.on_slot.findData("held"), 0))
        self.on_kind.currentIndexChanged.connect(lambda _i: self._kind_changed())
        self.on_slot.currentIndexChanged.connect(lambda _i: self._changed())
        self._hold_kind = None
        self.swatches = QLabel()
        self.info = QTextBrowser()
        self.info.setMaximumHeight(170)
        self.hue = QSlider(Qt.Horizontal)
        self.hue.setRange(-1, 360)
        self.hue.setValue(-1)
        self.hue_label = QLabel(KEEP)
        self.hue.valueChanged.connect(self._hue_changed)
        self.sliders = {}
        form = QFormLayout()
        hrow = QHBoxLayout()
        hrow.addWidget(self.hue, 1)
        hrow.addWidget(self.hue_label)
        form.addRow("Hue", hrow)
        for key, label, lo, hi, default in self.SLIDERS:
            s = QSlider(Qt.Horizontal)
            s.setRange(lo, hi)
            s.setValue(default)
            lab = QLabel(f"×{default / 100:.2f}")
            s.valueChanged.connect(lambda v, lab=lab: (lab.setText(f"×{v / 100:.2f}"),
                                                       self._changed()))
            r = QHBoxLayout()
            r.addWidget(s, 1)
            r.addWidget(lab)
            form.addRow(label, r)
            self.sliders[key] = s
        self.swap_from = QComboBox()
        self.swap_to = QComboBox()
        self.swap_to.addItem(KEEP)
        self.swap_to.addItems(self.pictures)
        self.swap_to.currentIndexChanged.connect(lambda _i: self._changed())
        self.swaps: dict[str, str] = {}
        self.swap_from.currentTextChanged.connect(self._swap_shown)
        b_own_pic = QPushButton("My own picture…")
        b_own_pic.setToolTip("Add a PNG of your own to the particle pictures (into the open mod)")
        b_own_pic.clicked.connect(self._own_picture)
        srow = QHBoxLayout()
        srow.addWidget(self.swap_from, 1)
        srow.addWidget(QLabel("→"))
        srow.addWidget(self.swap_to, 1)
        srow.addWidget(b_own_pic)
        form.addRow("Picture", srow)
        b_reset = QPushButton("Reset")
        b_reset.clicked.connect(self._reset)
        self.b_change = QPushButton("Change in my mod")
        self.b_change.setToolTip("Changes this effect of the game, everywhere the game uses it")
        self.b_change.clicked.connect(self.change)
        self.b_own = QPushButton("Make my own from this")
        self.b_own.setToolTip("Copies it into a free number of the effect table, with your "
                              "changes: give that number to a weapon (New weapon…)")
        self.b_own.clicked.connect(self.make_own)
        self.b_remove = QPushButton("Remove from mod")
        self.b_remove.clicked.connect(self.remove)
        self.notes = QLabel()
        self.notes.setWordWrap(True)
        right = QWidget()
        rl = QVBoxLayout(right)
        on3d = QWidget()
        ol = QVBoxLayout(on3d)
        ol.setContentsMargins(0, 0, 0, 0)
        orow = QHBoxLayout()
        orow.addWidget(QLabel("On"))
        orow.addWidget(self.on_kind, 1)
        orow.addWidget(self.on_slot)
        ol.addLayout(orow)
        ol.addWidget(self.hold, 1)
        sketch = QWidget()
        sl_ = QVBoxLayout(sketch)
        sl_.addWidget(self.picture, 0, Qt.AlignCenter)
        self.views = QTabWidget()
        self.views.addTab(on3d, "On a weapon (3D)")
        self.views.addTab(sketch, "Sketch")
        if not self.hold.available:
            self.views.setCurrentIndex(1)
        top = QHBoxLayout()
        top.addWidget(self.views, 3)
        col = QVBoxLayout()
        col.addWidget(self.swatches)
        col.addWidget(self.info, 1)
        top.addLayout(col, 2)
        rl.addLayout(top, 1)
        rl.addLayout(form)
        brow = QHBoxLayout()
        for b in (b_reset, self.b_change, self.b_own, self.b_remove):
            brow.addWidget(b)
        rl.addLayout(brow)
        rl.addWidget(self.notes)
        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([380, 720])
        lay = QVBoxLayout(self)
        lay.addWidget(split)
        legend = QLabel("<small>Both views are sketches from the effect's data (its pictures, "
                        "colours, sizes, life, start box, speed and gravity); how the game moves "
                        "particles is not all measured. Effects only change what is seen."
                        "</small>")
        lay.addWidget(legend)
        for b in (self.b_change, self.b_own, self.b_remove):
            b.setEnabled(self.mod_dir is not None)
        if self.mod_dir is None:
            self.notes.setText("Open or create a mod (bottom bar) to change effects.")
        self._fill()

    # ---- the list ------------------------------------------------------------------------

    def _mine(self) -> tuple[dict, set]:
        if self.mod_dir is None:
            return {}, set()
        own = {n: r for n, r in neweffect.own_effects(self.mod_dir)}
        changed = {n.lower() for n, _ in neweffect.changed_effects(self.mod_dir)}
        return own, changed

    def _fill(self) -> None:
        own, changed = self._mine()
        words = self.search.text().lower().split()
        group = self.group.currentData()
        keep = self.current
        self.list.blockSignals(True)
        self.list.clear()
        names = dict(weapons.groups())
        for e in self.table:
            mine = e.number in own
            if group == "mine" and not (mine or e.name.lower() in changed):
                continue
            if group and group != "mine" and e.group != group:
                continue
            hay = e.name.lower() + (" " + own[e.number]["effect"].get("from", "").lower()
                                    if mine else "")
            if words and not all(w in hay for w in words):
                continue
            if not mine and e.name not in self.effects:
                continue                                  # a free slot: nothing to show
            label = f"{e.number:3}  {e.name}"
            if e.tested:
                label += "  ✓"
            if mine:
                label += f"  (yours, from {own[e.number]['effect'].get('from')})"
            elif e.name.lower() in changed:
                label += "  (changed by your mod)"
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, e.number)
            tip = [names[e.group]]
            if e.tested:
                tip.append(f"checked in game: {e.tested}")
            if e.used_by:
                tip.append("used by " + ", ".join(e.used_by[:8]))
            it.setToolTip("\n".join(tip))
            self.list.addItem(it)
            if e.name == keep:
                self.list.setCurrentItem(it)
        self.list.blockSignals(False)

    def _select(self, item) -> None:
        if item is None:
            return
        num = int(item.data(Qt.UserRole))
        own, _ = self._mine()
        e = self.table[num - 1]
        self.current = e.name
        self.base_name = own[num]["effect"]["from"] if num in own else e.name
        self.base_changes = dict(own[num]["effect"].get("changes") or {}) if num in own else {}
        if num not in own and self.mod_dir is not None:
            for n, ch in neweffect.changed_effects(self.mod_dir):
                if n.lower() == e.name.lower():
                    self.base_changes = dict(ch)
        self._load_changes(self.base_changes)
        fxe = self.effects.get(self.base_name)
        pics = sorted({m.texture for m in fxe[1].emitters}) if fxe else []
        self.swap_from.blockSignals(True)
        self.swap_from.clear()
        self.swap_from.addItems(pics)
        self.swap_from.blockSignals(False)
        self._swap_shown(self.swap_from.currentText())
        self.refresh()

    def _load_changes(self, ch: dict) -> None:
        for w in [self.hue, *self.sliders.values()]:
            w.blockSignals(True)
        self.hue.setValue(int(ch["hue"]) if "hue" in ch else -1)
        self._hue_changed(self.hue.value(), refresh=False)
        for key, s in self.sliders.items():
            s.setValue(int(round(float(ch.get(key, 1.0)) * 100)))
        for w in [self.hue, *self.sliders.values()]:
            w.blockSignals(False)
        self.swaps = dict(ch.get("texture") or {})

    def _hue_changed(self, v: int, refresh: bool = True) -> None:
        if v < 0:
            self.hue_label.setText(KEEP)
            self.hue_label.setStyleSheet("")
        else:
            c = QColor.fromHsv(v % 360, 220, 230)
            self.hue_label.setText(f"{v}°")
            self.hue_label.setStyleSheet(f"background:{c.name()};padding:0 6px")
        if refresh:
            self._changed()

    def _swap_shown(self, pic: str) -> None:
        self.swap_to.blockSignals(True)
        self.swap_to.setCurrentText(self.swaps.get(pic, KEEP) if pic else KEEP)
        self.swap_to.blockSignals(False)

    def changes(self) -> dict:
        """The form as `convert.effects` changes."""
        pic = self.swap_from.currentText()
        if pic:
            to = self.swap_to.currentText()
            if to == KEEP:
                self.swaps.pop(pic, None)
            else:
                self.swaps[pic] = to
        ch: dict = {}
        if self.hue.value() >= 0:
            ch["hue"] = self.hue.value()
        for key, s in self.sliders.items():
            if s.value() != 100:
                ch[key] = round(s.value() / 100, 2)
        if self.swaps:
            ch["texture"] = dict(self.swaps)
        return ch

    def _reset(self) -> None:
        self._load_changes({})
        self.swap_to.setCurrentText(KEEP)
        self.refresh()

    # ---- picture -------------------------------------------------------------------------

    def _changed(self) -> None:
        self._timer.start()

    def refresh(self) -> None:
        if not self.current:
            return
        if self._busy:
            self._again = True
            return
        name, changes = self.base_name, self.changes()
        own_pics = self._own_picture_files()
        self._busy = True
        game, mod_dir, hold = self.game, self.mod_dir, self.hold
        kind, slot = self.on_kind.currentData(), self.on_slot.currentData()
        want_scene = hold.available and kind != self._hold_kind
        want_chuck = hold.needs_chuck(game)
        number = [x.name for x in self.table].index(self.current) + 1

        def job(progress):
            from ..container.vpath import AssetTree
            from ..convert import effect_preview as ep
            from ..convert.effects import apply_changes, describe
            from ..formats import effect as fx
            from ..profiles import locate
            tree = AssetTree(locate(game).root)
            base = fx.read_all(tree)[name][1]
            e = fx.Effect.parse(base.to_bytes())
            apply_changes(e, changes)
            finder = ep.texture_finder(tree)

            def textures(n):
                f = own_pics.get(n.lower())
                if f is not None:
                    import numpy as np
                    from ..convert import png
                    im = png.read(f)
                    return np.frombuffer(im.rgba, np.uint8).reshape(
                        im.height, im.width, 4).astype(np.float32) / 255
                return finder(n)
            out = (ep.preview(e, textures, 320), describe(e), [m.colour_keys() for m in e.emitters])
            if not hold.available:
                return out + (None, None, None, None)
            from ..convert import holding
            from ..mods import newweapon as nw
            pics: dict = {}
            view = nw.effect_view(tree, e, slot, number, mod_dir, pics)
            for n, f in own_pics.items():                 # pictures not saved in a recipe yet
                if n in {m.texture.lower() for m in e.emitters}:
                    pics[next(m.texture for m in e.emitters if m.texture.lower() == n)] = \
                        f.read_bytes()
            scene = nw.hold_scene(tree, game, nw.WeaponSpec(name="Preview", kind=kind),
                                  mod_dir=mod_dir) if want_scene else None
            chuck = holding.rest_glb(tree, game) if want_chuck else None
            return out + (view, pics, scene, chuck)
        self.main.run_job(job, self._shown)

    def _kind_changed(self) -> None:
        self._hold_kind = None              # a new weapon to show
        self._changed()

    def _shown(self, result, error) -> None:
        self._busy = False
        if error is not None:
            self.notes.setText(f"Picture: {error}")
        else:
            pic, lines, keys, view, pics, scene, chuck = result
            if chuck is not None:
                self.hold.set_chuck(self.game, chuck)
            if scene is not None:
                self.hold.show_scene(scene, keep_view=self._hold_kind is not None)
                self._hold_kind = self.on_kind.currentData()
            if view is not None:
                self.hold.set_effects([view], pics)
            self.picture.setPixmap(_pixmap(pic))
            sw = "".join(
                "<span style='background:rgb({},{},{});'>&nbsp;&nbsp;&nbsp;</span>".format(
                    *(int(max(0.0, min(1.0, c)) * 255) for c in k[:3])) for row in keys
                for k in row if k[3] > 0.004)
            self.swatches.setText(f"<b>Colours</b> {sw}")
            e = self.table[[x.name for x in self.table].index(self.current)]
            extra = []
            if e.tested:
                extra.append(f"<i>Checked in game:</i> {e.tested}")
            if e.used_by:
                extra.append("<i>The game uses it on:</i> " + ", ".join(e.used_by[:10]))
            self.info.setHtml("<br>".join([f"<b>{e.number}: {self.current}</b>",
                                           *lines, *extra]))
        if self._again:
            self._again = False
            self.refresh()

    # ---- writing into the mod --------------------------------------------------------------

    def _own_picture_files(self) -> dict:
        if self.mod_dir is None:
            return {}
        src = self.mod_dir / "sources"
        out = {}
        for r in (self.mod_dir / "add/data/models/effects.tex").glob("*.copy.json") \
                if (self.mod_dir / "add/data/models/effects.tex").is_dir() else []:
            name = r.name[:-len(".copy.json")]
            if (src / f"{name}.png").is_file():
                out[name.lower()] = src / f"{name}.png"
        return out

    def _own_picture(self) -> None:
        if self.mod_dir is None:
            return
        f, _ = QFileDialog.getOpenFileName(self, "Your particle picture (PNG with "
                                           "see-through parts)", "", "Pictures (*.png *.jpg)")
        if not f:
            return
        name, ok = QInputDialog.getText(self, "Particle picture", "Its name (letters, digits, _):",
                                        text=Path(f).stem.replace(" ", "_")[:24])
        if not ok or not name:
            return
        try:
            neweffect.new_particle_texture(self.main.plain_tree(), self.mod_dir, name, f)
        except Dr2Error as e:
            self.main.error(str(e))
            return
        self.swap_to.addItem(name)
        self.swap_to.setCurrentText(name)
        self.main.say(f"{name}: your particle picture is in the mod")
        self.main._set_mod(self.mod_dir)

    def change(self) -> None:
        if not self.current or self.mod_dir is None:
            return
        own, _ = self._mine()
        num = [x.name for x in self.table].index(self.current) + 1
        try:
            if num in own:                    # yours: update its recipe
                neweffect.remove(self.mod_dir, num)
                neweffect.new_effect(self.main.plain_tree(), self.game, self.mod_dir,
                                     self.base_name, self.changes(), num)
            else:
                neweffect.change_effect(self.main.plain_tree(), self.mod_dir, self.current,
                                        self.changes())
        except Dr2Error as e:
            self.main.error(str(e))
            return
        self.notes.setText(f"{self.current} changed in your mod (it changes it everywhere the "
                           f"game uses it). ▶ Play to see it.")
        self.main._set_mod(self.mod_dir)
        self._fill()

    def make_own(self) -> None:
        if not self.current or self.mod_dir is None:
            return
        try:
            num, _ = neweffect.new_effect(self.main.plain_tree(), self.game, self.mod_dir,
                                          self.base_name, self.changes())
        except Dr2Error as e:
            self.main.error(str(e))
            return
        self.notes.setText(f"Your effect is number {num}: choose it in New weapon… (effect "
                           f"boxes), or type {num} in an effect key.")
        self.main.say(f"your own effect {num} (from {self.base_name}) is in the mod")
        self.main._set_mod(self.mod_dir)
        self.current = self.table[num - 1].name
        self._fill()

    def remove(self) -> None:
        if not self.current or self.mod_dir is None:
            return
        own, _ = self._mine()
        num = [x.name for x in self.table].index(self.current) + 1
        gone = neweffect.remove(self.mod_dir, num if num in own else self.current)
        self.notes.setText("Removed from the mod." if gone else "Your mod doesn't change it.")
        self.main._set_mod(self.mod_dir)
        self._fill()

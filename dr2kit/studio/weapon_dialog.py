"""DR2 Studio's *New weapon…* window: the weapon wizard (phase 13 step 3).

One window for everything `mods.newweapon.WeaponSpec` holds, in the order a modder
thinks of it: the name (English and French; the other languages get the English), what
it swings like (a kind, `catalog.weapons`), its model (the game weapon's, the sample
sword, or a ``.glb`` of one's own, laid along the game weapon by `convert.weapon_fit`
with *handle end*, *length*, *turn* and *slide* to adjust it), damage and durability,
its element, its effects (picked from the named effect table, grouped, with what the
game uses each for and what was checked in game), its inventory icon, and a combo
recipe with its card.

*Preview* (also run after each change, after a short pause) draws in the background
(`MainWindow.run_job`): the new shape over the game weapon seen from its flat side, the
game weapon faded and the hands' grip nodes as red diamonds (where Chuck will hold it:
measured in game, the hands follow those nodes), the inventory icon, and the card.
*Make weapon* writes it into the open mod (`newweapon.make_weapon`); opening the window
on a weapon the mod already has fills it in again, and *Make* rebuilds it.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ..catalog import weapons
from ..errors import Dr2Error
from ..mods import newweapon as nw

NEW = "(a new weapon)"
SAMPLE = "The sample sword"
GAME_SHAPE = "The game weapon's own shape"


def _pixmap(rgba, scale: int = 1) -> QPixmap:
    """An RGBA numpy picture as a QPixmap (``scale``: nearest-neighbour enlargement)."""
    h, w = rgba.shape[:2]
    img = QImage(rgba.tobytes(), w, h, 4 * w, QImage.Format_RGBA8888).copy()
    pm = QPixmap.fromImage(img)
    return pm.scaled(w * scale, h * scale, Qt.KeepAspectRatio, Qt.FastTransformation) \
        if scale != 1 else pm


class EffectBox(QComboBox):
    """An effect picker: none, then every effect by group, with its use and checks."""

    def __init__(self, effects: list, slot: str, own: dict | None = None):
        super().__init__()
        own = own or {}
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.lineEdit().setPlaceholderText("type to search: snow, fire, spark…")
        self.addItem("none", 0)
        names = dict(weapons.groups())
        for num, recipe in sorted(own.items()):     # the mod's own effects first
            src = recipe.get("effect", {}).get("from", "")
            self.addItem(f"Yours: {num} (from {src})", num)
            self.setItemData(self.count() - 1, "your own effect (Effects… window)",
                             Qt.ToolTipRole)
        want_loop = slot in ("held", "swinging")
        for gid, gname in weapons.groups():
            group = [e for e in effects if e.group == gid]
            group.sort(key=lambda e: (e.loops is not want_loop, e.number))
            for e in group:
                mark = " ✓" if e.tested else ""
                self.addItem(f"{gname}: {e.number} {e.name}{mark}", e.number)
                tip = [f"{names[e.group]}, number {e.number}"]
                if e.loops is not None:
                    tip.append("keeps going (read from its name)" if e.loops
                               else "a burst (read from its name)")
                if e.tested:
                    tip.append(f"checked in game: {e.tested}")
                if e.used_by:
                    tip.append("the game uses it on " + ", ".join(e.used_by[:6]))
                self.setItemData(self.count() - 1, "\n".join(tip), Qt.ToolTipRole)
        self.completer().setFilterMode(Qt.MatchContains)
        self.completer().setCompletionMode(self.completer().CompletionMode.PopupCompletion)

    def number(self) -> int:
        i = self.findText(self.currentText())
        return int(self.itemData(i)) if i >= 0 else 0

    def set_number(self, n: int) -> None:
        i = self.findData(int(n))
        self.setCurrentIndex(max(i, 0))


class WeaponDialog(QDialog):
    """The weapon wizard (module docstring)."""

    def __init__(self, main, mod_dir: Path, name: str | None = None):
        super().__init__(main)
        self.main = main
        self.mod_dir = Path(mod_dir)
        self.game = main.game
        self.setWindowTitle("New weapon")
        self.resize(1180, 760)
        self._busy = False
        self._again = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(700)
        self._timer.timeout.connect(self.refresh_preview)

        tree = main.plain_tree()
        from ..formats.levelscript import Document
        try:
            self.items_doc = Document.parse(tree.resolve("data/datafile.big/items.txt").data())
        except Dr2Error:
            self.items_doc = None
        effects = weapons.effects(self.game, self.items_doc)
        item_names = sorted(b.name for b in (self.items_doc.blocks if self.items_doc else [])
                            if b.cls in ("cPlayerWeaponItem", "cFirearmItem", "cExplosiveItem",
                                         "cSprayItem", "cUtilityItem", "cFoodItem")
                            and b.name)

        # --- the form
        self.which = QComboBox()
        self.which.addItem(NEW)
        for w in nw.weapons_of(self.mod_dir):
            self.which.addItem(w)
        self.which.currentTextChanged.connect(self._open_weapon)
        self.name = QLineEdit()
        self.name.setPlaceholderText("its item name: letters, digits, _ (e.g. FrostBlade)")
        self.name_en = QLineEdit()
        self.name_en.setPlaceholderText("Frost Blade")
        self.name_fr = QLineEdit()
        self.name_fr.setPlaceholderText("Lame de givre (empty: the English name)")
        self.kind = QComboBox()
        for k in weapons.kinds(self.game):
            self.kind.addItem(f"{k.name} — like the {k.template(self.game)}", k.id)
            self.kind.setItemData(self.kind.count() - 1, k.note, Qt.ToolTipRole)
        self.model = QComboBox()
        self.model.addItems([GAME_SHAPE, SAMPLE])
        self.model.setEditable(False)
        self.model_file = ""
        b_model = QPushButton("Model file (.glb)…")
        b_model.clicked.connect(self._pick_model)
        self.handle = QComboBox()
        self.handle.addItem("found by itself", "auto")
        self.handle.addItem("one end", "min")
        self.handle.addItem("the other end", "max")
        self.length = QDoubleSpinBox()
        self.length.setRange(0, 3)
        self.length.setDecimals(2)
        self.length.setSingleStep(0.05)
        self.length.setSpecialValueText("the game weapon's")
        self.length.setSuffix(" m")
        self.turn = QSpinBox()
        self.turn.setRange(-180, 180)
        self.turn.setSingleStep(90)
        self.turn.setSuffix("°")
        self.slide = QDoubleSpinBox()
        self.slide.setRange(-1, 1)
        self.slide.setDecimals(2)
        self.slide.setSingleStep(0.02)
        self.slide.setSuffix(" m")
        self.damage = QSpinBox()
        self.damage.setRange(0, 100000)
        self.damage.setSpecialValueText("the game weapon's")
        self.durability = QSpinBox()
        self.durability.setRange(0, 10000)
        self.durability.setSpecialValueText("the game weapon's")
        self.element = QComboBox()
        for eid, e in weapons.elements().items():
            self.element.addItem(e["name"], eid)
            self.element.setItemData(self.element.count() - 1,
                                     e["description"] + ("\n" + e.get("checked", "")),
                                     Qt.ToolTipRole)
        from ..mods import neweffect
        own = dict(neweffect.own_effects(self.mod_dir))
        self.fx = {}
        for slot in weapons.slots():
            self.fx[slot] = EffectBox(effects, slot, own)
        self.icon = QComboBox()
        self.icon.addItem("A picture of the model", "auto")
        self.icon.addItem("The game weapon's icon", "keep")
        self.icon_file = ""
        b_icon = QPushButton("My own PNG…")
        b_icon.clicked.connect(self._pick_icon)

        self.combo = QCheckBox("Make it at a workbench from two items (with a combo card)")
        self.item1 = QComboBox()
        self.item2 = QComboBox()
        for box in (self.item1, self.item2):
            box.setEditable(True)
            box.addItems(item_names)
            box.completer().setFilterMode(Qt.MatchContains)
        self.card_en = QLineEdit()
        self.card_en.setPlaceholderText("the card's text (English)")
        self.card_fr = QLineEdit()
        self.card_fr.setPlaceholderText("the card's text (French)")
        self.card_pic = QComboBox()
        self.card_pic.addItem("A picture of the model", "auto")
        self.card_file = ""
        b_card = QPushButton("My own picture…")
        b_card.clicked.connect(self._pick_card)
        self.card_number = QSpinBox()
        self.card_number.setRange(0, 999)
        self.card_number.setSpecialValueText("the first free one")

        form = QFormLayout()
        form.addRow("Weapon", self.which)
        form.addRow("Item name", self.name)
        form.addRow("Name (English)", self.name_en)
        form.addRow("Name (French)", self.name_fr)
        form.addRow("Swings like", self.kind)
        mrow = QHBoxLayout()
        mrow.addWidget(self.model, 1)
        mrow.addWidget(b_model)
        form.addRow("Model", mrow)
        form.addRow("Its handle is", self.handle)
        form.addRow("Length", self.length)
        form.addRow("Turn about its length", self.turn)
        form.addRow("Slide (where the hands hold it)", self.slide)
        form.addRow("Damage per hit", self.damage)
        form.addRow("Durability (hits)", self.durability)
        form.addRow("Element", self.element)
        for slot, s in weapons.slots().items():
            self.fx[slot].setToolTip(s["description"])
            form.addRow(f"Effect: {s['name'].lower()}", self.fx[slot])
        irow = QHBoxLayout()
        irow.addWidget(self.icon, 1)
        irow.addWidget(b_icon)
        form.addRow("Inventory icon", irow)
        cbox = QGroupBox("Combo weapon")
        cf = QFormLayout(cbox)
        cf.addRow(self.combo)
        crow = QHBoxLayout()
        crow.addWidget(self.item1, 1)
        crow.addWidget(QLabel("+"))
        crow.addWidget(self.item2, 1)
        cf.addRow("Items", crow)
        cf.addRow("Card text", self.card_en)
        cf.addRow("", self.card_fr)
        prow = QHBoxLayout()
        prow.addWidget(self.card_pic, 1)
        prow.addWidget(b_card)
        cf.addRow("Card picture", prow)
        cf.addRow("Card number", self.card_number)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addLayout(form)
        ll.addWidget(cbox)
        ll.addStretch(1)

        # --- the preview
        self.side = QLabel("Preview: the new shape over the game weapon")
        self.side.setAlignment(Qt.AlignCenter)
        self.side.setMinimumSize(480, 200)
        self.side.setStyleSheet("background:#3c3c3c;color:#ccc")
        self.icon_view = QLabel()
        self.icon_view.setFixedSize(256, 128)
        self.icon_view.setStyleSheet("background:#3c3c3c")
        self.card_view = QLabel()
        self.card_view.setFixedSize(273, 384)
        self.card_view.setStyleSheet("background:#3c3c3c")
        self.notes = QLabel()
        self.notes.setWordWrap(True)
        legend = QLabel("<small>Red diamonds: where Chuck's hands go (the game weapon's grip "
                        "nodes). Faded: the game weapon. Move the new shape with <i>slide</i>, "
                        "<i>turn</i> and <i>length</i>.</small>")
        legend.setWordWrap(True)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(self.side)
        rl.addWidget(legend)
        row = QHBoxLayout()
        col = QVBoxLayout()
        col.addWidget(QLabel("Inventory icon"))
        col.addWidget(self.icon_view)
        col.addStretch(1)
        row.addLayout(col)
        col = QVBoxLayout()
        col.addWidget(QLabel("Combo card"))
        col.addWidget(self.card_view)
        row.addLayout(col)
        rl.addLayout(row)
        rl.addWidget(self.notes)
        rl.addStretch(1)

        b_preview = QPushButton("Preview")
        b_preview.clicked.connect(self.refresh_preview)
        self.b_make = QPushButton("Make weapon")
        self.b_make.setDefault(True)
        self.b_make.clicked.connect(self.make)
        b_remove = QPushButton("Remove from mod")
        b_remove.clicked.connect(self.remove)
        b_close = QPushButton("Close")
        b_close.clicked.connect(self.reject)
        brow = QHBoxLayout()
        brow.addWidget(b_remove)
        brow.addStretch(1)
        for b in (b_preview, self.b_make, b_close):
            brow.addWidget(b)

        top = QHBoxLayout()
        top.addWidget(left, 5)
        top.addWidget(right, 6)
        lay = QVBoxLayout(self)
        lay.addLayout(top, 1)
        lay.addLayout(brow)

        for w in (self.kind, self.model, self.handle, self.element, self.icon, self.card_pic):
            w.currentIndexChanged.connect(lambda _i: self._changed())
        for w in (self.length, self.slide):
            w.valueChanged.connect(lambda _v: self._changed())
        self.turn.valueChanged.connect(lambda _v: self._changed())
        self.combo.toggled.connect(lambda _v: self._changed())
        for w in (self.item1, self.item2):
            w.currentTextChanged.connect(lambda _t: self._changed())
        self._set_combo_enabled()
        self.combo.toggled.connect(lambda _v: self._set_combo_enabled())
        if name:
            self.which.setCurrentText(name)
        else:
            self._changed()

    def done(self, result: int) -> None:          # closing: no more previews
        self._timer.stop()
        self._again = False
        super().done(result)

    def closeEvent(self, ev):  # noqa: N802 - Qt's name
        self._timer.stop()
        self._again = False
        super().closeEvent(ev)

    # ---- the form <-> the spec -----------------------------------------------------------

    def spec(self, preview: bool = False) -> nw.WeaponSpec:
        """The form as a `WeaponSpec` (``preview``: a placeholder name when empty)."""
        name = self.name.text().strip() or ("Preview" if preview else "")
        if not name:
            raise Dr2Error("give the weapon an item name (letters, digits, _)")
        model = {GAME_SHAPE: None, SAMPLE: "sample"}.get(self.model.currentText(),
                                                         self.model_file or None)
        icon = self.icon.currentData() if self.icon.currentData() in ("auto", "keep") \
            else self.icon_file
        names = {"en": self.name_en.text().strip() or name}
        if self.name_fr.text().strip():
            names["fr"] = self.name_fr.text().strip()
        effects = {slot: box.number() for slot, box in self.fx.items() if box.number()}
        combo = None
        if self.combo.isChecked():
            desc = {k: v.text().strip() for k, v in (("en", self.card_en), ("fr", self.card_fr))
                    if v.text().strip()}
            combo = nw.Combo([self.item1.currentText().strip(), self.item2.currentText().strip()],
                             self.card_pic.currentData() if self.card_pic.currentData() == "auto"
                             else self.card_file,
                             self.card_number.value() or None, desc)
        return nw.WeaponSpec(name=name, kind=self.kind.currentData(), names=names, model=model,
                             handle=self.handle.currentData(),
                             length=self.length.value() or None, turn=float(self.turn.value()),
                             slide=self.slide.value(), damage=self.damage.value() or None,
                             durability=self.durability.value() or None,
                             element=self.element.currentData(), effects=effects, icon=icon,
                             combo=combo)

    def _open_weapon(self, which: str) -> None:
        if which == NEW:
            self.name.setEnabled(True)
            return
        try:
            s = nw.load_spec(self.mod_dir, which)
        except Dr2Error as e:
            self.notes.setText(str(e))
            return
        self.name.setText(s.name)
        self.name.setEnabled(False)
        self.name_en.setText(s.names.get("en", ""))
        self.name_fr.setText(s.names.get("fr", ""))
        self.kind.setCurrentIndex(max(self.kind.findData(s.kind), 0))
        if s.model is None:
            self.model.setCurrentText(GAME_SHAPE)
        elif s.model == "sample":
            self.model.setCurrentText(SAMPLE)
        else:
            self._set_model_file(s.model)
        self.handle.setCurrentIndex(max(self.handle.findData(s.handle), 0))
        self.length.setValue(s.length or 0)
        self.turn.setValue(int(s.turn))
        self.slide.setValue(s.slide)
        self.damage.setValue(s.damage or 0)
        self.durability.setValue(s.durability or 0)
        self.element.setCurrentIndex(max(self.element.findData(s.element), 0))
        for slot, box in self.fx.items():
            box.set_number(weapons.effect_number(self.game, s.effects.get(slot, 0)))
        if s.icon in ("auto", "keep"):
            self.icon.setCurrentIndex(self.icon.findData(s.icon))
        else:
            self._set_icon_file(s.icon)
        self.combo.setChecked(s.combo is not None)
        if s.combo:
            self.item1.setCurrentText(s.combo.items[0])
            self.item2.setCurrentText(s.combo.items[1])
            self.card_en.setText(s.combo.description.get("en", ""))
            self.card_fr.setText(s.combo.description.get("fr", ""))
            self.card_number.setValue(s.combo.number or 0)
            if s.combo.picture != "auto":
                self._set_card_file(s.combo.picture)
        self._changed()

    def _set_combo_enabled(self) -> None:
        for w in (self.item1, self.item2, self.card_en, self.card_fr, self.card_pic,
                  self.card_number):
            w.setEnabled(self.combo.isChecked())

    # ---- files ---------------------------------------------------------------------------

    def _set_model_file(self, f: str) -> None:
        self.model_file = f
        label = f"My model: {Path(f).name}"
        if self.model.findText(label) < 0:
            self.model.addItem(label)
        self.model.setCurrentText(label)

    def _pick_model(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Your weapon's model", "",
                                           "glTF binary (*.glb)")
        if f:
            self._set_model_file(f)

    def _set_icon_file(self, f: str) -> None:
        self.icon_file = f
        self.icon.addItem(f"My picture: {Path(f).name}", "file")
        self.icon.setCurrentIndex(self.icon.count() - 1)

    def _pick_icon(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Inventory icon (128×64, see-through "
                                           "background)", "", "Pictures (*.png *.jpg)")
        if f:
            self._set_icon_file(f)

    def _set_card_file(self, f: str) -> None:
        self.card_file = f
        self.card_pic.addItem(f"My picture: {Path(f).name}", "file")
        self.card_pic.setCurrentIndex(self.card_pic.count() - 1)

    def _pick_card(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "The card's picture (315×262)", "",
                                           "Pictures (*.png *.jpg)")
        if f:
            self._set_card_file(f)

    # ---- preview and make ----------------------------------------------------------------

    def _changed(self) -> None:
        self._timer.start()

    def refresh_preview(self) -> None:
        if self._busy:
            self._again = True
            return
        try:
            spec = self.spec(preview=True)
        except Dr2Error as e:
            self.notes.setText(str(e))
            return
        self._busy = True
        self.notes.setText("Drawing the preview…")
        game, sources = self.game, self.mod_dir / "sources"

        def job(progress):
            from ..container.vpath import AssetTree
            from ..profiles import locate
            return nw.preview(AssetTree(locate(game).root), game, spec, sources)
        self.main.run_job(job, self._previewed)

    def _previewed(self, result, error) -> None:
        self._busy = False
        if error is not None:
            self.notes.setText(f"Preview: {error}")
        else:
            self.side.setPixmap(_pixmap(result.side))
            if result.icon is not None:
                self.icon_view.setPixmap(_pixmap(result.icon, 2))
            else:
                self.icon_view.setText("the game weapon's icon")
            if result.card is not None:
                self.card_view.setPixmap(_pixmap(result.card).scaled(
                    273, 384, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                self.card_view.clear()
            self.notes.setText("\n".join(result.notes))
        if self._again:
            self._again = False
            self.refresh_preview()

    def make(self) -> None:
        try:
            spec = self.spec()
        except Dr2Error as e:
            self.main.error(str(e))
            return
        game, mod_dir = self.game, self.mod_dir
        self.b_make.setEnabled(False)
        self.notes.setText(f"Making {spec.name}…")

        def job(progress):
            from ..container.vpath import AssetTree
            from ..mods.deploy import recomp_folders
            from ..profiles import locate
            root = locate(game).root
            patched = recomp_folders(root)["patched"]
            return nw.make_weapon(AssetTree(root), game, mod_dir, spec,
                                  [patched] if patched.is_dir() else [])
        self.main.run_job(job, lambda r, e: self._made(spec, r, e))

    def _made(self, spec, made, error) -> None:
        self.b_make.setEnabled(True)
        if error is not None:
            self.notes.setText(str(error))
            self.main.error(str(error))
            return
        if self.which.findText(spec.name) < 0:
            self.which.addItem(spec.name)
        self.which.blockSignals(True)
        self.which.setCurrentText(spec.name)
        self.which.blockSignals(False)
        self.name.setEnabled(False)
        card = f", combo card {made.card_number}" if made.card_number else ""
        msg = (f"{spec.name} is in your mod{card}. Place it in a level: Maps tab, Add item… "
               f"(it is listed under your mod's items).")
        self.notes.setText("\n".join([msg, *made.notes]))
        self.main.say(msg)
        self.main._set_mod(self.mod_dir)

    def remove(self) -> None:
        which = self.which.currentText()
        if which == NEW:
            return
        game, mod_dir = self.game, self.mod_dir
        try:
            from ..mods.deploy import recomp_folders
            from ..profiles import locate
            root = locate(game).root
            patched = recomp_folders(root)["patched"]
            nw.remove_weapon(self.main.plain_tree(), mod_dir, which,
                             [patched] if patched.is_dir() else [])
        except Dr2Error as e:
            self.main.error(str(e))
            return
        self.which.removeItem(self.which.currentIndex())
        self.main.say(f"{which} removed from the mod")
        self.main._set_mod(self.mod_dir)

"""DR2 Studio's Variants panel: choose which head, shirt, colours… a model shows.

Why: a zombie model holds every look at once, and the game shows one choice per slot
(`dr2kit.convert.variants`). This panel sits beside the 3D view for any model that has
choices: one drop-down per slot (Head, Headwear, Shirt…), a tick box per on/off part
(wound caps, burnt…) and prop state (damaged, far-away copy), one drop-down per colour
choice (with a swatch of its main colour), the model's **Detail** levels (high, medium,
low: separate files the game swaps by distance), and three buttons: **Default** (the
first of each slot), **Random** (any look), **Show everything** (every part at once, as
the game never does; useful to see what's there).

The panel only edits a `variants.Choice`; `changed` tells the window, which hides and
shows parts in the 3D view at once and re-bakes the model when a colour changed
(docs/modding/17-variants.md).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..convert import variants as cvar


def _swatch(rgb) -> QIcon:
    pm = QPixmap(14, 14)
    pm.fill(QColor.fromRgbF(*(min(1.0, max(0.0, c)) for c in rgb[:3])))
    return QIcon(pm)


class VariantPanel(QScrollArea):
    """``changed(choice, colours_changed)`` when the user picks something;
    ``detail(asset id)`` when another detail level is chosen."""

    changed = Signal(object, bool)
    detail = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMinimumWidth(240)
        self.setMaximumWidth(320)
        self.mv: cvar.ModelVariants | None = None
        self._choice: cvar.Choice | None = None
        self._quiet = False
        self._body = QWidget()
        self.setWidget(self._body)
        self._lay = QVBoxLayout(self._body)
        self._lay.setContentsMargins(6, 6, 6, 6)
        title = QLabel("<b>Variants</b>")
        title.setToolTip("The game shows one choice per slot, never all at once")
        self._lay.addWidget(title)
        # the buttons first, so a long list of colours never hides them
        row = QHBoxLayout()
        self.btn_default = QPushButton("Default")
        self.btn_default.setToolTip("The first of each slot, accessories on, no wound caps, "
                                    "not burnt, own colours")
        self.btn_random = QPushButton("Random")
        self.btn_random.setToolTip("Any look, as the game could pick one")
        row.addWidget(self.btn_default)
        row.addWidget(self.btn_random)
        self._lay.addLayout(row)
        self.everything = QCheckBox("Show everything")
        self.everything.setToolTip("Every part at once (the game never shows this): to see "
                                   "what the model holds")
        self._lay.addWidget(self.everything)
        self.mask = QLabel()
        self.mask.setWordWrap(True)
        self.mask.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._lay.addWidget(self.mask)
        self._form = QFormLayout()
        self._lay.addLayout(self._form)
        self._colour_title = QLabel("<b>Colours</b>")
        self._colour_title.setToolTip("Other colours the game can give a piece of clothing")
        self._lay.addWidget(self._colour_title)
        self._colour_form = QFormLayout()
        self._lay.addLayout(self._colour_form)
        self._lay.addStretch(1)
        self.btn_default.clicked.connect(lambda: self._set(self.mv.default(), True))
        self.btn_random.clicked.connect(lambda: self._set(self.mv.random(), True))
        self.everything.toggled.connect(self._edited)
        self._slots: dict[str, QComboBox] = {}
        self._ticks: dict[str, QCheckBox] = {}
        self._colours: dict[str, QComboBox] = {}
        self._detail: QComboBox | None = None

    # -- filling --

    def set_model(self, mv: cvar.ModelVariants, choice: cvar.Choice,
                  levels: list | None = None, current_id: int | None = None,
                  swatches: dict | None = None) -> None:
        """Show ``mv``'s choices set to ``choice``. ``levels``: the model's detail levels
        (rows with ``id`` and ``detail``); ``swatches``: colour key → [rgb] per option
        (own first)."""
        self.mv = mv
        self._quiet = True
        for form in (self._form, self._colour_form):
            while form.rowCount():
                form.removeRow(0)
        self._slots.clear()
        self._ticks.clear()
        self._colours.clear()
        self._detail = None
        if levels:
            box = QComboBox()
            for r in levels:
                box.addItem(r["detail"], r["id"])
            box.setCurrentIndex(max(0, box.findData(current_id)))
            box.setToolTip("The game draws the high one close up and the others further "
                           "away (separate files)")
            box.currentIndexChanged.connect(lambda _i, b=box: self.detail.emit(b.currentData()))
            self._form.addRow("Detail", box)
            self._detail = box
        for key, nums in mv.slots.items():
            box = QComboBox()
            for n in nums:
                box.addItem(str(n), n)
            box.addItem("none", None)
            box.currentIndexChanged.connect(self._edited)
            self._form.addRow(cvar.SLOT[key].label, box)
            self._slots[key] = box
        for key in mv.toggles:
            t = cvar.TOGGLE[key]
            cb = QCheckBox(t.label)
            cb.setToolTip(t.hint)
            cb.toggled.connect(self._edited)
            self._form.addRow(cb)
            self._ticks[key] = cb
        for key in mv.states:
            cb = QCheckBox(cvar.PROP_STATE[key].label)
            cb.toggled.connect(self._edited)
            self._form.addRow(cb)
            self._ticks[key] = cb
        for col in mv.colours:
            box = QComboBox()
            sw = (swatches or {}).get(col.key, [])
            for n, name in enumerate([col.own] + col.options):
                label = "own colours" if n == 0 else f"choice {n}"
                if n < len(sw) and sw[n] is not None:
                    box.addItem(_swatch(sw[n]), label, n)
                else:
                    box.addItem(label, n)
                box.setItemData(n, name, Qt.ToolTipRole)
            box.currentIndexChanged.connect(lambda _i: self._edited(colour=True))
            box.setToolTip(f"{col.own}: the game can swap these colours in"
                           + ("" if col.listed is not False else " (not in its list)"))
            self._colour_form.addRow(col.key, box)
            self._colours[col.key] = box
        self._colour_title.setVisible(bool(mv.colours))
        has = bool(mv.has_choices)
        for w in (self.btn_default, self.btn_random, self.everything):
            w.setEnabled(has)
        self._quiet = False
        self._set(choice, False)

    def _set(self, choice: cvar.Choice, notify: bool) -> None:
        old = self._choice
        self._quiet = True
        for key, box in self._slots.items():
            box.setCurrentIndex(max(0, box.findData(choice.slots.get(key))))
        for key, cb in self._ticks.items():
            cb.setChecked(bool(choice.toggles.get(key, choice.states.get(key, False))))
        for key, box in self._colours.items():
            box.setCurrentIndex(max(0, box.findData(choice.colours.get(key, 0))))
        self.everything.setChecked(choice.everything)
        self._quiet = False
        self._choice = choice
        self._show_mask()
        if notify:
            self.changed.emit(choice, old is None or old.colours != choice.colours)

    # -- reading --

    def choice(self) -> cvar.Choice:
        """The choice the widgets show."""
        mv = self.mv
        c = cvar.Choice(
            slots={k: b.currentData() for k, b in self._slots.items()},
            toggles={k: cb.isChecked() for k, cb in self._ticks.items() if k in mv.toggles},
            states={k: cb.isChecked() for k, cb in self._ticks.items() if k in mv.states},
            colours={k: int(b.currentData() or 0) for k, b in self._colours.items()},
            everything=self.everything.isChecked())
        return c

    def _edited(self, *_args, colour: bool = False) -> None:
        if self._quiet or self.mv is None:
            return
        old = self._choice
        self._choice = self.choice()
        self._show_mask()
        self.changed.emit(self._choice, colour or (old is not None and
                                                   old.colours != self._choice.colours))

    def _show_mask(self) -> None:
        mv, c = self.mv, self._choice
        if mv is None or c is None:
            return
        shown = sum(mv.shown(c))
        text = f"{shown} of {len(mv.parts)} parts shown"
        if mv.zombie and not c.everything:
            text += f"<br><small>the game's hide mask: {mv.hide_mask(c):#018x}</small>"
        self.mask.setText(text)

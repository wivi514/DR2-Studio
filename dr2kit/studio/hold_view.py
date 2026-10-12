"""DR2 Studio's "Chuck holding it" view: a weapon in Chuck's hand, in 3D (phase 13.2).

Why: the weapon wizard's flat picture showed the new shape over the game weapon, but not
Chuck; lining a model up with his hands, and an effect along the blade, is easier when
he holds it as the game will show him standing still (user, 2026-10-12: "be able to
place it on Chuck in 3d view to the weapon mods we make so we properly align stuff").

What it shows (``web/hold.html`` + ``hold.js``, three.js in a QWebEngineView served by
the ``dr2:`` scheme as `model_view` does): Chuck's parts at rest (`convert.holding
.rest_glb`, sent once per game), posed by the page with the first frame of the game's
idle for the weapon's kind (`convert.holding.idle_pose`); the weapon's ``.glb`` hung from
his right-hand prop node by its grip node (`mods.newweapon.hold_scene`); the grip nodes
(red), the effect point (yellow, its line along the blade) and the effects playing (a
sketch: `hold.js`).

The **handles** (*Slide*, *Turn*, *Length*, *Effect point*) move the weapon along its
line, spin it about its length, scale it from its handle end, or slide the effect point
along the blade; when one is let go the page says the new value (``dr2:align {…}``) and
`aligned` carries it to the wizard, which puts it in its boxes and fits the model again.

Without QtWebEngine the view shows a note; the wizard keeps its flat picture.
"""

from __future__ import annotations

import json

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QHBoxLayout, QLabel, QPushButton,
                               QToolButton, QVBoxLayout, QWidget)

from . import model_view

PAGE_URL = "dr2://studio/hold.html"
MODES = (("look", "Look", "Turn the view around (drag) and zoom (wheel); nothing moves"),
         ("slide", "Slide", "Drag the arrow to slide the weapon along its length in his hand"),
         ("turn", "Turn", "Drag the ring to spin the weapon about its length"),
         ("length", "Length", "Drag the handle to make the weapon longer or shorter (from "
                              "its handle end)"),
         ("effect", "Effect point", "Drag the arrow to move where the effects on the weapon "
                                    "start, along the blade"))


class HoldView(QWidget):
    """The 3D view (module docstring). `show_scene` shows a `newweapon.HoldScene`."""

    aligned = Signal(dict)            # {"slide": m} / {"turn": °} / {"length": m} / {"effect_start": m}
    status = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        self.modes = QButtonGroup(self)
        self.modes.setExclusive(True)
        for i, (mid, label, tip) in enumerate(MODES):
            b = QToolButton()
            b.setText(label)
            b.setToolTip(tip)
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.setProperty("mode", mid)
            self.modes.addButton(b, i)
            bar.addWidget(b)
        bar.addSpacing(12)
        self.show_chuck = QCheckBox("Chuck")
        self.show_fx = QCheckBox("Effects")
        self.show_marks = QCheckBox("Grips")
        for c in (self.show_chuck, self.show_fx, self.show_marks):
            c.setChecked(True)
            bar.addWidget(c)
        reset = QPushButton("Reset view")
        bar.addStretch(1)
        bar.addWidget(reset)
        lay.addLayout(bar)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.ready = False
        self.last_message = ""
        self._pending: list[str] = []
        self._serial = 0
        self._chuck_game: str | None = None
        self.view = None
        if model_view.WEB_ENGINE and model_view._registered:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            self._profile, self._handler = model_view._profile_and_handler()
            self.view = QWebEngineView(self)
            self._page = model_view._Page(self._profile, self._message, self.view)
            self.view.setPage(self._page)
            self.view.load(QUrl(PAGE_URL))
            lay.addWidget(self.view, 1)
            self.modes.idClicked.connect(
                lambda i: self._js(f"dr2.setMode('{MODES[i][0]}')"))
            self.show_chuck.toggled.connect(lambda on: self._js(f"dr2.show('chuck', {str(on).lower()})"))
            self.show_fx.toggled.connect(lambda on: self._js(f"dr2.show('effects', {str(on).lower()})"))
            self.show_marks.toggled.connect(lambda on: self._js(f"dr2.show('grips', {str(on).lower()})"))
            reset.clicked.connect(lambda: self._js("dr2.resetView()"))
        else:
            why = model_view.WEB_ENGINE_ERROR or "the dr2: scheme could not be registered"
            note = QLabel("Chuck holding the weapon in 3D needs PySide6's QtWebEngine ("
                          + why + ").")
            note.setWordWrap(True)
            lay.addWidget(note, 1)
            for w in (*self.modes.buttons(), self.show_chuck, self.show_fx, self.show_marks,
                      reset):
                w.setEnabled(False)
        lay.addWidget(self.info)

    @property
    def available(self) -> bool:
        return self.view is not None

    def _serve(self, name: str, data: bytes) -> str:
        """Put bytes at a fresh ``dr2://studio/hold/…`` address (no stale cache)."""
        self._serial += 1
        path = f"/hold/{self._serial}/{name}"
        self._handler.files[path] = data
        return f"dr2://studio{path}"

    def needs_chuck(self, game: str) -> bool:
        """True until Chuck's model for ``game`` was sent (`set_chuck`)."""
        return self.view is not None and self._chuck_game != game

    def set_chuck(self, game: str, glb: bytes) -> None:
        """Chuck's parts at rest (`convert.holding.rest_glb`)."""
        if self.view is None:
            return
        self._chuck_game = game
        self._js(f"dr2.setChuck('{self._serve('chuck.glb', glb)}')")

    def show_scene(self, scene, keep_view: bool = True) -> None:
        """Show a `mods.newweapon.HoldScene`: the pose, the weapon and its effects."""
        if self.view is None:
            return
        for k in [k for k in self._handler.files if k.startswith("/hold/")]:
            if not k.endswith("/chuck.glb"):
                del self._handler.files[k]               # the previous weapon's files
        weapon = self._serve("weapon.glb", scene.weapon_glb)
        self._js("dr2.setPose(" + json.dumps(scene.pose) + ")")
        self._js(f"dr2.setWeapon('{weapon}', {json.dumps(scene.placement)}, "
                 f"{json.dumps(scene.frame)}, {json.dumps(scene.effect_point)}, "
                 f"{str(keep_view).lower()})")
        self.set_effects(scene.effects, scene.textures)
        idle = scene.idle.fullbody.rsplit("/", 1)[-1].removesuffix(".anm")
        hand = scene.idle.hand.rsplit("/", 1)[-1].removesuffix(".anm") if scene.idle.hand \
            else "none"
        self.info.setText(f"<small>Chuck in the game's idle for this kind: <b>{idle}</b> "
                          f"(first frame), hands <b>{hand}</b>. Red: the grip nodes his "
                          f"hands follow; yellow: where effects on the weapon start (+y "
                          f"along the blade).</small>")

    def set_effects(self, effects: list, textures: dict) -> None:
        """Only the effects (`newweapon.effect_view` dicts; ``textures``: particle picture
        name -> PNG bytes): the Effects window's sliders."""
        if self.view is None:
            return
        pictures = {n: self._serve(f"fx/{n}.png", png) for n, png in textures.items()}
        self._js(f"dr2.setEffects({json.dumps(effects)}, {json.dumps(pictures)})")

    def _js(self, code: str) -> None:
        if self.view is None:
            return
        if self.ready:
            self.view.page().runJavaScript(code)
        else:
            self._pending.append(code)

    def _message(self, text: str) -> None:
        self.last_message = text
        word, _, rest = text.partition(" ")
        if text == "ready":
            self.ready = True
            for code in self._pending:
                self.view.page().runJavaScript(code)
            self._pending.clear()
        elif word == "align":
            try:
                self.aligned.emit(json.loads(rest))
            except ValueError:
                pass
        else:
            self.status.emit(text)

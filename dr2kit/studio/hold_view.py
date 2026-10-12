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

**Moves** (phase 14): the *Move* box plays the weapon's attacks (its ``items.txt``
``AnimationAttackName…`` in its ``AnimBankName`` bank, every key read:
`convert.holding.clip`), looping, the weapon following his right-hand prop node; *Pause*
stops on a frame and the slider goes to any moment; *In place* takes out how far the move
carries him (the game moves him: a 360° slash travels 2 m). *Standing still* goes back to the
idle. With ``tools=False`` (the Library's animation view, `show_animation`) the handles,
effects and grips are hidden and any animation plays on Chuck, or on its rig drawn as
bones when it is not Chuck's (zombies, cutscene props, cameras).

Without QtWebEngine the view shows a note; the wizard keeps its flat picture.
"""

from __future__ import annotations

import json

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QHBoxLayout, QLabel,
                               QPushButton, QSlider, QToolButton, QVBoxLayout, QWidget)

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

    def __init__(self, parent=None, tools: bool = True):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.tools = tools
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
        play = QHBoxLayout()
        self.move = QComboBox()
        self.move.setToolTip("Play one of the weapon's moves (every key of the game's "
                             "animation), the weapon in his hand")
        self.move.addItem("Standing still", None)
        self.pause = QCheckBox("Pause")
        self.in_place = QCheckBox("In place")
        self.in_place.setChecked(True)
        self.in_place.setToolTip("Take out how far the move carries him (the game moves him "
                                 "that far): he stays where he stands")
        self.bones = QCheckBox("Bones")
        self.bones.setToolTip("Draw the rig as lines")
        self.time = QSlider(Qt.Horizontal)
        self.time.setRange(0, 1000)
        self.time.setToolTip("Go to a moment of the move (pauses it)")
        self.time_label = QLabel("")
        play.addWidget(QLabel("Move:"))
        play.addWidget(self.move, 1)
        play.addWidget(self.pause)
        play.addWidget(self.time, 2)
        play.addWidget(self.time_label)
        play.addWidget(self.in_place)
        play.addWidget(self.bones)
        lay.addLayout(play)
        self._clips: list = [None]
        if not tools:
            for w in (*self.modes.buttons(), self.show_fx, self.show_marks):
                w.hide()
            self.show_chuck.setText("Model")
            self.move.setToolTip("The animation shown")
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
            self.move.currentIndexChanged.connect(self._move_chosen)
            self.pause.toggled.connect(lambda on: self._js(f"dr2.pauseClip({str(on).lower()})"))
            self.bones.toggled.connect(lambda on: self._js(f"dr2.setBones({str(on).lower()})"))
            self.in_place.toggled.connect(
                lambda on: self._js(f"dr2.setInPlace({str(on).lower()})"))
            self.time.sliderMoved.connect(self._seek)
            self._tick = QTimer(self)
            self._tick.setInterval(100)
            self._tick.timeout.connect(self._poll)
        else:
            why = model_view.WEB_ENGINE_ERROR or "the dr2: scheme could not be registered"
            note = QLabel("Chuck holding the weapon in 3D needs PySide6's QtWebEngine ("
                          + why + ").")
            note.setWordWrap(True)
            lay.addWidget(note, 1)
            for w in (*self.modes.buttons(), self.show_chuck, self.show_fx, self.show_marks,
                      reset, self.move, self.pause, self.bones, self.time, self.in_place):
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
        self.set_moves(getattr(scene, "moves", []) or [])
        idle = scene.idle.fullbody.rsplit("/", 1)[-1].removesuffix(".anm")
        hand = scene.idle.hand.rsplit("/", 1)[-1].removesuffix(".anm") if scene.idle.hand \
            else "none"
        self.info.setText(f"<small>Chuck in the game's idle for this kind: <b>{idle}</b> "
                          f"(first frame), hands <b>{hand}</b>. Red: the grip nodes his "
                          f"hands follow; yellow: where effects on the weapon start (+y "
                          f"along the blade).</small>")

    def set_moves(self, moves: list, keep: bool = True) -> None:
        """The *Move* box's choices: ``[(label, clip)]`` (`convert.holding.clip`) after
        *Standing still*. ``keep``: stay on the move of the same label if there is one."""
        was = self.move.currentText() if keep else ""
        self.move.blockSignals(True)
        self.move.clear()
        self.move.addItem("Standing still" if self.tools else "(nothing)", None)
        self._clips = [None]
        for label, clp in moves:
            self.move.addItem(label)
            self._clips.append(clp)
        i = self.move.findText(was) if was else -1
        self.move.setCurrentIndex(max(i, 0))
        self.move.blockSignals(False)
        self._move_chosen(self.move.currentIndex())

    def show_animation(self, game: str, body_glb: bytes | None, label: str, clp: dict,
                       body_key: str = "chuck") -> None:
        """The Library's animation view: ``clp`` played on ``body_glb`` (Chuck's parts, or
        a skeleton's bones; None: the one already shown for ``body_key``)."""
        if self.view is None:
            return
        key = f"{game}:{body_key}"
        self._js("dr2.show('grips', false)")
        if body_glb is not None and self._chuck_game != key:
            self._chuck_game = key
            self._js(f"dr2.setChuck('{self._serve('chuck.glb', body_glb)}')")
        self.bones.setChecked(body_key != "chuck")
        self.set_moves([(label, clp)], keep=False)
        self.move.setCurrentIndex(1)

    def body_shown(self, game: str, body_key: str) -> bool:
        return self._chuck_game == f"{game}:{body_key}"

    def _move_chosen(self, i: int) -> None:
        clp = self._clips[i] if 0 <= i < len(self._clips) else None
        self.pause.blockSignals(True)
        self.pause.setChecked(False)
        self.pause.blockSignals(False)
        self._js("dr2.playClip(" + json.dumps(clp) + ")")
        if self.view is not None:
            (self._tick.start if clp else self._tick.stop)()
        if not clp:
            self.time_label.setText("")

    def _seek(self, v: int) -> None:
        if not self.pause.isChecked():
            self.pause.setChecked(True)
        self._js(f"dr2.seekClip({v / 1000:.4f})")

    def _poll(self) -> None:
        if not self.ready or not self.isVisible():
            return
        self.view.page().runJavaScript("JSON.stringify(dr2.clipState())", 0, self._clip_state)

    def _clip_state(self, text) -> None:
        try:
            st = json.loads(text) if isinstance(text, str) else None
        except ValueError:
            st = None
        if not st or not st.get("length"):
            return
        if not self.time.isSliderDown():
            self.time.blockSignals(True)
            self.time.setValue(int(1000 * st["time"] / st["length"]))
            self.time.blockSignals(False)
        self.time_label.setText(f"{st['time']:.2f} / {st['length']:.2f} s")

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

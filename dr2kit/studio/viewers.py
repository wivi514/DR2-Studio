"""DR2 Studio's centre pane: one viewer per kind of asset.

* `TextureViewer`: the texture decoded to pixels, with zoom (wheel, or the zoom box),
  a channel picker (RGBA over a checkerboard, RGB, R, G, B, A as grey), the mip level and
  the cube face. Decoding goes through `dr2kit.convert.texture`, the same code the CLI
  and the mod builder use, so what you see is what a PNG export gives.
* `PlainViewer`: text assets as text, anything else as a hex dump of its first bytes.

No format knowledge here: viewers ask `dr2kit` for pixels or bytes and show them.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView,
                               QHBoxLayout, QLabel, QPlainTextEdit, QSpinBox, QVBoxLayout,
                               QWidget)

from ..convert.texture import decode_level
from ..formats.bct import Bct

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

CHANNELS = ["RGBA", "RGB", "R", "G", "B", "A"]


def _checkerboard(size: int = 16) -> QBrush:
    pm = QPixmap(size * 2, size * 2)
    pm.fill(QColor(200, 200, 200))
    p = QPainter(pm)
    p.fillRect(0, 0, size, size, QColor(150, 150, 150))
    p.fillRect(size, size, size, size, QColor(150, 150, 150))
    p.end()
    return QBrush(pm)


def channel_view(rgba: bytes, mode: str) -> bytes:
    """RGBA bytes rearranged for display: one channel as grey, or alpha forced opaque."""
    if mode == "RGBA":
        return rgba
    if np is not None:
        a = np.frombuffer(rgba, np.uint8).reshape(-1, 4).copy()
        if mode == "RGB":
            a[:, 3] = 255
        else:
            c = a[:, "RGBA".index(mode)].copy()
            a[:, 0] = a[:, 1] = a[:, 2] = c
            a[:, 3] = 255
        return a.tobytes()
    out = bytearray(rgba)
    if mode == "RGB":
        out[3::4] = b"\xff" * (len(rgba) // 4)
    else:
        c = rgba["RGBA".index(mode)::4]
        out[0::4] = out[1::4] = out[2::4] = c
        out[3::4] = b"\xff" * len(c)
    return bytes(out)


class _ZoomView(QGraphicsView):
    zoomed = Signal(float)

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(_checkerboard())
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.item = QGraphicsPixmapItem()
        self.item.setTransformationMode(Qt.FastTransformation)   # see texels, not a blur
        self.scene().addItem(self.item)
        self.scale_ = 1.0

    def set_scale(self, s: float) -> None:
        s = max(0.05, min(64.0, s))
        self.resetTransform()
        self.scale(s, s)
        self.scale_ = s
        self.zoomed.emit(s)

    def wheelEvent(self, ev):
        self.set_scale(self.scale_ * (1.25 if ev.angleDelta().y() > 0 else 0.8))


class TextureViewer(QWidget):
    """Shows one texture; ``show_texture(bct)`` loads it."""

    def __init__(self):
        super().__init__()
        self.tex: Bct | None = None
        self.view = _ZoomView()
        self.channel = QComboBox()
        self.channel.addItems(CHANNELS)
        self.level = QSpinBox()
        self.level.setPrefix("mip ")
        self.face = QSpinBox()
        self.face.setPrefix("face ")
        self.zoom = QComboBox()
        self.zoom.setEditable(False)
        for z in ("fit", "25%", "50%", "100%", "200%", "400%", "800%"):
            self.zoom.addItem(z)
        self.info = QLabel()
        bar = QHBoxLayout()
        for w in (QLabel("Show"), self.channel, self.level, self.face, QLabel("Zoom"),
                  self.zoom, self.info):
            bar.addWidget(w)
        bar.addStretch(1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(bar)
        lay.addWidget(self.view, 1)
        self.channel.currentTextChanged.connect(self.refresh)
        self.level.valueChanged.connect(self.refresh)
        self.face.valueChanged.connect(self.refresh)
        self.zoom.currentTextChanged.connect(self._zoom_box)
        self.view.zoomed.connect(lambda s: self.info.setText(self._describe() + f"   {s:.0%}"))

    def show_texture(self, tex: Bct) -> None:
        self.tex = tex
        h = tex.header
        for spin, top in ((self.level, h.levels - 1), (self.face, h.faces - 1)):
            spin.blockSignals(True)
            spin.setRange(0, top)
            spin.setValue(0)
            spin.setEnabled(top > 0)
            spin.blockSignals(False)
        self.refresh()
        self._zoom_box(self.zoom.currentText())

    def _describe(self) -> str:
        if not self.tex:
            return ""
        h = self.tex.header
        lv = self.tex.level(self.level.value(), self.face.value())
        return (f"{self.tex.format.name}  {h.width}×{h.height}  level {lv.level}: "
                f"{lv.width}×{lv.height}")

    def refresh(self) -> None:
        if not self.tex:
            return
        lv = self.tex.level(self.level.value(), self.face.value())
        rgba = channel_view(decode_level(self.tex, lv), self.channel.currentText())
        img = QImage(rgba, lv.width, lv.height, lv.width * 4, QImage.Format_RGBA8888).copy()
        self.view.item.setPixmap(QPixmap.fromImage(img))
        self.view.scene().setSceneRect(0, 0, lv.width, lv.height)
        self.info.setText(self._describe() + f"   {self.view.scale_:.0%}")

    def _zoom_box(self, text: str) -> None:
        if text == "fit" and self.tex:
            r = self.view.scene().sceneRect()
            vw, vh = max(1, self.view.viewport().width() - 4), max(1, self.view.viewport().height() - 4)
            self.view.set_scale(min(vw / max(1, r.width()), vh / max(1, r.height()), 8.0))
        elif text.endswith("%"):
            self.view.set_scale(int(text[:-1]) / 100)


class PlainViewer(QPlainTextEdit):
    """Text as text; anything else as a hex dump of the first 4 KB."""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        f = QFont("monospace")
        f.setStyleHint(QFont.Monospace)
        self.setFont(f)

    def show_bytes(self, data: bytes, is_text: bool) -> None:
        if is_text:
            self.setPlainText(data[:2_000_000].decode("latin-1"))
            return
        lines = []
        for i in range(0, min(len(data), 4096), 16):
            chunk = data[i:i + 16]
            asc = "".join(chr(c) if 32 <= c < 127 else "." for c in chunk)
            lines.append(f"{i:08x}  {chunk.hex(' '):<47}  {asc}")
        if len(data) > 4096:
            lines.append(f"… {len(data) - 4096:,} more bytes")
        self.setPlainText("\n".join(lines))

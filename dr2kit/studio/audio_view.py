"""DR2 Studio's audio view: a sound's waveform, and playback.

Hearing a sound before extracting it is half of phase 5 (docs/roadmap.md). The view:

* draws the waveform (min/max per pixel column, one lane per channel) with the loop
  region shaded and a play head;
* plays the sound through Qt Multimedia's `QAudioSink` (16-bit PCM from a `QBuffer`);
  5.1 sounds are mixed down to stereo for listening (front + 0.7 × centre and surround);
* *Loop* replays the loop region the game would loop (or the whole sound) until
  *Stop*; clicking the waveform starts playback from there.

Decoding is `dr2kit.convert.audio.decode` (the same code as ``dr2 extract --wav``), done
by the caller in a worker thread; this widget only receives a `Pcm`. Qt Multimedia is
part of PySide6; if it can't open an output device the waveform still shows and the
view says why there is no sound.
"""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from ..convert.audio import Pcm

try:
    import numpy as np
except ImportError:  # pragma: no cover - Studio installs numpy
    np = None

try:
    from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSink, QMediaDevices
except ImportError:  # pragma: no cover - a PySide6 build without Qt Multimedia
    QAudioSink = None


# Lane labels: XMA2's channel order (stereo pairs: front, centre + LFE, surround).
CHANNEL_NAMES = {2: ["L", "R"], 6: ["L", "R", "C", "LFE", "Ls", "Rs"]}


def playback_bytes(pcm: Pcm) -> tuple[bytes, int]:
    """Interleaved 16-bit samples to play and their channel count (≤ 2)."""
    if pcm.channels <= 2 or np is None:
        return pcm.samples, pcm.channels
    a = np.frombuffer(pcm.samples, "<i2").reshape(-1, pcm.channels).astype(np.float32)
    left = a[:, 0] + 0.7 * a[:, 2] + (0.7 * a[:, 4] if pcm.channels > 4 else 0)
    right = a[:, 1] + 0.7 * a[:, 2] + (0.7 * a[:, 5] if pcm.channels > 5 else 0)
    out = np.clip(np.stack([left, right], 1), -32768, 32767).astype("<i2")
    return out.tobytes(), 2


def envelope(pcm: Pcm, columns: int) -> list:
    """Per channel, ``columns`` (min, max) pairs in -1..1: what the waveform draws."""
    if np is None or not pcm.frames:
        return []
    a = np.frombuffer(pcm.samples, "<i2").reshape(-1, pcm.channels)
    n = len(a)
    cols = max(1, min(columns, n))
    edges = np.linspace(0, n, cols + 1).astype(int)
    out = []
    for c in range(pcm.channels):
        ch = a[:, c].astype(np.float32) / 32768.0
        lo = np.minimum.reduceat(ch, edges[:-1])
        hi = np.maximum.reduceat(ch, edges[:-1])
        out.append(list(zip(lo.tolist(), hi.tolist())))
    return out


class Waveform(QWidget):
    """The waveform strip; emits ``seek(sample)`` when clicked."""
    seek = Signal(int)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.pcm: Pcm | None = None
        self.loop: tuple[int, int] | None = None
        self.head = -1
        self._env: list = []
        self._env_width = 0

    def set_sound(self, pcm: Pcm | None, loop: tuple[int, int] | None) -> None:
        self.pcm, self.loop, self.head = pcm, loop, -1
        self._env, self._env_width = [], 0
        self.update()

    def set_head(self, sample: int) -> None:
        self.head = sample
        self.update()

    def mousePressEvent(self, ev):
        if self.pcm and self.pcm.frames and self.width() > 0:
            x = max(0.0, min(1.0, ev.position().x() / self.width()))
            self.seek.emit(int(x * self.pcm.frames))

    def paintEvent(self, _ev):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(24, 26, 30))
        if not self.pcm or not self.pcm.frames:
            p.setPen(QColor(150, 150, 150))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, "no audio")
            return
        n = self.pcm.frames
        if self.loop:
            a, b = self.loop
            p.fillRect(QRectF(a / n * w, 0, max(1.0, (b - a) / n * w), h), QColor(40, 60, 45))
        if self._env_width != w:
            self._env, self._env_width = envelope(self.pcm, w), w
        lanes = max(1, len(self._env))
        lane_h = h / lanes
        names = CHANNEL_NAMES.get(lanes, [])
        for c, cols in enumerate(self._env):
            mid = lane_h * (c + 0.5)
            half = lane_h * 0.45
            p.setPen(QPen(QColor(110, 190, 255), 1))
            for x, (lo, hi) in enumerate(cols):
                p.drawLine(QPointF(x, mid - hi * half), QPointF(x, mid - lo * half))
            if c < len(names):
                p.setPen(QColor(200, 200, 200))
                p.drawText(QPointF(4, lane_h * c + 14), names[c])
        if self.head >= 0:
            p.setPen(QPen(QColor(255, 210, 80), 2))
            x = self.head / n * w
            p.drawLine(QPointF(x, 0), QPointF(x, h))


class AudioViewer(QWidget):
    """Shows and plays one sound; ``show_sound(pcm, loop, title)`` loads it."""

    def __init__(self):
        super().__init__()
        self.pcm: Pcm | None = None
        self.loop: tuple[int, int] | None = None
        self.wave = Waveform()
        self.title = QLabel()
        self.play_btn = QPushButton("Play")
        self.stop_btn = QPushButton("Stop")
        self.loop_box = QCheckBox("Loop")
        self.time = QLabel()
        self.note = QLabel()
        self.note.setWordWrap(True)
        bar = QHBoxLayout()
        for wd in (self.play_btn, self.stop_btn, self.loop_box, self.time):
            bar.addWidget(wd)
        bar.addStretch(1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.title)
        lay.addLayout(bar)
        lay.addWidget(self.wave, 1)
        lay.addWidget(self.note)
        self.play_btn.clicked.connect(lambda: self.play(self.wave.head if self.wave.head > 0 else 0))
        self.stop_btn.clicked.connect(self.stop)
        self.wave.seek.connect(self.play)
        self._sink = None
        self._buffer: QBuffer | None = None
        self._bytes = QByteArray()
        self._frame_bytes = 4
        self._start = 0
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)
        self.available = QAudioSink is not None and bool(QMediaDevices.audioOutputs())
        if not self.available:
            self.note.setText("No audio output device (or Qt Multimedia is missing): the "
                              "waveform shows, but nothing can play. Export WAV to listen.")
        self._update()

    # --- loading
    def show_sound(self, pcm: Pcm, loop: tuple[int, int] | None, title: str) -> None:
        self.stop()
        self.pcm, self.loop = pcm, loop
        data, ch = playback_bytes(pcm)
        self._bytes = QByteArray(data)
        self._play_channels = ch
        self._frame_bytes = 2 * ch
        self.wave.set_sound(pcm, loop)
        self.loop_box.setChecked(loop is not None)
        layout = {1: "mono", 2: "stereo", 6: "5.1"}.get(pcm.channels, f"{pcm.channels} ch")
        self.title.setText(f"<b>{title}</b>  {layout}, {pcm.rate} Hz, {pcm.seconds:.2f} s"
                           + (f", loops {loop[0] / pcm.rate:.2f}–{loop[1] / pcm.rate:.2f} s"
                              if loop else ""))
        self._update()

    def clear(self) -> None:
        self.stop()
        self.pcm = None
        self.wave.set_sound(None, None)
        self.title.setText("")
        self._update()

    # --- playback
    def play(self, start: int = 0) -> None:
        self.stop()
        if not self.pcm or not self.available or not self.pcm.frames:
            self.wave.set_head(start)
            return
        fmt = QAudioFormat()
        fmt.setSampleRate(self.pcm.rate)
        fmt.setChannelCount(self._play_channels)
        fmt.setSampleFormat(QAudioFormat.Int16)
        self._sink = QAudioSink(QMediaDevices.defaultAudioOutput(), fmt, self)
        self._sink.stateChanged.connect(self._state)
        self._buffer = QBuffer(self)
        self._buffer.setData(self._bytes)
        self._buffer.open(QIODevice.ReadOnly)
        self._start = max(0, min(start, self.pcm.frames - 1))
        self._buffer.seek(self._start * self._frame_bytes)
        self._sink.start(self._buffer)
        self._timer.start()
        self._update()

    def stop(self) -> None:
        self._timer.stop()
        if self._sink is not None:
            self._sink.stateChanged.disconnect(self._state)
            self._sink.stop()
            self._sink.deleteLater()
            self._sink = None
        if self._buffer is not None:
            self._buffer.close()
            self._buffer = None
        self._update()

    @property
    def playing(self) -> bool:
        return self._sink is not None

    def _state(self, state) -> None:
        if state == QAudio.IdleState:            # reached the end of the buffer
            if self.loop_box.isChecked() and self.pcm:
                self.play(self.loop[0] if self.loop else 0)
            else:
                self.stop()

    def _tick(self) -> None:
        if self._sink is None or not self.pcm:
            return
        played = int(self._sink.processedUSecs() * self.pcm.rate / 1_000_000)
        pos = self._start + played
        if self.loop and self.loop_box.isChecked() and pos >= self.loop[1]:
            self.play(self.loop[0])
            return
        self.wave.set_head(pos)
        self.time.setText(f"{pos / self.pcm.rate:6.2f} / {self.pcm.seconds:.2f} s")

    def _update(self) -> None:
        has = self.pcm is not None and self.available
        self.play_btn.setEnabled(has and not self.playing)
        self.stop_btn.setEnabled(self.playing)
        if self.pcm and not self.playing:
            self.time.setText(f"{self.pcm.seconds:.2f} s")

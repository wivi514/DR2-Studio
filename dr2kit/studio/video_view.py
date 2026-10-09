"""DR2 Studio's video view: play a Bink movie (Case West's ``data/movies``).

The pictures come from `dr2kit.convert.video.frames` (ffmpeg through PyAV), decoded on
the GUI thread one at a time as the clock reaches them (a 1280×720 frame takes a few
milliseconds). The sound is decoded once by the caller, in a worker thread
(`dr2kit.convert.video.audio`, 5.1 mixed to stereo), and played through `QAudioSink`;
while it plays, the sink's position is the clock, so picture and sound stay together.
Without an audio device, a timer is the clock and the movie plays silently.
"""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QElapsedTimer, QIODevice, Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QSlider, QVBoxLayout, QWidget)

from ..convert import video
from ..convert.audio import Pcm

try:
    from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices
except ImportError:  # pragma: no cover - a PySide6 build without Qt Multimedia
    QAudioSink = None


class VideoViewer(QWidget):
    """Shows and plays one movie: ``show_movie(data, info, pcm, title)``."""

    def __init__(self):
        super().__init__()
        self.data: bytes | None = None
        self.info: video.VideoInfo | None = None
        self.pcm: Pcm | None = None
        self.title = QLabel()
        self.picture = QLabel()
        self.picture.setAlignment(Qt.AlignCenter)
        self.picture.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.picture.setStyleSheet("background: black")
        self.play_btn = QPushButton("Play")
        self.loop_box = QCheckBox("Loop")
        self.slider = QSlider(Qt.Horizontal)
        self.time = QLabel()
        self.note = QLabel()
        self.note.setWordWrap(True)
        bar = QHBoxLayout()
        bar.addWidget(self.play_btn)
        bar.addWidget(self.loop_box)
        bar.addWidget(self.slider, 1)
        bar.addWidget(self.time)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.title)
        lay.addWidget(self.picture, 1)
        lay.addLayout(bar)
        lay.addWidget(self.note)
        self.play_btn.clicked.connect(self.toggle)
        self.slider.sliderReleased.connect(lambda: self.seek(self.slider.value() / 1000))
        self._frames = None
        self._image: QImage | None = None
        self._pos = 0.0                  # seconds shown
        self._start = 0.0                # where the clock started
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(10)
        self._timer.timeout.connect(self._tick)
        self._sink = None
        self._buffer: QBuffer | None = None
        self.audio_ok = QAudioSink is not None and bool(QMediaDevices.audioOutputs())

    def show_movie(self, data: bytes, info: video.VideoInfo, pcm: Pcm | None,
                   title: str) -> None:
        self.stop()
        self.data, self.info, self.pcm = data, info, pcm
        self.title.setText(f"<b>{title}</b>  {info.describe()}")
        self.slider.setRange(0, int(info.seconds * 1000))
        self.loop_box.setChecked("loop" in title.lower() or "monitor" in title.lower())
        self.note.setText("" if pcm is None or self.audio_ok else
                          "No audio output device: the movie plays without sound.")
        self.seek(0.0, play=False)

    def clear(self) -> None:
        self.stop()
        self.data = self.info = self.pcm = None
        self.picture.clear()
        self.title.setText("")

    @property
    def playing(self) -> bool:
        return self._timer.isActive()

    def toggle(self) -> None:
        if self.playing:
            self.stop()
        elif self.data is not None:
            self.seek(0.0 if self._pos >= self.info.seconds - 0.05 else self._pos)

    def seek(self, seconds: float, play: bool = True) -> None:
        """Show the picture at ``seconds``; with ``play``, play from there."""
        self.stop()
        if self.data is None:
            return
        self._frames = video.frames(self.data, seconds)
        self._next = next(self._frames, None)
        self._show_next()
        self._start = seconds
        if play:
            self._clock.start()
            self._start_sound(seconds)
            self._timer.start()
            self.play_btn.setText("Pause")

    def stop(self) -> None:
        self._timer.stop()
        self.play_btn.setText("Play")
        if self._sink is not None:
            self._sink.stop()
            self._sink.deleteLater()
            self._sink = None
        if self._buffer is not None:
            self._buffer.close()
            self._buffer = None

    def _start_sound(self, seconds: float) -> None:
        if self.pcm is None or not self.audio_ok:
            return
        fmt = QAudioFormat()
        fmt.setSampleRate(self.pcm.rate)
        fmt.setChannelCount(self.pcm.channels)
        fmt.setSampleFormat(QAudioFormat.Int16)
        self._sink = QAudioSink(QMediaDevices.defaultAudioOutput(), fmt, self)
        self._buffer = QBuffer(self)
        self._buffer.setData(QByteArray(self.pcm.samples))
        self._buffer.open(QIODevice.ReadOnly)
        self._buffer.seek(int(seconds * self.pcm.rate) * 2 * self.pcm.channels)
        self._sink.start(self._buffer)

    def _now(self) -> float:
        if self._sink is not None:
            return self._start + self._sink.processedUSecs() / 1e6
        return self._start + self._clock.elapsed() / 1000

    def _show_next(self) -> None:
        if self._next is not None:
            self._display(self._next)
            self._next = next(self._frames, None)

    def _display(self, frame) -> None:
        t, w, h, rgb = frame
        self._image = QImage(rgb, w, h, 3 * w, QImage.Format_RGB888).copy()
        self._pos = t
        self._paint()

    def _tick(self) -> None:
        now = self._now()
        due = None
        while self._next is not None and self._next[0] <= now:   # behind: skip pictures
            due = self._next
            self._next = next(self._frames, None)
        if due is not None:
            self._display(due)
        if self._next is None and now >= self.info.seconds:
            if self.loop_box.isChecked():
                self.seek(0.0)
            else:
                self.stop()
        if not self.slider.isSliderDown():
            self.slider.setValue(int(self._pos * 1000))

    def _paint(self) -> None:
        if self._image is None:
            return
        pm = QPixmap.fromImage(self._image).scaled(self.picture.size(), Qt.KeepAspectRatio,
                                                    Qt.SmoothTransformation)
        self.picture.setPixmap(pm)
        self.time.setText(f"{self._pos:6.2f} / {self.info.seconds:.2f} s")

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._paint()

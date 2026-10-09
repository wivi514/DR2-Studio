"""Bink movies (`.bik`, Case West only): look at them, listen to them, export them.

Case West ships ten Bink movies in ``data/movies`` (the intro, the logo, and the six
512×512 security-monitor loops of the labs). ffmpeg decodes Bink video and audio, and
PyAV (``pip install av``, the same optional dependency as sounds) gives us ffmpeg, so this
module only arranges what it decodes:

* `probe` → `VideoInfo` (size, frame rate, length, audio tracks);
* `frames` yields every picture as RGB (DR2 Studio's video view draws them);
* `audio` decodes the sound to a `dr2kit.convert.audio.Pcm`, mixed to stereo;
* `to_mp4` writes an ``.mp4`` anyone can play (``dr2 extract --mp4``).

**Audio tracks** (measured on the four movies with sound): a 5.1 movie carries four
Bink tracks, stereo + mono + mono + stereo = front left/right, centre, LFE (bass: 90 %
of its energy under 200 Hz, nearly silent), surround left/right. `audio` mixes them to
stereo with the usual weights (centre and surrounds at −3 dB, LFE left out) and scales
the result down only if it would clip. The logo loop has one stereo track.

**Encoders**: the export uses ffmpeg's own ``mpeg4`` video and ``aac`` audio encoders,
which are LGPL like the decoder. PyAV's wheels also carry x264/x265, which are GPL; the
toolkit doesn't use them (THIRD_PARTY.md).

Replacing a movie would need a Bink encoder (RAD's, not redistributable): not done.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from ..errors import Dr2Error
from .audio import AudioBackendMissing, Pcm

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

CENTRE_GAIN = SURROUND_GAIN = 0.7071       # −3 dB, the usual 5.1 → stereo weights


def have_bink() -> bool:
    """True when PyAV is importable and its ffmpeg decodes Bink video."""
    try:
        import av
        av.codec.Codec("binkvideo", "r")
        return True
    except Exception:  # noqa: BLE001 - any failure means "no"
        return False


def _open(data: bytes | str | Path):
    try:
        import av
    except ImportError:
        raise AudioBackendMissing("Bink movies need PyAV: pip install av") from None
    src = io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else str(data)
    try:
        return av.open(src)
    except Exception as e:  # noqa: BLE001 - ffmpeg's errors, said plainly
        raise Dr2Error(f"not a movie ffmpeg can read: {e}") from None


@dataclass
class VideoInfo:
    width: int
    height: int
    fps: float
    seconds: float
    audio_tracks: list[int] = field(default_factory=list)   # channels per track
    rate: int = 0                                            # audio sample rate

    @property
    def frames(self) -> int:
        return round(self.seconds * self.fps)

    def describe(self) -> str:
        sound = {0: "no sound", 2: "stereo", 6: "5.1"}.get(
            sum(self.audio_tracks), f"{sum(self.audio_tracks)} channels")
        return (f"Bink, {self.width}x{self.height}, {self.fps:.2f} fps, "
                f"{self.seconds:.1f} s, {sound}"
                + (f" ({len(self.audio_tracks)} tracks, {self.rate} Hz)"
                   if self.audio_tracks else ""))


def probe(data: bytes | str | Path) -> VideoInfo:
    """Size, frame rate, length and audio tracks of a movie."""
    with _open(data) as c:
        if not c.streams.video:
            raise Dr2Error("no video stream")
        v = c.streams.video[0]
        seconds = float(v.duration * v.time_base) if v.duration else float(c.duration or 0) / 1e6
        tracks = [a.codec_context.channels for a in c.streams.audio]
        rate = c.streams.audio[0].rate if c.streams.audio else 0
        return VideoInfo(v.codec_context.width, v.codec_context.height,
                         float(v.average_rate or 0), seconds, tracks, rate)


def frames(data: bytes | str | Path, start: float = 0.0):
    """Yield ``(seconds, width, height, rgb bytes)`` for every picture from ``start``."""
    with _open(data) as c:
        v = c.streams.video[0]
        if start > 0:
            c.seek(int(start / v.time_base), stream=v, backward=True, any_frame=False)
        for f in c.decode(v):
            t = float(f.pts * v.time_base) if f.pts is not None else 0.0
            if t + 1e-6 < start:
                continue
            rgb = f.to_ndarray(format="rgb24")
            yield t, f.width, f.height, rgb.tobytes()


def _mix(tracks: list) -> "np.ndarray":
    """``tracks`` (float arrays, channels × samples) → stereo, as described above."""
    n = min(t.shape[1] for t in tracks)
    tracks = [t[:, :n] for t in tracks]
    if len(tracks) == 1:
        a = tracks[0]
        return a if a.shape[0] == 2 else np.repeat(a[:1], 2, axis=0)
    chans = [row for t in tracks for row in t]
    if len(chans) == 6:                       # FL FR | C | LFE | SL SR
        fl, fr, c, _lfe, sl, sr = chans
        return np.stack([fl + CENTRE_GAIN * c + SURROUND_GAIN * sl,
                         fr + CENTRE_GAIN * c + SURROUND_GAIN * sr])
    return np.stack([sum(chans[0::2]), sum(chans[1::2] or chans[0::2])])


def audio(data: bytes | str | Path) -> Pcm | None:
    """The movie's sound as 16-bit stereo `Pcm` (None if it has none). Needs numpy."""
    if np is None:
        raise Dr2Error("decoding a movie's sound needs numpy: pip install numpy")
    tracks = []
    rate = 0
    with _open(data) as c:
        if not c.streams.audio:
            return None
    for k in range(len(probe(data).audio_tracks)):
        with _open(data) as c:
            s = c.streams.audio[k]
            rate = s.rate
            parts = [f.to_ndarray().astype(np.float32).reshape(f.layout.nb_channels, -1)
                     if f.format.is_planar else
                     f.to_ndarray().astype(np.float32).reshape(-1, f.layout.nb_channels).T
                     for f in c.decode(s)]
            tracks.append(np.concatenate(parts, axis=1))
    mix = _mix(tracks)
    peak = float(np.abs(mix).max()) if mix.size else 0.0
    if peak > 1.0:
        mix = mix / peak
    pcm = (np.clip(mix, -1, 1) * 32767).round().astype("<i2").T.tobytes()
    return Pcm(2, rate, pcm, peak)


def to_mp4(data: bytes | str | Path, out: str | Path, progress=None) -> VideoInfo:
    """Write the movie as ``.mp4`` (MPEG-4 video, AAC stereo). Returns its `VideoInfo`."""
    import av
    info = probe(data)
    sound = audio(data) if info.audio_tracks else None
    fps = Fraction(info.fps).limit_denominator(1001)
    with av.open(str(out), "w") as o:
        vs = o.add_stream("mpeg4", rate=fps)
        vs.width, vs.height = info.width, info.height
        vs.pix_fmt = "yuv420p"
        vs.bit_rate = 8_000_000
        a_s = None
        if sound is not None:
            a_s = o.add_stream("aac", rate=sound.rate, layout="stereo")
            a_s.bit_rate = 192_000
        n = 0
        for _t, w, h, rgb in frames(data):
            frame = av.VideoFrame.from_ndarray(
                np.frombuffer(rgb, np.uint8).reshape(h, w, 3), format="rgb24")
            for p in vs.encode(frame):
                o.mux(p)
            n += 1
            if progress and n % 300 == 0:
                progress(f"{n} frames")
        for p in vs.encode():
            o.mux(p)
        if a_s is not None:
            samples = np.frombuffer(sound.samples, "<i2").reshape(-1, 2)
            step = 1024
            for i in range(0, len(samples), step):
                chunk = np.ascontiguousarray(samples[i:i + step].T.astype(np.float32) / 32768)
                af = av.AudioFrame.from_ndarray(chunk, format="fltp", layout="stereo")
                af.sample_rate = sound.rate
                af.pts = i
                for p in a_s.encode(af):
                    o.mux(p)
            for p in a_s.encode():
                o.mux(p)
    return info

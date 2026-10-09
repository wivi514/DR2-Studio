"""`.xma` → PCM / WAV, and the metadata lookup that makes it possible.

This is the layer modders meet for audio: give it a virtual path, get a WAV. It joins
`dr2kit.formats.xma` (the two shapes of `.xma`, the ``cache.big`` stream tables) with
ffmpeg's ``xma2`` decoder, reached through **PyAV** (``pip install av``; an optional
dependency like Pillow: everything else in the toolkit works without it).

Why PyAV and not our own decoder: XMA2 is WMA Pro underneath (MDCT, entropy-coded
coefficients, stereo coding); ffmpeg's decoder is the one the recomps already trust
(``runtime/audio/xma_decoder.cpp`` in the CZ recomp). PyAV wheels bundle an LGPL ffmpeg.

Flow (`decode`):

1. `AudioLookup.info(vpath, data)` says how to read the bytes: a RIFF XMA2 file carries
   its own ``fmt`` chunk; raw packets in a streamed bank (``data/audio/<bank>.big``) get
   channels and rate from ``data/audio/cache.big/<bank>.$$$``.
2. Raw packets are wrapped in a RIFF header (`xma.riff_wrap`), so ffmpeg's WAV demuxer
   opens both shapes the same way.
3. ffmpeg decodes to float planes; `Pcm` holds them interleaved as 16-bit samples, the
   format of the WAV files we write (`write_wav`, standard library ``wave``).

The census (``dr2 census --audio``) runs this on every `.xma` of both games and checks
the length against the stored one (docs/formats.md §Audio).
"""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass
from pathlib import Path

from ..errors import Dr2Error, FormatError
from ..formats import xma

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


class AudioBackendMissing(Dr2Error):
    """PyAV (the ``av`` package) is not installed, so XMA can't be decoded."""


def have_decoder() -> bool:
    """True when PyAV is importable and its ffmpeg has the ``xma2`` decoder."""
    try:
        import av
        av.codec.Codec("xma2", "r")
        return True
    except Exception:  # noqa: BLE001 - any failure means "no"
        return False


@dataclass
class Pcm:
    """Decoded audio: interleaved signed 16-bit little-endian samples."""
    channels: int
    rate: int
    samples: bytes          # frames * channels * 2 bytes
    peak: float = 0.0       # largest absolute sample before conversion (1.0 = full scale)

    @property
    def frames(self) -> int:
        """Samples per channel (what a duration is measured in)."""
        return len(self.samples) // (2 * self.channels)

    @property
    def seconds(self) -> float:
        return self.frames / self.rate if self.rate else 0.0

    def wav_bytes(self) -> bytes:
        """The whole sound as a 16-bit PCM ``.wav`` file."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(self.channels)
            w.setsampwidth(2)
            w.setframerate(self.rate)
            w.writeframes(self.samples)
        return buf.getvalue()


def write_wav(pcm: Pcm, path: str | Path) -> None:
    """Write ``pcm`` as a 16-bit PCM WAV file."""
    Path(path).write_bytes(pcm.wav_bytes())


class AudioLookup:
    """Finds the metadata of any `.xma` of one game (caches the stream tables).

    ``tree`` is an `AssetTree`. Stream tables are read once, on first use.
    """

    def __init__(self, tree):
        self.tree = tree
        self._tables: dict[str, xma.StreamTable] | None = None

    def tables(self) -> dict[str, xma.StreamTable]:
        """``{bank: StreamTable}`` from ``data/audio/cache.big`` (empty if it's absent)."""
        if self._tables is None:
            self._tables = {}
            try:
                arc = self.tree.open_archive(xma.CACHE_ARCHIVE)
            except Dr2Error:
                return self._tables
            for e in arc.entries:
                if e.name.lower().endswith(".$$$"):
                    self._tables[e.name[:-4].lower()] = xma.StreamTable.parse(
                        e.data(), f"{xma.CACHE_ARCHIVE}/{e.name}")
        return self._tables

    def info(self, vpath: str, data: bytes) -> xma.AudioInfo:
        """How to decode the `.xma` at ``vpath`` whose bytes are ``data``."""
        if xma.is_riff(data):
            return xma.info_from_riff(data, vpath)
        bank = xma.bank_of(vpath)
        table = self.tables().get(bank) if bank else None
        name = vpath.rsplit("/", 1)[-1].split("#", 1)[0]
        rec = table.find(name) if table else None
        if rec is None:
            raise FormatError(f"{vpath}: raw XMA packets with no stream-table record "
                              f"(looked in {xma.CACHE_ARCHIVE}/{bank}.$$$)")
        if rec.size != len(data):
            raise FormatError(f"{vpath}: stream table says {rec.size} bytes, entry has "
                              f"{len(data)}")
        return xma.info_from_record(data, rec, bank)


def decode(data: bytes, info: xma.AudioInfo) -> Pcm:
    """Decode one `.xma` (either shape) to 16-bit PCM. Needs PyAV."""
    try:
        import av
    except ImportError as ex:
        raise AudioBackendMissing("decoding XMA needs PyAV: pip install av "
                                  "(or pip install -e \".[audio]\")") from ex
    if info.shape == "raw":
        riff = xma.riff_wrap(data[info.packets_offset:info.packets_offset + info.packets_size],
                             info.channels, info.rate)
    else:
        riff = data
    chunks: list = []
    peak = 0.0
    try:
        with av.open(io.BytesIO(riff), format="wav") as c:
            stream = c.streams.audio[0]
            for frame in c.decode(stream):
                if not frame.samples:
                    continue
                a = frame.to_ndarray()          # planar float: (channels, samples)
                chunks.append(a)
    except av.error.FFmpegError as ex:
        raise FormatError(f"ffmpeg could not decode the XMA: {ex}") from ex
    if np is None:  # pragma: no cover - PyAV itself needs numpy for to_ndarray
        raise AudioBackendMissing("decoding XMA needs numpy")
    if chunks:
        a = np.concatenate(chunks, axis=1)
        if a.shape[0] != info.channels:
            raise FormatError(f"decoder gave {a.shape[0]} channels, metadata says "
                              f"{info.channels}")
        peak = float(np.abs(a).max()) if a.size else 0.0
        pcm16 = (np.clip(a.T, -1.0, 1.0) * 32767.0).round().astype("<i2").tobytes()
    else:
        pcm16 = b""
    return Pcm(info.channels, info.rate, pcm16, peak)


def decode_vpath(tree, vpath: str, lookup: AudioLookup | None = None) -> tuple[Pcm, xma.AudioInfo]:
    """Resolve, read and decode the `.xma` at ``vpath``."""
    data = tree.resolve(vpath).data()
    info = (lookup or AudioLookup(tree)).info(vpath, data)
    return decode(data, info), info


def read_wav(path_or_bytes) -> Pcm:
    """A 16-bit PCM WAV file → `Pcm` (for checks and for mod builds)."""
    src = io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, (bytes, bytearray)) \
        else open(path_or_bytes, "rb")
    with src, wave.open(src, "rb") as w:
        if w.getsampwidth() != 2:
            raise FormatError(f"WAV must be 16-bit PCM (this one is {8 * w.getsampwidth()}-bit)")
        return Pcm(w.getnchannels(), w.getframerate(), w.readframes(w.getnframes()))


def length_check(pcm: Pcm, info: xma.AudioInfo, packets: bytes) -> str | None:
    """None when the decoded length agrees with the metadata; else what's wrong.

    Every sound: the packet headers' frame total says ``frames × 512 − 384`` less under
    one frame per stream (`xma.frame_count`). When a length is stored (a one-shot RIFF's
    ``dwPlayLength``, a looping stream's loop end) it must match exactly. A loop must fit
    in the sound (one sample of slack: 12 wind loops decode one sample past their end).
    """
    frames = xma.frame_count(packets, info.streams)
    top = frames * xma.FRAME_SAMPLES - xma.DECODER_DELAY
    if not (top - xma.FRAME_SAMPLES * info.streams < pcm.frames <= top):
        return (f"decoded {pcm.frames} samples, packet headers count {frames} frames "
                f"(expected {top} less under one frame per stream)")
    if info.expected_samples and pcm.frames != info.expected_samples:
        return f"decoded {pcm.frames} samples, stored length {info.expected_samples}"
    loop = info.loop
    if loop and not (loop[0] < loop[1] <= pcm.frames + 1):
        return f"loop {loop} does not fit in {pcm.frames} decoded samples"
    return None


def load_audio(path: str | Path) -> Pcm:
    """Any audio file a modder might have (WAV, OGG, FLAC, MP3...) → 16-bit `Pcm`.

    16-bit WAV is read with the standard library; everything else goes through PyAV.
    """
    path = Path(path)
    if path.suffix.lower() == ".wav":
        try:
            return read_wav(path)
        except (FormatError, wave.Error, EOFError):
            pass                     # a float or 24-bit WAV: let ffmpeg read it
    try:
        import av
    except ImportError as ex:
        raise AudioBackendMissing(f"{path.name}: reading this file needs PyAV "
                                  f"(pip install av), or save it as a 16-bit WAV") from ex
    chunks = []
    try:
        with av.open(str(path)) as c:
            s = c.streams.audio[0]
            channels, rate = s.codec_context.channels, s.codec_context.sample_rate
            res = av.AudioResampler(format="s16", layout=s.codec_context.layout.name,
                                    rate=rate)
            for frame in c.decode(s):
                for out in res.resample(frame):
                    chunks.append(bytes(out.planes[0])[:out.samples * channels * 2])
            for out in res.resample(None):
                chunks.append(bytes(out.planes[0])[:out.samples * channels * 2])
    except (av.error.FFmpegError, IndexError) as ex:
        raise FormatError(f"{path.name}: not an audio file ffmpeg can read ({ex})") from ex
    return Pcm(channels, rate, b"".join(chunks))


def conform(pcm: Pcm, channels: int, rate: int, frames: int) -> tuple[Pcm, list[str]]:
    """``pcm`` converted to ``channels`` × ``rate`` and cut or padded to ``frames``.

    What a replacement must look like for the recomp to play it in place of a sound:
    the same channel layout, the same rate, and exactly the decoded length of the
    original (the game decides how long a sound plays). Returns the result and notes
    for the modder about what was changed (resampled, mixed, cut, padded).
    """
    if np is None:
        raise AudioBackendMissing("converting audio needs numpy")
    notes = []
    a = np.frombuffer(pcm.samples, "<i2").astype(np.float32).reshape(-1, pcm.channels)
    if pcm.channels != channels:
        mono = a.mean(axis=1, keepdims=True)
        if channels == 1:
            a = mono
        elif pcm.channels == 1:
            a = np.repeat(a, channels, axis=1)
        elif channels > pcm.channels:            # stereo → 5.1: front pair, rest silent
            a = np.concatenate([a[:, :2], np.zeros((len(a), channels - 2), np.float32)], 1)
        else:                                    # 5.1 → stereo: keep the front pair
            a = a[:, :channels]
        notes.append(f"{pcm.channels} channel(s) converted to {channels}")
    if pcm.rate != rate and len(a):
        n = max(1, round(len(a) * rate / pcm.rate))
        x_old = np.arange(len(a)) / pcm.rate
        x_new = np.arange(n) / rate
        a = np.stack([np.interp(x_new, x_old, a[:, c]) for c in range(a.shape[1])], 1)
        if abs(pcm.rate - rate) > 50:
            notes.append(f"resampled {pcm.rate} Hz → {rate} Hz")
    if len(a) > frames:
        notes.append(f"cut from {len(a) / rate:.2f} s to the original's {frames / rate:.2f} s")
        a = a[:frames]
    elif len(a) < frames:
        if frames - len(a) > rate // 100:
            notes.append(f"padded with silence from {len(a) / rate:.2f} s to the "
                         f"original's {frames / rate:.2f} s")
        a = np.concatenate([a, np.zeros((frames - len(a), a.shape[1]), np.float32)])
    out = np.clip(np.round(a), -32768, 32767).astype("<i2")
    return Pcm(channels, rate, out.tobytes()), notes


def split_streams(pcm: Pcm) -> list[Pcm]:
    """One `Pcm` per XMA stream: channel pairs in order, the odd one out last as mono.

    The recomp decodes each stream in its own hardware context, so a 5.1 replacement is
    substituted as three stereo pieces (L R, C LFE, Ls Rs).
    """
    if pcm.channels <= 2:
        return [pcm]
    if np is None:
        raise AudioBackendMissing("splitting channels needs numpy")
    a = np.frombuffer(pcm.samples, "<i2").reshape(-1, pcm.channels)
    out = []
    for c in range(0, pcm.channels, 2):
        part = a[:, c:c + 2]
        out.append(Pcm(part.shape[1], pcm.rate, np.ascontiguousarray(part).tobytes()))
    return out


@dataclass
class StreamPackets:
    """One XMA stream decoded packet by packet, the way the recomps feed ffmpeg."""
    channels: int
    packets: list[int]     # packet indices of this stream, in decode order
    starts: list[int]      # decoded samples output before each packet's own output
    counts: list[int]      # samples each packet's decode call returned


def stream_packets(data: bytes, info: xma.AudioInfo) -> list[StreamPackets]:
    """Decode each stream of a sound one packet at a time; say where each packet's output
    lands. Needs PyAV.

    The recomps decode XMA one 2 KB packet per call into one decoder per hardware
    context (one per stream), so the samples a packet produces are fixed by the stream's
    packets before it. These numbers are what lets a recomp put each replacement sample
    where the original's would have gone (`dr2kit.mods.audio`). Checked: the outputs
    joined equal `decode`'s, sample for sample, for mono, stereo and each stereo
    stream of a 5.1 sound.
    """
    try:
        import av
    except ImportError as ex:
        raise AudioBackendMissing("needs PyAV: pip install av") from ex
    packets = data[info.packets_offset:info.packets_offset + info.packets_size]
    headers = xma.packet_headers(packets)
    out = []
    for s, first in enumerate(xma.stream_starts(packets, info.streams)):
        ch = 2 if info.channels - 2 * s >= 2 else 1
        cc = av.CodecContext.create("xma2", "r")
        cc.extradata = xma.Xma2Format(ch, info.rate, channel_mask=xma.CHANNEL_MASK[ch]).extradata()
        cc.sample_rate = info.rate
        cc.layout = "stereo" if ch == 2 else "mono"
        sp = StreamPackets(ch, [], [], [])
        done = 0
        i = first
        while i < len(headers):
            got = sum(f.samples for f in cc.decode(av.Packet(packets[i * xma.PACKET:
                                                                  (i + 1) * xma.PACKET])))
            sp.packets.append(i)
            sp.starts.append(done)
            sp.counts.append(got)
            done += got
            i += headers[i].skip + 1
        out.append(sp)
    return out

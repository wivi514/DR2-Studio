"""Audio (phase 5): `.xma` shapes, stream tables, packet headers, scripts, PCM helpers.

Synthetic data only: no game audio here (CLAUDE.md). XMA itself can't be made without
an encoder, so decoding is covered by the game-data tests (test_gamedata.py) and the
census (``dr2 census --audio``); these tests cover everything around it.
"""

import struct

import pytest

from dr2kit.errors import FormatError
from dr2kit.formats import audioscript, xma
from dr2kit.hashing import name_hash


def packet(frames: int, skip: int = 0, fill: int = 0) -> bytes:
    """A 2 KB packet whose header says ``frames`` frames start in it."""
    return struct.pack(">I", (frames << 26) | (1 << 8) | skip) + bytes([fill]) * 2044


def test_xma2_format_round_trip():
    f = xma.Xma2Format(channels=2, rate=48000, streams=1, channel_mask=3, play_length=1234,
                       loop_begin=384, loop_length=999, block_count=2)
    b = f.to_bytes()
    assert len(b) == 52 and struct.unpack_from("<H", b)[0] == xma.FORMAT_TAG_XMA2
    assert xma.Xma2Format.parse(b) == f
    assert len(f.extradata()) == 34 and f.extradata() == b[18:]
    with pytest.raises(FormatError):
        xma.Xma2Format.parse(b"\x01\x00" + b[2:])          # PCM tag, not XMA2


def test_riff_wrap_parses_back_and_info():
    pk = packet(5) + packet(4)
    data = xma.riff_wrap(pk, 6, 48000, play_length=4000)
    assert xma.is_riff(data) and not xma.is_riff(pk)
    r = xma.XmaRiff.parse(data, "t")
    assert r.fmt.channels == 6 and r.fmt.streams == 3 and r.fmt.channel_mask == 0x3F
    assert r.packets(data) == pk and r.chunks == ["fmt ", "data"] and r.leftover == 0
    info = xma.info_from_riff(data)
    assert (info.shape, info.channels, info.streams, info.expected_samples) == ("riff", 6, 3, 4000)
    assert info.loop is None


def test_riff_loop_info_counts_the_decoder_delay():
    data = xma.riff_wrap(packet(3), 1, 48000, play_length=1500, loop_begin=384,
                         loop_length=1000)
    info = xma.info_from_riff(data)
    assert info.expected_samples == 0            # looping RIFF: no exact stored length
    assert info.loop == (0, 1000)                # decoded samples, 384 of lead-in dropped


def test_riff_rejects_unknown_chunks_and_truncation():
    data = bytearray(xma.riff_wrap(packet(1), 1, 48000))
    with pytest.raises(FormatError, match="RIFF says"):
        xma.XmaRiff.parse(bytes(data[:-100]), "t")
    extra = bytes(data[:4]) + struct.pack("<I", len(data) - 8 + 12) + bytes(data[8:]) \
        + b"junk" + struct.pack("<I", 4) + b"abcd"
    with pytest.raises(FormatError, match="unknown RIFF chunks"):
        xma.XmaRiff.parse(extra, "t")


def test_packet_headers_frames_and_stream_starts():
    hs = xma.packet_headers(packet(17, skip=3) + packet(15, 1))
    assert hs[0] == xma.PacketHeader(17, 0, 1, 3) and hs[1].frames == 15
    assert xma.frame_count(packet(10) + packet(6)) == 16
    # three streams interleaved as in the 5.1 cinematics: 0->4, 1->3->5, 2->6
    pk = packet(1, 3) + packet(1, 1) + packet(1, 3) + packet(1, 1) + packet(1, 9) + \
        packet(1, 9) + packet(1, 9)
    assert xma.stream_starts(pk, 3) == [0, 1, 2]
    assert xma.stream_starts(packet(2) + packet(2), 1) == [0]


def test_fingerprint_is_fnv1a_64():
    assert xma.fingerprint(b"") == 0xCBF29CE484222325
    assert xma.fingerprint(b"a") == 0xAF63DC4C8601EC8C           # published test vector


def stream_table(*records) -> bytes:
    body = b"".join(struct.pack(">6I", name_hash(n), off, size, rate << 5 | ch << 2 | 1, lb, ll)
                    for n, off, size, rate, ch, lb, ll in records)
    return b"$GIB" + struct.pack(">III", 2, 3, len(records)) + body


def test_stream_table_parse_and_find():
    data = stream_table(("HB_Indemnify.xma", 0x800, 4096, 47999, 2, 384, 5000),
                        ("2727.xma", 0x1800, 2048, 48000, 1, 0, 0))
    t = xma.StreamTable.parse(data)
    rec = t.find("HB_Indemnify.xma")
    assert (rec.rate, rec.channels, rec.flags, rec.looped) == (47999, 2, 1, True)
    assert t.find("hb_indemnify.xma") is None       # the hash keeps the case
    info = xma.info_from_record(bytes(4096), rec, "music")
    assert info.expected_samples == 5000 and info.loop == (0, 5000)
    assert xma.info_from_record(bytes(2048), t.find("2727.xma"), "x").expected_samples == 0
    with pytest.raises(FormatError):
        xma.StreamTable.parse(data[:-4])


def test_bank_of():
    assert xma.bank_of("data/audio/music.big/X.xma") == "music"
    assert xma.bank_of("data/streamedassets.big/fx_main.big/X.xma") is None


SFX = """//Version=1.0
cSoundEffect NA
{
\tMixerCategory = "FEButtons"
\tcSfxTrack 1
\t{
\t\tPath = "C:\\bcg\\deadrising\\audio\\DR1_SystemSounds"
\t\tSample = "cursorError43a_01a.wav"
\t}

\tcSfxTrack 2
\t{
\t\tSample = "FrogSUB1.sfx"
\t}

}
"""

SCENE = """cAudioScene Prologue
{
\tcAudioScenario MechanicBattle
\t{
\t\tActivationEvent = "MechanicBattleStart"
\t\tcAudioActionLoad MechanicAssets
\t\t{
\t\t\tBigFile = "fx_mechanic.big"
\t\t}

\t\tcAudioJukebox MechanicMusic
\t\t{
\t\t\tTriggerPlay = "MechanicBattleStart"
\t\t\tcAudioJukeboxTrack Track
\t\t\t{
\t\t\t\tAsset = "music.big/HB_Indemnify"
\t\t\t}

\t\t}

\t}

}
"""


def test_sfx_tracks():
    assert audioscript.sfx_tracks(SFX) == ["cursorError43a_01a.xma", "FrogSUB1.sfx"]
    root = audioscript.parse(SFX)[0]
    assert (root.cls, root.get("mixercategory")) == ("cSoundEffect", "FEButtons")


def test_script_refs_and_context():
    refs = audioscript.script_refs(SCENE)
    assert [(r.key, r.bank, r.entry) for r in refs] == [
        ("BigFile", "fx_mechanic.big", None), ("Asset", "music.big", "HB_Indemnify")]
    track = refs[1]
    assert track.path == "Prologue/MechanicBattle/MechanicMusic/Track"
    assert track.context == ("Prologue/MechanicBattle/MechanicMusic/Track "
                             "(ActivationEvent=MechanicBattleStart; "
                             "TriggerPlay=MechanicBattleStart)")


@pytest.mark.parametrize("text, where", [("{\n", ":1:"), ("cA x\n{\n}\n}\n", ":4:"),
                                         ("cA x\n{\nnot a line\n}\n", ":3:"),
                                         ("cA x\n{\n", "ends inside")])
def test_script_errors_name_the_line(text, where):
    with pytest.raises(FormatError, match=where):
        audioscript.parse(text, "s.txt")


np = pytest.importorskip("numpy", reason="the PCM helpers need numpy")


def test_pcm_wav_round_trip_and_conform():
    from dr2kit.convert.audio import Pcm, conform, read_wav, split_streams
    a = (np.sin(np.arange(4800) / 10) * 10000).astype("<i2")
    mono = Pcm(1, 48000, a.tobytes())
    back = read_wav(mono.wav_bytes())
    assert (back.channels, back.rate, back.samples) == (1, 48000, mono.samples)
    fitted, notes = conform(mono, 2, 48000, 9600)
    assert (fitted.channels, fitted.frames) == (2, 9600)
    assert any("padded" in n for n in notes) and any("channel" in n for n in notes)
    st = np.frombuffer(fitted.samples, "<i2").reshape(-1, 2)
    assert (st[:4800, 0] == a).all() and (st[4800:] == 0).all()
    cut, notes = conform(Pcm(1, 24000, a.tobytes()), 1, 48000, 6000)
    assert cut.frames == 6000 and any("resampled" in n for n in notes)
    six = Pcm(6, 48000, np.arange(60, dtype="<i2").tobytes())
    parts = split_streams(six)
    assert [p.channels for p in parts] == [2, 2, 2]
    assert np.frombuffer(parts[1].samples, "<i2").tolist()[:2] == [2, 3]


def test_length_check_rules():
    from dr2kit.convert.audio import Pcm, length_check
    pk = packet(3) + packet(2)                  # 5 frames -> 5*512-384 = 2176 at most
    info = xma.AudioInfo(1, 48000, "raw", 0, len(pk), 0)
    ok = Pcm(1, 48000, bytes(2 * 2000))
    assert length_check(ok, info, pk) is None
    assert "packet headers" in length_check(Pcm(1, 48000, bytes(2 * 2200)), info, pk)
    exact = xma.AudioInfo(1, 48000, "raw", 0, len(pk), 2001)
    assert "stored length" in length_check(ok, exact, pk)

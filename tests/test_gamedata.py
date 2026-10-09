"""Tests on the real games. Each one SKIPS, saying why, when the game isn't installed.

These are the phase 1 gates in test form (docs/roadmap.md, docs/dev/testing.md):
every archive round-trips byte-identically, every compressed entry decodes to its size2,
nothing is left unparsed, and unpacking the XBLA package gives the recomp's files; plus
the phase 3-4 model checks on reference models.
Nothing here copies game data into the repository.

The slow LZX gates (re-encode every compressed entry, pure-Python decode of every
compressed entry) are not tests; run them with
``dr2 census --reencode --python-lzx`` (minutes, all CPUs).
"""

import random

import pytest

from dr2kit.census import run_census
from dr2kit.container.stfs import Package
from dr2kit.container.vpath import AssetTree
from dr2kit.profiles import find_packages, load_profile

pytestmark = pytest.mark.gamedata


@pytest.mark.slow
@pytest.mark.parametrize("game", ["cz", "cw"])
def test_census_gates(game, game_root):
    root = game_root(game)
    rep = run_census(game, AssetTree(root))
    assert rep.problems == [], f"{len(rep.problems)} problems, e.g. {rep.problems[:5]}"
    assert rep.roundtrip_ok == rep.archives
    assert rep.decoded_ok == rep.compression.get(2, 0)
    assert rep.hash_ok == rep.entries
    assert rep.unsafe_names == []
    expected = load_profile(game).census
    assert rep.archive_files == expected["archive_files"]
    assert rep.archives == expected["archives"]
    assert rep.entries == expected["entries"]
    # phase 3: every scene parses (models + skeletons)
    assert rep.scenes["model"] == expected["models"]
    assert rep.scenes["skeleton"] == expected["skeletons"]
    assert rep.scene_draws == expected["model_draws"]


@pytest.mark.slow
@pytest.mark.parametrize("game", ["cz", "cw"])
def test_every_model_draw_decodes(game, game_root):
    """The phase 3 model gate: every draw of every model decodes (dr2 census --models)."""
    rep = run_census(game, AssetTree(game_root(game)), models=True)
    assert rep.problems == [], f"{len(rep.problems)} problems, e.g. {rep.problems[:5]}"
    assert rep.scene_draws_decoded == rep.scene_draws == load_profile(game).census["model_draws"]
    assert rep.scene_checks["skin weights do NOT sum to 1"] == 0
    assert rep.scene_checks["normal NOT unit"] == 0


@pytest.mark.parametrize("game,vpath,bones", [
    ("cz", "data/models/npcs.big/chest_young_chuck.big", 98),
    ("cz", "data/models/npcs.big/boss_mechanic.big", 98),
    ("cw", "data/models/npcs.big/chest_default.big", 98),
])
def test_reference_model_exports_with_textures(game, vpath, bones, game_root):
    """A whole NPC and one of Chuck's parts export to .glb with every texture found."""
    from dr2kit.convert import gltf
    from dr2kit.convert.model import export_glb
    tree = AssetTree(game_root(game))
    st = gltf.ExportStats()
    g = gltf.Glb.parse(export_glb(tree, vpath, game=game, stats=st))
    assert len(g.gltf["skins"][0]["joints"]) == bones
    assert st.primitives > 0 and st.textures > 0
    assert st.missing_textures == []
    for mesh in g.gltf["meshes"]:
        for prim in mesh["primitives"]:
            w = g.accessor(prim["attributes"]["WEIGHTS_0"])
            assert all(abs(sum(r) - 1) < 1e-6 for r in w)


@pytest.mark.parametrize("game,vpath", [
    ("cz", "data/models/npcs.big/chest_young_chuck.big"),
    ("cz", "data/cine_props.big/cine_bike.big/cine_bike.big"),     # combined buffers
    ("cw", "data/models/npcs.big/chest_default.big"),
])
def test_reference_model_reimports(game, vpath, game_root):
    """Phase 4: export → import with no edits gives the identical model; rebuilding every
    shape from its own geometry decodes back the same (the census --reimport gates on
    a few models; the full run is `dr2 census --reimport`)."""
    from dr2kit.census import CensusReport, check_reimport
    data = AssetTree(game_root(game)).resolve(vpath).data()
    rep = CensusReport(game, "")
    check_reimport(rep, vpath, data)
    assert rep.problems == []
    assert rep.scene_checks["glb re-import identical"] == 1
    assert rep.scene_checks["draws rebuilt identically"] > 0


@pytest.mark.parametrize("game", ["cz", "cw"])
def test_python_decoder_on_a_sample(game, game_root):
    """Fast cross-check of the pure-Python decoder on a few real compressed entries."""
    tree = AssetTree(game_root(game))
    arc = tree.open_archive("data/datafile.big")
    entries = [e for e in arc.entries if e.compressed][:5]
    assert entries, "datafile.big has compressed entries in both games"
    for e in entries:
        assert e.data(python_lzx=True) == e.data()


@pytest.mark.parametrize("game", ["cz", "cw"])
def test_stfs_matches_unpacked_data(game, game_root):
    root = game_root(game)
    packages = find_packages(game)
    if not packages:
        pytest.skip(f"no {game} XBLA package next to the recomp")
    with Package(packages[0]) as pkg:
        assert f"{pkg.title_id:08X}" == load_profile(game).title_id
        data_files = sorted(p for p in pkg.files if p.lower().startswith("data/"))
        on_disk = {vp.lower() for vp, _ in AssetTree(root).files()}
        assert {p.lower() for p in data_files} == on_disk
        # Byte-compare a sample (all of them takes a while; `dr2 unpack` + diff does that).
        for name in random.Random(0).sample(data_files, 12) + ["data/datafile.big"]:
            assert pkg.read(name) == (root / name).read_bytes(), name


# --- phase 5: audio ---------------------------------------------------------------------

def _need_pyav():
    from dr2kit.convert.audio import have_decoder
    if not have_decoder():
        pytest.skip("PyAV with the xma2 decoder is not installed (pip install av)")


@pytest.mark.slow
@pytest.mark.parametrize("game", ["cz", "cw"])
def test_every_sound_decodes_to_its_length(game, game_root):
    """The phase 5 gate: every .xma decodes to its stored length (dr2 census --audio)."""
    _need_pyav()
    rep = run_census(game, AssetTree(game_root(game)), audio=True)
    assert rep.problems == [], f"{len(rep.problems)} problems, e.g. {rep.problems[:5]}"
    expected = load_profile(game).census
    assert rep.audio_decoded_ok == expected["sounds"] == sum(rep.audio_shapes.values())
    assert rep.sfx_parsed == expected["sfx"]
    assert rep.sfx_tracks["missing"] == expected["sfx_missing"]


def test_music_metadata_and_decode(game_root):
    """A raw stream (music) gets its rate and channels from cache.big, and decodes to
    exactly its loop end; a RIFF sound decodes to exactly its dwPlayLength."""
    _need_pyav()
    from dr2kit.convert.audio import decode_vpath, length_check
    tree = AssetTree(game_root("cz"))
    pcm, info = decode_vpath(tree, "data/audio/music.big/HB_Indemnify.xma")
    assert (info.shape, info.channels, info.rate) == ("raw", 2, 47999)
    assert pcm.frames == info.expected_samples == 5728896 and pcm.peak > 0.5
    pcm, info = decode_vpath(tree, "data/streamedassets.big/fx_main.big/FabricLeatherShort3.xma")
    assert info.shape == "riff" and pcm.frames == info.expected_samples == 39746


def test_audio_mod_build(game_root, tmp_path):
    """A replaced sound builds into a substitution table: every packet of the stream
    listed with its output position, the WAV fitted to the original's length."""
    _need_pyav()
    np = pytest.importorskip("numpy")
    from dr2kit.convert.audio import Pcm, stream_packets
    from dr2kit.mods.build import build
    from dr2kit.mods.manifest import Mod, create
    tree = AssetTree(game_root("cz"))
    vp = "data/streamedassets.big/fx_main.big/FabricLeatherShort3.xma"
    mod = create(tmp_path / "mod", "tone")
    dest = mod / "replace" / (vp + ".wav")
    dest.parent.mkdir(parents=True)
    tone = (np.sin(np.arange(48000) / 8) * 8000).astype("<i2").tobytes()
    dest.write_bytes(Pcm(1, 48000, tone).wav_bytes())
    res = build([Mod.load(mod)], "cz", tree, tmp_path / "out")
    table = (tmp_path / "out" / "dr2kit_audio" / "substitutions.txt").read_text()
    lines = [ln.split("#")[0].split() for ln in table.splitlines() if not ln.startswith("#")]
    assert lines[0][:4] == ["sound", "0", "1", "39746"]
    data = tree.resolve(vp).data()
    from dr2kit.convert.audio import AudioLookup
    sp = stream_packets(data, AudioLookup(tree).info(vp, data))[0]
    assert [int(ln[2]) for ln in lines[1:]] == sp.starts
    assert all(ln[3] == "u" for ln in lines[1:])
    assert any("cut" in w for w in res.warnings)

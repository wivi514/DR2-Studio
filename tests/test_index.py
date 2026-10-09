"""The asset index on a synthetic game folder."""

import struct

import pytest

from dr2kit.cli.main import main
from dr2kit.container.big import LZX
from dr2kit.container.vpath import AssetTree
from dr2kit.index import query
from dr2kit.index.build import MAT_RECORD, build_index, connect

from conftest import make_archive, make_bct


def mat_record(name: str) -> bytes:
    """One 100-byte MatTextureInfoArray record laid out by hand (formats.md)."""
    rec = struct.pack(">I", 1) + name.encode().ljust(52, b"\0") + struct.pack(">I", 0x1234)
    return rec.ljust(MAT_RECORD, b"\0")


@pytest.fixture
def game(tmp_path, monkeypatch):
    model = make_archive(("SceneHeader", bytes(20)),
                         ("geo_bodyShape Vertices 0", bytes(64)),
                         ("MatTextureInfoArray", mat_record("hero_cm") + mat_record("missing_cm")
                          + mat_record("gExposureTexture")))
    pack = make_archive(("hero_cm", make_bct("DXT1", 32, 32, 3)))
    npcs = make_archive(("hero.big", model.to_bytes(), LZX), ("hero.tex", pack.to_bytes(), LZX))
    other = make_archive(("hero_cm.bct", make_bct("DXT1", 32, 32, 3)), ("readme.txt", b"hi"))
    root = tmp_path / "game"
    (root / "data" / "models").mkdir(parents=True)
    (root / "data" / "models" / "npcs.big").write_bytes(npcs.to_bytes())
    (root / "data" / "other.big").write_bytes(other.to_bytes())
    monkeypatch.setenv("DR2_CZ_DATA", str(root))
    return root


def test_build_and_query(game, tmp_path):
    db = tmp_path / "i.sqlite"
    st = build_index("cz", AssetTree(game), db)
    assert st.problems == []
    assert st.textures == 2 and st.models == 1 and st.material_slots == 3
    con = connect(db)
    kinds = {r["vpath"]: r["kind"] for r in con.execute("SELECT vpath, kind FROM asset")}
    assert kinds["data/models/npcs.big/hero.big"] == "model"
    assert kinds["data/models/npcs.big/hero.tex"] == "texture-pack"
    assert kinds["data/models/npcs.big/hero.tex/hero_cm"] == "texture"
    assert kinds["data/other.big/readme.txt"] == "text"
    model = query.get(con, "cz", "DATA/MODELS/NPCS.BIG/HERO.BIG")     # case-insensitive
    slots = query.textures_of(con, model["id"])
    found = [(r["dst_name"], r["vpath"], r["rank"]) for r in slots]
    # The texture next to the model ranks first; the other copy elsewhere; the engine
    # sampler is not a relation; a name found nowhere is listed with no asset.
    assert found[0] == ("hero_cm", "data/models/npcs.big/hero.tex/hero_cm", 0)
    assert ("hero_cm", "data/other.big/hero_cm.bct", 1) in found
    assert ("missing_cm", None, 9) in found
    assert not any(n == "gExposureTexture" for n, _, _ in found)
    tex = query.get(con, "cz", "data/models/npcs.big/hero.tex/hero_cm")
    assert [r["vpath"] for r in query.used_by(con, tex["id"])] == ["data/models/npcs.big/hero.big"]
    assert query.thumbnail(con, tex["id"])[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(query.same_content(con, tex["id"])) == 1   # the identical copy in other.big
    assert [r["name"] for r in query.search(con, "hero *cm*", kind="texture")] == \
        ["hero_cm", "hero_cm.bct"]
    assert [r["name"] for r in query.search(con, "npcs.big/ cm")] == ["hero_cm"]


def test_incremental_rebuild(game, tmp_path):
    db = tmp_path / "i.sqlite"
    build_index("cz", AssetTree(game), db)
    st = build_index("cz", AssetTree(game), db)
    assert st.files_indexed == 0 and st.files_unchanged == 2
    (game / "data" / "other.big").unlink()
    st = build_index("cz", AssetTree(game), db)
    assert st.files_removed == 1
    con = connect(db)
    assert query.search(con, "readme") == []
    model = query.get(con, "cz", "data/models/npcs.big/hero.big")
    assert len([r for r in query.textures_of(con, model["id"]) if r["vpath"]]) == 1


def test_cli_index(game, tmp_path, capsys):
    db = str(tmp_path / "i.sqlite")
    assert main(["index", "build", "cz", "-q", "--db", db]) == 0
    assert "PROBLEMS (unparsed): 0" in capsys.readouterr().out
    assert main(["index", "search", "hero", "--kind", "texture", "--db", db]) == 0
    assert "hero.tex/hero_cm" in capsys.readouterr().out
    assert main(["index", "used-by", "data/models/npcs.big/hero.tex/hero_cm", "--db", db]) == 0
    assert "hero.big" in capsys.readouterr().out


def test_sounds_and_their_links(tmp_path):
    """Sounds get an `audio` row; a .sfx links to the recording of its bank; a scene
    script's Asset line links to the sound, with its trigger events as context."""
    import struct as st
    from dr2kit.formats import xma
    from test_audio import SCENE, SFX, packet
    sound = xma.riff_wrap(packet(5) + packet(4), 1, 48000, play_length=3000)
    fx = make_archive(("cursorError43a_01a.xma", sound), ("FEError.sfx", SFX.encode()))
    root = tmp_path / "game"
    (root / "data" / "audio").mkdir(parents=True)
    (root / "data" / "streamedassets.big").write_bytes(
        make_archive(("fx_main.big", fx.to_bytes())).to_bytes())
    music = make_archive(("HB_Indemnify.xma", packet(9) * 2))
    (root / "data" / "audio" / "music.big").write_bytes(music.to_bytes())
    from dr2kit.hashing import name_hash
    table = b"$GIB" + st.pack(">III", 2, 3, 1) + st.pack(
        ">6I", name_hash("HB_Indemnify.xma"), 0x800, 4096, 48000 << 5 | 2 << 2 | 1, 384, 4000)
    (root / "data" / "audio" / "cache.big").write_bytes(
        make_archive(("music.$$$", table)).to_bytes())
    (root / "data" / "audio" / "Prologue.txt").write_text(SCENE)
    db = tmp_path / "i.sqlite"
    st_ = build_index("cz", AssetTree(root), db, thumbs=False)
    assert st_.problems == [] and st_.sounds == 2
    con = connect(db)
    rec = query.get(con, "cz", "data/streamedassets.big/fx_main.big/cursorError43a_01a.xma")
    a = query.audio_info(con, rec["id"])
    assert (a["channels"], a["samples"], a["exact"], a["shape"]) == (1, 3000, 1, "riff")
    users = query.sound_users(con, rec["id"])
    assert [u["name"] for u in users] == ["FEError.sfx"]
    mus = query.get(con, "cz", "data/audio/music.big/HB_Indemnify.xma")
    assert dict(query.audio_info(con, mus["id"]))["loop_end"] == 4000
    users = query.sound_users(con, mus["id"])
    assert len(users) == 1 and "TriggerPlay=MechanicBattleStart" in users[0]["context"]
    sfx = query.get(con, "cz", "data/streamedassets.big/fx_main.big/FEError.sfx")
    targets = query.sound_targets(con, sfx["id"])
    assert [(t["dst_name"], t["vpath"] is not None) for t in targets] == [
        ("cursorError43a_01a.xma", True), ("FrogSUB1.sfx", False)]
    assert st_.unresolved_sounds == 1
    con.close()


def test_old_schema_is_dropped_and_rebuilt(game, tmp_path):
    """An index from an older toolkit is replaced, even with foreign keys between its
    tables (the first schema bump failed here: 'no such table: main.source_file')."""
    db = tmp_path / "i.sqlite"
    build_index("cz", AssetTree(game), db, thumbs=False)
    con = connect(db)
    con.execute("UPDATE meta SET value='0' WHERE key='schema'")
    con.commit()
    con.close()
    con = connect(db)
    assert con.execute("SELECT count(*) FROM asset").fetchone()[0] == 0
    con.close()
    assert build_index("cz", AssetTree(game), db, thumbs=False).assets > 0

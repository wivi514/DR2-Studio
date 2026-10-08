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

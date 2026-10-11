"""The Library (phase 8): groups, rig links, thumbnails and export, on synthetic data."""

import struct

import pytest

from dr2kit.catalog import export as cx
from dr2kit.catalog.groups import Catalog, catalog, check, glob_regex, slug
from dr2kit.cli.main import main
from dr2kit.container.big import LZX, BigArchive
from dr2kit.container.vpath import AssetTree
from dr2kit.convert import render
from dr2kit.index import build as ibuild
from dr2kit.index import query
from dr2kit.index.build import build_index, connect

from conftest import make_archive, make_bct, make_scene


def variant(scene: bytes, tag: str) -> bytes:
    """The same scene with different bytes (an extra entry), so it isn't folded as a copy."""
    arc = BigArchive.parse(scene)
    return make_archive(*[(e.name, e.data()) for e in arc.entries], ("note", tag.encode())).to_bytes()


def make_skeleton() -> bytes:
    """The rig of `make_scene` on its own: the same 3 bones, no meshes or materials."""
    arc = BigArchive.parse(make_scene())
    keep = []
    for e in arc.entries:
        if any(k in e.name for k in ("Vertices", "Indices", "persistent.big", "MatArray",
                                     "MatTextureInfoArray", "UsedShaders")):
            continue
        data = e.data()
        if e.name == "SceneDescription":
            data = data[:3 * 36]                     # the 3 bones, not the shape
        elif e.name == "SceneHeader":
            data = struct.pack(">5I", 1, 2, 2, 3, 1)
        keep.append((e.name, data))
    return make_archive(*keep).to_bytes()


RULES = """
[[group]]
id = "people"
section = "Models"
title = "People"
kinds = ["model"]
paths = ["data/npcs.big/**"]
sub_name = "^(chest|srv)_"
sub_default = "Others"
[group.sub_names]
chest = "Outfit parts"
"s?v" = "Survivors"

[[group]]
id = "pics"
section = "Textures"
title = "Pictures"
kinds = ["texture"]
paths = ["**"]
sub_role = true

[[group]]
id = "zones"
section = "Models"
title = "Zones"
kinds = ["model"]
paths = ["data/env/*/**"]
sub_path = "env/([^/]+)/"

[[label]]
groups = ["people"]
pattern = "^srv_(?P<rest>.+)$"
format = "{Rest} (survivor, {rest})"

[names.people]
chest_hero = "The hero's shirt"
"cw:chest_hero" = "Frank's shirt"
"""


def test_glob_regex_keeps_single_stars_in_one_folder():
    assert glob_regex("data/*.csv").match("data/items.csv")
    assert not glob_regex("data/*.csv").match("data/sub/items.csv")
    assert glob_regex("data/**").match("data/a.big/b.big/c")
    assert glob_regex("**/fx_*.big/*").match("data/streamedassets.big/fx_main.big/hit.xma")
    assert not glob_regex("**/fx_*.big/*").match("data/streamedassets.big/fx_main.big/a/b")


def test_rules_place_sub_and_label():
    cat = Catalog.from_toml(RULES)
    assert cat.place("cz", "model", "data/npcs.big/chest_hero.big", "chest_hero.big") == \
        ("people", "Outfit parts", "The hero's shirt")
    assert cat.place("cw", "model", "data/npcs.big/chest_hero.big", "chest_hero.big")[2] == \
        "Frank's shirt"                                       # a name for one game only
    assert cat.place("cz", "model", "DATA/NPCS.BIG/srv_old_man.big", "srv_old_man.big") == \
        ("people", "Survivors", "Old Man (survivor, old man)")
    assert cat.place("cz", "model", "data/npcs.big/dog.big", "dog.big") == ("people", "Others", "")
    assert cat.place("cz", "texture", "data/x.big/hero_nm", "hero_nm")[1] == "Normal maps"
    assert cat.place("cz", "model", "data/env/canyon/rock.big", "rock.big")[:2] == ("zones", "canyon")
    assert cat.place("cz", "audio", "data/a.big/x.xma", "x.xma") is None
    assert cat.sections() == ["Models", "Textures"]


def test_rules_refuse_unknown_keys():
    # a key that lands under the last [[group]] by mistake must not be ignored silently
    with pytest.raises(ValueError, match="unknown key"):
        Catalog.from_toml(RULES + '\n[[group]]\nid = "x"\nsection = "S"\ntitle = "T"\n'
                          'kinds = []\npaths = []\nchest_hero = "a stray name"\n')
    with pytest.raises(ValueError, match="unknown table"):
        Catalog.from_toml("[groups]\n")


def test_shipped_rules_load_and_place_known_assets():
    cat = catalog()
    assert {"characters", "zombies", "music", "rigs", "strings", "movies"} <= \
        {g.id for g in cat.groups}
    assert cat.place("cz", "model", "data/models/npcs.big/chest_young_chuck.big",
                     "chest_young_chuck.big") == \
        ("characters", "Outfit parts", "Young Chuck's orange 04 shirt (chest)")
    assert cat.place("cz", "model", "data/models/zombies.big/zombie_cop.big/zombie_cop_2.big",
                     "zombie_cop_2.big") == ("zombies", "zombie_cop", "Zombie Cop")
    # detail levels, not variants (phase 9): one item, the levels folded into it
    assert cat.detail("zombies", "zombie_cop_2.big") == ("zombie_cop", 0, "high")
    assert cat.detail("zombies", "zombie_cop_4.big") == ("zombie_cop", 2, "low")
    assert cat.detail("characters", "zombie_cop_4.big") is None
    assert cat.detail("zombies", "zombie_test.big") is None
    assert cat.place("cz", "audio", "data/streamedassets.big/fx_ftspsneaker.big/a.xma",
                     "a.xma")[:2] == ("footsteps", "sneaker")
    assert cat.place("cw", "video", "data/movies/dr2_logo.bik", "dr2_logo.bik")[2] == \
        "Dead Rising 2 logo"
    # every kind the Library shows has a catch-all, so nothing of it is left out
    for kind in ("model", "skeleton", "audio", "texture"):
        assert cat.place("cz", kind, "data/somewhere/new.big", "new.big") is not None
    assert slug("prologue / prologue_z01") == "prologue-prologue_z01"


@pytest.fixture
def game(tmp_path, monkeypatch):
    """Two characters (one with a texture pack, sharing its texture with an item), a
    rig with the same bones in skeleton/ and its copy in preload4.big, a sound."""
    monkeypatch.setattr(ibuild, "MIN_RIG_BONES", 2)          # the test rig has 3 bones
    scene, skel = make_scene(), make_skeleton()
    tex = make_bct("DXT1", 32, 32, 1)
    npcs = make_archive(("chest_hero.big", scene, LZX), ("srv_bob.big", make_scene(combined=True)),
                        ("chest_hero.tex", make_archive(("box_cm", tex)).to_bytes()))
    items = make_archive(("crate.big", make_archive(("crate.big", variant(scene, "crate")),
                                                    ("box_cm", tex)).to_bytes()))
    root = tmp_path / "game"
    for sub in ("models", "skeleton", "audio"):
        (root / "data" / sub).mkdir(parents=True)
    (root / "data" / "models" / "npcs.big").write_bytes(npcs.to_bytes())
    (root / "data" / "streamedassets.big").write_bytes(items.to_bytes())
    (root / "data" / "skeleton" / "herofullbody.big").write_bytes(skel)
    (root / "data" / "preload4.big").write_bytes(make_archive(("herofullbody.big", skel)).to_bytes())
    (root / "data" / "notes.csv").write_bytes(b"a,b\n1,2\n")
    monkeypatch.setenv("DR2_CZ_DATA", str(root))
    db = tmp_path / "i.sqlite"
    st = build_index("cz", AssetTree(root), db)
    assert st.problems == []
    return root, db, st


def test_index_library_rigs_thumbnails(game):
    root, db, st = game
    con = connect(db)
    counts = {(r["grp"], r["sub"]): r["n"] for r in query.library_counts(con, "cz")}
    assert counts[("characters", "Outfit parts")] == 1
    assert counts[("characters", "Survivors")] == 1
    assert counts[("items", "")] == 1
    assert counts[("rigs", "")] == 1                        # the preload4 copy folded in
    assert counts[("game-data", "")] == 1
    rig = query.get(con, "cz", "data/skeleton/herofullbody.big")
    copy = query.get(con, "cz", "data/preload4.big/herofullbody.big")
    assert query.library_item(con, copy["id"])["copy_of"] == rig["id"]
    assert [c["vpath"] for c in query.copies(con, rig["id"])] == [copy["vpath"]]
    # the shared texture is shown once, the copy in the item's archive points at it
    shown = query.library_items(con, "cz", "character-textures")
    assert [r["name"] for r in shown] == ["box_cm"]
    hero = query.get(con, "cz", "data/models/npcs.big/chest_hero.big")
    rigs = query.rigs_of(con, hero["id"])
    assert rigs[0]["vpath"] == rig["vpath"] and rigs[0]["rank"] == 0   # same bones, same pose
    assert {r["name"] for r in query.rig_users(con, rig["id"])} >= {"chest_hero.big"}
    info = query.scene_info(con, hero["id"])
    assert (info["bones"], info["meshes"], info["draws"], info["vertices"]) == (3, 1, 1, 4)
    assert info["bone_names"].split("\n") == ["dummy01", "dummy01.spine", "dummy01.l_arm"]
    if render.available():
        assert query.picture(con, hero["id"]).startswith(b"\x89PNG")
        assert st.thumbnails == 3
    report, problems = check(con, "cz")
    assert problems == [], problems
    assert any(line.startswith("model") for line in report)
    rows = query.library_items(con, "cz", "characters", text="bob")
    assert [r["label"] for r in rows] == ["Bob (survivor)"]


def test_check_names_a_stale_library(game):
    _root, db, _st = game
    con = connect(db)
    con.execute("UPDATE library_item SET grp='music' WHERE grp='items'")
    con.execute("DELETE FROM library_item WHERE grp='game-data'")
    _report, problems = check(con, "cz")
    assert any("rules say items" in p for p in problems)
    assert any("notes.csv" in p and "isn't in the Library" in p for p in problems)


@pytest.mark.skipif(not render.available(), reason="numpy not installed")
def test_render_draws_a_lit_textured_quad():
    import numpy as np
    pos = np.array([(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)], dtype=np.float32)
    tris = np.array([(0, 1, 2), (2, 1, 3)], dtype=np.int32)
    red = np.zeros((4, 4, 4), dtype=np.float32)
    red[..., 0] = red[..., 3] = 1.0
    uv = np.array([(0, 0), (1, 0), (0, 1), (1, 1)], dtype=np.float32)
    img = render.render([render.Part(pos, tris, None, uv, red)], size=32)
    assert img.shape == (32, 32, 4)
    covered = img[..., 3] > 0
    assert covered.sum() > 200                              # a quad seen at an angle
    assert (img[covered][:, 0] > img[covered][:, 1]).all()   # red, not grey
    # the triangle lattice: every point inside its triangle, none repeated
    k = np.array([1, 3, 7])
    ti, u, v = render._lattice(k)
    assert len(ti) == sum((x + 1) * (x + 2) // 2 for x in k)
    assert (u >= 0).all() and (v >= 0).all() and (u + v <= 1 + 1e-12).all()
    pts = {(int(t), round(float(a), 9), round(float(b), 9)) for t, a, b in zip(ti, u, v)}
    assert len(pts) == len(ti)
    assert render.render([], 16) is None


def test_plan_layout_and_name_clashes(tmp_path):
    rows = [{"id": 1, "name": "rock.big", "vpath": "data/env/a.big/rock.big", "kind": "model",
             "grp": "environments", "sub": "canyon / z01"},
            {"id": 2, "name": "rock.big", "vpath": "data/env/b.big/rock.big", "kind": "model",
             "grp": "environments", "sub": "canyon / z01"},
            {"id": 3, "name": "HB_Indemnify.xma", "vpath": "data/audio/music.big/HB_Indemnify.xma",
             "kind": "audio", "grp": "music", "sub": ""}]
    jobs = cx.plan(rows, tmp_path, "cz")
    assert [j.dest.relative_to(tmp_path).as_posix() for j in jobs] == [
        "cz/environments/canyon-z01/rock", "cz/environments/canyon-z01/rock__b",
        "cz/music/HB_Indemnify"]
    single = cx.plan(rows[:1], tmp_path, "cz", by_group=False)
    assert single[0].dest == tmp_path / "rock"


def test_export_model_folder_resume_and_cancel(game, tmp_path):
    root, db, _st = game
    ex = cx.Exporter(AssetTree(root), "cz", db)
    con = connect(db)
    hero = dict(query.get(con, "cz", "data/models/npcs.big/chest_hero.big"))
    res = ex.run(cx.plan([hero], tmp_path / "out", "cz", by_group=False))
    folder = tmp_path / "out" / "chest_hero"
    assert res.failed == [] and res.done == 1
    names = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
    assert names == ["chest_hero.glb", "info.txt", "skeleton.glb", "textures/box_cm.png",
                     "textures/textures.txt"]
    info = (folder / "info.txt").read_text()
    assert "Hero (chest)" in info and "rig:" in info and "herofullbody.big" in info
    assert "colour" in (folder / "textures" / "textures.txt").read_text()
    assert not list(folder.rglob("*.part"))
    again = ex.run(cx.plan([hero], tmp_path / "out", "cz", by_group=False))
    assert again.written == [] and len(again.skipped) == 5          # resumable
    # a whole group, only PNGs (and each folder's info.txt); a cancelled run writes nothing
    rows = cx.group_rows(con, "cz", "characters")
    res = cx.Exporter(AssetTree(root), "cz", db, {"png"}).run(cx.plan(rows, tmp_path / "g", "cz",
                                                                      con=con))
    assert {p.name for p in res.written} == {"box_cm.png", "textures.txt", "info.txt"}
    stopped = ex.run(cx.plan(rows, tmp_path / "c", "cz", con=con), cancel=lambda: True)
    assert stopped.cancelled and stopped.written == []
    with pytest.raises(Exception, match="no such Library group"):
        cx.group_rows(con, "cz", "nothing")
    ex.close()


def test_cli_library_and_export(game, tmp_path, capsys):
    _root, db, _st = game
    assert main(["library", "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "characters" in out and "Models" in out
    assert main(["library", "characters", "--db", str(db)]) == 0
    assert "Bob (survivor)" in capsys.readouterr().out
    assert main(["library", "--check", "-g", "cz", "--db", str(db)]) == 0
    assert "0 problem(s)" in capsys.readouterr().out
    out_dir = tmp_path / "x"
    assert main(["export", "characters", "rigs", "-o", str(out_dir), "--db", str(db), "-q"]) == 0
    assert (out_dir / "cz" / "characters" / "survivors" / "srv_bob" / "srv_bob.glb").is_file()
    assert (out_dir / "cz" / "rigs" / "herofullbody" / "herofullbody.glb").is_file()
    assert main(["export", "data/notes.csv", "-o", str(out_dir), "--db", str(db), "--list"]) == 0
    assert "notes" in capsys.readouterr().out


@pytest.mark.skipif(not render.available(), reason="numpy not installed")
def test_baked_material_colour_wins_over_the_texture():
    """Zombie clothing: the colour baked from shader constants is drawn, not the weight
    map its colour texture really is (the Library's pictures, like the .glb export)."""
    import numpy as np
    from dr2kit.formats.scene import Scene
    sc = Scene.parse(make_scene())
    green = np.zeros((2, 2, 4), dtype=np.float32)
    green[..., 1] = green[..., 3] = 1.0
    red = np.zeros((2, 2, 4), dtype=np.float32)
    red[..., 0] = red[..., 3] = 1.0
    parts = render.scene_parts(sc, lambda name: red, None, lambda m: green)
    assert parts and all(p.texture is green for p in parts)
    parts = render.scene_parts(sc, lambda name: red, None, lambda m: None)
    assert all(p.texture is red for p in parts)          # no bake: the texture


def test_new_thumbnail_version_redraws_pictures(game, monkeypatch):
    root, db, _st = game
    st = build_index("cz", AssetTree(root), db)
    assert st.thumbnails == 0                               # nothing changed
    monkeypatch.setattr(ibuild, "THUMB_VERSION", "test")
    st = build_index("cz", AssetTree(root), db)
    assert st.thumbnails == (3 if render.available() else 0)


@pytest.mark.skipif(not render.available(), reason="numpy not installed")
def test_render_alpha_test_and_large_pictures():
    import numpy as np
    pos = np.array([(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)], dtype=np.float32)
    tris = np.array([(0, 1, 2), (2, 1, 3)], dtype=np.int32)
    uv = np.array([(0, 0), (1, 0), (0, 1), (1, 1)], dtype=np.float32)
    half = np.ones((1, 2, 4), dtype=np.float32)
    half[0, 1, 3] = 0.0                                   # right half see-through
    solid = render.render([render.Part(pos, tris, None, uv, half)], 32)
    cut = render.render([render.Part(pos, tris, None, uv, half, alpha_test=True)], 32)
    assert 0.3 < (cut[..., 3] > 0).sum() / (solid[..., 3] > 0).sum() < 0.7
    # pictures bigger than 128 px need wider pixel numbers in the sort key: same coverage
    small = render.render([render.Part(pos, tris, None, None, None)], 128)
    large = render.render([render.Part(pos, tris, None, None, None)], 512)
    assert abs(small[..., 3].mean() - large[..., 3].mean()) / 255 < 0.02     # was 0.57 off

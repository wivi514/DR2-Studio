"""String banks (`dr2kit.formats.bcs`), the strings helpers and string mods, on
synthetic banks (no game text in tests)."""

import json
import struct

import pytest

from dr2kit.cli.main import main
from dr2kit.container.vpath import AssetTree
from dr2kit.convert import strings as cstr
from dr2kit.errors import FormatError
from dr2kit.formats import bcs
from dr2kit.mods import build as mbuild
from dr2kit.mods.manifest import Mod, ModError, create

from conftest import make_archive


def bank_bytes(strings: dict, pad_to: int = 0) -> bytes:
    """A bank built field by field, as docs/formats.md §Strings describes it."""
    ids = sorted(strings)
    n = len(ids)
    blob, offs = b"", []
    for i in ids:
        offs.append(4 + 8 * n + len(blob))
        blob += strings[i].encode() + b"\0"
    out = struct.pack(f"<I{n}I{n}I", n, *ids, *offs) + blob
    return out + bytes(max(0, pad_to - len(out)))


EN = {1: "_", 3: "START DEMO", 10: "@Press [@butstart] to skip", 20: "Day %d of %s",
      99: "Yeap, its always missing."}
LABELS = {1: "IDS_SPACE", 3: "IDS_START_DEMO", 10: "IDS_SKIP", 20: "IDS_DAY", 99: "IDS_LAST"}


def test_round_trip_padded_and_unpadded():
    for pad in (0, 300):
        data = bank_bytes(EN, pad)
        bank = bcs.StringBank.parse(data, "t")
        assert bank.strings == EN
        assert bank.to_bytes() == data


def test_reader_names_what_is_wrong():
    data = bytearray(bank_bytes(EN, 200))
    data[-1] = 7
    with pytest.raises(FormatError, match="not all zero"):
        bcs.StringBank.parse(bytes(data), "t")
    bad = bytearray(bank_bytes(EN))
    struct.pack_into("<I", bad, 4 + 4 * len(EN) + 4, 9999)      # second offset
    with pytest.raises(FormatError, match="back to back"):
        bcs.StringBank.parse(bytes(bad), "t")
    with pytest.raises(FormatError, match="too short"):
        bcs.StringBank.parse(b"\1", "t")


def test_edited_bank_keeps_size_when_it_fits():
    bank = bcs.StringBank.parse(bank_bytes(EN, 400))
    new, notes = bcs.apply(bank, {3: "START"})
    assert len(new.to_bytes()) == 400 and not notes
    big, _ = bcs.apply(bank, {3: "X" * 500})
    assert len(big.to_bytes()) > 400                     # written unpadded, as it must
    assert bcs.StringBank.parse(big.to_bytes()).strings[3] == "X" * 500


def test_apply_notes_and_rules():
    bank = bcs.StringBank.parse(bank_bytes(EN))
    _, notes = bcs.apply(bank, {10: "Press [@butstart]", 20: "Day %d"})
    assert any("start it with @" in n for n in notes)
    assert any("%s" in n for n in notes)
    _, notes = bcs.apply(bank, {5: "new"})
    assert any("new id" in n for n in notes)
    with pytest.raises(FormatError, match="last id"):
        bcs.apply(bank, {100: "after the last"})


def test_json_round_trip_and_labels():
    bank = bcs.StringBank.parse(bank_bytes(EN))
    text = bcs.to_json(bank, "data/frontend/str_en.bcs", LABELS)
    doc = json.loads(text)
    assert doc["labels"]["3"] == "IDS_START_DEMO"
    assert bcs.from_json(text) == EN
    by_label = {v: k for k, v in LABELS.items()}
    assert bcs.from_json('{"strings": {"IDS_START_DEMO": "GO"}}', "t", by_label) == {3: "GO"}
    with pytest.raises(FormatError, match="not a string id"):
        bcs.from_json('{"strings": {"START": "GO"}}')


@pytest.fixture
def game(tmp_path, monkeypatch):
    root = tmp_path / "assets" / "game"
    fe = root / "data" / "frontend"
    fe.mkdir(parents=True)
    (root / "data" / "datafile.big").write_bytes(make_archive(("a.txt", b"a")).to_bytes())
    (fe / "str_en.bcs").write_bytes(bank_bytes(EN, 512))
    (fe / "str_fr.bcs").write_bytes(bank_bytes({**EN, 3: "LANCER DÉMO"}, 512))
    (fe / "str_id.bcs").write_bytes(bank_bytes(LABELS, 512))
    monkeypatch.setenv("DR2_CZ_DATA", str(root))
    return root


def mod_with(tmp_path, name, strings, priority=0):
    root = create(tmp_path / name, name)
    if priority:
        t = (root / "mod.toml").read_text().replace("priority = 0", f"priority = {priority}")
        (root / "mod.toml").write_text(t)
    f = root / "replace/data/frontend/str_en.bcs.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"strings": strings}))
    return Mod.load(root)


def test_strings_helpers(game):
    tree = AssetTree(game)
    assert cstr.languages(tree) == ["en", "fr", "id"]
    assert cstr.resolve_id("ids_start_demo", cstr.load_labels(tree)) == 3
    hits = cstr.search(tree, "démo", ["en", "fr"])
    assert [(h.id, h.lang) for h in hits] == [(3, "fr")]


def test_string_mods_merge_by_id(game, tmp_path):
    tree = AssetTree(game)
    a = mod_with(tmp_path, "a", {"3": "A3", "IDS_SPACE": "A1"})
    b = mod_with(tmp_path, "b", {"3": "B3", "20": "Day %d of %s!"}, priority=2)
    plan = mbuild.plan_mods([a, b], "cz", tree)
    assert ("data/frontend/str_en.bcs id 3", "a", "b") in plan.shadowed
    res = mbuild.build([a, b], "cz", tree, tmp_path / "out")
    got = bcs.StringBank.parse((tmp_path / "out/data/frontend/str_en.bcs").read_bytes())
    assert got.strings[3] == "B3" and got.strings[1] == "A1" and got.strings[20] == "Day %d of %s!"
    assert len((tmp_path / "out/data/frontend/str_en.bcs").read_bytes()) == 512
    assert res.files == ["data/frontend/str_en.bcs"]
    c = mod_with(tmp_path, "c", {"3": "C3"})
    with pytest.raises(ModError, match="same priority"):
        mbuild.plan_mods([a, c], "cz", tree)


def test_whole_bank_and_strings_conflict(game, tmp_path):
    a = mod_with(tmp_path, "a", {"3": "A3"})
    b = create(tmp_path / "b", "b")
    (b / "replace/data/frontend").mkdir(parents=True)
    (b / "replace/data/frontend/str_en.bcs").write_bytes(bank_bytes(EN))
    with pytest.raises(ModError, match="as a whole"):
        mbuild.plan_mods([a, Mod.load(b)], "cz", AssetTree(game))


def test_digest_checked_files_are_refused(tmp_path, monkeypatch):
    root = tmp_path / "game"
    (root / "data" / "audio").mkdir(parents=True)
    (root / "data" / "datafile.big").write_bytes(make_archive(("a.txt", b"a")).to_bytes())
    (root / "data" / "audio" / "Prologue.txt").write_text("cAudioScene x\n{\n}\n")
    m = create(tmp_path / "m", "m")
    (m / "replace/data/audio").mkdir(parents=True)
    (m / "replace/data/audio/prologue.txt").write_text("edited")
    with pytest.raises(ModError, match="digest"):
        mbuild.plan_mods([Mod.load(m)], "cz", AssetTree(root))


def test_cli_strings(game, tmp_path, capsys):
    mod = tmp_path / "m"
    assert main(["mod", "new", str(mod)]) == 0
    assert main(["strings", "set", str(mod), "IDS_START_DEMO", "GO GO"]) == 0
    assert main(["strings", "set", str(mod), "20", "Jour %d"]) == 0
    err = capsys.readouterr().err
    assert "%s" in err                                      # placeholder dropped: noted
    doc = json.loads((mod / "replace/data/frontend/str_en.bcs.json").read_text())
    assert doc["strings"] == {"3": "GO GO", "20": "Jour %d"}
    assert doc["original"]["3"] == "START DEMO"
    assert main(["strings", "unset", str(mod), "20"]) == 0
    assert main(["strings", "search", "go", "--lang", "all"]) == 0
    assert main(["strings", "show", "3"]) == 0
    assert "LANCER DÉMO" in capsys.readouterr().out
    assert main(["strings", "export", "--lang", "all", "-o", str(tmp_path / "x")]) == 0
    assert (tmp_path / "x" / "str_fr.bcs.json").is_file()
    assert main(["mod", "build", str(mod), "-o", str(tmp_path / "out")]) == 0
    got = bcs.StringBank.parse((tmp_path / "out/data/frontend/str_en.bcs").read_bytes())
    assert got.strings[3] == "GO GO" and got.strings[20] == EN[20]

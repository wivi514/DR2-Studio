"""Moves brought into the other game's animation graph (`dr2kit.convert.graphcarry`), the
graph header's counts (`leveledits.recount`) and ``@text`` adds. The game-data tests SKIP,
saying why, when a game isn't installed."""

import pytest

from dr2kit.formats import leveledits as le
from dr2kit.formats.levelscript import Document

GRAPH = b"""# cGenericAnimState 1\r
# cCategoryChooser 1\r
# cChooserEntryInt 1\r
# cAnimRef 1\r
\r
cGenericAnimState 10\r
{\r
\tAbsoluteTranslationMode = "false"\r
\r
\tcCategoryChooser cRandomChooser\r
\t{\r
\t\tChooserType = "ATTACKWEAPONTYPE"\r
\r
\t\tcChooserEntryInt a_move\r
\t\t{\r
\t\t\tAnim = 1\r
\t\t\tValue = 0\r
\t\t}\r
\r
\t}\r
\r
\tcAnimRef 1\r
\t{\r
\t\tFile = 123\r
\t\tLooping = "false"\r
\t}\r
\r
}\r
\r
"""


def test_text_add_keeps_the_source_style_and_recount():
    doc = Document.parse(GRAPH)
    text = "cAnimRef 2\n{\n\tFile = -5\n\tDataRate = 1.000000\n}\n"
    doc.add(doc.find("cGenericAnimState 10"), "cAnimRef", "2", text=text)
    e = le.diff(Document.parse(GRAPH), doc)
    assert e.add["cGenericAnimState 10/cAnimRef 2"] == {"@text": text}
    out, _ = le.apply_all(GRAPH, [le.Layer("m", 0, le.from_json(le.to_json(e), "t"))])
    assert b"\t\tFile = -5\r\n" in out                      # unquoted, as given
    assert out.startswith(b"# cGenericAnimState 1\r\n# cCategoryChooser 1\r\n"
                          b"# cChooserEntryInt 1\r\n# cAnimRef 2\r\n")
    assert le.recount(GRAPH, Document.parse(GRAPH)) == GRAPH


def test_repeated_names_are_numbered_from_one():
    doc = Document.parse(b"A\r\n{\r\n\tB x\r\n\t{\r\n\t}\r\n\r\n\tB x\r\n\t{\r\n\t\tK = \"1\"\r\n\t}\r\n\r\n}\r\n")
    second = doc.blocks[0].children[1]
    assert doc.path(second) == "A/B x#2" and doc.find("A/B x#2") is second


@pytest.mark.gamedata
def test_impact_hammer_moves_carried_into_case_zero(game_root):
    from dr2kit.container.vpath import AssetTree
    from dr2kit.convert import graphcarry as gc
    src = Document.parse(AssetTree(game_root("cw")).resolve(gc.GRAPH).data())
    dst = Document.parse(AssetTree(game_root("cz")).resolve(gc.GRAPH).data())
    top = gc._numbered(dst)
    c = gc.carry(src, dst, "ATTACKWEAPONTYPE", "396")
    assert c.added == 1 and c.value == "396" and c.entries == ["impact_hammer_smash210421"]
    ref = next(b for b in dst.walk() if b.cls == "cAnimRef" and b.name == str(top + 1))
    assert ref.get("File") == "779333524" and ref.props[0].quoted is False
    again = gc.carry(src, dst, "ATTACKWEAPONTYPE", "396")      # already there: kept
    assert again.added == 0 and again.value == "396"
    laser = gc.carry(src, dst, "ATTACKWEAPONTYPE", "328")      # Case Zero has the move
    assert laser.added == 0

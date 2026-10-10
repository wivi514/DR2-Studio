"""The in-app help (`dr2kit.help`): pages, order, search, context help, links.

The help is the modding guides, so these tests also keep the guides healthy: every
link between them must lead somewhere, and every context entry must name a real guide.
"""

import re
from pathlib import Path

import pytest

from dr2kit import help as dhelp
from dr2kit.cli.main import main

DOCS = Path(__file__).resolve().parents[1] / "docs"


def test_topics_follow_the_guides_index():
    names = [t.name for t in dhelp.topics()]
    assert names[0] == "README.md" and names[-1] == "glossary.md"
    assert names.index("01-install.md") < names.index("05-first-mod-texture.md")
    assert all("`" not in t.title for t in dhelp.topics())
    assert dhelp.read("glossary.md").startswith("# Glossary")


def test_search_and_context():
    hits = dhelp.search("digest")
    assert hits and any(h.topic.name == "11-text.md" for h in hits)
    assert dhelp.search("") == []
    ctx = dhelp.context("texture-pack")              # alias of texture
    assert ctx.title == "Change this texture" and ctx.guide == "05-first-mod-texture.md"
    assert dhelp.context("no-such-kind") is None


def test_every_context_entry_names_a_guide():
    import tomllib
    data = tomllib.loads((DOCS / "modding" / "context.toml").read_text())
    for kind, entry in data.items():
        assert dhelp.page_path(entry["guide"]), (kind, entry["guide"])
        assert entry["steps"], kind


def test_context_links_reach_a_section():
    """Links in "How to mod this" steps open a guide at a heading that exists."""
    import tomllib
    from dr2kit.studio.help_view import slug
    data = tomllib.loads((DOCS / "modding" / "context.toml").read_text())
    links = [m for e in data.values() for st in e["steps"]
             for m in re.finditer(r"\]\(([^)#\s]+)#([^)\s]+)\)", st)]
    assert links                                           # the Blender tips, at least
    for m in links:
        page, section = m.group(1), m.group(2)
        heads = [slug(h.lstrip("#")) for h in dhelp.read(page).splitlines() if h.startswith("#")]
        assert section in heads, (page, section)
    assert dhelp.search("Material Preview")                 # findable from the help's search


def test_links_between_guides_resolve():
    bad = []
    for page in (DOCS / "modding").glob("*.md"):
        for m in re.finditer(r"\]\(([^)#\s]+)(#[^)]*)?\)", page.read_text()):
            target = m.group(1)
            if target.startswith(("http:", "https:", "mailto:")):
                continue
            if not (page.parent / target).exists():
                bad.append(f"{page.name}: {target}")
    assert bad == []


def test_falls_back_to_english(monkeypatch):
    assert dhelp.help_root("xx") == dhelp.help_root("en")
    assert dhelp.page_path("05-first-mod-texture.md", "xx") is not None


def test_cli_help(capsys):
    assert main(["help"]) == 0
    assert "05-first-mod-texture.md" in capsys.readouterr().out
    assert main(["help", "text"]) == 0
    assert capsys.readouterr().out.startswith("# Change in-game text")
    assert main(["help", "--search", "dr2mod"]) == 0
    assert "06-mod-packages.md" in capsys.readouterr().out
    assert main(["help", "nothing-like-this"]) == 1


def test_error_messages_lead_to_help():
    pytest.importorskip("PySide6")
    from dr2kit.studio.app import help_for_error
    page, _ = help_for_error("The picture is 512×512; this texture needs exactly 1024×1024 "
                             "(resize it in your editor).")
    assert page == "05-first-mod-texture.md"
    assert help_for_error("zzz") == ("12-troubleshooting.md", "")

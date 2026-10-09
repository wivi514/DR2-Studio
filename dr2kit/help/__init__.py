"""The in-app help: the modding guides, found, listed, searched and linked.

Why: modders should never have to leave DR2 Studio (or the terminal) to find out what
to do. The help *is* the modding guides (``docs/modding/*.md`` and the glossary), so
there is one text to keep current, and the guides follow the documentation rules.

Where the files are (`help_root`):

* a built package (pip install, a release): ``dr2kit/help/<lang>/``, copied there at
  build time by ``setup.py``;
* a source checkout: ``docs/modding/`` (English) and ``docs/modding/<lang>/`` for a
  translation, plus ``docs/glossary.md``.

**Languages:** English is complete. A translation is a folder of the same file names;
a page it lacks falls back to English (`page_path`), so a partial translation works.

**Context help** (``context.toml`` next to the guides): for each asset kind, a title,
a few steps and the guide to open: what DR2 Studio shows next to the selected asset
("How to mod this").

Used by DR2 Studio's help window (`dr2kit.studio.help_view`) and ``dr2 help``.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LANG = "en"
_HERE = Path(__file__).resolve().parent
_CHECKOUT_DOCS = _HERE.parents[1] / "docs"
_LINK = re.compile(r"\[[^\]]*\]\(([^)#\s]+\.md)(#[^)]*)?\)")


def languages() -> list[str]:
    """The help languages available (``en`` first)."""
    found = {DEFAULT_LANG}
    if any(_HERE.glob("*/README.md")):
        found |= {d.name for d in _HERE.iterdir() if (d / "README.md").is_file()}
    modding = _CHECKOUT_DOCS / "modding"
    if modding.is_dir():
        found |= {d.name for d in modding.iterdir() if d.is_dir() and len(d.name) == 2}
    return [DEFAULT_LANG] + sorted(found - {DEFAULT_LANG})


def help_root(lang: str = DEFAULT_LANG) -> Path:
    """The folder holding the guides of ``lang`` (English if that language is absent).
    Raises FileNotFoundError if no help is installed at all."""
    for cand in (_HERE / lang, _CHECKOUT_DOCS / "modding" / lang if lang != DEFAULT_LANG
                 else _CHECKOUT_DOCS / "modding"):
        if (cand / "README.md").is_file():
            return cand
    if lang != DEFAULT_LANG:
        return help_root(DEFAULT_LANG)
    raise FileNotFoundError("the help files are missing (dr2kit/help/en or docs/modding)")


def page_path(name: str, lang: str = DEFAULT_LANG) -> Path | None:
    """The file of page ``name`` (``05-first-mod-texture.md``, ``glossary.md``), in
    ``lang`` or else English; None if it doesn't exist."""
    for root in dict.fromkeys([help_root(lang), help_root(DEFAULT_LANG)]):
        p = root / name
        if p.is_file():
            return p
        if name == "glossary.md":
            for g in (root / ".." / "glossary.md", _CHECKOUT_DOCS / "glossary.md"):
                if g.resolve().is_file() and g.resolve().parent != _HERE:
                    return g.resolve()
    return None


@dataclass
class Topic:
    name: str        # file name, the topic's id ("05-first-mod-texture.md")
    title: str       # its first heading


def title_of(path: Path) -> str:
    for line in path.read_text("utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip().replace("`", "")
    return path.stem


def topics(lang: str = DEFAULT_LANG) -> list[Topic]:
    """Every page in reading order: the guides index first, then the guides in the
    order its table lists them, then any other page, then the glossary."""
    root = help_root(lang)
    readme = root / "README.md"
    order = ["README.md"]
    table = "\n".join(ln for ln in readme.read_text("utf-8").splitlines()
                      if ln.startswith("|"))           # the guides table sets the order
    for m in _LINK.finditer(table):
        name = m.group(1)
        if "/" not in name and name not in order and page_path(name, lang):
            order.append(name)
    rest = sorted(p.name for p in help_root(DEFAULT_LANG).glob("*.md")
                  if p.name not in order and p.name != "glossary.md")
    order += rest + ["glossary.md"]
    out = []
    for name in order:
        p = page_path(name, lang)
        if p is not None:
            out.append(Topic(name, "Guides: start here" if name == "README.md" else title_of(p)))
    return out


def read(name: str, lang: str = DEFAULT_LANG) -> str:
    p = page_path(name, lang)
    if p is None:
        raise FileNotFoundError(f"no help page {name!r}")
    return p.read_text("utf-8")


@dataclass
class Hit:
    topic: Topic
    heading: str     # the section the match is in
    line: str        # the matching line, trimmed


def search(text: str, lang: str = DEFAULT_LANG, limit: int = 100) -> list[Hit]:
    """Lines of the help containing every word of ``text`` (any case), with the
    section they're in; pages whose title matches come first."""
    words = [w.lower() for w in text.split() if w]
    if not words:
        return []
    hits: list[Hit] = []
    for t in topics(lang):
        heading = t.title
        for line in read(t.name, lang).splitlines():
            if line.startswith("#"):
                heading = line.lstrip("#").strip()
            low = line.lower()
            if all(w in low for w in words):
                hits.append(Hit(t, heading, line.strip()[:200]))
    hits.sort(key=lambda h: not all(w in h.topic.title.lower() for w in words))
    return hits[:limit]


@dataclass
class Context:
    """What to show next to an asset of one kind ("How to mod this")."""
    title: str
    steps: list[str]
    guide: str       # the page to open for more


def context(kind: str, lang: str = DEFAULT_LANG) -> Context | None:
    """The context help for an asset ``kind`` (``texture``, ``model``…), or None."""
    for root in dict.fromkeys([help_root(lang), help_root(DEFAULT_LANG)]):
        f = root / "context.toml"
        if f.is_file():
            data = tomllib.loads(f.read_text("utf-8"))
            entry = data.get(kind) or data.get(_KIND_ALIASES.get(kind, ""), None)
            if entry:
                return Context(entry["title"], list(entry.get("steps", [])),
                               entry.get("guide", "README.md"))
    return None


_KIND_ALIASES = {"texture-pack": "texture", "sfx": "audio", "skeleton": "model"}

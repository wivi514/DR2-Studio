"""Strings for people: find a string, export a bank as JSON, change one in a mod.

`dr2kit.formats.bcs` reads and writes the bank files; this module works at the level a
modder thinks in: "the text that says START DEMO, in English", "every string mentioning
Zombrex". It finds the banks in a game (``data/frontend/str_<lang>.bcs``), attaches the
labels from ``str_id.bcs`` (``IDS_START_DEMO``), and writes changes into a mod as
``replace/data/frontend/str_<lang>.bcs.json``, which `dr2kit.mods.build` applies (only
the listed ids change; several mods merge). Guide: docs/modding/11-text.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..container.vpath import AssetTree
from ..errors import Dr2Error
from ..formats import bcs

FRONTEND = "data/frontend"


def bank_vpath(lang: str) -> str:
    """``en`` → ``data/frontend/str_en.bcs`` (``id`` and ``lg`` work too)."""
    return f"{FRONTEND}/str_{lang.lower()}.bcs"


def languages(tree: AssetTree) -> list[str]:
    """The banks a game has, as language codes (``en``, ``fr``, … ``id``, ``lg``)."""
    node = tree.resolve(FRONTEND)
    return sorted(p.name[4:-4].lower() for p in node.path.iterdir()
                  if p.name.lower().startswith("str_") and p.name.lower().endswith(".bcs"))


def load_bank(tree: AssetTree, lang: str) -> bcs.StringBank:
    """The parsed bank of ``lang``. Raises `Dr2Error` if the game has no such bank."""
    vp = bank_vpath(lang)
    try:
        data = tree.resolve(vp).data()
    except Dr2Error:
        raise Dr2Error(f"no string bank {vp} (languages: "
                       f"{', '.join(languages(tree))})") from None
    return bcs.StringBank.parse(data, vp)


def load_labels(tree: AssetTree) -> dict[int, str]:
    """id → ``IDS_…`` label (empty if the game has no ``str_id.bcs``)."""
    try:
        return load_bank(tree, "id").strings
    except Dr2Error:
        return {}


def resolve_id(key: str | int, labels: dict[int, str]) -> int:
    """A string id from ``"3"``, ``3`` or ``"IDS_START_DEMO"``."""
    k = str(key).strip()
    if k.isdigit():
        return int(k)
    for i, name in labels.items():
        if name.upper() == k.upper():
            return i
    raise Dr2Error(f"{key!r} is neither a string id nor a known label (IDS_…)")


@dataclass
class Hit:
    id: int
    label: str
    lang: str
    text: str


def search(tree: AssetTree, text: str, langs: list[str] | None = None,
           limit: int = 200) -> list[Hit]:
    """Strings whose text or label contains ``text`` (any case), in ``langs``
    (default: English)."""
    labels = load_labels(tree)
    needle = text.lower()
    out: list[Hit] = []
    for lang in langs or ["en"]:
        for i, t in load_bank(tree, lang).strings.items():
            if needle in t.lower() or needle in labels.get(i, "").lower() or needle == str(i):
                out.append(Hit(i, labels.get(i, ""), lang, t))
                if len(out) >= limit:
                    return out
    return out


def mod_strings_path(mod_dir: str | Path, lang: str) -> Path:
    """Where a mod keeps its string changes for ``lang``."""
    return Path(mod_dir) / "replace" / (bank_vpath(lang) + ".json")


def read_mod_strings(mod_dir: str | Path, lang: str) -> dict[int, str]:
    """The string changes a mod already has for ``lang`` (empty if none)."""
    f = mod_strings_path(mod_dir, lang)
    if not f.is_file():
        return {}
    return bcs.from_json(f.read_text("utf-8-sig"), str(f))


def set_mod_strings(mod_dir: str | Path, lang: str, changes: dict[int, str],
                    labels: dict[int, str] | None = None,
                    original: dict[int, str] | None = None) -> Path:
    """Add or update string changes in a mod (``None`` as a text removes a change).

    The file keeps every change the mod had, sorted by id, with the label and the
    original text next to each as a reminder (``"labels"`` / ``"original"`` keys, which
    the build ignores)."""
    current = read_mod_strings(mod_dir, lang)
    for i, t in changes.items():
        if t is None:
            current.pop(i, None)
        else:
            current[i] = t
    f = mod_strings_path(mod_dir, lang)
    if not current:
        f.unlink(missing_ok=True)
        return f
    f.parent.mkdir(parents=True, exist_ok=True)
    doc: dict = {"format": bcs.JSON_FORMAT, "bank": bank_vpath(lang),
                 "strings": {str(i): current[i] for i in sorted(current)}}
    if labels:
        doc["labels"] = {str(i): labels[i] for i in sorted(current) if i in labels}
    if original:
        doc["original"] = {str(i): original[i] for i in sorted(current) if i in original}
    f.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return f

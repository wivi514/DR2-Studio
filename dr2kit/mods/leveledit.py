"""Edit a level text file *inside a mod*: the session the Maps tab and ``dr2 level edit``
share (phase 11).

A `TextEdits` opens one text file of ``datafile.big`` (``prologue.txt``,
``missions.txt``…) as the game has it (the recomp's ``game_patched`` copy when there is
one, as Play builds on it), applies the mod's ``.edits.json`` for that file if it has
one, and lets the caller change the `Document` freely (`levelscript.Document.set` /
`add` / `remove`). `save` writes the **difference** between the game's file and the
edited one (`leveledits.diff`) as the mod's
``replace/data/datafile.big/<file>.edits.json``, or deletes it when nothing is left. So
the mod always holds exactly its changes, however many times they were made and undone.

Undo and redo are snapshots of the text (`checkpoint` / `undo` / `redo`): files are small
(``missions.txt`` 222 KB) and a snapshot can't drift from what was saved.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..container.vpath import AssetTree, join, split
from ..convert import placed
from ..errors import Dr2Error
from ..formats import leveledits as le
from ..formats.levelscript import Document
from .manifest import REPLACE_DIR

UNDO_LIMIT = 200


def edits_path(mod_dir: str | Path, file: str) -> Path:
    """``<mod>/replace/data/datafile.big/<file>.edits.json``."""
    return Path(mod_dir).joinpath(REPLACE_DIR, *split(placed.DATAFILE), file + le.EXT)


def game_bytes(tree: AssetTree, file: str, base_dirs=()) -> bytes:
    """The text file as the game has it: the first ``base_dirs`` copy of
    ``datafile.big`` that holds it, else the shipped one."""
    vp = join(placed.DATAFILE, file)
    for b in base_dirs:
        if Path(b).joinpath(*split(placed.DATAFILE)).is_file():
            try:
                return AssetTree(b).resolve(vp).data()
            except Dr2Error:
                pass
    return tree.resolve(vp).data()


class TextEdits:
    """One mod's edits of one text file (module docstring)."""

    def __init__(self, mod_dir: str | Path, file: str, tree: AssetTree, base_dirs=()):
        self.mod_dir = Path(mod_dir)
        self.file = file
        self.vpath = join(placed.DATAFILE, file)
        self.original_bytes = game_bytes(tree, file, base_dirs)
        self.original = Document.parse(self.original_bytes, self.vpath)
        self.doc = Document.parse(self.original_bytes, self.vpath)
        self.notes: list[str] = []
        f = edits_path(mod_dir, file)
        if f.is_file():
            self.notes = le.apply(self.doc, le.from_json(f.read_text("utf-8-sig"), f.name))
        self._undo: list[bytes] = []
        self._redo: list[bytes] = []

    # ---- undo ----------------------------------------------------------------------------

    def checkpoint(self) -> None:
        """Remember the text before a change (call before every change)."""
        self._undo.append(self.doc.to_bytes())
        del self._undo[:-UNDO_LIMIT]
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.doc.to_bytes())
        self.doc = Document.parse(self._undo.pop(), self.vpath)
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.doc.to_bytes())
        self.doc = Document.parse(self._redo.pop(), self.vpath)
        return True

    # ---- what changed --------------------------------------------------------------------

    def edits(self) -> le.Edits:
        """The mod's changes as they would be saved."""
        return le.diff(self.original, self.doc)

    @property
    def dirty(self) -> bool:
        f = edits_path(self.mod_dir, self.file)
        saved = le.from_json(f.read_text("utf-8-sig")) if f.is_file() else le.Edits()
        return _canon(saved) != _canon(self.edits())

    def save(self) -> Path:
        """Write the mod's ``.edits.json`` (or remove it when nothing is changed)."""
        f = edits_path(self.mod_dir, self.file)
        e = self.edits()
        if not e:
            f.unlink(missing_ok=True)
            return f
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(le.to_json(e, self.vpath), "utf-8")
        return f


def _canon(e: le.Edits) -> str:
    return json.dumps({"s": e.set, "a": e.add, "r": sorted(e.remove)}, sort_keys=True)


def parse_assignments(items: list[str]) -> dict[str, str | None]:
    """``["Location=1,2,3", "PropState="]`` → ``{"Location": "1,2,3", "PropState": None}``
    (an empty value removes the key)."""
    out: dict[str, str | None] = {}
    for it in items:
        if "=" not in it:
            raise Dr2Error(f"{it!r}: write KEY=VALUE (KEY= to remove the key)")
        k, v = it.split("=", 1)
        out[k.strip()] = v.strip().strip('"') or None
    return out

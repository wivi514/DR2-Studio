"""Virtual paths: one address for any asset, however deeply it is nested.

A virtual path (vpath) is the asset's identity everywhere in the toolkit: the index, mod
manifests, the CLI and the GUI (CLAUDE.md, Conventions). It is the path of a file under
the game folder, then one ``/``-separated component per archive level::

    data/models/npcs.big/chest_default.tex/chest_default_cm
    └── file on disk ──┘ └─ entry ──────┘ └─ entry inside it ┘

Rules:

* Always ``/``, whatever the OS; ``\\`` is accepted on input and turned into ``/``.
* **Case-insensitive.** The games mix cases (``Prologue.txt``, ``chest_Bowling_…``)
  and Windows/macOS filesystems ignore case. A vpath is printed with the real case.
* Archive entry names repeat (a model holds several ``Combined Vertices``). The first
  one is ``name``; later ones are ``name#1``, ``name#2``… (0-based occurrence). An entry
  can also be addressed by position: ``@12`` is the entry at index 12.
  ``dr2 census`` checks that no real entry name contains ``#``, ``/`` or starts with
  ``@``, so these suffixes are never ambiguous.
* Compressed entries are decompressed on the way through: a compressed nested archive
  is opened like any other.

`AssetTree` resolves vpaths against one game folder and walks every archive in it.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ..errors import VPathError
from .big import BigArchive, BigEntry, is_big

_DUP = re.compile(r"^(.*)#(\d+)$")


def split(vpath: str) -> list[str]:
    """Split a vpath into components (``\\`` → ``/``; empty and ``.`` parts dropped)."""
    parts = [p for p in vpath.replace("\\", "/").split("/") if p not in ("", ".")]
    if ".." in parts:
        raise VPathError(f"{vpath}: '..' is not allowed in a virtual path")
    return parts


def join(*parts: str) -> str:
    """Join components into a vpath."""
    return "/".join(p.strip("/") for p in parts if p)


def entry_component(archive: BigArchive, entry: BigEntry) -> str:
    """The vpath component naming ``entry`` inside ``archive`` (``name`` or ``name#N``)."""
    occurrence = 0
    key = entry.name.lower()
    for e in archive.entries:
        if e is entry:
            break
        if e.name.lower() == key:
            occurrence += 1
    return entry.name if occurrence == 0 else f"{entry.name}#{occurrence}"


def entry_components(archive: BigArchive) -> list[str]:
    """`entry_component` for every entry, in order (one pass, for listings)."""
    seen: dict[str, int] = {}
    out = []
    for e in archive.entries:
        k = e.name.lower()
        n = seen.get(k, 0)
        seen[k] = n + 1
        out.append(e.name if n == 0 else f"{e.name}#{n}")
    return out


def find_entry(archive: BigArchive, component: str) -> BigEntry:
    """Look up one vpath component inside an archive (name, ``name#N`` or ``@N``)."""
    if component.startswith("@") and component[1:].isdigit():
        i = int(component[1:])
        if i >= len(archive.entries):
            raise VPathError(f"{archive.source}: no entry at position {i} "
                             f"(it has {len(archive.entries)})")
        return archive.entries[i]
    found = archive.find(component)
    if found:
        return found[0]
    m = _DUP.match(component)
    if m:
        found = archive.find(m.group(1))
        n = int(m.group(2))
        if n < len(found):
            return found[n]
    raise VPathError(f"{archive.source}: no entry named {component!r}")


@dataclass
class Node:
    """What a vpath points at: a folder, a file on disk, or an archive entry."""
    vpath: str                          # with the real letter case
    kind: str                           # "dir", "file" or "entry"
    path: Path | None = None            # for "dir" and "file"
    archive: BigArchive | None = None   # for "entry": the archive holding it
    entry: BigEntry | None = None       # for "entry"

    def data(self, decompress: bool = True) -> bytes:
        """The bytes: a file's contents, or an entry's asset (or stored bytes)."""
        if self.kind == "file":
            return self.path.read_bytes()
        if self.kind == "entry":
            return self.entry.data() if decompress else self.entry.stored
        raise VPathError(f"{self.vpath} is a folder")


class AssetTree:
    """The files and archives of one game folder, addressed by vpath.

    ``root`` is the folder that contains ``data/``. Opened archives are cached (a few at
    a time), since resolving many entries in one archive is the common case.
    """

    def __init__(self, root: str | Path, cache_size: int = 8):
        self.root = Path(root)
        self._cache: dict[str, BigArchive] = {}
        self._cache_size = cache_size

    @classmethod
    def for_game(cls, game: str) -> "AssetTree":
        from ..profiles import locate
        return cls(locate(game).root)

    # ---- resolving -----------------------------------------------------------------

    def resolve(self, vpath: str) -> Node:
        """Find what ``vpath`` points at, or raise `VPathError` naming the failing part."""
        parts = split(vpath)
        here = self.root
        real: list[str] = []
        i = 0
        while i < len(parts):
            if not here.is_dir():
                break
            child = _child_ci(here, parts[i])
            if child is None:
                raise VPathError(f"{join(*real, parts[i])}: no such file or folder")
            real.append(child.name)
            here = child
            i += 1
        if i == len(parts):
            return Node(join(*real), "dir" if here.is_dir() else "file", path=here)
        # `here` is a file and parts[i:] walk into it.
        archive = self._open_file(here, join(*real))
        while True:
            entry = find_entry(archive, parts[i])
            real.append(entry_component(archive, entry))
            i += 1
            if i == len(parts):
                return Node(join(*real), "entry", archive=archive, entry=entry)
            archive = self._open_entry(archive, entry, join(*real))

    def open_archive(self, vpath: str) -> BigArchive:
        """Open the archive at ``vpath`` (a `.big` file or a nested archive entry)."""
        node = self.resolve(vpath)
        if node.kind == "file":
            return self._open_file(node.path, node.vpath)
        if node.kind == "entry":
            return self._open_entry(node.archive, node.entry, node.vpath)
        raise VPathError(f"{node.vpath} is a folder, not an archive")

    def _open_file(self, path: Path, vpath: str) -> BigArchive:
        key = vpath.lower()
        if key in self._cache:
            return self._cache[key]
        with path.open("rb") as f:
            head = f.read(4)
        if not is_big(head):
            raise VPathError(f"{vpath}: not an archive (it starts {head.hex(' ')})")
        arc = BigArchive.parse(path.read_bytes(), vpath)
        self._remember(key, arc)
        return arc

    def _open_entry(self, parent: BigArchive, entry: BigEntry, vpath: str) -> BigArchive:
        key = vpath.lower()
        if key in self._cache:
            return self._cache[key]
        data = entry.data()
        if not is_big(data):
            raise VPathError(f"{vpath}: not an archive, so nothing can be inside it")
        arc = BigArchive.parse(data, vpath)
        self._remember(key, arc)
        return arc

    def _remember(self, key: str, arc: BigArchive) -> None:
        if len(self._cache) >= self._cache_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = arc

    # ---- listing and walking --------------------------------------------------------------

    def files(self) -> list[tuple[str, Path]]:
        """Every file under ``data/`` as ``(vpath, path)``, sorted, symlinks not followed."""
        out = []
        data = _child_ci(self.root, "data")
        if data is None:
            return out
        stack = [data]
        while stack:
            d = stack.pop()
            for p in d.iterdir():
                if p.is_symlink():
                    continue
                if p.is_dir():
                    stack.append(p)
                elif p.is_file():
                    out.append((p.relative_to(self.root).as_posix(), p))
        return sorted(out, key=lambda t: t[0].lower())

    def walk_archives(self, on_error=None) -> Iterator[tuple[str, BigArchive, int]]:
        """Yield ``(vpath, archive, depth)`` for every archive, nested ones included.

        Depth 0 is a file on disk. Nested archives are found by their magic, after
        decompression. ``on_error(vpath, exception)`` is called for anything that fails
        to open (and the walk goes on); without it, errors are raised.
        """
        for vp, path in self.files():
            with path.open("rb") as f:
                if not is_big(f.read(4)):
                    continue
            try:
                arc = BigArchive.parse(path.read_bytes(), vp)
            except Exception as e:  # noqa: BLE001 - reported, never swallowed
                if on_error is None:
                    raise
                on_error(vp, e)
                continue
            yield from _walk(arc, vp, 0, on_error)


def _walk(arc: BigArchive, vp: str, depth: int, on_error) -> Iterator[tuple[str, BigArchive, int]]:
    yield vp, arc, depth
    for comp, e in zip(entry_components(arc), arc.entries):
        child = join(vp, comp)
        try:
            if e.compressed:
                data = e.data()
            else:
                data = e.stored
            if not is_big(data):
                continue
            sub = BigArchive.parse(data, child)
        except Exception as ex:  # noqa: BLE001 - reported, never swallowed
            if on_error is None:
                raise
            on_error(child, ex)
            continue
        yield from _walk(sub, child, depth + 1, on_error)


def _child_ci(folder: Path, name: str) -> Path | None:
    """``folder/name`` ignoring case, returned with the name's real case."""
    low = name.lower()
    match = None
    for p in folder.iterdir():
        if p.name == name:
            return p
        if match is None and p.name.lower() == low:
            match = p
    return match

"""See the switched-on mods without the game: a view of the game data with them applied
(phase 10 step 5).

DR2 Studio shows every asset through an `AssetTree`. `Preview` plans a set of mods once
(the same mods, order and base copies as **Play**: `ModLibrary.active`, the recomp's
``game_patched`` copies) and `Preview.tree()` gives a `ModdedTree`: an `AssetTree` whose
archives come out of it **already patched**. When an archive is opened, every entry an
override replaces gets the replacement's bytes, and every entry that holds an override
deeper down gets its nested archive patched the same way. So every reader sees the mod,
including readers that parse a nested archive straight from an entry's bytes (the
texture finder does) and the Maps tab's zone builder, with no change to them.

**Exact bytes** (decision 2026-10-11): a replacement is built by the build's own
`mods.build.new_bytes` (a PNG encoded to DXT and tiled as the game's texture, a ``.glb``
rebuilt into the model, strings merged by id, level edits merged by block), so what Studio shows is what Play writes,
compression artefacts included; a test compares them byte for byte. Only the archives
*around* an override are written back uncompressed here (readers don't care; Play
re-compresses them for the game). Built replacements are cached in memory and on disk
(``<cache>/preview/``, named by the source file's size and date and the original's
SHA-1), so a big texture is encoded once.

A mod that fails its checks is left out and named in `problems` (the view shows the
original for it, never a half-applied mod). Sound replacements are not in the tree: the
recomp swaps sounds while playing (`mods.audio`); `changed` still lists them.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from pathlib import Path

from ..container.big import STORED, BigArchive, is_big
from ..container.vpath import AssetTree, Node, entry_components, join, split
from ..errors import Dr2Error
from . import build as mbuild
from .manifest import Mod


class _ModNode(Node):
    """A file on disk whose bytes a mod replaces."""
    def __init__(self, base: Node, data: bytes):
        super().__init__(base.vpath, base.kind, base.path, base.archive, base.entry)
        self._bytes = data

    def data(self, decompress: bool = True) -> bytes:
        return self._bytes


class Preview:
    """A set of mods applied to one game's data, planned once, shared by many trees."""

    def __init__(self, game: str, root: str | Path, mods: list[Mod], *,
                 base_dirs: list[Path] | tuple = (), cache_dir: str | Path | None = None):
        self.game, self.root = game, Path(root)
        self.base_dirs = [Path(b) for b in base_dirs]
        self.problems: list[str] = []
        self.mods: list[Mod] = []
        plain = AssetTree(self.root)
        plan = self._plan(list(mods), plain)
        self.audio = [p for p in plan if p.override.kind == "audio"]
        self.overrides: dict[str, list[mbuild.Planned]] = {}     # lower vpath -> planned
        for p in plan:
            if p.override.kind != "audio":
                self.overrides.setdefault(p.vpath.lower(), []).append(p)
        self._prefixes = sorted(self.overrides)
        if cache_dir is None:
            from ..userdirs import cache_dir as user_cache
            cache_dir = user_cache() / "preview"
        self.cache_dir = Path(cache_dir)
        self._memory: OrderedDict[str, bytes] = OrderedDict()
        self._lock = threading.Lock()

    @classmethod
    def for_play(cls, game: str, library=None, **kw) -> "Preview":
        """The mods Play would deploy for ``game`` (the mod library's switched-on mods,
        in its order), over the recomp's ``game_patched`` copies when there are some."""
        from ..profiles import locate
        from .deploy import recomp_folders
        from .library import ModLibrary
        lib = library or ModLibrary()
        root = locate(game).root
        patched = recomp_folders(root)["patched"]
        return cls(game, root, lib.active(game),
                   base_dirs=[patched] if patched.is_dir() else [], **kw)

    def _plan(self, mods: list[Mod], tree: AssetTree) -> list:
        """The plan of ``mods``; a mod that fails its checks (alone or with the others)
        is dropped and its problem kept in `problems`."""
        mods = [m for m in mods if self.game in m.games]
        try:
            plan = mbuild.plan_mods(mods, self.game, tree).planned
            self.mods = mods
            return plan
        except Dr2Error:
            pass
        keep = []
        for m in mods:
            try:
                mbuild.plan_mods([m], self.game, tree)
                keep.append(m)
            except Dr2Error as e:
                self.problems.append(f"{m.name or m.id}: {e}")
        try:
            plan = mbuild.plan_mods(keep, self.game, tree).planned
        except Dr2Error as e:                      # together they conflict: show none
            self.problems.append(str(e))
            keep, plan = [], []
        self.mods = keep
        return plan

    # ---- what is changed --------------------------------------------------------------

    @property
    def active(self) -> bool:
        return bool(self.overrides or self.audio)

    def changed(self, vpath: str) -> list[str]:
        """The mods that change ``vpath`` (or something inside it), by name."""
        low = vpath.lower()
        out = []
        for key, items in self.overrides.items():
            if key == low or key.startswith(low + "/"):
                out += [p.mod.name or p.mod.id for p in items]
        out += [p.mod.name or p.mod.id for p in self.audio if p.vpath.lower() == low]
        return list(dict.fromkeys(out))

    def touches(self, vpath_lower: str) -> bool:
        """An override is at ``vpath_lower`` or inside it."""
        pre = vpath_lower + "/"
        return vpath_lower in self.overrides or any(k.startswith(pre) for k in self._prefixes)

    def stamp(self, vpaths: list[str]) -> str:
        """A key for the overrides at or inside ``vpaths`` (their sources' sizes and
        dates): the Maps tab's zone files are named by it, so changing a mod's file
        rebuilds exactly the zones it touches."""
        parts = []
        lows = [v.lower() for v in vpaths]
        for key in self._prefixes:
            if any(key == v or key.startswith(v + "/") or v.startswith(key + "/")
                   for v in lows):
                for p in self.overrides[key]:
                    st = p.override.source.stat()
                    parts.append(f"{key}:{p.mod.id}:{st.st_size}:{st.st_mtime_ns}")
        return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12] if parts else ""

    # ---- bytes -----------------------------------------------------------------------

    def replacement(self, vpath_lower: str, original: bytes) -> bytes:
        """The bytes Play gives the game for an overridden asset (cached)."""
        items = self.overrides[vpath_lower]
        key = self._key(items, original)
        with self._lock:
            if key in self._memory:
                self._memory.move_to_end(key)
                return self._memory[key]
        path = self.cache_dir / f"{key}.bin"
        if path.is_file():
            data = path.read_bytes()
        else:
            data = mbuild.merged_bytes(items, original)
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".part")
                tmp.write_bytes(data)
                tmp.replace(path)
            except OSError:
                pass                                # a cache, not a must
        with self._lock:
            self._memory[key] = data
            while sum(len(v) for v in self._memory.values()) > 256 * 2**20 and \
                    len(self._memory) > 1:
                self._memory.popitem(last=False)
        return data

    @staticmethod
    def _key(items, original: bytes) -> str:
        h = hashlib.sha1(original)
        for p in items:
            st = p.override.source.stat()
            h.update(f"|{p.override.kind}|{p.override.source}|{st.st_size}|"
                     f"{st.st_mtime_ns}|{p.mod.priority}".encode())
        return h.hexdigest()

    def base_file(self, file_vpath: str) -> Path | None:
        """The ``game_patched`` copy of a file on disk, if Play would build on it."""
        for b in self.base_dirs:
            f = b.joinpath(*split(file_vpath))
            if f.is_file():
                return f
        return None

    def tree(self, cache_size: int = 16) -> "ModdedTree":
        return ModdedTree(self, cache_size)


class ModdedTree(AssetTree):
    """An `AssetTree` with a `Preview`'s mods applied (module docstring). Like any
    `AssetTree`, one per thread."""

    def __init__(self, preview: Preview, cache_size: int = 16):
        super().__init__(preview.root, cache_size)
        self.preview = preview

    def stamp(self, vpaths: list[str]) -> str:
        """For `convert.mapdata.stamp`: changes when an override in ``vpaths`` does."""
        return self.preview.stamp(vpaths)

    def resolve(self, vpath: str) -> Node:
        node = super().resolve(vpath)
        if node.kind == "file":
            low = node.vpath.lower()
            if self.preview.touches(low):
                return _ModNode(node, self._file_bytes(node))
        return node

    def _file_bytes(self, node: Node) -> bytes:
        low = node.vpath.lower()
        base = self.preview.base_file(node.vpath)
        original = (base or node.path).read_bytes()
        if low in self.preview.overrides:
            return self.preview.replacement(low, original)
        return self._patch(original, node.vpath)

    def _open_file(self, path: Path, vpath: str) -> BigArchive:
        key = vpath.lower()
        if not self.preview.touches(key) or key in self._cache:
            return super()._open_file(path, vpath)
        data = self._file_bytes(Node(vpath, "file", path=path))
        if not is_big(data):
            raise Dr2Error(f"{vpath}: a mod replaced it with something that is not an archive")
        arc = BigArchive.parse(data, vpath)
        self._remember(key, arc)
        return arc

    def _open_entry(self, parent: BigArchive, entry, vpath: str) -> BigArchive:
        # entries of a parent opened through this tree are already patched (`_patch`)
        return super()._open_entry(parent, entry, vpath)

    def _patch(self, data: bytes, vpath: str) -> bytes:
        """Archive bytes with every override inside them applied (stored, not
        re-compressed)."""
        if not is_big(data):
            return data
        arc = BigArchive.parse(data, vpath)
        self._apply(arc, vpath)
        return arc.to_bytes()

    def _apply(self, arc: BigArchive, vpath: str) -> None:
        pre = vpath.lower() + "/"
        for key, items in self.preview.overrides.items():      # new entries (add/)
            if key.startswith(pre) and "/" not in key[len(pre):] and \
                    items[-1].override.kind == "add" and \
                    not any(e.name.lower() == key[len(pre):] for e in arc.entries):
                arc.add(items[-1].vpath.rsplit("/", 1)[1],
                        mbuild.new_bytes(items[-1], b""), compression=STORED)
        for comp, e in zip(entry_components(arc), arc.entries):
            child = join(vpath, comp)
            low = child.lower()
            if low in self.preview.overrides:
                e.set_data(self.preview.replacement(low, e.data()), STORED)
            elif self.preview.touches(low):
                e.set_data(self._patch(e.data(), child), STORED)

    def walk_archives(self, on_error=None):
        raise Dr2Error("walking every archive with mods applied is not supported "
                       "(the index and the census read the game itself)")

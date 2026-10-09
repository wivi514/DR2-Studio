"""The mod manager: a library of installed mods, their order, and which are on.

Why: a player usually runs several mods at once (a texture pack, a sound swap, a
translation), and two of them may replace the same asset. The build already merges any
number of mods and decides conflicts by priority (`dr2kit.mods.build.plan_mods`); the
library adds what a player needs around it: one place where mods are installed, a
**load order** that sets the priorities, a switch per mod, and a deploy of everything
that is switched on.

The library is a folder (default: the per-user data folder, ``dr2 mod library FOLDER``
to change it, saved in the user config) holding one folder per mod and a
``modlist.toml``::

    mods/
      modlist.toml          # the order and the switches, written by the toolkit
      red_apron/            # a mod folder: mod.toml + replace/
      better_subtitles/

    # modlist.toml: later mods win over earlier ones
    [[mod]]
    id = "red_apron"
    enabled = true

Rules:

* **Order is priority.** The first mod in the list has the lowest priority, the last
  the highest; ``priority`` in a mod's own ``mod.toml`` only decides where it lands when
  it is installed. So two enabled mods never tie, and a conflict is never an error:
  the later mod wins and `ModLibrary.plan` lists what it hid (``ModPlan.shadowed``).
* Mods installed with `install` are enabled; a folder copied in by hand shows up
  disabled until it is enabled (nothing changes behind the player's back).
* A ``.zip`` installs if it holds one mod (``mod.toml`` at its top or in its one top
  folder). Entries that would land outside the library (absolute paths, ``..``) are
  refused. `pack` makes such a zip from a mod folder, for sharing.
"""

from __future__ import annotations

import dataclasses
import shutil
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .manifest import MANIFEST, Mod, ModError

LIST_FILE = "modlist.toml"


def default_library() -> Path:
    """The library folder: the user config's ``[mods] library``, else the per-user
    data folder's ``mods``."""
    from platformdirs import user_data_dir
    from ..profiles import get_config
    configured = get_config("mods", "library")
    if configured:
        return Path(configured).expanduser()
    return Path(user_data_dir("dr2kit", appauthor=False)) / "mods"


def set_default_library(folder: str | Path | None) -> None:
    """Remember ``folder`` as the library (``None``: back to the default)."""
    from ..profiles import set_config
    set_config("mods", "library", None if folder is None else str(Path(folder).resolve()))


@dataclass
class LibraryEntry:
    """One mod in the library: the mod, its switch, and its place (0 = lowest)."""
    mod: Mod
    enabled: bool
    position: int
    new: bool = False      # found on disk, not yet in modlist.toml


class ModLibrary:
    """A library folder. Read with `entries`; change with `install`, `remove`,
    `enable`, `move`; each change is saved to ``modlist.toml`` at once."""

    def __init__(self, folder: str | Path | None = None):
        self.folder = Path(folder) if folder else default_library()

    # ---- reading --------------------------------------------------------------------

    def _listed(self) -> list[dict]:
        f = self.folder / LIST_FILE
        if not f.is_file():
            return []
        try:
            raw = tomllib.loads(f.read_text("utf-8"))
        except tomllib.TOMLDecodeError as e:
            raise ModError(f"{f}: {e}") from None
        return [m for m in raw.get("mod", []) if isinstance(m, dict) and "id" in m]

    def _folders(self) -> dict[str, Mod]:
        """Every mod folder in the library by id. Raises `ModError` on a broken
        ``mod.toml`` or two folders with one id."""
        out: dict[str, Mod] = {}
        if not self.folder.is_dir():
            return out
        problems = []
        for d in sorted(self.folder.iterdir()):
            if not d.is_dir() or not (d / MANIFEST).is_file():
                continue
            try:
                mod = Mod.load(d)
            except ModError as e:
                problems.append(str(e))
                continue
            if mod.id in out:
                problems.append(f"{d} and {out[mod.id].root} both have id {mod.id!r}")
                continue
            out[mod.id] = mod
        if problems:
            raise ModError("the mod library has problems:\n  " + "\n  ".join(problems))
        return out

    def entries(self) -> list[LibraryEntry]:
        """The mods in load order (lowest priority first). Listed mods whose folder is
        gone are dropped; folders not listed yet come last, disabled, marked ``new``."""
        mods = self._folders()
        out: list[LibraryEntry] = []
        seen = set()
        for m in self._listed():
            mid = str(m["id"])
            if mid in mods and mid not in seen:
                out.append(LibraryEntry(mods[mid], bool(m.get("enabled", True)), 0))
                seen.add(mid)
        rest = sorted((m for i, m in mods.items() if i not in seen),
                      key=lambda m: (m.priority, m.id))
        out += [LibraryEntry(m, False, 0, new=True) for m in rest]
        for i, e in enumerate(out):
            e.position = i
        return out

    def get(self, mod_id: str) -> LibraryEntry:
        for e in self.entries():
            if e.mod.id == mod_id.lower():
                return e
        raise ModError(f"no mod {mod_id!r} in the library {self.folder} (dr2 mod list)")

    def active(self, game: str | None = None) -> list[Mod]:
        """The enabled mods (for ``game``, if given) with their priority set from the
        load order, ready for `dr2kit.mods.build.build`."""
        return [dataclasses.replace(e.mod, priority=e.position) for e in self.entries()
                if e.enabled and (game is None or game in e.mod.games)]

    def plan(self, game: str, tree):
        """`dr2kit.mods.build.plan_mods` over the enabled mods: what applies, what lost."""
        from .build import plan_mods
        return plan_mods(self.active(game), game, tree)

    # ---- changing -------------------------------------------------------------------

    def save(self, entries: list[LibraryEntry]) -> None:
        """Write ``modlist.toml`` for ``entries`` in this order."""
        self.folder.mkdir(parents=True, exist_ok=True)
        lines = ["# DR2 mod library: the load order. Later mods win over earlier ones.",
                 "# Written by `dr2 mod` and DR2 Studio's mod manager."]
        for e in entries:
            lines += ["", "[[mod]]", f'id = "{e.mod.id}"',
                      f"enabled = {'true' if e.enabled else 'false'}"]
        (self.folder / LIST_FILE).write_text("\n".join(lines) + "\n", "utf-8")

    def enable(self, mod_id: str, on: bool = True) -> None:
        entries = self.entries()
        e = next((e for e in entries if e.mod.id == mod_id.lower()), None)
        if e is None:
            raise ModError(f"no mod {mod_id!r} in the library {self.folder}")
        e.enabled = on
        self.save(entries)

    def move(self, mod_id: str, where: str | int) -> int:
        """Move a mod: ``"up"`` (higher priority), ``"down"``, ``"top"`` (highest),
        ``"bottom"`` or a 1-based position. Returns its new 1-based position."""
        entries = self.entries()
        i = next((k for k, e in enumerate(entries) if e.mod.id == mod_id.lower()), None)
        if i is None:
            raise ModError(f"no mod {mod_id!r} in the library {self.folder}")
        e = entries.pop(i)
        last = len(entries)
        target = {"up": i + 1, "down": i - 1, "top": last, "bottom": 0}.get(str(where))
        if target is None:
            try:
                target = int(where) - 1
            except ValueError:
                raise ModError(f"move where? up, down, top, bottom or a position, "
                               f"not {where!r}") from None
        target = max(0, min(last, target))
        entries.insert(target, e)
        self.save(entries)
        return target + 1

    def install(self, source: str | Path, replace: bool = False) -> Mod:
        """Copy a mod folder or a ``.zip`` into the library, enabled, at the place its
        ``priority`` gives it. ``replace`` updates an installed mod with the same id
        (keeping its place and switch)."""
        src = Path(source)
        with tempfile.TemporaryDirectory(prefix="dr2mod-install-") as tmp:
            if src.is_file() and zipfile.is_zipfile(src):
                folder = _unzip_mod(src, Path(tmp))
            elif src.is_dir():
                folder = src
            else:
                raise ModError(f"{src}: not a mod folder or a .zip")
            mod = Mod.load(folder)
            dest = self.folder / mod.id
            entries = self.entries()
            old = next((e for e in entries if e.mod.id == mod.id), None)
            if old is not None and not replace:
                raise ModError(f"{mod.id} is already installed ({old.mod.root}); "
                               f"use --replace to update it")
            if dest.resolve() == folder.resolve():
                raise ModError(f"{folder} is already the library's copy")
            if old is not None:
                shutil.rmtree(old.mod.root)
            if dest.exists():
                raise ModError(f"{dest} exists and is not mod {mod.id}; move it away first")
            self.folder.mkdir(parents=True, exist_ok=True)
            shutil.copytree(folder, dest)
        installed = Mod.load(dest)
        entries = [e for e in self.entries() if e.mod.id != mod.id or not e.new]
        if old is not None:
            for e in entries:
                if e.mod.id == mod.id:
                    e.enabled = old.enabled
        else:
            entry = LibraryEntry(installed, True, 0)
            at = sum(1 for e in entries if e.mod.priority <= installed.priority)
            entries.insert(at, entry)
        self.save(entries)
        return installed

    def remove(self, mod_id: str) -> Path:
        """Delete an installed mod's folder from the library. Returns the folder."""
        e = self.get(mod_id)
        if e.mod.root.resolve().parent != self.folder.resolve():
            raise ModError(f"{e.mod.root} is not inside the library; not deleting it")
        shutil.rmtree(e.mod.root)
        self.save([x for x in self.entries() if x.mod.id != e.mod.id])
        return e.mod.root


def _unzip_mod(zip_path: Path, into: Path) -> Path:
    """Extract a mod zip safely; return the folder holding its ``mod.toml``."""
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = PurePosixPath(info.filename.replace("\\", "/"))
            if name.is_absolute() or ".." in name.parts or ":" in info.filename:
                raise ModError(f"{zip_path.name}: refusing entry {info.filename!r} "
                               f"(it would be written outside the mod)")
        z.extractall(into)
    if (into / MANIFEST).is_file():
        return into
    tops = [d for d in into.iterdir() if d.is_dir() and (d / MANIFEST).is_file()]
    if len(tops) != 1:
        raise ModError(f"{zip_path.name}: expected one mod (a mod.toml at the top or in "
                       f"one top folder), found {len(tops)}")
    return tops[0]


def pack(folder: str | Path, out: str | Path | None = None) -> Path:
    """Zip a mod folder for sharing: ``<id>-<version>.zip`` holding ``<id>/…``.
    Hidden files and build leftovers (``dr2kit-build.json``) are left out."""
    mod = Mod.load(folder)
    dest = Path(out) if out else Path(f"{mod.id}-{mod.version}.zip")
    if dest.is_dir():
        dest = dest / f"{mod.id}-{mod.version}.zip"
    root = mod.root.resolve()
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(root)
            if p.is_dir() or any(part.startswith(".") for part in rel.parts) \
                    or p.name == "dr2kit-build.json" or p.resolve() == dest.resolve():
                continue
            z.write(p, f"{mod.id}/{rel.as_posix()}")
    return dest

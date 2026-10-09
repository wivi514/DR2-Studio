"""``mod.toml`` and the list of files a mod replaces.

Why a manifest: a mod folder must say which games it is for (an asset path that exists
in Case Zero may not exist in Case West), and the toolkit needs a stable id to name the
build and to report conflicts between mods.

What counts as an override, under ``replace/``:

* ``<vpath>.png`` where ``<vpath>`` is a texture: the PNG replaces that texture
  (same size, v1 rule; `dr2kit.convert.texture`).
* ``<vpath>.glb`` where ``<vpath>`` is a model (``npcs.big/chest_young_chuck.big``): the
  ``.glb`` (exported with ``dr2 extract --glb``, edited in Blender) replaces the model's
  meshes it names (`dr2kit.convert.model_import`).
* ``<vpath>.wav`` (or ``.ogg``, ``.flac``, ``.mp3``) where ``<vpath>`` is a sound
  (``music.big/HB_Indemnify.xma``): the recomp plays that audio instead of the sound
  (PCM substitution, `dr2kit.mods.audio`). The game files are not changed.
* ``<bank>.bcs.json`` where ``<bank>`` is a string bank (``data/frontend/str_en.bcs``):
  only the strings it lists, by id (``"3"``) or label (``"IDS_START_DEMO"``), change
  (`dr2kit.formats.bcs`). Several mods can change one bank; only an id that two of
  them change is a conflict, decided by priority.
* ``<vpath>`` exactly (any other file): its bytes replace the asset as they are, e.g. an
  edited ``datafile.big/zombie_effects.txt``. The toolkit re-compresses it if the
  original entry was compressed.

Paths are matched case-insensitively, like every vpath.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import Dr2Error
from ..profiles import GAME_IDS

MANIFEST = "mod.toml"
REPLACE_DIR = "replace"
AUDIO_EXTS = (".wav", ".ogg", ".flac", ".mp3")   # what can replace a sound
STRINGS_EXT = ".bcs.json"                         # string changes for a string bank
_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")

TEMPLATE = '''# A DR2 Case Zero / Case West mod. Reference: docs/modding/06-mod-packages.md
[mod]
id = "{id}"                 # lower-case letters, digits, _ . - (used to name builds)
name = "{name}"
version = "1.0.0"
games = ["cz", "cw"]        # which games this mod is for
author = ""
description = ""
# Higher priority wins when two mods replace the same asset (default 0).
priority = 0
'''


class ModError(Dr2Error):
    """A mod folder is malformed (bad manifest, unknown asset, wrong size, ...)."""


@dataclass
class Override:
    """One file of a mod: ``vpath`` is the asset it replaces, ``kind`` how."""
    vpath: str            # as written under replace/ (minus .png / .glb)
    source: Path
    kind: str             # "texture-png", "model-glb", "audio", "strings" or "raw"


@dataclass
class Mod:
    """A parsed mod folder."""
    root: Path
    id: str
    name: str
    version: str = "0"
    games: tuple[str, ...] = GAME_IDS
    author: str = ""
    description: str = ""
    priority: int = 0
    preview: str = ""       # a picture in the mod folder, shown by the mod manager
    extra: dict = field(default_factory=dict)

    @property
    def preview_path(self) -> Path | None:
        """The mod's preview picture (``preview`` in mod.toml, else ``preview.png``)."""
        for name in (self.preview, "preview.png", "preview.jpg"):
            if name and (self.root / name).is_file():
                return self.root / name
        return None

    @property
    def readme(self) -> str:
        """The mod's ``README.md`` (or ``README.txt``), '' if none."""
        for name in ("README.md", "README.txt", "readme.md", "readme.txt"):
            if (self.root / name).is_file():
                return (self.root / name).read_text("utf-8", "replace")
        return ""

    @classmethod
    def load(cls, folder: str | Path) -> "Mod":
        """Read ``folder/mod.toml``. Raises `ModError` saying what is wrong."""
        root = Path(folder)
        path = root / MANIFEST
        if not path.is_file():
            raise ModError(f"{root}: no {MANIFEST} (create one with: dr2 mod new {root})")
        try:
            raw = tomllib.loads(path.read_text("utf-8"))
        except tomllib.TOMLDecodeError as e:
            raise ModError(f"{path}: {e}") from None
        m = raw.get("mod")
        if not isinstance(m, dict):
            raise ModError(f"{path}: needs a [mod] table")
        mid = str(m.get("id", ""))
        if not _ID.match(mid):
            raise ModError(f"{path}: id {mid!r} must be lower-case letters, digits, _ . -")
        games = tuple(str(g).lower() for g in m.get("games", GAME_IDS))
        bad = [g for g in games if g not in GAME_IDS]
        if bad or not games:
            raise ModError(f"{path}: games must be a list from {list(GAME_IDS)}, got {games}")
        known = {"id", "name", "version", "games", "author", "description", "priority",
                 "preview"}
        return cls(root=root, id=mid, name=str(m.get("name", mid)),
                   version=str(m.get("version", "0")), games=games,
                   author=str(m.get("author", "")), description=str(m.get("description", "")),
                   priority=int(m.get("priority", 0)), preview=str(m.get("preview", "")),
                   extra={k: v for k, v in m.items() if k not in known})

    def save(self) -> Path:
        """Write this mod's ``mod.toml`` (the fields above, other keys kept), with the
        template's comments. Returns the file."""
        def q(v: str) -> str:
            return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
        lines = ["# A DR2 Case Zero / Case West mod. Reference: docs/modding/06-mod-packages.md",
                 "[mod]",
                 f"id = {q(self.id)}                 # lower-case letters, digits, _ . -",
                 f"name = {q(self.name)}",
                 f"version = {q(self.version)}",
                 "games = [" + ", ".join(q(g) for g in self.games) + "]   # which games it is for",
                 f"author = {q(self.author)}",
                 f"description = {q(self.description)}",
                 "# Higher priority wins when two mods replace the same asset (default 0).",
                 f"priority = {int(self.priority)}"]
        if self.preview:
            lines.append(f"preview = {q(self.preview)}   # the picture the mod manager shows")
        for k, v in self.extra.items():
            if isinstance(v, (int, float, bool)):
                lines.append(f"{k} = {str(v).lower() if isinstance(v, bool) else v}")
            elif isinstance(v, str):
                lines.append(f"{k} = {q(v)}")
        path = self.root / MANIFEST
        path.write_text("\n".join(lines) + "\n", "utf-8")
        Mod.load(self.root)                      # what we wrote must read back
        return path

    def files(self) -> list[tuple[str, Path]]:
        """Every file under ``replace/`` as ``(path relative to replace/, file)``, sorted."""
        base = self.root / REPLACE_DIR
        if not base.is_dir():
            return []
        out = [(p.relative_to(base).as_posix(), p) for p in base.rglob("*") if p.is_file()]
        return sorted(out, key=lambda t: t[0].lower())


def create(folder: str | Path, mod_id: str | None = None, name: str | None = None) -> Path:
    """Make a new, empty mod folder with a commented ``mod.toml``. Returns the folder."""
    root = Path(folder)
    mid = (mod_id or root.name).lower().replace(" ", "_")
    if not _ID.match(mid):
        raise ModError(f"{mid!r} is not a valid mod id (lower-case letters, digits, _ . -)")
    if (root / MANIFEST).exists():
        raise ModError(f"{root / MANIFEST} already exists")
    (root / REPLACE_DIR).mkdir(parents=True, exist_ok=True)
    (root / MANIFEST).write_text(TEMPLATE.format(id=mid, name=name or root.name), "utf-8")
    return root

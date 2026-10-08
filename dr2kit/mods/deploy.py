"""Deploy a mod build: copy its files where the game will read them.

Two targets (docs/ARCHITECTURE.md §Mod package format):

* **A recomp's ``assets/game_mods/``** (the default when a recomp holds the game data).
  The recomp checks that folder first for every file it opens, logs each file it serves
  from it, and ignores it when ``CZ_NO_MODS=1`` / ``CW_NO_MODS=1`` is set
  (docs/dev/recomp-integration.md). The recomp derives the folder from its game folder:
  ``<game root>_mods``, next to ``_patched``, ``_kbm`` and ``_bootskip``.
* **Any folder** (``--to``): the patched files laid out like the game, for Xenia, a real
  console, or by hand.

Deploying is undoable. A deploy writes ``dr2kit-deployed.json`` in the target listing
the files it wrote; the next deploy (or `undeploy`) removes exactly those files first and
nothing else, so files a person put there by hand are never touched.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..container.vpath import split
from .build import BUILD_INFO, BuildResult

DEPLOYED = "dr2kit-deployed.json"


def recomp_folders(game_root: Path) -> dict[str, Path]:
    """The recomp overlay folders next to a game root (``assets/game`` → ``game_mods``…)."""
    base = str(game_root).rstrip("/\\")
    return {name: Path(base + "_" + name) for name in ("mods", "patched", "kbm", "bootskip")}


def is_recomp_root(game_root: Path) -> bool:
    """True if ``game_root`` looks like a recomp's ``assets/game`` folder."""
    return game_root.name.lower() == "game" and game_root.parent.name.lower() == "assets"


def undeploy(target: Path) -> list[str]:
    """Remove the files the last deploy wrote into ``target``. Returns their vpaths."""
    record = target / DEPLOYED
    if not record.is_file():
        return []
    removed = []
    for vp in json.loads(record.read_text("utf-8")).get("files", []):
        f = target.joinpath(*split(vp))
        if f.is_file():
            f.unlink()
            removed.append(vp)
            # Tidy up folders this deploy created and left empty.
            d = f.parent
            while d != target and d.is_dir() and not any(d.iterdir()):
                d.rmdir()
                d = d.parent
    record.unlink()
    return removed


def deploy(build: BuildResult, target: str | Path) -> list[str]:
    """Copy a build's files into ``target`` (replacing the previous deploy's files)."""
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    undeploy(target)
    for vp in build.files:
        dest = target.joinpath(*split(vp))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(build.out_dir.joinpath(*split(vp)), dest)
    info = json.loads((build.out_dir / BUILD_INFO).read_text("utf-8"))
    info["files_written"] = list(build.files)
    (target / DEPLOYED).write_text(json.dumps({"files": build.files, "build": info},
                                              indent=1), "utf-8")
    return list(build.files)


def shadowed_layers(game_root: Path, files: list[str]) -> list[str]:
    """Warnings for files that a recomp toggle layer (``_kbm``, ``_bootskip``) also carries.

    ``game_mods`` is checked before those layers, so while the mod is deployed the
    toggle's version of that file is not used.
    """
    out = []
    dirs = recomp_folders(game_root)
    for vp in files:
        for layer in ("kbm", "bootskip"):
            if dirs[layer].joinpath(*split(vp)).is_file():
                out.append(f"{vp}: the recomp's game_{layer} layer also has this file; while "
                           f"the mod is deployed, the mod's copy is used instead")
    return out

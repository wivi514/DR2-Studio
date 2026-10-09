"""Play: deploy the switched-on mods and start the recomp; say what is deployed now.

Why: the last steps of every mod ("build, copy into ``game_mods/``, start the game")
were separate commands and windows. DR2 Studio's **Play** button and ``dr2 play`` do
them in one go (user decision, 2026-10-09: Studio may start the recomp):

1. `deploy_library(game)`: build every switched-on mod of the library for ``game``
   (`dr2kit.mods.library`), on top of the recomp's ``game_patched`` copies, and deploy
   it into ``game_mods/`` (replacing the previous deploy). With no mod switched on,
   the previous deploy is removed, so the game runs as shipped.
2. `launch(game)`: start the recomp's program (`find_recomp`), from its own folder,
   without waiting for it. *Play without mods* sets the profile's ``no_mods_env``
   (``CZ_NO_MODS=1``) for that run instead of touching ``game_mods/``.

`deployed(game)` reads ``game_mods/dr2kit-deployed.json`` (written by
`dr2kit.mods.deploy`): which mods, which files, when; `undeploy_all` removes them.

Where the recomp's program is: the user's choice (``dr2 games set-recomp``, saved as
``[recomps]`` in the config), else the first of the profile's ``recomp_executables``
in the recomp's folder (the folder holding ``assets/game``): a release has it next to
``assets/``; among source builds (``runtime/build``, ``runtime/build-release``) the
newest wins, because an old build may predate the ``game_mods/`` layer (on 2026-10-09
the CZ recomp's ``build-release`` was a month older than ``build``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..container.vpath import AssetTree
from ..errors import Dr2Error
from ..profiles import get_config, load_profile, locate, set_config
from . import build as mbuild
from . import deploy as mdeploy
from .library import ModLibrary


def recomp_folder(game: str) -> Path:
    """The recomp's folder (holding ``assets/game``); raises if the data isn't a recomp's."""
    root = locate(game).root
    if not mdeploy.is_recomp_root(root):
        raise Dr2Error(f"{load_profile(game).name}'s data ({root}) is not inside a recomp "
                       f"(…/assets/game), so there is no recomp to start or to deploy into")
    return root.parent.parent


def find_recomp(game: str) -> Path:
    """The recomp's program. Raises `Dr2Error` saying how to set it if none is found."""
    chosen = get_config("recomps", game)
    if chosen:
        p = Path(chosen).expanduser()
        if p.is_file():
            return p
        raise Dr2Error(f"the recomp program set for {game} ({p}) is gone; set it again "
                       f"(Studio: Game folders…, or dr2 games set-recomp {game} <file>)")
    folder = recomp_folder(game)
    found = [folder / rel for rel in load_profile(game).recomp_executables
             if (folder / rel).is_file() and (sys.platform == "win32" or
                                              os.access(folder / rel, os.X_OK))]
    release = [p for p in found if p.parent == folder]
    if release:                       # a release: the program sits next to assets/
        return release[0]
    if found:                         # source builds: the newest (an old build may
        return max(found, key=lambda p: p.stat().st_mtime)   # predate game_mods/)
    raise Dr2Error(f"no recomp program found in {folder}; choose it with Studio's Game "
                   f"folders… or `dr2 games set-recomp {game} <file>`")


def set_recomp(game: str, program: str | Path | None) -> None:
    """Remember the recomp program for ``game`` (``None`` forgets it)."""
    if program is not None and not Path(program).is_file():
        raise Dr2Error(f"{program}: no such file")
    set_config("recomps", game, None if program is None else str(Path(program).resolve()))


@dataclass
class Deployed:
    """What ``game_mods/`` holds now (from ``dr2kit-deployed.json``)."""
    folder: Path
    mods: list[str] = field(default_factory=list)      # "id version"
    files: list[str] = field(default_factory=list)
    when: float = 0.0                                   # file time, seconds since epoch

    def describe(self) -> str:
        if not self.files:
            return "no mods in the game"
        stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.when))
        return (f"{len(self.mods)} mod(s) in the game ({', '.join(self.mods)}), "
                f"{len(self.files)} file(s), deployed {stamp}")


def deployed(game: str) -> Deployed:
    target = mdeploy.recomp_folders(locate(game).root)["mods"]
    rec = target / mdeploy.DEPLOYED
    if not rec.is_file():
        return Deployed(target)
    data = json.loads(rec.read_text("utf-8"))
    mods = [f"{m['id']} {m.get('version', '')}".strip()
            for m in data.get("build", {}).get("mods", [])]
    return Deployed(target, mods, list(data.get("files", [])), rec.stat().st_mtime)


def undeploy_all(game: str) -> list[str]:
    """Remove every deployed file from the game; remove ``game_mods/`` if left empty."""
    target = mdeploy.recomp_folders(locate(game).root)["mods"]
    removed = mdeploy.undeploy(target)
    if target.is_dir() and not any(target.iterdir()):
        target.rmdir()
    return removed


def deploy_library(game: str, library: ModLibrary | None = None, progress=None) -> tuple[
        list[str], mbuild.BuildResult | None]:
    """Build the library's switched-on mods for ``game`` and deploy them. Returns the
    files written and the build (None when no mod is on: the old deploy is removed)."""
    lib = library or ModLibrary()
    loc = locate(game)
    if not mdeploy.is_recomp_root(loc.root):
        raise Dr2Error(f"{game}'s data is not in a recomp; use `dr2 mod build` and copy "
                       f"the files yourself")
    mods = lib.active(game)
    if not mods:
        undeploy_all(game)
        return [], None
    dirs = mdeploy.recomp_folders(loc.root)
    base = [dirs["patched"]] if dirs["patched"].is_dir() else []
    with tempfile.TemporaryDirectory(prefix="dr2play-") as tmp:
        res = mbuild.build(mods, game, AssetTree(loc.root), tmp, base,
                           progress=progress)
        written = mdeploy.deploy(res, dirs["mods"])
    return written, res


def launch(game: str, mods: bool = True, extra_env: dict | None = None) -> subprocess.Popen:
    """Start the recomp (not waiting for it). ``mods=False`` runs it with mods off."""
    exe = find_recomp(game)
    env = dict(os.environ)
    if not mods:
        env[load_profile(game).no_mods_env] = "1"
    env.update(extra_env or {})
    flags = {}
    if sys.platform == "win32":
        flags["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        flags["start_new_session"] = True
    return subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)

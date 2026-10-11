"""Game profiles (`cz`, `cw`) and finding each game's data on disk.

A profile is a small TOML file (``cz.toml``, ``cw.toml``) holding what differs between
the games: the name, the title ID, where a recomp keeps the unpacked data, and measured
totals. Code never branches on "is this CZ?"; it reads the profile (CLAUDE.md,
Conventions).

Where the game data comes from, in order:

1. A folder the user configured: ``dr2 games set cz <folder>``, saved in the user config
   file (`config_path`). Also ``DR2_CZ_DATA`` / ``DR2_CW_DATA`` environment variables.
2. A recomp next to this toolkit's checkout (``recomp_dirs`` in the profile).
3. Nothing: `GameNotFoundError`, with a message that says how to fix it.

The configured folder may be the folder that *contains* ``data/`` (a recomp's
``assets/game``, or the output of ``dr2 unpack``) or the ``data/`` folder itself; both
work. Users without a recomp (for example on macOS) unpack the XBLA package with
``dr2 unpack`` (dr2kit/container/stfs.py) and point the profile at the result.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from ..errors import GameNotFoundError

GAME_IDS = ("cz", "cw")
_CHECKOUT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Profile:
    """One game's settings, as loaded from its TOML file."""
    id: str
    name: str
    title_id: str
    recomp_dirs: tuple[str, ...] = ()
    package_globs: tuple[str, ...] = ()
    digest_checked: tuple[str, ...] = ()     # vpaths the executable checks (no mods)
    recomp_executables: tuple[str, ...] = ()  # the recomp program, relative to its folder
    no_mods_env: str = ""                     # env var that turns mods off for a run
    play_defaults: dict = field(default_factory=dict)  # env for Play when no <id>_defaults.env
    census: dict = field(default_factory=dict)
    variants: dict = field(default_factory=dict)  # the shape-group table (convert/variants.py)
    map_floors: tuple = ()      # the in-game map's floor pictures, placed (convert/mapdata.py)


def load_profile(game: str) -> Profile:
    """Load the built-in profile for ``game`` (``"cz"`` or ``"cw"``, any case)."""
    game = game.lower()
    if game not in GAME_IDS:
        raise GameNotFoundError(f"unknown game {game!r}; expected one of {', '.join(GAME_IDS)}")
    text = resources.files(__package__).joinpath(f"{game}.toml").read_text("utf-8")
    raw = tomllib.loads(text)
    return Profile(id=raw["id"], name=raw["name"], title_id=raw["title_id"],
                   recomp_dirs=tuple(raw.get("recomp_dirs", ())),
                   package_globs=tuple(raw.get("package_globs", ())),
                   digest_checked=tuple(raw.get("digest_checked", ())),
                   recomp_executables=tuple(raw.get("recomp_executables", ())),
                   no_mods_env=str(raw.get("no_mods_env", "")),
                   play_defaults={str(k): str(v) for k, v in raw.get("play_defaults", {}).items()},
                   census=dict(raw.get("census", {})),
                   variants=dict(raw.get("variants", {})),
                   map_floors=tuple(raw.get("map_floors", ())))


def config_path() -> Path:
    """The user config file (per-OS location, `dr2kit.userdirs`)."""
    from ..userdirs import config_dir
    return config_dir() / "config.toml"


def _read_config() -> dict:
    p = config_path()
    if not p.is_file():
        return {}
    return tomllib.loads(p.read_text("utf-8"))


def set_game_root(game: str, folder: str | Path) -> Path:
    """Remember ``folder`` as ``game``'s data location. Returns the normalised root."""
    root = normalise_root(Path(folder))
    if root is None:
        raise GameNotFoundError(f"{folder}: no 'data' folder with .big files there")
    set_config("games", game.lower(), str(root))
    return root


def get_config(section: str, key: str, default: str | None = None) -> str | None:
    """One value of the user config file (``[section] key = "value"``)."""
    return _read_config().get(section, {}).get(key, default)


def set_config(section: str, key: str, value: str | None) -> None:
    """Set (or, with ``None``, remove) one value of the user config file."""
    cfg = _read_config()
    if value is None:
        cfg.get(section, {}).pop(key, None)
    else:
        cfg.setdefault(section, {})[key] = str(value)
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # Tiny writer: the config only ever holds tables of string values.
    lines = ["# dr2kit user settings (written by `dr2 games set`, `dr2 mod library`)"]
    for name, table in sorted(cfg.items()):
        if not isinstance(table, dict) or not table:
            continue
        lines += ["", f"[{name}]"]
        lines += [f"{k} = {_toml_string(str(v))}" for k, v in sorted(table.items())]
    p.write_text("\n".join(lines) + "\n", "utf-8")


def _toml_string(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def normalise_root(folder: Path) -> Path | None:
    """The folder that contains ``data/``, given it or ``data/`` itself; None if neither.

    "Contains game data" means a ``data`` folder with at least one ``.big`` file
    directly in it (``datafile.big`` is there in both games).
    """
    folder = folder.expanduser()

    def has_bigs(d: Path | None) -> bool:
        return d is not None and any(p.suffix.lower() == ".big" for p in d.iterdir())

    if folder.name.lower() == "data" and folder.is_dir() and has_bigs(folder):
        return folder.parent.resolve()
    if has_bigs(_child_ci(folder, "data")):
        return folder.resolve()
    return None


def _child_ci(folder: Path, name: str) -> Path | None:
    """``folder/name`` matched case-insensitively (Linux filesystems care; data doesn't)."""
    if not folder.is_dir():
        return None
    exact = folder / name
    if exact.is_dir():
        return exact
    for p in folder.iterdir():
        if p.name.lower() == name.lower() and p.is_dir():
            return p
    return None


@dataclass(frozen=True)
class GameLocation:
    """Where a game's data was found, and how (for ``dr2 games``)."""
    profile: Profile
    root: Path            # the folder containing data/
    how: str              # "config", "environment" or "recomp"

    @property
    def data_dir(self) -> Path:
        return _child_ci(self.root, "data") or self.root / "data"


def locate(game: str) -> GameLocation:
    """Find ``game``'s data, or raise `GameNotFoundError` explaining what to do."""
    prof = load_profile(game)
    env = os.environ.get(f"DR2_{prof.id.upper()}_DATA")
    if env:
        root = normalise_root(Path(env))
        if root is None:
            raise GameNotFoundError(f"DR2_{prof.id.upper()}_DATA={env}: no game data there")
        return GameLocation(prof, root, "environment")
    configured = _read_config().get("games", {}).get(prof.id)
    if configured:
        root = normalise_root(Path(configured))
        if root is None:
            raise GameNotFoundError(f"{prof.name}: the configured folder {configured} has "
                                    f"no game data any more (fix: dr2 games set "
                                    f"{prof.id} <folder>)")
        return GameLocation(prof, root, "config")
    for rel in prof.recomp_dirs:
        root = normalise_root(_CHECKOUT / rel)
        if root is not None:
            return GameLocation(prof, root, "recomp")
    raise GameNotFoundError(
        f"{prof.name}: game data not found. Point the toolkit at it with "
        f"`dr2 games set {prof.id} <folder containing data/>`, or unpack the XBLA package "
        f"with `dr2 unpack <package> <folder>` first (docs/modding/02-game-data.md).")


def find_packages(game: str) -> list[Path]:
    """XBLA package files found next to a recomp checkout (may be empty)."""
    prof = load_profile(game)
    out = []
    for g in prof.package_globs:
        base = _CHECKOUT
        out += [p.resolve() for p in sorted(base.glob(g)) if p.is_file()]
    return out

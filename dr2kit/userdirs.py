"""Per-user folders (config, cache, data), the same everywhere the toolkit runs.

Why a module: the toolkit uses `platformdirs` for these (``%APPDATA%`` on Windows,
``~/Library/Application Support`` on macOS, the XDG folders on Linux), but the same core
also runs inside Blender's bundled Python (the ``io_dr2`` add-on), where platformdirs
isn't installed. Without it, these functions compute the same default folders
themselves, so the add-on, the CLI and DR2 Studio share one config file, one index and
one mod library.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP = "dr2kit"


def _fallback(kind: str) -> Path:
    home = Path.home()
    if sys.platform == "win32":          # platformdirs' default: local, not roaming
        base = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local") / APP
        return base / "Cache" if kind == "cache" else base
    if sys.platform == "darwin":
        lib = home / "Library"
        return (lib / "Caches" / APP) if kind == "cache" else \
            (lib / "Application Support" / APP)
    env, default = {"config": ("XDG_CONFIG_HOME", ".config"),
                    "cache": ("XDG_CACHE_HOME", ".cache"),
                    "data": ("XDG_DATA_HOME", ".local/share")}[kind]
    return Path(os.environ.get(env) or home / default) / APP


def _dir(kind: str) -> Path:
    try:
        import platformdirs
    except ImportError:
        return _fallback(kind)
    fn = {"config": platformdirs.user_config_dir, "cache": platformdirs.user_cache_dir,
          "data": platformdirs.user_data_dir}[kind]
    return Path(fn(APP, appauthor=False))


def config_dir() -> Path:
    """Where ``config.toml`` lives."""
    return _dir("config")


def cache_dir() -> Path:
    """Where the asset index lives."""
    return _dir("cache")


def data_dir() -> Path:
    """Where the mod library lives by default."""
    return _dir("data")

# SPDX-License-Identifier: GPL-3.0-or-later
"""Finding the DR2 toolkit (dr2kit) from inside Blender.

The add-on does not include dr2kit: the toolkit has its own (non-commercial) license,
and Blender add-ons are GPL. So the add-on imports dr2kit at run time from where it
already is on the user's machine:

1. ``import dr2kit`` as is (installed into Blender's Python with pip, or Blender runs on
   a system Python that has it);
2. the folder set in the add-on's preferences: the toolkit's folder, i.e. the folder
   that *contains* the ``dr2kit`` package (a git checkout, or the ``python`` folder of a
   DR2 Studio release).

dr2kit is pure Python (numpy, which Blender bundles, makes it faster), so it runs in
Blender's Python as it is. This module never imports bpy, so it can be tested without
Blender.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

CANDIDATES = (".", "python", "src")   # where dr2kit/ may sit under the chosen folder


class ToolkitMissing(Exception):
    """dr2kit can't be imported; the message says how to fix it."""


def find_package_root(folder: str | Path) -> Path | None:
    """The folder under ``folder`` that holds ``dr2kit/__init__.py`` (or None)."""
    base = Path(folder).expanduser()
    for sub in CANDIDATES:
        root = (base / sub).resolve()
        if (root / "dr2kit" / "__init__.py").is_file():
            return root
    if base.name == "dr2kit" and (base / "__init__.py").is_file():
        return base.parent.resolve()
    return None


def load(folder: str = ""):
    """Import and return the ``dr2kit`` module, using ``folder`` if needed."""
    if folder:
        root = find_package_root(folder)
        if root is None:
            raise ToolkitMissing(f"No dr2kit package in {folder}. Choose the toolkit's "
                                 f"folder (the one that contains 'dr2kit').")
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        loaded = sys.modules.get("dr2kit")
        if loaded is not None and not str(Path(loaded.__file__).resolve()).startswith(str(root)):
            raise ToolkitMissing(f"Another dr2kit is already loaded ({loaded.__file__}); "
                                 f"restart Blender to use the one in {root}.")
    try:
        return importlib.import_module("dr2kit")
    except ImportError as e:
        raise ToolkitMissing(
            "The DR2 toolkit (dr2kit) was not found. In Edit > Preferences > Add-ons > "
            "DR2 Modding Toolkit, set 'Toolkit folder' to the folder that contains "
            f"'dr2kit' ({e}).") from None
    except Exception as e:  # noqa: BLE001 - a broken install: say what failed
        raise ToolkitMissing(f"dr2kit failed to load: {e}") from None


def describe(dr2kit) -> str:
    """One line for the panel: version, where from, LZX decoder."""
    from dr2kit.container import lzx
    where = Path(dr2kit.__file__).parent.parent
    backend = lzx.backend_detail().split(" ")[0]
    return f"dr2kit {dr2kit.__version__} ({where}), LZX: {backend}"

"""A new item of your own, made from one the game has (phase 11 step 5, "own models").

An item is two things (docs/formats.md §Levels, "Items → models"): a block of
``items.txt`` (its class gives what it does: ``cPlayerWeaponItem`` swings,
``cUtilityItem`` with ``Unmoveable`` stands like a wall…) and a **pack**
``data/streamedassets.big/<ItemName>.big`` holding the scene (``<Name>.big``), its textures
(``<Name>.tex`` and ``<Name>_LOD.tex``) and the inventory icon. The game finds the pack by
the item's name, so a new item needs a new pack (checked in game, CZ 2026-10-11: a new
pack in ``streamedassets.big`` is found, once it declares its siblings' alignment).

**The mod holds a recipe, not game data** (a shared mod may only contain the modder's
own work, LICENSE): ``add/data/streamedassets.big/<Name>.big.copy.json`` says which pack
of the game to copy, and what of the modder's to put in it::

    {"format": "dr2kit-copy/1", "copy": "data/streamedassets.big/SledgeHammer.big",
     "rename": {"Sledgehammer": "MyHammer"},          <- the scene and texture packs
     "glb": "MyHammer.glb",                            <- its shape (in sources/), optional
     "textures": {"Sledgehammer_cm": "MyHammer_cm.png"}}   <- in sources/, optional

`build_copy` makes the pack from the player's own game when the mod is built (`mods.build`,
kind ``add``); `new_item` writes the recipe, the ``items.txt`` block (every key of the
template's, under the new name: an ``.edits.json`` add) and copies the ``.glb`` / PNGs into
the mod's ``sources/`` folder. Place the item from the Maps tab (*Add item…*).
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from ..container.big import BigArchive
from ..container.vpath import AssetTree, join, split
from ..convert import placed
from ..errors import Dr2Error
from .manifest import ADD_DIR

NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,40}$")
COPY_FORMAT = "dr2kit-copy/1"
COPY_EXT = ".copy.json"
SOURCES_DIR = "sources"


def build_copy(tree: AssetTree, recipe: dict, mod_root: Path, where: str = "") -> bytes:
    """The bytes of a new entry made by a ``.copy.json`` recipe (module docstring)."""
    pre = f"{where}: " if where else ""
    if recipe.get("format") != COPY_FORMAT or not recipe.get("copy"):
        raise Dr2Error(f"{pre}not a {COPY_FORMAT} recipe (needs \"copy\")")
    try:
        src = tree.resolve(recipe["copy"])
    except Dr2Error:
        raise Dr2Error(f"{pre}the game has no {recipe['copy']!r} to copy") from None
    pack = BigArchive.parse(src.data(), src.vpath)
    for old, new in (recipe.get("rename") or {}).items():
        for e in pack.entries:
            low = e.name.lower()
            for suffix in (".big", ".tex", "_lod.tex"):
                if low == old.lower() + suffix:
                    e.name = new + e.name[len(old):]
                    e.hash = None
    sources = Path(mod_root) / SOURCES_DIR
    scene_name = next((n for n in (recipe.get("rename") or {}).values()), None)
    if recipe.get("glb"):
        from ..convert.model_import import import_glb
        from ..formats.scene import Scene
        glb = sources / recipe["glb"]
        if not glb.is_file():
            raise Dr2Error(f"{pre}{glb} is missing")
        e = next((x for x in pack.entries if scene_name and
                  x.name.lower() == f"{scene_name.lower()}.big"), None)
        if e is None:
            raise Dr2Error(f"{pre}no scene {scene_name}.big in the copied pack")
        data, _ = import_glb(Scene.parse(e.data(), e.name), glb.read_bytes(), str(glb))
        e.set_data(data)
    if recipe.get("textures"):
        from ..convert import png
        from ..convert.texture import replace_image
        from ..formats.bct import Bct
        for tex, file in recipe["textures"].items():
            f = sources / file
            done = False
            for e in pack.entries:
                if not e.name.lower().endswith(".tex") or e.name.lower().endswith("_lod.tex"):
                    continue
                tp = BigArchive.parse(e.data(), e.name)
                for t in tp.entries:
                    if t.name.lower().removesuffix(".bct") == tex.lower():
                        t.set_data(replace_image(Bct.parse(t.data(), t.name),
                                                 png.read(f)).to_bytes())
                        done = True
                if done:
                    e.set_data(tp.to_bytes())
                    break
            if not done:
                raise Dr2Error(f"{pre}no texture {tex!r} in the copied pack")
    return pack.to_bytes()


def new_item(tree: AssetTree, mod_dir: str | Path, name: str, like: str,
             glb: str | Path | None = None, base_dirs=(),
             textures: dict[str, str | Path] | None = None) -> list[Path]:
    """Make the item ``name`` in the mod at ``mod_dir`` from the game's item ``like``
    (module docstring); ``textures``: texture name → a PNG of the same size. Returns the
    files written."""
    from .leveledit import TextEdits
    if not NAME.match(name):
        raise Dr2Error(f"{name!r}: an item name is a letter then letters, digits or _ "
                       f"(up to 41)")
    models = placed.ItemModels(tree)
    if name.lower() in models.blocks:
        raise Dr2Error(f"{name!r} is already an item of this game's items.txt")
    if name.lower() + ".big" in models.packs:
        raise Dr2Error(f"{placed.STREAMED} already has {name}.big")
    src = models.blocks.get(like.lower())
    if src is None:
        raise Dr2Error(f"{like!r} is not an item of this game's items.txt")
    scene_vp = models.resolve(like)
    if scene_vp is None:
        raise Dr2Error(f"{like}'s model doesn't ship in this game "
                       f"({models.why.get(like.lower())}): pick another item to start from")
    parts = split(scene_vp)
    if len(parts) != len(split(placed.STREAMED)) + 2:     # …/streamedassets.big/Pack/scene
        raise Dr2Error(f"{like}: its scene is a whole pack ({scene_vp}); not supported yet")
    root = Path(mod_dir)
    recipe: dict = {"format": COPY_FORMAT, "copy": join(*parts[:-1]),
                    "rename": {parts[-1][:-4]: name}}
    written = []
    for key, files in (("glb", {"": glb} if glb else {}), ("textures", textures or {})):
        for tex, f in files.items():
            dest = root / SOURCES_DIR / (f"{name}.glb" if key == "glb" else Path(f).name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if Path(f).resolve() != dest.resolve():
                shutil.copy(f, dest)
            written.append(dest)
            if key == "glb":
                recipe["glb"] = dest.name
            else:
                recipe.setdefault("textures", {})[tex] = dest.name
    build_copy(tree, recipe, root, name)                     # it must build now
    out = root.joinpath(ADD_DIR, *split(placed.STREAMED), f"{name}.big{COPY_EXT}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(recipe, indent=1) + "\n", "utf-8")
    s = TextEdits(mod_dir, "items.txt", tree, base_dirs)
    if s.doc.get(f"{src.cls} {name}") is None:
        s.doc.add(None, src.cls, name, [(p.key, p.value) for p in src.props])
    return [out, s.save(), *written]

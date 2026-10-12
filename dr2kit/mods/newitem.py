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

Phase 13 (the weapon wizard, `mods.newweapon`) adds to a pack's recipe:

* ``"icon": "MyHammer_icon.png"`` (128×64, in sources/) and ``"icon_name": "w_myhammer"``:
  the pack's inventory icon (its one loose ``.bct``: ``w_<name>.bct`` in Case Zero,
  ``<name>.bct`` in Case West, named by the block's ``IconFilename``) gets the picture and
  that name, so the new item doesn't share the template's icon.

and a recipe can copy a **texture** (a ``.bct``) instead of a pack, for a combo card's
picture in ``data/frontend/combocards.tex``::

    {"format": "dr2kit-copy/1", "copy": "data/frontend/combocards.tex/comboc_ied.bct",
     "image": "MyCard.png"}                               <- a whole picture of 364×512, or
     "card": {"portrait": "MyCard_portrait.png",          <- the window's picture
              "items": ["Broadsword", "FireExtinguisher"], <- drawn on the panel
              "faded": false}}                            <- true: the "not found" copy

and a **particle effect** of one's own (phase 13 step 6), copied from a game effect into
a free slot of the effect table (`mods.neweffect`)::

    {"format": "dr2kit-copy/1", "copy": "data/models/effects.big/EFFECT_Common137",
     "effect": {"from": "flamingsword_wpn_c_3_unq", "name": "wip_1",
                "changes": {"hue": 200}}}

A ``"card"`` is assembled when the mod is built (`build_card`): the empty card made from
the player's own cards (`convert.icon.card_template`), the modder's portrait, and line
drawings of the two items rendered from the player's game. So the mod holds no game
picture, only the modder's own.

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
    from ..formats.bct import is_bct
    if is_bct(src.data()[:4]):                     # a texture (named with or without .bct)
        return _build_texture(tree, recipe, src, Path(mod_root) / SOURCES_DIR, pre)
    if recipe.get("effect") is not None:
        return _build_effect(recipe, src, pre)
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
    if recipe.get("material_params"):
        e = next((x for x in pack.entries if scene_name and
                  x.name.lower() == f"{scene_name.lower()}.big"), None)
        if e is None:
            raise Dr2Error(f"{pre}no scene {scene_name}.big in the copied pack")
        e.set_data(set_material_params(e.data(), recipe["material_params"], pre))
    if recipe.get("locators"):
        e = next((x for x in pack.entries if scene_name and
                  x.name.lower() == f"{scene_name.lower()}.big"), None)
        if e is None:
            raise Dr2Error(f"{pre}no scene {scene_name}.big in the copied pack")
        e.set_data(set_locators(e.data(), recipe["locators"], pre))
    if recipe.get("icon") or recipe.get("icon_name"):
        _set_icon(pack, recipe, sources, pre)
    return pack.to_bytes()


def set_material_params(scene_data: bytes, params, pre: str = "") -> bytes:
    """A model archive whose textured materials get these four values (``MatArray``
    record +16, `formats.scene.Material.params`; how shiny: `newweapon.SHINES`)."""
    import struct
    from ..formats.scene import MAT_RECORD
    if len(params) != 4:
        raise Dr2Error(f"{pre}material_params: four numbers")
    arc = BigArchive.parse(scene_data, "scene")
    e = next((x for x in arc.entries if x.name == "MatArray"), None)
    if e is None:
        raise Dr2Error(f"{pre}the model has no materials")
    data = bytearray(e.data())
    for o in range(0, len(data), MAT_RECORD):
        if struct.unpack_from(">I", data, o + 8)[0]:          # has texture slots
            struct.pack_into(">4f", data, o + 16, *map(float, params))
    e.set_data(bytes(data))
    return arc.to_bytes()


LOCATOR_RECORD = 52                  # type, position, rotation x y z w, five words


def set_locators(scene_data: bytes, locators: dict, pre: str = "") -> bytes:
    """A model archive with locators moved: ``{"16": {"position": [x, y, z],
    "rotation": [x, y, z, w]}}`` by locator type. Each ``LocatorArray`` record of that
    type (type, position, rotation, five words; docs/formats.md §Weapons), in the model
    archive **and in its nested ``persistent.big``** (the copy the game keeps loaded:
    changing only the first did nothing in game, CZ 2026-10-12), and the node record at
    the same place (``LOC_particle_pos`` for 16) get the new values, so all stay in step."""
    arc = BigArchive.parse(scene_data, "scene")
    _set_locators(arc, locators, pre)
    inner = next((e for e in arc.entries if e.name.lower() == "persistent.big"), None)
    if inner is not None:
        sub = BigArchive.parse(inner.data(), "persistent.big")
        if any(e.name == "LocatorArray" for e in sub.entries):
            _set_locators(sub, locators, pre)
            inner.set_data(sub.to_bytes())
    return arc.to_bytes()


def _set_locators(arc: BigArchive, locators: dict, pre: str) -> None:
    import struct
    from ..formats.scene import NODE_RECORD, Node
    by = {e.name: e for e in arc.entries}
    if "LocatorArray" not in by or "NumLocatorArray" not in by:
        raise Dr2Error(f"{pre}the model has no locators")
    data = bytearray(by["LocatorArray"].data())
    count = struct.unpack(">I", by["NumLocatorArray"].data()[:4])[0]
    nodes = [(e, Node.parse(e.name, e.data())) for e in arc.entries
             if len(e.data()) == NODE_RECORD and not e.name.startswith("_")]
    for kind, where in locators.items():
        pos, rot = list(map(float, where["position"])), list(map(float, where["rotation"]))
        hit = False
        for i in range(count):
            at = i * LOCATOR_RECORD
            if struct.unpack_from(">I", data, at)[0] != int(kind):
                continue
            old = struct.unpack_from(">3f", data, at + 4)
            struct.pack_into(">3f4f", data, at + 4, *pos, *rot)
            for e, n in nodes:
                if max(abs(a - b) for a, b in zip(n.translation, old)) < 1e-4:
                    n.translation, n.rotation = tuple(pos), tuple(rot)
                    e.set_data(n.to_bytes())
            hit = True
        if not hit:
            raise Dr2Error(f"{pre}the model has no locator of type {kind}")
    by["LocatorArray"].set_data(bytes(data))


def _set_icon(pack: BigArchive, recipe: dict, sources: Path, pre: str) -> None:
    """The pack's inventory icon ``w_<…>.bct``: renamed to ``icon_name`` and given the
    picture ``icon`` (module docstring)."""
    from ..convert import png
    from ..convert.texture import replace_image
    from ..formats.bct import Bct
    icons = [e for e in pack.entries if e.name.lower().endswith(".bct")]
    icons.sort(key=lambda e: not e.name.lower().startswith("w_"))
    if not icons:
        raise Dr2Error(f"{pre}the copied pack has no inventory icon (a .bct in the pack)")
    e = icons[0]                     # CZ: w_<name>.bct; CW: <name>.bct (its IconFilename)
    if recipe.get("icon"):
        f = sources / recipe["icon"]
        if not f.is_file():
            raise Dr2Error(f"{pre}{f} is missing")
        e.set_data(replace_image(Bct.parse(e.data(), e.name), png.read(f)).to_bytes())
    if recipe.get("icon_name"):
        name = recipe["icon_name"]
        if not NAME.match(name):
            raise Dr2Error(f"{pre}icon name {name!r}: letters, digits and _ only")
        e.name = f"{name}.bct"
        e.hash = None                          # (entries keep their place: order is free)


def _build_effect(recipe: dict, src, pre: str) -> bytes:
    """A copied particle effect under a new name, with changes (`convert.effects`)."""
    from ..convert.effects import apply_changes
    from ..formats.effect import Effect, is_effect
    data = src.data()
    if not is_effect(data):
        raise Dr2Error(f"{pre}{src.vpath} is not a particle effect")
    spec = recipe["effect"]
    fx = Effect.parse(data, src.vpath)
    if spec.get("from") and spec["from"].lower() != fx.name.lower():
        raise Dr2Error(f"{pre}made from the effect {spec['from']!r}, but {src.vpath} is "
                       f"{fx.name!r} in this game")
    if spec.get("name"):
        fx.rename(spec["name"])
    return apply_changes(fx, spec.get("changes") or {}, pre.rstrip(": ")).to_bytes()


def _build_texture(tree: AssetTree, recipe: dict, src, sources: Path, pre: str) -> bytes:
    """A copied texture with the recipe's picture (``image``) or card (``card``)."""
    from ..convert import png
    from ..convert.texture import replace_image
    from ..formats.bct import Bct
    bct = Bct.parse(src.data(), src.vpath)
    if recipe.get("image"):
        f = sources / recipe["image"]
        if not f.is_file():
            raise Dr2Error(f"{pre}{f} is missing")
        img = png.read(f)
    elif recipe.get("card"):
        img = build_card(tree, recipe["card"], src.vpath, sources, pre)
    else:
        raise Dr2Error(f"{pre}a texture recipe needs \"image\" or \"card\"")
    try:
        return replace_image(bct, img).to_bytes()
    except Dr2Error as e:
        raise Dr2Error(f"{pre}{e}") from None


def build_card(tree: AssetTree, card: dict, copied: str, sources: Path, pre: str = ""):
    """A combo card's picture (`convert.png.Image`) from a ``"card"`` recipe (module
    docstring): the empty card of the archive holding ``copied``, the portrait, the two
    items' drawings."""
    import numpy as np
    from ..convert import icon, png
    from ..convert.render import scene_parts
    from ..convert.texture import to_image
    from ..formats.bct import Bct
    from ..formats.scene import Scene
    faded = bool(card.get("faded"))
    parent = join(*split(copied)[:-1])
    arc = tree.open_archive(tree.resolve(parent).vpath)
    cards = []
    for e in arc.entries:
        low = e.name.lower()
        if not low.startswith("comboc_") or low.endswith("_no.bct") != faded:
            continue
        im = to_image(Bct.parse(e.data(), e.name))
        cards.append(np.frombuffer(im.rgba, np.uint8).reshape(im.height, im.width, 4))
    empty = icon.card_template(cards)
    portrait = None
    if card.get("portrait"):
        f = sources / card["portrait"]
        if not f.is_file():
            raise Dr2Error(f"{pre}{f} is missing")
        p = png.read(f)
        portrait = np.frombuffer(p.rgba, np.uint8).reshape(p.height, p.width, 4)
        if faded:
            portrait = icon.faded(portrait)
    drawings = None
    if card.get("items"):
        models = placed.ItemModels(tree)
        drawings = []
        for item in card["items"][:2]:
            vp = models.resolve(item)
            if vp is None:
                drawings.append(None)
                continue
            drawings.append(icon.item_drawing(scene_parts(Scene.parse(tree.resolve(vp).data(),
                                                                      vp))))
    out = icon.compose_card(empty, portrait, drawings,
                            line=(110, 30, 40) if faded else (0, 0, 0))
    return png.Image(out.shape[1], out.shape[0], out.tobytes())


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

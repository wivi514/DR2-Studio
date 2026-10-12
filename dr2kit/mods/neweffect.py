"""Effects in a mod: change a game effect, or make one of your own (phase 13 step 6).

Why: the effect numbers of ``items.txt`` are a fixed table in the executable
(`catalog.weapons`), so there are no new numbers. But the game finds each effect by its
**name** in ``data/models/effects.big`` (`formats.effect`), and 36 names of the table
have no effect there (the same in both games: ``unused``, ``wip_1``-``wip_3``,
``garbage_wpn_dbs_2``…): **free slots**. An effect of one's own is a game effect copied
into a free slot under that name, with changes; its number is the slot's
(``wip_1`` = 69). Changing a game effect changes it everywhere the game uses it.

Both are recipes (the mod never holds the game's bytes, LICENSE):

* `change_effect` writes ``replace/data/models/effects.big/<entry>.effect.json``:
  ``{"format": "dr2kit-effect/1", "effect": "<name>", "changes": {…}}``
  (`mods.build.effect_bytes`).
* `new_effect` writes ``add/data/models/effects.big/EFFECT_Common<1000 + number>.copy.json``:
  a copy recipe with ``"effect": {"from": …, "name": <slot>, "changes": {…}}``
  (`mods.newitem.build_copy`). The build lists it in the effects scene
  (`mods.build.register_in_scene`), evicts ``preload4.big``'s copy and re-pins
  ``layout.bin``: without each of these an added effect never showed or crashed the game
  (measured, CZ 2026-10-12).
* `new_particle_texture` adds a particle picture of one's own to ``effects.tex`` (a copy
  recipe of a game picture of the same size, with the modder's PNG), for an effect's
  ``"texture"`` change.

The changes are `convert.effects.apply_changes`'s. Seen in game: see docs/formats.md
§Particle effects (what was checked, and when).
"""

from __future__ import annotations

import json
from pathlib import Path

from ..catalog import weapons
from ..container.vpath import AssetTree, split
from ..convert.effects import apply_changes
from ..errors import Dr2Error
from ..formats.effect import EFFECTS_BIG, read_all
from .build import EFFECT_FORMAT
from .manifest import ADD_DIR, EFFECT_EXT, REPLACE_DIR
from .newitem import COPY_EXT, COPY_FORMAT, NAME, SOURCES_DIR

EFFECTS_TEX = "data/models/effects.tex"

OWN_ENTRY = 1000                 # own effects: EFFECT_Common<1000 + number> (unique per slot)


def free_slots(tree: AssetTree, game: str) -> list[tuple[int, str]]:
    """(number, name) of the table's names with no effect in ``effects.big``."""
    have = {n.lower() for n in read_all(tree)}
    return [(i + 1, n) for i, n in enumerate(weapons.names(game)) if n.lower() not in have]


def _entry_of(tree: AssetTree, name: str) -> tuple[str, object]:
    fx = read_all(tree)
    hit = next(((e, f) for n, (e, f) in fx.items() if n.lower() == name.lower()), None)
    if hit is None:
        raise Dr2Error(f"no effect named {name!r} in this game (dr2 effects)")
    return hit


def change_effect(tree: AssetTree, mod_dir: str | Path, name: str, changes: dict) -> Path:
    """Change the game's effect ``name`` in a mod (module docstring)."""
    entry, fx = _entry_of(tree, name)
    apply_changes(fx, dict(changes), name)                  # it must apply now
    out = Path(mod_dir).joinpath(REPLACE_DIR, *split(EFFECTS_BIG), entry + EFFECT_EXT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"format": EFFECT_FORMAT, "effect": fx.name,
                               "changes": changes}, indent=1) + "\n", "utf-8")
    return out


def new_effect(tree: AssetTree, game: str, mod_dir: str | Path, base: str, changes: dict,
               slot: str | int | None = None) -> tuple[int, Path]:
    """An effect of one's own: ``base`` (a game effect's name) copied into a free slot
    (``slot``: its number or name; None: the first free one the mod doesn't use yet),
    with ``changes``. Returns (its number, the recipe)."""
    entry, fx = _entry_of(tree, base)
    free = free_slots(tree, game)
    taken = {n for n, _ in own_effects(mod_dir)}
    if slot is None:
        pick = next(((n, s) for n, s in free if n not in taken), None)
        if pick is None:
            raise Dr2Error("no free effect slot left")
    else:
        num = weapons.effect_number(game, slot)
        pick = next(((n, s) for n, s in free if n == num), None)
        if pick is None:
            raise Dr2Error(f"effect {num} ({weapons.names(game)[num - 1]}) is a game effect, "
                           f"not a free slot (free: {', '.join(str(n) for n, _ in free[:12])}…)")
    number, name = pick
    fx.rename(name)
    apply_changes(fx, dict(changes), base)                  # it must apply now
    recipe = {"format": COPY_FORMAT, "copy": f"{EFFECTS_BIG}/{entry}",
              "effect": {"from": base, "name": name, "changes": changes}}
    out = Path(mod_dir).joinpath(ADD_DIR, *split(EFFECTS_BIG),
                                 f"EFFECT_Common{OWN_ENTRY + number}{COPY_EXT}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(recipe, indent=1) + "\n", "utf-8")
    return number, out


def own_effects(mod_dir: str | Path) -> list[tuple[int, dict]]:
    """(number, recipe) of a mod's own effects."""
    folder = Path(mod_dir).joinpath(ADD_DIR, *split(EFFECTS_BIG))
    out = []
    for f in sorted(folder.glob(f"EFFECT_Common*{COPY_EXT}")) if folder.is_dir() else []:
        num = int(f.name[len("EFFECT_Common"):-len(COPY_EXT)]) - OWN_ENTRY
        out.append((num, json.loads(f.read_text("utf-8"))))
    return out


def changed_effects(mod_dir: str | Path) -> list[tuple[str, dict]]:
    """(effect name, changes) of the game effects a mod changes."""
    folder = Path(mod_dir).joinpath(REPLACE_DIR, *split(EFFECTS_BIG))
    out = []
    for f in sorted(folder.glob(f"*{EFFECT_EXT}")) if folder.is_dir() else []:
        d = json.loads(f.read_text("utf-8"))
        out.append((d.get("effect", f.name), d.get("changes", {})))
    return out


def new_particle_texture(tree: AssetTree, mod_dir: str | Path, name: str,
                         picture: str | Path) -> Path:
    """A particle picture of one's own, ``name`` in ``effects.tex`` (module docstring).
    The PNG is resized to the nearest size the game's particle pictures have (square,
    16-256) and stored in the mod's ``sources/``."""
    from ..convert import png
    from ..formats.bct import Bct
    from .texture_import import load_image, resize
    if not NAME.match(name):
        raise Dr2Error(f"{name!r}: a picture name is a letter then letters, digits or _")
    arc = tree.open_archive(tree.resolve(EFFECTS_TEX).vpath)
    if any(e.name.lower().removesuffix(".bct") == name.lower() for e in arc.entries):
        raise Dr2Error(f"effects.tex already has a picture named {name!r}")
    img = load_image(Path(picture).read_bytes(), str(picture))
    bases = {}
    for e in arc.entries:
        b = Bct.parse(e.data(), e.name)
        if b.header.width == b.header.height and b.format.name == "DXT5":
            bases.setdefault(b.header.width, e.name)
    side = min(bases, key=lambda s: abs(s - max(img.width, img.height)))
    sources = Path(mod_dir) / SOURCES_DIR
    sources.mkdir(parents=True, exist_ok=True)
    out_png = sources / f"{name}.png"
    png.write(out_png, resize(img, side, side))
    recipe = {"format": COPY_FORMAT, "copy": f"{EFFECTS_TEX}/{bases[side]}",
              "image": out_png.name}
    out = Path(mod_dir).joinpath(ADD_DIR, *split(EFFECTS_TEX), f"{name}{COPY_EXT}")  # no .bct,
    # like the game's particle pictures
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(recipe, indent=1) + "\n", "utf-8")
    return out


def remove(mod_dir: str | Path, what: str | int) -> list[Path]:
    """Take an effect change (by effect name) or an own effect (by number) out of a mod."""
    gone = []
    if isinstance(what, int) or str(what).isdigit():
        f = Path(mod_dir).joinpath(ADD_DIR, *split(EFFECTS_BIG),
                                   f"EFFECT_Common{OWN_ENTRY + int(what)}{COPY_EXT}")
        if f.is_file():
            f.unlink()
            gone.append(f)
        return gone
    folder = Path(mod_dir).joinpath(REPLACE_DIR, *split(EFFECTS_BIG))
    for f in folder.glob(f"*{EFFECT_EXT}") if folder.is_dir() else []:
        if json.loads(f.read_text("utf-8")).get("effect", "").lower() == str(what).lower():
            f.unlink()
            gone.append(f)
    return gone

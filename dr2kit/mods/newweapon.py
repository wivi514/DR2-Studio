"""A weapon of one's own from a few choices: the weapon wizard (phase 13 step 3).

Why: phase 12 made "Frostmourne" by hand (docs/phase12-kickoff.md §Status): a game
weapon's pack with a new shape, another weapon's moves, a freeze block, effects, a combo
card, names in two languages. Each piece was measured in game; this module does all of
them from one description, `WeaponSpec`, which Studio's *New weapon…* fills in and
``dr2 mod new-weapon`` reads from its options.

What `make_weapon` writes into the mod (nothing of the game's: LICENSE). The mod becomes a
mod for that one game (a weapon starts from one game's weapon, and a mod has no per-game
files):

* ``sources/<Name>.weapon.json``: the description itself, so the wizard can open the
  weapon again and change it (`load_spec`); running it again rebuilds every file below.
* the **pack** recipe ``add/data/streamedassets.big/<Name>.big.copy.json``
  (`mods.newitem`): the kind's game weapon copied under the new name, with the modder's
  model fitted into it (`convert.weapon_fit`: ``sources/<Name>.glb`` and its colour
  picture), a flat normal map and a plain shine map (the template's would not match the
  new shape's UVs), and the **inventory icon** rendered from the model
  (`convert.icon.weapon_icon`, ``sources/<Name>_icon.png``) under ``w_<name>``, or the
  modder's own PNG.
* the **``items.txt`` block** (``replace/data/datafile.big/items.txt.edits.json``): the
  game weapon's block (with its child blocks) under the new name, so its moves, sounds
  and handling come along; then damage, durability, the element (`catalog.weapons`:
  shock = ``Can_Electrocute``; fire / freeze = a child ``cPropHitZombieInfoItem``), the
  effects (on impact, on the zombie hit, while held = condition 30, while swinging =
  condition 31), its name's string id and its icon's name.
* **its name**, and the card's texts, in every string bank (``str_<lang>.bcs.json``): new
  string ids from a block of 100 that depends on the mod's id (`string_ids`), English and
  French written by the wizard, the other languages English unless filled.
* with a **combo**: a ``cComboCardItem`` in the weapon's block (the two items, a free
  card number, the game's first card's other keys), and its two card pictures
  ``add/data/frontend/combocards.tex/comboc_<name>(_no).bct.copy.json`` assembled when the
  mod is built (`mods.newitem.build_card`) from ``sources/<Name>_card.png`` (rendered from
  the model, `convert.icon.card_portrait`, or the modder's own).

Effects **on the weapon** (while held, while swinging) sit at the model's locator type 16
(``LOC_particle_pos``); the wizard moves it (the recipe's ``locators``,
`convert.weapon_fit.effect_locator`) to just above the hand with +y toward the tip, so an
effect made along +y runs along the blade: the game weapon's own is turned across the
blade (the Broadsword's: the flame hung down from the held sword, user, 2026-10-12).

Measured in game (phase 12): borrowed moves, the hands at the model's grip nodes, the
three elements, conditions 30/31, a card in the result's block, new packs loading
(phase 13: the "stall" of phase 12's test mod did not come back, docs/formats.md
§Weapons). Not yet seen in game: an icon under a new name, a card picture under a new
name, card numbers past the game's (phase13-kickoff.md §Status).
"""

from __future__ import annotations

import json
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..catalog import weapons
from ..container.vpath import AssetTree, join, split
from ..convert import placed
from ..errors import Dr2Error
from .manifest import ADD_DIR
from .newitem import COPY_EXT, COPY_FORMAT, NAME, SOURCES_DIR, build_copy

SPEC_FORMAT = "dr2kit-weapon/1"
SPEC_EXT = ".weapon.json"
CARDS = "data/frontend/combocards.tex"
STRING_BASE = 60000                # new string ids: 60000 + 100 × (a number from the mod id)
STRING_BLOCKS = 390                # … up to 98,999 (the banks end at 99,999)
WRITTEN_LANGS = ("en", "fr")       # the wizard's own text boxes; others get English
NO_TEXT_BANKS = ("id",)            # str_id.bcs holds labels, not text
CARD_ITEMS_SOURCE = "items"


ON_WEAPON = ("held", "swinging")     # effect slots drawn at the weapon's locator 16

# How shiny the weapon is: the four material values (MatArray +16) of a game weapon of the
# same shader (LIT_CM2DDL_NM_RMX_SPEC), copied. Their meanings are not measured one by one
# (docs/formats.md §Weapons); the 3rd seems to be the reflection: the Broadsword's 1.0
# turned Frostmourne's dark WoW picture black and gold in the sunset, the Lead Pipe's
# values showed the same picture right (CZ, 2026-10-12).
SHINES = {
    "game": ("The game weapon's", None),
    "matte": ("Matte (like the Baseball Bat)", (400.0, 0.0, 0.5, 1.0)),
    "little": ("A little (like the Lead Pipe)", (4244.44, 0.2, 0.15, 1.0)),
    "mirror": ("Mirror (like the Broadsword)", (911.111, 0.7, 1.0, 1.0)),
}


@dataclass
class Combo:
    """A combo recipe: ``items`` combined at a workbench make the weapon."""
    items: list[str]                                   # two items.txt names
    picture: str = "auto"                              # "auto" (rendered) or a PNG file
    number: int | None = None                          # CardIndexNumber; None: the first free
    description: dict[str, str] = field(default_factory=dict)   # lang -> card text


@dataclass
class WeaponSpec:
    """Everything the wizard asks (module docstring)."""
    name: str                                          # the item's name (letters, digits, _)
    kind: str                                          # a weapon_kinds.toml id
    names: dict[str, str] = field(default_factory=dict)   # lang -> shown name
    model: str | None = None        # a .glb file, "sample", or None: keep the game weapon's
    handle: str = "auto"            # convert.weapon_fit.fit placement
    length: float | None = None
    turn: float = 0.0
    slide: float = 0.0
    damage: int | None = None       # per attack; None: the game weapon's
    durability: int | None = None
    element: str = "none"
    effects: dict[str, int] = field(default_factory=dict)   # slot -> effect number
    effect_start: float = 0.10      # effects on the weapon: metres from the hand to the tip
    shine: str = "game"             # SHINES: the material values of a game weapon
    icon: str = "auto"              # "auto" (rendered), a PNG, or "keep"
    combo: Combo | None = None

    def to_json(self) -> str:
        d = asdict(self)
        d = {"format": SPEC_FORMAT, **d}
        return json.dumps(d, ensure_ascii=False, indent=1) + "\n"

    @classmethod
    def from_json(cls, text: str, where: str = "") -> "WeaponSpec":
        d = json.loads(text)
        if d.pop("format", None) != SPEC_FORMAT:
            raise Dr2Error(f"{where}: not a {SPEC_FORMAT} file")
        combo = d.pop("combo", None)
        spec = cls(**d)
        if combo:
            spec.combo = Combo(**combo)
        return spec


@dataclass
class Made:
    """What `make_weapon` did."""
    files: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    string_ids: dict[str, int] = field(default_factory=dict)
    card_number: int | None = None


# --- helpers ----------------------------------------------------------------------------

def spec_path(mod_dir: str | Path, name: str) -> Path:
    return Path(mod_dir) / SOURCES_DIR / f"{name}{SPEC_EXT}"


def load_spec(mod_dir: str | Path, name: str) -> WeaponSpec:
    f = spec_path(mod_dir, name)
    if not f.is_file():
        raise Dr2Error(f"{name} is not a weapon made by the wizard in this mod")
    return WeaponSpec.from_json(f.read_text("utf-8"), str(f))


def weapons_of(mod_dir: str | Path) -> list[str]:
    """The wizard's weapons in a mod."""
    d = Path(mod_dir) / SOURCES_DIR
    return sorted(p.name[:-len(SPEC_EXT)] for p in d.glob(f"*{SPEC_EXT}")) if d.is_dir() else []


def string_ids(mod_id: str, game_ids: set[int], taken: set[int], count: int) -> list[int]:
    """``count`` new string ids for a mod: from its own block of 100 (so two mods rarely
    pick the same ids; a clash is reported by the build), none the game or the mod uses."""
    start = STRING_BASE + 100 * (zlib.crc32(mod_id.encode()) % STRING_BLOCKS)
    out = []
    for k in range(start, 99_000):
        if k not in game_ids and k not in taken:
            out.append(k)
            if len(out) == count:
                return out
    raise Dr2Error("no free string ids left")


def _texts(spec_texts: dict[str, str], fallback: str) -> dict[str, str]:
    en = spec_texts.get("en") or fallback
    return {**{k: v for k, v in spec_texts.items() if v}, "en": en}


def _flat(width: int, height: int, rgba) -> "object":
    from ..convert import png
    return png.Image(width, height, bytes(rgba) * (width * height))


# --- the wizard -------------------------------------------------------------------------

def template_of(spec: WeaponSpec, game: str) -> str:
    return weapons.kind(spec.kind).template(game)


def make_weapon(tree: AssetTree, game: str, mod_dir: str | Path, spec: WeaponSpec,
                base_dirs=(), mod_id: str | None = None) -> Made:
    """Write the weapon ``spec`` into the mod at ``mod_dir`` (module docstring). Running
    it again for the same name replaces what it wrote before."""
    import numpy as np
    from ..convert import icon as cicon
    from ..convert import png
    from ..convert import strings as cstr
    from ..convert import weapon_fit as wf
    from .leveledit import TextEdits
    from .manifest import Mod

    root = Path(mod_dir)
    made = Made()
    mod = Mod.load(root)
    mod_id = mod_id or mod.id
    if tuple(mod.games) != (game,):            # its files are one game's (module docstring)
        mod.games = (game,)
        mod.save()
        made.notes.append(f"{mod.id} is now a mod for {game.upper()} only: a weapon is made "
                          f"from one game's weapon (make another mod for the other game)")
    name = spec.name
    if not NAME.match(name):
        raise Dr2Error(f"{name!r}: a weapon name is a letter then letters, digits or _ (up "
                       f"to 41)")
    if spec.element not in weapons.elements():
        raise Dr2Error(f"element {spec.element!r}: {', '.join(weapons.elements())}")
    for slot in spec.effects:
        if slot not in weapons.slots():
            raise Dr2Error(f"effect slot {slot!r}: {', '.join(weapons.slots())}")
    models = placed.ItemModels(tree)
    if name.lower() in models.blocks:
        raise Dr2Error(f"{name!r} is already an item of the game")
    sources = root / SOURCES_DIR
    sources.mkdir(parents=True, exist_ok=True)
    m = fit_weapon(tree, game, spec, sources, models)
    made.notes += m.notes
    src, frame = m.block, m.frame
    spec_path(root, name).write_text(spec.to_json(), "utf-8")
    made.files.append(spec_path(root, name))

    # 1. the pack: a recipe copying the game weapon's, with the model, textures and icon
    recipe: dict = {"format": COPY_FORMAT, "copy": m.pack_vp, "rename": {m.scene_name: name}}
    if m.glb is not None:
        glb_file = sources / f"{name}.glb"
        glb_file.write_bytes(m.glb)
        made.files.append(glb_file)
        recipe["glb"] = glb_file.name
        textures = {}
        for tname, (w, h) in m.tex_sizes.items():
            role = _role(tname)
            out = sources / f"{name}_{tname}.png"
            if role == "colour":
                pic = m.colour if (w, h) == m.colour_size else wf._resize(m.colour, w, h)
                if "blood" in tname:
                    pic = pic.copy()
                    pic[..., :3] = (pic[..., :3] * np.array([0.8, 0.45, 0.42])).astype(np.uint8)
                png.write(out, png.Image(w, h, np.ascontiguousarray(pic).tobytes()))
            elif role == "normal":
                png.write(out, _flat(w, h, (128, 128, 255, 255)))
            elif role == "specular":
                png.write(out, _flat(w, h, (90, 90, 90, 255)))
            else:
                continue
            textures[_entry_name(tree, m.pack_vp, m.scene_name, tname)] = out.name
            made.files.append(out)
        recipe["textures"] = textures
    parts_for_pictures = m.parts
    if spec.icon != "keep":
        icon_file = sources / f"{name}_icon.png"
        if spec.icon == "auto":
            pic = cicon.weapon_icon(parts_for_pictures, frame)
            png.write(icon_file, png.Image(pic.shape[1], pic.shape[0], pic.tobytes()))
        else:
            _copy_png(Path(spec.icon), icon_file, cicon.ICON_SIZE)
        recipe["icon"] = icon_file.name
        recipe["icon_name"] = f"w_{name.lower()}"
        made.files.append(icon_file)
    if spec.shine not in SHINES:
        raise Dr2Error(f"shine {spec.shine!r}: {', '.join(SHINES)}")
    if SHINES[spec.shine][1] is not None:
        recipe["material_params"] = list(SHINES[spec.shine][1])
    if any(slot in spec.effects for slot in ON_WEAPON):     # effects along the blade
        pos, rot = wf.effect_locator(frame, spec.effect_start)
        recipe["locators"] = {str(wf.EFFECT_LOCATOR): {"position": pos, "rotation": rot}}
    out = root.joinpath(ADD_DIR, *split(placed.STREAMED), f"{name}.big{COPY_EXT}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(recipe, indent=1) + "\n", "utf-8")
    build_copy(tree, recipe, root, name)                    # it must build now
    made.files.append(out)

    # 2. strings: the name (and the card's texts)
    langs = [lang for lang in cstr.languages(tree) if lang not in NO_TEXT_BANKS]
    en_bank = cstr.load_bank(tree, "en").strings
    mine: dict[str, dict[int, str]] = {lang: cstr.read_mod_strings(root, lang) for lang in langs}
    old = _previous_ids(root, name)
    taken = {i for d in mine.values() for i in d} - set(old.values())
    keys = ["name"] + (["card", "ticker", "description"] if spec.combo else [])
    ids = dict(zip(keys, [old[k] for k in keys if k in old] if all(k in old for k in keys)
                   else string_ids(mod_id, set(en_bank), taken, len(keys))))
    made.string_ids = ids
    for k, i in old.items():                                 # texts no longer needed
        if i not in ids.values():
            for lang in langs:
                mine[lang].pop(i, None)
    shown = _texts(spec.names, name)
    for lang in langs:
        mine[lang][ids["name"]] = shown.get(lang, shown["en"])

    # 3. the items.txt block
    items = TextEdits(root, "items.txt", tree, base_dirs)
    d = items.doc
    cls = src.cls
    prev = d.get(f"{cls} {name}")
    if prev is not None:
        d.remove(prev)
    from ..formats.levelscript import to_spec
    children = []
    for c in src.children:
        sp = list(to_spec(c))
        sp[1] = f"{name}_{c.name}" if c.name else c.name
        children.append(tuple(sp))
    b = d.add(None, cls, name, [(p.key, p.value) for p in src.props], children=children)
    d.set(b, "DisplayName", str(ids["name"]))
    if spec.icon != "keep":
        d.set(b, "IconFilename", f"w_{name.lower()}")
    attacks = max(len(b.numbered("AttackDamage")), len(b.numbered("AnimationAttackName")), 1)
    if spec.damage is not None:
        for i in range(attacks):
            d.set(b, f"AttackDamage{i}", str(int(spec.damage)))
        d.set(b, "MaxProjectileDamage", str(int(spec.damage)))
    if spec.durability is not None:
        d.set(b, "Durability", str(int(spec.durability)))
    el = weapons.elements()[spec.element]
    for k, v in (el.get("keys") or {}).items():
        d.set(b, k, v)
    if el.get("child"):
        ch = el["child"]
        d.add(b, ch["cls"], f"{name}_{spec.element}", list(ch["keys"].items()))
    _effects(d, b, spec, game, attacks)

    # 4. the combo card
    if spec.combo:
        made.card_number = _combo(tree, game, root, d, b, spec, ids, mine, langs, en_bank,
                                  models, parts_for_pictures, frame, made)
    else:                                       # no combo (any more): its files go
        for suffix in ("", "_no"):
            root.joinpath(ADD_DIR, *split(CARDS),
                          f"comboc_{name.lower()}{suffix}.bct{COPY_EXT}").unlink(missing_ok=True)
        for f in (f"{name}_card.png", f"{name}_card_faded.png"):
            (sources / f).unlink(missing_ok=True)
        _prune(root / ADD_DIR)
    made.files.append(items.save())
    for lang in langs:
        made.files.append(cstr.set_mod_strings(root, lang, {}, None) if not mine[lang] else
                          _write_strings(root, lang, mine[lang]))
    _remember_ids(root, name, ids)
    return made


@dataclass
class ModelFit:
    """A weapon's model as the wizard makes it (`fit_weapon`): the game weapon it starts
    from, and the new shape fitted into it (or the game's own shape)."""
    block: object                    # the game weapon's items.txt block
    scene: object                    # the game weapon's model (formats.scene.Scene)
    pack_vp: str
    scene_name: str
    frame: object                    # convert.weapon_fit.Frame of the game weapon
    tex_sizes: dict                  # texture name (lower case) -> (w, h)
    parts: list                      # renderer parts of the weapon as it will look
    game_parts: list                 # renderer parts of the game weapon
    glb: bytes | None = None         # the fitted .glb (None: the game's shape is kept)
    colour: object = None            # its colour picture (RGBA array)
    colour_size: tuple = (256, 256)
    notes: list = field(default_factory=list)


def fit_weapon(tree: AssetTree, game: str, spec: WeaponSpec, sources: Path | None = None,
               models=None) -> ModelFit:
    """Fit ``spec``'s model into its kind's game weapon (nothing written)."""
    import numpy as np
    from ..convert import render
    from ..convert import weapon_fit as wf
    from ..convert.model_import import import_glb
    from ..formats.scene import Scene
    like = template_of(spec, game)
    models = models or placed.ItemModels(tree)
    src = models.blocks.get(like.lower())
    scene_vp = models.resolve(like)
    if src is None or scene_vp is None:
        raise Dr2Error(f"{like}: not an item with a model in {game.upper()}")
    parts = split(scene_vp)
    pack_vp, scene_name = join(*parts[:-1]), parts[-1][:-4]
    scene = Scene.parse(tree.resolve(scene_vp).data(), scene_vp)
    tex_sizes = _pack_textures(tree, pack_vp, scene_name)
    game_parts = _game_parts(tree, scene)
    m = ModelFit(src, scene, pack_vp, scene_name, wf.weapon_frame(scene), tex_sizes,
                 game_parts, game_parts)
    if not spec.model:
        return m
    if spec.model == "sample":
        from ..catalog.sample_sword import sample_sword_glb
        glb_bytes, where = sample_sword_glb(), "the sample sword"
    else:
        f = Path(spec.model)
        if not f.is_file() and sources is not None:
            f = sources / spec.model
        if not f.is_file():
            raise Dr2Error(f"{spec.model}: no such model file")
        glb_bytes, where = f.read_bytes(), str(f)
    colour_name = next((mt.texture("colour") for mt in scene.materials
                        if mt.texture("colour")), None)
    m.colour_size = tex_sizes.get((colour_name or "").lower(), (256, 256))
    m.glb, m.colour, fit = wf.fit_model(tree, scene, glb_bytes, where,
                                        texture_size=m.colour_size, handle=spec.handle,
                                        length=spec.length, turn=spec.turn, slide=spec.slide)
    m.notes += fit.notes
    data, _ = import_glb(scene, m.glb, where)
    rgba = m.colour.astype(np.float32) / 255
    m.parts = render.scene_parts(Scene.parse(data, scene_vp), texture_for=lambda n: rgba)
    return m


@dataclass
class Preview:
    """Pictures of a weapon before it is made (`preview`), RGBA arrays."""
    side: object                     # the new shape over the game weapon, grip nodes red
    icon: object
    card: object | None
    notes: list = field(default_factory=list)


def _marker(at, size: float = 0.012):
    """A small red diamond at ``at`` (a renderer part): where a hand grips."""
    import numpy as np
    from ..convert import render
    p = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]],
                 np.float32) * size + np.asarray(at, np.float32)
    tri = np.array([[0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4], [2, 0, 5], [1, 2, 5],
                    [3, 1, 5], [0, 3, 5]], np.int32)
    red = np.zeros((2, 2, 4), np.float32)
    red[...] = (0.9, 0.05, 0.05, 1.0)
    return render.Part(p, tri, None, np.zeros((6, 2), np.float32), red)


def grip_points(scene) -> list:
    """Model-space positions of the model's hand nodes (right and left grips)."""
    import numpy as np
    nodes = scene.skeleton.nodes
    if not nodes:
        return []
    world = scene.skeleton.world_matrices()
    out = []
    for n in nodes:
        last = n.name.rsplit(".", 1)[-1].lower()
        if last.startswith(("loc_rhand", "ik_lhand", "loc_lhand", "loc_wep_", "loc_grip")):
            w = world[n.index]
            out.append(np.array([w[0][3], w[1][3], w[2][3]]))
    return out


def preview(tree: AssetTree, game: str, spec: WeaponSpec, sources: Path | None = None
            ) -> Preview:
    """The wizard's pictures without writing anything: the new shape laid over the game
    weapon (seen from its flat side, the game weapon faded, the hands' grip nodes as red
    diamonds), the inventory icon, and the combo card when there is one."""
    import numpy as np
    from ..convert import icon as cicon
    from ..convert import render
    m = fit_weapon(tree, game, spec, sources)
    basis = cicon.weapon_basis(m.frame, 0.0)
    w, h = 480, 200
    marks = [_marker(p) for p in grip_points(m.scene)]
    side = np.zeros((h, w, 4), np.uint8)
    if m.glb is not None:                            # the game weapon faded behind it
        both = render.render(m.parts + m.game_parts + [_frame_box(m)], width=w, height=h,
                             basis=basis, fill=0.92)
        new = render.render(m.parts + [_frame_box(m)], width=w, height=h,
                            basis=basis, fill=0.92)
        side = both.copy()
        side[..., 3] = (both[..., 3] * 0.35).astype(np.uint8)
        a = new[..., 3:4].astype(np.float32) / 255
        side[..., :3] = (new[..., :3] * a + side[..., :3] * (1 - a)).astype(np.uint8)
        side[..., 3] = np.maximum(side[..., 3], new[..., 3])
        dots = render.render(marks + [_frame_box(m)], width=w, height=h, basis=basis,
                             fill=0.92)
        if dots is not None:                          # the hands' nodes on top
            on = dots[..., 3] > 0
            side[on] = dots[on]
    else:
        pic = render.render(m.parts + marks, width=w, height=h, basis=basis, fill=0.92)
        if pic is not None:
            side = pic
    if any(slot in spec.effects for slot in ON_WEAPON):     # where weapon effects go
        line = render.render([_effect_line(m.frame, spec.effect_start), _frame_box(m)],
                             width=w, height=h, basis=basis, fill=0.92)
        if line is not None:
            on = line[..., 3] > 0
            side[on] = line[on]
    pic_icon = cicon.weapon_icon(m.parts, m.frame) if spec.icon != "keep" else None
    card = None
    if spec.combo:
        card = _card_preview(tree, m, spec)
    return Preview(side, pic_icon, card, m.notes)


# --- the 3D view: Chuck holding it (phase 13.2) ------------------------------------------

EFFECT_AT = {"held": "point", "swinging": "point", "impact": "tip", "victim": "tip"}


@dataclass
class HoldScene:
    """What Studio's 3D view of a weapon shows (`hold_scene`): the weapon (a textured
    ``.glb`` in its model space), where it hangs in Chuck's hand, Chuck's frozen idle for
    its kind, the line the drag handles move along, and its effects."""
    weapon_glb: bytes
    placement: list                  # 16 numbers, column order: weapon model -> Chuck
    pose: dict                       # Chuck's rig: node name -> local rotation / translation
    idle: object                     # convert.holding.Idle
    frame: dict                      # model space: origin (the handle end now), axis, side,
    #                                  thin (unit), length now, the game weapon's length,
    #                                  slide, turn, effect_start
    effect_point: dict               # model space: position, rotation (x y z w)
    effects: list                    # {slot, name, number, at: point|tip, emitters: [...]}
    textures: dict                   # particle picture name -> PNG bytes
    chuck: object = None             # convert.holding.Chuck
    notes: list = field(default_factory=list)
    moves: list = field(default_factory=list)   # [(label, clip)]: its kind's attacks


def _emitter_json(e) -> dict:
    return {"offset": e.get("offset"), "count": e.get("count_20"), "speed": e.get("speed"),
            "spread": e.get("spread"), "gravity": e.get("gravity"),
            "times": e.get("colour_times"), "colours": e.colour_keys(), "sizes": e.get("sizes"),
            "shape": e.get("shape"), "shape_values": e.shape_values, "texture": e.texture,
            "blend": e.get("blend")}


def effect_view(tree: AssetTree, fx, slot: str, number: int = 0,
                mod_dir: str | Path | None = None, textures: dict | None = None) -> dict:
    """One effect (`formats.effect.Effect`) as the 3D view takes it; its particle pictures
    are added to ``textures`` (name -> PNG bytes)."""
    from . import neweffect
    if textures is not None:
        for e in fx.emitters:
            if e.texture not in textures:
                png_bytes = neweffect.particle_png(tree, e.texture, mod_dir)
                if png_bytes:
                    textures[e.texture] = png_bytes
    return {"slot": slot, "name": fx.name, "number": number, "at": EFFECT_AT.get(slot, "tip"),
            "emitters": [_emitter_json(e) for e in fx.emitters]}


def hold_scene(tree: AssetTree, game: str, spec: WeaponSpec, sources: Path | None = None,
               mod_dir: str | Path | None = None, models=None) -> HoldScene:
    """Everything Studio's 3D view needs to show Chuck holding ``spec``'s weapon in the
    game's idle for its kind (`convert.holding`), with its effects (the mod's own and
    changed ones included). Nothing written."""
    import numpy as np
    from ..convert import holding, png
    from ..convert import weapon_fit as wf
    from ..convert.gltf import glb_with_picture
    from ..convert.model import model_glb
    from ..formats.effect import read_all
    from . import neweffect
    m = fit_weapon(tree, game, spec, sources, models)
    chuck = holding.posed_chuck(tree, m.block)
    if m.glb is not None:
        rgba = np.ascontiguousarray(m.colour, dtype=np.uint8)
        pic = png.encode(png.Image(rgba.shape[1], rgba.shape[0], rgba.tobytes()))
        weapon = glb_with_picture(m.glb, pic, spec.name)
    else:
        weapon = model_glb(tree, m.scene, game=game, mode="shown")
    place = holding.item_placement(chuck.hand, holding.grip_matrix(m.scene))
    f = m.frame
    length = spec.length or f.length
    vec = lambda v: [float(c) for c in v]          # noqa: E731
    frame = {"origin": vec(f.handle + f.axis * spec.slide), "axis": vec(f.axis),
             "side": vec(f.side), "thin": vec(f.thin), "length": float(length),
             "game_length": float(f.length), "slide": spec.slide, "turn": spec.turn,
             "effect_start": spec.effect_start,
             "tip": vec(f.handle + f.axis * (spec.slide + length)),
             "grips": [vec(g) for g in grip_points(m.scene)],
             "movable": m.glb is not None}
    pos, rot = wf.effect_locator(f, spec.effect_start)
    effects, textures, notes = [], {}, list(m.notes) + list(chuck.idle.notes)
    table = read_all(tree) if spec.effects else {}
    for slot, number in spec.effects.items():
        n = weapons.effect_number(game, number)
        fx = neweffect.effect_as_shown(tree, game, n, mod_dir, table)
        if fx is None:
            notes.append(f"effect {n} ({slot}): nothing to show (an empty slot)")
            continue
        effects.append(effect_view(tree, fx, slot, n, mod_dir, textures))
    moves = holding.move_clips(tree, m.block, chuck.idle)
    return HoldScene(weapon, holding.flat(place), chuck.pose, chuck.idle, frame,
                     {"position": pos, "rotation": rot}, effects, textures, chuck, notes,
                     moves)


def hold_glb(tree: AssetTree, game: str, spec: WeaponSpec, sources: Path | None = None,
             textures: bool = True, moves: bool = False) -> bytes:
    """One ``.glb`` of Chuck in the idle for ``spec``'s kind holding the weapon (for
    Blender: ``dr2 hold --mod``). The effects are not in it; an empty node marks the
    effect point (+y along the blade). ``moves``: the kind's attacks as glTF animations,
    the weapon under his hand node (`convert.holding.hang_on_hand`)."""
    from ..convert import gltf, holding
    scene = hold_scene(tree, game, spec, sources)
    chuck = scene.chuck
    asm = gltf.Assembler()
    holding.chuck_glb(tree, game, chuck, textures=textures, assembler=asm)
    m = [[scene.placement[c * 4 + r] for c in range(4)] for r in range(4)]
    node = holding.hang_on_hand(asm, chuck, scene.weapon_glb, spec.name, m, spec.name,
                                on_hand=moves)
    asm.empty("effect_point", node, scene.effect_point["position"],
              scene.effect_point["rotation"])
    asm.extras = {"weapon": spec.name, "idle": chuck.idle.fullbody, "hand": chuck.idle.hand}
    if moves:
        m = fit_weapon(tree, game, spec, sources)
        asm.extras["moves"] = holding.add_moves(asm, tree, m.block, chuck.idle)
    return asm.to_bytes()


def _effect_line(frame, start: float, length: float = 0.7):
    """A thin yellow bar where the effects on the weapon go: from their point
    (`convert.weapon_fit.effect_locator`) ``length`` metres along +y (the way the Flaming
    Sword's flame runs), for the preview."""
    import numpy as np
    from ..convert import render
    from ..convert import weapon_fit as wf
    pos, _ = wf.effect_locator(frame, start)
    a = np.asarray(pos, np.float32)
    b = a + np.asarray(frame.axis, np.float32) * length
    t = np.asarray(frame.side, np.float32) * 0.006 + np.asarray(frame.thin, np.float32) * 0.006
    u = np.asarray(frame.side, np.float32) * 0.006 - np.asarray(frame.thin, np.float32) * 0.006
    p = np.array([a + t, a - t, b - t, b + t, a + u, a - u, b - u, b + u], np.float32)
    tri = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]], np.int32)
    cyan = np.zeros((2, 2, 4), np.float32)
    cyan[...] = (1.0, 0.85, 0.1, 1.0)
    return render.Part(p, tri, None, np.zeros((8, 2), np.float32), cyan)


def _frame_box(m: ModelFit):
    """An invisible part spanning both shapes, so the new shape alone is framed like the
    two together (the renderer frames on what it draws)."""
    import numpy as np
    from ..convert import render
    pts = np.concatenate([p.positions for p in m.parts + m.game_parts])
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1])
                        for z in (lo[2], hi[2])], np.float32)
    clear = np.zeros((1, 1, 4), np.float32)
    return render.Part(corners, np.array([[0, 0, 0]], np.int32), None,
                       np.zeros((8, 2), np.float32), clear, alpha_test=True)


def _card_preview(tree: AssetTree, m: ModelFit, spec: WeaponSpec):
    import numpy as np
    from ..convert import icon as cicon
    from ..convert.render import scene_parts
    from ..convert.texture import to_image
    from ..formats.bct import Bct
    from ..formats.scene import Scene
    arc = tree.open_archive(tree.resolve(CARDS).vpath)
    cards = []
    for e in arc.entries:
        low = e.name.lower()
        if low.startswith("comboc_") and not low.endswith("_no.bct"):
            im = to_image(Bct.parse(e.data(), e.name))
            cards.append(np.frombuffer(im.rgba, np.uint8).reshape(im.height, im.width, 4))
    empty = cicon.card_template(cards)
    if spec.combo.picture == "auto":
        portrait = cicon.card_portrait(m.parts, m.frame, spec.element)
    else:
        from ..convert import png
        from .texture_import import load_image, resize
        w, h = cicon.portrait_size()
        img = resize(load_image(Path(spec.combo.picture).read_bytes(), spec.combo.picture), w, h)
        portrait = np.frombuffer(png.Image(w, h, img.rgba).rgba, np.uint8).reshape(h, w, 4)
    models = placed.ItemModels(tree)
    drawings = []
    for item in spec.combo.items[:2]:
        vp = models.resolve(item)
        drawings.append(None if vp is None else cicon.item_drawing(
            scene_parts(Scene.parse(tree.resolve(vp).data(), vp))))
    return cicon.compose_card(empty, portrait, drawings)


def _role(tname: str) -> str:
    from ..formats.scene import texture_role
    return texture_role(tname)


def _pack_textures(tree: AssetTree, pack_vp: str, scene_name: str) -> dict[str, tuple[int, int]]:
    """texture name (lower case) → (width, height) of the model's ``<scene>.tex``."""
    from ..container.big import BigArchive
    from ..formats.bct import Bct
    arc = tree.open_archive(tree.resolve(pack_vp).vpath)
    out = {}
    for e in arc.entries:
        if e.name.lower() == f"{scene_name.lower()}.tex":
            for t in BigArchive.parse(e.data(), e.name).entries:
                b = Bct.parse(t.data(), t.name)
                out[t.name.lower().removesuffix(".bct")] = (b.header.width, b.header.height)
    return out


def _entry_name(tree: AssetTree, pack_vp: str, scene_name: str, lower: str) -> str:
    """A texture's name as the pack spells it."""
    from ..container.big import BigArchive
    arc = tree.open_archive(tree.resolve(pack_vp).vpath)
    for e in arc.entries:
        if e.name.lower() == f"{scene_name.lower()}.tex":
            for t in BigArchive.parse(e.data(), e.name).entries:
                if t.name.lower().removesuffix(".bct") == lower:
                    return t.name.removesuffix(".bct")
    return lower


def _game_parts(tree: AssetTree, scene):
    """A game model's renderer parts with its colour textures."""
    from ..convert import render
    from ..convert.model import TextureFinder
    finder = TextureFinder(tree, scene.source, None)

    def tex(name):
        im = finder.image(name)
        return None if im is None else render.rgba_to_float(im.rgba, im.width, im.height)
    return render.scene_parts(scene, texture_for=tex)


def _copy_png(src: Path, dest: Path, size) -> None:
    from ..convert import png
    from .texture_import import load_image, resize
    if not src.is_file():
        raise Dr2Error(f"{src}: no such picture")
    img = resize(load_image(src.read_bytes(), str(src)), *size)
    png.write(dest, img)


def _effects(d, b, spec: WeaponSpec, game: str, attacks: int) -> None:
    slots = weapons.slots()
    for slot, value in spec.effects.items():
        n = weapons.effect_number(game, value)
        s = slots[slot]
        if "keys" in s:
            for key in s["keys"]:
                for i in range(attacks):
                    d.set(b, key.replace("#", str(i)), str(n))
            continue
        cond = str(s["condition"])                 # an effect on the weapon itself
        used = {int(k[len("PropEffectsOnCondition"):]) for k in (p.key for p in b.props)
                if k.startswith("PropEffectsOnCondition") and k[22:].isdigit()}
        same = next((i for i in sorted(used) if b.get(f"PropEffectsOnCondition{i}") == cond),
                    None)
        i = same if same is not None else max(used | {-1}) + 1
        if not n:
            continue
        d.set(b, f"PropEffectsOnCondition{i}", cond)
        d.set(b, f"PyroEffect{i}", str(n))
        d.set(b, f"PropEffectLocator{i}", "16")
        d.set(b, f"PropEffectLocatorIndex{i}", "0")


def _shown_name(tree, models, item: str, lang: str, cache: dict) -> str:
    from ..convert import strings as cstr
    blk = models.blocks.get(item.lower())
    if lang not in cache:
        try:
            cache[lang] = cstr.load_bank(tree, lang).strings
        except Dr2Error:
            cache[lang] = cstr.load_bank(tree, "en").strings
    try:
        return cache[lang].get(int(blk.get("DisplayName")), item)
    except (TypeError, ValueError, AttributeError):
        return item


def _combo(tree, game, root, d, b, spec, ids, mine, langs, en_bank, models, parts, frame,
           made) -> int:
    from ..convert import icon as cicon
    from ..convert import png
    combo = spec.combo
    if len(combo.items) != 2:
        raise Dr2Error("a combo needs two items")
    for it in combo.items:
        if it.lower() not in models.blocks:
            raise Dr2Error(f"{it!r} is not an item of {game.upper()}")
    first = next((x for x in d.walk() if x.cls == "cComboCardItem"), None)
    used = {x.get("CardIndexNumber") for x in d.walk() if x.cls == "cComboCardItem"}
    number = combo.number
    if number is None:
        number = next(k for k in range(1, 1000) if str(k) not in used)
    elif str(number) in used:
        made.notes.append(f"card number {number} is already a card of the game or the mod")
    keys = dict((p.key, p.value) for p in first.props) if first is not None else {}
    keys.pop("Attack2", None)
    keys.pop("AttackIndexToDisableIfNoColouredComboCard", None)
    keys.pop("DR2PRO", None)
    keys.update({"Card_Label": str(ids["card"]), "CardIndexNumber": str(number),
                 "IconAsset": f"comboc_{spec.name.lower()}",
                 "Ticker_Description": str(ids["ticker"]),
                 "Weapon_Description": str(ids["description"]),
                 "Weapon_1": combo.items[0], "Weapon_2": combo.items[1],
                 "ComboStationRotation_1": "0,0,0,1", "ComboStationRotation_2": "0,0,0,1"})
    d.add(b, "cComboCardItem", f"{spec.name}_Card", sorted(keys.items(), key=lambda kv: kv[0].lower()))
    shown = _texts(spec.names, spec.name)
    desc = combo.description or {}
    cache: dict = {}
    for lang in langs:
        nm = shown.get(lang, shown["en"])
        a, c = (_shown_name(tree, models, it, lang, cache) for it in combo.items)
        mine[lang][ids["card"]] = nm.upper()
        mine[lang][ids["ticker"]] = f"@{nm.upper()}: [00CC00FF,{a}] + [00CC00FF,{c}]"
        mine[lang][ids["description"]] = desc.get(lang) or desc.get("en") or nm
    sources = root / SOURCES_DIR
    portrait = sources / f"{spec.name}_card.png"
    if combo.picture == "auto":
        pic = cicon.card_portrait(parts, frame, spec.element)
        png.write(portrait, png.Image(pic.shape[1], pic.shape[0], pic.tobytes()))
        faded_src = sources / f"{spec.name}_card_faded.png"
        fp = cicon.card_portrait(parts, frame, glow=False)
        png.write(faded_src, png.Image(fp.shape[1], fp.shape[0], fp.tobytes()))
        made.files += [portrait, faded_src]
    else:
        _copy_png(Path(combo.picture), portrait, cicon.portrait_size())
        faded_src = portrait
        made.files.append(portrait)
    arc = tree.open_archive(tree.resolve(CARDS).vpath)
    base = next(e.name for e in arc.entries if e.name.lower().startswith("comboc_")
                and not e.name.lower().endswith("_no.bct"))
    for suffix, pic, faded in (("", portrait, False), ("_no", faded_src, True)):
        base_name = base if not faded else base[:-4] + "_no.bct"
        r = {"format": COPY_FORMAT, "copy": f"{CARDS}/{base_name}",
             "card": {"portrait": pic.name, "items": list(combo.items), "faded": faded}}
        f = root.joinpath(ADD_DIR, *split(CARDS), f"comboc_{spec.name.lower()}{suffix}.bct{COPY_EXT}")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(r, indent=1) + "\n", "utf-8")
        made.files.append(f)
    return number


def _prune(folder: Path) -> None:
    """Remove empty folders under ``folder`` (and it, if empty)."""
    if not folder.is_dir():
        return
    for d in sorted((p for p in folder.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        if not any(d.iterdir()):
            d.rmdir()
    if not any(folder.iterdir()):
        folder.rmdir()


def _write_strings(root: Path, lang: str, strings: dict[int, str]) -> Path:
    from ..convert import strings as cstr
    current = cstr.read_mod_strings(root, lang)
    gone = {i: None for i in current if i not in strings}
    return cstr.set_mod_strings(root, lang, {**gone, **strings})


IDS_FILE = "weapon_string_ids.json"


def _previous_ids(root: Path, name: str) -> dict[str, int]:
    f = root / SOURCES_DIR / IDS_FILE
    if not f.is_file():
        return {}
    return {k: int(v) for k, v in json.loads(f.read_text("utf-8")).get(name, {}).items()}


def _remember_ids(root: Path, name: str, ids: dict[str, int]) -> None:
    f = root / SOURCES_DIR / IDS_FILE
    data = json.loads(f.read_text("utf-8")) if f.is_file() else {}
    data[name] = ids
    f.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", "utf-8")


def remove_weapon(tree: AssetTree, mod_dir: str | Path, name: str, base_dirs=()) -> list[Path]:
    """Take a wizard weapon out of a mod (its block, strings, pack and card recipes,
    sources)."""
    from ..convert import strings as cstr
    from .leveledit import TextEdits
    root = Path(mod_dir)
    removed = []
    items = TextEdits(root, "items.txt", tree, base_dirs)
    for b in list(items.doc.blocks):
        if b.name == name:
            items.doc.remove(b)
    items.save()
    ids = _previous_ids(root, name)
    for lang in cstr.languages(tree):
        if lang in NO_TEXT_BANKS:
            continue
        if any(i in cstr.read_mod_strings(root, lang) for i in ids.values()):
            cstr.set_mod_strings(root, lang, {i: None for i in ids.values()})
    for f in [root.joinpath(ADD_DIR, *split(placed.STREAMED), f"{name}.big{COPY_EXT}"),
              *[root.joinpath(ADD_DIR, *split(CARDS), f"comboc_{name.lower()}{s}.bct{COPY_EXT}")
                for s in ("", "_no")]]:
        if f.is_file():
            f.unlink()
            removed.append(f)
    _prune(root / ADD_DIR)
    src = root / SOURCES_DIR
    for f in src.glob(f"{name}*") if src.is_dir() else []:
        if f.name == name + SPEC_EXT or f.name.startswith((f"{name}_", f"{name}.")):
            f.unlink()
            removed.append(f)
    f = src / IDS_FILE
    if f.is_file():
        data = json.loads(f.read_text("utf-8"))
        data.pop(name, None)
        f.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", "utf-8")
    return removed

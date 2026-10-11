"""Variants: which parts and colours of a model the game shows at once.

Why: a zombie model holds every look at once (four heads, four shirts, three pairs of
trousers, a burnt version, the wound caps shown when a limb comes off). The game draws
one choice per slot; a tool that draws every shape shows a zombie wearing all its
clothes on top of each other. This module works out, **the way the game does**, which
shapes belong to which choice, so DR2 Studio, the Library pictures and the exports can
show one look, any look, or everything sorted into groups.

How the game does it (docs/formats.md §Variants, both games, measured in the CZ recomp):

* **Shape groups.** A table in the executable (53 records ``{u64 mask, pattern}``,
  copied into the game profiles' ``[variants]`` by ``tools/variant_table.py``) gives
  each comma list of name patterns a bit. A pattern is a **prefix**, case-sensitive; a
  ``*`` ends it (``head1_*`` matches ``head1_headShape``). A shape's bits are the OR of
  every record whose pattern matches; the ``*`` record (``0x1000``) only counts when no
  other does (`Classifier.bits`).
* **The hide mask.** Each zombie carries 64 bits; a shape is skipped when
  ``bits & mask != 0`` (`ModelVariants.hide_mask`, `ModelVariants.shown`). So a choice
  is the set of bits to hide: every head but the chosen one, every shirt but the chosen
  one…, the wound caps, the burnt set. Shapes with no variant bits (``head_eyes``) always
  draw. Body-region bits (``head*``, ``larm_*``…) are for cutting limbs off and are never
  hidden here.
* **Slots** come from the game's own slot table (heads 1-5, headwear 1-5, shirts 1-6,
  trousers 1-7, skirt, feet 1-7, tall boots; CZ ``0x8208A2E0``); head tumours (CW's gas
  zombie) are a slot of their own here. **On/off parts** (`TOGGLES`) are the other bits:
  wound caps, burnt, gas look, bare arms, glasses, chest accessories, backpack, shirt
  tumour.
* **Misplaced digits.** The game reads the number from the name, so
  ``headwearShape2Deformed`` (digit after ``Shape``) loses its variant bit and is drawn
  on every zombie (CZ ``zombie_soldier_3``; CW ``zombie_security_2``/``_3``). Like the CZ
  recomp's fix, the classifier reads these as the artist meant
  (``headwear2ShapeDeformed``) and reports them (`Part.misplaced`).
* **Which models.** The table applies to crowd zombies: models in
  ``data/models/zombies.big`` and any model with numbered parts (cutscene zombies). Other
  models (Chuck, people, props) are never classified, so a prop's ``cap_…`` shape is not
  mistaken for a wound cap.

Not known yet (❓ in formats.md): how the game picks a number per slot (the code that
writes the spawn record's mask was not found), so the **default** look is the first
choice of each slot, accessories on, no caps, not burnt; ``random`` picks evenly.

**Prop states** (`PROP_STATES`, any model): a few props keep states as twin shapes
(slot machines: ``slot_logo`` / ``slot_logo_dmg``, ``LOD_slot_machine``,
``slot_screen_staticWin``). A state shape shows only when its state is on, and hides its
twin then. Off by default. Rules by name, applied only when the twin exists.

**Colour choices** (`colour_choices`): a material may swap its value set for another
(``zombie_skinny_mtl_jersey.pdv`` → ``…jersey1.pdv`` … ``jersey5.pdv``), which only
changes the shader constants `convert.material` bakes. The choices are value sets in
the shader bank (``data/shaders/*-sc.big``) named ``<own name>N.pdv`` or
``<own name>_varN.pdv``. That rule reproduces CZ's ``zombie_pdv_variations.txt`` exactly
(all 129 listed choices, and nothing listed is missed); CW's list is empty, so there the
rule alone gives the choices (whether CW's game uses them is ❓). `ColourChoice.listed`
says whether the game's list names a choice.

A **choice** is plain text, the same everywhere (Studio, ``info.txt``, the CLI's
``--variant``): ``head=2 shirt=1 headwear=none burnt=on colour.jersey=4``; ``everything``
shows every shape (the toolkit's view before phase 9). `ModelVariants.parse` reads it,
`Choice.text` writes it.
"""

from __future__ import annotations

import random as _random
import re
from dataclasses import dataclass, field

from ..errors import Dr2Error

ZOMBIE_ARCHIVE = "data/models/zombies.big/"     # crowd zombies: always classified
DEFAULT_BIT = 0x1000                            # the '*' record: "matched nothing else"


# --- the game's classifier --------------------------------------------------------------

def pattern_matches(pattern: str, name: str) -> bool:
    """The game's matcher (CZ ``sub_82795420``): any comma-separated alternative that is
    a prefix of ``name``; ``*`` ends an alternative; case-sensitive."""
    for alt in pattern.split(","):
        prefix = alt.split("*", 1)[0]
        if prefix and name.startswith(prefix):
            return True
    return False


_MISPLACED = re.compile(r"^(.+?)Shape(\d)Deformed")


def corrected_name(name: str) -> str | None:
    """``<part>Shape<digit>Deformed…`` → ``<part><digit>ShapeDeformed…`` (the name the
    artist meant), or None if the name has no misplaced digit. Same rule as the CZ
    recomp's ``runtime/cpu/zombie_variant_names.cpp``."""
    m = _MISPLACED.match(name)
    if m is None:
        return None
    return f"{m.group(1)}{m.group(2)}ShapeDeformed{name[m.end():]}"


class Classifier:
    """Shape name → the game's 64-bit group bits, from a profile's ``[variants]``."""

    def __init__(self, groups):
        self.groups: list[tuple[int, str]] = [(int(m, 16) if isinstance(m, str) else int(m), p)
                                              for m, p in groups]
        if not self.groups:
            raise Dr2Error("the game profile has no [variants] group table")

    @classmethod
    def for_game(cls, game: str) -> "Classifier":
        from ..profiles import load_profile
        return cls(load_profile(game).variants.get("groups", []))

    def bits(self, name: str) -> int:
        """OR of every matching record; the ``*`` record only if none matches (as the
        game's ``sub_827A2E10``)."""
        out = default = 0
        for mask, pattern in self.groups:
            if pattern.startswith("*"):
                default = mask
            elif pattern_matches(pattern, name):
                out |= mask
        return out or default


# --- slots, on/off parts, prop states ---------------------------------------------------

@dataclass(frozen=True)
class Slot:
    """A numbered choice: one of ``count`` bits starting at ``first`` (or none)."""
    key: str
    label: str
    first: int
    count: int
    on_by_default: bool          # default: the first number present (True) or none

    def bit(self, n: int) -> int:
        return self.first << (n - 1)

    @property
    def all_bits(self) -> int:
        return sum(self.bit(n) for n in range(1, self.count + 1))

    def number(self, bits: int) -> int | None:
        """Which number of this slot ``bits`` carry (the lowest), or None."""
        for n in range(1, self.count + 1):
            if bits & self.bit(n):
                return n
        return None


@dataclass(frozen=True)
class Toggle:
    """An on/off part: shapes with ``bit`` show only when it is on."""
    key: str
    label: str
    bit: int
    default: bool
    hint: str = ""


# The game's slot table (CZ 0x8208A2E0, CW 0x82084AE0) lists heads, headwear, shirts,
# trousers, skirt, feet and tall boots; head tumours are their own bits in the group
# table. Bits as in the profiles' group table (checked by tests against it).
SLOTS = (
    Slot("head", "Head", 0x10000, 5, True),
    Slot("tumour", "Head tumour", 0x200000, 4, True),
    Slot("headwear", "Headwear", 0x2000000, 5, True),
    Slot("shirt", "Shirt", 0x40000000, 6, True),
    Slot("pants", "Trousers", 0x2000000000, 7, True),
    Slot("skirt", "Skirt", 0x100000000000, 1, False),
    Slot("feet", "Feet", 0x200000000000, 7, True),
    Slot("tallboots", "Tall boots", 0x10000000000000, 1, False),
)
TOGGLES = (
    Toggle("caps", "Wound caps", 0x2, False,
           "the caps the game shows where a limb or the head came off"),
    Toggle("burnt", "Burnt", 0x8000, False, "the burnt look (a zombie set on fire)"),
    Toggle("gas", "Gas look", 0x4000, False),
    Toggle("bare_arms", "Bare arms", 0x2000, True, "the arms under short sleeves"),
    Toggle("glasses", "Glasses", 0x200, True),
    Toggle("chest_acc", "Chest accessories", 0x400, True),
    Toggle("backpack", "Backpack", 0x800, True),
    Toggle("shirt_tumour", "Shirt tumour", 0x1000000000, True),
)
SLOT = {s.key: s for s in SLOTS}
OPTIONAL_SLOTS = ("headwear", "tumour", "skirt", "tallboots")   # `random` may leave these off
TOGGLE = {t.key: t for t in TOGGLES}


@dataclass(frozen=True)
class PropState:
    """A prop state kept as twin shapes: ``<twin>`` and ``<prefix><twin>`` /
    ``<twin><suffix>`` (names compared without their ``Shape…`` ending)."""
    key: str
    label: str
    prefix: str = ""
    suffix: str = ""

    def twin(self, stem: str) -> str | None:
        if self.prefix and stem.startswith(self.prefix) and len(stem) > len(self.prefix):
            return stem[len(self.prefix):]
        if self.suffix and stem.endswith(self.suffix) and len(stem) > len(self.suffix):
            return stem[:-len(self.suffix)]
        return None


# Found by name over every model of both games (2026-10-10): only the two slot machines
# keep states as shapes (other damaged props are separate files: cashregister_dmg.big).
PROP_STATES = (
    PropState("far", "Far-away copy", prefix="LOD_"),
    PropState("damaged", "Damaged", suffix="_dmg"),
    PropState("screen_win", "Win screen", suffix="Win"),
    PropState("screen_off", "Screen off", suffix="Off"),
)
PROP_STATE = {p.key: p for p in PROP_STATES}


def shape_stem(name: str) -> str:
    """A shape name without its ``Shape…`` ending (``slot_logo_dmgShape`` → ``slot_logo_dmg``)."""
    i = name.find("Shape")
    return name[:i] if i > 0 else name


# --- a model's variants -----------------------------------------------------------------

@dataclass
class Part:
    """One shape of a model and what it belongs to."""
    index: int                   # the mesh's index in the scene
    name: str
    bits: int                    # the game's group bits (0 when the model isn't classified)
    group: str                   # "Head 2", "Burnt", "Damaged", "Always shown"…
    needs: tuple[str, ...] = ()  # prop states that must be on to show it
    hidden_by: tuple[str, ...] = ()   # prop states that hide it (its state twin is shown)
    misplaced: bool = False      # read with its digit moved (corrected_name)


@dataclass
class Choice:
    """One look: a number (or None) per slot, on/off parts, prop states, colours."""
    slots: dict[str, int | None] = field(default_factory=dict)
    toggles: dict[str, bool] = field(default_factory=dict)
    states: dict[str, bool] = field(default_factory=dict)
    colours: dict[str, int] = field(default_factory=dict)   # key → 0 own, N = Nth choice
    everything: bool = False     # show every shape (the pre-phase-9 view)

    def text(self) -> str:
        """``head=2 shirt=1 headwear=none burnt=on colour.jersey=4`` (`ModelVariants.parse`)."""
        if self.everything:
            return "everything"
        out = [f"{k}={'none' if v is None else v}" for k, v in self.slots.items()]
        out += [f"{k}={'on' if v else 'off'}" for k, v in self.toggles.items()]
        out += [f"{k}={'on' if v else 'off'}" for k, v in self.states.items()]
        out += [f"colour.{k}={v}" for k, v in self.colours.items() if v]   # 0: own colours
        return " ".join(out)


@dataclass
class ColourChoice:
    """A material's colour choices: value sets it can swap its own for."""
    key: str                     # "jersey" (the own name after "_mtl_")
    own: str                     # "zombie_skinny_mtl_jersey.pdv"
    materials: list[int]         # material indices using that value set
    options: list[str]           # choice N is options[N - 1]
    listed: bool | None = None   # named by the game's list (None: the game has no list)


@dataclass
class ModelVariants:
    """What a model can show: its slots, on/off parts, prop states and colour choices."""
    source: str
    zombie: bool                 # classified with the game's table
    parts: list[Part]
    slots: dict[str, list[int]]  # slot key → numbers present
    toggles: list[str]           # on/off parts present
    states: list[str]            # prop states present
    colours: list[ColourChoice] = field(default_factory=list)

    @property
    def has_choices(self) -> bool:
        return bool(self.slots or self.toggles or self.states or self.colours)

    @property
    def misplaced(self) -> list[Part]:
        return [p for p in self.parts if p.misplaced]

    # choices
    def default(self) -> Choice:
        """The default look: the first number of each slot (skirt and tall boots: none),
        accessories on, no wound caps, not burnt, prop states off, own colours."""
        return Choice(
            slots={k: (nums[0] if SLOT[k].on_by_default else None) for k, nums in self.slots.items()},
            toggles={k: TOGGLE[k].default for k in self.toggles},
            states={k: False for k in self.states},
            colours={c.key: 0 for c in self.colours})

    def random(self, rng: _random.Random | None = None) -> Choice:
        """Any look: a number per slot (none too, for optional slots), each colour."""
        rng = rng or _random.Random()
        c = self.default()
        for k, nums in self.slots.items():
            optional = k in OPTIONAL_SLOTS or not SLOT[k].on_by_default
            c.slots[k] = rng.choice(nums + ([None] if optional else []))
        for col in self.colours:
            c.colours[col.key] = rng.randint(0, len(col.options))
        return c

    def everything(self) -> Choice:
        c = self.default()
        c.everything = True
        return c

    def parse(self, text: str | None, base: Choice | None = None) -> Choice:
        """A choice from text (``head=2,shirt=1 colour.jersey=4``; commas or spaces), on
        top of ``base`` (default: `default`). ``default`` and ``everything`` are words
        too. Unknown keys or numbers the model hasn't got raise `Dr2Error` naming what
        it has."""
        c = base or self.default()
        c = Choice(dict(c.slots), dict(c.toggles), dict(c.states), dict(c.colours), c.everything)
        for word in re.split(r"[\s,]+", (text or "").strip()):
            if not word:
                continue
            if word in ("everything", "all"):
                c.everything = True
                continue
            if word == "default":
                c = self.default()
                continue
            if "=" not in word:
                raise Dr2Error(f"{word!r}: expected key=value ({self.keys_text()})")
            k, v = (s.strip().lower() for s in word.split("=", 1))
            if k in self.slots:
                if v in ("none", "off", "0"):
                    c.slots[k] = None
                else:
                    try:
                        n = int(v)
                    except ValueError:
                        raise Dr2Error(f"{k}={v}: a number or none") from None
                    if n not in self.slots[k]:
                        raise Dr2Error(f"{k}={n}: this model has {SLOT[k].label.lower()} "
                                       f"{', '.join(map(str, self.slots[k]))}")
                    c.slots[k] = n
            elif k in self.toggles or k in self.states:
                if v not in ("on", "off", "yes", "no", "1", "0", "true", "false"):
                    raise Dr2Error(f"{k}={v}: on or off")
                (c.toggles if k in self.toggles else c.states)[k] = v in ("on", "yes", "1", "true")
            elif k.startswith("colour.") or k.startswith("color."):
                key = k.split(".", 1)[1]
                col = next((x for x in self.colours if x.key == key), None)
                if col is None:
                    raise Dr2Error(f"{k}: no such colour choice ({self.keys_text()})")
                n = 0 if v in ("own", "default") else int(v) if v.isdigit() else -1
                if not 0 <= n <= len(col.options):
                    raise Dr2Error(f"{k}={v}: 0 (own) to {len(col.options)}")
                c.colours[key] = n
            else:
                raise Dr2Error(f"{k}: this model has no such choice ({self.keys_text()})")
            c.everything = False
        return c

    def keys_text(self) -> str:
        keys = [f"{k}={'|'.join(map(str, v))}|none" for k, v in self.slots.items()]
        keys += [f"{k}=on|off" for k in self.toggles + self.states]
        keys += [f"colour.{c.key}=0-{len(c.options)}" for c in self.colours]
        return "choices: " + (" ".join(keys) if keys else "none")

    # what shows
    def hide_mask(self, choice: Choice) -> int:
        """The game's 64-bit hide mask for ``choice`` (bits of every slot number not
        chosen, of every on/off part switched off). Prop states are not in the mask."""
        if not self.zombie or choice.everything:
            return 0
        mask = 0
        for slot in SLOTS:
            if slot.key in self.slots:
                n = choice.slots.get(slot.key)
                mask |= slot.all_bits & ~(slot.bit(n) if n else 0)
        for t in TOGGLES:
            if t.key in self.toggles and not choice.toggles.get(t.key, t.default):
                mask |= t.bit
        return mask

    def choice_from_mask(self, mask: int) -> Choice:
        """The choice a game hide mask stands for (read from the recomp, say): per slot
        the lowest number the model has whose bit is clear (none if all are set), each
        on/off part on when its bit is clear."""
        c = self.default()
        for k, nums in self.slots.items():
            free = [n for n in nums if not mask & SLOT[k].bit(n)]
            c.slots[k] = free[0] if free else None
        for k in self.toggles:
            c.toggles[k] = not mask & TOGGLE[k].bit
        return c

    def shown_by_mask(self, mask: int) -> list[bool]:
        """Per part: does the game draw it under hide mask ``mask`` (``bits & mask == 0``)?"""
        return [not (p.bits & mask) for p in self.parts]

    def shown(self, choice: Choice) -> list[bool]:
        """Per part (scene mesh order): does ``choice`` show it?"""
        if choice.everything:
            return [True] * len(self.parts)
        mask = self.hide_mask(choice)
        out = []
        for p in self.parts:
            ok = not (p.bits & mask)
            ok = ok and all(choice.states.get(s, False) for s in p.needs)
            ok = ok and not any(choice.states.get(s, False) for s in p.hidden_by)
            out.append(ok)
        return out

    def colour_options(self, choice: Choice) -> dict[int, str]:
        """Material index → the value-set name ``choice`` swaps in (only changed ones)."""
        out = {}
        for col in self.colours:
            n = choice.colours.get(col.key, 0)
            if n:
                for m in col.materials:
                    out[m] = col.options[n - 1]
        return out

    def describe(self, choice: Choice | None = None) -> list[str]:
        """Plain lines for ``info.txt`` and ``dr2 variants``."""
        lines = []
        for k, nums in self.slots.items():
            lines.append(f"{SLOT[k].label} ({k}): {', '.join(map(str, nums))} or none")
        for k in self.toggles:
            t = TOGGLE[k]
            lines.append(f"{t.label} ({k}): on/off" + (f", {t.hint}" if t.hint else ""))
        for k in self.states:
            lines.append(f"{PROP_STATE[k].label} ({k}): on/off")
        for col in self.colours:
            listed = {True: "", False: " (not in the game's list)", None: " (by name)"}[col.listed]
            lines.append(f"Colour {col.key}: own + {len(col.options)} choices{listed} "
                         f"({col.own})")
        for p in self.misplaced:
            lines.append(f"note: {p.name} has its number after 'Shape'; the game reads it "
                         f"without (read here as {corrected_name(p.name)})")
        if choice is not None:
            lines.append(f"chosen: {choice.text() or '(no choices)'}")
            if self.zombie and not choice.everything:
                lines.append(f"the game's hide mask for it: {self.hide_mask(choice):#018x}")
        return lines


def _group_label(bits: int) -> str:
    """The one group a classified shape is filed under (most specific first)."""
    for key in ("caps", "burnt", "gas", "shirt_tumour"):
        if bits & TOGGLE[key].bit:
            return TOGGLE[key].label
    for key in ("tumour", "headwear", "head", "shirt", "pants", "skirt", "feet", "tallboots"):
        n = SLOT[key].number(bits)
        if n is not None:
            return SLOT[key].label + ("" if SLOT[key].count == 1 else f" {n}")
    for key in ("glasses", "chest_acc", "backpack", "bare_arms"):
        if bits & TOGGLE[key].bit:
            return TOGGLE[key].label
    return "Always shown"


def model_variants(scene, game: str = "cz", classifier: Classifier | None = None) -> ModelVariants:
    """A scene's variants: every mesh's group, the slots and parts present, prop states.
    Colour choices need the game data: `colour_choices` fills ``.colours``."""
    cls = classifier or Classifier.for_game(game)
    names = [m.name for m in scene.meshes]
    bits, misplaced = [], []
    for n in names:
        fixed = corrected_name(n)
        bits.append(cls.bits(fixed or n))
        misplaced.append(fixed is not None and cls.bits(fixed) != cls.bits(n))
    numbered = any(SLOT[k].number(b) is not None for b in bits for k in SLOT)
    zombie = numbered or (scene.source or "").lower().replace("\\", "/").find(ZOMBIE_ARCHIVE) >= 0
    if not zombie:
        bits = [0] * len(names)
        misplaced = [False] * len(names)
    slots: dict[str, list[int]] = {}
    toggles: list[str] = []
    for s in SLOTS:
        nums = sorted({s.number(b & s.all_bits) for b in bits if b & s.all_bits})
        if nums:
            slots[s.key] = nums
    for t in TOGGLES:
        if any(b & t.bit for b in bits):
            toggles.append(t.key)
    # prop states: twin shapes, by name
    stems = [shape_stem(n) for n in names]
    have = set(stems)
    needs: list[list[str]] = [[] for _ in names]
    hidden_by: list[list[str]] = [[] for _ in names]
    states: list[str] = []
    for ps in PROP_STATES:
        for i, st in enumerate(stems):
            twin = ps.twin(st)
            if twin is not None and twin in have:
                needs[i].append(ps.key)
                for j, other in enumerate(stems):
                    if other == twin:
                        hidden_by[j].append(ps.key)
                if ps.key not in states:
                    states.append(ps.key)
    parts = []
    for i, n in enumerate(names):
        group = _group_label(bits[i]) if zombie else "Always shown"
        if needs[i]:
            group = " + ".join(PROP_STATE[k].label for k in needs[i])
        parts.append(Part(i, n, bits[i], group, tuple(needs[i]), tuple(hidden_by[i]),
                          misplaced[i]))
    return ModelVariants(scene.source or "", zombie, parts, slots, toggles, states)


# --- colour choices ---------------------------------------------------------------------

def colour_key(own: str) -> str:
    """``zombie_skinny_mtl_jersey.pdv`` → ``jersey``."""
    stem = own.lower().removesuffix(".pdv")
    return stem.split("_mtl_", 1)[1] if "_mtl_" in stem else stem


def colour_rule(own: str, bank_names) -> list[str]:
    """The bank's value sets named ``<own>N.pdv`` or ``<own>_varN.pdv``, by N."""
    stem = re.escape(own.lower().removesuffix(".pdv"))
    pat = re.compile(stem + r"(?:_var)?(\d+)\.pdv")
    hits = []
    for n in bank_names:
        m = pat.fullmatch(n.lower())
        if m:
            hits.append((int(m.group(1)), n))
    return [n for _, n in sorted(hits)]


def parse_colour_list(text: str) -> dict[str, dict[str, list[str]]]:
    """``zombie_pdv_variations.txt``: ``[model]`` sections of ``own.pdv=alt1.pdv,alt2.pdv,``
    → {model: {own: [alts]}} (all lower case)."""
    out: dict[str, dict[str, list[str]]] = {}
    section = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].lower()
            out.setdefault(section, {})
        elif "=" in line and section is not None:
            own, alts = line.split("=", 1)
            out[section][own.strip().lower()] = [a.strip().lower() for a in alts.split(",")
                                                 if a.strip()]
    return out


class ColourBank:
    """One game's colour value sets (``data/shaders/*-sc.big``) and its list file."""

    def __init__(self, tree, game: str = "cz"):
        self.tree, self.game = tree, game
        self._names: dict[str, str] | None = None
        self._list: dict | None = None

    def names(self) -> dict[str, str]:
        """Value-set name (lower case) → vpath of its ``.scv``."""
        if self._names is None:
            from ..formats.shader import ValueSet
            self._names = {}
            folder = self.tree.root / "data" / "shaders"
            for f in sorted(folder.glob("*-sc.big")) if folder.is_dir() else []:
                vp = f"data/shaders/{f.name}"
                for e in self.tree.open_archive(vp).entries:
                    try:
                        vs = ValueSet.parse(e.data(), e.name)
                    except Dr2Error:
                        continue
                    self._names.setdefault(vs.name.lower(), f"{vp}/{e.name}")
        return self._names

    def listed(self) -> dict | None:
        """The game's list (`parse_colour_list`), {} for an empty one, None if absent."""
        if self._list is None:
            from ..profiles import load_profile
            self._list = {}
            found = False
            for vp in load_profile(self.game).variants.get("colour_lists", []):
                try:
                    text = self.tree.resolve(vp).data().decode("latin-1")
                except Dr2Error:
                    continue
                found = True
                for k, v in parse_colour_list(text).items():
                    self._list.setdefault(k, {}).update(v)
            if not found:
                self._list = None
        return self._list

    def valueset(self, name: str):
        """The `ValueSet` called ``name`` (a ``.pdv`` name), or None."""
        from ..formats.shader import ValueSet
        vp = self.names().get(name.lower())
        if vp is None:
            return None
        return ValueSet.parse(self.tree.resolve(vp).data(), vp)


def colour_choices(scene, bank: ColourBank) -> list[ColourChoice]:
    """The model's materials that have colour choices, one entry per own value set."""
    from .material import material_valueset
    names = list(bank.names())
    listed = bank.listed()
    model = (scene.source or "").replace("\\", "/").rsplit("/", 1)[-1].lower().removesuffix(".big")
    by_own: dict[str, ColourChoice] = {}
    for i, m in enumerate(scene.materials):
        vs = material_valueset(scene, m)
        if vs is None:
            continue
        own = vs.name.lower()
        if own in by_own:
            by_own[own].materials.append(i)
            continue
        opts = colour_rule(own, names)
        if not opts:
            continue
        if listed is None or not listed:
            flag = None
        else:
            flag = own in listed.get(model, {})
        by_own[own] = ColourChoice(colour_key(own), own, [i], opts, flag)
    # two own names with the same key (rare): make keys unique
    seen: dict[str, int] = {}
    for c in by_own.values():
        if c.key in seen:
            seen[c.key] += 1
            c.key = f"{c.key}_{seen[c.key]}"
        else:
            seen[c.key] = 1
    return list(by_own.values())


def read_variants(tree, scene, game: str, bank: ColourBank | None = None) -> ModelVariants:
    """`model_variants` plus the colour choices (needs the game data)."""
    mv = model_variants(scene, game)
    try:
        mv.colours = colour_choices(scene, bank or ColourBank(tree, game))
    except Dr2Error:
        mv.colours = []
    return mv

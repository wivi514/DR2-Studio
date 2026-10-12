"""Weapon kinds and particle effects as data, for the weapon wizard (phase 13 step 2).

Why data: what makes a weapon swing, burn or sparkle is plain ``items.txt`` keys
(docs/formats.md §Weapons), measured in game in phase 12. The wizard (`mods.newweapon`,
Studio's *New weapon…*, ``dr2 mod new-weapon``) offers them by name, from two files:

* ``weapon_kinds.toml``: each kind of weapon, and per game the game weapon a new one
  starts from (its pack, its block, so its moves). `kinds`.
* ``effects.toml``: the effect table's names (number = position + 1, made by
  ``tools/effect_table.py`` from the executables), groups for people ("Ice and snow",
  "Fire"…), what was checked in game, the elements (fire, freeze, shock) and the effect
  slots of a weapon. `effects`, `ELEMENTS`, `SLOTS`.

An effect's name says a little about it (``snowtrail_wpn_bs_1``: what, then the family:
``wpn`` weapon, ``bld`` blood, ``env`` level, ``elm`` element, ``exp`` explosion, ``chr``
character, ``veh`` vehicle; then letters and a number). From the game's own use, a ``c``
in the letters marks effects that keep going (the Tiki Torch's flame, ``c_2``) and a ``b``
one-off bursts (blood on a hit, ``bs``): `Effect.loops` is that **reading of the name**,
not a measurement ❓. ``s``/``m``/``l`` read as small / medium / large the same way.
"""

from __future__ import annotations

import re
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import Dr2Error

HERE = Path(__file__).parent
EFFECTS_FILE = HERE / "effects.toml"
KINDS_FILE = HERE / "weapon_kinds.toml"
EFFECT_KEYS = re.compile(r"^(EffectOnVictim|EffectOnImpact|EffectOnWeapon|PyroEffect)\d+$|"
                         r"^ThrowEffectOn(Victim|Impact|Weapon)$", re.I)

_cache: dict = {}


def _load(path: Path) -> dict:
    if path not in _cache:
        with open(path, "rb") as f:
            _cache[path] = tomllib.load(f)
    return _cache[path]


# --- kinds ------------------------------------------------------------------------------

@dataclass
class Kind:
    """A kind of weapon (``weapon_kinds.toml``)."""
    id: str
    name: str
    hands: int
    note: str
    source: dict = field(default_factory=dict)      # game -> items.txt block name

    def template(self, game: str) -> str:
        """The game weapon a new one of this kind starts from in ``game``."""
        if game not in self.source:
            raise Dr2Error(f"{self.name}: no weapon of this kind in {game.upper()}")
        return self.source[game]


def kinds(game: str | None = None) -> list[Kind]:
    """Every kind (only those ``game`` has, when given), in the file's order."""
    out = [Kind(k["id"], k["name"], int(k.get("hands", 1)), k.get("note", ""),
                dict(k.get("from", {}))) for k in _load(KINDS_FILE)["kind"]]
    return [k for k in out if game is None or game in k.source]


def kind(kind_id: str) -> Kind:
    for k in kinds():
        if k.id == kind_id.lower():
            return k
    raise Dr2Error(f"no weapon kind {kind_id!r} (dr2 mod new-weapon --list-kinds)")


# --- effects ----------------------------------------------------------------------------

@dataclass
class Effect:
    """One effect of the executable's table."""
    number: int                    # what items.txt writes (1-based)
    name: str
    group: str                     # a group id of effects.toml
    family: str                    # the name's second part: wpn, bld, env…
    loops: bool | None             # read from the name ("c"): keeps going ❓
    size: str                      # "small" / "medium" / "large" / "" (from the name ❓)
    tested: str = ""               # what was seen in game
    used_by: list[str] = field(default_factory=list)   # "Item (key)" of the game

    @property
    def label(self) -> str:
        return f"{self.number}: {self.name}"


def names(game: str) -> list[str]:
    """The effect table of ``game``: names in number order (number = index + 1)."""
    data = _load(EFFECTS_FILE)
    n = data["names"]
    if game == "cz":
        return n[:data["cz_shared"]] + list(data["cz_own"])
    if game == "cw":
        return list(n)
    raise Dr2Error(f"unknown game {game!r}")


def groups() -> list[tuple[str, str]]:
    """(group id, name) in the list's order."""
    return [(g["id"], g["name"]) for g in _load(EFFECTS_FILE)["groups"]]


def _group_of(name: str) -> str:
    low = name.lower()
    fam = low.split("_")[1] if "_" in low else ""
    for g in _load(EFFECTS_FILE)["groups"]:
        if fam in g.get("category", []) or any(w in low for w in g["words"]):
            return g["id"]
    return "other"


def _reading(name: str) -> tuple[str, bool | None, str]:
    parts = name.lower().split("_")
    family = parts[1] if len(parts) > 1 else ""
    letters = parts[2] if len(parts) > 2 and parts[2].isalpha() else ""
    loops = True if "c" in letters else (False if "b" in letters else None)
    size = {"s": "small", "m": "medium", "l": "large"}.get(letters[-1:], "") if letters else ""
    return family, loops, size


def usage(doc) -> dict[int, list[str]]:
    """effect number → ``"Item (Key)"`` for every item of a parsed ``items.txt``."""
    out: dict[int, list[str]] = defaultdict(list)
    for b in doc.walk():
        seen = set()
        for p in b.props:
            if EFFECT_KEYS.match(p.key):
                try:
                    n = int(p.value)
                except ValueError:
                    continue
                key = re.sub(r"\d+$", "", p.key)
                if n > 0 and (n, key) not in seen:
                    seen.add((n, key))
                    out[n].append(f"{b.name} ({key})")
    return out


def effects(game: str, items_doc=None) -> list[Effect]:
    """Every effect of ``game``'s table, with what was tested and (given the parsed
    ``items.txt``) which items use it."""
    tested = {int(k): v for k, v in _load(EFFECTS_FILE).get("tested", {}).items()}
    used = usage(items_doc) if items_doc is not None else {}
    out = []
    for i, n in enumerate(names(game)):
        fam, loops, size = _reading(n)
        out.append(Effect(i + 1, n, _group_of(n), fam, loops, size, tested.get(i + 1, ""),
                          used.get(i + 1, [])))
    return out


def effect_number(game: str, value: str | int) -> int:
    """An effect given by number or by name → its number (0 = none)."""
    if value in (None, "", 0, "0", "none"):
        return 0
    table = names(game)
    try:
        n = int(value)
    except (TypeError, ValueError):
        low = str(value).lower()
        for i, name in enumerate(table):
            if name.lower() == low:
                return i + 1
        raise Dr2Error(f"no effect named {value!r} in {game.upper()} (dr2 effects -g {game})")
    if not 0 <= n <= len(table):
        raise Dr2Error(f"effect {n}: {game.upper()} has effects 1-{len(table)}")
    return n


# --- elements and slots -----------------------------------------------------------------

def elements() -> dict[str, dict]:
    """element id → {name, description, keys, child, checked} (``effects.toml``)."""
    return dict(_load(EFFECTS_FILE)["elements"])


def slots() -> dict[str, dict]:
    """slot id → {name, description, keys or condition, checked} (``effects.toml``)."""
    return dict(_load(EFFECTS_FILE)["slots"])

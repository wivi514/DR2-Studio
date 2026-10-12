"""What a mod needs to build and play: ``[requires]``, ``requirements.json``, ``REQUIRES.txt``
(phase 15, docs/phase15-kickoff.md §Requirements).

Why: a mod made with the toolkit holds recipes, not game data (LICENSE), so a mod that
uses Case West's things in Case Zero can only be **built** on a computer that has Case
West's data too. Some mods also need other mods, change what a save holds, or change
the world that every co-op player must see the same way. A launcher (XenonLive, which
has no mod support yet) or another player's toolkit needs to know that *before* it
builds or starts anything, so every mod says it in one small file.

Three places, one meaning:

* ``[requires]`` in ``mod.toml``: what the modder wrote. Every key is optional; the toolkit
  fills the rest from what the mod contains (`infer`)::

      [requires]
      games = ["cz", "cw"]          # game data needed to build it (recipes from Case West)
      play = ["cz"]                 # the games it runs in (default: [mod] games)
      toolkit = ">=0.1.0"           # the dr2kit version that can build it
      mods = ["frostmourne>=1.0"]   # other mods it needs, with versions
      saves = "needs-mod"           # "safe" | "needs-mod"
      coop = "all-players"          # "all-players" | "host-only" | "local"

* ``requirements.json``: the same, machine-readable, with the games' **title ids**
  (CZ ``58410A8D``, CW ``58410B00``) and a ``content_hash`` (sha1 of the mod's files) so
  two players can compare their mods before a co-op game. Written at the root of every
  ``.dr2mod`` (`library.pack`) and kept in the build's ``dr2kit-build.json``.
* ``REQUIRES.txt``: the same in plain words, for people.

What the toolkit works out by itself (`infer`):

* ``games``: the games it plays in, plus every game a recipe copies from
  (``"from": "cw"`` in an ``add/…copy.json``: `dr2kit.mods.crossgame`).
* ``saves``: ``needs-mod`` as soon as the mod **adds** anything (new archive entries or
  files under ``add/``, or blocks added by an ``.edits.json``): measured in phase 11, a
  save made with a mod's own mission crashes without the mod, so anything new is taken
  the same way (conservative: a save may name it). Replacements and changed keys:
  ``safe``.
* ``coop``: ``local`` when the mod only changes how things look or sound (textures,
  models, sounds, text), else ``all-players`` (anything that changes the world: levels,
  items, buildings, effects that hit, new things). ``host-only`` is never guessed: the
  modder writes it.

`check` says what is missing on this computer (game data, mods, versions); the build
(`mods.build.plan_mods`) refuses a mod whose needs aren't met and says why.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..profiles import GAME_IDS, load_profile
from .manifest import EDITS_EXT, Mod, ModError

FORMAT = "dr2kit-requires/1"
JSON_NAME = "requirements.json"
TEXT_NAME = "REQUIRES.txt"
GENERATED = (JSON_NAME, TEXT_NAME, "dr2kit-build.json")   # left out of content_hash
SAVES = ("safe", "needs-mod")
COOP = ("all-players", "host-only", "local")
LOOKS_ONLY = ("texture-png", "model-glb", "audio", "strings")   # coop "local" kinds
_SPEC = re.compile(r"^\s*([a-z0-9][a-z0-9_.-]*?)\s*(>=|<=|==|!=|>|<|=)?\s*([0-9][0-9a-z.]*)?\s*$",
                   re.I)


@dataclass
class Requirements:
    """What one mod needs (module docstring). ``written`` holds the keys the modder set
    in ``[requires]`` (they win over what `infer` finds)."""
    id: str
    version: str
    games: list[str]
    play: list[str]
    toolkit: str
    sources: list[str] = field(default_factory=list)   # games its recipes copy from
    mods: list[tuple[str, str]] = field(default_factory=list)   # (mod id, ">=1.0" or "")
    saves: str = "safe"
    coop: str = "local"
    content_hash: str = ""
    written: tuple[str, ...] = ()

    def to_json(self) -> dict:
        """The ``requirements.json`` object."""
        return {"format": FORMAT, "id": self.id, "version": self.version,
                "play": self.play,
                "games": {g: load_profile(g).title_id for g in self.games},
                "built_from": self.sources,
                "mods": [{"id": i, "version": v} for i, v in self.mods],
                "toolkit": self.toolkit, "saves": self.saves, "coop": self.coop,
                "content_hash": self.content_hash}

    def to_text(self) -> str:
        """``REQUIRES.txt``: the same in plain words."""
        names = {g: load_profile(g).name for g in GAME_IDS}
        lines = [f"{self.id} {self.version}: what this mod needs", ""]
        lines.append("Plays in: " + ", ".join(names[g] for g in self.play))
        need = ", ".join(f"{names[g]} ({load_profile(g).title_id})" for g in self.games)
        lines.append(f"Games involved: {need}")
        other = [g for g in self.sources]
        if other:
            lines.append("Made from " + ", ".join(names[g] for g in other) + "'s files: "
                         "you need that game's data on your computer too (the mod is "
                         "built from your own copy)")
        if self.mods:
            lines.append("Other mods it needs: " + ", ".join(f"{i} {v}".strip()
                                                             for i, v in self.mods))
        lines.append(f"Toolkit: dr2kit {self.toolkit}")
        lines.append("Saves: " + ("saves made with this mod need it to load"
                                  if self.saves == "needs-mod" else
                                  "saves made with it still load without it"))
        lines.append("Co-op: " + {"all-players": "every player needs it, the same version",
                                  "host-only": "only the host needs it",
                                  "local": "only changes how things look or sound: each "
                                           "player can choose"}[self.coop])
        if self.content_hash:
            lines.append(f"Content hash: {self.content_hash}")
        return "\n".join(lines) + "\n"


def parse_spec(text: str) -> tuple[str, str]:
    """``"frostmourne>=1.0"`` -> ``("frostmourne", ">=1.0")``; a bare id needs any version."""
    m = _SPEC.match(str(text))
    if not m or (m.group(2) and not m.group(3)):
        raise ModError(f"[requires] mods: {text!r} is not a mod id with an optional version "
                       f"(\"other-mod\", \"other-mod>=1.2\")")
    op = m.group(2) or ("==" if m.group(3) else "")
    return m.group(1).lower(), f"{'==' if op == '=' else op}{m.group(3) or ''}"


def _version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v.split(".dev")[0])[:4]) or (0,)


def version_ok(have: str, spec: str) -> bool:
    """Is version ``have`` within ``spec`` (``">=1.0"``, ``"==2"``, ``""`` = any)?"""
    if not spec:
        return True
    m = re.match(r"^(>=|<=|==|!=|>|<)(.+)$", spec.strip())
    if not m:
        return True
    a, b = _version(have), _version(m.group(2))
    n = max(len(a), len(b))
    a, b = a + (0,) * (n - len(a)), b + (0,) * (n - len(b))
    return {">=": a >= b, "<=": a <= b, "==": a == b, "!=": a != b, ">": a > b,
            "<": a < b}[m.group(1)]


def content_hash(root: Path) -> str:
    """sha1 over every file of a mod folder (path and bytes, sorted), leaving out hidden
    files and what the toolkit generates (``GENERATED``)."""
    h = hashlib.sha1()
    for p in sorted(Path(root).rglob("*")):
        rel = p.relative_to(root)
        if not p.is_file() or any(x.startswith(".") for x in rel.parts) or \
                p.name in GENERATED:
            continue
        h.update(rel.as_posix().encode("utf-8") + b"\0")
        h.update(hashlib.sha1(p.read_bytes()).digest())
    return h.hexdigest()


def recipe_sources(mod: Mod) -> set[str]:
    """Games the mod's recipes copy from (``"from"`` in ``add/…copy.json``)."""
    out = set()
    for rel, src in mod.added():
        if not rel.lower().endswith(".copy.json"):
            continue
        try:
            g = json.loads(src.read_text("utf-8")).get("from")
        except (ValueError, OSError):
            continue
        if g:
            out.add(str(g).lower())
    return out


def _adds_blocks(src: Path) -> bool:
    try:
        return bool(json.loads(src.read_text("utf-8")).get("add"))
    except (ValueError, OSError):
        return False


def infer(mod: Mod, with_hash: bool = False) -> Requirements:
    """``mod``'s requirements: ``[requires]`` as written, the rest worked out from what the
    mod contains (module docstring)."""
    from .. import __version__
    from .build import _kind_of
    w = dict(mod.requires)
    kinds = {_kind_of(rel)[0] for rel, _ in mod.files()}
    added = mod.added()
    adds = bool(added) or any(_adds_blocks(src) for rel, src in mod.files()
                              if rel.lower().endswith(EDITS_EXT))
    play = [str(g).lower() for g in w.get("play", mod.games)]
    if isinstance(w.get("play"), str):
        play = [w["play"].lower()]
    src = recipe_sources(mod) | ({str(g).lower() for g in w.get("games", ())} - set(play))
    want = set(play) | src
    games = [g for g in GAME_IDS if g in want] + sorted(want - set(GAME_IDS))
    sources = [g for g in GAME_IDS if g in src] + sorted(src - set(GAME_IDS))
    bad = [g for g in games + play if g not in GAME_IDS]
    if bad:
        raise ModError(f"{mod.id}: [requires] names unknown games {bad} (known: "
                       f"{list(GAME_IDS)})")
    mods = [parse_spec(s) for s in w.get("mods", ())]
    saves = str(w.get("saves", "needs-mod" if adds else "safe"))
    coop = str(w.get("coop", "local" if not added and kinds <= set(LOOKS_ONLY)
                     else "all-players"))
    if saves not in SAVES:
        raise ModError(f"{mod.id}: [requires] saves must be one of {list(SAVES)}")
    if coop not in COOP:
        raise ModError(f"{mod.id}: [requires] coop must be one of {list(COOP)}")
    base = ".".join(str(x) for x in _version(__version__)[:3])
    return Requirements(id=mod.id, version=mod.version, games=games, play=play,
                        sources=sources, toolkit=str(w.get("toolkit", f">={base}")), mods=mods, saves=saves,
                        coop=coop, content_hash=content_hash(mod.root) if with_hash else "",
                        written=tuple(sorted(w)))


def available_games() -> dict[str, bool]:
    """Which games' data this computer has (`profiles.locate`)."""
    from ..errors import GameNotFoundError
    from ..profiles import locate
    out = {}
    for g in GAME_IDS:
        try:
            locate(g)
            out[g] = True
        except GameNotFoundError:
            out[g] = False
    return out


def check(req: Requirements, target: str | None = None, mods: dict[str, str] | None = None,
          games: dict[str, bool] | None = None) -> list[str]:
    """What this computer is missing to build ``req`` for ``target`` (None: for every
    game it plays in), in plain words ([] = nothing).

    ``mods``: id -> version of the mods switched on alongside it (None: don't check
    mods); ``games``: which games' data is here (default: `available_games`). A build
    for one game needs that game and the games the recipes copy from, not the other
    game a mod also supports."""
    from .. import __version__
    need = ([target] if target else list(req.play)) + [g for g in req.sources if g != target]
    out = []
    if target is not None and target not in req.play:
        out.append(f"{req.id} plays in " + ", ".join(load_profile(g).name for g in req.play)
                   + f", not {load_profile(target).name}")
    if any(g != target for g in need):
        games = available_games() if games is None else games
    for g in dict.fromkeys(need):
        if g != target and not games.get(g):
            prof = load_profile(g)
            why = ("it is made from its files" if g in req.sources else "it plays in it")
            out.append(f"{req.id} needs {prof.name}'s game data on this computer ({why}). "
                       f"Point the toolkit at it: Game folders… in Studio, or "
                       f"`dr2 games set {g} <folder>`")
    if mods is not None:
        for mid, spec in req.mods:
            if mid not in mods:
                out.append(f"{req.id} needs the mod {mid} {spec}".rstrip() +
                           " installed and switched on")
            elif not version_ok(mods[mid], spec):
                out.append(f"{req.id} needs {mid} {spec}, this library has {mods[mid]}")
    if not version_ok(__version__, req.toolkit):
        out.append(f"{req.id} needs dr2kit {req.toolkit}; this is {__version__}")
    return out


def summary(mod: Mod, switched_on: dict[str, str] | None = None) -> str:
    """A few lines of Markdown for Studio (mod manager, Install): what ``mod`` needs and
    what this computer lacks (bold), '' when it needs nothing special."""
    try:
        req = infer(mod)
    except ModError as e:
        return f"**{e}**"
    names = {g: load_profile(g).name for g in GAME_IDS}
    lines = []
    if req.sources:
        lines.append("Made from " + ", ".join(names[g] for g in req.sources)
                     + "'s files: needs that game's data to build.")
    if req.mods:
        lines.append("Needs the mods " + ", ".join(f"{i} {v}".strip() for i, v in req.mods)
                     + ".")
    if req.saves == "needs-mod":
        lines.append("Saves made with it need it.")
    if req.coop == "all-players":
        lines.append("Co-op: every player needs it.")
    for m in check(req, None, switched_on):
        lines.append(f"**Missing: {m}**")
    return "  \n".join(lines)


def write_files(req: Requirements, folder: Path) -> list[Path]:
    """Write ``requirements.json`` and ``REQUIRES.txt`` into ``folder``."""
    folder = Path(folder)
    a, b = folder / JSON_NAME, folder / TEXT_NAME
    a.write_text(json.dumps(req.to_json(), indent=1) + "\n", "utf-8")
    b.write_text(req.to_text(), "utf-8")
    return [a, b]


def read_json(path: Path) -> dict:
    """A ``requirements.json`` (a launcher's view of a mod); checks its format."""
    raw = json.loads(Path(path).read_text("utf-8"))
    if raw.get("format") != FORMAT:
        raise ModError(f"{path}: not a {FORMAT} file")
    return raw

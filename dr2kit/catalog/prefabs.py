"""Prefabs: ready-made things to add to a level, cloned from the game's own working
examples (phase 11 step 5, docs/phase11-kickoff.md §Plan 5).

Every "usable" thing of a level is a block of a text file (a save point is a
``cTriggerVolume`` with ``ActionType 4`` in ``waypoint_<level>.txt``, a workbench an item
placement…), never code. So a thing that behaves like the real one is a **copy of a real
one**, moved: `prefabs.toml` (data, per game: profiles are data) names, for each prefab,
the block it is cloned from in each game, which file the copy goes to, and its *anchor*,
the key whose position is where the modder clicks. `place` copies the block's keys, moves
every key holding ``x,y,z`` within `NEAR` metres of the anchor by the same offset (so a
save point's box, its action point and, in Case West, its corners in world space move
together) and adds it under a new name through `studio.maps_edit.LevelEditor` (saved
into the mod as ``.edits.json``, undoable).

Checked in game (CZ, 2026-10-11): a cloned save point saves, a workbench combines, the
road block (``MilitaryBarrier``) blocks the player. A prefab whose ``checked`` is empty
says so in the list.

**Your own prefabs** (``.dr2prefab``, plain JSON, `save_own` / `load_own`): the blocks of
something you configured (a placed item with its flags; several blocks), their file
(``level`` / ``waypoint``) and the anchor point, to place again or share. They live in the
user's data folder (`own_folder`) or anywhere.
"""

from __future__ import annotations

import json
import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import Dr2Error

DATA = Path(__file__).with_name("prefabs.toml")
NEAR = 15.0                       # metres: positions this close to the anchor move with it
ANGLE_KEYS = ("ActionActorRotation", "Rotation0", "Rotation1", "Rotation2", "Rotation3")
OWN_FORMAT = "dr2kit-prefab/1"
OWN_EXT = ".dr2prefab"


@dataclass
class Prefab:
    """One prefab (see `prefabs.toml`)."""
    id: str
    name: str
    group: str
    file: str                                   # "level" or "waypoint"
    description: str = ""
    anchor: str = "Location"
    checked: str = ""
    keys: dict = field(default_factory=dict)
    source: dict = field(default_factory=dict)  # game -> (file, block path)
    item: dict = field(default_factory=dict)    # game -> ItemName to put in the copy
    blocks: list = field(default_factory=list)  # own prefabs: [{cls, name, props}]
    origin: tuple[float, float, float] | None = None
    path: Path | None = None                    # an own prefab's file

    def for_game(self, game: str) -> bool:
        return bool(self.blocks) or bool(self.source.get(game))

    def file_for(self, script: str) -> str:
        return f"waypoint_{script}.txt" if self.file == "waypoint" else f"{script}.txt"


def load(path: Path = DATA) -> list[Prefab]:
    """The prefabs shipped with the toolkit."""
    with open(path, "rb") as f:
        raw = tomllib.load(f).get("prefab", [])
    out = []
    for p in raw:
        src = {g: tuple(v) for g, v in (p.get("source") or {}).items() if v}
        out.append(Prefab(p["id"], p["name"], p.get("group", "Other"), p.get("file", "level"),
                          p.get("description", ""), p.get("anchor", "Location"),
                          p.get("checked", ""), dict(p.get("keys") or {}), src,
                          dict(p.get("item") or {})))
    return out


def own_folder() -> Path:
    """Where the modder's own ``.dr2prefab`` files are kept."""
    from ..userdirs import data_dir
    return data_dir() / "prefabs"


def load_own(folder: Path | None = None) -> list[Prefab]:
    """Every ``.dr2prefab`` of ``folder`` (default `own_folder`); bad files are skipped."""
    folder = folder or own_folder()
    out = []
    for f in sorted(Path(folder).glob(f"*{OWN_EXT}")) if Path(folder).is_dir() else []:
        try:
            out.append(read_own(f))
        except Dr2Error:
            continue
    return out


def read_own(path: Path) -> Prefab:
    """One ``.dr2prefab`` file."""
    try:
        doc = json.loads(Path(path).read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise Dr2Error(f"{path}: not a prefab ({e})") from None
    if doc.get("format") != OWN_FORMAT or not isinstance(doc.get("blocks"), list):
        raise Dr2Error(f"{path}: not a {OWN_FORMAT} file")
    return Prefab(Path(path).stem, doc.get("name") or Path(path).stem, "My prefabs",
                  doc.get("file", "level"), doc.get("description", ""),
                  checked=doc.get("checked", ""), blocks=doc["blocks"],
                  origin=tuple(doc.get("origin") or (0, 0, 0)), path=Path(path))


def save_own(path: Path, name: str, file: str, blocks: list[dict],
             origin, description: str = "") -> Path:
    """Write a ``.dr2prefab``: ``blocks`` are ``{"cls", "name", "props": {…}}``."""
    path = Path(path)
    if path.suffix != OWN_EXT:
        path = path.with_suffix(OWN_EXT)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"format": OWN_FORMAT, "name": name, "description": description, "file": file,
           "origin": [round(float(c), 3) for c in origin], "blocks": blocks}
    path.write_text(json.dumps(doc, indent=1) + "\n", "utf-8")
    return path


def _vec(v: str):
    try:
        out = tuple(float(c) for c in v.split(","))
    except (ValueError, AttributeError):
        return None
    return out if len(out) == 3 else None


def moved(props: dict, anchor_at, target, yaw_deg: float = 0.0) -> dict:
    """``props`` with every position near ``anchor_at`` moved to stay where it was
    relative to ``target`` (turned ``yaw_deg`` about the up axis around it), a quaternion
    ``Rotation`` and the one-angle facings (`ANGLE_KEYS`: where Chuck faces at a save
    point, a spawn point's heading; radians, the same turn as `placed` reads them)
    turned by the same yaw."""
    from ..studio.maps_edit import fmt, yaw_quaternion
    out = dict(props)
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    for k, v in props.items():
        p = _vec(v)
        if p is None or math.dist(p, anchor_at) > NEAR:
            continue
        if math.dist(p, (0, 0, 0)) <= 5 and math.dist(anchor_at, (0, 0, 0)) > 20:
            continue                     # a corner in the thing's own space (CZ triggers)
        dx, dy, dz = (p[i] - anchor_at[i] for i in range(3))
        rx, rz = c * dx + s * dz, -s * dx + c * dz          # a turn about Y
        out[k] = fmt((target[0] + rx, target[1] + dy, target[2] + rz))
    for k in ANGLE_KEYS:                                # a facing in radians
        if yaw_deg and k in props:
            try:
                out[k] = f"{float(props[k]) + math.radians(yaw_deg):.3f}"
            except ValueError:
                pass
    q = props.get("Rotation", "")
    parts = q.split(",")
    if yaw_deg and len(parts) == 4:
        try:
            from ..studio.maps_edit import qmul
            out["Rotation"] = fmt(qmul(yaw_quaternion(yaw_deg), tuple(float(x) for x in parts)))
        except ValueError:
            pass
    return out


def place(editor, prefab: Prefab, game: str, script: str, at,
          yaw_deg: float = 0.0) -> tuple[list[str], list]:
    """Add ``prefab`` to the level of ``script`` at ``at`` through ``editor`` (a
    `studio.maps_edit.LevelEditor`). Returns the new blocks' names (in the file
    `Prefab.file_for` gives) and the editor's states of placed items (for the page)."""
    dest = prefab.file_for(script)
    if prefab.blocks:                                   # an own prefab
        specs = [(b["cls"], b.get("name") or b["cls"], dict(b.get("props") or {}))
                 for b in prefab.blocks]
        anchor_at = prefab.origin or (0.0, 0.0, 0.0)
    else:
        if not prefab.source.get(game):
            raise Dr2Error(f"the prefab {prefab.name!r} has no example in this game")
        src_file, src_path = prefab.source[game]
        b = editor.session(src_file).original.find(src_path)
        props = {p.key: p.value for p in b.props}
        if prefab.item.get(game):                     # another item at that spot: only
            props = {"ItemName": prefab.item[game],    # its name, place and turn
                     "Location": props.get("Location", "0,0,0"),
                     "Rotation": "0.000,0.000,0.000,1.000"}
        anchor_at = _vec(props.get(prefab.anchor, "")) or _vec(props.get("Location", ""))
        if anchor_at is None:
            raise Dr2Error(f"{src_path} has no {prefab.anchor} to place it by")
        specs = [(b.cls, b.name, props)]
    names = []

    def fn(doc):
        for cls, base, props in specs:
            name = editor.unique_name(dest, f"{prefab.id}_{base}" if not prefab.blocks else base)
            doc.add(None, cls, name, moved(props, anchor_at, at, yaw_deg))
            names.append(name)
    states = editor._change(dest, fn)
    return names, states

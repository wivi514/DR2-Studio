"""Edit a zone's buildings *inside a mod*: the session the Maps tab's editor uses for
level pieces (phase 11 step 4), the counterpart of `dr2kit.mods.leveledit.TextEdits`.

A `PieceEdits` opens one zone (``data/models/environment/prologue/prologue_z05.big``):
its shipped placement table (`formats.level.ZoneOrganization`) and the mod's
``ZONE_ORGANIZATION.big.pieces.json`` for it, if any (`formats.pieceedits`). Changes are
made to the `Edits` (`hide`, `place`, `copy`, `drop_copy`, `restore`), and `save` writes
them as the mod's file, or deletes it when nothing is left, so the mod always holds just
its changes. Undo and redo are snapshots of the edits (they are small).

`states` tells the page what each changed piece looks like now (`PieceState`): where it
is, hidden or not, and the copies.

**Whole buildings** (`convert.buildings`: a building's pieces and its collision shapes):
`place_building`, `hide_building`, `restore_building` and `copy_building` change every
part together, the building's first piece leading, and **move its collision with it**
(the ``collision`` edits; saved in a second file next to ``MERGED_COLLISION.big``).
Collision can be moved or hidden but not turned or resized (`formats.collision`), so a
turned or resized building keeps its collision as shipped, only moved: those calls
return a warning saying so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import math

from ..container.vpath import AssetTree, join, split
from ..errors import Dr2Error
from ..formats import pieceedits as pe
from ..formats.level import Placement, ZoneOrganization
from .manifest import REPLACE_DIR

UNDO_LIMIT = 200


def pieces_path(mod_dir: str | Path, zone_vpath: str, target: str = pe.TARGET) -> Path:
    """``<mod>/replace/<zone vpath>/ZONE_ORGANIZATION.big.pieces.json`` (or the
    collision's, ``MERGED_COLLISION.big.pieces.json``)."""
    return Path(mod_dir).joinpath(REPLACE_DIR, *split(zone_vpath), target + pe.EXT)


def read_organization(tree: AssetTree, zone_vpath: str) -> ZoneOrganization:
    """The zone's placement table as the game ships it."""
    arc = tree.open_archive(join(zone_vpath, pe.TARGET))
    return ZoneOrganization.from_entries({e.name: e.data() for e in arc.entries},
                                         join(zone_vpath, pe.TARGET))


@dataclass
class PieceState:
    """One piece (or a copy, ``name`` ``<piece>#<n>``) as the edits leave it, for the
    page. ``removed``: a copy that is gone."""
    zone: str                  # the zone's name (prologue_z05)
    name: str
    piece: str
    position: tuple | None = None
    rotation: tuple | None = None
    scale: tuple | None = None
    hidden: bool = False
    copy: bool = False
    removed: bool = False
    url: str | None = None     # set by the Maps view: the copy's model to load

    def to_dict(self) -> dict:
        return {"zone": self.zone, "name": self.name, "piece": self.piece,
                "position": self.position and list(self.position),
                "rotation": self.rotation and list(self.rotation),
                "scale": self.scale and list(self.scale), "hidden": self.hidden,
                "copy": self.copy, "removed": self.removed, "url": self.url}


@dataclass
class PieceEdits:
    """One mod's building edits of one zone (module docstring)."""
    mod_dir: Path
    zone_vpath: str
    original: ZoneOrganization
    edits: pe.Edits = field(default_factory=pe.Edits)
    _undo: list = field(default_factory=list)
    _redo: list = field(default_factory=list)
    tree: AssetTree | None = None
    game: str | None = None              # for the modder's building corrections
    _buildings: list | None = None
    _shapes: dict | None = None

    @classmethod
    def open(cls, mod_dir: str | Path, tree: AssetTree, zone_vpath: str) -> "PieceEdits":
        zone_vpath = tree.resolve(zone_vpath).vpath           # the game's letter case
        s = cls(Path(mod_dir), zone_vpath, read_organization(tree, zone_vpath), tree=tree)
        f = pieces_path(mod_dir, zone_vpath)
        if f.is_file():
            s.edits = pe.from_json(f.read_text("utf-8-sig"), f.name)
        c = pieces_path(mod_dir, zone_vpath, pe.COLLISION)
        if c.is_file():
            s.edits.collision = pe.from_json(c.read_text("utf-8-sig"), c.name).collision
        return s

    @property
    def zone(self) -> str:
        return split(self.zone_vpath)[-1].removesuffix(".big")

    # ---- what is placed ------------------------------------------------------------------

    def shipped(self, piece: str) -> Placement:
        for p in self.original.placements:
            if p.piece.lower() == piece.lower():
                return p
        raise Dr2Error(f"{self.zone}: no piece named {piece!r}")

    def key(self, piece: str) -> str:
        """``piece`` as the edits spell it (the shipped name's letter case)."""
        return self.shipped(piece).piece

    def placement(self, name: str) -> Placement:
        """A piece (or ``<piece>#<n>``, a copy) as the edits put it (not parked)."""
        piece, n = split_name(name)
        if n:
            c = self._copy(name)
            return pe.placed(self.shipped(c["piece"]), c.get("position"), c.get("rotation"),
                             c.get("scale"))
        spec = self.edits.pieces.get(self.key(piece), {})
        return pe.placed(self.shipped(piece), spec.get("position"), spec.get("rotation"),
                         spec.get("scale"))

    def hidden(self, piece: str) -> bool:
        return bool(self.edits.pieces.get(self.key(piece), {}).get("hidden"))

    def _copy(self, name: str) -> dict:
        piece, n = split_name(name)
        if not 1 <= n <= len(self.edits.copies) or \
                self.edits.copies[n - 1]["piece"].lower() != piece.lower():
            raise Dr2Error(f"{self.zone}: no copy {name}")
        return self.edits.copies[n - 1]

    def state(self, name: str) -> PieceState:
        piece, n = split_name(name)
        p = self.placement(name)
        return PieceState(self.zone, name, p.piece, tuple(p.position), tuple(p.rotation),
                          tuple(p.scale), hidden=not n and self.hidden(piece), copy=bool(n))

    def states(self) -> list[PieceState]:
        """Every piece the edits change and every copy, as they are now."""
        out = [self.state(k) for k in sorted(self.edits.pieces, key=str.lower)]
        out += [self.state(f"{c['piece']}#{i + 1}") for i, c in enumerate(self.edits.copies)]
        return out

    # ---- changes (each one saved) ----------------------------------------------------------

    def _snap(self) -> str:
        return pe.to_json(self.edits)

    def checkpoint(self) -> None:
        self._undo.append(self._snap())
        del self._undo[:-UNDO_LIMIT]
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._snap())
        self.edits = pe.from_json(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._snap())
        self.edits = pe.from_json(self._redo.pop())
        return True

    def place(self, name: str, position=None, rotation=None, scale=None) -> None:
        """Put a piece or a copy somewhere else (any of the three; the rest stays)."""
        piece, n = split_name(name)
        if n:
            spec = self._copy(name)
        else:
            spec = self.edits.pieces.setdefault(self.key(piece), {})
        shipped = self.shipped(piece)
        for k, v, orig in (("position", position, shipped.position),
                           ("rotation", rotation, shipped.rotation),
                           ("scale", scale, shipped.scale)):
            if v is None:
                continue
            v = [float(c) for c in v]
            if k == "scale" and any(abs(c) < 1e-3 for c in v):
                raise Dr2Error("a size of 0 would make the building vanish: use Delete "
                               "to hide it")
            if not n and all(abs(a - b) < 1e-4 for a, b in zip(v, orig)):
                spec.pop(k, None)                 # back where the game has it
            else:
                spec[k] = v
        if not n and not spec:
            self.edits.pieces.pop(self.key(piece), None)

    def hide(self, piece: str, hidden: bool = True) -> None:
        """Hide a piece (or show it again); a copy is taken out instead."""
        p, n = split_name(piece)
        if n:
            self.drop_copy(piece)
            return
        spec = self.edits.pieces.setdefault(self.key(p), {})
        if hidden:
            spec["hidden"] = True
        else:
            spec.pop("hidden", None)
        if not spec:
            self.edits.pieces.pop(self.key(p), None)

    def restore(self, piece: str) -> None:
        """A piece back as the game has it."""
        self.edits.pieces.pop(self.key(piece), None)

    def copy(self, name: str, position=None, rotation=None, scale=None) -> str:
        """A new placement of the piece of ``name`` (a piece or a copy), placed like it
        unless told otherwise; returns the copy's name."""
        p = self.placement(name)
        self.edits.copies.append({
            "piece": p.piece,
            "position": [float(c) for c in (position if position is not None else p.position)],
            "rotation": [float(c) for c in (rotation if rotation is not None else p.rotation)],
            "scale": [float(c) for c in (scale if scale is not None else p.scale)]})
        return f"{p.piece}#{len(self.edits.copies)}"

    def drop_copy(self, name: str) -> None:
        c = self._copy(name)
        self.edits.copies.remove(c)

    def save(self) -> Path:
        """Write the mod's ``.pieces.json`` files (removing one when it has nothing)."""
        pe.apply(self.original, self.edits, self.zone_vpath)     # names checked
        f = pieces_path(self.mod_dir, self.zone_vpath)
        for path, part in ((f, self.edits.placements_part()),
                           (pieces_path(self.mod_dir, self.zone_vpath, pe.COLLISION),
                            self.edits.collision_part())):
            if not part:
                path.unlink(missing_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(pe.to_json(part, self.zone), "utf-8")
        return f

    # ---- whole buildings ---------------------------------------------------------------

    def buildings(self) -> list:
        """The zone's buildings (`convert.buildings.zone_buildings`), read once."""
        if self._buildings is None:
            from ..convert import buildings as cb
            from ..convert import level as cl
            level_vp, zname = self.zone_vpath.rsplit("/", 1)
            zd = cl.Level.open(self.tree, level_vp).zone(zname.removesuffix(".big"))
            shapes = cl.zone_shapes(self.tree, zd)
            self._shapes = {s.shape.mesh.lower(): s for s in shapes}
            moves = cb.corrections(self.game, self.zone) if self.game else {}
            self._buildings = cb.zone_buildings(zd, shapes, moves)
        return self._buildings

    def building(self, name: str):
        """The building a piece (or a copy) is part of (None: none)."""
        from ..convert.buildings import building_of
        return building_of(self.buildings(), name)

    def _building(self, name: str):
        b = self.building(name)
        if b is None:
            raise Dr2Error(f"{self.zone}: {name} is not part of a building")
        return b

    def place_building(self, name: str, position, rotation=None, scale=None) -> list[str]:
        """Put the building of ``name`` where its first piece goes (``position`` …), every
        part kept where it is relative to it, and its collision moved along. Returns
        warnings (a turned or resized building's collision is only moved)."""
        b = self._building(name)
        lead = self.placement(b.parts[0])
        rot = tuple(rotation) if rotation is not None else tuple(lead.rotation)
        ratio = (float(scale[0]) / lead.scale[0]) if scale is not None and lead.scale[0] else 1.0
        turn = _qmul(_unit(rot), _qinv(_unit(lead.rotation)))
        for part in b.parts:
            p = self.placement(part)
            off = _qrot(turn, [(a - c) * ratio for a, c in zip(p.position, lead.position)])
            self.place(part, [a + o for a, o in zip(position, off)],
                       list(_qmul(turn, _unit(p.rotation))),
                       [c * ratio for c in p.scale])
        return self._move_collision(b)

    def _move_collision(self, b) -> list[str]:
        """The building's collision, moved by what its first piece moved (from as shipped)."""
        shipped = self.shipped(b.parts[0])
        now = self.placement(b.parts[0])
        d = [a - c for a, c in zip(now.position, shipped.position)]
        warn = []
        dot = abs(sum(a * c for a, c in zip(_unit(now.rotation), _unit(shipped.rotation))))
        if dot < 1 - 1e-6 or any(abs(a - c) > 1e-4 for a, c in zip(now.scale, shipped.scale)):
            warn.append(f"{b.name}: its collision can be moved but not turned or resized, "
                        f"so it keeps its shape as the game has it (docs: guide 19)")
        self.buildings()
        for mesh in b.shapes:
            spec = self.edits.collision.setdefault(mesh, {})
            ps = self._shapes.get(mesh.lower())
            local = d
            if ps is not None and ps.rule == "piece" and ps.piece is not None:
                inv = _qinv(_unit(ps.piece.rotation))      # the offset in the piece's space
                local = [c / s for c, s in zip(_qrot(inv, d), ps.piece.scale)]
            if all(abs(c) < 1e-4 for c in local):
                spec.pop("move", None)
            else:
                spec["move"] = [round(c, 4) for c in local]
            if not spec:
                self.edits.collision.pop(mesh, None)
        return warn

    def hide_building(self, name: str, hidden: bool = True) -> None:
        """Hide every part of the building and its collision (or show them again)."""
        b = self._building(name)
        for part in b.parts:
            self.hide(part, hidden)
        for mesh in b.shapes:
            spec = self.edits.collision.setdefault(mesh, {})
            if hidden:
                spec["hidden"] = True
            else:
                spec.pop("hidden", None)
            if not spec:
                self.edits.collision.pop(mesh, None)

    def restore_building(self, name: str) -> None:
        """The building and its collision back as the game has them."""
        b = self._building(name)
        for part in b.parts:
            self.restore(part)
        for mesh in b.shapes:
            self.edits.collision.pop(mesh, None)

    def copy_building(self, name: str, position) -> list[str]:
        """A copy of every part, the first piece at ``position`` (copies have no
        collision: module docstring); returns the copies' names, the first piece's first."""
        b = self._building(name)
        lead = self.placement(b.parts[0])
        out = []
        for part in b.parts:
            p = self.placement(part)
            out.append(self.copy(part, [a + (c - l) for a, c, l in
                                        zip(position, p.position, lead.position)]))
        return out

    def building_hidden(self, name: str) -> bool:
        b = self.building(name)
        return b is not None and all(self.hidden(p) for p in b.parts)

    def count(self) -> int:
        return self.edits.count()

    def snapshot(self) -> dict:
        """``{name: state dict}`` of every changed piece and copy (to compare)."""
        return {s.name.lower(): s.to_dict() for s in self.states()}


def _unit(q):
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return tuple(c / n for c in q)


def _qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def _qinv(q):
    return (-q[0], -q[1], -q[2], q[3])


def _qrot(q, v):
    x, y, z, _w = _qmul(_qmul(q, (v[0], v[1], v[2], 0.0)), _qinv(q))
    return [x, y, z]


def split_name(name: str) -> tuple[str, int]:
    """``"z05_bench02#2"`` → ``("z05_bench02", 2)``; a piece's own name → ``(name, 0)``."""
    piece, _, n = name.partition("#")
    try:
        return piece, int(n) if n else 0
    except ValueError:
        raise Dr2Error(f"{name!r}: a copy is named <piece>#<number>") from None


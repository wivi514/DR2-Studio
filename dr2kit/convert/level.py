"""Levels in 3D: find a game's levels, read their zones, put the pieces in their places.

A **level** (Case Zero's Fortune City street ``prologue``, Case West's
``living_research``…) is a folder under ``data/models/environment/`` with a
``zonelist.big``; each **zone** is an archive of **pieces** (ordinary scenes) plus a
placement table (`dr2kit.formats.level`). This module:

* lists levels and zones (`list_levels`, `Level`), and a zone's pieces, placements, and
  what doesn't match: placements naming no piece, pieces never placed (`ZoneData`);
* builds a zone as one ``.glb`` (`zone_glb`): each piece exported by
  `convert.model.model_glb` exactly as the Library shows it, then placed by its record
  (world = rotation × (scale × local) + position, checked by ``dr2 census --levels``),
  one mesh shared by every placement of a piece (`convert.gltf.Assembler`). ``lod=True``
  uses the game's small ``_LOD`` textures (the Maps tab's far zones).

Why one ``.glb`` per zone: a whole level is ~1.2 million triangles and ~200 MB of
archives. The game itself streams zone by zone; so do the Maps tab (near the camera
first) and the export (one file per zone by default, docs/phase10-kickoff.md §Decisions).

Every piece is read through the tree it is given, so a `mods.preview.ModdedTree` shows
a level with the switched-on mods (phase 10 step 5) without anything here knowing.
Formats and how they were checked: docs/formats.md §Levels.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..container.vpath import AssetTree, join
from ..errors import Dr2Error, VPathError
from ..formats import level as lvl

LEVELS_DIR = "data/models/environment"
ORGANIZATION = "ZONE_ORGANIZATION.big"
NOT_PIECES = {"zone_organization", "merged_collision"}      # zone entries that aren't pieces


@dataclass
class ZoneData:
    """What one zone holds: its pieces (name → scene vpath), placements, and mismatches."""
    level: str
    zone: lvl.Zone
    vpath: str                                   # the zone's archive
    pieces: dict[str, str] = field(default_factory=dict)
    organization: lvl.ZoneOrganization | None = None
    unplaced: list[str] = field(default_factory=list)       # pieces with no placement
    missing: list[str] = field(default_factory=list)        # placements naming no piece

    @property
    def name(self) -> str:
        return self.zone.zone

    @property
    def placements(self) -> list[lvl.Placement]:
        return self.organization.placements if self.organization else []


@dataclass
class Level:
    """One level folder: its zones (from ``zonelist.big``), read on demand."""
    tree: AssetTree
    name: str
    vpath: str
    zones: list[lvl.Zone]

    @classmethod
    def open(cls, tree: AssetTree, name: str) -> "Level":
        """The level called ``name`` (``prologue``), or its folder's vpath."""
        vp = name if "/" in name else join(LEVELS_DIR, name)
        try:
            node = tree.resolve(vp)
            num = tree.resolve(join(node.vpath, "zonelist.big", "NumZones")).data()
            zl = tree.resolve(join(node.vpath, "zonelist.big", "ZoneList")).data()
        except VPathError as e:
            raise Dr2Error(f"{name}: not a level (no zonelist.big: {e})") from None
        zones = lvl.read_zone_list(num, zl, join(node.vpath, "zonelist.big"))
        return cls(tree, node.vpath.rsplit("/", 1)[-1], node.vpath, zones)

    def zone_names(self) -> list[str]:
        return [z.zone for z in self.zones]

    def find_zone(self, zone: str) -> lvl.Zone:
        """A zone by name (``prologue_z05``) or short name (``z05``), any case."""
        key = zone.lower()
        for z in self.zones:
            if z.zone.lower() in (key, f"{self.name.lower()}_{key}"):
                return z
        raise Dr2Error(f"{self.name} has no zone {zone!r} (it has "
                       f"{', '.join(self.zone_names())})")

    def zone(self, zone: str | lvl.Zone) -> ZoneData:
        """Read one zone: its pieces, placement table and mismatches."""
        z = zone if isinstance(zone, lvl.Zone) else self.find_zone(zone)
        zvp = join(self.vpath, f"{z.zone}.big")
        try:
            arc = self.tree.open_archive(zvp)
        except VPathError as e:
            raise Dr2Error(f"{zvp}: the zone's archive is missing ({e})") from None
        zvp = arc.source
        out = ZoneData(self.name, z, zvp)
        org = None
        for e in arc.entries:
            low = e.name.lower()
            if not low.endswith(".big"):
                continue
            stem = e.name[:-4]
            if low == ORGANIZATION.lower():
                sub = self.tree.open_archive(join(zvp, e.name))
                org = lvl.ZoneOrganization.from_entries({x.name: x.data() for x in sub.entries},
                                                        join(zvp, e.name))
            elif stem.lower() not in NOT_PIECES:
                out.pieces[stem] = join(zvp, e.name, f"_COMP_{stem}.big")
        if org is None:
            raise Dr2Error(f"{zvp}: no {ORGANIZATION}")
        out.organization = org
        placed = {p.piece.lower() for p in org.placements}
        have = {k.lower(): k for k in out.pieces}
        out.unplaced = sorted(k for k in out.pieces if k.lower() not in placed)
        out.missing = sorted({p.piece for p in org.placements if p.piece.lower() not in have})
        return out

    def zone_data(self) -> list[ZoneData]:
        return [self.zone(z) for z in self.zones]


def list_levels(tree: AssetTree) -> list[Level]:
    """Every level folder of the game (folders under ``environment/`` with a zone list),
    sorted by name. Level-less folders and loose ``.big`` files (the sky) are skipped."""
    try:
        node = tree.resolve(LEVELS_DIR)
    except VPathError:
        return []
    out = []
    for p in sorted(node.path.iterdir(), key=lambda p: p.name.lower()):
        if p.is_dir() and any(c.name.lower() == "zonelist.big" for c in p.iterdir()):
            out.append(Level.open(tree, join(node.vpath, p.name)))
    return out


def piece_name(placement: lvl.Placement, zone: ZoneData) -> str | None:
    """The piece a placement puts down, with the archive's letter case (None: missing)."""
    key = placement.piece.lower()
    return next((k for k in zone.pieces if k.lower() == key), None)


def unit(q) -> tuple[float, float, float, float]:
    """A quaternion scaled to length 1 (glTF requires it; one placement of Case West's
    safehouse stores a length of 1.017)."""
    n = sum(c * c for c in q) ** 0.5 or 1.0
    return tuple(c / n for c in q)


def placement_node(p: lvl.Placement, extras: dict | None = None) -> dict:
    """A placement as `gltf.Assembler.add` takes it."""
    out = {"name": p.piece, "translation": p.position, "rotation": unit(p.rotation),
           "extras": {"dr2_piece": p.piece, "dr2_index": p.index, **(extras or {})}}
    if any(abs(s - 1.0) > 1e-7 for s in p.scale):
        out["scale"] = p.scale
    return out


@dataclass
class ZoneStats:
    pieces: int = 0
    placements: int = 0
    triangles: int = 0
    textures: int = 0
    failed: list = field(default_factory=list)              # (piece, why)
    missing_textures: set = field(default_factory=set)


def zone_glb(tree: AssetTree, zone: ZoneData, *, game: str, textures: bool = True,
             lod: bool = False, db_path=None, stats: ZoneStats | None = None,
             assembler=None, parent: int | None = None, progress=None) -> bytes | None:
    """The zone as one ``.glb``: every placed piece in its place, under one group node
    named after the zone. ``lod``: the small ``_LOD`` textures. With ``assembler`` (a
    `gltf.Assembler`), the zone goes into it under ``parent`` and None is returned
    (several zones in one file). A piece that fails to read is skipped and named in
    ``stats.failed``, never silently."""
    from . import gltf
    from .model import TextureFinder, model_glb, read_scene
    st = stats if stats is not None else ZoneStats()
    own = assembler is None
    asm = assembler or gltf.Assembler()
    group = asm.group(zone.name, parent, {"dr2_zone": zone.name, "dr2_level": zone.level})
    by_piece: dict[str, list[lvl.Placement]] = {}
    for p in zone.placements:
        name = piece_name(p, zone)
        if name is None:
            st.failed.append((p.piece, "placed, but the zone has no such piece"))
            continue
        by_piece.setdefault(name, []).append(p)
    for i, (name, places) in enumerate(by_piece.items()):
        if progress:
            progress(i, len(by_piece), name)
        vp = zone.pieces[name]
        try:
            sc = read_scene(tree, vp)
            es = gltf.ExportStats()
            finder = TextureFinder(tree, vp, game, db_path, lod=lod) if textures else None
            data = model_glb(tree, sc, game=game, finder=finder, textures=textures,
                             db_path=db_path, stats=es, mode="shown", colour_variants=False)
        except Exception as e:  # noqa: BLE001 - named in stats.failed, the zone goes on
            st.failed.append((name, str(e)))
            continue
        asm.add(data, [placement_node(p, {"dr2_vpath": vp}) for p in places], group, vp)
        st.pieces += 1
        st.placements += len(places)
        st.triangles += es.triangles * len(places)
        st.textures += es.textures
        st.missing_textures.update(es.missing_textures or ())
    if not own:
        return None
    asm.extras = {"level": zone.level, "zone": zone.name, "source": zone.vpath,
                  "lod": lod}
    return asm.to_bytes()

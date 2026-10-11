"""Export everything at once: one asset, a selection, or a whole Library group.

What a modder wants from "give me Chuck's shirt" is everything it is made of, in files
other programs open: the model with its textures and bones for Blender, every texture
as a PNG for an image editor or Substance Painter, the rig on its own, and a note of
what is what. This module writes that, one folder per model (decision of 2026-10-09,
docs/phase8-kickoff.md):

    chest_young_chuck/
        chest_young_chuck.glb   meshes, skeleton, skin, materials, textures embedded
        textures/*.png          every texture its materials name, named as in the game
        textures/textures.txt   which texture is colour / normal / specular, for which material
        textures/colours/*.png  models with colour choices (phase 9): each choice, baked
        skeleton.glb            the rig alone (an armature in Blender)
        info.txt                where it comes from, its counts against the game's limits,
                                the rig it matches, its detail levels and variants, how
                                to open it

A model with variants (`convert.variants`, phase 9) goes into its ``.glb`` with every
part sorted into groups, the parts of the chosen look (default: the first of each slot)
shown and the others marked hidden; ``mode="shown"`` keeps only that look's parts.

and one file per sound (``music/HB_Indemnify.wav``), movie (``.mp4``), string bank
(``.json``, the format a mod's ``.bcs.json`` uses), texture (``.png``) or text file.

**Resumable and cancellable.** Every file is written to a temporary name and renamed
when complete, and a file that already exists is skipped, so an export that was
cancelled or crashed continues where it stopped when run again. ``cancel()`` is checked
between files.

**Layout of a group export** (`plan`): ``<out>/<game>/<group>/<sub-group>/…``, so the two
games never mix in one folder (their files share names, and existing files are
skipped). Two different assets with the same name in one folder get the name of the
archive they come from appended (``817_cliff01__main_menu``).

Used by ``dr2 export`` and DR2 Studio's *Export all…* (docs/modding/16-library.md).
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..container.vpath import AssetTree, split
from ..errors import Dr2Error
from ..index import query
from .groups import catalog, slug

OUTPUTS = ("glb", "png", "wav", "mp4", "json", "raw")
LIMIT_PART_VERTICES = 65_536        # docs/modding/15-limits.md, formats.md §Engine limits
LIMIT_DRAW_BONES = 61


@dataclass
class Job:
    """One asset to export: its index row and where it goes (a folder for models and
    skeletons, a file path without extension for the others)."""
    row: dict
    dest: Path


@dataclass
class Result:
    written: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)          # existed already
    failed: list[tuple[str, str]] = field(default_factory=list)  # (vpath, why)
    cancelled: bool = False
    done: int = 0                                              # assets finished

    def summary(self) -> str:
        s = (f"{self.done} asset(s): {len(self.written)} file(s) written, "
             f"{len(self.skipped)} already there")
        if self.failed:
            s += f", {len(self.failed)} failed"
        return s + (" (cancelled)" if self.cancelled else "")


def stem(name: str) -> str:
    """An asset's name without its extension (``chest_young_chuck.big`` → …``chuck``)."""
    return name.rsplit(".", 1)[0] if "." in name.lstrip(".") else name


def _parent_stem(vpath: str) -> str:
    parts = split(vpath)
    return stem(parts[-2]) if len(parts) > 1 else "data"


def plan(rows: list, out: str | Path, game: str, *, by_group: bool = True,
         con: sqlite3.Connection | None = None) -> list[Job]:
    """Where each asset goes. ``by_group``: under ``<out>/<game>/<group>/<sub>/`` (the
    Library's group of each row, from ``con``); otherwise straight into ``out``."""
    out = Path(out)
    used: dict[Path, int] = {}
    jobs = []
    for r in rows:
        r = dict(r)
        folder = out
        if by_group:
            item = query.library_item(con, r["id"]) if con is not None else None
            grp = r.get("grp") or (item["grp"] if item else "other")
            sub = r.get("sub") if "sub" in r else (item["sub"] if item else "")
            folder = out / game / slug(grp)
            if sub:
                folder = folder / slug(sub)
        name = stem(r["name"])
        dest = folder / name
        if dest in used and used[dest] != r["id"]:
            dest = folder / f"{name}__{_parent_stem(r['vpath'])}"
            n = 2
            while dest in used and used[dest] != r["id"]:
                dest = folder / f"{name}__{_parent_stem(r['vpath'])}_{n}"
                n += 1
        used[dest] = r["id"]
        jobs.append(Job(r, dest))
    return jobs


def group_rows(con: sqlite3.Connection, game: str, target: str) -> list:
    """The items of a Library group (``characters``), a sub-group
    (``environments/prologue / prologue_z01`` or its folder name ``…/prologue-prologue_z01``)
    or a whole section (``sounds``)."""
    cat = catalog()
    grp, _, sub = target.partition("/")
    g = cat.group(grp)
    if g is None:
        sections = {slug(s): s for s in cat.sections()}
        if slug(target) in sections:
            out = []
            for gg in cat.groups:
                if gg.section == sections[slug(target)]:
                    out += query.library_items(con, game, gg.id, details=True)
            return out
        raise Dr2Error(f"{target}: no such Library group. Groups: "
                       + ", ".join(x.id for x in cat.groups)
                       + "; sections: " + ", ".join(slug(s) for s in cat.sections()))
    rows = query.library_items(con, game, g.id, details=True)
    if sub:
        rows = [r for r in rows if r["sub"] == sub or slug(r["sub"]) == slug(sub)]
        if not rows:
            raise Dr2Error(f"{target}: {g.title} has no sub-group {sub!r}")
    return rows


# ---- writing ----------------------------------------------------------------------------

class _Writer:
    """Writes files atomically and records them in a `Result`."""

    def __init__(self, result: Result):
        self.result = result

    def exists(self, path: Path) -> bool:
        if path.is_file():
            self.result.skipped.append(path)
            return True
        return False

    def write(self, path: Path, data: bytes | str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        if isinstance(data, str):
            tmp.write_text(data, "utf-8")
        else:
            tmp.write_bytes(data)
        os.replace(tmp, path)
        self.result.written.append(path)


class Exporter:
    """Exports assets of one game. ``outputs`` limits what is written (any of
    `OUTPUTS`; None = everything)."""

    def __init__(self, tree: AssetTree, game: str, db_path=None,
                 outputs: set[str] | None = None, *, variant: str | None = None,
                 mode: str = "all"):
        self.tree, self.game, self.db_path = tree, game, db_path
        # variants (phase 9): the look to export (choice text, `convert.variants`), and
        # "all" (every part, sorted into groups) or "shown" (only that look's parts)
        self.variant, self.mode = variant, mode
        self.outputs = set(outputs) if outputs else set(OUTPUTS)
        bad = self.outputs - set(OUTPUTS)
        if bad:
            raise Dr2Error(f"unknown output(s) {', '.join(sorted(bad))}: use "
                           + ", ".join(OUTPUTS))
        self._lookup = None
        self._labels = None
        from ..index.build import connect, default_db_path
        path = Path(db_path) if db_path else default_db_path()
        self.con = connect(path)

    def close(self) -> None:
        self.con.close()

    def run(self, jobs: list[Job], *, progress: Callable[[int, int, str], None] | None = None,
            cancel: Callable[[], bool] | None = None) -> Result:
        """Export every job; ``progress(done, total, vpath)`` before each asset."""
        res = Result()
        w = _Writer(res)
        for i, job in enumerate(jobs):
            if cancel and cancel():
                res.cancelled = True
                break
            if progress:
                progress(i, len(jobs), job.row["vpath"])
            try:
                self.export(job, w, cancel)
            except Exception as ex:  # noqa: BLE001 - every failure is listed
                res.failed.append((job.row["vpath"], str(ex).splitlines()[0] if str(ex)
                                   else type(ex).__name__))
            if cancel and cancel():
                res.cancelled = True
                break
            res.done += 1
        if progress:
            progress(res.done, len(jobs), "")
        return res

    def export(self, job: Job, w: _Writer, cancel=None) -> None:
        kind = job.row["kind"]
        fn = {"model": self.model, "skeleton": self.skeleton, "audio": self.sound,
              "video": self.movie, "strings": self.strings, "texture": self.texture}.get(kind)
        (fn or self.raw)(job, w, cancel)

    # -- one kind each --

    def _bytes(self, vpath: str) -> bytes:
        return self.tree.resolve(vpath).data()

    def texture(self, job: Job, w: _Writer, cancel=None) -> None:
        if "png" not in self.outputs:
            return
        path = job.dest.with_name(job.dest.name + ".png")
        if not w.exists(path):
            w.write(path, _png(self._bytes(job.row["vpath"]), job.row["vpath"]))

    def raw(self, job: Job, w: _Writer, cancel=None) -> None:
        if "raw" not in self.outputs:
            return
        path = job.dest.with_name(job.row["name"])
        if not w.exists(path):
            w.write(path, self._bytes(job.row["vpath"]))

    def sound(self, job: Job, w: _Writer, cancel=None) -> None:
        if "wav" not in self.outputs:
            return
        path = job.dest.with_name(job.dest.name + ".wav")
        if w.exists(path):
            return
        from ..convert.audio import AudioLookup, decode
        if self._lookup is None:
            self._lookup = AudioLookup(self.tree)
        data = self._bytes(job.row["vpath"])
        pcm = decode(data, self._lookup.info(job.row["vpath"], data))
        w.write(path, pcm.wav_bytes())

    def movie(self, job: Job, w: _Writer, cancel=None) -> None:
        if "mp4" not in self.outputs:
            return
        path = job.dest.with_name(job.dest.name + ".mp4")
        if w.exists(path):
            return
        from ..convert.video import to_mp4
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part.mp4")
        to_mp4(self._bytes(job.row["vpath"]), tmp)
        os.replace(tmp, path)
        w.result.written.append(path)

    def strings(self, job: Job, w: _Writer, cancel=None) -> None:
        if "json" not in self.outputs:
            return
        path = job.dest.with_name(job.dest.name + ".bcs.json")
        if w.exists(path):
            return
        from ..convert import strings as cstr
        from ..formats import bcs
        if self._labels is None:
            self._labels = cstr.load_labels(self.tree)
        bank = bcs.StringBank.parse(self._bytes(job.row["vpath"]), job.row["vpath"])
        w.write(path, bcs.to_json(bank, job.row["vpath"], self._labels))

    def skeleton(self, job: Job, w: _Writer, cancel=None) -> None:
        from ..convert import gltf
        from ..convert.model import read_scene
        folder = job.dest
        sc = read_scene(self.tree, job.row["vpath"])
        glb = folder / f"{folder.name}.glb"
        if "glb" in self.outputs and not w.exists(glb):
            w.write(glb, gltf.skeleton_to_glb(sc))
        info = folder / "info.txt"
        if "glb" in self.outputs and not w.exists(info):
            w.write(info, self.info_text(job.row, sc, []))

    def model(self, job: Job, w: _Writer, cancel=None) -> None:
        """The folder of one model: .glb, textures, skeleton, info (module docstring)."""
        from ..convert import gltf
        from ..convert import variants as cvar
        from ..convert.model import TextureFinder, model_glb, read_scene
        from ..formats.scene import texture_role
        folder = job.dest
        vpath = job.row["vpath"]
        sc = read_scene(self.tree, vpath)
        finder = TextureFinder(self.tree, sc.source, self.game, self.db_path)
        missing: list[str] = []
        mv = cvar.read_variants(self.tree, sc, self.game)
        try:
            choice = mv.parse(self.variant)
        except Dr2Error:
            choice = mv.default()       # a choice for another model of the group
        mode = self.mode if mv.has_choices else "all"

        glb = folder / f"{folder.name}.glb"
        if "glb" in self.outputs and not w.exists(glb):
            st = gltf.ExportStats()
            w.write(glb, model_glb(self.tree, sc, game=self.game, finder=finder, stats=st,
                                   variant=choice, mode=mode, variants=mv))
            missing += st.missing_textures or []

        # colour choices: each one's colour map, baked (textures/colours/)
        colour_lines = []
        if "png" in self.outputs and mv.colours:
            bank = cvar.ColourBank(self.tree, self.game)
            for col in mv.colours:
                for n, name in enumerate([None] + col.options):
                    if cancel and cancel():
                        return
                    stem = col.own.removesuffix(".pdv")
                    path = folder / "textures" / "colours" / f"{stem}_{n}.png"
                    vs = bank.valueset(name) if name else None
                    if name and vs is None:
                        continue
                    colour_lines.append(f"colours/{path.name:<40} {'own colours' if not n else name}")
                    if w.exists(path):
                        continue
                    baked = finder.bake(sc, sc.materials[col.materials[0]], vs,
                                        suffix=f"_{col.key}{n}" if n else "")
                    if baked is not None:
                        w.write(path, baked[1])

        # every texture the materials name, once each, with what it is for
        used: dict[str, list[int]] = {}
        for i, m in enumerate(sc.materials):
            for s in m.slots:
                if not s.engine and s.name:
                    used.setdefault(s.name, []).append(i)
        lines = []
        for name, mats in used.items():
            if cancel and cancel():
                return
            hit = finder.bct(name)
            mats_txt = ", ".join(str(i) for i in sorted(set(mats)))
            role = texture_role(name)
            if hit is None:
                if name not in missing:
                    missing.append(name)
                lines.append(f"{name:<40} {role:<11} NOT FOUND in the game data (materials {mats_txt})")
                continue
            tvp, data = hit
            from ..formats.bct import Bct
            tex = Bct.parse(data, tvp)
            h = tex.header
            lines.append(f"{name + '.png':<40} {role:<11} {h.width}x{h.height} {tex.format.name:<8} "
                         f"materials {mats_txt}   ({tvp})")
            path = folder / "textures" / f"{name}.png"
            if "png" in self.outputs and not w.exists(path):
                w.write(path, _png(data, tvp))
        if "png" in self.outputs and used:
            note = folder / "textures" / "textures.txt"
            if not w.exists(note):
                if colour_lines:
                    lines += ["", "Colour choices (the game may swap these in for a material's own "
                                  "colours; already baked, ready to look at):"] + colour_lines
                w.write(note, _TEXTURES_HEAD.format(name=job.row["name"]) + "\n".join(lines) + "\n")

        skel = folder / "skeleton.glb"
        if "glb" in self.outputs and sc.skeleton.nodes and not w.exists(skel):
            w.write(skel, gltf.skeleton_to_glb(sc))
        info = folder / "info.txt"
        if self.outputs & {"glb", "png"} and not w.exists(info):
            w.write(info, self.info_text(job.row, sc, missing, len(used), mv, choice, mode))

    # -- info.txt --

    def info_text(self, row, sc, missing: list[str], textures: int = 0, mv=None,
                  choice=None, mode: str = "all") -> str:
        """The ``info.txt`` of a model or skeleton folder."""
        item = query.library_item(self.con, row["id"])
        g = catalog().group(item["grp"]) if item else None
        lines = [f"{row['name']}" + (f"  —  {item['label']}" if item and item["label"] else ""),
                 "",
                 f"game:        {self.game}",
                 f"game path:   {row['vpath']}",
                 f"library:     {g.section + ' / ' + g.title if g else '-'}"
                 + (f" / {item['sub']}" if item and item["sub"] else ""),
                 f"size:        {row['size']:,} bytes"]
        for c in query.copies(self.con, row["id"]):
            lines.append(f"also in:     {c['vpath']}  (the same bytes)")
        draws = [d for m in sc.meshes for d in m.draws]
        lines += ["", f"bones:       {len(sc.skeleton)}"]
        if sc.meshes:
            part = max(sum(d.vertex_count for d in m.draws) for m in sc.meshes)
            pal = max((d.palette_count for d in draws if d.skinned), default=0)
            lines += [
                f"parts:       {len(sc.meshes)} ({len(draws)} draws, "
                f"{sum(d.vertex_count for d in draws):,} vertices)",
                f"materials:   {len(sc.materials)}; textures: {textures}"
                + (f" ({len(missing)} not found: {', '.join(missing)})" if missing else ""),
                f"largest part: {part:,} vertices (the game's limit: {LIMIT_PART_VERTICES:,})",
                f"most bones one draw uses: {pal} (the game's limit: {LIMIT_DRAW_BONES})"]
            rigs = query.rigs_of(self.con, row["id"])
            if rigs:
                r = rigs[0]
                how = {0: "the same bones, same rest pose",
                       1: "the same bone names, other proportions"}.get(
                    r["rank"], f"all its bones, plus {r['extra']} more")
                lines.append(f"rig:         {r['vpath']}  ({how})")
            elif len(sc.skeleton):
                lines.append("rig:         its own (no skeleton file has the same bones)")
        levels = query.detail_levels(self.con, row["id"])
        if levels:
            lines += ["", "detail levels (the game draws the high one close up, the low one far "
                          "away; each has its own folder):"]
            lines += [f"  {lv['detail']:<7} {lv['vpath']}" for lv in levels]
        if mv is not None and mv.has_choices:
            lines += ["", "variants (docs/modding/17-variants.md): the game shows one choice per "
                          "slot, never all at once",
                      "  in the .glb: " + ("every part, in groups; the parts this look doesn't "
                                           "show are marked hidden" if mode == "all" else
                                           "only the parts this look shows")]
            lines += ["  " + x for x in mv.describe(choice)]
        lines += ["", _HOW_TO_USE if sc.meshes else _HOW_TO_USE_RIG]
        return "\n".join(lines) + "\n"


_TEXTURES_HEAD = """The textures of {name}, as the game stores them (decoded to PNG, full size).
Role, from the name's ending: colour = what you see (_cm), normal = bumps, OpenGL-style
green up (_nm), specular = the colour of the shine (_sm), mask = tint mask (_mask).
To put an edited one back: DR2 Studio, select the texture, Replace with PNG… (the same
size), or Import textures… on the model for a whole folder (docs/modding/14-texturing-tools.md).

"""

_HOW_TO_USE = """How to use these files
- Blender: File > Import > glTF 2.0, pick the model's .glb (textures and bones included).
  With the DR2 add-on (docs/modding/13-blender-addon.md) you can check and export it back.
- Substance Painter / other texturing programs: import the .glb as the mesh; the PNGs in
  textures/ are the game's own maps to start from (docs/modding/14-texturing-tools.md).
- skeleton.glb is the rig alone, for animating or for building a new model on it
  (docs/modding/09-new-model.md).
- Limits to respect when you change it: docs/modding/15-limits.md.
"""

_HOW_TO_USE_RIG = """How to use these files
- Blender: File > Import > glTF 2.0, pick the .glb: an armature with the game's bone names.
- A new model for this rig: docs/modding/09-new-model.md.
"""


def _png(data: bytes, source: str) -> bytes:
    from ..convert import png
    from ..convert.texture import png_mode, to_image
    from ..formats.bct import Bct
    tex = Bct.parse(data, source)
    img = to_image(tex)
    return png.encode(img, png_mode(tex, img))

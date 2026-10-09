"""Build mods: turn their overrides into whole replacement files for one game.

Why whole files: the game (and the recomp's overlay folders) only ever swap whole files
on disk, so a texture three archives deep means rewriting the archive on disk that holds
it. The build does that and nothing else:

1. **Classify** every file under each mod's ``replace/`` (`classify`): a ``.png`` next to
   a texture's vpath replaces that texture; a ``.glb`` next to a model's vpath replaces
   that model's meshes (`dr2kit.convert.model_import`, checked by the rig validator
   first); any other file replaces the asset with the same vpath, byte for byte. Unknown paths, wrong sizes and conflicts between mods are
   errors, reported all at once.
2. **Patch** each file on disk that holds an override (`patch_archive`): parse it, walk
   down the vpath, replace the leaf, and re-serialise every archive on the way back up.
   An entry that was LZX-compressed is compressed again (the game crashes on a stored
   replacement; CLAUDE.md rule 4), and every encode is verified by decoding.
3. **Verify** the output: read every override back through a fresh `AssetTree` over the
   build folder and compare it with what was meant to be written.

``base_dirs``: folders laid out like the game root (``data/...``) whose copy of a file is
patched instead of the shipped one. A recomp's ``assets/game_patched`` goes here, so a
mod that touches ``datafile.big`` keeps the recomp's own edits to it
(docs/ARCHITECTURE.md §Recomp integration, "Conflict rule").
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..container.big import BigArchive, is_big
from ..container.vpath import AssetTree, entry_component, find_entry, join, split
from ..errors import Dr2Error
from ..formats.bct import Bct, is_bct
from .manifest import Mod, ModError, Override

BUILD_INFO = "dr2kit-build.json"


@dataclass
class Planned:
    """An override that passed classification, with the real-case vpath it resolves to."""
    override: Override
    mod: Mod
    vpath: str            # real letter case, as the game spells it
    disk_parts: int       # how many leading vpath components are folders/file on disk


@dataclass
class BuildResult:
    """What a build wrote. ``files`` are vpaths of whole files (``data/...``)."""
    game: str
    out_dir: Path
    files: list[str] = field(default_factory=list)
    overrides: list[Planned] = field(default_factory=list)
    base_used: dict = field(default_factory=dict)     # file vpath -> base folder used
    warnings: list[str] = field(default_factory=list)


def _disk_parts(tree: AssetTree, vpath: str) -> int:
    """Number of vpath components that are on disk (folders + the file itself)."""
    parts = split(vpath)
    here = tree.root
    for i, p in enumerate(parts):
        if not here.is_dir():
            return i
        nxt = next((c for c in here.iterdir() if c.name.lower() == p.lower()), None)
        if nxt is None:
            return i
        here = nxt
    return len(parts)


def classify(mods: list[Mod], game: str, tree: AssetTree) -> list[Planned]:
    """Check every override of ``mods`` against the game and return the plan.

    Raises `ModError` listing every problem: an unknown vpath, a PNG whose target is not a
    texture, two mods replacing the same asset at the same priority, or one mod replacing
    an archive while another replaces something inside it.
    """
    problems: list[str] = []
    plan: dict[str, Planned] = {}
    for mod in sorted(mods, key=lambda m: m.priority):
        if game not in mod.games:
            continue
        for rel, src in mod.files():
            kind = "raw"
            target = rel
            if rel.lower().endswith(".png"):
                target = rel[:-4]
                kind = "texture-png"
            elif rel.lower().endswith(".glb"):
                target = rel[:-4]
                kind = "model-glb"
            try:
                node = tree.resolve(target)
            except Dr2Error:
                problems.append(f"{mod.id}: replace/{rel}: no asset {target!r} in {game}")
                continue
            if node.kind == "dir":
                problems.append(f"{mod.id}: replace/{rel}: {node.vpath} is a folder")
                continue
            if kind == "texture-png" and not is_bct(node.data()[:3]):
                problems.append(f"{mod.id}: replace/{rel}: {node.vpath} is not a texture, "
                                f"so a PNG can't replace it")
                continue
            if kind == "model-glb":
                problem = _check_model(node, src)
                if problem:
                    problems.append(f"{mod.id}: replace/{rel}: {problem}")
                    continue
            key = node.vpath.lower()
            if key in plan and plan[key].mod.priority == mod.priority:
                problems.append(f"{node.vpath}: replaced by both {plan[key].mod.id} and "
                                f"{mod.id} at the same priority; raise one mod's priority")
                continue
            plan[key] = Planned(Override(node.vpath, src, kind), mod, node.vpath,
                                _disk_parts(tree, node.vpath))
    keys = sorted(plan)
    for a in keys:
        for b in keys:
            if b != a and b.startswith(a + "/"):
                problems.append(f"{plan[a].mod.id} replaces {plan[a].vpath} as a whole, and "
                                f"{plan[b].mod.id} replaces {plan[b].vpath} inside it; "
                                f"only one can apply")
    if problems:
        raise ModError("the mod set can't be built:\n  " + "\n  ".join(problems))
    return [plan[k] for k in keys]


def _check_model(node, src: Path) -> str | None:
    """Why a ``.glb`` can't replace this asset (None if it can): the rig validator."""
    from ..convert.model_import import plan_import
    from ..formats.scene import Scene
    data = node.data()
    if not is_big(data):
        return f"{node.vpath} is not a model, so a .glb can't replace it"
    try:
        scene = Scene.parse(data, node.vpath)
    except Dr2Error as e:
        return f"{node.vpath} is not a model ({e})"
    plan = plan_import(scene, src.read_bytes(), str(src))
    if not plan.ok:
        return "the model check failed:\n    " + "\n    ".join(str(i) for i in plan.errors)
    return None


def new_bytes(p: Planned, original: bytes) -> bytes:
    """The replacement bytes for one override, given the asset's current bytes."""
    if p.override.kind == "raw":
        return p.override.source.read_bytes()
    if p.override.kind == "model-glb":
        from ..convert.model_import import import_glb
        from ..formats.scene import Scene
        try:
            out, _ = import_glb(Scene.parse(original, p.vpath), p.override.source.read_bytes(),
                                str(p.override.source))
        except Dr2Error as e:
            raise ModError(f"{p.mod.id}: replace/{p.vpath}.glb: {e}") from None
        return out
    from ..convert import png
    from ..convert.texture import replace_image
    tex = Bct.parse(original, p.vpath)
    try:
        img = png.read(p.override.source)
    except Dr2Error as e:
        raise ModError(f"{p.mod.id}: {e}") from None
    try:
        return replace_image(tex, img).to_bytes()
    except Dr2Error as e:
        raise ModError(f"{p.mod.id}: replace/{p.vpath}.png: {e}") from None


def patch_archive(data: bytes, vpath: str, edits: dict) -> bytes:
    """Apply ``edits`` to the archive ``data`` and return the new archive bytes.

    ``edits`` maps a vpath component to either a nested dict (edit inside that entry,
    which must be an archive) or a `Planned` leaf. Compressed entries are re-compressed.
    """
    arc = BigArchive.parse(data, vpath)
    for comp, sub in edits.items():
        entry = find_entry(arc, comp)
        evp = join(vpath, entry_component(arc, entry))
        current = entry.data()
        if isinstance(sub, dict):
            if not is_big(current):
                raise ModError(f"{evp}: not an archive, nothing can be replaced inside it")
            updated = patch_archive(current, evp, sub)
        else:
            updated = new_bytes(sub, current)
        entry.set_data(updated)
    return arc.to_bytes()


def build(mods: list[Mod], game: str, tree: AssetTree, out_dir: str | Path,
          base_dirs: list[Path] | tuple = (), progress=None) -> BuildResult:
    """Build ``mods`` for ``game`` into ``out_dir`` (laid out like the game root).

    Returns a `BuildResult`; raises `ModError` (nothing written) if the plan is invalid.
    ``progress(message)`` is called per file written.
    """
    out = Path(out_dir)
    plan = classify(mods, game, tree)
    res = BuildResult(game, out, overrides=plan)
    by_file: dict[str, list[Planned]] = {}
    for p in plan:
        file_vp = join(*split(p.vpath)[:p.disk_parts])
        by_file.setdefault(file_vp, []).append(p)
    for file_vp, items in sorted(by_file.items()):
        src = tree.root.joinpath(*split(file_vp))
        base = next((Path(b) for b in base_dirs if Path(b).joinpath(*split(file_vp)).is_file()),
                    None)
        if base is not None:
            src = base.joinpath(*split(file_vp))
            res.base_used[file_vp] = str(base)
        data = src.read_bytes()
        whole = [p for p in items if p.disk_parts == len(split(p.vpath))]
        if whole:                                  # the file itself is replaced
            data = new_bytes(whole[0], data)
        else:
            edits: dict = {}
            for p in items:
                comps = split(p.vpath)[p.disk_parts:]
                node = edits
                for c in comps[:-1]:
                    node = node.setdefault(c, {})
                node[comps[-1]] = p
            data = patch_archive(data, file_vp, edits)
        dest = out.joinpath(*split(file_vp))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        res.files.append(file_vp)
        if progress:
            progress(file_vp)
    verify(res, tree, base_dirs)
    info = {
        "game": game,
        "mods": [{"id": m.id, "version": m.version, "priority": m.priority} for m in mods
                 if game in m.games],
        "files": {f: hashlib.sha1(out.joinpath(*split(f)).read_bytes()).hexdigest()
                  for f in res.files},
        "overrides": [{"vpath": p.vpath, "kind": p.override.kind, "mod": p.mod.id}
                      for p in plan],
        "base_used": res.base_used,
    }
    (out / BUILD_INFO).write_text(json.dumps(info, indent=1), "utf-8")
    return res


def verify(res: BuildResult, tree: AssetTree, base_dirs=()) -> None:
    """Read every override back from the build and check it is what was meant.

    For a texture or a model, "what was meant" is the replacement built again from the
    original; for a raw override, the file's bytes. Raises `ModError` on any difference.
    """
    built = AssetTree(res.out_dir)
    for p in res.overrides:
        got = built.resolve(p.vpath).data()
        if p.override.kind == "raw":
            want = p.override.source.read_bytes()
        else:
            original = _original(tree, base_dirs, p)
            want = new_bytes(p, original)
        if got != want:
            raise ModError(f"build check failed: {p.vpath} reads back differently")


def _original(tree: AssetTree, base_dirs, p: Planned) -> bytes:
    for b in base_dirs:
        f = Path(b).joinpath(*split(p.vpath)[:p.disk_parts])
        if f.is_file():
            return AssetTree(b).resolve(p.vpath).data()
    return tree.resolve(p.vpath).data()

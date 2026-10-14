"""Build mods: turn their overrides into whole replacement files for one game.

Why whole files: the game (and the recomp's overlay folders) only ever swap whole files
on disk, so a texture three archives deep means rewriting the archive on disk that holds
it. The build does that and nothing else:

1. **Classify** every file under each mod's ``replace/`` (`classify`): a ``.png`` next to
   a texture's vpath replaces that texture; a ``.glb`` next to a model's vpath replaces
   that model's meshes (`dr2kit.convert.model_import`, checked by the rig validator
   first); a ``.wav``/``.ogg``/``.flac``/``.mp3`` next to a sound's vpath is played by
   the recomp instead of that sound (`dr2kit.mods.audio`: no game file changes, the
   build writes ``dr2kit_audio/``); a ``.bcs.json`` next to a string bank changes the
   strings it lists (`dr2kit.formats.bcs`; several mods merge by string id); a
   ``.edits.json`` next to a level text file changes the blocks it names
   (`dr2kit.formats.leveledits`; several mods merge by block and key, applied over the
   recomp's copy when there is one); a ``.pieces.json`` next to a zone's
   ``ZONE_ORGANIZATION.big`` hides, moves, turns, resizes or copies its buildings, and one
   next to its ``MERGED_COLLISION.big`` moves or hides their collision
   (`dr2kit.formats.pieceedits`; several mods merge by piece and shape); any other file
   replaces the asset with the same
   vpath, byte for byte. Files under ``add/`` are **new entries** of an archive
   (`manifest`; inserted in name order, compressed like their neighbours), or, where the
   folder above is a folder (or one the game doesn't have), **new files** (kind
   ``file``, phase 14: a level of one's own, ``data/models/environment/<slot>/zonelist.big``). Unknown paths, wrong
   sizes, files the game digest-checks and conflicts between mods at the same priority
   are errors, reported all at once. Between different priorities the higher one wins,
   and `plan_mods` lists what lost (``ModPlan.shadowed``) for the mod manager. A change
   to a file the game reads from its copy in ``preload4.big`` (the profile's
   ``preload_evict``: the particle effects) **evicts** that copy (its index hash is
   changed, nothing re-encoded), so the game reads the changed loose file.
2. **Patch** each file on disk that holds an override (`patch_archive`): parse it, walk
   down the vpath, replace the leaf, and re-serialise every archive on the way back up.
   An entry that was LZX-compressed is compressed again (the game crashes on a stored
   replacement; CLAUDE.md rule 4), and every encode is verified by decoding.
3. **Re-pin** ``layout.bin`` (`repin_layout`): the game reads each file by the size
   this table pins, so a build whose files changed size carries a ``layout.bin`` with
   their new sizes, and a record for every new file.
4. **Verify** the output: read every override back through a fresh `AssetTree` over the
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
from ..container.vpath import entry_components as entry_components_of
from ..errors import Dr2Error
from ..formats.bct import Bct, is_bct
from .manifest import (ADD_DIR, AUDIO_EXTS, EDITS_EXT, EFFECT_EXT, PIECES_EXT, STRINGS_EXT, Mod,
                       ModError, Override)

MERGED = ("strings", "edits", "pieces")     # kinds that several mods apply to one file together
PRELOAD = "data/preload4.big"
EVICT_XOR = 0xDEADBEEF                      # the CZ recomp's own eviction (gen_pc_options.py)
EFFECT_FORMAT = "dr2kit-effect/1"

BUILD_INFO = "dr2kit-build.json"


@dataclass
class Planned:
    """An override that passed classification, with the real-case vpath it resolves to."""
    override: Override
    mod: Mod
    vpath: str            # real letter case, as the game spells it
    disk_parts: int       # how many leading vpath components are folders/file on disk
    strings: dict | None = None   # kind "strings": id -> text, read from the .bcs.json
    edits: object = None          # kind "edits": a leveledits.Edits, read from the .edits.json;
                                  # kind "pieces": a pieceedits.Edits (.pieces.json)
    data: bytes | None = None     # kind "add" from a .copy.json recipe: the entry's bytes


@dataclass
class BuildResult:
    """What a build wrote. ``files`` are vpaths of whole files (``data/...``)."""
    game: str
    out_dir: Path
    files: list[str] = field(default_factory=list)
    overrides: list[Planned] = field(default_factory=list)
    base_used: dict = field(default_factory=dict)     # file vpath -> base folder used
    warnings: list[str] = field(default_factory=list)
    shadowed: list = field(default_factory=list)      # (vpath, losing mod, winning mod)
    new_files: list[str] = field(default_factory=list)   # kind "file": not in the game


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


@dataclass
class ModPlan:
    """What a set of mods will do: the overrides that apply, and what lost.

    ``shadowed`` lists ``(vpath, losing mod id, winning mod id)`` for every asset (or
    string id, written ``<bank vpath> id <n>``) that two mods replace: the mod with the
    higher priority wins (the mod manager's order sets priorities). ``notes`` are
    warnings for the modder (a string without its ``@``, placeholders changed…).
    """
    planned: list[Planned]
    shadowed: list[tuple[str, str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _kind_of(rel: str) -> tuple[str, str]:
    """``(kind, target vpath)`` of a file under ``replace/`` (see `manifest`)."""
    low = rel.lower()
    if low.endswith(".png"):
        return "texture-png", rel[:-4]
    if low.endswith(".glb"):
        return "model-glb", rel[:-4]
    if low.endswith(STRINGS_EXT):
        return "strings", rel[:-len(".json")]
    if low.endswith(EDITS_EXT):
        return "edits", rel[:-len(EDITS_EXT)]
    if low.endswith(PIECES_EXT):
        return "pieces", rel[:-len(PIECES_EXT)]
    if low.endswith(EFFECT_EXT):
        return "effect", rel[:-len(EFFECT_EXT)]
    if low.endswith(AUDIO_EXTS) and rel.rsplit(".", 1)[0].lower().endswith(".xma"):
        return "audio", rel.rsplit(".", 1)[0]
    return "raw", rel


def classify(mods: list[Mod], game: str, tree: AssetTree) -> list[Planned]:
    """Check every override of ``mods`` against the game and return the plan.

    Raises `ModError` listing every problem (see `plan_mods`).
    """
    return plan_mods(mods, game, tree).planned


def plan_mods(mods: list[Mod], game: str, tree: AssetTree) -> ModPlan:
    """Check every override of ``mods`` against the game and return a `ModPlan`.

    Raises `ModError` listing every problem: an unknown vpath, a PNG whose target is not a
    texture, a file the game checks against a digest (it crashes on an edited copy), two
    mods replacing the same asset at the same priority, or one mod replacing an archive
    while another replaces something inside it. String overrides (``.bcs.json``) merge:
    several mods can change one bank, and only a string id that two of them change is a
    conflict.
    """
    from ..profiles import load_profile
    digest = [d.lower() for d in load_profile(game).digest_checked]
    problems: list[str] = []
    plan: dict[str, Planned] = {}
    shadowed: list[tuple[str, str, str]] = []
    notes: list[str] = []
    from .requires import check, infer
    switched_on = {m.id: m.version for m in mods if game in m.games}
    refused: set[str] = set()                       # mods whose needs aren't met
    for mod in sorted(mods, key=lambda m: m.priority):
        if game not in mod.games:
            continue
        try:                                        # [requires]: game data, other mods
            missing = check(infer(mod), game, switched_on)
        except ModError as e:
            missing = [str(e)]
        if missing:
            problems += missing
            refused.add(mod.id)
            continue
        for rel, src in mod.files():
            kind, target = _kind_of(rel)
            try:
                node = tree.resolve(target)
            except Dr2Error:
                problems.append(f"{mod.id}: replace/{rel}: no asset {target!r} in {game}")
                continue
            if node.kind == "dir":
                problems.append(f"{mod.id}: replace/{rel}: {node.vpath} is a folder")
                continue
            low = node.vpath.lower()
            hit = next((d for d in digest if low == d or low.startswith(d + "/")), None)
            if hit:
                problems.append(f"{mod.id}: replace/{rel}: the game checks {hit} against a "
                                f"digest and crashes on an edited copy, so it can't be "
                                f"modded (docs/formats.md)")
                continue
            if kind == "texture-png" and not is_bct(node.data()[:3]):
                problems.append(f"{mod.id}: replace/{rel}: {node.vpath} is not a texture, "
                                f"so a PNG can't replace it")
                continue
            if kind == "effect":
                problem = _check_effect(node, src)
                if problem:
                    problems.append(f"{mod.id}: replace/{rel}: {problem}")
                    continue
            if kind == "model-glb":
                problem = _check_model(node, src)
                if problem:
                    problems.append(f"{mod.id}: replace/{rel}: {problem}")
                    continue
            strings = edits = None
            if kind == "strings":
                try:
                    strings = _read_strings(tree, node, src)
                except Dr2Error as e:
                    problems.append(f"{mod.id}: replace/{rel}: {e}")
                    continue
                key = f"{low}|strings|{mod.id}"
            elif kind == "edits":
                try:
                    edits = _read_edits(node, src)
                except Dr2Error as e:
                    problems.append(f"{mod.id}: replace/{rel}: {e}")
                    continue
                key = f"{low}|edits|{mod.id}"
            elif kind == "pieces":
                try:
                    edits = _read_pieces(node, src)
                except Dr2Error as e:
                    problems.append(f"{mod.id}: replace/{rel}: {e}")
                    continue
                key = f"{low}|pieces|{mod.id}"
            else:
                key = low
            if key in plan and plan[key].mod.priority == mod.priority:
                problems.append(f"{node.vpath}: replaced by both {plan[key].mod.id} and "
                                f"{mod.id} at the same priority; raise one mod's priority")
                continue
            if key in plan:
                shadowed.append((node.vpath, plan[key].mod.id, mod.id))
            plan[key] = Planned(Override(node.vpath, src, kind), mod, node.vpath,
                                _disk_parts(tree, node.vpath), strings, edits)
    # Level textures: the game takes a name from the first pack of the zone that has it,
    # whichever piece uses it, so a PNG must reach every identical copy in the zone
    # (docs/formats.md §Levels; the shed/garage wall test of 2026-10-11)
    for key in list(plan):
        p = plan[key]
        if p.override.kind != "texture-png":
            continue
        for vp in level_texture_copies(tree, p.vpath):
            low = vp.lower()
            if low in plan:
                continue
            plan[low] = Planned(Override(vp, p.override.source, "texture-png"), p.mod, vp,
                                _disk_parts(tree, vp))
            notes.append(f"{p.mod.id}: {p.vpath.rsplit('/', 2)[-1]} is also in "
                         f"{vp.rsplit('/', 2)[-2]} of the same zone: changed there too (the "
                         f"game uses the first copy in the zone)")
    keys = sorted(plan)
    for a in keys:
        for b in keys:
            if b != a and b.startswith(a + "/"):
                problems.append(f"{plan[a].mod.id} replaces {plan[a].vpath} as a whole, and "
                                f"{plan[b].mod.id} replaces {plan[b].vpath} inside it; "
                                f"only one can apply")
    banks: dict[str, list[Planned]] = {}
    for k in keys:
        if plan[k].override.kind == "strings":
            banks.setdefault(plan[k].vpath.lower(), []).append(plan[k])
    for low, items in banks.items():
        if low in plan:
            problems.append(f"{plan[low].mod.id} replaces {plan[low].vpath} as a whole and "
                            f"{items[0].mod.id} changes strings in it; use a .bcs.json "
                            f"for both")
        owner: dict[int, Planned] = {}
        for p in sorted(items, key=lambda p: p.mod.priority):
            for i in p.strings:
                if i in owner and owner[i].mod.priority == p.mod.priority:
                    problems.append(f"{p.vpath} id {i}: changed by both {owner[i].mod.id} "
                                    f"and {p.mod.id} at the same priority")
                elif i in owner:
                    shadowed.append((f"{p.vpath} id {i}", owner[i].mod.id, p.mod.id))
                owner[i] = p
    for mod in sorted(mods, key=lambda m: m.priority):    # new entries (add/)
        if game not in mod.games or mod.id in refused:
            continue
        for rel, src in mod.added():
            from .newitem import COPY_EXT, build_copy
            recipe = None
            if rel.lower().endswith(COPY_EXT):            # made from the player's game
                rel = rel[:-len(COPY_EXT)]
                try:
                    recipe = build_copy(tree, json.loads(src.read_text("utf-8")), mod.root,
                                        f"{mod.id}: {ADD_DIR}/{rel}{COPY_EXT}")
                except (Dr2Error, ValueError) as e:
                    problems.append(str(e))
                    continue
            parent, _, name = rel.rpartition("/")
            folder = _new_file_folder(tree, parent)
            if folder is not None:                       # a new file, not an entry
                vp = join(folder, name) if folder else rel
                if (tree.root.joinpath(*split(vp))).exists():
                    problems.append(f"{mod.id}: {ADD_DIR}/{rel}: the game already has "
                                    f"{vp}; put a changed copy under replace/ instead")
                    continue
                key = vp.lower()
                if key in plan and plan[key].mod.priority == mod.priority:
                    problems.append(f"{vp}: added by both {plan[key].mod.id} and {mod.id}")
                    continue
                if key in plan:
                    shadowed.append((vp, plan[key].mod.id, mod.id))
                plan[key] = Planned(Override(vp, src, "file"), mod, vp, len(split(vp)),
                                    data=recipe)
                continue
            try:
                node = tree.resolve(parent)
                arc = tree.open_archive(node.vpath)
            except Dr2Error:
                problems.append(f"{mod.id}: {ADD_DIR}/{rel}: {parent!r} is not an archive of "
                                f"{game}")
                continue
            if any(e.name.lower() == name.lower() for e in arc.entries):
                problems.append(f"{mod.id}: {ADD_DIR}/{rel}: {node.vpath} already has "
                                f"{name}; put a changed copy under replace/ instead")
                continue
            vp = join(node.vpath, name)
            key = vp.lower()
            if key in plan and recipe is not None and plan[key].data == recipe:
                continue          # the same new entry from two mods (a brought shader)
            if key in plan and plan[key].mod.priority == mod.priority:
                problems.append(f"{vp}: added by both {plan[key].mod.id} and {mod.id}")
                continue
            if key in plan:
                shadowed.append((vp, plan[key].mod.id, mod.id))
            plan[key] = Planned(Override(vp, src, "add"), mod, vp, _disk_parts(tree, vp),
                                data=recipe)
    # Files the game reads from preload4.big (profile preload_evict: the effects): the
    # nested copy is evicted (its index hash changed) so the game reads the changed
    # loose file; re-encoding inside preload4.big crashes the boot (docs/formats.md)
    for key in list(plan):
        p = plan[key]
        for loose, entry in load_profile(game).preload_evict.items():
            if not (p.vpath.lower() == loose.lower() or
                    p.vpath.lower().startswith(loose.lower() + "/")):
                continue
            evp = join(PRELOAD, entry)
            ekey = evp.lower() + "|evict"
            try:
                tree.resolve(evp)
            except Dr2Error:
                continue
            if ekey not in plan:
                plan[ekey] = Planned(Override(evp, p.override.source, "evict"), p.mod, evp,
                                     _disk_parts(tree, evp))
    keys = sorted(plan)
    texts: dict[str, list[Planned]] = {}
    for k in keys:
        if plan[k].override.kind == "edits":
            texts.setdefault(plan[k].vpath.lower(), []).append(plan[k])
    from ..formats import leveledits
    facts = None
    added_spawns: dict[str, set[str]] = {}       # level file stem -> spawn points mods add
    for low, items in texts.items():
        stem = low.rsplit("/", 1)[-1].removesuffix(".txt")
        for p in items:
            for path in p.edits.add:
                if path.lower().startswith("cspawnpoint ") and "/" not in path:
                    added_spawns.setdefault(stem, set()).add(path.split(" ", 1)[1].lower())
    for low, items in texts.items():
        if low in plan:
            problems.append(f"{plan[low].mod.id} replaces {plan[low].vpath} as a whole and "
                            f"{items[0].mod.id} edits blocks in it; use an .edits.json for "
                            f"both (dr2 level diff turns a whole file into one)")
            continue
        sh, pr = leveledits.merge([_layer(p) for p in items])
        shadowed += [(f"{items[0].vpath}: {w}", a, b) for w, a, b in sh]
        problems += [f"{items[0].vpath}: {x}" for x in pr]
        if not pr:
            try:          # applies over the shipped copy (the build: over the recomp's)
                out, n = _apply_edits(items, tree.resolve(items[0].vpath).data())
                notes += n
            except Dr2Error as e:
                problems.append(str(e))
                continue
            from ..convert import levelcheck
            from ..formats.levelscript import Document
            if facts is None:
                facts = levelcheck.GameFacts(tree, game)
                _added_scripts(facts, plan)
                facts.zombie_types |= {      # zombie types a mod fills (phase 15)
                    p.vpath.rsplit("/", 1)[-1].lower()[:-4] for p in plan.values()
                    if p.override.kind == "add" and p.vpath.lower().startswith(
                        "data/models/zombies.big/") and p.vpath.lower().endswith(".big")}
                for stem, names in added_spawns.items():
                    facts.spawn_points(stem).update(names)
                facts.added_items = {path.split(" ", 1)[1].lower()
                                     for ps in texts.values() for p in ps
                                     if p.vpath.lower().endswith("/items.txt")
                                     for path in p.edits.add if "/" not in path}
            doc = Document.parse(out, items[0].vpath)
            tops = {path.lower() for p in items for path in p.edits.add
                    if "/" not in path}
            for p in items:
                for f in levelcheck.check(facts, p.vpath, doc, p.edits, tops):
                    (problems if f.error else notes).append(
                        f"{p.mod.id}: {p.vpath.rsplit('/', 1)[-1]}: {f}")
    zones: dict[str, list[Planned]] = {}
    for k in keys:
        if plan[k].override.kind == "pieces":
            zones.setdefault(plan[k].vpath.lower(), []).append(plan[k])
    for low, items in zones.items():
        if low in plan or any(k.startswith(low + "/") and plan[k].override.kind != "pieces"
                              for k in plan):
            other = plan.get(low) or next(plan[k] for k in plan if k.startswith(low + "/"))
            problems.append(f"{other.mod.id} replaces {other.vpath} and {items[0].mod.id} "
                            f"moves buildings in it ({PIECES_EXT}): only one can")
            continue
        from ..formats import pieceedits
        _m, sh, pr = pieceedits.merge([_piece_layer(p) for p in items])
        shadowed += [(f"{items[0].vpath}: {w}", a, b) for w, a, b in sh]
        problems += [f"{items[0].vpath}: {x}" for x in pr]
        if not pr:
            try:
                _apply_pieces(items, tree.resolve(items[0].vpath).data())
            except Dr2Error as e:
                problems.append(str(e))
    if problems:
        raise ModError("the mod set can't be built:\n  " + "\n  ".join(problems))
    planned = [plan[k] for k in keys]
    for low, items in banks.items():
        try:
            _apply_strings(items, tree.resolve(items[0].vpath).data(), notes)
        except Dr2Error as e:
            raise ModError(f"the mod set can't be built:\n  {e}") from None
    return ModPlan(planned, shadowed, notes)


def level_texture_copies(tree: AssetTree, vpath: str) -> list[str]:
    """Other full-size copies of a level texture in its zone: the same name (with or
    without ``.bct``) in another ``.tex`` pack of the same zone archive, with the same
    bytes. Empty for anything that isn't a texture in a zone's pack."""
    parts = split(vpath)
    low = [x.lower() for x in parts]
    if "environment" not in low:
        return []
    i = low.index("environment")
    z = i + 3                                     # environment/<level>/<zone>.big
    if len(parts) != z + 2 or not low[z - 1].endswith(".big") or \
            not low[z].endswith(".tex") or low[z].endswith("_lod.tex"):
        return []
    zone_vp = join(*parts[:z])
    name = low[-1].removesuffix(".bct")
    try:
        mine = tree.resolve(vpath).data()
        zone = tree.open_archive(zone_vp)
    except Dr2Error:
        return []
    out = []
    for comp, e in zip(entry_components_of(zone), zone.entries):
        lc = comp.lower()
        if not lc.endswith(".tex") or lc.endswith("_lod.tex") or lc == low[z]:
            continue
        data = e.data()
        if not is_big(data):
            continue
        pack = BigArchive.parse(data, join(zone_vp, comp))
        for t in pack.entries:
            if t.name.lower().removesuffix(".bct") == name and t.data() == mine:
                out.append(join(zone_vp, comp, t.name))
    return out


def _read_strings(tree: AssetTree, node, src: Path) -> dict[int, str]:
    """A ``.bcs.json`` override's changes, ids resolved (labels through ``str_id``)."""
    from ..formats import bcs
    bcs.StringBank.parse(node.data(), node.vpath)         # the target must be a bank
    by_label = None
    folder = node.vpath.rsplit("/", 1)[0]
    try:
        ids = tree.resolve(f"{folder}/{bcs.LABEL_BANK}.bcs").data()
        by_label = {v.upper(): k for k, v in bcs.StringBank.parse(ids).strings.items()}
    except Dr2Error:
        pass
    text = src.read_text("utf-8-sig")
    out = bcs.from_json(text, src.name, by_label)
    copies = json.loads(text).get("copy") or {}
    if copies:                                     # text from the other game (phase 15)
        out = {**_copied_strings(node.vpath, copies, src.name), **out}
    return out


def _copied_strings(bank_vp: str, copies: dict, where: str) -> dict[int, str]:
    """``"copy": {"<new id>": {"from": "cw", "id": 50324}}`` of a ``.bcs.json``: each new
    id gets that string of the source game's bank of the same language (its English one
    when it has no such bank), read when the mod is built, so the mod holds no game
    text (`dr2kit.convert.crossgame`)."""
    from ..convert.crossgame import source_tree
    from ..formats import bcs
    banks: dict[tuple[str, str], object] = {}
    out = {}
    for k, spec in copies.items():
        if not str(k).isdigit() or not isinstance(spec, dict) or "id" not in spec:
            raise Dr2Error(f'{where}: copy {k!r}: write "<new id>": {{"from": "cw", "id": n}}')
        g = str(spec.get("from", "")).lower()
        tree = source_tree(g, where)
        if (g, bank_vp) not in banks:
            for vp in (bank_vp, "data/frontend/str_en.bcs"):
                try:
                    banks[(g, bank_vp)] = bcs.StringBank.parse(tree.resolve(vp).data(), vp)
                    break
                except Dr2Error:
                    continue
            else:
                raise Dr2Error(f"{where}: {g} has no string bank {bank_vp}")
        bank = banks[(g, bank_vp)]
        if int(spec["id"]) not in bank.strings:
            raise Dr2Error(f"{where}: {g}'s {bank_vp} has no string {spec['id']}")
        out[int(k)] = bank.strings[int(spec["id"])]
    return out


def _read_edits(node, src: Path):
    """A ``.edits.json`` override, its target checked to be a block text file."""
    from ..formats import leveledits
    from ..formats.levelscript import Document
    Document.parse(node.data(), node.vpath)
    return leveledits.from_json(src.read_text("utf-8-sig"), src.name)


def _read_pieces(node, src: Path):
    """A ``.pieces.json`` override, its target checked to be a zone's
    ``ZONE_ORGANIZATION.big``."""
    from ..formats import pieceedits
    if split(node.vpath)[-1].lower() not in [t.lower() for t in pieceedits.TARGETS] or \
            not is_big(node.data()):
        raise ModError(f"{PIECES_EXT} goes next to a zone's {pieceedits.TARGET} or "
                       f"{pieceedits.COLLISION}, not {node.vpath}")
    return pieceedits.from_json(src.read_text("utf-8-sig"), src.name)


def _piece_layer(p: Planned):
    from ..formats.pieceedits import Layer
    return Layer(p.mod.id, p.mod.priority, p.edits)


def _apply_pieces(items: list[Planned], original: bytes) -> bytes:
    """``ZONE_ORGANIZATION.big`` or ``MERGED_COLLISION.big`` with every ``.pieces.json``
    in ``items`` merged and applied."""
    from ..formats import pieceedits
    merged, _sh, problems = pieceedits.merge([_piece_layer(p) for p in items])
    if problems:
        raise ModError(f"{items[0].vpath}: " + "; ".join(problems))
    return pieceedits.target_bytes(original, merged, items[0].vpath)


def _layer(p: Planned):
    from ..formats.leveledits import Layer
    return Layer(p.mod.id, p.mod.priority, p.edits)


def _apply_edits(items: list[Planned], original: bytes) -> tuple[bytes, list[str]]:
    """The text file ``original`` with every ``.edits.json`` in ``items`` applied, lowest
    priority first (so the highest wins)."""
    from ..formats.leveledits import apply_all
    return apply_all(original, [_layer(p) for p in items], items[0].vpath)


def merged_bytes(items: list[Planned], original: bytes) -> bytes:
    """The bytes of one asset that several overrides of a merged kind change together
    (strings by id, level edits by block), or the one override's bytes."""
    kind = items[0].override.kind
    if kind == "strings":
        return _apply_strings(items, original)
    if kind == "edits":
        return _apply_edits(items, original)[0]
    if kind == "pieces":
        return _apply_pieces(items, original)
    return new_bytes(items[-1], original)


def _apply_strings(items: list[Planned], original: bytes, notes: list | None = None) -> bytes:
    """The bank ``original`` with every string override in ``items`` applied, lowest
    priority first (so the highest wins)."""
    from ..formats import bcs
    bank = bcs.StringBank.parse(original, items[0].vpath)
    for p in sorted(items, key=lambda p: p.mod.priority):
        bank, n = bcs.apply(bank, p.strings, f"{p.mod.id}: {p.vpath}")
        if notes is not None:
            notes += n
    return bank.to_bytes()


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


def _check_effect(node, src: Path) -> str | None:
    """Why an ``.effect.json`` can't apply to ``node``, or None (a dry run)."""
    from ..formats.effect import is_effect
    if not is_effect(node.data()[:4]):
        return f"{node.vpath} is not a particle effect"
    try:
        effect_bytes(node.data(), src, node.vpath)
    except Dr2Error as e:
        return str(e)
    return None


def effect_bytes(original: bytes, src: Path, vpath: str) -> bytes:
    """An effect with an ``.effect.json``'s changes applied (`convert.effects`)."""
    from ..convert.effects import apply_changes
    from ..formats.effect import Effect
    fx = Effect.parse(original, vpath)
    try:
        doc = json.loads(Path(src).read_text("utf-8"))
    except ValueError as e:
        raise Dr2Error(f"not JSON: {e}") from None
    if doc.get("format") != EFFECT_FORMAT:
        raise Dr2Error(f"not a {EFFECT_FORMAT} file")
    if doc.get("effect") and doc["effect"].lower() != fx.name.lower():
        raise Dr2Error(f"made for the effect {doc['effect']!r}, but this entry is "
                       f"{fx.name!r} in this game")
    return apply_changes(fx, doc.get("changes") or {}).to_bytes()


def new_bytes(p: Planned, original: bytes) -> bytes:
    """The replacement bytes for one override, given the asset's current bytes."""
    if p.override.kind in ("add", "file") and p.data is not None:
        return p.data
    if p.override.kind in ("raw", "add", "file"):
        return p.override.source.read_bytes()
    if p.override.kind in MERGED:
        return merged_bytes([p], original)
    if p.override.kind == "effect":
        try:
            return effect_bytes(original, p.override.source, p.vpath)
        except Dr2Error as e:
            raise ModError(f"{p.mod.id}: replace/{p.vpath}{EFFECT_EXT}: {e}") from None
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
    which must be an archive) or a list of `Planned` leaves (several when they merge:
    strings, level edits). Compressed entries are re-compressed.
    """
    arc = BigArchive.parse(data, vpath)
    added = []
    for comp, sub in edits.items():
        if isinstance(sub, list) and sub[0].override.kind == "add":
            add_entry(arc, comp, new_bytes(sub[-1], b""))
            added.append(comp)
            continue
        if isinstance(sub, list) and sub[0].override.kind == "evict":
            evict_entry(arc, comp)
            continue
        entry = find_entry(arc, comp)
        evp = join(vpath, entry_component(arc, entry))
        current = entry.data()
        if isinstance(sub, dict):
            if not is_big(current):
                raise ModError(f"{evp}: not an archive, nothing can be replaced inside it")
            updated = patch_archive(current, evp, sub)
        else:
            updated = merged_bytes(sub, current)
        entry.set_data(updated)
    if added:
        register_in_scene(arc, added)
    return arc.to_bytes()


SCENE_EFFECT = 13          # SceneDescription kind of an EFFECT_Common<k> chunk (effects.big)


def register_in_scene(arc: BigArchive, names: list[str]) -> None:
    """List new particle effects in their scene (``data/models/effects.big``): the game
    loads the chunks ``SceneDescription`` lists (32-byte name + u32 kind, 13 for an
    effect), counted by ``SceneHeader``'s word 3, not every entry of the archive
    (measured in phase 13: an added effect not listed never showed). Other archives:
    nothing to do."""
    import struct
    names = [n for n in names if n.upper().startswith("EFFECT_")]
    try:
        desc = find_entry(arc, "SceneDescription")
        head = find_entry(arc, "SceneHeader")
    except Dr2Error:
        return
    if not names:
        return
    d = bytearray(desc.data())
    listed = {bytes(d[i:i + 32]).split(b"\0")[0].decode("latin-1").lower()
              for i in range(0, len(d), 36)}
    for n in names:
        if n.lower() in listed:
            continue
        if len(n.encode()) >= 32:
            raise ModError(f"{n}: a scene chunk name is at most 31 characters")
        d += n.encode().ljust(32, b"\0") + struct.pack(">I", SCENE_EFFECT)
    h = bytearray(head.data())
    struct.pack_into(">I", h, 12, len(d) // 36)
    desc.set_data(bytes(d))
    head.set_data(bytes(h))


def _added_scripts(facts, plan: dict) -> None:
    """Level scripts the mods add (phase 14, maps of one's own: ``add/…/datafile.big/
    <x>.txt`` with ``waypoint_<x>.txt`` or ``nm_<x>.txt``) count as levels for the level
    checks, with their spawn points and zombie areas, so a door can lead to them and a
    mission can spawn zombies there."""
    from ..formats.levelscript import Document
    added = {p.vpath.rsplit("/", 1)[-1].lower(): p for p in plan.values()
             if p.override.kind == "add" and p.vpath.lower().startswith("data/datafile.big/")}
    for name, p in added.items():
        if not name.endswith(".txt") or name.startswith(("waypoint_", "nm_")):
            continue
        stem = name[:-4]
        if f"waypoint_{stem}.txt" not in added and f"nm_{stem}.txt" not in added:
            continue
        try:
            doc = Document.parse(new_bytes(p, b""), p.vpath)
        except Dr2Error:
            facts.add_script(stem)
            continue
        facts.add_script(stem, doc)


def _new_file_folder(tree: AssetTree, parent: str) -> str | None:
    """Where an ``add/`` file goes when it is a new file (kind ``file``): its folder's
    vpath with the game's letter case for the part that exists (new folders as written),
    or None when ``parent`` is (inside) an archive: then it is a new entry."""
    parts = split(parent)
    if not parts or parts[0].lower() != "data":
        return None
    here, out = tree.root, []
    for i, p in enumerate(parts):
        nxt = next((c for c in here.iterdir() if c.name.lower() == p.lower()), None) \
            if here.is_dir() else None
        if nxt is None:
            return join(*out, *parts[i:]) if here.is_dir() else None
        if nxt.is_file():
            return None                                  # an archive on disk
        out.append(nxt.name)
        here = nxt
    return join(*out)


def evict_entry(arc: BigArchive, name: str) -> None:
    """Make the game's lookups miss entry ``name`` of ``arc`` (its index hash changed, its
    bytes kept), so it reads the loose file instead (`PRELOAD`). Already evicted (by the
    recomp's own patched copy): left alone."""
    e = find_entry(arc, name)
    if e.hash == e.computed_hash():
        e.hash ^= EVICT_XOR


def add_entry(arc: BigArchive, name: str, data: bytes) -> None:
    """Put a new entry ``name`` into ``arc`` where the name order puts it (where most
    archives have their entries; 1,724 of CZ's 3,717 follow no order, so the place is
    free: docs/formats.md §`.big` container), compressed like most of its neighbours
    (the game expects an LZX entry where its siblings are; CLAUDE.md rule 4)."""
    from ..container.big import LZX, STORED
    comp = LZX if sum(e.compression == LZX for e in arc.entries) * 2 > len(arc.entries) \
        else STORED
    e = arc.add(name, data, compression=comp)
    arc.entries.remove(e)
    at = next((i for i, x in enumerate(arc.entries) if x.name.lower() > name.lower()),
              len(arc.entries))
    arc.entries.insert(at, e)


def build(mods: list[Mod], game: str, tree: AssetTree, out_dir: str | Path,
          base_dirs: list[Path] | tuple = (), progress=None) -> BuildResult:
    """Build ``mods`` for ``game`` into ``out_dir`` (laid out like the game root).

    Returns a `BuildResult`; raises `ModError` (nothing written) if the plan is invalid.
    ``progress(message)`` is called per file written.
    """
    out = Path(out_dir)
    mplan = plan_mods(mods, game, tree)
    plan = mplan.planned
    res = BuildResult(game, out, overrides=plan, shadowed=mplan.shadowed,
                      warnings=list(mplan.notes))
    by_file: dict[str, list[Planned]] = {}
    sounds = [p for p in plan if p.override.kind == "audio"]
    if sounds:
        from .audio import build_audio
        build_audio(sounds, tree, out, res, progress)
    for p in plan:
        if p.override.kind == "audio":
            continue
        file_vp = join(*split(p.vpath)[:p.disk_parts])
        by_file.setdefault(file_vp, []).append(p)
    for file_vp, items in sorted(by_file.items()):
        if items[0].override.kind == "file":           # a new file: its bytes as they are
            dest = out.joinpath(*split(file_vp))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(new_bytes(items[-1], b""))
            res.files.append(file_vp)
            res.new_files.append(file_vp)
            if progress:
                progress(file_vp)
            continue
        src = tree.root.joinpath(*split(file_vp))
        base = next((Path(b) for b in base_dirs if Path(b).joinpath(*split(file_vp)).is_file()),
                    None)
        if base is not None:
            src = base.joinpath(*split(file_vp))
            res.base_used[file_vp] = str(base)
            for p in items:                         # a whole replacement wipes its edits
                if p.override.kind == "raw" and p.disk_parts < len(split(p.vpath)):
                    try:
                        if AssetTree(base).resolve(p.vpath).data() != \
                                tree.resolve(p.vpath).data():
                            res.warnings.append(
                                f"{p.mod.id}: replaces {p.vpath} as a whole, so the "
                                f"recomp's own changes to it are lost; an .edits.json "
                                f"keeps them (dr2 level diff makes one)")
                    except Dr2Error:
                        pass
        data = src.read_bytes()
        whole = [p for p in items if p.disk_parts == len(split(p.vpath))]
        if whole:                                  # the file itself (merged kinds: all)
            data = merged_bytes(whole, data)
        else:
            edits: dict = {}
            for p in items:
                comps = split(p.vpath)[p.disk_parts:]
                node = edits
                for c in comps[:-1]:
                    node = node.setdefault(c, {})
                node.setdefault(comps[-1], []).append(p)
            data = patch_archive(data, file_vp, edits)
        dest = out.joinpath(*split(file_vp))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        res.files.append(file_vp)
        if progress:
            progress(file_vp)
    from .requires import infer
    if repin_layout(res, tree, base_dirs):
        res.files.append(LAYOUT)
    verify(res, tree, base_dirs)
    info = {
        "game": game,
        "mods": [{"id": m.id, "version": m.version, "priority": m.priority,
                  "requires": infer(m, with_hash=True).to_json()} for m in mods
                 if game in m.games],
        "files": {f: hashlib.sha1(out.joinpath(*split(f)).read_bytes()).hexdigest()
                  for f in res.files},
        "overrides": [{"vpath": p.vpath, "kind": p.override.kind, "mod": p.mod.id}
                      for p in plan],
        "shadowed": [{"what": w, "lost": a, "won": b} for w, a, b in res.shadowed],
        "base_used": res.base_used,
    }
    (out / BUILD_INFO).write_text(json.dumps(info, indent=1), "utf-8")
    return res


LAYOUT = "layout.bin"
LAYOUT_RECORD = 152                 # name (128), a word, BE size at +132, disc position
LAYOUT_ALIGN = 0x800                # a file's disc position: the one before's end, rounded


def new_layout_record(vpath: str, size: int, position: int) -> bytes:
    """A ``layout.bin`` record for a file the game doesn't have (phase 14): its name, a
    hash word left 0 (the game works the name's hash out itself when it reads the table
    and keeps that: CZ ``0x82786230``), its size, and a disc position after every other
    file (a 64-bit number at +136; files are laid out every 0x800 bytes)."""
    name = vpath.encode("latin-1")
    if len(name) >= 128:
        raise ModError(f"{vpath}: a file name is at most 127 characters")
    return (name.ljust(128, b"\0") + (0).to_bytes(4, "big") + size.to_bytes(4, "big")
            + position.to_bytes(8, "big") + bytes(8))


def repin_layout(res: BuildResult, tree: AssetTree, base_dirs=()) -> bool:
    """Write ``layout.bin`` into the build with the built files' sizes, when one changed,
    and a record for every new file (`new_layout_record`).

    Why: ``layout.bin`` (the game root's, opened first) pins every file's size in
    152-byte records (the name, then the size big-endian at +132), and the loader reads a
    file by that size. A file that grew is cut short: measured in phase 13, an
    ``effects.big`` 4 KB larger crashed the game as soon as it was opened; the CZ
    recomp's own patcher re-pins the files it changes the same way
    (``runtime/host/overlay_gen.cpp``). The copy re-pinned is the recomp's patched one
    when it has one (its own pins kept). Returns True when a ``layout.bin`` was written."""
    src = next((Path(b) / LAYOUT for b in base_dirs if (Path(b) / LAYOUT).is_file()),
               tree.root / LAYOUT)
    if not src.is_file():
        return False
    data = bytearray(src.read_bytes())
    sizes = {f.lower(): res.out_dir.joinpath(*split(f)).stat().st_size for f in res.files}
    changed = False
    listed, end = set(), 0
    for at in range(0, len(data) - LAYOUT_RECORD + 1, LAYOUT_RECORD):
        name = bytes(data[at:at + 128]).split(b"\0")[0].decode("latin-1").lower()
        listed.add(name)
        size = sizes.get(name)
        if size is not None and int.from_bytes(data[at + 132:at + 136], "big") != size:
            data[at + 132:at + 136] = size.to_bytes(4, "big")
            changed = True
        old = int.from_bytes(data[at + 132:at + 136], "big")
        end = max(end, int.from_bytes(data[at + 136:at + 144], "big") + old)
    for f in getattr(res, "new_files", []):
        if f.lower() in listed:
            continue
        end = (end + LAYOUT_ALIGN - 1) // LAYOUT_ALIGN * LAYOUT_ALIGN
        data += new_layout_record(f, sizes[f.lower()], end)
        end += sizes[f.lower()]
        changed = True
    if changed:
        (res.out_dir / LAYOUT).write_bytes(bytes(data))
    return changed


def verify(res: BuildResult, tree: AssetTree, base_dirs=()) -> None:
    """Read every override back from the build and check it is what was meant.

    For a texture or a model, "what was meant" is the replacement built again from the
    original; for a raw override, the file's bytes. Raises `ModError` on any difference.
    """
    built = AssetTree(res.out_dir)
    banks: dict[str, list[Planned]] = {}
    for p in res.overrides:
        if p.override.kind == "strings":
            banks.setdefault(p.vpath.lower(), []).append(p)
    texts: dict[str, list[Planned]] = {}
    for p in res.overrides:
        if p.override.kind == "edits":
            texts.setdefault(p.vpath.lower(), []).append(p)
    for items in texts.values():
        got = built.resolve(items[0].vpath).data()
        if got != _apply_edits(items, _original(tree, base_dirs, items[0]))[0]:
            raise ModError(f"build check failed: {items[0].vpath} reads back differently")
    zones: dict[str, list[Planned]] = {}
    for p in res.overrides:
        if p.override.kind == "pieces":
            zones.setdefault(p.vpath.lower(), []).append(p)
    for items in zones.values():
        got = built.resolve(items[0].vpath).data()
        if got != _apply_pieces(items, _original(tree, base_dirs, items[0])):
            raise ModError(f"build check failed: {items[0].vpath} reads back differently")
    for items in banks.values():
        got = built.resolve(items[0].vpath).data()
        if got != _apply_strings(items, _original(tree, base_dirs, items[0])):
            raise ModError(f"build check failed: {items[0].vpath} reads back differently")
        from ..formats.bcs import StringBank
        final = StringBank.parse(got, items[0].vpath).strings
        winner = {}
        for p in sorted(items, key=lambda p: p.mod.priority):
            winner.update(p.strings)
        if any(final.get(i) != t for i, t in winner.items()):
            raise ModError(f"build check failed: {items[0].vpath} lost a string")
    for p in res.overrides:
        if p.override.kind in ("audio", *MERGED):     # audio: checked by build_audio
            continue
        if p.override.kind == "evict":                # its bytes stay; the hash changed
            continue
        got = built.resolve(p.vpath).data()
        if p.override.kind in ("raw", "add", "file"):
            want = new_bytes(p, b"")
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

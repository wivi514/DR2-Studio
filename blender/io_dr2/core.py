# SPDX-License-Identifier: GPL-3.0-or-later
"""What the add-on's buttons do, without Blender: search, export, check, write to a mod.

Every function here calls dr2kit (loaded by `toolkit.load`) and returns plain Python
values, so the logic is tested outside Blender (``tests/test_blender_addon.py``) and the
Blender side (``__init__.py``) is only buttons and the glTF importer/exporter. No format
knowledge lives here either: it is the same dr2kit calls as ``dr2 index search``,
``dr2 extract --glb`` and ``dr2 model check``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SCENE_KINDS = ("model", "skeleton")


@dataclass
class Found:
    """One search result."""
    vpath: str
    name: str
    kind: str
    size: int


def index_path() -> Path:
    from dr2kit.index.build import default_db_path
    return default_db_path()


def search(game: str, text: str, kind: str = "", limit: int = 200) -> list[Found]:
    """Models and skeletons of ``game`` whose name matches ``text`` (the index's rules:
    words, ``*`` and ``?``). Raises ``RuntimeError`` when there is no index yet."""
    from dr2kit.index import query
    from dr2kit.index.build import connect
    db = index_path()
    if not db.is_file():
        raise RuntimeError(f"No asset index yet ({db}). Build it once with DR2 Studio "
                           f"(Build / refresh index) or `dr2 index build`.")
    con = connect(db)
    try:
        kinds = [kind] if kind else list(SCENE_KINDS)
        rows = []
        for k in kinds:
            rows += query.search(con, text or "*", game=game, kind=k, limit=limit)
    finally:
        con.close()
    if not rows and not any(r["n"] for r in _counts(game)):
        raise RuntimeError(f"The index has nothing for {game}: build it with DR2 Studio "
                           f"or `dr2 index build {game}`.")
    rows.sort(key=lambda r: r["vpath"].lower())
    return [Found(r["vpath"], r["name"], r["kind"], r["size"]) for r in rows[:limit]]


def _counts(game: str):
    from dr2kit.index import query
    from dr2kit.index.build import connect
    con = connect(index_path())
    try:
        return [r for r in query.counts(con) if r["game"] == game]
    finally:
        con.close()


def tree(game: str):
    from dr2kit.container.vpath import AssetTree
    from dr2kit.profiles import locate
    return AssetTree(locate(game).root)


def export_glb(game: str, vpath: str, skeleton_only: bool = False,
               textures: bool = True) -> tuple[bytes, str, list[str]]:
    """The asset as ``.glb`` bytes, a one-line summary, and notes (missing textures)."""
    from dr2kit.convert import gltf
    from dr2kit.convert.model import export_glb as model_glb
    from dr2kit.convert.model import export_skeleton_glb, read_scene
    t = tree(game)
    scene = read_scene(t, vpath)
    if skeleton_only or not scene.meshes:
        return export_skeleton_glb(t, vpath), f"{len(scene.skeleton)} bones", []
    st = gltf.ExportStats()
    data = model_glb(t, vpath, game=game, textures=textures, stats=st)
    summary = (f"{st.meshes} meshes, {st.triangles:,} triangles, {len(scene.skeleton)} "
               f"bones, {st.textures} textures")
    notes = [f"texture {n!r} not found" for n in st.missing_textures]
    return data, summary, notes


@dataclass
class Check:
    """The rig validator's verdict on a ``.glb`` for a model."""
    ok: bool
    report: str          # `dr2kit.convert.model_import.format_plan`
    errors: int
    warnings: int


def check(game: str, vpath: str, glb: bytes, name: str = "blender export") -> Check:
    """Run the rig validator (``dr2 model check``) on ``glb`` against the model."""
    from dr2kit.convert.model_import import format_plan, plan_import
    from dr2kit.formats.scene import Scene
    data = tree(game).resolve(vpath).data()
    plan = plan_import(Scene.parse(data, vpath), glb, name)
    warnings = len(plan.issues) - len(plan.errors)
    return Check(plan.ok, format_plan(plan), len(plan.errors), warnings)


def write_to_mod(mod_folder: str, game: str, vpath: str, glb: bytes) -> Path:
    """Put ``glb`` in a mod as ``replace/<vpath>.glb`` (creating the mod if the folder
    has no ``mod.toml``; its ``games`` then lists only ``game``). Returns the file."""
    from dr2kit.mods.manifest import MANIFEST, REPLACE_DIR, Mod, create
    root = Path(mod_folder).expanduser()
    if not (root / MANIFEST).is_file():
        create(root)
        text = (root / MANIFEST).read_text("utf-8").replace(
            'games = ["cz", "cw"]', f'games = ["{game}"]')
        (root / MANIFEST).write_text(text, "utf-8")
    mod = Mod.load(root)
    if game not in mod.games:
        raise RuntimeError(f"The mod {mod.id} is not for {game} (games = {list(mod.games)} "
                           f"in its mod.toml)")
    dest = root / REPLACE_DIR / (vpath + ".glb")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(glb)
    return dest


# ---- levels (dr2kit phase 10) ------------------------------------------------------------

def levels(game: str) -> list[tuple[str, list[str]]]:
    """The game's levels and their zones: ``[("prologue", ["prologue_z01", …]), …]``."""
    from dr2kit.convert.level import list_levels
    return [(L.name, L.zone_names()) for L in list_levels(tree(game))]


def level_scripts(game: str, level: str) -> list[str]:
    """The item sets of a level (its own first): ``["prologue", "prologue_safehouse"]``."""
    from dr2kit.convert.mapdata import scripts_of
    return scripts_of(tree(game), level)


def export_level_zone(game: str, level: str, zone: str, script: str = "",
                      items: bool = True, markers: bool = True,
                      lod: bool = False) -> tuple[bytes, str, list[str]]:
    """One zone as ``.glb`` bytes (pieces, items, markers: dr2kit's ``dr2 export <level>
    --zone``), a summary and notes (what could not be exported)."""
    from dr2kit.catalog.level_export import DEFAULT_MARKERS, LevelExport, level_glb
    from dr2kit.convert import mapdata, placed
    from dr2kit.convert.level import Level
    t = tree(game)
    L = Level.open(t, level)
    scripts = mapdata.scripts_of(t, L.name)
    script = script or (scripts[0] if scripts else "")
    ls = placed.read_script(t, script, placed.ItemModels(t), mapdata._strings(t)) \
        if script and (items or markers) else None
    res = LevelExport(Path("."))
    data = level_glb(t, game, L, [L.find_zone(zone)], ls, items=items,
                     markers=DEFAULT_MARKERS if markers else (), lod=lod, result=res)
    summary = (f"{res.pieces} pieces, {res.items} items and doors, {res.markers} markers, "
               f"{res.triangles:,} triangles")
    return data, summary, [f"{a}: {b}" for a, b in res.failed]

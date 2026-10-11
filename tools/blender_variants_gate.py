"""Phase 9 gate, Blender part: a chosen look exports and opens in Blender as chosen.

For one zombie of each game (and a look with a colour choice), this:

1. exports it **as shown** (`convert.model.model_glb`, ``mode="shown"``) and checks, in
   Blender, that exactly the look's parts arrive;
2. exports it **everything, organised** (``mode="all"``) and opens it in Blender with
   the very script DR2 Studio's *Open in Blender* writes (`studio.edit_tools`), then
   checks that every part is in the collection of its group (*Head 2*, *Shirt 3*…), that
   exactly the look's parts are visible, and that the **glTF Variants** switch puts a
   colour choice's material on the parts that use it.

Runs Blender in the background with a throwaway user folder (``--factory-startup``,
``BLENDER_USER_RESOURCES``), so the user's Blender settings are untouched; the files go
to a temporary folder that is deleted at the end.

Usage::

    python tools/blender_variants_gate.py [--blender /usr/bin/blender]

Exit status 0 when every check passed. Needs the game data of both games (a game that
is missing is skipped, saying so).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CASES = [
    ("cz", "data/models/zombies.big/zombie_skinny.big/zombie_skinny_2.big",
     "head=3 headwear=none shirt=2 pants=3 colour.shirt2=3", "shirt2 3"),
    ("cw", "data/models/zombies.big/zombie_fat_female.big/zombie_fat_female_2.big",
     "head=4 headwear=2 shirt=3 pants=none skirt=1 tallboots=1 feet=none "
     "colour.cleavgshirt=2", "cleavgshirt 2"),
]

INSIDE = r'''
import bpy, json, sys
args = sys.argv[sys.argv.index("--") + 1:]
mode, glb, script, out = args
res = {}
if mode == "shown":
    bpy.ops.wm.read_factory_settings(use_empty=True)
    props = bpy.ops.import_scene.gltf.get_rna_type().properties   # no bone-shape Icosphere
    bpy.ops.import_scene.gltf(filepath=glb, **({"disable_bone_shape": True}
                                               if "disable_bone_shape" in props else {}))
    res["meshes"] = sorted(o.name for o in bpy.data.objects if o.type == "MESH")
else:
    exec(open(script).read(), {"__name__": "__main__"})     # Studio's Open in Blender script
    top = next(c for c in bpy.data.collections if c.get("dr2_vpath"))
    res["groups"] = {c.name: sorted(o.name for o in c.objects) for c in top.children}
    res["visible"] = sorted(o.name for o in top.all_objects
                            if o.type == "MESH" and o.visible_get())
    res["variants"] = [v.name for v in bpy.context.scene.gltf2_KHR_materials_variants_variants]
    want = args and json.loads(open(out + ".want").read())
    idx = res["variants"].index(want["variant"])
    bpy.context.scene.gltf2_active_variant = idx
    bpy.ops.scene.gltf2_display_variant()
    res["switched"] = sorted({s.material.name for o in top.all_objects if o.type == "MESH"
                              for s in o.material_slots
                              if s.material and want["variant"] in s.material.name})
open(out, "w").write(json.dumps(res))
'''


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--blender", default=shutil.which("blender") or "blender")
    a = ap.parse_args(argv)
    from dr2kit.container.vpath import AssetTree
    from dr2kit.convert.model import model_glb, read_scene
    from dr2kit.convert.variants import read_variants
    from dr2kit.errors import GameNotFoundError
    from dr2kit.profiles import locate
    from dr2kit.studio.edit_tools import BLENDER_SCRIPT

    work = Path(tempfile.mkdtemp(prefix="dr2-variants-gate-"))
    env = dict(os.environ, BLENDER_USER_RESOURCES=str(work / "blender-user"))
    inside = work / "inside.py"
    inside.write_text(INSIDE, "utf-8")
    failed = 0
    try:
        for game, vpath, look, variant in CASES:
            try:
                tree = AssetTree(locate(game).root)
            except GameNotFoundError as e:
                print(f"SKIP {game}: {e}")
                continue
            sc = read_scene(tree, vpath)
            mv = read_variants(tree, sc, game)
            choice = mv.parse(look)
            shown = sorted(p.name for p, s in zip(mv.parts, mv.shown(choice)) if s)
            groups: dict[str, list[str]] = {}
            for p in mv.parts:
                groups.setdefault(p.group, []).append(p.name)
            name = vpath.rsplit("/", 1)[-1]
            checks = []
            for mode in ("shown", "all"):
                glb = work / f"{game}_{mode}.glb"
                glb.write_bytes(model_glb(tree, sc, game=game, variant=choice, mode=mode,
                                          variants=mv))
                script = work / f"{game}_{mode}_open.py"
                script.write_text(BLENDER_SCRIPT.format(job=json.dumps(
                    {"game": game, "vpath": vpath, "glb": str(glb), "name": name, "mod": ""})),
                    "utf-8")
                out = work / f"{game}_{mode}.json"
                (work / f"{game}_{mode}.json.want").write_text(json.dumps({"variant": variant}))
                r = subprocess.run([a.blender, "-b", "--factory-startup", "--python",
                                    str(inside), "--", mode, str(glb), str(script), str(out)],
                                   env=env, capture_output=True, text=True, timeout=600)
                if not out.is_file():
                    print(r.stdout[-2000:], r.stderr[-2000:])
                    checks.append((f"{mode}: Blender ran", False))
                    continue
                res = json.loads(out.read_text())
                if mode == "shown":
                    if res["meshes"] != shown:
                        print("   shown diff:", sorted(set(res["meshes"]) ^ set(shown)))
                    checks.append((f"as shown: Blender has exactly the look's "
                                   f"{len(shown)} parts", res["meshes"] == shown))
                else:
                    got = {g: sorted(v) for g, v in res["groups"].items()}
                    checks.append((f"organised: {len(got)} group collections, each with its "
                                   f"parts", got == {g: sorted(v) for g, v in groups.items()}))
                    checks.append(("organised: only the look's parts visible",
                                   res["visible"] == shown))
                    checks.append((f"organised: {len(res['variants'])} colour choices in "
                                   f"glTF Variants", len(res["variants"]) == sum(
                                       len(c.options) for c in mv.colours)))
                    checks.append((f"organised: '{variant}' switches material(s) "
                                   f"{res['switched']}", bool(res["switched"])))
            print(f"== {game} {name}  look: {choice.text()}")
            for text, ok in checks:
                print(f"   {'PASS' if ok else 'FAIL'}  {text}")
                failed += not ok
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("gate passed" if not failed else f"{failed} check(s) failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

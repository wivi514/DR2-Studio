"""Phase 3 skeleton gate: game rig → .glb → Blender import → Blender export → records.

For every skeleton (``data/skeleton/*.big``, or every scene with ``--all-scenes``) of the
chosen games, this exports the rig with `dr2kit.convert.gltf.skeleton_to_glb`, has
Blender import it and export it again (one headless Blender run for the whole batch),
reads the result back with `skeleton_from_glb`, and compares every 52-byte node record
with the game's bytes. The gate passes when every record is bit-identical.

It also reports the largest raw difference Blender introduced before snapping (float
noise from storing bones as matrices), so a change in Blender's behaviour shows up as a
number, not as a silent snap.

Usage (from the repository root, dev venv active):
    python tools/blender_skeleton_gate.py [cz] [cw] [--all-scenes] [--blender PATH]

Needs Blender (4.2+; tested with 5.2) and the game data. Nothing is written to the
repository: the .glb files go to a temporary folder that is deleted afterwards.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BLENDER_SCRIPT = r"""
import bpy, json, sys
jobs = json.loads(open(sys.argv[sys.argv.index('--') + 1]).read())
for src, out in jobs:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    bpy.ops.import_scene.gltf(filepath=src)
    bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', export_extras=True)
    print('DR2GATE done', out, flush=True)
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("games", nargs="*", default=["cz", "cw"])
    ap.add_argument("--all-scenes", action="store_true",
                    help="every scene with a skeleton (models too), not just data/skeleton")
    ap.add_argument("--blender", default=shutil.which("blender") or "blender")
    args = ap.parse_args()

    from dr2kit.container.vpath import AssetTree
    from dr2kit.convert.gltf import Glb, skeleton_from_glb, skeleton_to_glb
    from dr2kit.formats.scene import Scene, is_scene

    tmp = Path(tempfile.mkdtemp(prefix="dr2gate-"))
    try:
        jobs, originals = [], {}
        for game in args.games:
            tree = AssetTree.for_game(game)
            for vp, arc, _ in tree.walk_archives():
                if not is_scene(arc):
                    continue
                if not args.all_scenes and not vp.lower().startswith("data/skeleton/"):
                    continue
                scene = Scene.from_archive(arc, vp)
                if not scene.skeleton.nodes:
                    continue
                n = len(jobs)
                src, out = tmp / f"{n}.glb", tmp / f"{n}_rt.glb"
                src.write_bytes(skeleton_to_glb(scene))
                jobs.append((str(src), str(out)))
                originals[str(out)] = (game, vp, scene.skeleton.nodes)
        print(f"{len(jobs)} rigs exported; running Blender ({args.blender})", file=sys.stderr)
        (tmp / "jobs.json").write_text(json.dumps(jobs))
        (tmp / "gate.py").write_text(BLENDER_SCRIPT)
        r = subprocess.run([args.blender, "-b", "--factory-startup", "--python",
                            str(tmp / "gate.py"), "--", str(tmp / "jobs.json")],
                           capture_output=True, text=True)
        if r.returncode:
            print(r.stdout[-3000:], r.stderr[-3000:], file=sys.stderr)
            return 1

        total = same = 0
        worst = [0.0, 0.0, 0.0]
        failures = []
        for out, (game, vp, nodes) in originals.items():
            data = Path(out).read_bytes()
            g = Glb.parse(data, out)
            by_index = {n.index: n for n in nodes}
            for node in g.gltf.get("nodes", []):
                meta = (node.get("extras") or {}).get("dr2")
                if isinstance(meta, str):
                    meta = json.loads(meta)
                if not meta:
                    continue
                o = by_index[meta["index"]]
                pairs = [(node.get("translation", [0, 0, 0]), o.translation),
                         (node.get("rotation", [0, 0, 0, 1]), o.rotation),
                         (node.get("scale", [1, 1, 1]), o.scale)]
                for k, (a, b) in enumerate(pairs):
                    d = max(abs(x - y) for x, y in zip(a, b))
                    if k == 1:
                        d = min(d, max(abs(-x - y) for x, y in zip(a, b)))
                    worst[k] = max(worst[k], d)
            back = {n.index: n for n in skeleton_from_glb(data, out)}
            for n in nodes:
                total += 1
                b = back.get(n.index)
                if b is not None and b.to_bytes() == n.to_bytes() and b.name == n.name:
                    same += 1
                else:
                    failures.append(f"{game} {vp}: node {n.index} {n.name}")
        print(f"rigs: {len(originals)}   node records: {total}   bit-identical: {same}")
        print(f"largest raw difference Blender introduced: translation {worst[0]:.2e}, "
              f"rotation {worst[1]:.2e}, scale {worst[2]:.2e}")
        for f in failures[:50]:
            print("  DIFFERS", f)
        return 0 if same == total else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

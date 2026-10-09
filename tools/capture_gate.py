"""Phase 3 in-game gate: check the model reader against draws the game really made.

Input: a folder of ``vsdump_*.bin`` files written by the Case Zero recomp
(``CZ_CAPTURE_DUMP_VS=<vertex shader hash>`` + ``CZ_CAPTURE_KEY=<dir>`` + an F9 press;
docs/dev/recomp-integration.md §"Phase 3 capture"). Each dump holds, for one draw of
the captured frame: the 256 vertex-shader constants, the raw bytes of the draw's first
vertex stream, and its index buffer.

What it checks, for every dump it can match to a draw of a model in the game data:

1. **Same bytes.** The dumped vertex stream and indices equal the buffers
   `dr2kit.formats.scene` picked for that draw (so the reader found the right buffers,
   strides and index ranges).
2. **Bone palettes.** The game uploads one 3×4 matrix per palette slot (constants
   ``c8 + 3·slot``). The reader says slot *k* of a draw is skeleton node
   ``palette_start + k``. Two draws of the same character in the same frame that share
   a node must then receive the *identical* matrix for it. Checked for every pair of
   draws, and for shifted palettes (start ± 1, ± 2) as a control, which must fail.
3. **Skeleton.** Each palette matrix is (posed node) × (rest node)⁻¹. Multiplying by the
   reader's rest pose gives the posed nodes; a child's offset from its parent must then
   have the length of the game's 52-byte record (animation rotates bones, it does not
   stretch them), so the rest pose the reader builds is the one the game skins with.
4. **Picture** (``--overlay out.png``): every vertex, skinned the way the reader exports
   it (joints + weights) with the game's matrices and projected with the game's camera
   (``c0``-``c3``, ``c4``-``c6``), is drawn as a dot on the captured frame.

Usage:
    python tools/capture_gate.py <capture dir> [--game cz] [--models data/models/npcs.big]
                                 [--overlay overlay.png]
"""

from __future__ import annotations

import argparse
import glob
import math
import os
import struct
import sys
from collections import defaultdict

DUMP_MAGIC = 0x504D5544


def load_dump(path: str) -> dict:
    """One vsdump file (layout: the CZ recomp's tools/vsdump_skin.py)."""
    b = open(path, "rb").read()
    hdr = struct.unpack("<16I", b[:64])
    if hdr[0] != DUMP_MAGIC:
        raise SystemExit(f"{path}: not a vsdump")
    (_, _, draw, prim, icount, indexed, i32, iend, va, sizedw, vend, stride, ib) = hdr[:13]
    consts = struct.unpack("<1024f", b[64:64 + 4096])
    off = 64 + 4096
    vbytes = b[off:off + sizedw * 4]
    off += sizedw * 4
    return dict(path=path, draw=draw, prim=prim, icount=icount, stride=stride * 4,
                consts=consts, vbytes=vbytes, ibytes=b[off:off + ib])


def row(c, k):
    return c[4 * k:4 * k + 4]


def palette_matrix(c, slot):
    """The 3×4 matrix the game uploaded for a palette slot (rows c8+3·slot …)."""
    return [list(row(c, 8 + 3 * slot + r)) for r in range(3)]


def mat_close(a, b, tol=1e-5):
    return all(abs(x - y) <= tol for ra, rb in zip(a, b) for x, y in zip(ra, rb))


def to4(m3):
    return [list(r) for r in m3] + [[0.0, 0.0, 0.0, 1.0]]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("capture")
    ap.add_argument("--game", default="cz")
    ap.add_argument("--models", default="data/models/npcs.big",
                    help="archive whose scenes are searched for the dumped draws")
    ap.add_argument("--overlay", help="write the captured frame with skinned vertices drawn on it")
    args = ap.parse_args()

    from dr2kit.container.vpath import AssetTree
    from dr2kit.formats.scene import Scene, is_scene, mat_mul

    dumps = [load_dump(p) for p in sorted(glob.glob(os.path.join(args.capture, "vsdump_*.bin")))]
    if not dumps:
        print("no vsdump_*.bin in", args.capture)
        return 1
    tree = AssetTree.for_game(args.game)
    by_icount = defaultdict(list)
    for vp, arc, _ in tree.walk_archives():
        if not vp.lower().startswith(args.models.lower()) or not is_scene(arc):
            continue
        sc = Scene.from_archive(arc, vp)
        for m in sc.meshes:
            for d in m.draws:
                by_icount[d.index_count].append((sc, m, d))

    # 1. same bytes
    matched = []
    for dp in dumps:
        hit = None
        for sc, m, d in by_icount.get(dp["icount"], []):
            s0 = d.streams.get(0)
            if s0 is None or s0.buffer is None or s0.stride != dp["stride"]:
                continue
            vb = sc.entry(s0.buffer).data()
            ib = sc.entry(d.index_buffer).data()
            start = (d.index_bind + d.first_index) * 2
            ours_i = ib[start:start + d.index_count * 2]
            first = (s0.first + d.base_vertex + d.first_vertex) * s0.stride
            ours_v = vb[first:first + d.vertex_count * s0.stride]
            if dp["ibytes"][:len(ours_i)] == ours_i and ours_v and \
                    dp["vbytes"][:len(ours_v)] == ours_v:
                hit = (sc, m, d)
                break
        if hit:
            matched.append((dp, *hit))
    print(f"dumps: {len(dumps)}; matched to a model draw with identical vertex AND index "
          f"bytes: {len(matched)}")
    for dp, sc, m, d in matched:
        print(f"    draw {dp['draw']:>5}: {sc.source.split('/')[-1]} {m.name} "
              f"({d.vertex_count} vertices, {d.index_count} strip indices, prim {dp['prim']})")
    if not matched:
        return 1

    # 2. palettes: identical matrices for shared nodes, and the shifted controls
    def agreement(shift: int):
        """Pairs whose shared nodes got identical matrices, with draw B's palette start
        moved by ``shift`` (0 = the reader's mapping; anything else is a control)."""
        agree = disagree = 0
        groups = defaultdict(list)
        for dp, sc, m, d in matched:
            groups[sc.source].append((dp, d))
        for items in groups.values():
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    (a, da), (b, db) = items[i], items[j]
                    na = {da.palette_start + k: k for k in range(da.palette_count)}
                    nb = {db.palette_start + shift + k: k for k in range(db.palette_count)}
                    shared = set(na) & set(nb)
                    if not shared:
                        continue
                    ok = all(mat_close(palette_matrix(a["consts"], na[n]),
                                       palette_matrix(b["consts"], nb[n])) for n in shared)
                    if ok:
                        agree += 1
                    else:
                        disagree += 1
        return agree, disagree
    print("bone palettes, pairs of draws of the same model sharing a node "
          "(agree = every shared node got the identical matrix):")
    for sh in (0, -2, -1, 1, 2):
        a, dsg = agreement(sh)
        label = "the reader's mapping" if sh == 0 else f"control: one draw's start {sh:+d}"
        print(f"    {label}: {a} pairs agree, {dsg} disagree")

    # 3. skeleton: bone lengths from the game's matrices vs the reader's records
    worst = 0.0
    checked = 0
    gaps = []
    for dp, sc, m, d in matched:
        rest = sc.skeleton.world_matrices()
        posed = {}
        for k in range(d.palette_count):
            n = d.palette_start + k
            posed[n] = mat_mul(to4(palette_matrix(dp["consts"], k)), rest[n])
        for n, wm in posed.items():
            node = sc.skeleton.nodes[n]
            if node.is_root or node.parent not in posed:
                continue
            pm = posed[node.parent]
            gap = math.dist([wm[r][3] for r in range(3)], [pm[r][3] for r in range(3)])
            want = math.sqrt(sum(c * c for c in node.translation))
            worst = max(worst, abs(gap - want))
            gaps.append((abs(gap - want), node.name))
            checked += 1
    gaps.sort()
    print(f"skeleton: {checked} parent→child offsets from the game's matrices vs the "
          f"records' bone lengths: median difference {gaps[len(gaps) // 2][0]:.1e} m, "
          f"{sum(1 for g in gaps if g[0] < 1e-4)} within 0.1 mm, largest {worst:.2e} m")
    for g, name in gaps[-8:][::-1]:
        if g >= 1e-4:
            print(f"    {name}: {g * 1000:.2f} mm")

    # 4. picture
    if args.overlay:
        overlay(args, matched)
    return 0


def overlay(args, matched) -> None:
    from PIL import Image, ImageDraw
    pics = glob.glob(os.path.join(args.capture, "capture_*.ppm"))
    if not pics:
        print("no capture_*.ppm to draw on")
        return
    im = Image.open(pics[0]).convert("RGB")
    W, H = im.size
    # The dumped constants are the game's own, taken before the recomp's renderer applies
    # its widescreen patch. For a wider-than-16:9 surface the recomp hands the game a
    # wider field of view (so its frustum covers the full width), then the renderer
    # multiplies row 1 (y) of this composite projection by k = 9W/16H to undo the
    # vertical stretch (CZ recomp, vk_renderer.cpp WideFovFactor / the composite form).
    # Doing the same here lands NDC on the whole captured surface.
    k = 9.0 * W / (16.0 * H)
    draw = ImageDraw.Draw(im)
    drawn = 0
    for dp, sc, m, d in matched:
        dd = sc.draw_data(d, m.name)
        c = dp["consts"]
        for p, js, ws in zip(dd.positions, dd.joints or [], dd.weights or []):
            sk = [0.0, 0.0, 0.0]
            for j, w in zip(js, ws):
                if w == 0:
                    continue
                M = palette_matrix(c, j - d.palette_start)
                for r in range(3):
                    sk[r] += w * (M[r][0] * p[0] + M[r][1] * p[1] + M[r][2] * p[2] + M[r][3])
            world = [sum(a * b for a, b in zip(row(c, 4 + r), (*sk, 1.0))) for r in range(3)]
            clip = [sum(a * b for a, b in zip(row(c, r), (*world, 1.0))) for r in range(4)]
            clip[1] *= k
            if clip[3] <= 1e-6:
                continue
            x = (clip[0] / clip[3] * 0.5 + 0.5) * W
            y = (0.5 - clip[1] / clip[3] * 0.5) * H
            draw.point((x, y), fill=(0, 255, 0))
            drawn += 1
    im.save(args.overlay)
    print(f"overlay: {drawn} skinned vertices drawn on {os.path.basename(pics[0])} -> {args.overlay}")


if __name__ == "__main__":
    sys.exit(main())

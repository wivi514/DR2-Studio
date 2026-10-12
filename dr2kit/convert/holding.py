"""Chuck holding an item, frozen in the game's own idle pose for it (phase 13.2).

Why: a weapon of one's own is lined up with Chuck's hands in the weapon wizard
(`mods.newweapon`); seeing him hold it, in the pose the game shows when he stands still
with that kind of item, lets a modder fix the grip before going in game
(docs/phase13-kickoff.md §Phase 13.2). Everything here is read from the game's data:

* **Chuck's look**: ``data/datafile.big/outfits.csv``'s ``OUTFIT_DEFAULT`` line names
  his parts (headwear, head, facewear, chest, hands, leg, feet), each a model
  ``data/models/npcs.big/<slot>_<name>.big`` (CZ ``chest_young_chuck``, CW
  ``chest_default``…). Every part carries the same 98-node rig as
  ``data/skeleton/playerfullbody.big``.
* **Which idle**: the game's animation graph ``data/datafile.big/sgraph.txt`` (blocks:
  ``cGenericAnimState`` → ``cAnimGroup`` → ``cCategoryChooser`` with a ``ChooserType`` →
  ``cChooserEntryInt <name>`` with ``Anim`` (a group or ``cAnimRef`` number) and
  ``Value``; a ``cAnimRef``'s ``File`` is the name hash of ``<name>.anm``, as a signed
  number). The standing idle's ``IDLEHOLDTYPE`` chooser takes the item's
  ``AnimationChooserValueForIdle`` (`items.txt`): 0 one-hand items (the plain combat idle),
  1 guns (then ``FIREARMTYPE``), 4 large boxes, 9 the chainsaw, 13 small boxes and
  chairs, 14 poles and spears, 15 the samurai sword stance, -1 nothing held. The
  ``HANDTYPE`` chooser takes ``AnimationChooserValueForHand``: the fingers' pose
  (``hand.big/male_hand_hold_pole_pose.anm``…). Choosers that depend on the moment are
  fixed to the plain choice (`DEFAULTS`: Chuck, no ambient fidget, the item switched off;
  a random chooser takes its likeliest entry).
* **The pose**: the first frame (`formats.anim.Animation.first_pose`) of the full-body
  idle, of the same name in ``root.big`` (where the hips are), and the hand pose, put on
  the game's animation rig ``data/skeleton/playerfullbody.big`` by node name; every part
  is then drawn on that one rig, skinned from its own rest pose (`full_pose`: the parts'
  rest offsets differ a little, the boots' by 2.4 cm).
* **Where the item goes**: measured in game (phase 12), the hands follow the item
  model's grip nodes; the item hangs from Chuck's ``dummy01.r_hand_prop`` node with its
  right-hand grip node (``LOC_rhand``, ``LOC_WEP_<x>_R``…) on it, turned the same way:
  item placement = hand prop × grip⁻¹ (`item_placement`) ❓ to be compared with the game
  (the phase 13.2 gate). The left hand is not moved to the item's ``IK_lhand`` (the game
  does that by IK ❓; not done here).

Needs numpy only for `posed_parts` (pictures).
"""

from __future__ import annotations

import csv
import ctypes
import io
import math
from dataclasses import dataclass, field

from ..container.vpath import AssetTree
from ..errors import Dr2Error, FormatError
from ..formats import anim as fanim
from ..formats.scene import (Node, Scene, Skeleton, mat_inverse_affine, mat_mul,
                             trs_matrix)
from ..hashing import name_hash

OUTFITS = "data/datafile.big/outfits.csv"
GRAPH = "data/datafile.big/sgraph.txt"
NPCS = "data/models/npcs.big"
OUTFIT = "OUTFIT_DEFAULT"
SLOTS = ("headwear", "head", "facewear", "chest", "hands", "leg", "feet")
ANIM_DIR = "data/anim/default.big"
HAND_PROP = "dummy01.r_hand_prop"
IDLE = "male_idle_combat.anm"          # the plain standing idle (with nothing in hand)
DEFAULTS = {"CHARACTERTYPE": 0, "CANPLAYAMBIENTIDLES": 0, "WEAPONON": 0, "FIREARMTYPE": 0}
GRIP_RIGHT = ("loc_rhand", "loc_wep_", "loc_grip")


def _signed(h: int) -> int:
    return ctypes.c_int32(h).value


def outfit_parts(tree: AssetTree, outfit: str = OUTFIT) -> list[str]:
    """Chuck's part models for ``outfit`` (module docstring), as vpaths that exist."""
    text = tree.resolve(OUTFITS).data().decode("latin-1")
    row = None
    for r in csv.reader(io.StringIO(text)):
        if r and r[0].strip().upper() == outfit.upper():
            row = [c.strip() for c in r[1:]]
            break
    if row is None:
        raise Dr2Error(f"{OUTFITS}: no {outfit} line")
    out = []
    for slot, name in zip(SLOTS, row):
        if not name or name.upper() == "NONE":
            continue
        vp = f"{NPCS}/{slot}_{name}.big"
        try:
            out.append(tree.resolve(vp).vpath)
        except Dr2Error:
            continue                        # e.g. a facewear the game leaves empty
    if not out:
        raise Dr2Error(f"{OUTFITS}: {outfit} names no model that exists")
    return out


# --- the animation graph ------------------------------------------------------------------

@dataclass
class Idle:
    """What `item_idle` picked: the animations (vpaths) and why."""
    fullbody: str
    root: str | None
    hand: str | None
    idle_value: int
    hand_value: int
    notes: list[str] = field(default_factory=list)


class AnimGraph:
    """``sgraph.txt`` read just enough to pick an idle (module docstring)."""

    def __init__(self, tree: AssetTree):
        from ..formats.levelscript import Document
        self.tree = tree
        self.doc = Document.parse(tree.resolve(GRAPH).data(), GRAPH)
        self.parent: dict[int, object] = {}
        for top in self.doc.blocks:
            self._index(top)
        self._names: dict[int, str] | None = None

    def _index(self, block) -> None:
        for c in block.children:
            self.parent[id(c)] = block
            self._index(c)

    def choosers(self, kind: str) -> list:
        """Every chooser block of a ``ChooserType``."""
        return [b for top in self.doc.blocks for b in top.walk()
                if b.cls.endswith("Chooser") and (b.get("ChooserType") or "") == kind]

    def anm_names(self) -> dict[int, str]:
        """Signed name hash → ``<name>.anm`` for every animation under ``data/anim/default.big``."""
        if self._names is None:
            self._names = {}
            for part in ("fullbody", "hand", "upperbody", "root", "facial"):
                try:
                    arc = self.tree.open_archive(f"{ANIM_DIR}/{part}.big")
                except Dr2Error:
                    continue
                for e in arc.entries:
                    self._names.setdefault(_signed(name_hash(e.name.lower())), e.name)
        return self._names

    def _find(self, container, anim_id: str):
        for c in container.children:
            if c.name == anim_id and c.cls in ("cAnimRef", "cAnimGroup"):
                return c
        return None

    @staticmethod
    def _value(entry) -> float:
        try:
            return float(entry.get("Value") or 0)
        except ValueError:
            return 0.0

    def pick(self, chooser, value: int | None, values: dict | None = None) -> str | None:
        """The ``.anm`` name a chooser leads to for ``value`` (None: its plain choice),
        following nested groups with `DEFAULTS` and ``values`` (chooser type → value)."""
        values = {**DEFAULTS, **(values or {})}
        entries = [e for e in chooser.children if e.cls.startswith("cChooserEntry")]
        if not entries:
            return None
        if chooser.cls == "cRandomChooser":
            entry = max(entries, key=self._value)
        else:
            want = value if value is not None else values.get(chooser.get("ChooserType") or "")
            entry = next((e for e in entries if want is not None and self._value(e) == want),
                         None)
            if entry is None:
                entry = next((e for e in entries if self._value(e) == 0), entries[0])
        container = self.parent.get(id(chooser))
        target = self._find(container, entry.get("Anim") or "") if container is not None \
            else None
        while target is None and container is not None:     # refs may sit higher up
            container = self.parent.get(id(container))
            target = self._find(container, entry.get("Anim") or "") if container else None
        if target is None:
            return None
        if target.cls == "cAnimRef":
            try:
                return self.anm_names().get(int(target.get("File")))
            except (TypeError, ValueError):
                return None
        inner = next((c for c in target.children if c.cls.endswith("Chooser")), None)
        return self.pick(inner, None, values) if inner is not None else None

    def standing_idle(self):
        """The ``IDLEHOLDTYPE`` chooser of the standing idle: the one whose plain choice
        (value 0, Chuck, no fidget) is ``male_idle_combat.anm`` and that has the most
        entries (other states hold doors, carts, the injured idle)."""
        best = None
        for c in self.choosers("IDLEHOLDTYPE"):
            if (self.pick(c, 0) or "").lower() != IDLE:
                continue
            n = sum(1 for e in c.children if e.cls.startswith("cChooserEntry"))
            if best is None or n > best[0]:
                best = (n, c)
        if best is None:
            raise FormatError(f"{GRAPH}: no IDLEHOLDTYPE chooser leads to {IDLE}")
        return best[1]

    def hand_chooser(self):
        found = self.choosers("HANDTYPE")
        if not found:
            raise FormatError(f"{GRAPH}: no HANDTYPE chooser")
        return found[0]


_graphs: dict[str, AnimGraph] = {}


def graph(tree: AssetTree) -> AnimGraph:
    """The game's `AnimGraph`, read once per game folder."""
    key = str(tree.root)
    if key not in _graphs:
        _graphs[key] = AnimGraph(tree)
    return _graphs[key]


def _int(block, key: str, default: int) -> int:
    v = block.get(key) if block is not None else None
    try:
        return int(float(v)) if v not in (None, "") else default
    except ValueError:
        return default


def item_idle(tree: AssetTree, block=None, *, idle_value: int | None = None,
              hand_value: int | None = None) -> Idle:
    """The idle animations for an ``items.txt`` block (or for the values given; no block
    and no values: standing with nothing in hand)."""
    g = graph(tree)
    iv = idle_value if idle_value is not None else _int(
        block, "AnimationChooserValueForIdle", -1 if block is None else 0)
    hv = hand_value if hand_value is not None else _int(block, "AnimationChooserValueForHand", 0)
    values = {}
    if block is not None and block.get("FirearmType") is not None:
        values["FIREARMTYPE"] = _int(block, "FirearmType", 0)
    notes = []
    body = g.pick(g.standing_idle(), iv, values)
    if body is None:
        body = IDLE
        notes.append(f"idle value {iv}: not in the game's idle chooser, the plain idle shown")
    hand = g.pick(g.hand_chooser(), hv)
    if hand is None:
        notes.append(f"hand value {hv}: no hand pose in the game's chooser")
    root = None
    try:
        root = tree.resolve(f"{ANIM_DIR}/root.big/{body}").vpath
    except Dr2Error:
        notes.append(f"{body}: no root.big animation (hips at rest height)")
    return Idle(tree.resolve(f"{ANIM_DIR}/fullbody.big/{body}").vpath, root,
                tree.resolve(f"{ANIM_DIR}/hand.big/{hand}").vpath if hand else None,
                iv, hv, notes)


# --- posing -------------------------------------------------------------------------------

def _part_names(tree: AssetTree, part: str, cache: dict) -> list[str]:
    if part not in cache:
        sk = Scene.from_archive(tree.open_archive(fanim.SKELETONS[part])).skeleton
        cache[part] = [n.name for n in sk.nodes]
    return cache[part]


def animation_pose(tree: AssetTree, vpaths: list[str]) -> dict[str, dict]:
    """The first frame of each animation, layered in order, by node name (lower case):
    ``{"dummy01.r_hand": {"rotation": (x, y, z, w), "translation": (x, y, z)}}``."""
    names: dict = {}
    out: dict[str, dict] = {}
    for vp in vpaths:
        part = fanim.part_of(vp)
        if part is None:
            raise Dr2Error(f"{vp}: not in a skeleton part's archive (fullbody.big, hand.big…)")
        pose = fanim.Animation.parse(tree.resolve(vp).data(), vp).first_pose()
        nm = _part_names(tree, part, names)
        for i, q in pose.rotations.items():
            if i < len(nm):
                out.setdefault(nm[i].lower(), {})["rotation"] = q
        for i, t in pose.translations.items():
            if i < len(nm):
                out.setdefault(nm[i].lower(), {})["translation"] = t
    return out


def posed_skeleton(skel: Skeleton, pose: dict[str, dict]) -> Skeleton:
    """A copy of ``skel`` with the pose's local transforms on the nodes it names."""
    nodes = []
    for n in skel.nodes:
        p = pose.get(n.name.lower(), {})
        nodes.append(Node(n.name, n.index, n.parent, n.flag, n.scale,
                          tuple(p.get("translation", n.translation)),
                          tuple(p.get("rotation", n.rotation))))
    return Skeleton(nodes)


def idle_pose(tree: AssetTree, idle: Idle) -> dict[str, dict]:
    """The frozen pose of `item_idle`'s choice: full body, then root, then the hands."""
    return animation_pose(tree, [v for v in (idle.fullbody, idle.root, idle.hand) if v])


# --- the item in the hand -----------------------------------------------------------------

def grip_matrix(scene: Scene) -> list[list[float]] | None:
    """The item model's right-hand grip node (model space), or None."""
    nodes = scene.skeleton.nodes
    if not nodes:
        return None
    world = scene.skeleton.world_matrices()
    for n in nodes:
        last = n.name.rsplit(".", 1)[-1].lower()
        if last.startswith(GRIP_RIGHT) and not last.endswith("_l"):
            return world[n.index]
    return None


def hand_matrix(posed: Skeleton) -> list[list[float]]:
    """Chuck's right-hand prop node in the posed rig (model space)."""
    n = posed.by_name(HAND_PROP)
    if n is None:
        raise Dr2Error(f"Chuck's rig has no {HAND_PROP}")
    return posed.world_matrices()[n.index]


def item_placement(hand: list[list[float]], grip: list[list[float]] | None
                   ) -> list[list[float]]:
    """The item model's matrix in Chuck's space: hand prop × grip⁻¹ (module docstring).
    Without a grip node, the item's origin goes to the hand."""
    return mat_mul(hand, mat_inverse_affine(grip)) if grip is not None else hand


def decompose(m) -> tuple[list[float], list[float], list[float]]:
    """A rigid (+ scale) 4×4 as translation, rotation (x, y, z, w) and scale."""
    cols = [[m[r][c] for r in range(3)] for c in range(3)]
    s = [math.sqrt(sum(v * v for v in col)) or 1.0 for col in cols]
    r = [[m[i][j] / s[j] for j in range(3)] for i in range(3)]
    tr = r[0][0] + r[1][1] + r[2][2]
    if tr > 0:
        w = math.sqrt(1 + tr) * 2
        q = [(r[2][1] - r[1][2]) / w, (r[0][2] - r[2][0]) / w, (r[1][0] - r[0][1]) / w, w / 4]
    else:
        i = max(range(3), key=lambda k: r[k][k])
        j, k = (i + 1) % 3, (i + 2) % 3
        d = math.sqrt(max(0.0, 1 + r[i][i] - r[j][j] - r[k][k])) * 2
        q = [0.0, 0.0, 0.0, (r[k][j] - r[j][k]) / d]
        q[i], q[j], q[k] = d / 4, (r[j][i] + r[i][j]) / d, (r[k][i] + r[i][k]) / d
    return [m[0][3], m[1][3], m[2][3]], q, s


def flat(m) -> list[float]:
    """A 4×4 row-major matrix as 16 numbers in column order (three.js ``Matrix4.fromArray``,
    glTF)."""
    return [m[r][c] for c in range(4) for r in range(4)]


# --- Chuck as one .glb ----------------------------------------------------------------------

RIG = "data/skeleton/playerfullbody.big"


@dataclass
class Chuck:
    """Chuck posed for an item (`posed_chuck`)."""
    parts: list[str]                     # the part models (vpaths)
    idle: Idle
    pose: dict                           # node name -> local transform, every node of the rig
    rest: Skeleton                       # the game's animation rig at rest (`RIG`)
    posed: Skeleton

    @property
    def hand(self) -> list[list[float]]:
        return hand_matrix(self.posed)


def posed_chuck(tree: AssetTree, block=None, *, idle_value: int | None = None,
                hand_value: int | None = None, outfit: str = OUTFIT) -> Chuck:
    """Chuck's parts and rig, posed in the idle for ``block`` (module docstring)."""
    parts = outfit_parts(tree, outfit)
    idle = item_idle(tree, block, idle_value=idle_value, hand_value=hand_value)
    rest = Scene.from_archive(tree.open_archive(RIG)).skeleton
    posed = posed_skeleton(rest, idle_pose(tree, idle))
    return Chuck(parts, idle, full_pose(posed), rest, posed)


def full_pose(posed: Skeleton) -> dict[str, dict]:
    """Every node's local transform in the posed rig, by name (lower case). The parts
    get all of them, not only the animated ones: a part's own rest offsets differ a
    little from the rig's (the boots' ankles sit 2.4 cm higher), and the game draws
    every part on the one animated rig, each skinned from its own rest pose."""
    return {n.name.lower(): {"rotation": tuple(n.rotation), "translation": tuple(n.translation)}
            for n in posed.nodes}


def chuck_glb(tree: AssetTree, game: str, chuck: Chuck, *, textures: bool = True,
              assembler=None, parent: int | None = None) -> bytes | None:
    """Chuck's parts (each in its default look) as one ``.glb``, the rig's nodes set to the
    pose (glTF skinning then draws him posed, in Studio and in Blender). With an
    ``assembler`` (`convert.gltf.Assembler`), adds to it and returns None."""
    from . import gltf
    from .model import model_glb, read_scene
    own = assembler is None
    asm = assembler or gltf.Assembler()
    group = asm.group("Chuck", parent, extras={"dr2": {"idle": chuck.idle.fullbody,
                                                         "hand": chuck.idle.hand}})
    for vp in chuck.parts:
        scene = read_scene(tree, vp)
        glb = model_glb(tree, scene, game=game, textures=textures, mode="shown")
        asm.add(glb, [{"name": vp.rsplit("/", 1)[-1].removesuffix(".big")}], group,
                source=vp, pose=chuck.pose)
    return asm.to_bytes() if own else None


def posed_parts(tree: AssetTree, game: str, chuck: Chuck, texture_for=None) -> list:
    """Chuck posed as renderer parts (`convert.render`), for pictures without a GPU."""
    import numpy as np
    from . import render
    from .model import read_scene
    from .variants import read_variants
    posed_w = {n.name.lower(): np.asarray(m, np.float64)
               for n, m in zip(chuck.posed.nodes, chuck.posed.world_matrices())}
    out = []
    for vp in chuck.parts:
        scene = read_scene(tree, vp)
        own = scene.skeleton
        skin = [posed_w.get(n.name.lower(), np.asarray(m, np.float64)) @ np.linalg.inv(m)
                for n, m in zip(own.nodes, (np.asarray(w, np.float64)
                                            for w in own.world_matrices()))]
        mv = read_variants(tree, scene, game)
        shown = mv.shown(mv.parse(None))
        meshes = {i for i, s in enumerate(shown) if s} if mv.has_choices else None
        out += render.scene_parts(scene, texture_for, meshes=meshes, skin=skin)
    return out


_rest: dict[tuple, bytes] = {}


def rest_glb(tree: AssetTree, game: str, outfit: str = OUTFIT) -> bytes:
    """Chuck's parts at rest as one ``.glb`` (kept once per game folder): Studio poses
    the rig itself (`idle_pose` sent to the page), so changing the kind is instant."""
    from . import gltf
    from .model import model_glb, read_scene
    key = (str(tree.root), outfit)
    if key not in _rest:
        asm = gltf.Assembler()
        group = asm.group("Chuck", None)
        for vp in outfit_parts(tree, outfit):
            scene = read_scene(tree, vp)
            asm.add(model_glb(tree, scene, game=game, mode="shown"),
                    [{"name": vp.rsplit("/", 1)[-1].removesuffix(".big")}], group, source=vp)
        _rest[key] = asm.to_bytes()
    return _rest[key]


# --- for the command line: Chuck holding a game item ----------------------------------

def item_hold_glb(tree: AssetTree, game: str, item: str, *, textures: bool = True
                  ) -> tuple[bytes, Chuck]:
    """Chuck in the idle for a game item (its ``items.txt`` name) holding its model, as
    one ``.glb`` (``dr2 hold``)."""
    from . import gltf, placed
    from .model import model_glb
    models = placed.ItemModels(tree)
    block = models.blocks.get(item.lower())
    scene_vp = models.resolve(item)
    if block is None or scene_vp is None:
        raise Dr2Error(f"{item}: not an item with a model in {game.upper()} (items.txt names: "
                       f"dr2 library weapons)")
    chuck = posed_chuck(tree, block)
    scene = Scene.parse(tree.resolve(scene_vp).data(), scene_vp)
    asm = gltf.Assembler()
    chuck_glb(tree, game, chuck, textures=textures, assembler=asm)
    t, q, s = decompose(item_placement(chuck.hand, grip_matrix(scene)))
    asm.add(model_glb(tree, scene, game=game, textures=textures, mode="shown"),
            [{"name": block.name, "translation": t, "rotation": q, "scale": s}],
            source=scene_vp)
    asm.extras = {"item": block.name, "idle": chuck.idle.fullbody, "hand": chuck.idle.hand}
    return asm.to_bytes(), chuck


def picture(tree: AssetTree, game: str, chuck: Chuck, item_parts: list, placement,
            width: int = 360, height: int = 540) -> "object":
    """Chuck holding an item as an RGBA picture (front, side and three-quarter views side
    by side; `convert.render`, no GPU). ``item_parts``: renderer parts in the item's model
    space; ``placement``: its 4×4 matrix in Chuck's space."""
    import numpy as np
    from . import render
    from .model import TextureFinder

    def textures(vp):
        finder = TextureFinder(tree, vp, game)

        def tex(name):
            im = finder.image(name)
            return None if im is None else render.rgba_to_float(im.rgba, im.width, im.height)
        return tex
    parts = []
    for vp in chuck.parts:
        parts += posed_parts(tree, game, Chuck([vp], chuck.idle, chuck.pose, chuck.rest,
                                               chuck.posed), textures(vp))
    w = np.asarray(placement, np.float64)
    for p in item_parts:
        q = render.Part(p.positions, p.triangles, p.normals, p.uvs, p.texture, p.alpha_test)
        q.positions = (p.positions.astype(np.float64) @ w[:3, :3].T + w[:3, 3]).astype(np.float32)
        if p.normals is not None:
            q.normals = (p.normals.astype(np.float64) @ w[:3, :3].T).astype(np.float32)
        parts.append(q)
    views = (((1, 0, 0), (0, 1, 0), (0, 0, 1)), ((0, 0, -1), (0, 1, 0), (1, 0, 0)), None)
    pics = [render.render(parts, width=width, height=height, basis=b, fill=0.9) for b in views]
    return np.concatenate([p for p in pics if p is not None], axis=1)

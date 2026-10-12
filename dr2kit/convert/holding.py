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

def item_hold_glb(tree: AssetTree, game: str, item: str, *, textures: bool = True,
                  moves: bool = False) -> tuple[bytes, Chuck]:
    """Chuck in the idle for a game item (its ``items.txt`` name) holding its model, as
    one ``.glb`` (``dr2 hold``). ``moves``: its attacks too, as glTF animations, the item
    hung under his hand node so it swings with him (`hang_on_hand`)."""
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
    glb = model_glb(tree, scene, game=game, textures=textures, mode="shown")
    place = item_placement(chuck.hand, grip_matrix(scene))
    hang_on_hand(asm, chuck, glb, block.name, place, scene_vp, on_hand=moves)
    asm.extras = {"item": block.name, "idle": chuck.idle.fullbody, "hand": chuck.idle.hand}
    if moves:
        asm.extras["moves"] = add_moves(asm, tree, block, chuck.idle)
    return asm.to_bytes(), chuck


def hang_on_hand(asm, chuck: Chuck, glb: bytes, name: str, placement, source: str,
                 on_hand: bool = False) -> int:
    """Put an item's ``.glb`` in Chuck's hand: at ``placement`` (its matrix in Chuck's
    space), or with ``on_hand`` as a child of his first ``dummy01.r_hand_prop`` node
    (hand⁻¹ × placement), so it follows the hand when a move plays (Blender parents it
    to that bone). Returns its node."""
    parent = None
    if on_hand:
        parent = next((i for i, n in enumerate(asm.b.gltf["nodes"])
                       if (n.get("name") or "").lower() == HAND_PROP), None)
    m = placement if parent is None else mat_mul(mat_inverse_affine(chuck.hand), placement)
    t, q, s = decompose(m)
    return asm.add(glb, [{"name": name, "translation": t, "rotation": q, "scale": s}],
                   parent, source=source)[0]


def add_moves(asm, tree: AssetTree, block, idle: Idle | None) -> list[str]:
    """Every attack of ``block`` (`move_clips`) as a glTF animation of ``asm`` (named after
    the move). Returns their names."""
    names = []
    for label, clp in move_clips(tree, block, idle):
        if add_animation(asm, label.split("  ")[0], clp):
            names.append(label)
    return names


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


# --- animations played (phase 14) ---------------------------------------------------------
#
# Every key of an ``.anm`` is read (`formats.anim.Animation.decode`), so a move plays: an
# attack of the weapon's kind with the weapon in Chuck's hand (Studio's "Chuck holding it"
# view), any animation of the game on the rig it was made for (the Library), or as a glTF
# animation in Blender (`dr2 extract --glb <.anm>`, `dr2 hold --moves`).
#
# Which rig: an ``.anm``'s first word is its skeleton's id, the same number every skeleton
# file stores in its ``_ANIMCHANNELINFO_`` (word 1); the game refuses an animation whose
# id differs from the skeleton's ("the anim data does not match the skeleton that it is
# being played on!"). Several skeleton files share an id (player, child, female and large
# full bodies are the same rig): `skeleton_for` prefers the player's.

SKELETON_DIR = "data/skeleton"
CHUCK_IDS = {0x24F628C0, 0xAD2B0240, 0x70CB2D80, 0xDA1D8000, 0xADC1BFE0}
BANKS = "data/streamedassets.big"

_skeletons: dict[str, dict[int, str]] = {}


def skeleton_ids(tree: AssetTree) -> dict[int, str]:
    """Skeleton id → the skeleton file (vpath) whose ``_ANIMCHANNELINFO_`` holds it (the
    player's first when several share it), read once per game folder."""
    import struct
    key = str(tree.root)
    if key not in _skeletons:
        found: dict[int, str] = {}
        names = [vp.rsplit("/", 1)[-1] for vp, _p in tree.files()
                 if vp.lower().startswith(SKELETON_DIR + "/") and vp.count("/") == 2]
        names.sort(key=lambda n: (not n.lower().startswith("player"),
                                  not n.lower().startswith("zombie"), n.lower()))
        for n in names:
            if not n.lower().endswith(".big"):
                continue
            vp = f"{SKELETON_DIR}/{n}"
            try:
                arc = tree.open_archive(vp)
            except Dr2Error:
                continue
            for e in arc.entries:
                if e.name == "_ANIMCHANNELINFO_":
                    d = e.data()
                    if len(d) >= 8:
                        found.setdefault(struct.unpack_from(">I", d, 4)[0], vp)
        _skeletons[key] = found
    return _skeletons[key]


def skeleton_for(tree: AssetTree, anim: "fanim.Animation", vpath: str = "") -> str | None:
    """The skeleton file an animation plays on: by its id, else by its part's archive."""
    sk = skeleton_ids(tree).get(anim.skeleton_id)
    if sk is None:
        part = fanim.part_of(vpath)
        sk = fanim.SKELETONS.get(part) if part else None
    return sk


def companions(tree: AssetTree, vpath: str) -> list[str]:
    """An animation with its partner of the same name: a ``fullbody.big`` move gets the
    ``root.big`` one (where the hips are, how the body travels) and the other way round.
    Full body first, then root."""
    parts = vpath.split("/")
    if len(parts) < 2:
        return [vpath]
    folder = parts[-2].lower()
    out = [vpath]
    for mine, other in (("fullbody.big", "root.big"), ("root.big", "fullbody.big")):
        if folder == mine:
            try:
                partner = tree.resolve("/".join(parts[:-2] + [parts[-2][:-len(mine)] + other,
                                                              parts[-1]])).vpath
            except Dr2Error:
                break
            out = [vpath, partner] if mine == "fullbody.big" else [partner, vpath]
            break
    return out


def move_files(tree: AssetTree, name: str, bank: str | None = None) -> list[str]:
    """A move's ``.anm`` files by its name (``AnimationAttackName``): the weapon's bank
    ``streamedassets.big/anm_<bank>.big`` first, then ``data/anim/default.big``; the full
    body then the root one. Empty when the game has neither."""
    stem = name.removesuffix(".anm")
    places = [f"{BANKS}/anm_{bank}.big"] if bank else []
    places.append(ANIM_DIR)
    for place in places:
        try:
            return companions(tree, tree.resolve(f"{place}/fullbody.big/{stem}.anm").vpath)
        except Dr2Error:
            continue
    return []


@dataclass
class Move:
    """One of an item's moves: what the game calls it, a label for people, its files."""
    name: str
    label: str
    files: list[str]


def item_moves(tree: AssetTree, block) -> list[Move]:
    """The attacks of an ``items.txt`` block (``AnimationAttackName<i>``, in the weapon's
    ``AnimBankName`` bank), the ones whose files the game has."""
    if block is None:
        return []
    bank = block.get("AnimBankName")
    out, seen = [], set()
    for i in range(32):
        name = block.get(f"AnimationAttackName{i}")
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        files = move_files(tree, name, bank)
        if not files:
            continue
        air = "JUMP" in (block.get(f"ActionRequiredAnimState{i}") or "")
        label = f"{name}{'  (in the air)' if air else ''}"
        out.append(Move(name, label, files))
    return out


def clip(tree: AssetTree, vpaths: list[str], digits: int = 5, rig: str | None = None
         ) -> dict:
    """Animations played together (layered in order: full body, root, hands) as one
    clip by node name: ``{"length": s, "rate": fps, "frames": n, "nodes": {name: {"r":
    {"t": [s…], "v": [[x, y, z, w]…]}, "p": {"t": […], "v": [[x, y, z]…]}}}}``. Times are
    seconds; between keys a rotation turns the short way (nlerp) and a position moves in
    a straight line, as `formats.anim.Channel.at`.

    ``rig`` (a skeleton file, Chuck's `RIG`): every node of it the animations don't move
    gets its rest value as a one-key channel, so each of Chuck's parts is drawn on the
    one rig and not on its own rest pose (`full_pose`: the boots' differs)."""
    from ..formats.scene import Scene
    names: dict[str, list[str]] = {}
    nodes: dict[str, dict] = {}
    length, rate, frames = 0.0, 30.0, 1
    for vp in vpaths:
        a = fanim.Animation.parse(tree.resolve(vp).data(), vp)
        sk = skeleton_for(tree, a, vp)
        if sk is None:
            raise Dr2Error(f"{vp}: no skeleton file with its id {a.skeleton_id:08X}")
        if sk not in names:
            names[sk] = [n.name for n in Scene.from_archive(tree.open_archive(sk)).skeleton.nodes]
        nm = names[sk]
        c = a.decode()
        if c.length > length:
            length, rate, frames = c.length, c.rate, c.frames
        for ch in c.channels:
            what = ch.track.what
            if ch.track.node >= len(nm) or what not in ("rotation", "translation"):
                continue
            key = "r" if what == "rotation" else "p"
            t = [round(f / c.rate, 6) for f in ch.frames] if c.rate else [0.0]
            nodes.setdefault(nm[ch.track.node].lower(), {})[key] = {
                "t": t, "v": [[round(x, digits) for x in v] for v in ch.values]}
    if rig is not None:
        for n in Scene.from_archive(tree.open_archive(rig)).skeleton.nodes:
            keys = nodes.setdefault(n.name.lower(), {})
            keys.setdefault("r", {"t": [0.0], "v": [[round(x, digits) for x in n.rotation]]})
            keys.setdefault("p", {"t": [0.0], "v": [[round(x, digits) for x in n.translation]]})
    return {"length": length, "rate": rate, "frames": frames, "nodes": nodes,
            "files": list(vpaths)}


_clips: dict[tuple, dict] = {}


def cached_clip(tree: AssetTree, vpaths: list[str], rig: str | None = RIG) -> dict:
    """`clip`, kept (the weapon wizard redraws often; at most 64 kept)."""
    key = (str(tree.root), tuple(vpaths), rig)
    if key not in _clips:
        if len(_clips) >= 64:
            _clips.pop(next(iter(_clips)))
        _clips[key] = clip(tree, vpaths, rig=rig)
    return _clips[key]


def move_clips(tree: AssetTree, block, idle: Idle | None = None) -> list[tuple[str, dict]]:
    """An item's attacks as ``(label, clip)`` for Studio's *Move* box: each move's full
    body and root animations, then the item's hand pose (`Idle.hand`) so the fingers hold
    it; on Chuck's rig. A move that doesn't read is left out."""
    out = []
    for mv in item_moves(tree, block):
        files = mv.files + ([idle.hand] if idle is not None and idle.hand else [])
        try:
            out.append((mv.label, cached_clip(tree, files)))
        except (Dr2Error, FormatError):
            continue
    return out


def body_for(tree: AssetTree, vpath: str) -> str:
    """Who an animation is shown on: ``chuck`` for the player's rigs, else the skeleton
    file it plays on (drawn as bones)."""
    a = fanim.Animation.parse(tree.resolve(vpath).data(), vpath)
    if a.skeleton_id in CHUCK_IDS:
        return "chuck"
    return skeleton_for(tree, a, vpath) or "chuck"


def add_animation(asm, name: str, clp: dict) -> int:
    """A clip (`clip`) as a glTF animation on every node of ``asm`` (a
    `convert.gltf.Assembler`) whose name it moves: each of Chuck's parts carries its own
    copy of the rig, and all of them move. Returns the number of channels."""
    b = asm.b
    by_name: dict[str, list[int]] = {}
    for i, n in enumerate(b.gltf["nodes"]):
        if n.get("name"):
            by_name.setdefault(n["name"].lower(), []).append(i)
    samplers, channels = [], []
    for node, keys in clp["nodes"].items():
        targets = by_name.get(node)
        if not targets:
            continue
        for key, path, type_ in (("r", "rotation", "VEC4"), ("p", "translation", "VEC3")):
            if key not in keys:
                continue
            t, v = keys[key]["t"], keys[key]["v"]
            if len(t) == 1:                 # glTF wants a time range: hold the one key
                t, v = [0.0, max(clp["length"], 1 / 30)], [v[0], v[0]]
            inp = b.accessor(t, "SCALAR", minmax=True, target=None)
            out = b.accessor([tuple(x) for x in v], type_, target=None)
            s = len(samplers)
            samplers.append({"input": inp, "output": out, "interpolation": "LINEAR"})
            channels += [{"sampler": s, "target": {"node": i, "path": path}} for i in targets]
    if channels:
        b.add("animations", {"name": name, "samplers": samplers, "channels": channels})
    return len(channels)


def animation_glb(tree: AssetTree, game: str, vpath: str, *, textures: bool = True
                  ) -> tuple[bytes, dict]:
    """An animation (and its root / full-body partner, `companions`) as a ``.glb``:
    Chuck's parts (the player's rigs) or the skeleton's bones, with the move as a glTF
    animation (Blender: an Action). Returns the bytes and the clip."""
    from . import gltf
    files = companions(tree, vpath)
    body = body_for(tree, vpath)
    clp = clip(tree, files, rig=RIG if body == "chuck" else None)
    asm = gltf.Assembler()
    if body == "chuck":
        from .model import model_glb, read_scene
        group = asm.group("Chuck", None)
        for vp in outfit_parts(tree):
            scene = read_scene(tree, vp)
            asm.add(model_glb(tree, scene, game=game, textures=textures, mode="shown"),
                    [{"name": vp.rsplit("/", 1)[-1].removesuffix(".big")}], group, source=vp)
    else:
        scene = Scene.from_archive(tree.open_archive(body), body)
        asm.add(gltf.skeleton_to_glb(scene), [{"name": body.rsplit("/", 1)[-1]}], source=body)
    name = vpath.rsplit("/", 1)[-1].removesuffix(".anm")
    add_animation(asm, name, clp)
    asm.extras = {"animation": files, "body": body}
    return asm.to_bytes(), clp

"""Level edits as a mod: ``<file>.txt.edits.json``, only what changed, by block path
(phase 11, docs/phase11-kickoff.md §Plan 1).

Why not a whole ``.txt``: the CZ recomp already edits ``missions.txt`` (its co-op
changes, in ``game_patched``), and two mods that each move one zombie would replace each
other's whole file. An ``.edits.json`` holds **only its changes**, so the build applies
them to whatever file is underneath (the shipped one, or the recomp's patched one) and
several mods merge: only the same key of the same block changed by two mods is a
conflict, decided by priority (`merge`). The same idea as a ``.bcs.json`` for strings
(`dr2kit.formats.bcs`).

The file (``replace/data/datafile.big/prologue.txt.edits.json``)::

    {"format": "dr2kit-level-edits/1",
     "set":    {"cItemPlacement Scissors1": {"Location": "-140.0,3.399,-89.9",
                                             "PropState": null}},        <- null: remove the key
     "add":    {"cItemPlacement MyKatana": {"ItemName": "Katana",
                                            "Location": "-141,3.4,-88", "Rotation": "0,0,0,1"},
                "cMissionDefinition PrologueZombies/cMissionLevelReady PrologueZombieReady/cMissionSpawnZombie Mine":
                    {"ZombieType": "zombie_fat", "SpawnPoint": "-150,3.4,-90", "Rotation": "1.5"}},
     "remove": ["cItemPlacement Shampoo"]}

* A **block path** is ``cls name`` per level joined with ``/`` (`levelscript.Document.find`):
  mission blocks nest and their names are only unique within their parent. Where a name
  repeats among siblings (the animation graph's ``cCategoryChooser cRandomChooser``), each
  is ``cls name#n``, n counting from 1.
* ``add`` values are the block's keys; a value that is itself an object is a child block
  (its key ``cls name``); ``"@values"`` is a list of bare values (nav-mesh vertices);
  ``"@text"`` is instead the block's whole text, written as it is (re-indented): blocks
  copied from a hand-written file whose reader cares about quoting and key order (the
  animation graph, `convert.graphcarry`); ``"@after"`` names the sibling it goes after (``""``: first; default: last), which
  `diff` writes so that applying edits and then their reverse gives the file back byte
  for byte.
* Order of work: adds, then sets (a set can change a block the same file adds), then
  removes.

`apply` changes a parsed `Document` and raises `FormatError` naming every block or key it
can't find; `diff` computes the edits between two versions of a file (a modder who
edited a whole ``.txt`` turns it into an ``.edits.json`` with ``dr2 level diff``);
`merge` lays several mods' edits of one file over each other by priority and reports what
lost. The checks of what the edits *mean* (an ``ItemName`` the game has, a zombie type the
level loads) are `dr2kit.convert.levelcheck`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..errors import FormatError
from .levelscript import Block, Document, seg, split_path

FORMAT = "dr2kit-level-edits/1"
EXT = ".edits.json"


def norm(path: str) -> str:
    """A block path written one way (single spaces, no empty parts)."""
    return "/".join(split_path(path))


@dataclass
class Edits:
    """One mod's changes to one text file (module docstring)."""
    set: dict[str, dict[str, str | None]] = field(default_factory=dict)
    add: dict[str, dict] = field(default_factory=dict)
    remove: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.set or self.add or self.remove)

    def touched(self) -> list[tuple[tuple[str, ...], str]]:
        """What the edits change, for conflicts: ``(key, shown)`` pairs, the key
        ``("key", path, key)`` per set and ``("block", path)`` per add or remove (lower
        case, to compare), ``shown`` as the mod wrote it."""
        out: list[tuple[tuple[str, ...], str]] = []
        for p, keys in self.set.items():
            out += [(("key", norm(p).lower(), k.lower()), f"{norm(p)} {k}") for k in keys]
        out += [(("block", norm(p).lower()), norm(p)) for p in self.add]
        out += [(("block", norm(p).lower()), norm(p)) for p in self.remove]
        return out

    def count(self) -> int:
        return sum(len(v) for v in self.set.values()) + len(self.add) + len(self.remove)


def from_json(text: str, where: str = "<edits>") -> Edits:
    """Read an ``.edits.json``; `FormatError` saying what is wrong."""
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        raise FormatError(f"{where}: not valid JSON ({e})") from None
    if not isinstance(doc, dict):
        raise FormatError(f'{where}: needs an object with "set", "add" and/or "remove"')
    if doc.get("format", FORMAT) != FORMAT:
        raise FormatError(f"{where}: format {doc['format']!r}, expected {FORMAT!r}")
    unknown = set(doc) - {"format", "set", "add", "remove", "file", "comment"}
    if unknown:
        raise FormatError(f"{where}: unknown part(s) {sorted(unknown)} (set, add, remove)")
    e = Edits()
    sets = doc.get("set", {})
    if not isinstance(sets, dict):
        raise FormatError(f'{where}: "set" must be {{"<block path>": {{"Key": "value"}}}}')
    for path, keys in sets.items():
        if not isinstance(keys, dict):
            raise FormatError(f"{where}: set {path!r}: needs {{\"Key\": \"value\"}}")
        for k, v in keys.items():
            if v is not None and not isinstance(v, str):
                raise FormatError(f"{where}: set {path!r} {k}: a value is text in quotes "
                                  f"(or null to remove the key), got {json.dumps(v)}")
        e.set[norm(path)] = dict(keys)
    adds = doc.get("add", {})
    if not isinstance(adds, dict):
        raise FormatError(f'{where}: "add" must be {{"<block path>": {{"Key": "value"}}}}')
    for path, spec in adds.items():
        _check_spec(spec, f"{where}: add {path!r}")
        e.add[norm(path)] = spec
    rem = doc.get("remove", [])
    if not isinstance(rem, list) or not all(isinstance(r, str) for r in rem):
        raise FormatError(f'{where}: "remove" must be a list of block paths')
    e.remove = [norm(r) for r in rem]
    return e


def to_json(e: Edits, file: str = "") -> str:
    """An ``.edits.json`` (``file`` is written as a note of what it edits)."""
    doc: dict = {"format": FORMAT}
    if file:
        doc["file"] = file
    if e.set:
        doc["set"] = e.set
    if e.add:
        doc["add"] = e.add
    if e.remove:
        doc["remove"] = e.remove
    return json.dumps(doc, ensure_ascii=False, indent=1) + "\n"


def _check_spec(spec, where: str) -> None:
    if not isinstance(spec, dict):
        raise FormatError(f"{where}: a block is {{\"Key\": \"value\", …}}")
    for k, v in spec.items():
        if k == "@values":
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                raise FormatError(f"{where}: @values is a list of text values")
        elif k == "@text":
            if not isinstance(v, str) or not v.strip():
                raise FormatError(f"{where}: @text is the block's text")
        elif k == "@after":
            if not isinstance(v, str):
                raise FormatError(f"{where}: @after names a sibling block (text)")
        elif isinstance(v, dict):
            _check_spec(v, f"{where}/{k}")
        elif not isinstance(v, str):
            raise FormatError(f"{where}: {k}: a value is text in quotes, got {json.dumps(v)}")


def spec_of(block: Block) -> dict:
    """A parsed block as an ``add`` value (keys in file order, children nested)."""
    out: dict = {p.key: p.value for p in block.props}
    if block.values:
        out["@values"] = [v for v, _ in block.values]
    for c in block.children:
        out[seg(c)] = spec_of(c)
    return out


def _tuple_of(path_seg: str, spec: dict) -> tuple:
    """``(cls, name, props, children, values)`` for `Document.add` / `render`."""
    cls, _, name = path_seg.partition(" ")
    props = [(k, v) for k, v in spec.items() if not k.startswith("@") and not isinstance(v, dict)]
    kids = [_tuple_of(k, v) for k, v in spec.items() if isinstance(v, dict)]
    return cls, name, props, kids, spec.get("@values")


def apply(doc: Document, e: Edits, where: str = "") -> list[str]:
    """Apply ``e`` to ``doc`` in place. Returns notes; raises `FormatError` listing every
    path or key that isn't there (nothing half-applied is kept by callers: they parse a
    fresh `Document` per build)."""
    pre = f"{where}: " if where else ""
    problems: list[str] = []
    notes: list[str] = []
    # adds, parents first (a path may add under a block another add makes)
    for path in sorted(e.add, key=lambda p: len(split_path(p))):
        spec = e.add[path]
        parts = split_path(path)
        parent = None
        if len(parts) > 1:
            parent = doc.get("/".join(parts[:-1]))
            if parent is None:
                problems.append(f"add {path}: no block {'/'.join(parts[:-1])!r} to add it to"
                                f"{_hint(doc, '/'.join(parts[:-1]))}")
                continue
        sibs = parent.children if parent else doc.blocks
        index = None
        if "@after" in spec:
            after = spec["@after"]
            if after == "":
                index = 0
            else:
                k = next((i for i, b in enumerate(sibs) if seg(b).lower() == norm(after).lower()),
                         None)
                if k is None:
                    notes.append(f"{pre}add {path}: @after {after!r} isn't there, added last")
                else:
                    index = k + 1
        cls, name, props, kids, values = _tuple_of(parts[-1], spec)
        try:
            if "@text" in spec:                 # written as its source had it
                doc.add(parent, cls, name, index=index, text=spec["@text"])
            else:
                doc.add(parent, cls, name, props, kids, index, values)
        except FormatError as ex:
            problems.append(f"add {path}: {_strip(ex, doc)}")
    for path, keys in e.set.items():
        block = doc.get(path)
        if block is None:
            problems.append(f"set {path}: {_why_missing(doc, path)}")
            continue
        for k, v in keys.items():
            try:
                if v is None:
                    if not doc.unset(block, k):
                        notes.append(f"{pre}set {path}: no key {k} to remove")
                else:
                    doc.set(block, k, v)
            except FormatError as ex:
                problems.append(f"set {path} {k}: {_strip(ex, doc)}")
    for path in e.remove:
        block = doc.get(path)
        if block is None:
            problems.append(f"remove {path}: {_why_missing(doc, path)}")
            continue
        doc.remove(block)
    if problems:
        raise FormatError(f"{pre}" + ("\n  ".join(problems) if len(problems) == 1 else
                                      "\n  " + "\n  ".join(problems)))
    return notes


def _strip(ex: Exception, doc: Document) -> str:
    return str(ex).removeprefix(f"{doc.source}: ")


def _why_missing(doc: Document, path: str) -> str:
    try:
        doc.find(path)
    except FormatError as ex:
        return _strip(ex, doc) + _hint(doc, path)
    return "not found"


def _hint(doc: Document, path: str) -> str:
    """``(did you mean …)`` for a top-level name that differs only in its class or case."""
    last = split_path(path)[-1].partition(" ")[2].lower() if path else ""
    if not last:
        return ""
    near = [doc.path(b) for b in doc.walk() if b.name.lower() == last][:3]
    return f" (blocks with that name: {', '.join(near)})" if near else ""


# ---- diff -----------------------------------------------------------------------------

def diff(before: Document, after: Document) -> Edits:
    """The edits that turn ``before`` into ``after`` (blocks matched by path; a block whose
    path is not unique among its siblings is compared by its place among them)."""
    e = Edits()
    _diff(before.blocks, after.blocks, "", e)
    return e


def _keyed(blocks: list[Block]) -> list[tuple[str, Block]]:
    """Each block's path part: ``cls name``, or ``cls name#n`` (n from 1) for every block
    whose name repeats among its siblings (`levelscript.Document.find` reads it)."""
    count: dict[str, int] = {}
    for b in blocks:
        count[seg(b).lower()] = count.get(seg(b).lower(), 0) + 1
    seen: dict[str, int] = {}
    out = []
    for b in blocks:
        k = seg(b)
        n = seen.get(k.lower(), 0) + 1
        seen[k.lower()] = n
        out.append((k if count[k.lower()] == 1 else f"{k}#{n}", b))
    return out


def _diff(old: list[Block], new: list[Block], pre: str, e: Edits) -> None:
    a = dict((k.lower(), (k, b)) for k, b in _keyed(old))
    b = dict((k.lower(), (k, x)) for k, x in _keyed(new))
    for low, (k, blk) in a.items():
        if low not in b:
            if "#" in k:
                raise FormatError(f"{pre}{k}: two blocks share this path; can't diff them")
            e.remove.append(pre + k)
    order = [k for k, _ in _keyed(new)]
    for i, (k, blk) in enumerate(_keyed(new)):
        if "#" in k and k.lower() not in a:
            raise FormatError(f"{pre}{k}: two blocks share this path; can't diff them")
        if k.lower() not in a:
            spec = {"@text": blk.raw} if blk.raw is not None else spec_of(blk)
            if i < len(order) - 1:
                spec["@after"] = order[i - 1] if i else ""
            e.add[pre + k] = spec
            continue
        ob = a[k.lower()][1]
        changed: dict[str, str | None] = {}
        ov = {p.key.lower(): p for p in ob.props}
        nv = {p.key.lower(): p for p in blk.props}
        for low, p in nv.items():
            if low not in ov or ov[low].value != p.value:
                changed[p.key] = p.value
        for low, p in ov.items():
            if low not in nv:
                changed[p.key] = None
        if [v for v, _ in ob.values] != [v for v, _ in blk.values]:
            raise FormatError(f"{pre}{k}: its bare values changed; an .edits.json can't say "
                              f"that (remove the block and add it again)")
        if changed:
            e.set[pre + k] = changed
        _diff(ob.children, blk.children, f"{pre}{k}/", e)


# ---- several mods ---------------------------------------------------------------------

@dataclass
class Layer:
    """One mod's edits of a file, with what decides between mods."""
    mod: str
    priority: int
    edits: Edits


def merge(layers: list[Layer]) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Check several mods' edits of one file: returns ``(shadowed, problems)``.

    ``shadowed`` is ``(what, losing mod, winning mod)`` for every key or block two mods
    change (the higher priority is applied last, so it wins); ``problems`` lists the same
    thing at the **same** priority, and a set or add inside a block another mod removes.
    Two mods removing the same block agree, so that is fine.
    """
    shadowed: list[tuple[str, str, str]] = []
    problems: list[str] = []
    owner: dict[tuple, Layer] = {}
    removed: dict[str, Layer] = {}
    for L in sorted(layers, key=lambda L: L.priority):
        mine = {norm(r).lower() for r in L.edits.remove}
        for t, shown in L.edits.touched():
            if t[0] == "block" and t[1] in mine and t[1] in removed:
                continue                                # both remove it: they agree
            if t in owner and owner[t].mod != L.mod:
                if owner[t].priority == L.priority:
                    problems.append(f"{shown}: changed by both {owner[t].mod} and {L.mod} at "
                                    f"the same priority")
                else:
                    shadowed.append((shown, owner[t].mod, L.mod))
            owner[t] = L
        for r in mine:
            removed.setdefault(r, L)
    for path, L in removed.items():
        for t, other in owner.items():
            if other.mod == L.mod:
                continue
            inside = t[1].startswith(path + "/") or (t[0] == "key" and t[1] == path)
            if inside:
                problems.append(f"{t[1]}: {other.mod} changes it but {L.mod} removes {path}")
    return shadowed, problems


def apply_all(data: bytes, layers: list[Layer], where: str = "") -> tuple[bytes, list[str]]:
    """``data`` (a whole text file) with every layer applied, lowest priority first.
    Returns the new bytes and the notes."""
    doc = Document.parse(data, where or "<text>")
    notes: list[str] = []
    ordered = sorted(layers, key=lambda L: L.priority)
    for i, L in enumerate(ordered):
        edits = L.edits
        later = {norm(p).lower() for H in ordered[i + 1:] for p in H.edits.add}
        if later & {norm(p).lower() for p in edits.add}:     # a higher mod adds it too
            edits = Edits(edits.set, {p: v for p, v in edits.add.items()
                                      if norm(p).lower() not in later}, edits.remove)
            edits.set = {p: v for p, v in edits.set.items() if norm(p).lower() not in later}
        notes += apply(doc, edits, f"{L.mod}: {where}" if where else L.mod)
    return recount(doc.to_bytes(), doc), notes


HEADER_COUNT = re.compile(rb"^# (\w+) (\d+)(\r?)$", re.M)


def recount(data: bytes, doc: Document) -> bytes:
    """A file opening with ``# <class> <count>`` lines (the animation graph
    ``sgraph.txt``: one per block class, exactly the file's counts in both games) with
    those counts made true again after edits. The game sizes its pools from them: Case
    Zero faulted at boot (a null call) on a graph with blocks added and the old counts
    (2026-10-13). A class the header lacks is added after the last count line."""
    if not data.startswith(b"# "):
        return data
    from collections import Counter
    have = Counter(b.cls for b in doc.walk())
    seen: set[str] = set()

    def fix(m):
        cls = m.group(1).decode("latin-1")
        seen.add(cls)
        return b"# " + m.group(1) + b" " + str(have.get(cls, 0)).encode() + m.group(3)
    out = HEADER_COUNT.sub(fix, data)
    extra = [c for c in have if c not in seen]
    if extra and seen:
        last = list(HEADER_COUNT.finditer(out))[-1]
        nl = last.group(3) + b"\n"
        at = last.end() + 1                          # after the last count line's "\n"
        add = b"".join(b"# " + c.encode("latin-1") + b" " + str(have[c]).encode() + nl
                       for c in sorted(extra))
        out = out[:at] + add + out[at:]
    return out

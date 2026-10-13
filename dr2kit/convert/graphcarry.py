"""Bring an item's moves into the other game's animation graph (phase 15, U1 2026-10-13).

Why: the user's test of Case West's Impact Hammer in Case Zero: it was there, but "doesn't
properly attack". An item's moves are not found by name: its ``items.txt`` keys hold
**chooser values** (``AnimationAttackChooserValue<n> = "396"``), and the game's animation
graph ``data/datafile.big/sgraph.txt`` maps each value to an animation: a
``cCategoryChooser`` of a ``ChooserType`` holds ``cChooserEntryInt <name>`` entries with
``Value`` and ``Anim``, ``Anim`` being the number of a ``cAnimRef`` / ``cAnimGroup`` block
of the same state, whose ``File`` is the name hash of the ``.anm`` (the move bank holds the
``.anm``). Case Zero's graph has the Laser Sword's attacks (Dead Rising 2's) but not the
Impact Hammer's, so its values select nothing there.

Which key uses which chooser (measured on every item of both games, each key's values all
found in one chooser type): ``AnimationAttackChooserValue`` → ``ATTACKWEAPONTYPE`` (CZ 121
values, CW 147), ``WeaponImpactAnimation`` → ``WEAPONIMPACT`` (27 / 28),
``AnimationChooserValueForThrow`` → ``THROWTYPE`` (21 / 25). `KEYS`. The other chooser keys
take a few small values both games share.

`carry` copies, for one value: every source chooser of the type holding an entry with that
value → the target chooser of the same type sharing most entry names with it (state
numbers differ between the games: Case West's state 482 holds ``WEAPONIMPACT``, Case
Zero's 482 is a vehicle state) → the entry's animation block copied into the target
chooser's state with a new number (``cAnimRef`` / ``cAnimGroup`` numbers, and the
``Anim`` inside the copy, renumbered past the graph's largest), and a new entry with the
value kept when the target's choosers of that type don't use it, else the next free one
(the item's key then changes). An entry of the same name the target already has is used
as it is. Changes are made on a `Document` (the mod's ``sgraph.txt.edits.json`` through
`mods.leveledit.TextEdits`), so several imports into one mod share the numbering.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..formats.levelscript import Block, Document

GRAPH = "data/datafile.big/sgraph.txt"
KEYS = {"AnimationAttackChooserValue": "ATTACKWEAPONTYPE",
        "WeaponImpactAnimation": "WEAPONIMPACT",
        "AnimationChooserValueForThrow": "THROWTYPE"}
ANIM_BLOCKS = ("cAnimRef", "cAnimGroup")


def chooser_type(key: str) -> str | None:
    """The chooser type an ``items.txt`` key selects in (`KEYS`), or None."""
    return KEYS.get(re.sub(r"\d+$", "", key))


@dataclass
class Carried:
    """What `carry` did for one value."""
    value: str                       # the value the target uses (the item's key gets it)
    entries: list[str] = field(default_factory=list)    # entry names added or kept
    added: int = 0                   # entries added
    missing: bool = False            # the source graph has no entry with that value


def _choosers(doc: Document, ctype: str) -> list[tuple[Block, Block]]:
    """(state, chooser) for every chooser of ``ctype``; the state is the top-level block."""
    out = []
    for top in doc.blocks:
        for b in top.walk():
            if b.cls == "cCategoryChooser" and (b.get("ChooserType") or "") == ctype:
                out.append((top, b))
    return out


def _entries(chooser: Block) -> list[Block]:
    return [e for e in chooser.children if e.get("Value") is not None]


def _numbered(doc: Document) -> int:
    """The largest ``cAnimRef`` / ``cAnimGroup`` number of the graph."""
    return max((int(b.name) for b in doc.walk() if b.cls in ANIM_BLOCKS and b.name.isdigit()),
               default=0)


def _anim_block(state: Block, number: str) -> Block | None:
    return next((b for b in state.walk() if b.cls in ANIM_BLOCKS and b.name == number), None)


def carry(src: Document, dst: Document, ctype: str, value: str) -> Carried:
    """Make ``value`` of chooser type ``ctype`` select in ``dst`` what it selects in
    ``src`` (module docstring). Changes ``dst``."""
    found = [(st, ch, e) for st, ch in _choosers(src, ctype) for e in _entries(ch)
             if e.get("Value") == value]
    if not found:
        return Carried(value, missing=True)
    targets = _choosers(dst, ctype)
    used = {e.get("Value") for _, ch in targets for e in _entries(ch)}
    # the value the target uses: the same when free (or already this move), else a new one
    names = {e.name.lower() for _, _, e in found}
    same = [e for _, ch in targets for e in _entries(ch) if e.name.lower() in names]
    if same:
        new_value = same[0].get("Value")
    elif value not in used:
        new_value = value
    else:
        nums = [int(v) for v in used if v and v.lstrip("-").isdigit()]
        new_value = str(max(nums, default=0) + 1)
    out = Carried(new_value)
    next_number = _numbered(dst) + 1
    for st, ch, e in found:
        src_names = {x.name.lower() for x in _entries(ch)}
        best = max(targets, key=lambda t: len(src_names & {x.name.lower() for x in _entries(t[1])}),
                   default=None)
        if best is None:
            continue
        dst_state, dst_chooser = best
        if any(x.name.lower() == e.name.lower() for x in _entries(dst_chooser)):
            out.entries.append(e.name)
            continue
        anim = _anim_block(st, e.get("Anim") or "")
        if anim is None:
            continue
        text, renum = _renumbered(src, anim, next_number)
        next_number += len(renum)
        dst.add(dst_state, anim.cls, renum.get(anim.name, anim.name), text=text)
        entry = _retext(src.text(e), {"Anim": renum}, {"Value": new_value})
        dst.add(dst_chooser, e.cls, e.name, text=entry)
        out.entries.append(e.name)
        out.added += 1
    return out


def _renumbered(doc: Document, block: Block, start: int) -> tuple[str, dict[str, str]]:
    """``block``'s text with its animation blocks numbered from ``start`` (and every
    ``Anim`` inside it following them), written as the source has it (quoting, key order:
    the game's reader of this hand-written file is strict; Case Zero faulted at boot on
    the tool's style, 2026-10-13)."""
    renum: dict[str, str] = {}
    n = start
    for b in block.walk():
        if b.cls in ANIM_BLOCKS and b.name.isdigit() and b.name not in renum:
            renum[b.name] = str(n)
            n += 1
    lines = []
    for ln in doc.text(block).splitlines(keepends=True):
        m = HEADER.match(ln)
        if m and m.group(2) in renum:
            ln = f"{m.group(1)}{renum[m.group(2)]}{ln[m.end(2):]}"
        lines.append(ln)
    return _retext("".join(lines), {"Anim": renum}, {}), renum


HEADER = re.compile(r"^(\s*(?:cAnimRef|cAnimGroup) )(\d+)")
KEYLINE = re.compile(r'^(\s*(\w+) = "?)([^"\r\n]*)')


def _retext(text: str, remap: dict[str, dict[str, str]], put: dict[str, str]) -> str:
    """``text`` with ``Key = value`` lines changed: ``remap[key][old] -> new`` and
    ``put[key] = value`` (quoting kept)."""
    out = []
    for ln in text.splitlines(keepends=True):
        m = KEYLINE.match(ln)
        if m:
            key, val = m.group(2), m.group(3)
            if key in put:
                ln = m.group(1) + put[key] + ln[m.end(3):]
            elif key in remap and val in remap[key]:
                ln = m.group(1) + remap[key][val] + ln[m.end(3):]
        out.append(ln)
    return "".join(out)

"""Audio scripts: ``.sfx`` sound definitions and the audio scene scripts (``.txt``).

Both are the engine's block text format: ``cClassName ObjectName`` followed by a
``{ ... }`` block of ``Key = "value"`` lines and nested blocks. ``//`` starts a comment.

* A **`.sfx`** (4,745 in Case Zero, inside the ``fx_*.big`` banks next to the sounds)
  is one sound effect: a ``cSoundEffect`` with mixer category, volume, and one
  ``cSfxTrack`` per layer. Each track names its source recording, ``Sample =
  "cursorError43a_01a.wav"``; the bank's `.xma` of the same stem is that recording
  (``cursorError43a_01a.xma``). A ``Sample`` can also be another `.sfx` of the bank (a
  sub-effect, ``Distant1ShotNightFrogSUB1.sfx``). The game plays a `.sfx` by name, so its
  stem is the sound's event name. Measured: every track resolves inside its own bank
  except 22 (CZ) and 1 (CW) recordings that the shipped data doesn't contain.
* An **audio scene script** (``data/audio/Prologue.txt`` in Case Zero; ``Safehouse.txt``,
  ``SecureLab.txt``… and ``scenegraph.txt`` in Case West) wires game events to sounds:
  ``Asset = "music.big/HB_Indemnify"`` or ``"fx_main.big/FEError.sfx"``, ``BigFile =
  "fx_mechanic.big"`` (a bank to load), triggers, emitters, jukeboxes.

Case Zero checks ``Prologue.txt`` against a SHA-1 digest stored in the executable (the
CZ recomp's ``docs/phase3-notes.md``, finding 50), so an edited copy is not a safe way to
remap sounds there (docs/modding/10-audio.md).

The parser keeps everything (`Block`: class, name, ordered properties, children) and
reports what it could not read with line numbers (CLAUDE.md rule 6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..errors import FormatError

_HEADER = re.compile(r"^(c\w+)(?:\s+(.*?))?\s*$")
_PROP = re.compile(r'^(\w+)\s*=\s*"(.*)"\s*$')


@dataclass
class Block:
    """One ``cClass Name { ... }`` block."""
    cls: str
    name: str
    props: list[tuple[str, str]] = field(default_factory=list)
    children: list["Block"] = field(default_factory=list)
    line: int = 0

    def get(self, key: str, default: str | None = None) -> str | None:
        """The first value of ``key`` (case-insensitive), or ``default``."""
        k = key.lower()
        return next((v for p, v in self.props if p.lower() == k), default)

    def walk(self, path: tuple[str, ...] = ()):
        """Yield ``(path of names, block)`` for this block and every block inside it."""
        here = path + (self.name,)
        yield here, self
        for c in self.children:
            yield from c.walk(here)


def parse(text: str, source: str = "<memory>") -> list[Block]:
    """Parse a whole script. Raises `FormatError` with the line of the first problem."""
    roots: list[Block] = []
    stack: list[Block] = []
    pending: Block | None = None
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if line == "{":
            if pending is None:
                raise FormatError(f"{source}:{no}: '{{' without a block header")
            (stack[-1].children if stack else roots).append(pending)
            stack.append(pending)
            pending = None
            continue
        if pending is not None:
            raise FormatError(f"{source}:{no}: block {pending.cls} {pending.name!r} has no '{{'")
        if line == "}":
            if not stack:
                raise FormatError(f"{source}:{no}: '}}' with no open block")
            stack.pop()
            continue
        m = _PROP.match(line)
        if m:
            if not stack:
                raise FormatError(f"{source}:{no}: property outside any block")
            stack[-1].props.append((m.group(1), m.group(2)))
            continue
        m = _HEADER.match(line)
        if m:
            pending = Block(m.group(1), m.group(2) or "", line=no)
            continue
        raise FormatError(f"{source}:{no}: can't read {line[:60]!r}")
    if stack or pending is not None:
        raise FormatError(f"{source}: ends inside a block")
    return roots


def sfx_tracks(text: str, source: str = "<memory>") -> list[str]:
    """The bank entries a `.sfx` plays, in track order.

    ``Sample = "cursorError43a_01a.wav"`` → ``cursorError43a_01a.xma`` (the recording
    in the same bank); ``Sample = "FrogSUB1.sfx"`` → ``FrogSUB1.sfx`` (a sub-effect).
    """
    out = []
    for root in parse(text, source):
        for _, b in root.walk():
            s = b.get("Sample")
            if b.cls != "cSfxTrack" or not s:
                continue
            stem, dot, ext = s.rpartition(".")
            if not dot:
                stem, ext = s, "wav"
            out.append(stem + (".sfx" if ext.lower() == "sfx" else ".xma"))
    return out


@dataclass(frozen=True)
class ScriptRef:
    """One asset a scene script names, and where."""
    key: str          # "Asset" or "BigFile"
    value: str        # as written: "music.big/HB_Indemnify", "fx_mechanic.big"
    path: str         # names of the enclosing blocks: "Prologue/MechanicBattle/..."
    cls: str          # class of the block holding it
    line: int
    triggers: str = ""  # trigger properties of the block and its parents, "Key=value; ..."

    @property
    def context(self) -> str:
        """Where the reference sits, for people: block path, then its triggers."""
        return self.path + (f" ({self.triggers})" if self.triggers else "")

    @property
    def bank(self) -> str:
        """The archive name the reference starts with (``music.big``)."""
        return self.value.replace("\\", "/").split("/", 1)[0]

    @property
    def entry(self) -> str | None:
        """The entry inside the bank (``HB_Indemnify``), None for a whole bank."""
        parts = self.value.replace("\\", "/").split("/", 1)
        return parts[1] if len(parts) == 2 else None


def script_refs(text: str, source: str = "<memory>") -> list[ScriptRef]:
    """Every ``Asset`` and ``BigFile`` a scene script names."""
    out: list[ScriptRef] = []

    def visit(b: Block, path: tuple[str, ...], triggers: tuple[str, ...]) -> None:
        here = path + ((b.name,) if b.name else ())
        trig = triggers + tuple(f"{k}={v}" for k, v in b.props
                                if k in _TRIGGERS and v)
        for k, v in b.props:
            if k in ("Asset", "BigFile") and v:
                out.append(ScriptRef(k, v, "/".join(here), b.cls, b.line,
                                     "; ".join(dict.fromkeys(trig))))
        for c in b.children:
            visit(c, here, trig)

    for root in parse(text, source):
        visit(root, (), ())
    return out


# Properties that say which game event starts or stops a block (kept as context).
_TRIGGERS = ("ActivationEvent", "TriggerEvent", "TriggerPlay", "TriggerStop", "StartEvent",
             "TargetEvent", "EventToFire")

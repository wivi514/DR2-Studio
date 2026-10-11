"""The engine's block text files, read **without losing a byte** (phase 10).

The level files of ``data/datafile.big`` (``prologue.txt``, ``waypoint_prologue.txt``,
``nm_prologue.txt``…), ``items.txt`` and ``missions.txt`` share one format::

    cItemPlacement Scissors1          <- a block: class, then name
    {
        ItemName = "Scissors"         <- a property: Key = "value"
        Location = "-140.911,3.399,-89.938"
        cItemPlacement Inner { … }    <- blocks nest
    }
    Vertices                          <- a block with no class prefix (nav meshes)
    {
        "-287.896,3.373,-40.740"      <- a bare value
    }

with CRLF line ends, tabs, and ``//`` comments (also after a value: ``start = "0"
//Day 1 at 0:0``). `dr2kit.formats.audioscript` reads the same format for sounds but
keeps only the values; this reader keeps **every line as it was** (`Document.lines`),
and each block and property remembers its line, so:

* ``Document.to_bytes()`` gives back the file byte for byte (``dr2 census --levels``
  checks every level file of both games);
* an edit changes only the lines it touches (`Document.set`), the way a phase 11 level
  editor will save its changes (docs/phase11-kickoff.md).

Anything the reader can't place is an error naming the file and line (CLAUDE.md rule 6).
What the level files' classes mean: `dr2kit.convert.placed` and docs/formats.md §Levels.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..errors import FormatError

ENCODING = "latin-1"     # every byte maps to one character: nothing can fail to decode

_HEADER = re.compile(r"^([A-Za-z_]\w*)(?:[ \t]+(\S.*?))?$")
_PROP = re.compile(r'^(\w+)[ \t]*=[ \t]*(?:"([^"]*)"|([^\s"/]+))?[ \t]*(?://.*)?$')
_VALUE = re.compile(r'^"([^"]*)"[ \t]*(?://.*)?$')


@dataclass
class Prop:
    """``Key = "value"`` on line ``line`` (0-based index into `Document.lines`)."""
    key: str
    value: str
    line: int
    quoted: bool = True


@dataclass
class Block:
    """One block: ``cls`` (``cItemPlacement``, or a bare word such as ``Vertices``),
    ``name`` (may be empty), properties and bare values in file order, children."""
    cls: str
    name: str
    line: int                                   # the header line
    props: list[Prop] = field(default_factory=list)
    values: list[tuple[str, int]] = field(default_factory=list)
    children: list["Block"] = field(default_factory=list)
    end: int = -1                               # the closing brace's line

    def get(self, key: str, default: str | None = None) -> str | None:
        """The first value of ``key`` (case-insensitive), or ``default``."""
        k = key.lower()
        return next((p.value for p in self.props if p.key.lower() == k), default)

    def floats(self, key: str) -> tuple[float, ...] | None:
        """``"x,y,z"`` as floats, or None if the key is missing or not numbers."""
        v = self.get(key)
        if v is None:
            return None
        try:
            return tuple(float(c) for c in v.split(","))
        except ValueError:
            return None

    def numbered(self, prefix: str) -> list[str]:
        """``Vertex0``, ``Vertex1``… in number order (the files sort keys as text, so
        ``Vertex10`` comes before ``Vertex2``)."""
        out = {}
        n = len(prefix)
        for p in self.props:
            if p.key[:n].lower() == prefix.lower() and p.key[n:].isdigit():
                out[int(p.key[n:])] = p.value
        return [out[i] for i in sorted(out)]

    def walk(self):
        """This block and every block inside it, depth first."""
        yield self
        for c in self.children:
            yield from c.walk()


@dataclass
class Document:
    """A whole file: its lines (line ends included) and its top-level blocks."""
    lines: list[str]
    blocks: list[Block]
    source: str = "<memory>"
    props: list[Prop] = field(default_factory=list)     # properties outside any block

    @classmethod
    def parse(cls, data: bytes | str, source: str = "<memory>") -> "Document":
        text = data.decode(ENCODING) if isinstance(data, bytes) else data
        lines = text.splitlines(keepends=True)
        doc = cls(lines, [], source)
        stack: list[Block] = []
        pending: Block | None = None
        for no, raw in enumerate(lines):
            line = raw.strip()
            if not line or line.startswith("//") or line.startswith("#"):
                continue
            where = f"{source}:{no + 1}"
            if line == "{":
                if pending is None:
                    raise FormatError(f"{where}: '{{' without a block header")
                (stack[-1].children if stack else doc.blocks).append(pending)
                stack.append(pending)
                pending = None
                continue
            if pending is not None:
                raise FormatError(f"{where}: block {pending.cls} {pending.name!r} has no '{{'")
            if line == "}":
                if not stack:
                    raise FormatError(f"{where}: '}}' with no open block")
                stack.pop().end = no
                continue
            m = _PROP.match(line)
            if m:
                prop = Prop(m.group(1), m.group(2) if m.group(2) is not None else (m.group(3) or ""),
                            no, m.group(2) is not None)
                (stack[-1].props if stack else doc.props).append(prop)
                continue
            m = _VALUE.match(line)
            if m:
                if not stack:
                    raise FormatError(f"{where}: a value outside any block")
                stack[-1].values.append((m.group(1), no))
                continue
            m = _HEADER.match(line)
            if m:
                pending = Block(m.group(1), m.group(2) or "", no)
                continue
            raise FormatError(f"{where}: can't read {line[:60]!r}")
        if stack or pending is not None:
            raise FormatError(f"{source}: ends inside a block")
        return doc

    def to_bytes(self) -> bytes:
        """The file, as it was read plus any `set` edits."""
        return "".join(self.lines).encode(ENCODING)

    def walk(self):
        """Every block of the file, depth first."""
        for b in self.blocks:
            yield from b.walk()

    def set(self, block: Block, key: str, value: str) -> None:
        """Change (or add) one property, touching only its line: the rest of the file
        stays byte-identical (the way a level edit is saved, phase 11)."""
        if '"' in value or "\n" in value or "\r" in value:
            raise FormatError(f"{self.source}: a value can't hold quotes or line breaks")
        for p in block.props:
            if p.key.lower() == key.lower():
                old = self.lines[p.line]
                body = old.rstrip("\r\n")
                ending = old[len(body):]
                indent = body[:len(body) - len(body.lstrip())]
                self.lines[p.line] = f'{indent}{p.key} = "{value}"{ending}'
                p.value, p.quoted = value, True
                return
        # a new property: before the closing brace, indented like the block's others
        if block.end < 0:
            raise FormatError(f"{self.source}: block {block.name!r} has no closing brace")
        ref = self.lines[block.props[-1].line if block.props else block.end]
        body = ref.rstrip("\r\n")
        ending = ref[len(body):] or "\r\n"
        indent = body[:len(body) - len(body.lstrip())] or "\t"
        if not block.props:
            indent += "\t"
        self.lines.insert(block.end, f'{indent}{key} = "{value}"{ending}')
        at = block.end
        for b in self.walk():                    # later lines move down by one
            b.line += b.line >= at
            b.end += b.end >= at
            for p in b.props:
                p.line += p.line >= at
            b.values = [(v, n + (n >= at)) for v, n in b.values]
        block.props.append(Prop(key, value, at))

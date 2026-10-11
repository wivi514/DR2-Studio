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
* an edit changes only the lines it touches: `Document.set` / `unset` one property,
  `Document.add` / `remove` a whole block (phase 11, the level editor's ``.edits.json``
  mods, `dr2kit.formats.leveledits`). A new block or key is written in the style of the
  tool that wrote the files (measured over every file of both games, 2026-10-11): one tab
  per level, ``Key = "value"``, keys sorted ignoring case (when the block's own keys
  are; hand-ordered files such as ``zombiesets.txt`` keep their order and a new key goes
  last), properties before child blocks, no blank line before the first child, one blank
  line after each child, and the line end the file uses. ``dr2 census --levels`` checks
  that every shipped block of the edited files is written back by `render` exactly, and
  that removing a block and adding it back at its place gives the same file (byte for
  byte where the file keeps one gap size between siblings; some shipped files mix one
  and two blank lines, and a re-added block gets its neighbours' gap).

A block is addressed by its **path**, ``cls name`` per level joined with ``/``
(``cMissionDefinition PrologueZombies/cMissionLevelReady PrologueZombieReady/…``): names
are only unique within their parent (`Document.find`), and no name holds a ``/`` or a
space (checked over both games).

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
_VALUE_SPAN = re.compile(r'^(\s*\w+[ \t]*=[ \t]*)(?:"[^"]*"|[^\s"/]+)')   # up to the value's end


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

    # ---- finding blocks ----------------------------------------------------------------

    @property
    def newline(self) -> str:
        """The file's line end (``\\r\\n`` for every shipped file)."""
        for ln in self.lines:
            body = ln.rstrip("\r\n")
            if len(body) != len(ln):
                return ln[len(body):]
        return "\r\n"

    def find(self, path: str) -> Block:
        """The block at ``path`` (module docstring), or `FormatError` saying which part is
        missing or matches more than one block (case-insensitive)."""
        here: list[Block] = self.blocks
        found: Block | None = None
        done = []
        for part in split_path(path):
            hits = [b for b in here if seg(b).lower() == part.lower()]
            if not hits:
                raise FormatError(f"{self.source}: no block {part!r}"
                                  + (f" in {'/'.join(done)}" if done else ""))
            if len(hits) > 1:
                raise FormatError(f"{self.source}: {len(hits)} blocks named {part!r}"
                                  + (f" in {'/'.join(done)}" if done else "")
                                  + "; a path must name one")
            found = hits[0]
            here = found.children
            done.append(seg(found))
        if found is None:
            raise FormatError(f"{self.source}: an empty block path")
        return found

    def get(self, path: str) -> Block | None:
        """`find`, or None when the path names no block (or more than one)."""
        try:
            return self.find(path)
        except FormatError:
            return None

    def parent(self, block: Block) -> Block | None:
        """The block holding ``block`` (None at the top of the file)."""
        for b in self.walk():
            if any(c is block for c in b.children):
                return b
        return None

    def path(self, block: Block) -> str:
        """``block``'s path (`find` gives it back)."""
        parts = []
        b: Block | None = block
        while b is not None:
            parts.append(seg(b))
            b = self.parent(b)
        return "/".join(reversed(parts))

    def text(self, block: Block) -> str:
        """The block's lines as they are in the file (header to closing brace)."""
        return "".join(self.lines[block.line:block.end + 1])

    # ---- editing -------------------------------------------------------------------------

    def set(self, block: Block, key: str, value: str) -> None:
        """Change (or add) one property, touching only its line: the rest of the file
        stays byte-identical (the way a level edit is saved, phase 11), and so does the
        rest of the line (its spacing, a ``// comment`` after the value: the costs in
        ``zombiesets.txt``). A new key goes where the tool would have sorted it (module
        docstring)."""
        _check_value(value, self.source)
        for p in block.props:
            if p.key.lower() == key.lower():
                old = self.lines[p.line]
                body = old.rstrip("\r\n")
                ending = old[len(body):]
                m = _VALUE_SPAN.match(body)
                if m:                    # keep the spacing and a trailing // comment
                    self.lines[p.line] = f'{m.group(1)}"{value}"{body[m.end():]}{ending}'
                else:
                    indent = body[:len(body) - len(body.lstrip())]
                    self.lines[p.line] = f'{indent}{p.key} = "{value}"{ending}'
                p.value, p.quoted = value, True
                return
        if block.end < 0:
            raise FormatError(f"{self.source}: block {block.name!r} has no closing brace")
        _check_key(key, self.source)
        indent = self._indent(block) + "\t"
        keys = [p.key.lower() for p in block.props]
        if block.props and keys == sorted(keys):
            at_prop = next((i for i, k in enumerate(keys) if k > key.lower()), len(keys))
        else:
            at_prop = len(keys)
        if at_prop < len(block.props):
            at = block.props[at_prop].line
        elif block.props:
            at = block.props[-1].line + 1
        elif block.values:
            at = block.values[0][1]
        else:
            at = block.children[0].line if block.children else block.end
        self._insert(at, [f'{indent}{key} = "{value}"{self.newline}'])
        block.props.insert(at_prop, Prop(key, value, at))

    def unset(self, block: Block, key: str) -> bool:
        """Remove one property's line; False if the block hasn't it."""
        for i, p in enumerate(block.props):
            if p.key.lower() == key.lower():
                del block.props[i]
                self._delete(p.line, p.line)
                return True
        return False

    def remove(self, block: Block) -> None:
        """Remove a block (and the blocks inside it), with the blank line that kept it
        apart from its neighbours, so removing and adding it back at the same index
        gives the file byte for byte."""
        parent = self.parent(block)
        sibs = parent.children if parent else self.blocks
        i = next(k for k, b in enumerate(sibs) if b is block)
        first, last = block.line, block.end
        if i > 0:                                    # the gap before it
            first = sibs[i - 1].end + 1
        elif len(sibs) > 1:                          # first of several: the gap after it
            last = sibs[1].line - 1
        elif parent is not None:                     # an only child: up to the brace
            last = parent.end - 1
        del sibs[i]
        self._delete(first, last)

    def add(self, parent: Block | None, cls: str, name: str = "",
            props: list[tuple[str, str]] | dict | None = None,
            children: list | None = None, index: int | None = None,
            values: list[str] | None = None) -> Block:
        """Add a block under ``parent`` (None: at the top of the file), at ``index``
        among its siblings (default: last), written in the tool's style (`render`).
        ``children`` are ``(cls, name, props, children[, values])`` tuples (the same
        shape, nested; `to_spec`). Returns the new block (with its lines). Raises `FormatError` when a
        sibling already has that class and name."""
        sibs = parent.children if parent else self.blocks
        key = f"{cls} {name}".strip().lower()
        if name and any(seg(b).lower() == key for b in sibs):
            raise FormatError(f"{self.source}: there is already a block {cls} {name}"
                              + (f" in {self.path(parent)}" if parent else ""))
        depth = self._depth(parent) + 1 if parent else 0
        nl = self.newline
        body = render(cls, name, props, children, depth, nl, values)
        if index is None or index > len(sibs):
            index = len(sibs)
        gap = [nl] * self._gap(parent)
        if sibs and index > 0:                       # after the previous sibling
            at = sibs[index - 1].end + 1
            new = gap + body
        elif sibs:                                   # before the first one
            at = sibs[0].line
            new = body + gap
        elif parent is not None:                     # the parent's first child
            at = parent.end
            new = body + [nl]
        else:                                        # an empty file
            at = len(self.lines)
            new = body + [nl]
        self._insert(at, new)
        start = at + (len(gap) if sibs and index > 0 else 0)
        made = Document.parse("".join(body), self.source).blocks[0]
        _move(made, start)
        sibs.insert(index, made)
        return made

    # ---- line bookkeeping ----------------------------------------------------------------

    def _depth(self, block: Block) -> int:
        body = self.lines[block.line]
        return len(body) - len(body.lstrip("\t"))

    def _indent(self, block: Block) -> str:
        return "\t" * self._depth(block)

    def _gap(self, parent: Block | None) -> int:
        """Blank lines between siblings here: as the file has them (the tool writes 1,
        ``missions.txt`` 2 between its missions), else 1."""
        sibs = parent.children if parent else self.blocks
        for a, b in zip(sibs, sibs[1:]):
            return b.line - a.end - 1
        return 1

    def _insert(self, at: int, new: list[str]) -> None:
        self._shift(at, len(new))
        self.lines[at:at] = new

    def _delete(self, first: int, last: int) -> None:
        del self.lines[first:last + 1]
        n = last - first + 1
        for b in self.walk():
            for attr in ("line", "end"):
                v = getattr(b, attr)
                if v > last:
                    setattr(b, attr, v - n)
            for p in b.props:
                if p.line > last:
                    p.line -= n
            b.values = [(v, k - n if k > last else k) for v, k in b.values]
        for p in self.props:
            if p.line > last:
                p.line -= n

    def _shift(self, at: int, n: int) -> None:
        """Every line at or after ``at`` moves down by ``n``."""
        for b in self.walk():
            b.line += n if b.line >= at else 0
            b.end += n if b.end >= at else 0
            for p in b.props:
                p.line += n if p.line >= at else 0
            b.values = [(v, k + n if k >= at else k) for v, k in b.values]
        for p in self.props:
            p.line += n if p.line >= at else 0


def seg(block: Block) -> str:
    """One path part: ``cls name`` (``cls`` alone for a block without a name)."""
    return f"{block.cls} {block.name}" if block.name else block.cls


def split_path(path: str) -> list[str]:
    """``"a b/c d"`` → ``["a b", "c d"]`` (spaces around a part are dropped)."""
    return [" ".join(p.split()) for p in path.split("/") if p.strip()]


def render(cls: str, name: str = "", props=None, children=None, depth: int = 0,
           nl: str = "\r\n", values: list[str] | None = None) -> list[str]:
    """A block's lines in the tool's style (module docstring). ``props`` is a dict or
    ``(key, value)`` pairs; their order is the tool's (sorted, ignoring case)."""
    t = "\t" * depth
    pairs = list(props.items()) if isinstance(props, dict) else list(props or ())
    for k, v in pairs:
        _check_key(k, cls)
        _check_value(v, cls)
    pairs.sort(key=lambda kv: kv[0].lower())
    out = [f"{t}{cls} {name}{nl}" if name else f"{t}{cls}{nl}", f"{t}{{{nl}"]
    out += [f'{t}\t{k} = "{v}"{nl}' for k, v in pairs]
    out += [f'{t}\t"{_check_value(v, cls)}"{nl}' for v in values or ()]
    for c in children or ():
        if isinstance(c, Block):
            out += render_block(c, depth + 1, nl)
        else:
            ccls, cname, cprops, ckids, *cvals = c
            out += render(ccls, cname, cprops, ckids, depth + 1, nl,
                          cvals[0] if cvals else None)
        out.append(nl)
    out.append(f"{t}}}{nl}")
    return out


def render_block(block: Block, depth: int = 0, nl: str = "\r\n") -> list[str]:
    """A parsed block written again by `render` (the census compares it with the file)."""
    return render(block.cls, block.name, [(p.key, p.value) for p in block.props],
                  block.children, depth, nl, [v for v, _ in block.values])


def to_spec(block: Block) -> tuple:
    """``(cls, name, props, children, values)`` of a parsed block, the shape
    `Document.add` takes (props in file order)."""
    return (block.cls, block.name, [(p.key, p.value) for p in block.props],
            [to_spec(c) for c in block.children], [v for v, _ in block.values])


def _move(block: Block, start: int) -> None:
    """Line numbers of a block parsed on its own, moved to start at ``start``."""
    for b in block.walk():
        b.line += start
        b.end += start
        for p in b.props:
            p.line += start
        b.values = [(v, k + start) for v, k in b.values]


def _check_value(value: str, where: str) -> str:
    if not isinstance(value, str):
        raise FormatError(f"{where}: a value must be text, got {type(value).__name__}")
    if '"' in value or "\n" in value or "\r" in value:
        raise FormatError(f"{where}: a value can't hold quotes or line breaks ({value[:40]!r})")
    return value


def _check_key(key: str, where: str) -> None:
    if not re.fullmatch(r"\w+", key or ""):
        raise FormatError(f"{where}: {key!r} is not a key (letters, digits and _)")

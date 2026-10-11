"""The Library's groups: sort assets by what they are (characters, music, rigs…).

The games store things by how they are loaded: a character is a model in
``npcs.big``, its textures in a ``.tex`` pack next to it, its rig in ``skeleton/``;
a footstep sound is one entry of ``streamedassets.big/fx_ftspsneaker.big``. A modder
looks for *Chuck's shirt* or *the title music*. This module puts each asset into one
group, an optional sub-group and a friendlier label, from the rules in ``groups.toml``
(data, so a new group needs no code: see the comments at the top of that file).

The index stores the result (table ``library_item``, filled by
`dr2kit.index.build.link_library` after every build), so DR2 Studio's Library tab and
``dr2 export <group>`` read it in milliseconds. Identical copies (same bytes, e.g. a
skeleton in ``skeleton/`` and again in ``preload4.big``) are shown once: the others
point at it (`copy_of`) and are listed as "also in…".

Docs: docs/ARCHITECTURE.md §The Library, docs/modding/16-library.md.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources

from ..formats.scene import texture_role

ROLE_TITLES = {"colour": "Colour", "normal": "Normal maps", "specular": "Specular",
               "mask": "Masks", "detail": "Detail", "reflection": "Reflection",
               "self-illum": "Self-illumination", "opacity": "Opacity", "glow": "Glow",
               "lightmap": "Lightmaps (levels)", "other": "Other"}


def glob_regex(pattern: str) -> re.Pattern:
    """A path glob as a regex: ``*`` within one path part, ``**`` across parts."""
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        out.append("[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c))
        i += 1
    return re.compile("".join(out) + r"\Z")


def _pretty(text: str, capital: bool) -> str:
    text = text.replace("_", " ").strip()
    if capital:
        return " ".join(w[:1].upper() + w[1:] for w in text.split(" ") if w)
    return text


_GROUP_KEYS = {"id", "section", "title", "description", "kinds", "paths", "sub_path",
               "sub_name", "sub_role", "sub_names", "sub_default"}


@dataclass
class Group:
    """One ``[[group]]`` of groups.toml."""
    id: str
    section: str
    title: str
    description: str
    kinds: tuple[str, ...]
    paths: tuple[re.Pattern, ...]
    sub_path: re.Pattern | None = None
    sub_name: re.Pattern | None = None
    sub_role: bool = False
    sub_names: list[tuple[re.Pattern, str]] = field(default_factory=list)
    sub_default: str = ""

    def matches(self, kind: str, vpath_lower: str) -> bool:
        return kind in self.kinds and any(p.match(vpath_lower) for p in self.paths)

    def sub(self, vpath_lower: str, name: str) -> str:
        """The sub-group an asset of this group goes in ('' when the group isn't split)."""
        if self.sub_role:
            return ROLE_TITLES.get(texture_role(name.lower().removesuffix(".bct")), "Other")
        rx, text = ((self.sub_path, vpath_lower) if self.sub_path is not None
                    else (self.sub_name, name.lower()) if self.sub_name is not None
                    else (None, ""))
        if rx is None:
            return ""
        m = rx.search(text)
        raw = "".join(g for g in m.groups() if g) if m else ""
        if not raw:
            return self.sub_default
        for pat, label in self.sub_names:
            if pat.match(raw):
                return label
        return raw.replace("/", " / ")


@dataclass
class LabelRule:
    groups: tuple[str, ...]
    pattern: re.Pattern
    format: str

    def apply(self, stem: str) -> str | None:
        m = self.pattern.match(stem)
        if not m:
            return None
        values = {}
        for k, v in m.groupdict().items():
            v = v or ""
            values[k] = _pretty(v, False)
            values[k[:1].upper() + k[1:]] = _pretty(v, True)
        return self.format.format(**values)


@dataclass
class DetailRule:
    """``[[detail]]``: files of one model at several detail levels (``zombie_cop_2``,
    ``_3``, ``_4``), shown as one Library item (phase 9)."""
    groups: tuple[str, ...]
    pattern: re.Pattern            # named groups: base, n
    levels: dict[str, str]         # n -> level name ("2" -> "high"), in order of detail


@dataclass
class Catalog:
    """The rules of groups.toml, ready to apply."""
    groups: list[Group]
    labels: list[LabelRule]
    names: dict[str, dict[str, str]]          # group id -> name -> label
    details: list[DetailRule] = field(default_factory=list)

    @classmethod
    def from_toml(cls, text: str) -> "Catalog":
        data = tomllib.loads(text)
        unknown = set(data) - {"group", "label", "names", "detail"}
        if unknown:
            raise ValueError(f"groups.toml: unknown table(s) {', '.join(sorted(unknown))}")
        groups = []
        for g in data.get("group", []):
            extra = set(g) - _GROUP_KEYS
            if extra:
                # a key misplaced under the last [[group]] would otherwise be ignored silently
                raise ValueError(f"groups.toml: group {g.get('id')!r} has unknown key(s) "
                                 f"{', '.join(sorted(extra))}")
            groups.append(Group(
                g["id"], g["section"], g["title"], g.get("description", ""),
                tuple(g["kinds"]), tuple(glob_regex(p) for p in g["paths"]),
                re.compile(g["sub_path"]) if "sub_path" in g else None,
                re.compile(g["sub_name"]) if "sub_name" in g else None,
                bool(g.get("sub_role", False)),
                [(glob_regex(k), v) for k, v in g.get("sub_names", {}).items()],
                g.get("sub_default", "")))
        ids = [g.id for g in groups]
        if len(set(ids)) != len(ids):
            raise ValueError("groups.toml: a group id is used twice")
        labels = [LabelRule(tuple(r["groups"]), re.compile(r["pattern"], re.IGNORECASE),
                            r["format"]) for r in data.get("label", [])]
        names = {gid: {k.lower(): v for k, v in table.items()}
                 for gid, table in data.get("names", {}).items()}
        details = [DetailRule(tuple(r["groups"]), re.compile(r["pattern"], re.IGNORECASE),
                              {str(k): v for k, v in r["levels"].items()})
                   for r in data.get("detail", [])]
        return cls(groups, labels, names, details)

    def detail(self, group_id: str, name: str) -> tuple[str, int, str] | None:
        """``(model base name, rank, level name)`` when ``name`` is one detail level of a
        model (rank 0 = the most detailed), else None."""
        stem = name.rsplit(".", 1)[0] if "." in name else name
        for r in self.details:
            if group_id in r.groups:
                m = r.pattern.match(stem)
                if m and m.group("n") in r.levels:
                    order = list(r.levels)
                    return m.group("base").lower(), order.index(m.group("n")), \
                        r.levels[m.group("n")]
        return None

    def group(self, group_id: str) -> Group | None:
        return next((g for g in self.groups if g.id == group_id), None)

    def sections(self) -> list[str]:
        """Section titles in file order (Models, Skeletons, Sounds, …)."""
        out: list[str] = []
        for g in self.groups:
            if g.section not in out:
                out.append(g.section)
        return out

    def place(self, game: str, kind: str, vpath: str, name: str) -> tuple[str, str, str] | None:
        """``(group id, sub-group, label)`` for an asset, or None when no group takes it."""
        low = vpath.lower()
        for g in self.groups:
            if g.matches(kind, low):
                return g.id, g.sub(low, name), self.label(g.id, game, name)
        return None

    def label(self, group_id: str, game: str, name: str) -> str:
        """A friendlier name for an asset ('' when the game's name is all there is)."""
        stem = name.rsplit(".", 1)[0] if "." in name else name
        low = stem.lower()
        table = self.names.get(group_id, {})
        hit = table.get(f"{game}:{low}") or table.get(low)
        if hit:
            return hit
        for r in self.labels:
            if group_id in r.groups:
                text = r.apply(stem)
                if text is not None:
                    return text
        return ""


@lru_cache(maxsize=1)
def catalog() -> Catalog:
    """The toolkit's own rules (``groups.toml`` next to this module)."""
    return Catalog.from_toml(resources.files(__package__).joinpath("groups.toml")
                             .read_text("utf-8"))


def slug(text: str) -> str:
    """A folder name for a group or sub-group: lower case, safe on every OS."""
    s = re.sub(r"[^a-z0-9._-]+", "-", text.lower()).strip("-.")
    return s or "other"


def check(con, game: str) -> tuple[list[str], list[str]]:
    """The Library's count gate for one game: ``(report lines, problems)``.

    Checks that (1) every indexed asset of a kind the Library shows is in it, shown or
    folded into an identical copy, except text inside models (their ``UsedShaders.txt``);
    (2) placing each asset again with the current rules gives the stored group and
    sub-group (a stale index says so); (3) every copy points at a shown item with the
    same bytes. ``problems`` empty = the counts Studio and ``dr2 library`` show match the
    index."""
    cat = catalog()
    kinds = sorted({k for g in cat.groups for k in g.kinds})
    report, problems = [], []
    stored = {r["asset_id"]: r for r in con.execute(
        "SELECT * FROM library_item WHERE game=?", (game,))}
    marks = ",".join("?" * len(kinds))
    per_kind: dict[str, list[int]] = {k: [0, 0, 0, 0] for k in kinds}   # index, shown, copies, out
    for a in con.execute(f"""
            SELECT a.id, a.vpath, a.name, a.kind, a.sha1, p.kind AS parent_kind,
                   pp.kind AS grandparent_kind
            FROM asset a LEFT JOIN asset p ON p.id = a.parent_id
            LEFT JOIN asset pp ON pp.id = p.parent_id
            WHERE a.game = ? AND a.kind IN ({marks})""", (game, *kinds)):
        c = per_kind[a["kind"]]
        c[0] += 1
        row = stored.get(a["id"])
        hit = cat.place(game, a["kind"], a["vpath"], a["name"])
        if row is None:
            c[3] += 1
            in_scene = "model" in (a["parent_kind"], a["grandparent_kind"]) or \
                "skeleton" in (a["parent_kind"], a["grandparent_kind"])
            if hit is not None:
                problems.append(f"{a['vpath']}: belongs in {hit[0]} but isn't in the Library "
                                f"(index older than the rules: rebuild it)")
            elif not (a["kind"] == "text" and in_scene):
                problems.append(f"{a['vpath']}: a {a['kind']} in no Library group")
            continue
        if hit is None or (hit[0], hit[1]) != (row["grp"], row["sub"]):
            problems.append(f"{a['vpath']}: stored in {row['grp']}/{row['sub']}, the rules say "
                            f"{hit[0] + '/' + hit[1] if hit else 'no group'} (rebuild the index)")
        if row["copy_of"] is None:
            c[1] += 1
        else:
            c[2] += 1
            keep = stored.get(row["copy_of"])
            same = con.execute("SELECT sha1 FROM asset WHERE id=?", (row["copy_of"],)).fetchone()
            if keep is None or keep["copy_of"] is not None or same is None or same[0] != a["sha1"]:
                problems.append(f"{a['vpath']}: copy of asset {row['copy_of']}, which isn't a "
                                f"shown item with the same bytes")
    report.append(f"{'kind':<10} {'indexed':>8} {'shown':>8} {'copies':>8} {'not shown':>10}")
    for k, (n, shown, cp, out) in per_kind.items():
        if n:
            report.append(f"{k:<10} {n:>8} {shown:>8} {cp:>8} {out:>10}"
                          + ("   (text inside models)" if k == "text" and out else ""))
            if shown + cp + out != n:
                problems.append(f"{k}: {n} indexed but {shown} + {cp} + {out} counted")
    return report, problems

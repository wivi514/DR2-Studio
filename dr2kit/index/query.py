"""Read the asset index: search, browse, and follow relations.

Every function takes an open connection (`dr2kit.index.build.connect`) and returns
plain `sqlite3.Row` objects (use them like dicts: ``row["vpath"]``). DR2 Studio and
``dr2 index`` both go through here, so the SQL lives in one place.

The Library (phase 8): `library_counts` / `library_items` list the groups of
dr2kit/catalog/groups.toml as the index stored them, `picture` gives an item's
thumbnail, `rigs_of` the skeletons a model's bones match, `copies` the identical
copies folded into one item.

Search syntax (`search`): words are matched against asset names, all must match
(``mech apron`` finds ``mech_apron_cm``); ``*`` and ``?`` work as wildcards; a word
with a ``/`` is matched against the whole vpath instead (``npcs.big/ apron``).
"""

from __future__ import annotations

import sqlite3

ASSET_COLUMNS = ("a.id, a.game, a.vpath, a.parent_id, a.depth, a.position, a.name, a.ext, "
                 "a.kind, a.stored_size, a.size, a.compressed, a.flags, a.sha1")


def _like(word: str) -> str:
    w = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    w = w.replace("*", "%").replace("?", "_")
    return w if ("%" in w or "_" in w.replace("\\_", "")) else f"%{w}%"


def search(con: sqlite3.Connection, text: str, *, game: str | None = None,
           kind: str | None = None, fmt: str | None = None, limit: int = 500) -> list[sqlite3.Row]:
    """Assets whose name (or vpath, for words with ``/``) matches every word of ``text``."""
    where, args = [], []
    for word in text.split():
        col = "a.vpath_lower" if "/" in word else "lower(a.name)"
        where.append(f"{col} LIKE ? ESCAPE '\\'")
        args.append(_like(word.lower()))
    if game:
        where.append("a.game = ?")
        args.append(game)
    if kind:
        where.append("a.kind = ?")
        args.append(kind)
    join = ""
    if fmt:
        join = "JOIN texture t ON t.asset_id = a.id"
        where.append("t.format = ?")
        args.append(fmt)
    sql = (f"SELECT {ASSET_COLUMNS} FROM asset a {join} "
           f"{'WHERE ' + ' AND '.join(where) if where else ''} "
           f"ORDER BY a.game, a.vpath_lower LIMIT ?")
    return con.execute(sql, (*args, limit)).fetchall()


def get(con: sqlite3.Connection, game: str, vpath: str) -> sqlite3.Row | None:
    """The asset at ``vpath`` (case-insensitive), or None."""
    return con.execute(f"SELECT {ASSET_COLUMNS} FROM asset a WHERE a.game=? AND a.vpath_lower=?",
                       (game, vpath.lower().replace("\\", "/").strip("/"))).fetchone()


def by_id(con: sqlite3.Connection, asset_id: int) -> sqlite3.Row | None:
    return con.execute(f"SELECT {ASSET_COLUMNS} FROM asset a WHERE a.id=?", (asset_id,)).fetchone()


def children(con: sqlite3.Connection, parent_id: int) -> list[sqlite3.Row]:
    """The entries of an archive, in archive order."""
    return con.execute(f"SELECT {ASSET_COLUMNS} FROM asset a WHERE a.parent_id=? "
                       f"ORDER BY a.position", (parent_id,)).fetchall()


def files(con: sqlite3.Connection, game: str) -> list[sqlite3.Row]:
    """The files on disk of one game, sorted by vpath."""
    return con.execute(f"SELECT {ASSET_COLUMNS} FROM asset a WHERE a.game=? AND a.depth=0 "
                       f"ORDER BY a.vpath_lower", (game,)).fetchall()


def texture_info(con: sqlite3.Connection, asset_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM texture WHERE asset_id=?", (asset_id,)).fetchone()


def thumbnail(con: sqlite3.Connection, asset_id: int) -> bytes | None:
    row = con.execute("SELECT thumb_png FROM texture WHERE asset_id=?", (asset_id,)).fetchone()
    return row[0] if row else None


def textures_of(con: sqlite3.Connection, model_id: int) -> list[sqlite3.Row]:
    """The textures a model's material slots name (best match first per slot)."""
    return con.execute(f"""
        SELECT r.slot, r.dst_name, r.rank, {ASSET_COLUMNS}
        FROM relation r LEFT JOIN asset a ON a.id = r.dst_id
        WHERE r.src_id = ? AND r.kind = 'material-texture'
        ORDER BY r.slot, r.rank, a.vpath_lower""", (model_id,)).fetchall()


def used_by(con: sqlite3.Connection, texture_id: int) -> list[sqlite3.Row]:
    """The models whose material slots name this texture (closest first)."""
    return con.execute(f"""
        SELECT DISTINCT r.rank, {ASSET_COLUMNS}
        FROM relation r JOIN asset a ON a.id = r.src_id
        WHERE r.dst_id = ? AND r.kind = 'material-texture'
        ORDER BY r.rank, a.vpath_lower""", (texture_id,)).fetchall()


def same_content(con: sqlite3.Connection, asset_id: int) -> list[sqlite3.Row]:
    """Other assets with identical bytes (same SHA-1), e.g. a texture shipped in many packs."""
    return con.execute(f"""
        SELECT {ASSET_COLUMNS} FROM asset a
        WHERE a.sha1 = (SELECT sha1 FROM asset WHERE id=?) AND a.id <> ?
        ORDER BY a.game, a.vpath_lower""", (asset_id, asset_id)).fetchall()


def counts(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """Assets per game and kind (for ``dr2 index stats``)."""
    return con.execute("SELECT game, kind, count(*) AS n FROM asset GROUP BY game, kind "
                       "ORDER BY game, n DESC").fetchall()


def games_indexed(con: sqlite3.Connection) -> list[str]:
    return [r[0] for r in con.execute("SELECT DISTINCT game FROM asset ORDER BY game")]


def audio_info(con: sqlite3.Connection, asset_id: int) -> sqlite3.Row | None:
    """Channels, rate, length and loop of a sound (the ``audio`` table)."""
    return con.execute("SELECT * FROM audio WHERE asset_id=?", (asset_id,)).fetchone()


def sound_targets(con: sqlite3.Connection, src_id: int) -> list[sqlite3.Row]:
    """What a ``.sfx`` plays, or what an audio scene script names (in file order)."""
    return con.execute(f"""
        SELECT r.kind AS rel_kind, r.slot, r.dst_name, s.context, {ASSET_COLUMNS}
        FROM relation r LEFT JOIN asset a ON a.id = r.dst_id
        LEFT JOIN sound_ref s ON s.src_id = r.src_id AND s.slot = r.slot AND s.kind = r.kind
        WHERE r.src_id = ? AND r.kind IN ('sfx-track', 'script-asset')
        ORDER BY r.slot""", (src_id,)).fetchall()


def sound_users(con: sqlite3.Connection, asset_id: int) -> list[sqlite3.Row]:
    """Who plays this sound: the ``.sfx`` whose tracks name it, the scripts whose
    ``Asset`` lines name it or such a ``.sfx`` (with the events that trigger them)."""
    return con.execute(f"""
        SELECT DISTINCT r.kind AS rel_kind, s.context, {ASSET_COLUMNS}
        FROM relation r JOIN asset a ON a.id = r.src_id
        LEFT JOIN sound_ref s ON s.src_id = r.src_id AND s.slot = r.slot AND s.kind = r.kind
        WHERE r.kind IN ('sfx-track', 'script-asset')
          AND (r.dst_id = ? OR r.dst_id IN
               (SELECT x.src_id FROM relation x WHERE x.dst_id = ? AND x.kind = 'sfx-track'))
        ORDER BY r.kind, a.vpath_lower""", (asset_id, asset_id)).fetchall()


# ---- the Library (phase 8) -------------------------------------------------------------

def library_counts(con: sqlite3.Connection, game: str) -> list[sqlite3.Row]:
    """Shown items per group and sub-group (identical copies counted once)."""
    return con.execute("""
        SELECT grp, sub, count(*) AS n FROM library_item
        WHERE game = ? AND copy_of IS NULL AND detail_of IS NULL
        GROUP BY grp, sub ORDER BY grp, sub""",
                       (game,)).fetchall()


def library_items(con: sqlite3.Connection, game: str, grp: str, sub: str | None = None,
                  text: str = "", limit: int | None = None, details: bool = False
                  ) -> list[sqlite3.Row]:
    """The items shown in a group (or one of its sub-groups), with their label and
    sub-group, by label then name. ``text``: words that must all appear in the label or
    the name. ``details``: also the lower detail levels folded into an item (exports)."""
    where, args = ["l.game = ?", "l.grp = ?", "l.copy_of IS NULL"], [game, grp]
    if not details:
        where.append("l.detail_of IS NULL")
    if sub is not None:
        where.append("l.sub = ?")
        args.append(sub)
    for word in text.lower().split():
        where.append("(lower(l.label) LIKE ? ESCAPE '\\' OR lower(a.name) LIKE ? ESCAPE '\\')")
        args += [_like(word)] * 2
    sql = (f"SELECT {ASSET_COLUMNS}, l.grp, l.sub, l.label, l.detail, l.detail_of "
           f"FROM library_item l "
           f"JOIN asset a ON a.id = l.asset_id WHERE {' AND '.join(where)} "
           f"ORDER BY l.sub, (l.label = ''), lower(l.label), lower(a.name)")
    if limit:
        sql += f" LIMIT {int(limit)}"
    return con.execute(sql, args).fetchall()


def library_item(con: sqlite3.Connection, asset_id: int) -> sqlite3.Row | None:
    """An asset's Library row (group, sub-group, label, copy_of), or None."""
    return con.execute("SELECT * FROM library_item WHERE asset_id=?", (asset_id,)).fetchone()


def detail_levels(con: sqlite3.Connection, asset_id: int) -> list[sqlite3.Row]:
    """The detail levels of the model ``asset_id`` belongs to (itself included), most
    detailed first, each with its ``detail`` name; [] when it has none."""
    row = con.execute("SELECT detail, detail_of FROM library_item WHERE asset_id=?",
                      (asset_id,)).fetchone()
    if row is None or not row["detail"]:
        return []
    top = row["detail_of"] or asset_id
    return con.execute(f"""
        SELECT {ASSET_COLUMNS}, l.detail FROM library_item l JOIN asset a ON a.id = l.asset_id
        WHERE l.asset_id = ? OR l.detail_of = ?
        ORDER BY (l.detail_of IS NOT NULL), a.vpath_lower""", (top, top)).fetchall()


def copies(con: sqlite3.Connection, asset_id: int) -> list[sqlite3.Row]:
    """The identical copies the Library folds into this item ("also in…")."""
    return con.execute(f"""
        SELECT {ASSET_COLUMNS} FROM library_item l JOIN asset a ON a.id = l.asset_id
        WHERE l.copy_of = ? ORDER BY a.vpath_lower""", (asset_id,)).fetchall()


def scene_info(con: sqlite3.Connection, asset_id: int) -> sqlite3.Row | None:
    """A model's or skeleton's counts, bone names and thumbnail (the ``scene`` table)."""
    return con.execute("SELECT * FROM scene WHERE asset_id=?", (asset_id,)).fetchone()


def picture(con: sqlite3.Connection, asset_id: int) -> bytes | None:
    """The Library's picture of an asset: a texture's thumbnail or a model's render."""
    row = con.execute("SELECT thumb_png FROM texture WHERE asset_id=? UNION ALL "
                      "SELECT thumb_png FROM scene WHERE asset_id=?",
                      (asset_id, asset_id)).fetchone()
    return row[0] if row else None


def rigs_of(con: sqlite3.Connection, model_id: int) -> list[sqlite3.Row]:
    """The skeletons a model matches, best first as `build.link_rigs` ordered them
    (``rank`` 0: the same bones and pose; 1: the same names, other proportions; 2: the
    skeleton has ``extra`` more bones)."""
    return con.execute(f"""
        SELECT r.rank, r.slot AS extra, {ASSET_COLUMNS}
        FROM relation r JOIN asset a ON a.id = r.dst_id
        WHERE r.src_id = ? AND r.kind = 'model-rig' ORDER BY r.rowid""",
                       (model_id,)).fetchall()


def rig_users(con: sqlite3.Connection, skeleton_id: int) -> list[sqlite3.Row]:
    """The models that match this skeleton (the reverse of `rigs_of`)."""
    return con.execute(f"""
        SELECT r.rank, {ASSET_COLUMNS}
        FROM relation r JOIN asset a ON a.id = r.src_id
        WHERE r.dst_id = ? AND r.kind = 'model-rig' ORDER BY r.rank, a.vpath_lower""",
                       (skeleton_id,)).fetchall()

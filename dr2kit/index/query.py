"""Read the asset index: search, browse, and follow relations.

Every function takes an open connection (`dr2kit.index.build.connect`) and returns
plain `sqlite3.Row` objects (use them like dicts: ``row["vpath"]``). DR2 Studio and
``dr2 index`` both go through here, so the SQL lives in one place.

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

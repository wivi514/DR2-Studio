"""Build the asset index: every file and entry of a game into one SQLite database.

Why an index: the games hold ~125k (CZ) and ~172k (CW) entries, many inside compressed,
nested archives. Searching them by walking the archives takes half a minute; the index
answers "every texture named *apron*" or "which models use this texture" in
milliseconds, and keeps a small thumbnail of every texture for DR2 Studio's grid.

What goes in (schema: ``schema.sql``, design: docs/ARCHITECTURE.md §The asset index):

* ``asset``: one row per file on disk and per archive entry at every depth, with its
  vpath, kind, sizes, compression and the SHA-1 of its uncompressed bytes (equal hashes
  = the same asset stored twice, which is common for textures);
* ``texture``: header facts and a PNG thumbnail (``THUMB_SIZE`` px) per texture;
* ``material_slot`` + ``relation``: what each model's ``MatTextureInfoArray`` names,
  linked to the textures of that name.
* ``audio``: channels, rate and length of every sound (phase 5, no decoding needed);
* ``sound_ref`` + ``relation``: the recordings each `.sfx` plays, and the sounds each
  audio scene script names, with the events that trigger them (the "event names").
* ``scene`` (phase 8): each model's and skeleton's counts, bone names and a rendered
  thumbnail (`scene_pass`, `dr2kit.convert.render`); ``relation`` kind ``model-rig``
  links a model to the skeletons its bone names match (`link_rigs`);
* ``library_item`` (phase 8): the Library group, sub-group and label of each asset, with
  identical copies folded into one (`link_library`, rules in dr2kit/catalog/groups.toml).

**Incremental.** Each file on disk is recorded with its size and modification time; a
rebuild re-reads only files that changed (and drops files that are gone). Relations are
recomputed for the whole game after each build, because a texture added in one archive
can satisfy a model in another.

Anything that fails to parse is counted and listed in the returned `IndexStats`, never
skipped silently (CLAUDE.md rule 6).
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from ..census import content_kind, texture_suffix
from ..container.big import BigArchive, is_big
from ..container.vpath import AssetTree, entry_components, join
from ..convert.audio import AudioLookup
from ..formats import audioscript, xma
from ..formats.bct import Bct, is_bct

# Bumped when the tables change *or* when assets are classified differently (an index
# only re-reads changed files, so a new rule would otherwise miss old rows).
# 2: audio tables (phase 5). 3: string banks get kind "strings" (phase 6).
# 4: scene facts, thumbnails, model->rig links and the Library (phase 8).
# 5: detail levels in the Library (library_item.detail, detail_of; phase 9).
SCHEMA_VERSION = "5"
THUMB_SIZE = 128
SCENE_HEADER = "sceneheader"
MAT_TEXTURE_INFO = "mattextureinfoarray"
MAT_RECORD = 100          # bytes per MatTextureInfoArray record (formats.md)
MAT_NAME = slice(4, 56)   # NUL-padded texture name inside a record
MIN_RIG_BONES = 8         # models with fewer bones are not linked to a rig (link_rigs)
RIG_LINKS = 3             # at most this many matching skeletons per model, closest first
# Bumped when model thumbnails are drawn differently: the next build redraws them all
# (without re-reading the archives). 2: baked zombie-clothing colours. 3: hair, opacity
# maps and glass lenses see-through. 4: clear glass that vanished drawn solid. 5: hair
# colour from gDiffuseColourControl. 6: rigid parts placed by their node. 7: the default
# look of models with variants (phase 9: one head, one shirt…, no wound caps).
THUMB_VERSION = "7"
POSE_TOLERANCE = 0.001    # metres: a model's bones this close to a rig's are "the same pose"

_EXT_KIND = {"xma": "audio", "sfx": "sfx", "anm": "anim", "po": "shader", "vo": "shader", "pdo": "shader",
             "vdo": "shader", "sdo": "shader", "scv": "shader", "bik": "video",
             "bcs": "strings"}


def default_db_path() -> Path:
    """Where the index lives: the per-user cache folder (`dr2kit.userdirs`)."""
    from ..userdirs import cache_dir
    return cache_dir() / "index.sqlite"


@dataclass
class IndexStats:
    """What one build did. ``problems`` lists (vpath, reason) for anything unparsed."""
    game: str
    files_seen: int = 0
    files_indexed: int = 0
    files_unchanged: int = 0
    files_removed: int = 0
    assets: int = 0
    textures: int = 0
    models: int = 0
    material_slots: int = 0
    relations: int = 0
    sounds: int = 0
    sound_links: int = 0
    unresolved_sounds: int = 0
    unresolved_slots: int = 0
    scenes: int = 0
    thumbnails: int = 0
    rig_links: int = 0
    library: int = 0
    problems: list = field(default_factory=list)
    seconds: float = 0.0


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) the index database, with the current schema."""
    path = Path(db_path) if db_path else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=60)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    # WAL lets DR2 Studio keep reading while a build writes in another thread.
    con.execute("PRAGMA journal_mode = WAL")
    ver = None
    try:
        row = con.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
        ver = row[0] if row else None
    except sqlite3.OperationalError:
        pass
    if ver not in (None, SCHEMA_VERSION):
        # An index from an older toolkit: drop it, it is only a cache. Foreign keys off
        # while dropping: with them on, dropping a table whose parent is already gone
        # fails ("no such table: main.source_file"), seen on the first schema bump.
        con.execute("PRAGMA foreign_keys = OFF")
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            con.execute(f"DROP TABLE IF EXISTS {name}")
        con.commit()
        con.execute("PRAGMA foreign_keys = ON")
    con.executescript(resources.files(__package__).joinpath("schema.sql").read_text("utf-8"))
    con.execute("INSERT OR REPLACE INTO meta VALUES ('schema', ?)", (SCHEMA_VERSION,))
    con.commit()
    return con


def thumbnail(tex: Bct) -> bytes:
    """A small PNG of a texture: the first mip level that fits in ``THUMB_SIZE``."""
    from ..convert import png
    from ..convert.texture import decode_level, downsample, png_mode
    levels = [lv for lv in tex.levels() if lv.face == 0]
    lv = next((x for x in levels if max(x.width, x.height) <= THUMB_SIZE), levels[-1])
    rgba = decode_level(tex, lv)
    w, h = lv.width, lv.height
    while max(w, h) > THUMB_SIZE:            # no small enough mip stored
        nw, nh = max(1, w // 2), max(1, h // 2)
        rgba = downsample(rgba, w, h, nw, nh)
        w, h = nw, nh
    img = png.Image(w, h, rgba)
    return png.encode(img, "RGBA" if png_mode(tex, img) == "RGBA" else "RGB", level=6)


def classify(name: str, ext: str, data: bytes, arc: BigArchive | None) -> str:
    """The ``kind`` of an asset from its name, extension, bytes and (for archives) entries."""
    if not data:
        return "empty"
    if is_bct(data):
        return "texture"
    if arc is not None:
        names = {e.name.lower() for e in arc.entries}
        if SCENE_HEADER in names:
            if any(n.endswith(" vertices 0") or n.startswith("combined vertices") for n in names):
                return "model"
            return "skeleton"
        if ext == "tex":
            return "texture-pack"
        return "archive"
    if ext in _EXT_KIND:
        return _EXT_KIND[ext]
    return "text" if content_kind(data) == "text" else "binary"


def _material_slots(data: bytes) -> list[tuple[int, str, bool]] | None:
    if len(data) % MAT_RECORD:
        return None
    out = []
    for i in range(len(data) // MAT_RECORD):
        raw = data[i * MAT_RECORD:][MAT_NAME]
        name = raw.split(b"\0", 1)[0].decode("latin-1")
        engine = len(name) > 1 and name[0] == "g" and name[1].isupper()
        out.append((i, name, engine))
    return out


class _Builder:
    def __init__(self, con: sqlite3.Connection, game: str, stats: IndexStats, thumbs: bool,
                 tree: AssetTree | None = None):
        self.con, self.game, self.stats, self.thumbs = con, game, stats, thumbs
        self.lookup = AudioLookup(tree) if tree is not None else None

    def sound(self, asset_id: int, vpath: str, data: bytes) -> None:
        if self.lookup is None:
            return
        try:
            info = self.lookup.info(vpath, data)
        except Exception as ex:  # noqa: BLE001 - reported
            self.stats.problems.append((vpath, f"audio: {ex}"))
            return
        if info.expected_samples:
            samples, exact = info.expected_samples, 1
        else:
            pk = data[info.packets_offset:info.packets_offset + info.packets_size]
            samples = xma.frame_count(pk, info.streams) * xma.FRAME_SAMPLES - xma.DECODER_DELAY
            exact = 0
        loop = info.loop or (None, None)
        self.con.execute("INSERT INTO audio VALUES (?,?,?,?,?,?,?,?)",
                         (asset_id, info.channels, info.rate, info.shape, max(0, samples),
                          exact, loop[0], loop[1]))
        self.stats.sounds += 1

    def sound_refs(self, asset_id: int, vpath: str, ext: str, data: bytes) -> None:
        """Record what a .sfx or an audio scene script names (resolved later)."""
        if ext == "sfx":
            try:
                tracks = audioscript.sfx_tracks(data.decode("latin-1"), vpath)
            except Exception as ex:  # noqa: BLE001 - reported
                self.stats.problems.append((vpath, f"sfx: {ex}"))
                return
            rows = [(asset_id, "sfx-track", i, "", t, f"track {i + 1}")
                    for i, t in enumerate(tracks)]
        elif ext == "txt" and b"cAudioScene" in data[:4096]:
            try:
                refs = audioscript.script_refs(data.decode("latin-1"), vpath)
            except Exception as ex:  # noqa: BLE001 - reported
                self.stats.problems.append((vpath, f"audio script: {ex}"))
                return
            rows = [(asset_id, "script-asset", i, r.bank, r.entry or "", r.context)
                    for i, r in enumerate(refs) if r.key == "Asset" and r.entry]
        else:
            return
        self.con.executemany("INSERT INTO sound_ref VALUES (?,?,?,?,?,?)", rows)

    def insert(self, source_id, parent_id, depth, position, vpath, name, name_hash, ext,
               kind, stored, size, compressed, flags, data) -> int:
        cur = self.con.execute(
            "INSERT INTO asset (game, vpath, vpath_lower, source_id, parent_id, depth, "
            "position, name, name_hash, ext, kind, stored_size, size, compressed, flags, sha1) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.game, vpath, vpath.lower(), source_id, parent_id, depth, position, name,
             name_hash, ext, kind, stored, size, int(compressed), flags,
             hashlib.sha1(data).hexdigest()))
        self.stats.assets += 1
        return cur.lastrowid

    def texture(self, asset_id: int, vpath: str, name: str, data: bytes) -> None:
        try:
            tex = Bct.parse(data, vpath)
            thumb = thumbnail(tex) if self.thumbs else None
        except Exception as ex:  # noqa: BLE001 - reported
            self.stats.problems.append((vpath, f"texture: {ex}"))
            return
        h = tex.header
        tex_name = name[:-4] if name.lower().endswith(".bct") else name
        suffix = texture_suffix(name)
        self.con.execute("INSERT INTO texture VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (asset_id, h.width, h.height, tex.format.name, h.levels,
                          int(h.is_cube), h.flags, "" if suffix == "(none)" else suffix,
                          tex_name.lower(), thumb))
        self.stats.textures += 1

    def archive(self, arc: BigArchive, vpath: str, source_id: int, parent_id: int,
                depth: int) -> None:
        for pos, (comp, e) in enumerate(zip(entry_components(arc), arc.entries)):
            evp = join(vpath, comp)
            try:
                data = e.data()
            except Exception as ex:  # noqa: BLE001 - reported
                self.stats.problems.append((evp, f"decode: {ex}"))
                continue
            sub = None
            if is_big(data):
                try:
                    sub = BigArchive.parse(data, evp)
                except Exception as ex:  # noqa: BLE001 - reported
                    self.stats.problems.append((evp, f"nested archive: {ex}"))
            kind = classify(e.name, e.ext, data, sub)
            aid = self.insert(source_id, parent_id, depth, pos, evp, e.name, e.hash, e.ext,
                              kind, e.size, e.size2, e.compressed, e.flags, data)
            if kind == "texture":
                self.texture(aid, evp, e.name, data)
            elif kind == "audio":
                self.sound(aid, evp, data)
            elif kind in ("sfx", "text"):
                self.sound_refs(aid, evp, e.ext, data)
            elif kind == "model":
                self.stats.models += 1
            if sub is not None:
                if kind == "model":
                    self.model_slots(aid, sub, evp)
                self.archive(sub, evp, source_id, aid, depth + 1)

    def model_slots(self, model_id: int, arc: BigArchive, vpath: str) -> None:
        for e in arc.entries:
            if e.name.lower() != MAT_TEXTURE_INFO:
                continue
            slots = _material_slots(e.data())
            if slots is None:
                self.stats.problems.append((join(vpath, e.name),
                                            f"{e.size2} bytes, not a whole number of "
                                            f"{MAT_RECORD}-byte records"))
                return
            self.con.executemany("INSERT INTO material_slot VALUES (?,?,?,?)",
                                 [(model_id, i, n, int(g)) for i, n, g in slots])
            self.stats.material_slots += len(slots)


def build_index(game: str, tree: AssetTree, db_path: str | Path | None = None, *,
                thumbs: bool = True, full: bool = False, progress=None) -> IndexStats:
    """Index one game. Re-reads only changed files unless ``full``.

    ``progress(text)`` is called for each file being (re)indexed (its vpath), and now and
    then while models are drawn for their thumbnails.
    """
    t0 = time.time()
    stats = IndexStats(game)
    con = connect(db_path)
    b = _Builder(con, game, stats, thumbs, tree)
    if full:
        con.execute("DELETE FROM source_file WHERE game=?", (game,))
    known = {r["vpath"]: r for r in con.execute(
        "SELECT id, vpath, size, mtime_ns FROM source_file WHERE game=?", (game,))}
    seen = set()
    for vp, path in tree.files():
        stats.files_seen += 1
        seen.add(vp)
        st = path.stat()
        old = known.get(vp)
        if old and old["size"] == st.st_size and old["mtime_ns"] == st.st_mtime_ns:
            stats.files_unchanged += 1
            continue
        if old:
            con.execute("DELETE FROM source_file WHERE id=?", (old["id"],))
        if progress:
            progress(vp)
        raw = path.read_bytes()
        sid = con.execute("INSERT INTO source_file (game, vpath, size, mtime_ns) VALUES (?,?,?,?)",
                          (game, vp, st.st_size, st.st_mtime_ns)).lastrowid
        name = path.name
        ext = path.suffix.lower().lstrip(".")
        arc = None
        if is_big(raw):
            try:
                arc = BigArchive.parse(raw, vp)
            except Exception as ex:  # noqa: BLE001 - reported
                stats.problems.append((vp, f"parse: {ex}"))
        kind = classify(name, ext, raw, arc)
        aid = b.insert(sid, None, 0, 0, vp, name, None, ext, kind, len(raw), len(raw),
                       False, None, raw)
        if kind == "texture":
            b.texture(aid, vp, name, raw)
        elif kind == "text":
            b.sound_refs(aid, vp, ext, raw)
        if arc is not None:
            if kind == "model":
                stats.models += 1
                b.model_slots(aid, arc, vp)
            b.archive(arc, vp, sid, aid, 1)
        stats.files_indexed += 1
        con.commit()
    for vp, row in known.items():
        if vp not in seen:
            con.execute("DELETE FROM source_file WHERE id=?", (row["id"],))
            stats.files_removed += 1
    link_relations(con, game, stats)
    scene_pass(con, game, tree, stats, thumbs, progress)
    link_rigs(con, game, stats)
    link_library(con, game, stats)
    con.execute("ANALYZE")          # table statistics, so the query planner chooses well
    con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)",
                (f"built:{game}", time.strftime("%Y-%m-%d %H:%M:%S")))
    con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (f"root:{game}", str(tree.root)))
    con.commit()
    con.close()
    stats.seconds = time.time() - t0
    return stats


def link_relations(con: sqlite3.Connection, game: str, stats: IndexStats) -> None:
    """Recompute model→texture relations of ``game`` from the material slots."""
    con.execute("DELETE FROM relation WHERE src_id IN (SELECT id FROM asset WHERE game=?)",
                (game,))
    # CROSS JOIN fixes the join order (SQLite never reorders it): start from the slots,
    # look each name up through the texture_name index. Left to the planner, without
    # statistics, this query nested two scans of every asset and took ten minutes.
    con.execute("""
        INSERT INTO relation (src_id, dst_id, kind, slot, dst_name, rank)
        SELECT m.id, t.asset_id, 'material-texture', s.slot, s.name,
               CASE WHEN ta.parent_id = m.parent_id
                      OR (SELECT p.parent_id FROM asset p WHERE p.id = ta.parent_id) = m.parent_id
                      OR ta.parent_id = m.id
                    THEN 0 ELSE 1 END
        FROM material_slot s
        CROSS JOIN asset m ON m.id = s.model_id
        CROSS JOIN texture t ON t.tex_name = lower(s.name)
        CROSS JOIN asset ta ON ta.id = t.asset_id
        WHERE s.engine = 0 AND s.name <> '' AND m.game = ? AND ta.game = ?
    """, (game, game))
    con.execute("""
        INSERT INTO relation (src_id, dst_id, kind, slot, dst_name, rank)
        SELECT s.model_id, NULL, 'material-texture', s.slot, s.name, 9
        FROM material_slot s CROSS JOIN asset m ON m.id = s.model_id
        WHERE s.engine = 0 AND s.name <> '' AND m.game = ?
          AND NOT EXISTS (SELECT 1 FROM texture t CROSS JOIN asset ta ON ta.id = t.asset_id
                          WHERE t.tex_name = lower(s.name) AND ta.game = ?)
    """, (game, game))
    link_sounds(con, game, stats)
    stats.relations = con.execute(
        "SELECT count(*) FROM relation r JOIN asset a ON a.id = r.src_id "
        "WHERE a.game=? AND r.dst_id IS NOT NULL", (game,)).fetchone()[0]
    stats.unresolved_slots = con.execute(
        "SELECT count(*) FROM relation r JOIN asset a ON a.id = r.src_id "
        "WHERE a.game=? AND r.dst_id IS NULL AND r.kind='material-texture'",
        (game,)).fetchone()[0]


def link_sounds(con: sqlite3.Connection, game: str, stats: IndexStats) -> None:
    """Resolve ``sound_ref`` rows into ``relation`` rows (called by `link_relations`).

    A ``.sfx`` track is an entry of the ``.sfx``'s own bank. A script's ``Asset =
    "music.big/HB_Indemnify"`` is the entry ``HB_Indemnify`` (or ``.xma`` / ``.sfx``) of
    any archive called ``music.big``: banks sit in different places (``data/audio/``,
    inside ``streamedassets.big``), and a bank can be shipped twice.
    """
    con.execute("""
        INSERT INTO relation (src_id, dst_id, kind, slot, dst_name, rank)
        SELECT r.src_id, d.id, r.kind, r.slot, r.name, 0
        FROM sound_ref r CROSS JOIN asset s ON s.id = r.src_id
        LEFT JOIN asset d ON d.parent_id = s.parent_id AND lower(d.name) = lower(r.name)
        WHERE r.kind = 'sfx-track' AND s.game = ?
    """, (game,))
    con.execute("""
        INSERT INTO relation (src_id, dst_id, kind, slot, dst_name, rank)
        SELECT r.src_id, d.id, r.kind, r.slot, r.bank || '/' || r.name, 0
        FROM sound_ref r CROSS JOIN asset s ON s.id = r.src_id
        LEFT JOIN asset b ON b.game = s.game AND lower(b.name) = lower(r.bank)
        LEFT JOIN asset d ON d.parent_id = b.id AND lower(d.name) IN
             (lower(r.name), lower(r.name) || '.xma', lower(r.name) || '.sfx')
        WHERE r.kind = 'script-asset' AND s.game = ?
    """, (game,))
    # A reference that matched in one copy of a bank but not another isn't unresolved.
    con.execute("""
        DELETE FROM relation WHERE dst_id IS NULL AND kind IN ('sfx-track', 'script-asset')
          AND EXISTS (SELECT 1 FROM relation o WHERE o.src_id = relation.src_id
                      AND o.slot = relation.slot AND o.kind = relation.kind
                      AND o.dst_id IS NOT NULL)""")
    q = ("SELECT count(*) FROM relation r JOIN asset a ON a.id = r.src_id WHERE a.game=? "
         "AND r.kind IN ('sfx-track', 'script-asset') AND r.dst_id IS {} NULL")
    stats.sound_links = con.execute(q.format("NOT"), (game,)).fetchone()[0]
    stats.unresolved_sounds = con.execute(q.format(""), (game,)).fetchone()[0]


def _scene_facts(sc) -> tuple:
    """(bones, meshes, draws, vertices, max part vertices, max draw bones, materials,
    bone names, bone positions) of a parsed scene, without decoding any vertex."""
    import struct
    draws = [d for m in sc.meshes for d in m.draws]
    part = max((sum(d.vertex_count for d in m.draws) for m in sc.meshes), default=0)
    pal = max((d.palette_count for d in draws if d.skinned), default=0)
    names = "\n".join(n.name.lower() for n in sc.skeleton.nodes)
    try:
        pos = [c for p in sc.skeleton.world_positions() for c in p] if sc.skeleton.nodes else []
        blob = struct.pack(f"<{len(pos)}f", *pos)
    except Exception:  # noqa: BLE001 - a broken hierarchy: no pose, names still link
        blob = None
    return (len(sc.skeleton), len(sc.meshes), len(draws), sum(d.vertex_count for d in draws),
            part, pal, len(sc.materials), names, blob)


def scene_pass(con: sqlite3.Connection, game: str, tree: AssetTree, stats: IndexStats,
               thumbs: bool = True, progress=None) -> None:
    """Read every model and skeleton not yet in the ``scene`` table: its counts and bone
    names, and (``thumbs``, numpy present) a thumbnail of each model.

    Runs after the relations are linked, so a model's colour textures are found the way
    `link_relations` found them (the texture next to the model first), and drawn from the
    index's own texture thumbnails: no texture is decoded twice. Models are visited in
    vpath order, so each archive is opened once (the tree's cache)."""
    from ..convert import material as cmat
    from ..convert import png, render
    from ..convert import variants as cvar
    from ..formats.scene import Scene
    draw = thumbs and render.available()
    key = f"thumbs:{game}"
    old = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    if draw and (old[0] if old else None) != THUMB_VERSION:
        con.execute("UPDATE scene SET rendered = 0 WHERE asset_id IN "
                    "(SELECT id FROM asset WHERE game=? AND kind='model')", (game,))
    if draw:
        con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, THUMB_VERSION))
    rows = con.execute("""
        SELECT a.id, a.vpath, a.kind, s.asset_id AS known FROM asset a
        LEFT JOIN scene s ON s.asset_id = a.id
        WHERE a.game = ? AND a.kind IN ('model', 'skeleton')
          AND (s.asset_id IS NULL OR (? AND a.kind = 'model' AND s.rendered = 0))
        ORDER BY a.vpath_lower""", (game, int(draw))).fetchall()
    if not rows:
        return
    reader = AssetTree(tree.root, cache_size=32)
    decoded: dict[int, object] = {}
    shaders = cmat.ShaderLibrary(reader) if draw else None
    classifier = cvar.Classifier.for_game(game) if draw else None
    for i, r in enumerate(rows):
        if progress and i % 100 == 0:
            progress(f"models and skeletons: {i}/{len(rows)}")
        problem, thumb = "", None
        try:
            sc = Scene.parse(reader.resolve(r["vpath"]).data(), r["vpath"])
            facts = _scene_facts(sc)
        except Exception as ex:  # noqa: BLE001 - reported
            stats.problems.append((r["vpath"], f"scene: {ex}"))
            sc, facts = None, (0, 0, 0, 0, 0, 0, 0, "", None)
            problem = str(ex)
        if sc is not None and draw and r["kind"] == "model":
            texs = {}
            for t in con.execute("""
                    SELECT lower(r.dst_name) AS name, t.asset_id, t.thumb_png
                    FROM relation r JOIN texture t ON t.asset_id = r.dst_id
                    WHERE r.src_id = ? AND r.kind = 'material-texture' AND t.thumb_png IS NOT NULL
                    ORDER BY r.rank DESC""", (r["id"],)):
                texs[t["name"]] = (t["asset_id"], t["thumb_png"])   # best rank wins (last)

            def image(name: str):
                hit = texs.get(name.lower())
                if hit is None:
                    return None
                if hit[0] not in decoded:
                    if len(decoded) > 512:
                        decoded.clear()
                    decoded[hit[0]] = png.decode(hit[1])
                return decoded[hit[0]]

            def texture_for(name: str):
                im = image(name)
                return None if im is None else render.rgba_to_float(im.rgba, im.width, im.height)

            def material_colour(m, sc=sc):
                # zombie clothing etc.: colour from shader constants, baked like the .glb
                rec = cmat.recipe(sc, m, shaders)
                im = cmat.bake(rec, image) if rec is not None else None
                return None if im is None else render.rgba_to_float(im.rgba, im.width, im.height)
            try:
                bad: list[str] = []
                mv = cvar.model_variants(sc, game, classifier)     # the default look
                look = None if not mv.has_choices else {
                    k for k, on in enumerate(mv.shown(mv.default())) if on}
                parts = render.scene_parts(sc, texture_for, bad, material_colour, look)
                img = render.render(parts)
                if img is None and any(p.alpha_test for p in parts):
                    # all see-through (clear glass): draw it solid, so it has a picture
                    for p in parts:
                        p.alpha_test = False
                    img = render.render(parts)
                thumb = render.to_png(img) if img is not None else None
                if bad:
                    problem = f"{len(bad)} draw(s) not drawn: {bad[0]}"
                if thumb is not None:
                    stats.thumbnails += 1
            except Exception as ex:  # noqa: BLE001 - reported
                stats.problems.append((r["vpath"], f"thumbnail: {ex}"))
                problem = f"thumbnail: {ex}"
        con.execute("INSERT OR REPLACE INTO scene VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (r["id"], *facts, int(draw and r["kind"] == "model"), thumb, problem))
        stats.scenes += 1
        if i % 200 == 199:
            con.commit()
    con.commit()


def _bones(names: str, pos: bytes | None) -> dict[str, tuple[float, float, float]]:
    """Bone name -> rest-pose position (0, 0, 0 for all when the pose is unknown)."""
    import struct
    keys = names.split("\n")
    if pos is None or len(pos) != 12 * len(keys):
        return {k: (0.0, 0.0, 0.0) for k in keys}
    vals = struct.unpack(f"<{3 * len(keys)}f", pos)
    return {k: vals[3 * i:3 * i + 3] for i, k in enumerate(keys)}


def link_rigs(con: sqlite3.Connection, game: str, stats: IndexStats) -> None:
    """Link each model to the skeleton files it matches (relation ``model-rig``).

    A model carries its own copy of its rig (docs/formats.md §Scene container); the link
    names the skeleton file that rig is, i.e. the one its animations are made for. The
    rig families (player, female, large, child, their cutscene versions) all have the
    same 98 bone names, so names only narrow it down: the rest pose decides. Rank 0:
    the same bones in the same pose (every bone within `POSE_TOLERANCE`); 1: the same
    names, other proportions (closest pose first); 2: the skeleton also has other bones.
    Of identical skeleton files (``skeleton/`` and the ``preload4.big`` copy) only the
    first by path is linked; at most `RIG_LINKS` per model. Models with fewer than
    `MIN_RIG_BONES` bones (props with a door or a wheel) are not linked: a handful of
    names matches too many skeletons to mean anything."""
    import math
    con.execute("DELETE FROM relation WHERE kind='model-rig' AND src_id IN "
                "(SELECT id FROM asset WHERE game=?)", (game,))
    skels, seen = [], set()
    for r in con.execute("""
            SELECT a.id, a.name, a.sha1, s.bone_names, s.bone_pos FROM asset a
            JOIN scene s ON s.asset_id = a.id
            WHERE a.game = ? AND a.kind = 'skeleton' AND s.bones > 0
            ORDER BY (a.vpath_lower LIKE '%preload4.big%'), a.depth, a.vpath_lower""", (game,)):
        if r["sha1"] in seen:
            continue
        seen.add(r["sha1"])
        skels.append((r["id"], r["name"], _bones(r["bone_names"], r["bone_pos"])))
    rows = []
    for m in con.execute("""
            SELECT a.id, s.bone_names, s.bone_pos FROM asset a JOIN scene s ON s.asset_id = a.id
            WHERE a.game = ? AND a.kind = 'model' AND s.bones >= ?""", (game, MIN_RIG_BONES)):
        mine = _bones(m["bone_names"], m["bone_pos"])
        hits = []
        for sid, sname, theirs in skels:
            if not mine.keys() <= theirs.keys():
                continue
            far = [math.dist(p, theirs[k]) for k, p in mine.items()]
            worst, mean = max(far), sum(far) / len(far)
            extra = len(theirs) - len(mine)
            rank = 2 if extra else (0 if worst <= POSE_TOLERANCE else 1)
            # mean rounded to 0.1 mm: identical rigs differ by float noise, and then the
            # whole-body file (…fullbody) should win over its cutscene twin (cine…)
            hits.append((rank, round(mean, 4), extra, "fullbody" not in sname.lower(),
                         sname.lower(), sid, sname))
        for rank, _mean, extra, _f, _n, sid, sname in sorted(hits)[:RIG_LINKS]:
            rows.append((m["id"], sid, "model-rig", extra, sname, rank))
    con.executemany("INSERT INTO relation (src_id, dst_id, kind, slot, dst_name, rank) "
                    "VALUES (?,?,?,?,?,?)", rows)
    stats.rig_links = len(rows)


def link_library(con: sqlite3.Connection, game: str, stats: IndexStats) -> None:
    """Put every asset the Library shows into its group (dr2kit/catalog/groups.toml),
    folding identical copies into one: the copy outside ``preload4.big``, nearest the
    top, first by path, is shown; the others get ``copy_of``. Detail levels of one model
    (groups.toml ``[[detail]]``) are folded the same way into the highest level
    (``detail_of``), and each row says its level (``detail``)."""
    from ..catalog.groups import catalog
    cat = catalog()
    kinds = sorted({k for g in cat.groups for k in g.kinds})
    con.execute("DELETE FROM library_item WHERE game=?", (game,))
    placed = []
    for r in con.execute(f"""
            SELECT id, vpath, name, kind, sha1 FROM asset
            WHERE game = ? AND kind IN ({','.join('?' * len(kinds))})
            ORDER BY (vpath_lower LIKE '%preload4.big%'), depth, vpath_lower""", (game, *kinds)):
        hit = cat.place(game, r["kind"], r["vpath"], r["name"])
        if hit is not None:
            placed.append((r, hit))
    keeper: dict[tuple[str, str], int] = {}
    rows = []
    for r, (grp, sub, label) in placed:
        key = (r["kind"], r["sha1"])
        first = keeper.setdefault(key, r["id"])
        rows.append([r["id"], game, grp, sub, label, None if first == r["id"] else first,
                     "", None])
    # detail levels ([[detail]] rules): one item per model, the highest level shown
    names = {r["id"]: r["name"] for r, _ in placed}
    levels: dict[tuple, list] = {}
    for row in rows:
        if row[5] is not None:
            continue
        hit = cat.detail(row[2], names[row[0]])
        if hit is not None:
            base, rank, level = hit
            levels.setdefault((row[2], row[3], base), []).append((rank, level, row))
    for members in levels.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda m: m[0])
        top = members[0][2]
        for rank, level, row in members:
            row[6] = level
            if row is not top:
                row[7] = top[0]
                row[4] = f"{top[4] or row[4]} ({level} detail)".strip()
    con.executemany("INSERT INTO library_item VALUES (?,?,?,?,?,?,?,?)", rows)
    stats.library = sum(1 for x in rows if x[5] is None and x[7] is None)


def format_stats(s: IndexStats) -> str:
    lines = [
        f"== index: {s.game}",
        f"files: {s.files_seen} seen, {s.files_indexed} (re)indexed, {s.files_unchanged} "
        f"unchanged, {s.files_removed} removed",
        f"assets added: {s.assets}; textures: {s.textures}; models: {s.models} "
        f"({s.material_slots} material slots)",
        f"model->texture links: {s.relations}; slots naming a texture found nowhere: "
        f"{s.unresolved_slots}",
        f"sounds: {s.sounds}; .sfx/script->sound links: {s.sound_links}; names found "
        f"nowhere: {s.unresolved_sounds}",
        f"models/skeletons read: {s.scenes} ({s.thumbnails} thumbnails drawn); "
        f"model->rig links: {s.rig_links}; Library items: {s.library}",
        f"PROBLEMS (unparsed): {len(s.problems)}",
    ]
    lines += [f"    {vp}: {why}" for vp, why in s.problems[:40]]
    lines.append(f"took {s.seconds:.1f} s")
    return "\n".join(lines)

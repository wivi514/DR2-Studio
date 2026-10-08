-- The asset index: one row per file and per archive entry, at every nesting depth, for
-- both games. Built by `dr2 index build` (dr2kit/index/build.py); read by `dr2 index
-- search` and DR2 Studio (dr2kit/index/query.py). Design: docs/ARCHITECTURE.md §The asset index.
-- Bump SCHEMA_VERSION in build.py when this changes: an old index is then rebuilt.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

-- Files on disk, with what they looked like when indexed (for incremental rebuilds).
CREATE TABLE IF NOT EXISTS source_file (
    id INTEGER PRIMARY KEY,
    game TEXT NOT NULL,
    vpath TEXT NOT NULL,             -- data/models/npcs.big
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    UNIQUE (game, vpath)
);

CREATE TABLE IF NOT EXISTS asset (
    id INTEGER PRIMARY KEY,
    game TEXT NOT NULL,              -- 'cz' or 'cw'
    vpath TEXT NOT NULL,             -- real letter case; compare with lower()
    vpath_lower TEXT NOT NULL,
    source_id INTEGER NOT NULL REFERENCES source_file(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES asset(id) ON DELETE CASCADE,   -- NULL for files on disk
    depth INTEGER NOT NULL,          -- 0 = file on disk, 1 = entry of it, ...
    position INTEGER NOT NULL,       -- index in the parent archive (0 for files)
    name TEXT NOT NULL,              -- last vpath component, as stored
    name_hash INTEGER,               -- the .big index hash (NULL for files on disk)
    ext TEXT NOT NULL,               -- 'bct', 'big', ... or ''
    kind TEXT NOT NULL,              -- texture, texture-pack, model, skeleton, scene, archive,
                                     -- audio, anim, shader, text, binary, empty
    stored_size INTEGER NOT NULL,
    size INTEGER NOT NULL,           -- uncompressed
    compressed INTEGER NOT NULL,     -- 1 if LZX-compressed in its archive
    flags INTEGER,                   -- the .big index flags word
    sha1 TEXT NOT NULL               -- of the uncompressed bytes
);
CREATE UNIQUE INDEX IF NOT EXISTS asset_vpath ON asset (game, vpath_lower);
CREATE INDEX IF NOT EXISTS asset_parent ON asset (parent_id, position);
CREATE INDEX IF NOT EXISTS asset_source ON asset (source_id);
CREATE INDEX IF NOT EXISTS asset_name ON asset (name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS asset_kind ON asset (game, kind);
CREATE INDEX IF NOT EXISTS asset_sha1 ON asset (sha1);

CREATE TABLE IF NOT EXISTS texture (
    asset_id INTEGER PRIMARY KEY REFERENCES asset(id) ON DELETE CASCADE,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    format TEXT NOT NULL,            -- DXT1, DXT5, DXN, A8R8G8B8, L8
    mips INTEGER NOT NULL,
    is_cube INTEGER NOT NULL,
    flags INTEGER NOT NULL,          -- header byte 3
    suffix TEXT NOT NULL,            -- role from the name: _cm, _nm, _sm, ... or ''
    tex_name TEXT NOT NULL,          -- lower-case name without '.bct' (what models refer to)
    thumb_png BLOB                   -- at most THUMB_SIZE px on the long side
);
CREATE INDEX IF NOT EXISTS texture_format ON texture (format);
CREATE INDEX IF NOT EXISTS texture_name ON texture (tex_name);

-- What a model's MatTextureInfoArray names, slot by slot (100-byte records, name at +4;
-- docs/formats.md "Scene container"). Engine samplers (gExposureTexture, ...) included.
CREATE TABLE IF NOT EXISTS material_slot (
    model_id INTEGER NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    slot INTEGER NOT NULL,
    name TEXT NOT NULL,
    engine INTEGER NOT NULL          -- 1 for engine samplers (g + capital letter)
);
CREATE INDEX IF NOT EXISTS material_slot_model ON material_slot (model_id);
CREATE INDEX IF NOT EXISTS material_slot_name ON material_slot (lower(name));

-- Links between assets, recomputed from material_slot after every build.
-- kind 'material-texture': a model's slot names a texture; every texture with that name
-- in the same game is linked. rank 0 = the texture sits next to the model (same parent
-- archive, or in a pack in it), 1 = elsewhere.
CREATE TABLE IF NOT EXISTS relation (
    src_id INTEGER NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    dst_id INTEGER REFERENCES asset(id) ON DELETE CASCADE,  -- NULL: name found nowhere
    kind TEXT NOT NULL,
    slot INTEGER,
    dst_name TEXT NOT NULL,
    rank INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS relation_src ON relation (src_id);
CREATE INDEX IF NOT EXISTS relation_dst ON relation (dst_id);

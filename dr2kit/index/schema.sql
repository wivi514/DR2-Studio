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

-- One row per sound (.xma): what dr2kit.formats.xma reads from its RIFF header or its
-- cache.big stream-table record. No decoding happens while indexing (PyAV is optional):
-- `samples` is the stored length, or the packet headers' estimate (exact = 0).
CREATE TABLE IF NOT EXISTS audio (
    asset_id INTEGER PRIMARY KEY REFERENCES asset(id) ON DELETE CASCADE,
    channels INTEGER NOT NULL,
    rate INTEGER NOT NULL,
    shape TEXT NOT NULL,             -- 'riff' (fx banks) or 'raw' (streamed banks)
    samples INTEGER NOT NULL,        -- per channel
    exact INTEGER NOT NULL,          -- 1 if `samples` is a stored length
    loop_start INTEGER,              -- decoded samples; NULL for a one-shot
    loop_end INTEGER
);

-- What .sfx files and audio scene scripts name (dr2kit.formats.audioscript), resolved
-- into `relation` rows by link_relations: 'sfx-track' (a .sfx -> the .xma or sub-.sfx
-- of its bank it plays) and 'script-asset' (a scene script -> the sound an `Asset =`
-- line names). `context` is where: the script's block path and its trigger events.
CREATE TABLE IF NOT EXISTS sound_ref (
    src_id INTEGER NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,              -- 'sfx-track' or 'script-asset'
    slot INTEGER NOT NULL,           -- track number / reference number in the file
    bank TEXT NOT NULL,              -- 'music.big'; '' = the .sfx's own bank
    name TEXT NOT NULL,              -- 'HB_Indemnify', 'cursorError43a_01a.xma'
    context TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sound_ref_src ON sound_ref (src_id);

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

-- Links between assets, recomputed from material_slot and sound_ref after every build.
-- kinds: 'material-texture' (below), 'sfx-track' and 'script-asset' (see sound_ref),
-- 'model-rig' (a model -> the skeletons whose bone names include all of the model's:
-- rank 0 the same bones in the same rest pose, 1 the same names but other proportions,
-- 2 the skeleton has more bones; slot = how many more; build.link_rigs).
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

-- One row per model and skeleton (phase 8): what the Library shows next to it, read with
-- dr2kit.formats.scene after the entries are indexed (build.scene_pass). `bone_names` is
-- the skeleton's node names, lower case, one per line, in node order, and `bone_pos`
-- their rest-pose positions: together they link a model to the rig it matches
-- (relation kind 'model-rig'; the rig families share their bone names, not their pose). `thumb_png` is a 128-px picture
-- drawn by dr2kit.convert.render (models only; NULL without numpy or with --no-thumbs).
CREATE TABLE IF NOT EXISTS scene (
    asset_id INTEGER PRIMARY KEY REFERENCES asset(id) ON DELETE CASCADE,
    bones INTEGER NOT NULL,
    meshes INTEGER NOT NULL,
    draws INTEGER NOT NULL,
    vertices INTEGER NOT NULL,       -- sum of the draws' vertex ranges
    max_part_vertices INTEGER NOT NULL,   -- largest draw vertex range (limit: 65,536)
    max_draw_bones INTEGER NOT NULL,      -- largest bone palette of one draw (limit: 61)
    materials INTEGER NOT NULL,
    bone_names TEXT NOT NULL,
    bone_pos BLOB,                   -- rest-pose world positions, 3 float32 per bone
    rendered INTEGER NOT NULL DEFAULT 0,  -- 1 once a thumbnail was attempted
    thumb_png BLOB,
    problem TEXT                     -- why it couldn't be read or drawn ('' if fine)
);

-- The Library (phase 8): the group, sub-group and friendly label of each asset it shows,
-- from dr2kit/catalog/groups.toml (build.link_library, after every build). An asset
-- whose bytes equal another's is listed once: `copy_of` names the one shown. Detail
-- levels of one model (phase 9: zombie_cop_2/_3/_4, the [[detail]] rules) are listed
-- once too: `detail_of` names the high-detail one, `detail` says which level a row is.
CREATE TABLE IF NOT EXISTS library_item (
    asset_id INTEGER PRIMARY KEY REFERENCES asset(id) ON DELETE CASCADE,
    game TEXT NOT NULL,
    grp TEXT NOT NULL,
    sub TEXT NOT NULL,
    label TEXT NOT NULL,
    copy_of INTEGER,                 -- NULL: shown; otherwise the asset shown instead
    detail TEXT NOT NULL DEFAULT '', -- 'high', 'medium', 'low' ('' when no levels)
    detail_of INTEGER                -- NULL: shown; otherwise its high-detail item
);
CREATE INDEX IF NOT EXISTS library_group ON library_item (game, grp, sub);
CREATE INDEX IF NOT EXISTS library_copy ON library_item (copy_of);
CREATE INDEX IF NOT EXISTS library_detail ON library_item (detail_of);

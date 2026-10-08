# Code tour

Every package and module, what it does, what it calls, and where to start reading.
Kept current with each change (definition of done, [`README.md`](README.md)).

```
dr2kit/
  __init__.py          version; the package map
  __main__.py          `python -m dr2kit` = the `dr2` command
  errors.py            the exception hierarchy
  hashing.py           the engine's string hash
  census.py            read everything, count it, run the format gates
  profiles/            per-game settings (cz.toml, cw.toml) + finding the game data
  container/
    big.py             the .big archive: read, edit, write (byte-identical)
    xcompress.py       chunk framing of compressed entries
    lzx/               LZX: native loader, pure-Python decoder, encoder
    vpath.py           virtual paths + AssetTree (any asset at any depth)
    stfs.py            the XBLA package (STFS) reader / unpacker
  formats/
    bct.py             textures: 48-byte header, mip/face layout, Xenos tiling
  convert/
    png.py             pure-Python PNG reader/writer (Pillow used when present)
    dxt.py             DXT1/DXT5/DXN block decode + encode (numpy, pure-Python fallback)
    texture.py         .bct <-> RGBA image: decode, replace (reference blocks), mips
  index/
    schema.sql         the SQLite tables
    build.py           build / refresh the asset index (incremental), thumbnails, relations
    query.py           search, children, model<->texture relations
  mods/
    manifest.py        mod.toml, the list of overrides
    build.py           overrides -> whole replacement files (re-pack, re-compress, verify)
    deploy.py          copy a build into a recomp's game_mods/ (and undo it)
  studio/
    app.py, viewers.py DR2 Studio (PySide6): tree, search, texture viewer, mod bar
  cli/main.py          the `dr2` command
native/lzx/            the C library behind the fast LZX decoder (libmspack, LGPL)
tests/                 unit tests (synthetic data) + game-data tests (skip if absent)
tools/                 one-off developer scripts (e.g. the PyAV codec check)
```

## How a read flows

Reading `data/models/npcs.big/chest_default.tex/chest_default_cm`:

1. `AssetTree.resolve()` (`container/vpath.py`) walks the folders under the game root,
   ignoring case, until it reaches a file: `data/models/npcs.big`.
2. It parses that file with `BigArchive.parse()` (`container/big.py`), which checks the
   header before trusting anything and builds a list of `BigEntry`.
3. It finds the entry `chest_default.tex`. The entry's `data()` returns the asset; if the
   entry is compressed, `xcompress.decompress_entry()` splits it into chunks and
   `lzx.decompress()` decodes each one (native library, or the Python fallback).
4. The result starts with the `.big` magic, so it is parsed as a nested archive, and
   `chest_default_cm` is looked up inside it.

Writing goes the other way: `BigEntry.set_data()` re-encodes if the entry was
compressed (`xcompress.compress_entry()` → `lzx.encode_chunk()`, verified by decoding),
and `BigArchive.to_bytes()` lays the archive out again.

## Modules

### `dr2kit/errors.py`
`Dr2Error` is the base of every error raised on purpose; the CLI turns it into a one-line
message. `FormatError` (and its `LzxError`) mean "the bytes don't match the format we
know", and always name the file or vpath. `GameNotFoundError` and `VPathError` are
"you asked for something that isn't there".

### `dr2kit/hashing.py`
`name_hash()` is the engine's `h = h*33 ^ c` string hash (signed chars, 32-bit).
`entry_hash()` lower-cases first, which is what every `.big` index stores (checked over
every entry of both games by the census).

### `dr2kit/profiles/`
`load_profile("cz")` reads `cz.toml`: name, title ID, where a recomp keeps the data,
and the census totals the game-data tests expect. `locate("cz")` finds the data: the
`DR2_CZ_DATA` environment variable, then the user config file (`dr2 games set`), then a
recomp next to the checkout. It returns a `GameLocation` (the root folder containing
`data/`, and how it was found). Game differences belong in the TOML, never in `if game
== "cw"` code.

### `dr2kit/container/big.py`
The heart of phase 1. `BigArchive.parse(bytes)` / `.open(path)` → `.entries`, a list
of `BigEntry` (name, stored bytes, `size2`, `flags`, `compression`, `hash`,
`alignment`). `.to_bytes()` / `.save()` write it back. Read its module docstring first:
it lists the measured facts the code relies on. Two design points:

- **Entries are a list, not a dict.** Names repeat inside one archive, so position is
  the identity; `find()` / `get(name, occurrence)` are conveniences.
- **No stored offsets.** The writer recomputes every offset from each entry's
  `alignment` (the largest power of two, up to 0x800, that divided its original
  offset). That reproduces shipped archives exactly and keeps payloads aligned after an
  edit. Why that works is explained in the docstring.

### `dr2kit/container/xcompress.py`
The framing of a compressed entry: a big-endian header (size, window), then chunks of at
most 32 KB, each with its own `0xFF` header and an independent LZX stream.
`parse_stream()` checks every length (and reports leftovers), `decompress_entry()`
decodes, `compress_entry()` encodes and verifies by decoding.

### `dr2kit/container/lzx/`
- `__init__.py`: `decompress()` picks the native decoder when it loads, Python
  otherwise; `backend_detail()` says which.
- `native.py`: finds and loads `dr2lzx` with ctypes (search order in
  [`setup.md`](setup.md)).
- `pydecode.py`: the pure-Python decoder, written from the format description (not from
  libmspack, which is LGPL). Its docstring is a short LZX primer.
- `encode.py`: the encoder ported from the CZ recomp: greedy LZ77 + per-chunk Huffman
  trees, verbatim blocks, and uncompressed blocks for data that doesn't compress (as the
  game's own encoder does).

### `dr2kit/container/vpath.py`
Virtual paths ([glossary](../glossary.md)): `split()`/`join()`, `name#N` for repeated
names and `@N` for positions, `AssetTree` to resolve them against a game folder, and
`walk_archives()` to visit every archive, nested and compressed ones included.

### `dr2kit/container/stfs.py`
`Package(path)` opens an Xbox 360 XContent package (STFS, or SVOD); `.files`, `.read()`,
`.describe()`. `unpack()` writes the files to a folder. Used by `dr2 unpack` so people
without a recomp (macOS) can get the data.

### `dr2kit/census.py`
`run_census(game, tree)` reads every file, archive and entry (nested and compressed
ones too), counts extensions, flags, compression, block types, alignments and texture
header bytes, and runs the gates: round trip, decode, and optionally re-encode
(parallel) and a pure-Python cross-check. `format_report()` prints it; `problems` must
be empty.

### `dr2kit/cli/main.py`
`dr2 doctor | games | ls | find | extract [--png] | info | index … | mod … | studio |
census [--textures] | unpack`. One `cmd_<name>`
function per command, no format logic. Exit code 1 on a `Dr2Error` or when a census
finds problems.

### `dr2kit/formats/bct.py` (phase 2)
A texture's bytes → `Bct` (a `BctHeader` with every field kept, plus the still-tiled
payload). `layout(header)` lists every `Level` (mip level × cube face) with its byte
offset, row pitch and, for packed levels, its unit offset inside the shared tile.
`untile()` / `tile()` move one level between tiled order and plain rows (numpy when
available); `swap_to_little()` undoes the big-endian storage. Read its docstring and
`formats.md` §Textures first: the layout rules there are what everything else trusts.
`Bct.parse` checks the header and that every unit of every level fits in the payload.

### `dr2kit/convert/png.py`, `dxt.py`, `texture.py` (phase 2)
- `png`: `Image` (width, height, RGBA bytes) is the one image type of the toolkit.
  `encode()` writes 8-bit RGBA/RGB/L; `decode()` reads what editors write (uses Pillow
  if installed, `decode_pure()` otherwise).
- `dxt`: `decode(fmt, blocks, w, h)` and `encode(fmt, rgba, w, h, reference=None)` for
  DXT1/DXT5/DXN (and BC4). With a `reference`, blocks whose pixels are unchanged are
  copied from it, and only the others are encoded. That is what makes "export, re-import
  unchanged" give back the shipped bytes. Pure-Python twins of both exist and are tested
  against the numpy ones.
- `texture`: `to_image(bct, level)` (cube maps as a 6-face strip), `decode_level`,
  `encode_level`, and `replace_image(bct, image)`: same size only (v1), reference
  blocks, mips kept if level 0 is unchanged, else rebuilt by `downsample`.

### `dr2kit/index/` (phase 2)
`build.build_index(game, tree, db)` walks every file and archive (like the census) and
fills `asset`, `texture` (with a PNG thumbnail), `material_slot` (the names in each
model's `MatTextureInfoArray`), then `link_relations()` joins slot names to textures.
Unchanged files (same size and mtime) are skipped on a rebuild. `connect()` creates the
schema, drops an index from an older schema version, and uses WAL mode. `query` holds
every SELECT: `search`, `get`, `children`, `files`, `textures_of`, `used_by`,
`same_content`, `thumbnail`. The default database is in the user cache folder
(`default_db_path()`).

### `dr2kit/mods/` (phase 2)
- `manifest`: `Mod.load(folder)` reads `mod.toml`; `Mod.files()` lists `replace/`;
  `create()` makes a new mod folder.
- `build`: `classify()` checks every override against the game and returns a plan (or
  one `ModError` listing every problem: unknown path, not a texture, conflicts).
  `build()` groups overrides by file on disk, runs `patch_archive()` down each vpath
  (re-encoding compressed entries via `BigEntry.set_data`), writes whole files, then
  `verify()` reads every override back through a fresh `AssetTree`. `base_dirs` makes
  it patch a recomp's `game_patched` copy instead of the shipped file.
- `deploy`: `deploy(build, target)` copies files and records them in
  `dr2kit-deployed.json`; `undeploy(target)` removes exactly those. `recomp_folders()`
  names `game_mods` / `game_patched` / `game_kbm` / `game_bootskip` next to a game root.

### `dr2kit/studio/` (phase 2)
DR2 Studio; see [`studio.md`](studio.md).

## Tests

`tests/conftest.py` has `make_archive()` (build a synthetic archive in one line) and
the `game_root` fixture (skip with a reason when a game is absent). One test file per
module; `test_gamedata.py` holds the real-data checks. See [`testing.md`](testing.md).

# Code tour

Every package and module, what it does, what it calls, and where to start reading.
Kept current with each change (definition of done, [`README.md`](README.md)).

```
dr2kit/
  __init__.py          version; the package map
  __main__.py          `python -m dr2kit` = the `dr2` command
  errors.py            the exception hierarchy
  userdirs.py          per-user folders, with or without platformdirs (Blender) (phase 6)
  help/                the in-app help: the modding guides, found, listed, searched (phase 7)
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
    scene.py           models and skeletons: nodes, materials, meshes, draws (phase 3)
    scene_write.py     writing scenes: chunk serialisers, strips, new geometry (phase 4)
    vertex.py          360 vertex declarations, stream decoding and encoding (phases 3-4)
    xma.py             sounds: RIFF XMA2, cache.big stream tables, packet headers (phase 5)
    audioscript.py     .sfx and audio scene scripts: the block text format (phase 5)
    shader.py          shader constant tables (.po) and material value sets (.scv)
    bcs.py             string banks (str_<lang>.bcs): read, write, JSON, apply changes (phase 6)
    level.py           levels: the zone list and each zone's placement table (phase 10)
    levelscript.py     the block text files (level, items, missions), kept byte for byte (phase 10);
                       block paths, add / remove blocks and keys in the tool's style (phase 11)
    leveledits.py      .edits.json: a mod's changes to a text file by block path; apply, diff, merge (phase 11)
    collision.py       a zone's collision: Havok triangle meshes in MERGED_COLLISION.big (phase 10)
    effect.py          particle effects of effects.big: emitters, fields (phase 13)
    anim.py            animations (.anm): header, tracks, key mask, every key (phases 13.2, 14)
  convert/
    png.py             pure-Python PNG reader/writer (Pillow used when present)
    dxt.py             DXT1/DXT5/DXN block decode + encode (numpy, pure-Python fallback)
    texture.py         .bct <-> RGBA image: decode, replace (reference blocks), mips
    gltf.py            scene -> .glb (skeleton, meshes, skin, materials); .glb -> node records
    model.py           vpath -> .glb with textures found by name (TextureFinder)
    model_import.py    .glb (Blender) -> model: matching, rig validator, import (phase 4)
    audio.py           .xma -> PCM / WAV through PyAV; fitting audio to a sound (phase 5)
    material.py        bake colours that come from shader constants (zombie clothing)
    strings.py         find, search and export strings; write a mod's string changes (phase 6)
    variants.py        which parts and colours a model shows: the game's shape classifier,
                       slots, looks, colour choices, prop states (phase 9)
    level.py           levels: list them, read a zone, put its pieces in place → .glb (phase 10)
    placed.py          what the level text files place: items (→ models), doors, markers (phase 10)
    zombies.py         zombie crowds from missions.txt, spread over their areas (phase 10)
    levelcheck.py      what level edits mean: items, zombie types, load sets, areas, triggers (phase 11)
    buildings.py       a zone's pieces grouped into buildings, each with its collision shapes (phase 11)
    mapdata.py         the Maps tab's data: zone files cached on disk, a level's markers as JSON (phase 10)
    weapon_fit.py      any .glb laid where a game weapon lies (handle end, grip nodes), one texture atlas (phase 13)
    icon.py            a weapon's pictures from its model: inventory icon, combo card (empty card, portrait, drawings) (phase 13)
    holding.py         Chuck holding an item: his outfit, the idle from sgraph.txt, the frozen pose,
                       the item at his hand (phase 13.2)
    video.py           Bink movies (Case West): probe, frames, sound, .mp4 export (phase 6)
  index/
    schema.sql         the SQLite tables
    build.py           build / refresh the asset index (incremental), thumbnails, relations
    query.py           search, children, model<->texture relations
  mods/
    manifest.py        mod.toml, the list of overrides
    build.py           overrides -> whole replacement files (re-pack, re-compress, verify)
    deploy.py          copy a build into a recomp's game_mods/ (and undo it)
    audio.py           sound overrides -> dr2kit_audio/ (WAVs + substitution table, phase 5)
    library.py         the mod manager: a library folder, load order, on/off, install, pack (phase 6);
                       linked mods, new mods, mod sets, .dr2mod, update summaries (phase 7)
    play.py            Play: deploy the switched-on mods, start the recomp, what is deployed (phase 7)
    preview.py         see the switched-on mods without the game: a ModdedTree for every view (phase 10)
    leveledit.py       one mod's edits of one text file: edit, undo, save as the diff (phase 11)
    pieceedit.py       one mod's building edits of one zone: pieces, copies, collision, undo (phase 11)
    newitem.py         a new item of your own: a recipe that copies a game item's pack (phase 11);
                       its own icon, combo-card pictures assembled at build time (phase 13)
    newweapon.py       the weapon wizard: WeaponSpec -> pack recipe, items.txt block, strings, combo card (phase 13)
    texture_import.py  exports from Substance Painter / Blender / any program → the model's textures (phase 7)
  studio/
    app.py, viewers.py DR2 Studio (PySide6): tree, search, texture viewer, mod bar
    model_view.py      the 3D view: QWebEngineView + three.js over a dr2: URL scheme
    variant_panel.py   the Variants panel beside the 3D view: slots, colours, detail (phase 9)
    maps_view.py       the Maps tab: level list, the 3D level page, layers, Go to, what is this (phase 10);
                       the Edit section (phase 11)
    maps_edit.py       the Maps editor: LevelEditor (move, turn, add, delete, undo; buildings), item_glb (phase 11)
    maps_panels.py     the Maps editor's Place (drag things in) and Hierarchy (find things) panels
    docks.py           every panel a dock window: layout, the two modes, Windows menu, saved layout
    audio_view.py      the audio view: waveform, playback (QAudioSink), loop (phase 5)
    text_view.py       text editor with a diff, and the string-bank table (phase 6)
    video_view.py      the movie view: Bink pictures + sound (phase 6)
    mod_manager.py     the mod manager window (phase 6)
    setup_dialog.py    "Game folders": each game's folder or package, the programs Studio starts
    help_view.py       the help window (phase 7)
    welcome.py         the first-steps checklist (phase 7)
    edit_tools.py      edit in the image editor (re-import on save), open in Blender (phase 7)
    share_dialog.py    Share (details, preview, check, .dr2mod) and Install windows (phase 7)
    weapon_dialog.py   the New weapon… window: the wizard's form, live preview (phase 13)
    hold_view.py       "Chuck holding it": the 3D view of a weapon in his hand, handles, effects (phase 13.2)
    icon/              dr2studio.svg, the app icon (phase 7)
    web/               its pages (viewer, maps, hold: .html + .js) and vendored three.js (MIT)
  cli/main.py          the `dr2` command
native/lzx/            the C library behind the fast LZX decoder (libmspack, LGPL)
blender/io_dr2/        the Blender add-on (GPL; toolkit.py, core.py, __init__.py): dev/blender-addon.md
packaging/             PyInstaller spec + entry scripts + the release README: dev/packaging.md
tests/                 unit tests (synthetic data) + game-data tests (skip if absent)
tools/                 developer scripts: PyAV codec check, the phase 3 gates
                       (blender_skeleton_gate.py, capture_gate.py; --root for phase 4),
                       blender_gate_model.py (builds the phase 4 test model in Blender),
                       xex_digests.py (the files each executable digest-checks),
                       blender_addon_gate.py (the add-on's flow inside Blender),
                       build_release.py + release/build_ffmpeg_lgpl.sh + release/make_icons.py
                       (releases), newcomer_gate.py (phase 7: make, share, install, Play),
                       variant_table.py (phase 9: the shape-group table out of an executable),
                       effect_table.py (phase 13: the particle-effect names out of an executable)
setup.py               only a build hook: copies docs/modding into dr2kit/help/en/ in packages
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

### `dr2kit/help/` (phase 7)
The help *is* the modding guides. `help_root(lang)` finds them: `dr2kit/help/<lang>/` in
a built package (copied there by `setup.py`), `docs/modding/` (English) or
`docs/modding/<lang>/` in a checkout; a missing language or page falls back to English.
`topics()` lists pages in the order of the guides table, then the glossary; `read`,
`search(text)` (lines containing every word, with their section), `context(kind)` (the
"How to mod this" entry from `context.toml`). Used by Studio's help window and
`dr2 help`. `tests/test_help.py` also checks that every link between guides resolves.

### `dr2kit/mods/play.py` (phase 7)
`find_recomp(game)` (the user's choice `[recomps]`, else a release's program beside
`assets/`, else the newest source build from the profile's `recomp_executables`),
`set_recomp`, `deploy_library(game, library)` (build + deploy the switched-on mods, or
remove the deploy when none is on), `launch(game, mods=True, extra_env)` (detached, in
the program's folder; mods off through the profile's `no_mods_env`; `launch_env` adds the
profile's `play_defaults`, the renderer switch, when the program is a source build with no
`<game>_defaults.env` beside it), `deployed(game)` /
`undeploy_all(game)`. Used by `dr2 play`, `dr2 mod status` and Studio's Play buttons.

### `dr2kit/mods/texture_import.py` (phase 7)
`plan(tree, model_vpath, sources, game)` → `TexturePlan`: each exported picture matched
to a game texture of the model, by exact texture name or by `<texture set>_<channel>`
(the texture set is a material as our `.glb` names it, `00_<colour texture>`, possibly
after Painter's `$mesh_` prefix; the channel word picks the role: BaseColor/Diffuse →
colour, Normal → normal, Specular → specular; Roughness/AO… are named and skipped),
with notes (resize, green flipped, alpha lost on DXT1). A `.glb` source gives its
materials' base colour and normal images. `green_convention(img)` is the integrability
test of `formats.md` §Texture conventions; `_metal_rough` turns BaseColor + Metallic
into diffuse + specular; `resize` uses Pillow's Lanczos, else numpy area/bilinear.
`apply(plan, mod)` writes `replace/<vpath>.png` at the game's size. Used by
`dr2 mod import-textures` and Studio's *Import textures…* (and drops on a model).

### `dr2kit/userdirs.py` (phase 6)
`config_dir()`, `cache_dir()`, `data_dir()`: platformdirs' folders when it is installed,
the same folders computed by hand when not (Blender's Python). Used by
`profiles.config_path`, `index.build.default_db_path`, `mods.library.default_library`.

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
the files the executable digest-checks (`digest_checked`), whether its program needs
`_BONEHIERARCHY_` in every scene (`scene_hierarchy`, Case Zero), and the census totals the
game-data tests expect. `get_config` / `set_config` read and write the user config file
(`[games]`, `[mods]`). `locate("cz")` finds the data: the
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
ones too), counts extensions, flags, compression, block types, alignments, texture
header bytes and scenes (`check_scene`: every scene's chunks rewrite identically;
with `models=True` every draw is decoded and its vertices re-encoded; with
`reimport=True`, `check_reimport` exports each model to `.glb`, imports it back and
rebuilds every shape; with `audio=True` every `.xma` is decoded in a process pool and
its length checked, every `.sfx` track resolved and every Bink movie decoded,
`check_movie`; string banks are always parsed and re-written, `check_bcs`), and runs the gates: round trip, decode, and optionally re-encode
(parallel) and a pure-Python cross-check. `format_report()` prints it; `problems` must
be empty.

### `dr2kit/cli/main.py`
`dr2 doctor | games | ls | find | extract [--png | --glb | --wav | --mp4] | model check|import | info |
index … | mod … | strings … | studio | census [--textures] [--models] [--reimport] [--audio] | unpack`.
`dr2 mod` covers single mods (`new`, `check`, `build`, `deploy`, `undeploy`) and the mod
manager (`list`, `install`, `remove`, `enable`, `disable`, `move`, `conflicts`,
`library`, `pack`); `check/conflicts/build/deploy` with no mod folder use the library's
switched-on mods. One `cmd_<name>`
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

### `dr2kit/formats/scene.py`, `vertex.py` (phase 3)
`Scene.parse(bytes)` / `Scene.from_archive(arc)` → `header`, `description`,
`skeleton` (a `Skeleton` of `Node` records in index order; `world_matrices()` gives the
rest pose), `hierarchy`, `materials` (`Material` with its `TextureSlot`s), `shaders`,
`meshes` (`Mesh` → `Draw`s) and `unknown` (chunk names it doesn't use). A `Draw` is one
`RenderStrip` record + one command-buffer packet (`parse_command_buffer`): material
(already resolved from its id), bone palette, vertex declaration, which buffer each stream
reads and from where, index range. `Scene.draw_data(draw)` decodes it to a `DrawData`
(positions, normals, UV sets, colours, joints as node indices, weights, triangles).
`Scene.rigid_node(mesh)` is the node an unskinned shape's vertices are relative to
(`formats.md` §Rigid parts; the `.glb` export, the importer and the renderer use it).
`vertex.py` holds the 360 `D3DDECLTYPE` table and one decoder per packing. Read
`formats.md` §Scene container first; both docstrings list the facts the code trusts.

### `dr2kit/formats/scene_write.py` (phase 4)
The way back. Read its docstring and `formats.md` §Writing scenes first.

- **Serialisers** (`command_buffer_bytes`, `strip_bytes`, `shape_bytes`,
  `buffer_record`) and `rewrite_problems(scene)`, which rebuilds every chunk the reader
  interprets and names any that differ (the census runs it on every scene: none do).
- `split_packets(cmds, offsets)`: a command buffer cut into one packet per draw at
  the `RenderStrip` word-5 offsets.
- `triangles_to_strip`: triangles → one strip with the games' winding rule.
- `DrawGeometry`: one part of a shape in model space (positions, triangles, normals,
  UVs, colours, joints as node indices, float weights). `quantize_weights`,
  `compute_tangents`, `split_by_palette` (runs of ≤ 61 nodes).
- `find_template(scene, mesh, material)`: the original draw a new part copies (its
  declaration, packet, flags).
- `SceneEditor(scene).replace_mesh(name, parts)` then `.to_bytes()`: encodes the parts,
  rewrites the shape's own buffers or appends to the combined ones, clones packets,
  writes `RenderStrip`, shape chunk, headers, bounds and `_BOUNDINGBOX_`. It edits the
  `Scene`'s archives **in place**: decode everything you need before calling it.

`vertex.py` gained `encode_element` / `encode_value`, the exact inverse of each decoder
(and its signed-normalised decode no longer clamps, so the inverse exists).

### `dr2kit/convert/model_import.py` (phase 4)
`plan_import(scene, glb)` → `ImportPlan` (shapes to rewrite as `DrawGeometry` lists,
shapes kept, every `Issue` found: the **rig validator**); `import_glb` runs it, writes
through `SceneEditor`, then parses the result and decodes the new draws as a check;
`format_plan` prints a plan (`dr2 model check`, Studio's *Replace with .glb…*). Matching
rules (shape and bone names, materials, skinning back to the rest pose, "unchanged"
detection): [`gltf-mapping.md`](gltf-mapping.md) §Coming back: models. Mods use it for a
`replace/<model vpath>.glb` (`mods/build.py`, kind `model-glb`).

### `dr2kit/formats/xma.py`, `audioscript.py` (phase 5)
Read `formats.md` §Audio first: it has the measured rules these modules trust.

- `xma`: `Xma2Format` (the 52-byte `fmt` chunk; `extradata()` is what ffmpeg takes),
  `XmaRiff.parse` (fmt / seek / data, unknown chunks are errors), `riff_wrap(packets,
  channels, rate)` (a RIFF header around raw packets, so ffmpeg opens both shapes the
  same way), `PacketHeader` / `packet_headers` / `frame_count` / `stream_starts`
  (multi-stream sounds), `fingerprint` (FNV-1a 64 of a packet, the recomps' key),
  `StreamTable` (`cache.big`'s `$GIB` tables; `find(name)` hashes the case-kept name),
  and `AudioInfo` (channels, rate, shape, where the packets are, the expected length,
  the loop in decoded samples) built by `info_from_riff` / `info_from_record`.
- `audioscript`: `parse(text)` → `Block` trees (class, name, properties, children;
  errors name the line); `sfx_tracks` (the bank entries a `.sfx` plays) and
  `script_refs` (every `Asset` / `BigFile` of a scene script, with the block path and
  trigger events as `context`).

### `dr2kit/formats/shader.py`, `dr2kit/convert/material.py`
Some materials take their colour from shader constants, not from their `_cm` texture
(`formats.md` §Materials: value sets). `shader.constant_table(po)` reads a shader's
name → register table; `ValueSet.parse(scv)` a material's constants by register, and
`.named(table)` by name. `material.ShaderLibrary(tree)` finds pixel shaders by hash;
`recipe(scene, material, shaders)` says whether (and how) a material must be baked;
`bake(recipe, image)` computes the colour texture with numpy. `model.TextureFinder.baker(scene)`
is the `base_colour` hook `gltf.model_to_glb` uses (CLI `--glb`, Studio's 3D view and
*Export .glb…*). Families: pattern, body part, channel, lens (glasses) and hair (lashes; the
last two keep opacity in alpha). `alpha_mode(shader name)` says whether a shader uses its
colour map's alpha as transparency (`…OM…` and hair shaders), and `material_shaders(scene)`
which shaders each material's draws use: the `.glb`'s `alphaMode` and the Library's
pictures both follow it.

### `dr2kit/formats/bcs.py`, `dr2kit/convert/strings.py` (phase 6)
Read `formats.md` §Strings first.

- `bcs`: `StringBank.parse(bytes)` → `.strings` (id → text, in id order) and `.size`
  (the padded file size, kept so an unedited bank writes back identically);
  `.to_bytes()`. `to_json` / `from_json` (ids or `IDS_` labels), `apply(bank, changes)`
  → a new bank plus notes for the modder (markup without `@`, placeholders changed,
  new ids; refuses ids past the last), `markup_problems(text)`.
- `strings`: the modder's level. `languages(tree)`, `load_bank(tree, "fr")`,
  `load_labels(tree)` (from `str_id.bcs`), `resolve_id("IDS_PRESS_START")`,
  `search(tree, text, langs)`, and a mod's string file: `read_mod_strings`,
  `set_mod_strings(mod, lang, {id: text or None})` (keeps labels and the original text
  next to each change as a reminder). Used by `dr2 strings` and Studio's strings table.

### `dr2kit/convert/video.py` (phase 6)
Case West's Bink movies through PyAV: `probe` → `VideoInfo`, `frames(data, start)`
yields RGB pictures, `audio(data)` → stereo `Pcm` (5.1 tracks mixed, see the module
docstring and `formats.md` §Movies), `to_mp4` (ffmpeg's LGPL `mpeg4` + `aac`
encoders). Used by `dr2 extract --mp4`, `dr2 info`, the census (`check_movie`) and
Studio's video view.

### `dr2kit/convert/audio.py` (phase 5)
`AudioLookup(tree).info(vpath, data)` finds a sound's format (its RIFF header, or its
stream-table record; tables are read once). `decode(data, info)` → `Pcm` (16-bit
interleaved, plus the peak) through PyAV; `length_check` is the census rule;
`stream_packets` decodes stream by stream, one packet per call like the recomps, and
says where each packet's output lands (what the substitution table records).
`load_audio` reads a modder's WAV/OGG/FLAC/MP3, `conform` fits it to a sound (channels,
rate, exact length; returns notes), `split_streams` cuts 5.1 into stereo streams.
`have_decoder()` says whether PyAV with `xma2` is there; without it, `decode` raises
`AudioBackendMissing` with the install command.

### `dr2kit/convert/gltf.py`, `model.py` (phase 3)
- `gltf`: `GlbBuilder` (accessors, buffer views → `.glb` bytes) and `Glb.parse` (the
  reverse); `skeleton_to_glb(scene)`, `model_to_glb(scene, texture_png)`,
  `skeleton_from_glb(bytes)` (records back, bit-exact within the snap tolerance). The
  mapping is documented in [`gltf-mapping.md`](gltf-mapping.md).
- `model`: `TextureFinder(tree, model_vpath, game)` is the `texture_png` callback: the
  model's own `.tex` pack first, then the archives around it, then the `.tex` files in
  the model's folder on disk (loose models such as `data/dynamicprops/special/*.big`),
  then the asset index (shared packs elsewhere, e.g. `models/special/weapon_common.tex`).
  `export_glb(tree, vpath)` / `export_skeleton_glb` tie it together for the CLI
  (`dr2 extract --glb`) and Studio. `TextureFinder.bake(scene, material, valueset)` bakes
  a material's colours (with another value set for a colour choice) and remembers it.
- Phase 9: `model_glb(tree, scene, variant=…, mode="all"|"shown")` is the one way every
  caller (CLI, Studio, Export all, the Blender add-on) makes a model's `.glb` in a look:
  `"all"` tags each node (`dr2_group`, `dr2_shown`, `dr2_part`) and writes the colour
  choices as `KHR_materials_variants`; `"shown"` leaves the hidden parts (and their
  textures) out. `model_to_glb` gained the `parts`, `include`, `colour_variants` and
  `extras` arguments for it.
- Phase 10: `TextureFinder` treats `<piece>.tex` as a level piece's own pack (its scene is
  `<piece>.big/_COMP_<piece>.big`) and ranks the small `_LOD.tex` copies last
  (`lod=True`: first). `gltf.Assembler` merges whole `.glb` files into one: `add(glb,
  placements, parent)` copies meshes and materials once and gives each placement its
  own node tree (instancing), images with the same bytes are stored once, `group(name)`
  makes a folder node (a Blender collection).

### `dr2kit/formats/level.py`, `dr2kit/convert/level.py` (phase 10)
Levels ([`formats.md`](../formats.md) §Levels). `formats.level` reads the binary tables:
`read_zone_list` (`zonelist.big` → `Zone` records), `ZoneOrganization.from_entries`
(`ZONE_ORGANIZATION.big` → `Placement` records: piece, scale, quaternion, position,
world bounds, distances, flags, the unknown bytes kept in `tail`), each with `to_bytes`
(byte-identical, checked by the census). `Placement.matrix()` / `to_world(p)` apply
world = rotation × (scale × local) + position. `convert.level` finds the levels
(`list_levels`, `Level.open(tree, "prologue")`), reads a zone (`Level.zone("z05")` →
`ZoneData`: pieces by name → scene vpath, placements, `unplaced`, `missing`) and builds
it as one `.glb` (`zone_glb`: each piece through `model.model_glb` in its default look,
placed by `gltf.Assembler`; `lod=True` for the small textures). The level census is
`census.check_levels` (`dr2 census --levels`); the CLI is `dr2 level list|info|things`.

Step 2: `formats.levelscript.Document.parse(bytes)` reads the block text format keeping
every line (`to_bytes()` is the file again; `set(block, key, value)` edits one line, for
phase 11), `Block.get/floats/numbered` read values. `convert.placed` turns a **script**
(`script_names`, `geometry_of`: which level folder it sits on) into `Thing`s by kind
(`read_script` → `LevelScript`: items, doors, spawn points, zombie areas, map / lighting
areas, triggers, sound areas, map points, `NavMesh`), naming unknown classes;
`ItemModels.resolve(item)` finds an item's scene through `items.txt` and the
`streamedassets.big` packs. `level.things_glb` places item models like `zone_glb`
places pieces, and `level.zone_of(position, zones)` says which zone a thing is in;
`census.check_level_scripts` is the text half of the level census.

Stretch: `mapdata.light_table(tree, name)` reads a lighting table into 24 hourly dicts
(sky, fog, key light, ambient up/down from the SH matrices), `mapdata.lighting(cache,
script)` lists a level's lighting contexts with their areas; the page draws the sky
gradient (the `Skybox` shader's formula), fog and lights for the context the camera is
in (`dr2.setHour`).
Stretch: `convert.zombies.crowds(tree, script)` reads the zombie factories of
`missions.txt` for a level, `spots(ls, crowds)` spreads them over their area's floor
polygons (ear-clipped, seeded); `level.zombies_glb` makes each type's model once per look
and places it (`gltf.Assembler.add(static=True)`: rest pose, no bones). `MapCache.zombies`
caches a zone's; the Maps page asks for them as a third part.
Stretch: `formats.collision.read_collision(arc, vpath)` reads every shape of a zone's
`MERGED_COLLISION.big` (found by its `hkCollisionShapeMesh` entry); `level.zone_collision
(tree, zone)` puts them in world space (the shape's piece, by name or the collision node
number, then the placement when the placed shape lands among the zone's pieces; no piece:
world; the few whose place is unknown are left out and named) and `level.collision_glb`
makes one see-through orange mesh. `MapCache.collision` caches it (one size); the Maps
page's fourth part, drawn with `collisionLook` (fill + wireframe); `level_glb(collision=
True)` adds a *Collision* group to exports; `census.check_levels` counts shapes by rule.

Step 3: `convert.mapdata.MapCache(tree, game)` builds and keeps a zone's `pieces(level,
zone, detail)` and `items(level, zone, script, detail)` files on disk (named by
`stamp`: `MAP_VERSION`, the source files' sizes and dates, the tree's own `stamp()` when
it has one), and `overview(cache, level, script)` is the JSON a level opens with
(`map_picture`: the in-game map and the world rectangle it covers, from `map_rects`). In
`convert.gltf`, `lightmap_slots(scene)` and `blend_slots(scene)` say which materials
carry a lightmap (occlusion texture on its UV set) or a two-texture blend (extras).
`studio/maps_view.py` holds `MapsList` (left tab), `MapsView` (page + its panels) and
`_Builder` threads; `web/maps.js` the page (zone streaming, fly / orbit camera, markers,
picking) and `web/levelmaterials.js` the level materials, shared with `viewer.js`.

### `dr2kit/formats/leveledits.py`, `convert/levelcheck.py`, `mods/leveledit.py` (phase 11)
Level edits as mods ([`formats.md`](../formats.md) §Levels, "Level edits as mods").
`levelscript.Document` gained `find(path)` / `get` / `path(block)` / `parent`, `set`
(a new key goes where the tool sorts it; a changed value keeps its `// comment`), `unset`,
`remove(block)` and `add(parent, cls, name, props, children, index)`, all keeping the line
numbers of every other block right (`_insert` / `_delete`), and `render(...)`, which writes
a block as the game's tool did. `leveledits` reads and writes `.edits.json` (`Edits`:
`set`, `add`, `remove`), `apply(doc, edits)` (adds, then sets, then removes; every missing
path named at once), `diff(before, after)` (the edits between two versions, adds with
`@after`), `merge(layers)` (conflicts and what lost, by priority) and `apply_all(bytes,
layers)`. In `mods/build.py` the kind `edits` is planned like `strings`: grouped by file,
merged, dry-run over the shipped file and checked by `levelcheck.check` (errors stop the
build, warnings become notes); several overrides of one entry inside an archive now reach
`patch_archive` as a list (`merged_bytes`). `mods/leveledit.TextEdits(mod, file, tree,
base_dirs)` opens a file as the game has it with the mod's edits on top, keeps text
snapshots for undo / redo, and `save()` writes `diff(game file, edited)`. The CLI is `dr2
level show|edit|diff`; the census gate is `census.check_level_edits`. Step 2:
`studio/maps_edit.LevelEditor` (move / set_item / set_key / delete / add / duplicate,
undo / redo across files; each returns `ItemState`s of the changed placements) and
`item_glb`; `MapsView`'s Edit section and `maps.js`'s gizmo (dev/studio.md, "Editing").
Step 3: `convert.zombies.mission_spawns(tree, script)` gives a level's crowds and every
single zombie, respawn crate and clearing (`MissionSpawn`, with block paths);
`levelcheck.check` refuses a block added inside a game mission (`SAVE_BREAK`).
`studio/maps_edit.ZombieEdits` (mixed into `LevelEditor`): `zombies(script)` (what the page
draws, from the mod's `missions.txt`), `zombie_set`, `zombie_move`, `crowd_amounts`,
`own_mission` / `add_zombie` (the mod's own mission, cloned from the level's main zombie
mission), `remove_zombie`. Step 5: `LevelEditor.set_keys` / `remove_block` (*Settings…*,
deleting what the mod added), `added_markers` (the triggers and spawn points a mod adds,
for `dr2.setEditedMarkers`), `catalog.prefabs`; `MapsView.sync_edits` shows a mod's
changes when a level opens. Own items: `mods/newitem.new_item` writes a `.copy.json` recipe
(`build_copy` makes the pack: renamed, a `.glb` imported, PNGs over textures), the
`items.txt` block and `sources/`; `mods/build.py` plans `add/` files (kind `add`,
`Planned.data` for recipes) and `add_entry` inserts them; `BigArchive.add` gives a new
entry its siblings' declared alignment (`sibling_flags`); `ModdedTree._apply` shows adds;
`LevelEditor.reload_models` sees the mod's own items (a `Preview` of the mod alone).

### `formats/pieceedits.py`, `mods/pieceedit.py`, `convert/buildings.py` (phase 11 step 4)
Building edits ([`formats.md`](../formats.md) §Levels, "Piece edits", "Buildings").
`pieceedits` reads and writes `.pieces.json` (`Edits`: `pieces`, `copies`, `collision`),
`apply(org, edits)` (a new `ZoneOrganization`: records placed anew by `placed`, hidden ones
`parked`, copies appended), `zone_bytes` / `collision_bytes` / `target_bytes` (the nested
archive written again) and `merge(layers)`. `formats.collision.move_shapes` moves shapes
(vertices, the search tree's origin, the header). `mods/build.py` plans the kind `pieces`
like `edits` (grouped by target, merged, dry-run; verified after the build).
`convert.level.zone_shapes` gives each collision shape placed (`PlacedShape`: rule, piece,
world vertices; `zone_collision` merges them). `buildings.zone_buildings(zone, shapes,
moves)` groups pieces (`Building`: parts, shapes, bounds), `corrections` /
`set_correction` keep the modder's own (`buildings.json`). `mods/pieceedit.PieceEdits`
holds one zone's edits in a mod: `place`, `hide`, `restore`, `copy`, `drop_copy`, the
whole-building calls (`place_building` moves the parts relative to the first and the
collision by the first's offset, in each shape's own space), undo snapshots, `save` (two
files). `maps_edit.LevelEditor` wraps them (`piece_*`, `building_*`, `_piece_states`).
`census.check_buildings` checks every search tree's origin, a moved shape per zone, and
counts the buildings.

### The weapon wizard (phase 13): `mods/newweapon.py`, `convert/weapon_fit.py`, `convert/icon.py`
How a weapon of one's own is made (guide [`20-make-a-weapon.md`](../modding/20-make-a-weapon.md),
[`formats.md`](../formats.md) §Weapons). `newweapon.WeaponSpec` is everything the wizard
asks (kind, names, model and its placement, damage, durability, element, effects by slot,
icon, `Combo`); it is saved in the mod (`sources/<Name>.weapon.json`, `load_spec`), so
running `make_weapon(tree, game, mod, spec)` again rebuilds the weapon. `fit_weapon`
finds the kind's game weapon (`catalog.weapons`), its pack and texture sizes, and fits the
model: `weapon_fit.read_glb` (every mesh, node transforms, each material's colour as a
picture), `weapon_frame` (the game weapon's line: principal axes; the handle end from the
"business end" nodes, else the hand nodes), `fit` (the model's own frame onto it:
handle, length, turn, slide), `atlas` (one picture, UVs moved into cells), `fitted_glb`
(the game model's `.glb` with its first shape replaced, other shapes emptied), then the
import (`model_import.import_glb`) to be sure it goes in. `make_weapon` writes the pack
recipe (`newitem`: `glb`, `textures`, and phase 13's `icon` / `icon_name`), the
`items.txt` block (the template's props and children under new names, damage, element
keys and child block, effects: per attack, or a `PropEffectsOnCondition` slot), the
strings (`string_ids`: a block of 100 ids per mod id; English and French, the others
English; `weapon_string_ids.json` keeps them stable across runs), and the combo card (a
`cComboCardItem` with the game's first card's other keys, two `.bct.copy.json` recipes
with a `card`). `newitem.build_card` assembles a card when the mod is built:
`icon.card_template` (the median of the game's cards), the portrait (`icon.faded` for the
`_no` one), `icon.item_drawing` of the two items, `icon.compose_card`. `preview` draws
everything without writing (the shape over the faded game weapon, grip nodes as red
diamonds, the icon, the card): Studio's `weapon_dialog.WeaponDialog` runs it in a job
after each change. `remove_weapon` takes it all out. CLI: `dr2 mod new-weapon` /
`remove-weapon`, `dr2 effects`. Later the same day: `WeaponSpec.effect_start` and
`shine`; `weapon_fit.effect_locator(frame, start)` (the effect point: position and
rotation, +y toward the tip) → recipe `locators` → `newitem.set_locators` (both
`LocatorArray` copies, the model's and its `persistent.big`'s, and the node);
`SHINES` → recipe `material_params` → `newitem.set_material_params` (`MatArray` +16);
`preview` draws the effect line (`_effect_line`, yellow); `dr2 studio --mod --weapon`
(`studio.app.main`) opens a weapon's window.

### Particle effects (phase 13 step 6): `formats/effect.py`, `convert/effects.py`, `convert/effect_preview.py`, `mods/neweffect.py`, `studio/effects_dialog.py`
Guide [`21-effects.md`](../modding/21-effects.md), [`formats.md`](../formats.md) §Particle
effects. `formats.effect` reads and writes one effect (`Effect`: version, name, header
words, `Emitter`s kept as their bytes; `FIELDS` names each emitter field with how sure it
is, `Emitter.get` / `set`, `colour_keys`, `rename`) and `read_all(tree)` every effect of
`effects.big` by name; the census writes each one back byte for byte. `convert.effects
.apply_changes` applies a change dict (hue, saturation, brightness, alpha, size, time,
texture swaps, per-emitter fields, removals; unknown keys are an error) and `describe`
says an effect in words. `convert.effect_preview.preview` draws a sketch (each emitter's
particle picture tinted by its colour keys, at its sizes; `texture_finder` reads
`effects.tex`). `mods.neweffect`: `free_slots` (table names with no effect),
`change_effect` (an `.effect.json` in `replace/`), `new_effect` (a copy recipe
`EFFECT_Common<1000+number>.copy.json` in `add/`, the effect renamed to its slot),
`new_particle_texture` (a picture copy recipe in `effects.tex`), `own_effects`,
`changed_effects`, `remove`. The build (`mods/build.py`): `effect_bytes` makes an
`.effect.json`'s effect; `newitem.build_copy` an own effect; `register_in_scene` lists
added effects in the effects' scene (`SceneDescription` kind 13, `SceneHeader` word 3);
the profile's `preload_evict` files are evicted from `preload4.big` (index hash
`^ 0xDEADBEEF`); `repin_layout` writes `layout.bin` with the built sizes. Studio's
`effects_dialog.EffectsDialog` (*Effects…*) lists the table, previews in a job after each
slider move, and writes with *Change in my mod* / *Make my own from this*; the weapon
wizard's `EffectBox` lists the mod's own effects first. CLI: `dr2 effects [--show|--free]`,
`dr2 mod effect / new-effect / effect-picture`. Step 6.5 added the `layout` change (a new
emitter list from copies of the base's emitters) and `dr2 effects --free`.

### Chuck holding it (phase 13.2): `formats/anim.py`, `convert/holding.py`, `studio/hold_view.py`
[`formats.md`](../formats.md) §Animations; guide [`20-make-a-weapon.md`](../modding/20-make-a-weapon.md).
`formats.anim.Animation.parse` reads an `.anm`'s header, track table and key mask
(`keys(track)`), `first_pose()` its first keys as a `Pose` (rotations and translations by
skeleton node index; a rotation that isn't unit raises), `part_of(vpath)` which skeleton
part (`SKELETONS`) the track numbers refer to, `census(tree)` every `.anm` (`dr2 census
--anims`). `convert.holding`: `outfit_parts` (Chuck's models from `outfits.csv`),
`AnimGraph` (`sgraph.txt` read with `levelscript.Document`; `pick(chooser, value)` follows
nested groups with `DEFAULTS`, `standing_idle`, `hand_chooser`; one per game, `graph`),
`item_idle(tree, block)` → `Idle` (full-body, root and hand animations), `animation_pose`
/ `idle_pose` (first frames by node name), `posed_skeleton`, `full_pose` (every node's
posed local transform: what the parts and the page get), `posed_chuck` → `Chuck` (on
`RIG`, `playerfullbody.big`), `grip_matrix`, `hand_matrix`, `item_placement` (hand prop ×
grip⁻¹), `decompose`, `flat`; `chuck_glb` (posed, through `gltf.Assembler.add(…, pose=)`)
and `rest_glb` (at rest, cached: the page poses it), `posed_parts` / `picture` (the
software renderer with `render.scene_parts(…, skin=)`), `item_hold_glb` (`dr2 hold`).
`mods.newweapon.hold_scene` gathers what the page shows (`HoldScene`: the fitted weapon
with its colour picture, `gltf.glb_with_picture`; the placement; the pose; the weapon's
line in model space for the handles; the effect point; the effects, `effect_view`, with
the mod's own and changed ones, `neweffect.effect_as_shown` / `particle_png`), `hold_glb`
one `.glb` for Blender. `studio.hold_view.HoldView` hosts `web/hold.html` + `hold.js`
(three.js: the rig posed by the glTF names three.js keeps in `userData.name`, the weapon
under an `align` group whose TransformControls do slide / turn / length, the effect
point, `Emitter` particles drawn added); a handle let go sends `dr2:align {…}`, which
`WeaponDialog._aligned` puts in its boxes. The *Effects…* window shows the selected
effect, with its unsaved changes, on a game weapon of a chosen kind.

### Animations played (phase 14): `formats/anim.py` `decode`, `convert/holding.py` clips
[`formats.md`](../formats.md) §Animations. `Animation.decode()` reads every key the way the
game's decoder does (`_first_keys`, then frame by frame each track's next key:
`packed_rotation`, `delta_rotation`, `packed_translation`; `_rescale` is the game's Newton
step) into a `Clip` of `Channel`s (frames + values; `Channel.at` / `Clip.pose` interpolate,
`nlerp`); it raises when the keys don't end at the file's last byte. `convert.holding`:
`skeleton_ids` (skeleton id → skeleton file from `_ANIMCHANNELINFO_`), `skeleton_for`,
`companions` (a `fullbody.big` move with its `root.big` partner), `move_files` /
`item_moves` → `Move` (an item's `AnimationAttackName…` in its `AnimBankName` bank),
`clip` (layered files → JSON-able keys by node name; `rig=` fills every other node of
Chuck's rig with its rest value, as `full_pose` does for the parts), `cached_clip`,
`move_clips` (an item's attacks with its hand pose, for the *Move* box), `body_for`
(Chuck or a skeleton), `add_animation` (a clip as a glTF animation on every copy of each
node), `animation_glb` (`dr2 extract --glb <.anm>`, Studio's Export / Open in Blender),
`hang_on_hand` / `add_moves` (`dr2 hold --moves`: the item under the hand node).
`mods.newweapon.HoldScene.moves` carries the kind's attacks; `studio.hold_view.HoldView`
has the *Move* box, *Pause*, a time slider and *In place*, and with `tools=False` is the
Library's animation view (`MainWindow._show_anim`); `hold.js` samples the clip each frame
(`sampleKeys`), moves the weapon with the hand (`rememberHand` / `followHand`), takes the
travel out of `dummy01.root` (*In place*) and draws bones as lines (`setBones`).

### Buildings and maps of one's own (phase 14, the toolkit side)
[`phase14-kickoff.md`](../phase14-kickoff.md). `formats.pieceedits`: a `.pieces.json`'s
`new` list (`_new_spec`, `new_placement`: a `like` piece's record renamed, numbered past
the zone's highest, its own box placed). `mods.newitem.build_copy`: level pieces (the
`_COMP_<piece>.big` scene renamed with the piece; `textures` straight into a copied
`.tex` pack), `rename_textures` (`texture_names`: `.bct` entries and material slot
names), `_build_plain` (a plain file copied, level `edits` applied). `mods.build`:
`_new_file_folder` (an `add/` file under a folder is a new file, kind `file`),
`new_layout_record` and `repin_layout` (a `layout.bin` record per new file),
`_added_scripts` (a mod's own level scripts count as levels for the door checks). The
test mods are made by scripts outside the repo (`~/.cache/dr2kit-p14/scripts/`).

### Other games and the phase 13 gate: `tools/wow_import.py`, `tools/weapon_gate.py`
`wow_import` is a **local tool** (guide [`22-from-other-games.md`](../modding/22-from-other-games.md);
never part of Studio or the shipped CLI). `read_m2` reads a WoW 3.3.5 `.m2` (`M2`:
vertices, textures, texture lookup, `Particle`s: `M2Particle` 0x1DC bytes with its
`M2Track` / `FBlock` keys), `read_skin` a `.skin` (triangles, submeshes, texture units),
`blp_to_png` a texture (Pillow's BLP reader; `particle=True` puts the brightness into
alpha), `Source` finds files next to the model or in the MPQs (mpyq, patches first).
`model_glb` writes one mesh per submesh with its texture (`skin_texture` guesses an
item's replaceable texture); `import_effect` turns every emitter into one DR2 emitter
(`model_frame`, `emitter_changes`) of an own effect, adds the pictures as own particle
pictures and marks the mod `local_only` (`manifest.Mod.local_only`; `library.pack`
refuses it). `weapon_gate` drives Studio's own `EffectsDialog` and `WeaponDialog`
offscreen to make Frostmourne, places it, shares and installs it on a clean library
(`--install-user` puts it in the user's library and deploys it).

### `studio/docks.py`, `studio/maps_panels.py` (2026-10-11)
The window's dock windows and the Maps editor's Place and Hierarchy panels: dev/studio.md,
"Dock windows" and "The Maps tab".

### `dr2kit/convert/variants.py` (phase 9)
What a model can show, the way the game decides it ([`formats.md`](../formats.md)
§Variants; guide [`17-variants.md`](../modding/17-variants.md)). `Classifier` holds the
game's 53-record shape-group table from the profile (`[variants]`, copied from the
executable by `tools/variant_table.py`) and gives a shape name its bits with the game's
prefix rule. `model_variants(scene, game)` → `ModelVariants`: each mesh as a `Part`
(bits, group label such as *Head 2*, prop states, misplaced-digit flag), the `SLOTS` and
`TOGGLES` present, the `PROP_STATES` (twin shapes by name). `Choice` is one look;
`ModelVariants.parse(text)` / `Choice.text()` convert it, `default()`, `random()`,
`everything()` make one, `shown(choice)` and `hide_mask(choice)` apply it (and
`choice_from_mask` / `shown_by_mask` go the other way). `ColourBank(tree, game)` reads the
shader bank's value sets (`*-sc.big`) and the game's colour list; `colour_choices(scene,
bank)` finds each material's choices by the name rule; `read_variants` does both.

### `dr2kit/index/` (phase 2)
`build.build_index(game, tree, db)` walks every file and archive (like the census) and
fills `asset`, `texture` (with a PNG thumbnail), `material_slot` (the names in each
model's `MatTextureInfoArray`), then `link_relations()` joins slot names to textures.
Unchanged files (same size and mtime) are skipped on a rebuild. `connect()` creates the
schema, drops an index from an older schema version, and uses WAL mode. `query` holds
every SELECT: `search`, `get`, `children`, `files`, `textures_of`, `used_by`,
`same_content`, `thumbnail`, and for sounds (phase 5) `audio_info`, `sound_targets`
(what a `.sfx` or script names) and `sound_users` (who plays a sound, with events).
Phase 5 added the `audio` table (format and length of every sound, read without
decoding) and `sound_ref` (what each `.sfx` and audio scene script names), resolved
into `relation` rows by `link_sounds()`. The default database is in the user cache
folder (`default_db_path()`).

Phase 8 added `scene_pass()` (the `scene` table: each model's and skeleton's counts,
bone names, rest-pose bone positions, and a thumbnail drawn by `convert.render` from the
index's own texture thumbnails), `link_rigs()` (relation `model-rig`: the skeleton files
whose bone names include the model's, ranked by rest pose, because the rig families share
their 98 names) and `link_library()` (the `library_item` table from
`catalog/groups.toml`, identical copies folded with `copy_of`). `query` gained
`library_counts`, `library_items`, `library_item`, `copies`, `scene_info`, `picture`,
`rigs_of` and `rig_users`. Schema version 4.

Phase 9: `link_library()` also folds a model's detail levels (`[[detail]]` rules:
`zombie_cop_2/_3/_4`) into one item (`library_item.detail`, `detail_of`);
`library_items(details=True)` includes them (exports), `detail_levels(con, id)` lists
them. The model pictures show the default look (`convert.variants`; `THUMB_VERSION` 7).
Schema version 5.

### `dr2kit/convert/render.py` (phase 8)
A numpy software renderer for the Library's model pictures, run while the index is
built (no window or GPU needed). `scene_parts(scene, texture_for)` turns a scene's draws
into `Part`s (positions, triangles, normals, UVs, colour texture); `render(parts, size)`
draws them orthographically from the front-right, rasterising every triangle with a
lattice of points (`_lattice`) and keeping the nearest per pixel with one sort of packed
integer keys; only the winning points are shaded. `to_png` encodes the result.
`scene_parts` takes a `material_colour` hook, tried before the texture: the index uses it
to bake zombie clothing (`convert.material`), as the `.glb` export does, and a `meshes`
set (phase 9: the default look of a zombie, not every part). Changing how
pictures are drawn: bump `index.build.THUMB_VERSION`, and the next build redraws them.

### `dr2kit/catalog/` (phase 8)
- `groups`: the Library's rules. `groups.toml` (data) lists the groups by section, each
  with the kinds and path globs it takes, how it splits into sub-groups (`sub_path` /
  `sub_name` regex, `sub_role` for textures) and friendly labels (`[[label]]` regex
  rules, `[names.<group>]` single names, per game with `cz:`/`cw:`). `catalog()` loads
  it (unknown keys are an error, so a misplaced line can't be ignored), `Catalog.place()`
  gives an asset's group, sub-group and label; `check(con, game)` is the count gate
  behind `dr2 library --check`.
- `export`: `plan(rows, out, game)` decides where each asset goes (`<out>/<game>/<group>/
  <sub>/`, name clashes get the parent archive's name), `group_rows()` resolves a group,
  sub-group or section name, `Exporter.run(jobs, progress, cancel)` writes them: a model
  folder (`.glb`, `textures/*.png` + `textures.txt`, `skeleton.glb`, `info.txt`), WAV,
  MP4, `.bcs.json`, PNG or the raw file. Each file is written to `*.part` and renamed, and
  existing files are skipped, so an export resumes where it stopped. Phase 9: the
  `Exporter` takes a look (`variant`) and a `mode`; models get every part organised by
  default, `textures/colours/` holds each colour choice baked, and `info.txt` lists the
  detail levels and the variants.
- `prefabs` (phase 11): `prefabs.toml` (data: per prefab its file kind, anchor key, the
  example block per game, an item swap, whether it was checked in game), `load()`,
  `place(editor, prefab, game, script, at, yaw)` (copies the example, `moved()` shifts
  every position near the anchor and turns facings, adds it through the `LevelEditor`),
  own prefabs `save_own` / `read_own` / `load_own` (`.dr2prefab` JSON in `own_folder()`).
- `weapons` (phase 13): the weapon wizard's data. `weapon_kinds.toml` → `kinds(game)` /
  `kind(id)` (`Kind.template(game)`: the game weapon a kind starts from);
  `effects.toml` → `names(game)` (the executable's effect table, number = index + 1;
  `tools/effect_table.py` made and checks it), `effects(game, items_doc)` (`Effect`:
  group by name words, `loops` / `size` read from the name, what was checked in game,
  `used_by` from `usage(items_doc)`), `effect_number(game, value)` (a number or a name),
  `elements()` and `slots()` (the keys measured in game).
- `sample_sword` (phase 13): `sample_sword_glb()`, a sword made of boxes (three
  materials, one picture made in code) to try the wizard with and to test with.
- `level_export` (phase 10): `export_level(tree, game, level, out, zones=, script=,
  items=, markers=, whole=, lod=)` writes `<out>/<game>/<level>/`: one `.glb` per zone
  (or one for all, `whole`), `text/` (the level's text files) and `info.txt`; resumable
  like `export`. `level_glb(tree, game, L, zones, ls)` is one file in memory (the
  Blender add-on's *Import zone* uses it): per zone a group (`extras.dr2_layer = "zone"`)
  holding Buildings (`level.zone_glb`), Items and doors (`level.things_glb`) and Markers
  (`add_markers`: spawn and map points as empties, areas / triggers / sound boxes as
  outlines, the nav mesh as a mesh, each group with its `dr2_layer`). `gltf.Assembler`
  gained `empty`, `lines` (LINE_LOOP primitives) and `mesh` for them.

### `dr2kit/mods/` (phase 2)
- `manifest`: `Mod.load(folder)` reads `mod.toml`; `Mod.files()` lists `replace/`;
  `create()` makes a new mod folder.
- `build`: `classify()` checks every override against the game and returns a plan (or
  one `ModError` listing every problem: unknown path, not a texture, conflicts).
  `build()` groups overrides by file on disk, runs `patch_archive()` down each vpath
  (re-encoding compressed entries via `BigEntry.set_data`), writes whole files, then
  `verify()` reads every override back through a fresh `AssetTree`. `base_dirs` makes
  it patch a recomp's `game_patched` copy instead of the shipped file.
- `audio` (phase 5): `build_audio()` turns `replace/<sound>.xma.<wav|ogg|flac|mp3>`
  overrides (kind `audio`) into `dr2kit_audio/`: one fitted WAV per XMA stream and
  `substitutions.txt` listing every packet's fingerprint and output position;
  `shared_packets()` scans every sound of the game so packets that occur elsewhere are
  marked continue-only; `verify_audio()` reads it all back. No game file changes.
  Design: [`recomp-integration.md`](recomp-integration.md#audio-substitution).
- `build.plan_mods(mods, game, tree)` → `ModPlan`: the overrides that apply, what lost
  (`shadowed`: two mods replace one asset or string id, the higher priority wins) and
  notes. Also refuses files the game digest-checks (`Profile.digest_checked`). String
  overrides (`.bcs.json`, kind `strings`) merge by id; `_apply_strings` applies them in
  priority order. `classify()` is `plan_mods(...).planned`.
- `library` (phase 6): `ModLibrary(folder)`: `entries()` in load order (lowest priority
  first; folders not in `modlist.toml` come last, off, marked new), `active(game)` (the
  switched-on mods with priorities set from the order), `plan`, `install` (folder or
  zip, refusing zip entries that escape), `remove`, `enable`, `move`; `pack(folder)`
  zips a mod; `default_library()` / `set_default_library()` (user config `[mods]`).
  Phase 7: `link(folder)` (a mod that stays where it is: `path` in `modlist.toml`;
  `remove` only forgets it), `create(name)` (a new mod inside the library),
  `sets` / `save_set` / `use_set` / `delete_set` (`modsets.toml`), `last_changes` (what an
  update changed), and `pack` writes `<id>-<version>.dr2mod`. `manifest.Mod` gained
  `preview`, `preview_path`, `readme` and `save()` (writes `mod.toml` back). Phase 13:
  `Mod.local_only` (`local_only = true`), which `pack` refuses.
- `formats/shaderbank.py` (phase 15): the shader banks' descriptions: `Description`
  (`.sdo`: passes naming programs by hash, `programs()`), `ParamFile` (`.pdo` /
  `.vdo`: `Param`s with their per-game numbers and sliders), `StringTable`
  (`strings.bin`, `add`), `registry(tree)` (name → number), `census` (every file of a
  game, byte for byte; `census.check_shaders`).
- `convert/crossgame.py` (phase 15): `table()` reads `profiles/crossgame.toml` (written
  and checked by `tools/crossgame_table.py`: each program's zombie type and level tables
  found by their pointer arrays and the code that builds their address, the script
  classes the other game uses that a program doesn't name, each game's shader
  descriptions); `zombie_types`, `level_slots`, `empty_level_slots`, `unknown_classes`;
  `source_tree(game)` opens the game a recipe copies from, or says the mod needs it.
  `fit_scenes(data, game)`: scenes of the other game made right for `game`'s program
  (Case Zero's needs `_BONEHIERARCHY_`, profile `scene_hierarchy`; written from the node
  records by `formats.scene.Skeleton.hierarchy_pairs`), run by `newitem.build_copy` on
  every recipe with `"from"`.
- `convert/shadercarry.py` (phase 15): a model of the other game drawn with its own
  game's shaders. `used_shaders(pack)` (descriptions from every `UsedShaders.txt`, pixel
  shaders from every value set), `plan(src_tree, dst_tree, src, dst, sd, ps)` → `Carry`
  (old → new hash per kind, `new_name`: a crc of game/kind/hash, low 5 bits clear, free in
  both games; a program is shared only when it and its `.vdo`/`.pdo` are byte-identical),
  `recipes(carry, dst_tree)` (the `add/data/shaders/<bank>/<new>.<ext>.copy.json` files),
  `build_entry` (a brought entry at build time: a description's hash and programs
  renamed, a `.pdo`'s parameter numbers from `number_map`, a `.vdo`'s hash),
  `convert_pack` (`UsedShaders.txt`, `0x3C`/`0x3F` commands, value sets' pixel shader).
- `mods/importitem.py` (phase 15): an item of the other game. `plan(src_tree, dst_tree,
  src, dst, item)` → `Plan`: every key of the block and its children resolved
  (`Resolution`: kept / brought / renumbered / dropped, or `unresolved`), the closure of
  items it names, recipes (pack with `"shaders"`, move bank, sound banks, card pictures,
  shader bank entries, effects the target lacks into free slots of its table with their
  particle pictures: `_bring_effect`, `mod_effects`; `PropAudioType` cut to the target's
  bits, `_Game.audio_bits`; keys naming a dropped child left out), text copies; `write` (blocks into `items.txt.edits.json`,
  recipes, `.bcs.json` `"copy"` in every language, `[requires] games`,
  `sources/imported.json`); `import_item`; `census` (every item both ways, `dr2 census
  --import`). Studio: `studio/import_dialog.py` (*Other game's items…*). The build side:
  `newitem.build_copy` reads `"from"` (`crossgame.source_tree`; an effect then in the
  target's layout, `formats.effect.Effect.as_version`; a picture copied as it is), `"shader"` and
  `"shaders"`; `build._copied_strings` makes a `.bcs.json`'s `"copy"` texts; the
  profiles' `preload_evict` lists the seven shader banks.
- `mods/importzombie.py` (phase 15 step 4): a zombie type of the other game. `plan(src_tree,
  dst_tree, src, dst, type, slot, levels, taken, sets_text)` → `ZombiePlan`: the slot
  (`empty_slots`: the target's type table names with no model shipped; the same name first,
  then one the source game doesn't name), the model recipe (renamed to the slot, its
  shaders `shadercarry`), the `cZombieClassItem` keys, the `cZombieBehaviourItem` blocks
  the target lacks, the load sets with `costs` and the `budget` warning; `write` (also
  mirrors `zombiesets.txt`'s edits into `persistent_filecache.big`'s copy), `import_zombie`,
  `mod_slots`, `census`. CLI `dr2 mod import-zombie`. The build's level check counts the
  zombie models mods add (`build.plan_mods`: `facts.zombie_types`).
- `requires` (phase 15): what a mod needs. `Mod.requires` is `[requires]` as written
  (keys checked by `manifest._requires_table`); `infer(mod)` → `Requirements` (games,
  play, sources = games its recipes copy from via `"from"`, mods with version specs,
  saves, coop, toolkit; the modder's keys win); `check(req, target, switched_on)` lists
  what this computer lacks (a build for one game needs it plus `sources`); `to_json()` /
  `to_text()` are `requirements.json` / `REQUIRES.txt`, written into every `.dr2mod` by
  `library.pack` and into `dr2kit-build.json`; `content_hash` ignores those generated
  files; `summary` feeds Studio's mod manager and Install window. `build.plan_mods` calls
  `check` first and refuses (with every reason) a mod whose needs are missing.
  `dr2 mod info` prints it.
- `deploy`: `deploy(build, target)` copies files and records them in
  `dr2kit-deployed.json`; `undeploy(target)` removes exactly those. `recomp_folders()`
  names `game_mods` / `game_patched` / `game_kbm` / `game_bootskip` next to a game root.

- `preview` (phase 10): `Preview(game, root, mods, base_dirs=)` (or
  `Preview.for_play(game)`: the mod library's switched-on mods over the recomp's
  `game_patched` copies, like Play) plans the mods once, drops the ones that fail their
  check (`problems`), and makes the replacement bytes with `build.new_bytes` (cached in
  memory and in `<cache>/preview/`). `Preview.tree()` is a `ModdedTree`: an `AssetTree`
  whose archives are patched as they are opened (overridden entries get the replacement,
  archives holding overrides get their nested archives patched, stored), so every reader
  sees the mods. `changed(vpath)` names the mods that change an asset, `stamp(vpaths)`
  keys the Maps tab's zone files. `build.level_texture_copies` (same phase): the other
  identical copies of a level texture in its zone, which `plan_mods` changes too.

### `dr2kit/studio/` (phases 2-3)
DR2 Studio; see [`studio.md`](studio.md). `model_view.py` is the 3D view (phase 3),
`audio_view.py` the audio view (phase 5: `Waveform`, `AudioViewer`, `playback_bytes`
mixes 5.1 to stereo for listening). Phase 6: `text_view.py` (`TextEditor`: edit a text
file into the open mod, *Changes* shows a diff; `StringsViewer`: a bank as a filterable
table, edits go into the mod's `.bcs.json`), `video_view.py` (`VideoViewer`), and
`mod_manager.py` (`ModManager`, the library window). Phase 8: `library_view.py`
(`LibraryView`, the Library tab; `run_export`, an export with a progress bar and Cancel
in a worker thread). Phase 9: `variant_panel.py` (`VariantPanel`: slots, on/off parts,
prop states, colour choices with swatches, the detail levels, Default / Random / Show
everything); the window keeps each model's look (`MainWindow.looks`) for the 3D view,
Export .glb (as shown), Export all and Open in Blender; `viewer.js`'s `dr2.setShown`
hides parts without reloading, a colour change re-bakes and reloads keeping the camera.

## Tests

`tests/conftest.py` has `make_archive()` (build a synthetic archive in one line) and
the `game_root` fixture (skip with a reason when a game is absent). One test file per
module; `test_gamedata.py` holds the real-data checks. See [`testing.md`](testing.md).

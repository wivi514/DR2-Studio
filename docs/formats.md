# File formats

Status key: **✅ cracked** (verified against an oracle or census) · **🟡 partial** · **❓ unknown**.
"Verified" names the check. Unless stated, facts come from Case Zero and still need a
Case West census before they count as rules (CLAUDE.md rule 7).

| Format | Where | Status | Notes |
|---|---|---|---|
| `.big` container | everywhere, nested (up to 3 levels) | ✅ read + write | `dr2kit/container/big.py`. Every archive of both games round-trips byte-identically (phase 1 census, below) |
| LZX compressed entry | inside `.big` | ✅ decode + encode | `dr2kit/container/xcompress.py`, `lzx/`. Every compressed entry of both games decodes (two independent decoders agree) and re-encodes |
| `.bct` texture | loose, inside `.tex` | ✅ read + write | `dr2kit/formats/bct.py`, `convert/texture.py`. Every texture of both games decodes and re-encodes to its exact bytes; flags byte bits 0x04/0xE0 and header word 0x0C still unexplained (preserved) |
| `.tex` texture pack | next to every model `.big` | ✅ | a `.big` whose entries are `.bct`, named without extension |
| `.scv` value set | `<model>.big/valuesets.big` | ✅ read | `dr2kit/formats/shader.py`: a material's pixel-shader constants (colours of zombie clothing…), by register; names from the shader's constant table. All 674 (CZ) / 819 (CW) parse |
| shader constant table | `.po` / `.vo` in `shaders/*.big` | ✅ read | `formats/shader.constant_table`: name → register (D3DX constant table, as XenosRecomp reads it) |
| scene (model / skeleton) | `models/**/*.big`, `skeleton/*.big`, props, environments | ✅ read + write | `dr2kit/formats/scene.py`, `vertex.py`. Every scene of both games parses and every draw decodes; buffers and bone palettes checked against the running game; exports to glTF. **Written back** (phase 4): every chunk rewrites identically, `.glb` → model, new meshes and rigs; checked in game |
| `.xma` audio | `audio/*.big` (streamed), `streamedassets.big/fx_*.big` | ✅ read; replaced by PCM substitution | `dr2kit/formats/xma.py`, `convert/audio.py`. Two shapes: RIFF XMA2 files (fx banks) and raw packets whose format is in `audio/cache.big`. Every sound of both games decodes to its stored length (phase 5 census, below). No XMA encoder: mods replace sounds through the recomps (§Replacing sounds) |
| `cache.big` stream tables `$GIB` | `audio/cache.big/<bank>.$$$` | ✅ | `xma.StreamTable`: rate, channels, loop of every raw stream, keyed by the case-kept name hash |
| `.sfx` sound effect | next to the sounds in `fx_*.big` | ✅ text | `dr2kit/formats/audioscript.py`: `cSoundEffect` with one `cSfxTrack` per layer; `Sample` = the bank's `.xma` (or a sub-`.sfx`) |
| audio scene scripts `.txt` | `audio/Prologue.txt` (CZ), `audio/*.txt` + `scenegraph.txt` | ✅ text | `cAudioScene` / `cAudioJukebox` tree, `Asset = "music.big/<name>"`. **CZ's `Prologue.txt` is digest-checked by the executable: an edited copy crashes the game** |
| `.bcs` string bank | `frontend/str_<lang>.bcs` | ✅ read + write | `dr2kit/formats/bcs.py` (§Strings). All 16 banks of both games re-write byte-identically (census); `.bcs.json` mod overrides change strings by id; a changed string checked in game in both recomps |
| `.bcf` font | `system/**` | 🟡 | 9 of 11 in CZ and 6 of 11 in CW are plain `.big` archives (read by the census); the rest start `04 03 02 01`, an unknown sibling container ❓ |
| `.anm` animation | `anim/**` (`default.big/<part>.big`), weapon banks `streamedassets.big/anm_<bank>.big` | ✅ every key read | `dr2kit/formats/anim.py` (§Animations): header, track table, key mask and **every key** of every `.anm` of both games, read as the game's decoder reads them, to the file's last byte (census `--anims`); the rig from the skeleton id. Played in Studio and exported as glTF animations (`convert/holding.py`). The idle per item kind comes from `sgraph.txt` |
| ragdoll `.dat` | `skeleton/*_ragdoll.dat` | ❓ | Havok likely (`hkp*` RTTI in the XEX) |
| shader banks `.vo/.po/.vdo/.pdo/.sdo/.scv` | `shaders/*-{vs,ps,vd,pd,sc,sd,ss}.big` | 🟡 | `.vo`/`.po` are standard 360 D3D shader containers (`10 2A 11 01`, XenosRecomp translates them); `.sdo` = a shader name's permutations (`5cef4d20.sdo` → `ProtoSkinnedClothRGB`). `.sdo`, `.pdo`, `.vdo`, `strings.bin` ✅ read and written (`dr2kit/formats/shaderbank.py`, phase 15, §Across the games: shader banks). Models carry their **own** vertex declarations, so the decoder doesn't need `-vd.big` (phase 0 guessed it did) |
| mission / data `.txt`, `.csv` | `datafile.big`, CW loose `.csv` | ✅ text | engine scripting; edited for co-op in the CZ recomp |
| weapon blocks, effect numbers | `items.txt`; a table in the executable | 🟡 | elements (shock, fire, freeze) measured in game; effect numbers = 1-based index into the executable's effect table (§Weapons) |
| `.bik` | **CW only**, `data/movies` | ✅ read (Bink) | `dr2kit/convert/video.py` through PyAV: all 10 movies decode, every frame and the sound (`census --audio`); export to `.mp4`. Replacing one needs a Bink encoder (§Movies) |
| level zones (`zonelist.big`, `ZONE_ORGANIZATION.big`) | `models/environment/<level>/` | ✅ read, edited | where each level piece is placed: 208-byte records, placement maths confirmed, written back identically; a few tail bytes unknown; pieces hidden, moved, turned, resized and copied by mods, checked in game (§Levels, "Piece edits", `formats/level.py`, `formats/pieceedits.py`) |
| level text files (`<level>.txt`, `waypoint_*`, `nm_*`, `fe_map_*`) | `datafile.big` | ✅ text | placed items, doors, spawn points, zombie areas, triggers, the navigation mesh, the in-game map; read losslessly, every item resolved to its model (§Levels) |
| zone collision `MERGED_COLLISION.big` | every zone | ✅ read, moved | Havok triangle meshes, placed by their piece; 5 of 1,514 shapes' place unknown; a shape can be moved or sent away (its search tree's origin), not turned, checked in game (§Levels, "Collision", "Piece edits", `formats/collision.py`) |
| digest list | the XEX's `Digest` resource | ✅ | files the executable checks; mods can't touch them (§Digest-checked files) |

## `.big` container

Full history of how it was cracked: `../Dead_Rising_2_Case_Zero_Xenon_Recomp/docs/big-archive-format.md`.
Implemented by `dr2kit/container/big.py`, whose docstring repeats the facts the code
relies on.

```
LE header (0x18 bytes): magic 06 05 04 03 | data_start | total_size | entry_count | 0x18 | names_offset
LE index, 28 bytes/entry: name_offset | hash | size (stored) | size2 (uncompressed) | data_offset | flags | compression
names: NUL-terminated, variable length, read from each entry's name_offset
payloads: from data_start on, in index order, each aligned (zero padding in between)
```

Verified over **every archive of both games, nested ones included** (`dr2 census`,
2026-10-08), unless a line says otherwise:

- **Layout.** `header_size == 0x18`, `names_offset == 0x18 + 28·count`, and
  `total_size` equals the data length, in every archive. Names sit back to back in index
  order and `data_start` is exactly the end of the last name (no padding). Payloads are
  in index order and never overlap; there are no bytes after the last payload.
- **Padding.** Every gap between payloads is zero bytes, and every gap is explained by
  aligning the payload to some power of two from 2 to 0x800 (no gap is unexplained).
  Which power depends on the archive and the entry (0x800 for audio banks and model
  packs, 16-32 for vertex data in scene chunks, 4 for most scene chunks). The writer
  keeps, for each entry, the largest power of two (≤ 0x800) dividing its original offset.
  That is never smaller than the real requirement, and on an unedited archive it lands
  every payload where it was (`big.py` docstring has the argument).
- **Entry order: no rule** (phase 13 census, CZ, every archive to two nesting levels:
  3,717 with two entries or more). 1,379 are in lower-case name order, 489 in name *and*
  hash order, 112 in hash order only, 13 in upper-case name order only, 1,724 in **no**
  name or hash order (the animation packs, e.g.
  `data/anim/battle/army.big/fullbody.big`; a model pack lists `leadpipe_LOD.tex` before
  `leadpipe.big`). *Retracted:* "every archive of both games is sorted by lower-case
  name" (the mod builder's docstrings, phase 11). The game finds entries by name hash,
  so a new entry's place doesn't matter: the builder still puts it in name order, and
  such entries load (phases 11 and 13).
- **`compression` (the last index word; `resv` in the recomp's tools)** is `2` on every
  LZX-compressed entry and `0` on every stored one; no other value occurs. For stored
  entries `size == size2` always. mariokart64n's MaxScript says `1` means zlib on PC;
  never seen on 360, but the reader supports it.
- **`hash`** is the engine's string hash (`dr2kit/hashing.py`) **of the lower-cased
  name**, for all 124,932 (CZ) + 172,322 (CW) entries. Recompute it for new entries.
- **`flags`** is the entry's **declared alignment**: every payload of both games starts
  at a multiple of it (123,534 CZ + 170,360 CW entries with data, measured 2026-10-11), and
  a new entry declared `0` made the game wait forever for it (an added item pack in
  `streamedassets.big`, CZ, in game). Kept on write; a new entry takes the value of its
  siblings with the same extension (`BigArchive.sibling_flags`). *Retraction:* this page
  said "meaning still unknown" until phase 11. Values and where they occur:

  | flags | CZ | CW | on |
  |---|---|---|---|
  | `0x4` | 94,475 | 126,271 | scene chunks, `.xma`, `.anm`, `.sfx`, `.tex`, `.pdo`, `.big`, `.txt`, … (the common case) |
  | `0x10` | 10,967 | 20,865 | textures inside `.tex` packs (named with or without `.bct`) |
  | `0x20` | 12,216 | 16,065 | extension-less scene chunks |
  | `0x80` | 2,844 | 2,966 | shader objects `.po` / `.vo` |
  | `0x100` | 1,640 | 1,837 | nested `.big` |
  | `0x800` | 2,790 | 4,318 | entries of the top-level banks: `.xma`, `.big`, `.bct`, `.tex`, `.txt`, `.csv`, … |

- **Nesting** goes 3 levels deep (`npcs.big` → `boss_mechanic.big` → `persistent.big`).
  Nested archives are also stored **compressed**: most of `npcs.big`'s models, and
  `preload4.big`'s `fecmn.big`. A nested archive is found by its magic after decompression.
- **Duplicate names exist, but are rare**: 12 entries in 2 archives (CZ), 44 in 8 (CW):
  `zonelist.big` ×7 (CZ) / ×19 (CW) inside `persistent_filecache.big`, and a few CW texture
  packs listing the same texture twice. The toolkit addresses entries by **position**
  (vpaths add `#1`, `#2`… to later copies). *Retraction:* this page used to give "a scene
  holds several `Combined Vertices` entries" as the example; those differ by a number
  and are not duplicates. (*Correction, phase 3:* the number is the buffer's stride,
  `Combined Vertices 12`, not a counter; see §Scene container.)
- No entry name contains `#`, `/` or `\`, starts with `@`, or is invalid as a Windows file
  name (`<>:"|?*`, control characters, a trailing dot or space, `CON`, `NUL`, …). So
  vpaths and `dr2 extract` are safe on every OS. The census checks this.
- **Extensions**: only 1-3 letter extensions are real; scene node names contain dots
  (`dummy01.l_thigh`).

### Census totals (2026-10-08, `dr2 census`)

| | Case Zero | Case West |
|---|---|---|
| `.big` files on disk | 146 (12,481 entries, 1,671 compressed: matches the recomp's `big_list`) | 154 (13,833 entries, 1,886 compressed) |
| other archive files on disk | 42 `.tex` (569 entries, 270 compressed) + 9 `.bcf` | 42 `.tex` (736 entries, 240 compressed) + 6 `.bcf` |
| archives incl. nested (depth 0/1/2/3) | 7,413 (197 / 3,952 / 1,980 / 1,284) | 8,017 (202 / 4,200 / 2,263 / 1,352) |
| entries at all depths | 124,932 (1,398 empty) | 172,322 (1,962 empty) |
| compressed entries at all depths | 10,754 (564 MB stored → 1,196 MB) | 21,354 (798 MB → 1,892 MB) |
| round trip identical | 7,413 / 7,413 | 8,017 / 8,017 |
| unparsed | 0 | 0 |

Entry extensions (CZ / CW): none 82,414 / 112,317 (scene chunks, textures in `.tex`),
`.xma` 8,916 / 11,735, `.bct` 6,060 / 18,254, `.anm` 5,792 / 6,271, `.big` 5,031 / 5,458,
`.sfx` 4,745 / 5,194 (text), `.tex` 2,850 / 3,201, `.pdo` and `.po` 2,558 / 2,674 each,
`.txt` 1,789 / 1,849, `.scv` 972 / 1,349, `.sdo` 446 / 462, `.vdo` and `.vo` 286 / 292
each, `.jaw` 159 / 222, `.fx` 30 / 27, `.csv` 20 / 29, `.ini` 12 / 12, `.bin` 4 / 4, plus
singletons (`.pos`, `.dat`, `.new`; CW: `.loc` 3, `.fx1`, `.gun`).

### Compressed entry stream (BE)

```
u32 uncompressed_size (== size2) | u32 window (0x8000)
repeat until the entry ends:
    u32 chunk_length                (bytes after this word, up to the next chunk)
    u8  0xFF | u16 unc_len (<= 0x8000) | u16 comp_len
    comp_len bytes: one independent LZX stream
    padding up to chunk_length      (always 5 zero bytes)
```

*Correction:* this summary used to omit the `u32 chunk_length` word; the recomp's
`big_decompress.cpp` had it right.

Verified on every compressed entry of both games (`dr2 census --reencode --python-lzx`):
the window is always 0x8000; the chunk lengths always add up to `size2` with nothing left
over; the padding is always 5 zero bytes (41,474 chunks in CZ, 67,920 in CW); the
Intel E8 translation bit is never set. Two independent decoders agree on every entry:
libmspack (native) and the toolkit's pure-Python one, which was written from the format
description.

**An empty compressed entry is just `00 00 00 00`** (the size word; no window, no
chunks). 27 of these are in CW's `data/preload4.big` (`audiomixer.txt`, `curves.txt`,
`glassbroken.big`, …, all `size2 == 0`, `flags 0x800`); CZ ships the same 27 entries
with content. Found by the CW census, which first reported them as unparseable.

**Block types used by the game's own encoder** (first block of each chunk):

| LZX block type | CZ | CW |
|---|---|---|
| 1 verbatim | 5,145 | 8,118 |
| 2 aligned offset | 36,090 | 59,388 |
| 3 uncompressed | 239 | 414 |

**Type 3 (uncompressed) is the game encoder's choice for small or hard-to-compress
chunks.** Of CZ's 239 type-3 chunks, 185 are under 1 KB (mostly the short last chunk of
an entry, e.g. the 48-byte tail of `cc_03.bct`). For 49 of them the toolkit's encoder
would have produced a smaller verbatim block, so the game's rule is not simply "use type 3
when compression would grow the data"; its exact threshold is unknown. No type-1/2 chunk
in CZ is larger than its input. Layout of a type-3 stream: the 28 header bits padded to a
16-bit word, then R0, R1, R2 as LE u32 (the shipped ones carry left-over encoder state
such as 12, 4, 1), then the raw bytes (plus one pad byte if the length is odd). *Note on an earlier belief:* the CZ
recomp's `gen_pc_options.py` concluded the game's decoder "plausibly never implemented"
type 3, because one of its type-3 test streams crashed the game. Shipped type-3 chunks sit in
archives the game reads at boot (`datafile.big`'s `zombie_effects.txt`, `preload4.big`'s
`commoncolourcubes.tex`), so the game's decoder does handle type 3. That
crash also had other suspects (the same streams lacked the 5-byte padding, which the
game's read-ahead needs). The toolkit's encoder uses type 3 only for chunks whose verbatim
block would be at least as large as the type-3 form (so less often than the game does). Whether the game accepts our
re-encoded entries is the phase 2 in-game gate.

The game rejects stored entries where it expects compression, and crashed on degenerate
streams from the recomp's early encoders. Re-encode with the real encoder, then decode
the result and compare (`xcompress.compress_entry` does both). The toolkit's encoder
(greedy LZ77, verbatim blocks) produces streams 1.07× (CZ) / 1.07× (CW) the size of the
shipped ones.

## Textures: `.tex` and `.bct`

Implemented by `dr2kit/formats/bct.py` (header, layout, tiling) and
`dr2kit/convert/texture.py` + `dxt.py` (pixels). **✅ cracked (phase 2, 2026-10-08):**
every texture of both games parses, decodes, and re-encodes to its exact shipped bytes
(census below).

A `.tex` file is a `.big` holding one or more textures, usually named without extension
(e.g. `goretech_head_combine_cm`); textures also appear as `*.bct` entries in other
archives and as 13 loose files on disk. Only the first three bytes `05 01 01` identify a
texture (retraction below).

### Header: 48 bytes, big-endian

It is **not** a GPU fetch constant (the phase 0 guess): it is the engine's own compact
description.

```
0x00  05 01 01         magic
0x03  u8   flags        bit 0x02 always set; 0x08 = cube map; 0x04 = alpha? (table below)
0x04  u16  width, u16 height
0x08  u8   format       engine code: 08 DXT1, 0A DXT5, 1B DXN, 00 A8R8G8B8, 21 L8
0x09  u8   0x23 (every CZ texture) / 0x24 (all but 6 of CW's 23,120): writer version? (the
           toolkit gives a texture brought from the other game the target's value,
           profile texture_version; whether the game cares is not known: 2026-10-13)
0x0A  u8   mip levels   stored levels, base included (1-10)
0x0B  u8   bits per pixel (4, 8 or 32; always agrees with the format)
0x0C  u32  unknown      differs per texture, low 5 bits always 0; not the name hash,
                        not CRC-32 of the name (checked); preserved on write
0x10  u32  0x18         in every texture
0x14  u32  0
0x18  u32  0x30         payload offset
0x1C  u32  payload size
0x20  u32  0x30 + payload size = file size (every texture)
0x24  u32  faces - 1    5 on cube maps, 0 otherwise
0x28  u32  0, 0x2C u32 0
0x30  payload           tiled; byte order per format (below)
```

| Format code | Format | Unit | Stored byte order | CZ | CW | Verified by |
|---|---|---|---|---|---|---|
| `0x08` | DXT1 (BC1) | 4×4 block, 8 B | 16-bit words BE | 10,073 | 18,910 | decoded images (faces, clothing) |
| `0x0A` | DXT5 (BC3) | 4×4 block, 16 B | 16-bit words BE | 1,524 | 1,564 | decoded UI icons with alpha |
| `0x1B` | DXN (BC5, two channels) | 4×4 block, 16 B | 16-bit words BE | 594 | 2,623 | decoded `_nm` maps look like normal maps |
| `0x00` | A8R8G8B8 | texel, 4 B | 32-bit words BE (A,R,G,B) | 37 | 36 | `cc_00.bct`, an identity colour LUT: R = x mod 32, G = y, B = slice, mean error 0.5 |
| `0x21` | L8 (one channel) | texel, 1 B | as is | 9 | 6 | font atlases decode to readable glyphs |

Normal maps are not all DXN: 583 `_nm` textures in CZ (325 in CW) are DXT1.

### Layout of the payload

Every texture is **tiled** with the Xbox 360's `XGAddress2DTiledOffset` (the CZ recomp's
`Tiled2DOffset`), with the row pitch rounded up to 32 units. Regions:

1. **Level 0**, then each mip level, each region starting on a 4 KB boundary and taking
   its whole tile footprint: `align(pitch × align(rows, 32) × unit bytes, 4096)`. Level
   *L* ≥ 1 is sized from the *next power of two* of the base size, shifted by *L*
   (Xenia's `GetGuestTextureLayout` rule). No texture with mips has a
   non-power-of-two size (351 NPOT textures in CZ, 518 in CW, all single-level), so this
   rule is only exercised on powers of two.
2. **Packed mips.** Once a level's shorter side is ≤ 16 texels, that level and all smaller
   ones share one 32×32-unit tile, each at a fixed offset (Xenia's `GetPackedMipOffset`):
   16, 8, 4 texels across for square and tall textures, down for wide ones, then the long
   side's size shifted down. A small texture's **level 0 is itself packed**: a 16×16 DXT1
   base sits at block (4,0), a 16×8 DXN base at block row 4. *Verified* by locating the
   non-zero blocks of real 4×16, 8×32, 4×8 and 16×8 textures: they sit exactly at those
   offsets.
3. **Cube maps**: each level stores its six faces one after another (face order +X, −X,
   +Y, −Y, +Z, −Z assumed from D3D), each a whole 4 KB-aligned region. *Verified*: for
   every cube map, each face's level 1 matches its level 0 downsampled (mean error 0-13 of
   255; a wrong layout gives noise).

**Payload size model** (`bct.model_data_size`): the regions above, with the *last*
region of a 2D texture cut to the 4 KB page that holds its last used unit. It matches
12,186 of 12,237 CZ textures and 23,038 of 23,139 CW ones exactly; the rest are **larger**
than predicted, by up to one tile footprint, and never smaller. Every one of those 152 is
either a non-power-of-two size (40×40, 160×160, 288×144 …) or a tall, narrow packed
texture (4×16, 8×32, 4×8). Which rule makes the game's exporter keep the whole last tile
for those is **unknown**. It doesn't matter for reading (each level is addressed from the
layout, and the reader checks that every unit fits the payload) or for replacing (the
toolkit keeps the original payload size).

### Flags byte (byte 3)

**Retraction (2026-10-08):** "magic `05 01 01 E2` on every loose `.bct`" was based on the
few files the recomp checked. The census found that **the 4th byte varies**, in loose files
and `.tex` packs alike. Only `05 01 01` identifies a `.bct`. Over every texture (12,224 in
CZ, 23,126 in CW; `dr2 census`, "texture (.bct) header byte 3"):

| byte 3 | CZ | CW |
|---|---|---|
| `E2` | 9,953 | 20,047 |
| `E6` | 1,831 | 2,226 |
| `06` | 177 | 142 |
| `62` | 140 | 403 |
| `EA` | 56 | 228 |
| `02` | 25 | 13 |
| `66` | 16 | 7 |
| `C2` | 10 | 16 |
| `C6` | 9 | 10 |
| `42` | 3 | 31 |
| `82` | 2 | 2 |
| `A2` | 2 | 0 |
| `A6` | 0 | 1 |

11 `.bct` entries
in CZ's `streamedassets.big` weapon models are empty (0 bytes).

What is known now (phase 2 census, counts for CZ / CW):

- `0x02`: set on every texture of both games.
- `0x08`: **cube map**, verified: set exactly on the textures whose word 0x24 is 5 and
  whose payload holds six faces (57 / 229, flag value `EA`).
- `0x04` (counted over textures inside archives): set on every DXT5 but one (1,518 of
  1,519 / 1,558 of 1,559), on 456 / 793 DXT1s, 35 / 15 DXNs, 15 of 35 / 14 of 34
  A8R8G8B8 and on every L8. *Hypothesis:* "has alpha" (DXT1 can carry 1-bit alpha).
  Unconfirmed.
- `0xE0` (bits 0x20, 0x40, 0x80): all three are set on 92% of textures. All three are
  clear on most front-end (UI) textures and on the 4×4 defaults in `preload4.big`.
  *Hypothesis:* addressing (wrap vs clamp) or filtering per axis, since UI art is clamped.
  Unconfirmed.

The toolkit preserves the byte on write, like every field it doesn't understand.

### Census (2026-10-08, `dr2 census --textures`)

| | Case Zero | Case West |
|---|---|---|
| textures (in archives + loose files) | 12,237 (12,224 + 13) | 23,139 (23,126 + 13) |
| parse with no problem | 12,237 | 23,139 |
| decode → re-encode → re-tile gives the identical file | **12,237** | **23,139** |
| cube maps | 57 | 229 |
| mip levels 1 / 2-6 / 7-10 | 1,291 / 6,301 / 4,645 | 2,286 / 13,914 / 6,939 |
| largest | 2048×2048 (`cine_wasps_cm`) | 2048×2048 (`glass_tube_cm400e`) |

The re-encode gate: every level of every texture is untiled, swapped to little-endian,
decoded to RGBA, encoded again with the original blocks as reference (`dxt.encode`
keeps any block whose pixels are unchanged), swapped back and re-tiled into a fresh
copy. The result must be byte-identical. That proves the layout, the byte order and the
decoders are consistent with every shipped texture; whether they are *right* is checked
by the images above and by the in-game gate.

**Role suffixes** seen (CZ): `_cm` colour (DXT1 5,197, DXT5 208), `_nm` normal (DXN 594,
DXT1 583), `_sm` specular (435), `_ne`, `_rm`, `_si`, `_no`, `_mask` (clothing tint
masks), `_det`, `_om`, `_ig`; 4,245 textures have no suffix.

Examples: `grid.bct` 128×128; `goretech_head_combine_cm` 512×512; `cc_03.bct` 1024×32 =
a 32³ colour-grading LUT unrolled into a 2D strip (A8R8G8B8); `reflection_basic` a
128×128 DXT1 cube map.

*Retraction of the phase 0 plan text* ("`.bct` header: 48 bytes … then a Xenos texture
fetch constant", ARCHITECTURE.md §Textures): the header holds no fetch constant. Format,
size and mip count are plain fields; tiling is always on and implied.

## Scene container (models and skeletons)

Implemented by `dr2kit/formats/scene.py` (chunks, skeleton, materials, meshes, draws)
and `dr2kit/formats/vertex.py` (vertex declarations and streams). **✅ cracked (phase 3,
2026-10-08):** every scene of both games parses and every draw of every model decodes
(census below), the reader's buffers, strips and bone palettes were checked against
draws captured from the running game, and the result exports to glTF for Blender
(`dr2kit/convert/gltf.py`, mapping in [`dev/gltf-mapping.md`](dev/gltf-mapping.md)).

A model (`npcs.big/chest_young_chuck.big`) or a skeleton (`skeleton/playerfullbody.big`)
is a `.big` of named chunks. **Everything is big-endian.** A skeleton file has the same
chunks with empty material arrays and no geometry, so one reader serves both. A scene is
any archive with a `SceneHeader` entry: 1,510 in CZ (1,397 models, 113 skeletons) and
1,639 in CW (1,495 + 144).

### Chunks in the scene archive

| Chunk | Size | Meaning (status) |
|---|---|---|
| `SceneHeader` | 20 | 5 words, e.g. `1, 2, 2, 0x67, 3`. **Word 3 = the number of `SceneDescription` records** (✅ every scene); word 4 often equals the material count (❓) |
| `SceneDescription` | 36·n | a 32-byte NUL-padded name + u32 kind: **2 = transform node, 0 = shape** (✅) |
| `_BONENAMES_` | 31·n | the skeleton's node names, **31 bytes each**; a name longer than 30 characters is **cut to 30** (✅, see below) |
| `<node name>` | **52** | one per node: the node record below (✅) |
| `_BONEHIERARCHY_` | 8·n | (u32 index, s32 parent) pairs: the **same pairs as the node records, in a parents-first order** (✅ every scene **of Case Zero**; equal to the records' order in characters, different in 158 CZ props). *Corrected 2026-10-12:* "every scene" held for Case Zero only: **Case West has none** (0 scenes), and Case Zero's program hangs without it (§Across the games) |
| `MatArray` | 36·n | one per material (✅ layout, below) |
| `MatTextureInfoArray` | 100·n | texture slots; name at +4 (52 bytes), a hash at +0x38 (below) |
| `UsedShaders.txt` | text | `0x5CEF4D20 : ProtoSkinnedClothRGB` lines: shader hash → name |
| `<shape> Vertices N`, `<shape> Indices N` | | a shape's own vertex streams and index buffer (characters) |
| `Combined Vertices <stride>`, `Combined Indices 2` | | vertex streams shared by every shape, **named by their stride in bytes** (`… 12` = positions, `… 8` = UVs, `… 24` = the rest); one index buffer of 2-byte indices (props, environments) |
| `persistent.big` | nested | **the mesh descriptions** (next section), plus collision (`COL_*Shape`, Havok chunks) and `_BOUNDINGBOX_` (6 floats: min, max) |
| `valuesets.big` | nested | `<hash>.scv` per material: shader parameter sets (❓) |
| `ANIM_<a>_FRAME_<f>_`, `_VERTEXANIM_<a>_`, `VA_<mesh>` | | **vertex animation** (CZ/CW `Larvae.big`): per frame 4 words (1, 1, 1, vertex count) then FLOAT3 positions; `_VERTEXANIM_0_` = frame count (191) |
| `_ATTRIBUTE_`, `_ANIMCHANNELINFO_`, `_COLLPRIMS_`, `LocatorArray`, `EFFECT_Common<N>`, `_ANIM_`, `ModelInstanceArray*`, `_ZONEINFO_`, `LightObjects`, `OccluderArray<N>`, `_SHPROBEARRAY_`, `_REV_ANIM_` | small | not used by the reader yet ❓ (the census counts them by name) |

### Node record (52 bytes) and the skeleton ✅

```
0x00 u32  node index           (== its position in _BONENAMES_, every scene)
0x04 s32  parent index         -1 = root; == own index = root of a split rig (below)
0x08 u32  flag                 1 on most records, 0 on some (❓ meaning; preserved)
0x0C f32×3 scale               (1,1,1) on all but 18 records (8 CZ, 10 CW; props)
0x18 f32×3 translation         relative to the parent, metres
0x24 f32×4 rotation quaternion (x, y, z, w), relative to the parent
```

A node's rest pose in model space is parent × local, root first (standard TRS
composition, `Skeleton.world_matrices`). *Verified:* Chuck's head comes out at
y = 1.62 m, his feet near 0, his left hand at x = +0.56; and the bone matrices the game
uploads, multiplied by this rest pose, keep these bone lengths (in-game gate below).

- **Unit quaternions** on 16,007 of 16,009 CZ records and 25,194 of 25,200 CW ones; the
  8 others belong to prop nodes that also carry a non-unit scale (a cactus, sky domes,
  a crate). The phase 0 check (3,474 records of the 76 skeleton files) still holds.
- **Split rigs.** `preload4.big`'s `femaleroot.big`, `zombiehand.big`… and some files in
  `data/skeleton/` hold one part of a rig. Their root's parent is **its own index**
  (`dummy01.root`: index 0, parent 0) instead of -1: 37 records in CZ, 30 in CW.
- **Truncated names.** `_BONENAMES_` keeps 30 characters; the node's entry has the whole
  name (`geo_pitchfork.LOC_collision_end…`). Two names can share the 30 characters
  (`…geo_carrier` and `…geo_carrier1` in `broken_ambulance.big`); the record whose
  index matches settles it.
- Coordinates: **Y up, characters face +Z with their left side at +X**, metres. That is
  glTF's convention, so the exporter converts nothing.

### Materials ✅

`MatArray`, 36 bytes per material:

```
0x00 u32 id                 1-based; records are NOT stored in id order
0x04 u32 hash               (❓ not the shader hash)
0x08 u32 slot count         its texture slots ...
0x0C u32 slot offset        ... start at this BYTE offset in MatTextureInfoArray
0x10 f32×4                  e.g. 909.1, 0.7, 0.5, 1.0 (❓)
0x20 u32 value set          name of its .scv in valuesets.big (hex)
```

`MatTextureInfoArray`, 100 bytes per slot: u32 (always 1), the texture name (52 bytes,
NUL-padded), then at +0x38 a hash that equals the sampler hash the command buffer binds
(`0x33` below) for the engine samplers (`gCascadedShadowMapTexture` = `F3AF86E0`); it
is not the engine's name hash or CRC-32 of the name. Each material owns 3-7 slots: its
own textures plus engine samplers (`gExposureTexture`, …). The texture's role comes from
its suffix (`_cm` colour, `_nm` normal, `_sm` specular, `_mask` mask; a trailing digit
is allowed: `mech_eye_cm1`). Added 2026-10-09 after the user found Case West's final
boss white in DR2 Studio: **`_dm`** ("diffuse map") is a colour map too
(`boss_commander_epi_upper_dm`, the only model using it), and environment textures
carry a **hex tag** after the role (`glass_cmda77`, `Metal_oldred_02_CM4c73`,
`showcase_glass_gray_ome00d`): 1,000+ slots in CZ, more in CW. A material with no texture
named like a colour map uses its first plain-named texture (`Raw_flesh`,
`swatch_black`), never a lightmap (`LM_`, `AO_`) or a shared reflection map
(`reflection_*`). After that, 25 (CZ) / 30 (CW) materials have no colour texture:
lights with only a self-illumination map, glass with only opacity and reflection. The
+0x38 word differs per texture name, so it can't identify the diffuse sampler. Note
also that a `_cm1` can be a weight map rather than a colour (§Materials: value sets).

**A draw names its material by id: RenderStrip word 0 = id − 1** (✅). *Found the hard
way:* phase 3 first read word 0 as a position in `MatArray`, which is right for Chuck's
parts (stored in id order) and wrong for `boss_mechanic.big` (ids 5, 4, 10, 1, 3, 11, …):
his apron wore the shoes texture. The user spotted it in a DR2 Studio screenshot
that had already been reviewed and passed as correct. With the id
rule every mesh gets its own texture (apron → `mech_apron_cm`, head → `mech_head_cm`);
the census checks that every draw of both games finds exactly one material with that id.

### Materials: value sets and colours from shader constants ✅

> **Correction (2026-10-09, found by the user in DR2 Studio):** not every material's
> `_cm*` texture is a colour map. Zombie clothing showed red, green and purple: its
> `_cm1` is a **weight map**, and the colours are shader constants. The phase 3
> exporter (and the slot-role rule above, "`_mask` tint mask") assumed otherwise.

A material's 9th `MatArray` word names its **value set**, `<model>.big/valuesets.big/
<hash>.scv` (`0xFFFFFFFF`: none). Big-endian:

```
u32 n, name (n bytes incl. NUL, then padded to 4)   "pro_zombie_cop_mtl_shirt.pdv"
u32 own hash   u32 0xFFFFFFFF   u32 pixel shader (the .po entry name, hex)   u32 count
count × { u32 2, u32 0, u32 k, u32 1, u32 register, u32 name hash, k × f32 }
```

The register is a float4 constant register of that pixel shader; the shader's own
constant table (D3DX `CONSTANTTABLE` at container word 4, the layout XenosRecomp reads)
names it. Checked: every register of the cop shirt's value set names a constant of its
shader `21b5af40.po` (`gBaseTextureColour` = c141 = (0.67, 0.62, 0.53), `gBloodColour`
= c137…). The name hash is not the engine string hash, CRC-32 or FNV of the name
(tried over every string of the shader banks). All 674 (CZ) / 819 (CW) value sets parse.

Families that replace the colour map (formulas read from the pixel shaders translated
with XenosRecomp; implemented in `dr2kit/convert/material.py`, which bakes them for
previews and `.glb`):

| Family (constants) | CZ / CW materials | Colour (`d` = the `_cm*` texture, squared = linear) |
|---|---|---|
| **pattern**: `gBaseTextureColour`, `gPattern1-3Colour` (+ `gBloodColour` on zombies) | 275 / 194 (zombie clothes, cutscene zombies, some NPC clothing such as `chest_default_mtl_tshirt`) | Σ colourᵢ × weightᵢ × dᵢ² over channels R G B A; weight = the colour's 4th value or `gBaseTextureScale`/`gPatternNScale`. `d` is sampled at `((u + so.z)·so.x, (v + so.w)·so.y)` (`gUVScaleOffset`; or `gUVOffset`/`gUVScale`): 35 / 31 materials tile it (10 × 20 stripes) or flatten it (scale 0). Blood: `a = mask.A²·mask.B²·gPackedBumpAmbBloodvis.z`, colour += `a·blood.w·(a·blood.rgb·colour − colour)` |
| **body part**: `gBodyPart1-4Colour` | 18 / 18 (LOD zombies) | `d.A` picks the part: > 0.875 none, (0.75, 0.875] 1, (0.625, 0.75] 2, (0.5, 0.625] 3, ≤ 0.5 4; colour = `d.rgb²` × part colour |
| **channel**: `gRed/Green/BlueChannelColour`, `…Saturation`, `gDiffuseTint` | 4 / 0 (Sharon's dress, Royce) | colours desaturated (`lum + (c − lum)·sat`, lum weights 0.2125/0.7154/0.0721); start `d.A²·tint`, blend to `d.G²·green` by `d.G²·green.w`, then blue, then red the same way |
| **lens**: `gLensColour` (`ProtoSkinnedLens`, `1595db80.po`; added 2026-10-09) | 4 / 17 (glasses: frames and lenses) | the texture is channels (cyan/blue/green), not a colour: colour = `1.4·d.B²·gLensColour.rgb` (before lighting and the environment reflection/refraction the shader adds), opacity = `d.G²·gLensColour.a` (frames 1.0, lenses ~0.28) |
| **hair**: `gDiffuseColourControl`, `gHairTransparencyScale` (`ProtoSkinnedHair` `ca7f0160.po`, `ZombieHair`, `ZombieHairLOD2`; added 2026-10-09) | 29 / 37 (eyelashes, some hair) | colour = `d.R²·gDiffuseColourControl.rgb`, opacity = `d.A·gHairTransparencyScale`. Katey's lash texture is pure red (255, 4, 1): red is a weight; in game the lashes are dark brown. The zombie hair shaders read the same two channels with the same constants (`cw b772f300.po` squares R explicitly); checked visually on every zombie |

~~Other value-set constants (`gSelfIlluminationColour`, `gLensColour`,
`gDiffuseColourControl`, UV and specular parameters) don't replace the colour map.~~
(Retracted 2026-10-09: `gLensColour` and `gDiffuseColourControl` do, rows above; found by
the user, who saw bright green glasses and red eyes in the Library's pictures.)
`gSelfIlluminationColour`, UV and specular parameters don't.
Checked: every material of these families bakes in both games (297 / 212); visually
on the cop (khaki shirt, olive trousers, black boots), skinny zombie, waitress, trucker,
a cutscene zombie (striped sleeves), a LOD fat zombie and Sharon's dress. Not checked
against an in-game capture; lighting, specular and the game's per-spawn colour choice
(if any) are not modelled.

### Mesh descriptions (in `persistent.big`) ✅

For each shape `<shape>` (a name like `geo_tshirtShape`, `moto_bodyShape`,
`meshSkyDome`; a render shape is one with a `RenderStrip`; `COL_*Shape` are collision):

| Chunk | Size | Meaning |
|---|---|---|
| `<shape>` | 72 | 8 words, then 7 floats: **bounding radius** (from the origin), **box min, box max** (exact min/max of the positions), then 3 words (zero on most shapes, kept). Word 2 = own vertex buffers, word 3 = vertex declarations, word 4 = own index buffers, **word 5 = number of draws**, words 6-7 = the first draw's palette (✅ every shape, phase 4); words 0-1 ❓ |
| `<shape> RenderStrip` | 28 per draw | `material id − 1`, flags (`0x3F`/`0x7F`/`0x103F`…), flags (`0`/`0x1001`/`0x02000000`), **palette first node, palette node count**, **the byte offset of the draw's packet in the command buffer** (word 5), **the packet's word count up to the end of its draw command** (word 6; one less on the 106 packets without an `0x04` end ❓). Words 5-6 found in phase 4, see §Writing scenes |
| `<shape> D3DVertexDesc N` | 12 per element | vertex declaration N (next section). Several draws can share one |
| `<shape> VDHeader` | 8 per declaration | `0, 0xFFFFFFFF` each (❓ beyond the count) |
| `<shape> CommandBuffer` | words | the recorded draw calls (below) |
| `<shape> VBHeader`, `<shape> IBHeader` | 56 per buffer | the shape's own buffers: name (36 bytes, `"<shape> 0"`), `0xFFFFFFFF`, **count, stride**, 0, 0 |
| `Combined_VBHeader`, `Combined_IBHeader` | 56 per buffer | the same records for the `Combined …` buffers (empty when shapes have their own) |

**The command buffer** is a list of words; the low byte is an opcode, the others are
arguments in the word, and some opcodes take extra words. Every command buffer of both
games parses with this table (an unknown opcode is a named error):

| Opcode | Extra words | Meaning |
|---|---|---|
| `0x0A` | 0 | starts a draw packet; **byte 1 = which `D3DVertexDesc` the draw uses** |
| `0x0B` | 0 | bind the shape's own vertex buffer: byte 1 = stream, byte 2 = which buffer (`<shape> Vertices <byte 2>`) |
| `0x0C` | 0 | bind the shape's own index buffer number byte 1 (`<shape> Indices <byte 1>`) |
| `0x28` | 1 | bind a combined vertex buffer: bit 31 set, bits 16-23 = **stride** (which `Combined Vertices <stride>`), byte 1 = stream; arg = first vertex. **Without bit 31** (`00000228`, stride 0) the stream is filled at run time: the vertex-animated larvae, whose positions come from `ANIM_0_FRAME_<f>_` |
| `0x47` | 1 | bind the combined index buffer (byte 1 = index size, 2); arg = first index |
| `0x08` | 6 | **the draw**: base vertex, first vertex, vertex count, first index, index count, 1. The word is `0x408` (or `0x308` on 13 CZ / 5 CW draws ❓) |
| `0x3C` | 1 | set the shader (hash from `UsedShaders.txt`); `0x3F` + hash closes the packet |
| `0x33` | 1 | set an engine sampler (its hash); `0x3B` + hash: a texture by hash |
| `0x16` | 2 | a hash and a float (−0.1); fence poles only ❓ |
| `0x0D`, `0x0E`, `0x0F`, `0x41`, `0x43`, `0x71`, `0x73` | 0 | render state around the draw ❓ |
| `0x04` | 0 | end of packet (upper bits vary: `fffff004`, `fffff604`…) |

So vertex *v* of a draw is stream vertex `bind first + base + first vertex + v`, and an
index *i* addresses `i − first vertex` (✅: every index of every draw falls inside its
range).

**Indices are one triangle strip per draw**, 16-bit big-endian, with strips joined by
repeated indices (`… 2 2 3 3 3 4 …`, degenerate triangles). No restart markers (`0xFFFF`)
occur. *Verified:* 4,993 of 6,954 CZ draws (7,576 of 10,548 CW) have an index count that
is not a multiple of 3; read as a list, almost every draw is full of degenerate triangles;
and the game's GPU state for these draws says primitive type 6 (triangle strip) in the
captured frame. Taking even triangles as (a, b, c) and odd ones as (b, a, c) gives
**counter-clockwise front faces**: the face normal agrees with the stored vertex normals
on 99.4% of triangles in both games.

*Retraction (2026-10-08):* the `.big` section and the phase 0 table said models hold
`Combined Vertices 0`, `… 1` "numbered" buffers and wondered whether indices were
"strips or lists". The number after `Combined Vertices` is the **stride**, and indices
are strips.

### Vertex declarations ✅

A `D3DVertexDesc` chunk is the Xbox 360 D3D `D3DVERTEXELEMENT9` array as is: 12 bytes per
element, `u16 stream | u16 offset | u32 type | u8 method | u8 usage | u8 usage index |
u8 pad`, ended by stream `0xFF`, type `0xFFFFFFFF`. The type is the **360's own
`D3DDECLTYPE`** (its low 6 bits are the Xenos vertex format). Every element of both games
uses one of these (counts of elements, CZ / CW):

| Type | Value | Use | CZ | CW | Decoding (verified by) |
|---|---|---|---|---|---|
| FLOAT3 | `0x2A23B9` | POSITION | 6,953 | 10,547 | 3 BE floats (positions inside each shape's box) |
| FLOAT2 | `0x2C23A5` | TEXCOORD 0-4 | 10,046 | 20,026 | 2 BE floats (textures land right in the renders) |
| HEND3N | `0x2A2190` | NORMAL | 6,944 | 10,492 | 10_11_11 signed normalised: x = bits 0-10, y = 11-21, z = 22-31 (unit length on every vertex but 136 / 2,117 zero normals) |
| DEC4N | `0x1A2187` | TANGENT | 2,622 | 5,928 | 2_10_10_10: x, y, z 10 bits signed, w 2 bits (xyz unit length on every vertex; **w is 0 on half of them**, see §Tangent w) |
| SHORT2N | `0x2C2159` | TEXCOORD 1-5 | 3,033 | 6,579 | two 16-bit signed normalised, **x = high half of the BE word** (the first in memory; lightmaps land right in a game frame, phase 10) |
| UBYTE4N | `0x1A2086` | BLENDWEIGHT | 2,121 | 2,452 | 4 bytes / 255, **x = low byte of the BE word** (the four sum to 255 on every vertex) |
| UBYTE4 | `0x1A2286` | BLENDINDICES | 2,121 | 2,452 | 4 bytes, x = low byte |
| D3DCOLOR | `0x182886` | COLOR4 | 4 | 1 | `0xAARRGGBB` |

**Byte order:** every element is read as big-endian 32-bit words and component *x* is in
the **low** bits. This is how the CZ recomp's renderer fetches vertices (it draws both
games correctly), and the skin weights only sum to 255 this way round. **Except 16-bit
pairs** (`SHORT2N`): *x* is the **high** half. *Retraction (2026-10-11, phase 10):* the
table said "x = low half" by analogy with the byte formats, never checked: `SHORT2N`
only holds level lightmap UVs, which nothing drew before phase 10. Drawn that way, CZ's
safehouse bathroom, seen from the camera of a recomp capture, got blocky shadows across
its door; swapped, its shading matches the game frame. Why: the Xbox's vertex fetch
hands a shader a 16-bit pair transposed and the game's shaders swap it back (a `yx`
destination swizzle on most 16-bit fetches; the CZ recomp's `vk_renderer.cpp`,
`g_SwappedTexcoords`). The vertex re-encode gate is unaffected (decode and encode
changed together).

**Signed normalised values are not clamped** (phase 4). A *b*-bit field holds *q* and
decodes to *q* / (2^(b−1) − 1). The lowest code, −2^(b−1), gives slightly less than −1
(−1.002 for 10 bits); the GPU clamps it to −1. The games store −1.0 **that way** on most
fields (DEC4N x/y/z never use −511), while HEND3N also has −(2^(b−1) − 1) in places, and
the 2-bit tangent w uses `11` (−1), never `10`. Phase 3's decoder clamped to −1, which
made two codes decode alike, so the encoder could not give the stored bits back
(60,537 CZ and 701,150 CW tangents, 129,755 / 1,139,556 normals). *Retraction
(2026-10-08):* "clamped to −1" is gone; with the unclamped rule, every element of
every vertex of both games re-encodes to its stored bytes (census below).

### Rigid parts: vertices relative to their node ✅

Found 2026-10-10 (user report: the Zombrex box's lid flap stuck out of its side). An
unskinned shape's vertices are stored **relative to a skeleton node**, the one in word 1
of the shape record, which is also every draw's palette start (`Scene.rigid_node`); the
game draws it with that node's world matrix. Measured over every model: every unskinned
shape uses one node and it is always word 1 (CZ 2,736 shapes, CW 4,498); its node is not
at the origin for CZ 1,677 draws in 369 models and CW 5,101 draws in 665 (props,
vehicles, cutscene props, level pieces; on skinned models every rigid draw's node is at
the origin). Checked by drawing models both ways: placed by their node, the Zombrex lids
close the box's end (lid nodes 12.2 cm down, vertices at height 0), the security
camera's base joins it, the canyon vista lies flat; as stored, they don't. The exporter
hangs such a mesh under its node in the `.glb` (positions unchanged), and the importer
takes the node's rest pose back off (from the mesh node's own offset when it still hangs
under its node: an inverse of the scaled sky-dome nodes adds float noise); `dr2 census
--reimport` still gives every model's exact bytes (CZ 1,397, CW 1,495, 2026-10-10). Phase 3–8 exports before this put those parts at the model's origin.

### Skinning and the bone palette ✅

Read from the game's own vertex shader `ProtoSkinnedClothRGB` (`shaders/…-vs.big/13176040.vo`,
translated to HLSL with XenosRecomp):

- Each vertex has **4 influences**; weight component *k* goes with index component *k*
  (x with x … w with w). The 3 used by the CZ crowd shader (`.yzw`) are a special case.
- A blend index is a **palette row**: 3 × the palette slot, because each bone is a 3×4
  matrix in three shader constants starting at `c8` (`gWorldMatrix[183]`, so at most 61
  bones per draw; the largest palette is 56 in CZ, 60 in CW). `c4`-`c6` = model → world, `c0`-`c3` =
  projection × view.
- **The palette is a run of skeleton nodes: slot *k* of a draw is node
  `palette_start + k`**, with `palette_start`, `palette_count` = RenderStrip words 3-4.
  This was the open problem of the old community tools. *Verified* three ways:
  1. geometrically: for 98% of skinned draws (1,732 / 1,767 CZ, 2,002 / 2,081 CW) every
     vertex sits closest to the bones it is weighted to with this mapping rather than a
     shifted one (distance to the bone segment); the rest are ties or within a few cm;
  2. in game: draws of Chuck that share a bone receive the *identical* matrix for it in
     the same frame (79 pairs of draws agree, and moving one draw's palette by ±1 or ±2
     makes all of them disagree), see "In-game check" below;
  3. posing the exported model in Blender bends arms, head and fingers cleanly.
- Static props skin rigidly: palette count 1, every vertex on palette slot 0 (the bike's
  parts each follow one node). Meshes without blend elements are in model space.

### Census (2026-10-08, `dr2 census --models`)

| | Case Zero | Case West |
|---|---|---|
| scenes parsed | 1,510 (1,397 models, 113 skeletons) | 1,639 (1,495, 144) |
| nodes | 16,009 | 25,200 |
| meshes / draws | 4,857 / 6,954 | 6,950 / 10,548 |
| draws decoded | **6,954 / 6,954** | **10,548 / 10,548** |
| vertices / triangles | 3,549,989 / 3,408,086 | 6,813,688 / 5,311,901 |
| vertex streams: combined / own / run-time | 15,294 / 1,309 / 1 | 25,346 / 1,323 / 1 |
| skin weights summing to 1 | 654,133 / 654,133 | 707,997 / 707,997 |
| problems | 0 | 0 |

Unused by any draw: 10 CW shapes (`construction_kart.big` and one other) carry extra
stride-12 streams (`… Vertices 3`, `… Vertices 4`) with the shape's vertex count; deformation
targets, probably ❓.

### In-game check (2026-10-08, Case Zero)

`tools/capture_gate.py` on a frame captured from the CZ recomp (procedure:
[`dev/recomp-integration.md`](dev/recomp-integration.md) §Phase 3): of the 40 draws of the
skinning shader in the frame, **30 match a draw of the game data byte for byte**, both
vertex stream and indices (Chuck's chest, arms, head, eyes, mouth, hands, watch, pants and
boots, from 5 model files, in two passes); the other 10 are other characters. Bone
palettes agree as described above. The game's bone matrices × the reader's rest pose keep
the records' bone lengths (median difference 0.01 mm; the few larger ones, up to 7 mm,
are foot and face bones, which animation translates). Every vertex skinned the way the
`.glb` is, then projected with the game's camera, lands on Chuck in the captured picture.

**Not proven yet:** a Case West capture (its census and exports look the same); what
`_ATTRIBUTE_`, `_COLLPRIMS_`, the value sets and the material floats do; LODs (no LOD
chunks were seen: each shape has its draws only).

### Writing scenes (phase 4) ✅

Implemented by `dr2kit/formats/scene_write.py` (chunks, strips, new geometry for a
shape) and `dr2kit/convert/model_import.py` (`.glb` → shapes). Everything below was
measured over every scene of both games before the writer relied on it.

**Command packets.** A shape's command buffer is one packet per draw, in draw order.
`RenderStrip` word 5 is the **byte offset where the draw's packet starts**, and word 6
the number of words from there up to the end of the draw command (`0x08` + its 6
arguments). Checked on 6,941 / 6,954 CZ and 10,455 / 10,548 CW draws; on the others
word 6 is one less ❓. Those are exactly the packets that don't end with an `0x04`
word (13 CZ in 9 shapes, 93 CW in 72 shapes: crowd seats, sky domes, glowing lights;
they chain into the next packet), so **word 5 is the authority for where a packet
starts.** A writer
that clones a packet keeps its word 6 and sets word 5.

**Shape words** (72-byte chunk): word 2 = number of the shape's own vertex buffers
(`<shape> Vertices k`), word 3 = number of `D3DVertexDesc` chunks, word 4 = own index
buffers, word 5 = draws, words 6-7 = the first draw's palette (start, count). Equal on
every shape of both games, except word 2 on 10 CW shapes that carry extra unused
stride-12 buffers (deformation targets?) ❓. **Bounds:** the radius is the largest
distance of a vertex from the origin (as float32) and the box is the exact min/max of
the positions, on every shape checked (964 of a 300-model sample). `_BOUNDINGBOX_` (the
whole model) is the union of the shapes' boxes in 80 % of models and larger in the rest
(other things count, ❓); the writer recomputes the union when it was one, and only grows
the box otherwise.

**Layouts.** Every skinned shape of both games has **one draw**. Own-buffer shapes
(characters) put their draws back to back in `<shape> Vertices k` / `Indices k`
(first vertex and first index in the draw arguments; 1,139 CZ and 1,207 CW shapes);
one shape, the CZ gunship, uses 9 vertex and 3 index buffers, each draw binding its own
set. Combined-buffer draws (props) bind every stream at a first vertex (`0x28`) and the
index buffer at a first index (`0x47`); the draw arguments are zeros on 4,139 of 5,804
CZ and 7,034 of 9,338 CW such draws. New combined draws use the bind arguments and
zeros.

**What the writer produces** for a shape it replaces, per part (glTF primitive):

- a **template**: an original draw with the same material (this shape first, then any
  shape with the same buffer family). Its vertex declaration, command packet (shader,
  textures, render state), flag words 1-2 and word 6 are copied;
- vertices encoded with that declaration (every packing has an exact encoder);
- one triangle strip per draw: runs that continue the last edge with the right parity,
  joined by repeated indices (an extra repeat when the next run would start on an odd
  position). `scene.strip_to_triangles` of the result gives back every triangle with
  its winding;
- weights: the 4 strongest influences, quantised to bytes that **sum to exactly 255**
  (largest remainders get the leftovers); blend index = 3 × (node − palette start);
- palettes: triangles sorted by the nodes they use and packed greedily into runs of at
  most **61** nodes. A part that needs more becomes several draws (packets cloned, word
  5 set for each);
- own buffers rewritten whole; combined buffers **appended to**, so other shapes keep
  their bytes. Header counts (`VBHeader`, `IBHeader`, `Combined_*`), shape words 3/5/6/7,
  bounds and `_BOUNDINGBOX_` follow.

A rigid shader (no blend elements, palette of 1) takes one bone per draw; a skinned
shader needs weights. A shape filled at run time (the vertex-animated larvae) is not
replaceable.

### Tangent w ❓

The game's skinning vertex shader (`ProtoSkinnedClothRGB`, translated with XenosRecomp)
outputs the bitangent as `cross(normal, tangent) × tangent.w`, so w is used as a sign.
But the stored w does not follow the UV layout's handedness: over a sample of 250 models
per game, w = 0, +1 and −1 each pair with "mirrored" and "not mirrored" UVs in the same
proportions (about 20 % / 80 % in CZ, 37 % / 63 % in CW), and half the vertices have w = 0 (code `00`, which
decodes to 0, or to +1/3 if the GPU uses its "no zero" signed mode). So it is not a
reliable handedness flag in the shipped data. **New tangents** are computed from the
first UV set and given w = +1 where `cross(N, T)` points against the UV bitangent (the
case of most of the games' vertices: 80 % in CZ, 63 % in CW) and −1 otherwise. Not verified visually on a normal
map; unchanged shapes keep their stored tangents.

### Census (phase 4, 2026-10-08, `dr2 census --reimport`)

| | Case Zero | Case West |
|---|---|---|
| scenes whose every interpreted chunk rewrites identically | **1,510 / 1,510** | **1,639 / 1,639** |
| draws whose every vertex element re-encodes to the stored bytes | **6,954 / 6,954** | **10,548 / 10,548** |
| models exported to `.glb` and imported back **byte-identical** | **1,397 / 1,397** | **1,495 / 1,495** |
| draws rebuilt from their own geometry (new strip, buffers, packets, palette, bounds) that decode to the same triangles and vertex values | **6,953** + 1 vertex-animated skipped | **10,547** + 1 skipped |
| problems | 0 | 0 |

(About 4 minutes for CZ, 8 for CW.) A Blender round trip (import, export with defaults
+ custom properties) of `chest_young_chuck.big` rebuilds every shape with the same
triangles, palettes and skin weights; positions come back within 1 µm (float noise).

### In-game check (phase 4, 2026-10-08, Case Zero)

A mod replacing `npcs.big/chest_young_chuck.big` with a `.glb` that went through
Blender: shirt and shirt bottom unchanged (rebuilt), both arms pushed out 2 cm along
their normals, and the watch replaced by a **new mesh**: a sphere on every face and
finger bone (each weighted 100 % to its bone) and a blob on the left wrist weighted 50/50
between the forearm twist and the hand. It needs nodes 25-91 (67 > 61), so it was split
into two draws (palettes 25-85 and 86-91). Captured with `tools/capture_gate.py --root`
(procedure in [`dev/recomp-integration.md`](dev/recomp-integration.md) §Phase 4):

- the recomp served `npcs.big` from `game_mods/`; the game ran normally;
- **32 of 32** dumped draws of the skinning shader match the mod build byte for byte,
  vertex stream and indices: the rebuilt shirt parts, the inflated arms and **both
  draws of the new mesh** (360 + 3,240 vertices), in both passes;
- bone palettes: 80 pairs of draws sharing a node got identical matrices, 0 disagree
  (shifted controls fail), so the split palettes are right; for all 34 face bones the
  head draw also covers, the new mesh got exactly the head's matrices, and 21 of them
  were moving relative to the head in that frame; finger bones were bent up to 45°;
- the picture: the forearm is visibly thicker, the spheres sit on Chuck's lips and nose
  and on his fingers curled round the bottle, the shirt looks as without the mod.

**Not proven yet:** a Case West run (its census passes the same gates); replacing a
combined-buffer prop in game (the writer and census cover it); normal-map appearance
of new tangents.

## Audio

Every sound of both games is **XMA2**, the Xbox 360's hardware audio codec: a cut-down
WMA Pro, cut into 2 KB *packets* that carry 512-sample *frames*
([glossary](glossary.md#xma)). The toolkit decodes it with ffmpeg's `xma2` decoder through
PyAV (`dr2kit/convert/audio.py`), the same decoder the recomps use
(`runtime/audio/xma_decoder.cpp`).

> **Retraction (phase 5, 2026-10-09).** Phase 0 wrote "`.xma` entries hold raw XMA …
> There is no `RIFF`/`XMA2` header, so channels and sample rate must come from
> elsewhere". That holds only for the 1,269 (CZ) / 2,545 (CW) sounds of the streamed
> banks in `data/audio/`, the ones phase 0 looked at. The other 7,647 / 9,190, in the
> `fx_*.big` banks inside `streamedassets.big`, are complete RIFF files. Found by
> counting the first four bytes of every `.xma` of both games.

### Two shapes ✅

| Shape | Where | Count CZ / CW | Format from |
|---|---|---|---|
| **RIFF XMA2 file** | every `.xma` in `streamedassets.big/fx_*.big` (sound-effect banks) | 7,647 / 9,190 | its own `fmt ` chunk |
| **raw packets** | every `.xma` in `data/audio/*.big` (music, voices, cinematics, ambience) | 1,269 / 2,545 | `data/audio/cache.big/<bank>.$$$` |

**RIFF XMA2** (`xma.XmaRiff`): `RIFF`/`WAVE`, then exactly three chunks in this order:

- `fmt ` (52 bytes, **little-endian**): `XMA2WAVEFORMATEX`, format tag `0x166`, `cbSize`
  34. The 34-byte tail is `wNumStreams, dwChannelMask, dwSamplesEncoded,
  dwBytesPerBlock (0x10000), dwPlayBegin, dwPlayLength, dwLoopBegin, dwLoopLength,
  bLoopCount, bEncoderVersion (4), wBlockCount`: what ffmpeg takes as extradata.
- `seek`: one **big-endian** dword per 64 KB block, the samples decoded by the end of
  that block (so the chunk flips byte order inside a little-endian file, rule 1).
- `data`: the packets.

The entry size is `88 + 4 × blocks + data`, which is why fx entries are 2 KB multiples
plus 92, 96, 100… bytes.

**Raw packets**: the entry is the packets alone, 0x800-aligned in its bank. Their format
is in a **stream table** (`xma.StreamTable`), one per streamed bank, in
`data/audio/cache.big`: `ambience.$$$`, `music.$$$`, `cinematics.$$$`, `charvocals.$$$`,
`chuck.$$$`, `streamfx.$$$`, `bossvocals.$$$` (CW adds the same set for its banks).

```
0x00  "$GIB"   magic ("BIG$" backwards)
0x04  u32 BE   2        (version?)
0x08  u32 BE   3        (unknown, same in every table)
0x0C  u32 BE   record count
0x10  records, 24 bytes each, sorted by hash as signed ints:
      u32 hash         engine hash of the entry name WITH ITS CASE KEPT ("HB_Indemnify.xma")
      u32 offset       where the entry sits in its bank file
      u32 size         the entry's size
      u32 format       rate << 5 | channels << 2 | 1
      u32 loop_begin   as RIFF dwLoopBegin (0 = no loop)
      u32 loop_length  as RIFF dwLoopLength
```

Verified: every record of both games matches an entry of its bank by hash, offset and
size (and vice versa), and every decode agrees with the rate, channels and loop. The
hash is the *case-kept* name, unlike the `.big` index, which hashes the lower-cased
name. The low two bits of `format` are 1 in every record (meaning unknown, preserved).

### Channels, rates, streams ✅

- Channels: 1 (8,846 / 11,644), 2 (42 / 73), **6** (28 / 18: the 5.1 cinematics).
- Rates: 48,000 Hz (8,750 / 11,567), the rest a few hertz off (47,866 to 48,530 Hz in CZ,
  47,060 to 48,294 in CW): the encoder stored each recording's measured rate.
- More than two channels are stored as **several streams** of one or two channels, their
  packets interleaved. The 32-bit packet header (big-endian) is `frame count:6 |
  first-frame bit offset:15 | metadata:3 | packet skip:8`; *skip* is how many packets of
  other streams follow before this stream's next one. A 5.1 sound is three stereo
  streams (L R, C LFE, Ls Rs) starting at packets 0, 1 and 2 (`xma.stream_starts`). The
  hardware decodes one stream per context, and so do the recomps (CZ `audio.cpp`,
  "ADVANCE ALONG THIS STREAM'S OWN PACKET CHAIN").

### Lengths ✅

A decode is always **384 samples shorter than the frames encoded** (`xma.DECODER_DELAY`;
the decoder drops that lead-in). Loop points count those 384 samples, and nearly every
loop begins at exactly 384, the first decoded sample. Measured rules, each checked on
every sound of both games:

| Sound | Decodes to |
|---|---|
| one-shot RIFF (7,479 / 9,028) | exactly `dwPlayLength` |
| looping raw stream (5 / 17) | exactly `loop_begin + loop_length − 384` |
| looping RIFF (168 / 162) | no exact stored length: most end at the loop end (±1 sample: 12 CZ wind and waterfall loops decode one sample past it); 4 (CZ) / 2 (CW) carry a tail after it (`SlotWinBig1`, `SlotWinSmall1`, `SlotWinJackpot1`, `sysEscapeTimer`; CW `sysEscapeTimer`, `SurgicalSawIdleLoop`) |
| any sound | `frames × 512 − 384`, less under one frame per stream (`frames` = sum of the packet headers' frame counts / streams; the encoder marks the padding of the last frame) |

The 6-channel prologue cinematic (`cinematics.big/39694.xma`) decodes to 316.45 s,
which agrees with the CZ recomp's own measurement (316.5 s from the packet headers, ~5 min
10 s by stopwatch).

**Silent placeholders**: 15 (CZ) / 20 (CW) sounds in the voice banks are one packet
of 0.1 s silence, all identical (`charvocals.big/4857.xma`, `chuck.big/28390.xma`…).

### Decoding packet by packet ✅

The recomps feed ffmpeg one packet per call, one decoder per stream. Decoded that way
(`convert.audio.stream_packets`), each packet returns a varying number of samples (960,
5,120, 4,608… for the title music; the decoder holds about 3,900 back until it is
flushed), and the outputs joined are **the same samples** as decoding the whole file
(largest difference one 16-bit step), for mono, stereo, and each stereo stream of a 5.1
sound decoded on its own. So where a packet's output lands is fixed by the packets before
it, which is what audio substitution relies on (§Replacing sounds).

### `.sfx` sound effects ✅

Text in the engine's block format (`audioscript.parse`): `cSoundEffect NA { MixerCategory,
PlaybackMode, Volume, cSfxTrack 1 { Path, Sample, Loop, Table, cModifierMap … } … }`.
`Sample = "cursorError43a_01a.wav"` names the recording; the bank's `.xma` of the same
stem is it. A `Sample` ending in `.sfx` is another effect of the bank (a sub-effect,
2,509 / 2,717 tracks). Every `.sfx` of both games parses (4,745 / 5,194); every track
resolves inside its own bank except **22 (CZ) / 1 (CW) recordings the shipped data
lacks** (`fx_main.big/ChuckLaugh.sfx` → `DR2_Chuck_S2_Laugh_01`…, CW
`TruthVanished.sfx` → `sysGameover46a_01a`). The game plays an effect by its file name, so
the `.sfx` stem is the sound's event name.

### Audio scene scripts ✅ (text), ⚠ digest-checked

Same block format. `cAudioScene` → `cAudioScenario` (with `ActivationEvent`) →
`cAudioActionLoad { BankId, BigFile = "fx_mechanic.big", TriggerEvent }`,
`cAudioJukebox { TriggerPlay, TriggerStop, … cAudioJukeboxTrack { Asset =
"music.big/HB_Indemnify" } }`, `cAudioActionPlay { Asset = "fx_main.big/FEError.sfx" }`,
emitters with positions, timers, mixer keys. CZ: `data/audio/Prologue.txt` (324 `Asset`,
98 `BigFile`) and `datafile.big/scenegraph.txt` (DR2's, naming banks CZ doesn't ship:
268 of its references resolve nowhere). CW: `data/audio/{LivingResearch, Safehouse,
SecureLab, StoragePens, scenegraph}.txt`; `audiomixer.txt` and `curves.txt` are other
formats. The index links every `Asset` to its sound with the enclosing block path and
trigger events as context (`audioscript.script_refs`).

**Case Zero verifies `Prologue.txt` against a SHA-1 in the executable** (its `Digest`
resource has exactly that one entry; CZ recomp `docs/phase3-notes.md` finding 50). Checked
in game, 2026-10-09: a copy with one `Asset` changed was served from `game_mods/`, the
digest check ran on it (`CZ_DIGEST_PROBE=1`), and the game crashed on the spot (the
check's failure path is an assert that stores to address 0). So remapping sounds by
editing the scene script, the PC community's music swap, **does not work on Case
Zero**. Case West has the same digest manager (its gotcha about "Bad file digest"); ~~which
of its files are listed was not measured, so treat its scripts the same way~~ (superseded
2026-10-09: its list was read from the XEX, §Digest-checked files: `Safehouse.txt`,
`scenegraph.txt`, `audiomixer.txt` and `curves.txt` are checked; `LivingResearch.txt`,
`SecureLab.txt` and `StoragePens.txt` are not).

### Voice lines and the GASP tables (`audio/gasp.big`) ⚠ partial

Read 2026-10-09 (CZ) while looking for voice-line names for the Library. Per speaker
set (`char`, `chuc`, `boss`, …) five block files: `*_smp` (samples, `id = 20893`: the
numbers of the voice `.xma` entries), `*_sg` (speech groups: a list of sample ids,
"takes" of one line), `*_bkt` (buckets: lists of speech groups), `*_snt` (concepts: a
priority and bucket list), `*_kwd` (`<hash> = [concept ids]`); plus `stmts.txt` and
`rules.txt` (conditions). Keywords and statements are **name hashes** (`h*33 ^ c`,
`hashing.name_hash`): of 41 keyword and 24 statement hashes, only 2 and 1 matched any
of 28,253 words from the game's text files and string labels (`ArmyPA`,
`ChuckEmotePositive`, `characterNameID`). **No link to subtitles** (`IDS_SUBTITLE_*`)
was found: samples carry `sid = #0`, `sup = #0`. So the Library lists voice lines by
number; naming them needs the concept names (❓).

### Replacing sounds: PCM substitution ✅ (in game, both games)

There is no redistributable XMA encoder, so mods don't write `.xma`. The recomps decode
XMA on the host anyway, so they **substitute PCM**: `dr2 mod build` lists every packet of
a replaced stream by its FNV-1a 64 hash (`xma.fingerprint`) with the decoded-sample
position where its output begins, and writes the new audio as 16-bit WAV per stream,
fitted to the sound's channels, rate and exact decoded length. The runtime hashes each
packet it decodes and, on a hit, writes the replacement samples over the decoded ones.
The game's files and everything it sees stay as shipped. Design and table format:
[`dev/recomp-integration.md`](dev/recomp-integration.md#audio-substitution); code:
`dr2kit/mods/audio.py`.

Packets are unique enough for this: over every sound of CZ, 8,961 of 8,972 stream-first
packets occur nowhere else; the rest are the silent placeholders and one twin
(`BomberBy2`, shipped in two banks with a different second half). A packet that also
occurs in another sound is marked *continue only* in the table, so it never starts a
substitution.

### Census (phase 5, 2026-10-09, `dr2 census --audio`)

| | Case Zero | Case West |
|---|---|---|
| `.xma` sounds | 8,916 (riff 7,479, raw 1,264, riff looped 168, raw looped 5) | 11,735 (9,028 / 2,528 / 162 / 17) |
| decoded to the stored length | **8,916 / 8,916** | **11,735 / 11,735** |
| total audio | 3.17 h | 3.82 h |
| silent sounds | 15 | 20 |
| stream-first packets shared by different sounds | 1 group | 1 group |
| `.sfx` parsed / tracks (xma, sfx, missing) | 4,745 / 8,892, 2,509, 22 | 5,194 / 10,269, 2,717, 1 |
| time (with the other gates) | 30 s | 42 s |

### In-game check (phase 5, 2026-10-09, both games)

The gate: one music swap is audible in the recomp. A mod replaced each game's title-screen
music (`music.big/PressStartPrologue.xma` in CZ, `PressStartDR2.xma` in CW) with another
track of the same game (`HB_Indemnify`, `MercenariesBattleUnderground`). Each recomp was
booted headless to the title screen for 90 s with SDL's `disk` audio driver recording what
the game sent to the speakers, once with the mod and once with `CZ_NO_AUDIO_MODS=1` /
`CW_NO_AUDIO_MODS=1` on the same binary (procedure: `dev/recomp-integration.md`).

- With the mod, the log says `audio mods: ctx0 plays <file> from sample 0 (start #1)` and
  never restarts; the recording follows the replacement track second by second (CZ:
  1 s windows match it at up to 0.94 normalised correlation, 0.4-0.8 typical, each at
  the right position in the track; CW: 0.50-0.57 at the right positions) and no longer
  the original.
- Off switch: no `audio mods` line; the recording follows the original title track
  (CZ 0.31 at the right position, the replacement ≤ 0.06).
- Both recordings drift from their reference by about 0.01 s per second, the replacement
  and the original alike: the runtime's playback pace, not the substitution.

Not proven yet: a 5.1 cinematic replaced in game (built, and positions checked against
PyAV per stream, but not heard); a sound effect from an fx bank in game.

## Texture conventions (what each map holds) ✅

Measured 2026-10-09 over the textures of both games (the index: CZ 12,237, CW 23,139),
for texturing programs (docs/modding/14-texturing-tools.md, `mods/texture_import.py`).
Roles come from the name (`texture_role`).

| Role | Formats (CZ / CW) | What it holds |
|---|---|---|
| colour `_cm` | DXT1 2,636 / 1,593 · DXT5 535 / 388 · A8R8G8B8 2 / 1 | RGB colour. **Alpha only in DXT5** ones: on characters every DXT5 colour map uses it (CZ 214, CW 149) ~~for hair, eyelashes, mouths, smooth transparency~~ (corrected 2026-10-09 below: only the hair and eye shaders use it as transparency); DXT1 ones have none, or on/off alpha (6 / 4 character maps) |
| normal `_nm` | DXN 594 / 783 · DXT1 475 / 350 | tangent-space normal, X in red, Y in green (DXN stores only those two). **OpenGL-style: green = up** (below) |
| specular `_sm` | DXT1 371 / 543 · DXT5 2 / 2 | **coloured** specular (RGB; only 2 of 22 CZ and 40 of 128 CW character maps are grey) |
| mask `_mask` | DXT1 337 / 327 · DXT5 134 / 114 | separate channels (RGB, and alpha in the DXT5 ones); what each channel tints is not decoded ❓ |
| self-illum `_si`, reflection `_rm`, opacity `_om` | DXT1 | ❓ meaning per channel |

- **Which shaders use alpha as transparency** (measured 2026-10-09 over every model's
  colour maps in both games, `convert.material.alpha_mode`): shaders whose name has an
  **`OM`** part (opacity map: `CM_OM_LM`, `LIT_CM_OM_RMX`, `CM_OM_NM_RMX_LM`… foliage,
  fences, decals; median 57-97% see-through texels) and the **hair** shaders
  (`ProtoSkinnedHair`, `ProtoSkinnedHairRGB`, `ZombieHair`; 25-82%). Opaque: cloth and
  skin (below), `ZombieDiffuse` (far-away zombies, alpha picks the body part),
  `ZombieHairLOD2` (no see-through texels), every shader without `OM`. Lenses blend
  (§Materials: the lens family). The `.glb` export marks these materials `MASK` (cutoff
  0.5) / `BLEND`, and the Library's pictures use the same rule.
- **A colour map's alpha is not always transparency** (measured 2026-10-09, CZ, every
  DXT5 colour map of `npcs.big` and `zombies.big` by the shader that draws it, from the
  index's thumbnails): with `ProtoSkinnedCloth`, `ProtoSkinnedSkin`, `ZombieCloth` and
  `ZombieClothLOD2` (24, 3, 47 and 32 maps) a median **97%** of texels have alpha under
  0.5, yet those clothes are drawn solid in game, so that alpha is another channel (a
  mask; meaning ❓). Hair shaders (`ProtoSkinnedHair` 6, `…HairRGB` 5, `ZombieHair` 1)
  have 25-82% see-through texels: transparency. Found because the Library's thumbnail
  renderer first alpha-tested every map and drew zombies without their clothes; it now
  ~~draws everything opaque, like the `.glb` export. Which shaders read alpha as
  transparency should come from the shaders themselves (not decoded yet).~~ (superseded the
  same day: the rule by shader above, measured over both games.)
- **Normal-map green direction.** Measured with an integrability ("curl") test: a normal
  map made from a height field has consistent slopes, the change of the x-slope down the
  rows matches the change of the y-slope across the columns, with a + sign for
  DirectX-style (green down) and a − sign for OpenGL-style (green up). Over 400
  character normal maps per game: **OpenGL-style 323 / 300, DirectX-style 31 / 56,
  unclear 46 / 44** (CZ / CW). This agrees with the tangent analysis (§Tangent w: the
  shader's bitangent points against the UV v direction for most vertices). So DR2's
  normal maps are OpenGL-style, the same as Blender and glTF; a mod's normal map should
  be too (`texture_import` measures a submitted map and flips green when it disagrees
  with the original).
- **Sizes.** Largest 2048×2048; 351 (CZ) / 518 (CW) textures are not powers of two.
  Characters' colour maps are mostly 256-512 px, up to 1024. A replacement keeps the
  size and format of the texture it replaces (v1 rule).
- **No PBR maps.** DR2 is a diffuse + specular engine: no roughness, metallic or height
  maps exist. A metal/roughness export converts to diffuse = BaseColor × (1 − metallic),
  specular = mix(0.04, BaseColor, metallic).

## Striped head textures of Chuck's hat heads ❓

Found 2026-10-10 by the user in DR2 Studio. `head_White_Cowboy_Hat`, `head_Black_Cowboy_Hat`
and `head_Mohawk_Hair` (Case Zero; the "Head" item worn with the matching `headwear_*`,
`datafile.big/clothingdatabase.csv`) share one colour map (same SHA-1 `27232c74…`) whose
forehead and eye rows are horizontal purple/green bands, as is their `_mask` in the same
rows. Checked: every one of the 9 mip levels has the bands (so the file holds them, not
our decoder); the matching headwear covers only the scalp (`headcapshape`, hair or hat),
not the eyes and nose; the skin shader `1175e4e0.po` draws the colour map unchanged
(samplers: masks .x, diffuse, normal); the slots' bind hashes are their own. A census of
all 93 head colour maps of both games finds only these three (and Royce's, a channel
weight map that the bake already handles). So the game probably binds another texture
(Chuck's normal face?) to these heads at run time. **Not verified in game.** Until it is,
the toolkit shows and exports the file as it is.

## Variants: which parts and colours a model shows ✅

Found 2026-10-10 (research for phase 9, [`phase9-kickoff.md`](phase9-kickoff.md)); the
layout corrected and the rules implemented the same day (`dr2kit/convert/variants.py`,
`dr2 variants`, `dr2 census --variants`). A model can hold several looks at once; the
game draws only some shapes and may swap a material's value set. Tools that draw every
shape (the toolkit before phase 9) show a zombie wearing all its clothes at once. How the
game picks a look per zombie is still unknown ❓ (below).

**Shape groups (in the executable, both games).** 53 records of 16 bytes,
**`{u64 mask, u32 pattern address, u32 0}`**, big-endian, at CZ `0x829DF718` and CW
`0x829F25D0` (read from the recomps' `assets/game/default_image.bin`, the image mapped at
`0x82000000`; `tools/variant_table.py` finds and prints them, and checks the copy in the
profiles' `[variants]`). The loader (CZ `sub_825AC588`) passes that address and the count
53 to the classifier. Each pattern is a comma list; a shape matching it gets that bit:

| Mask | Patterns (abridged) | The toolkit calls it |
|---|---|---|
| `0x1` … `0x80` | `head*`, `chest*` (+ hip caps), `pants_*,skirt_*`, `larm_*`, `rarm_*`, `lleg_*`, `rleg_*`, each with its `cap_…` | body regions (cutting limbs off); never hidden by a look |
| `0x2` | `cap_*` | Wound caps |
| `0x100` | `headwear*` | (headwear region) |
| `0x200`, `0x400`, `0x800` | `eyewear_acc*`, `chest_acc*`, `chest_acc_bkpc` | Glasses, Chest accessories, Backpack |
| `0x1000` | `*` | matched nothing else (only used then) |
| `0x2000`, `0x4000`, `0x8000` | `larm_arm*,rarm_arm*`; `head_gas*…`; `head_black*,…,pants_black*` | Bare arms, Gas look, Burnt |
| `0x10000` … `0x100000` | `head1_*,chestupper_neck1*,cap_neckchest1,cap_chestneck1` … `head5_…` | Head 1-5 |
| `0x200000` … `0x1000000` | `head1_head_tumour1*,…,head5_head_tumour1*` … tumour 4 | Head tumour 1-4 |
| `0x2000000` … `0x20000000` | `headwear1*,geo_head1*` (`headwear2*` adds `headwear_acc*`) … 5 | Headwear 1-5 |
| `0x40000000` … `0x800000000` | `chest_shirt1*,rarm_shirt1*,larm_shirt1*,chest_tshirt1*,geo_upper1*,…,cap_chestlarm1` … 6 | Shirt 1-6 |
| `0x1000000000` | `chest_shirt1_tumour1*,larm_shirt1_tumour1,…` | Shirt tumour |
| `0x2000000000` … `0x80000000000` | `pants_pants1*,rleg_pants1*,…,geo_lower1*,cap_rleghip1,…` … 7 | Trousers 1-7 |
| `0x100000000000` | `skirt_skirt1*,…,geo_skirt_lower1*,…` | Skirt |
| `0x200000000000` … `0x8000000000000` | `lleg_lfoot1*,rleg_rfoot1*` … 7 | Feet 1-7 |
| `0x10000000000000` | `lleg_tallboot1*,rleg_tallboot1*` | Tall boots |

CW's table is CZ's plus `cap_lfoot*` / `cap_rfoot*` in the leg regions (`0x40`, `0x80`).

> **Retraction (2026-10-10, same day).** The first reading took the records as
> `{u32 pattern, u32 0, u64 mask}` starting at CZ `0x829DF720`, which pairs every pattern
> with the mask of the record before it. That made the masks look "twice the bits the
> game uses" ("the per-mesh bits are the table values shifted right by one") and left the
> tall boots' mask unreadable ("the words after it read as floats"). Both came from the
> 8-byte misalignment: the classifier loads the mask with `ld r29,0(r6)` and the pattern
> with `lwz r11,8(r6)`, the 8 bytes before `0x829DF720` hold `0x1` (head) and the tall
> boots' mask is `0x10000000000000`. The values the CZ recomp measured (head 1
> `0x10000`, the helmet `0x04000101`) are the table's own values.

**The matcher** (CZ `sub_82795420`, called by `sub_827A2E10` for each record): an
alternative matches when it is a **prefix** of the shape name; `*` ends the alternative
(so `head1_*` and `cap_neckchest1` are both prefixes); comparison is case-sensitive.
A shape's bits are the OR of every record that matches; the `*` record counts only when
nothing else did (the classifier keeps it apart: `cmplwi r11,42`).

**The slot table** (CZ `0x8208A2E0`, CW `0x82084AE0`): 7 rows of 7 u64, the masks of
heads 1-5, headwear 1-5, shirts 1-6, trousers 1-7, skirt, feet 1-7, tall boots (unused
entries 0). The same loader reads it to build, for each of 6 shirts, a 32-bit set of
meshes: the burnt meshes plus head 1, headwear 1, that shirt, trousers 1, skirt, feet 1
and tall boots. Its use (a burnt look?) is not traced further ❓.

**At run time (measured in the CZ recomp, its sessions 2026-10-08 to 10; code
`runtime/cpu/zombie_variant_names.cpp` there, commit `78632f1`).**
- When a model loads, `sub_827ACF00` runs every mesh name through the classifier and
  builds a per-type table, 8 bytes per mesh in model order (head 1 `0x10000`, the helmet
  `headwear2` `0x04000101` = headwear 2 + headwear + head region).
- **Each zombie carries a 64-bit hide mask** (actor `+0x40`); at draw time `sub_827ADD40`
  skips a mesh when `bits & mask != 0`. So a set bit hides a variant, and meshes with no
  variant bits always draw. The mask is set in `sub_82437600` (`0x82437978`):
  `actor+0x40 = r24 ? 0x4000 : *(spawn+0x30)`. The spawn record is filled by
  `sub_8248A420` (`std r9,48(r3)`) from its callers' objects (`sub_82439960`: `+128`;
  `sub_8243C688`, `sub_82475D78`, `sub_8243D2C0` via `sub_8248A460`). ❓ Where those
  objects get the mask: probably rolled from the zombie-spawn seed (random stream 4, a
  Park-Miller generator at `0x8276F728`), not found yet. ❓ How a colour set is chosen.
- The measured live mask `0x001FFFCF767EC602` decodes to: wound caps, glasses, chest
  accessories, gas and burnt hidden; heads 2-5 hidden (head 1 shown); head tumours 1-2
  hidden; headwear 1, 2, 4, 5 hidden (headwear 3 shown: the soldier has none, so no hat);
  shirts 1, 3-6 hidden; trousers 2-7, skirt, every foot and the tall boots hidden. So the
  game hides every number but one per slot, numbers the model doesn't have included, and
  can pick a number the model lacks (no hat, no feet). `tests/test_variants.py` checks
  that this mask draws exactly the bare-headed soldier with the toolkit's rule.
- **Distance:** the crowd renderer `sub_825B8680` gives the zombies largest on screen `_2`,
  the next `_3`, the rest `_4`. `_2` and `_3` honour the mask; `_3`'s shaders don't sample
  normal maps; `_4` is one baked texture (`zombie_fat_4.tex/al_lod4_cm`) and only roughly
  follows the outfit.
- **Names decide, so a misspelling breaks a variant.** CZ `zombie_soldier_3.big` has
  `headwearShape2Deformed` and `chestupper_neckShape2Deformed` (digit after "Shape"), which
  classify without their variant bit: every far soldier wore the helmet. The CZ recomp
  corrects the name for the classifier. CW `zombie_security_2.big` **and `_3.big`** have
  `chestupper_neckShape1Deformed` and `chestupper_neckShape3Deformed` (census: these 6 are
  all, both games); the CW recomp has no such fix ❓ (effect in CW not checked). The
  toolkit reads them as meant and says so.

**Which models.** The game classifies crowd zombies. The toolkit applies the table to
every model in `data/models/zombies.big` and to any model with numbered parts (cutscene
zombies `cine_zombie_*`); never to people or props, whose `cap_…` or `head_…` names mean
nothing to the table. Census (`dr2 census --variants`, 2026-10-10): CZ 43 models, CW 42;
no shape carries two numbers of one slot; zombie shapes that match no pattern (always
drawn): CZ 113, CW 162, nearly all `geo_*` and `polySurface*` parts of cutscene zombies.

**Detail levels.** `<zombie>_2.big`, `_3.big`, `_4.big` are high, medium and low detail
(CZ `zombie_cop`: 214, 102, 19 KB). `_3` keeps `_2`'s slots (census: every zombie of both
games; CZ `zombie_cop_3` adds a `pants2` shape); `_4` keeps headwear (as `geo_headN`), shirts
and trousers (as `geo_upperN`/`geo_lowerN`) or none (`zombie_cop_4`: `geo_lod4`).

**Colour variants.** A value set (`.scv`) carries its `.pdv` name inside. CZ's
`data/datafile.big/zombie_pdv_variations.txt` maps, per model section (`[zombie_skinny_2]`),
a material's own `.pdv` to its alternatives:
`zombie_skinny_mtl_jersey.pdv=zombie_skinny_mtl_jersey1.pdv,…jersey5.pdv,` (8 models,
36 materials, 129 alternatives). The alternatives are value sets in
`shaders/deadrisingprologue-sc.big` (149; the same 149 in `preload4.big`), found by
their embedded names: **all 129 found** (2026-10-10). **The name rule** — the bank's value
sets named `<own name>N.pdv` or `<own name>_varN.pdv`, by N — **gives exactly the listed
choices** for every listed material (census, 2026-10-10), and also choices for materials
the list doesn't name: CZ's `_3` models (the list has `_2` and `_4` sections only): 219
choices for 62 materials in all. CW's list (`data/preload4.big/zombie_pdv_variations.txt`)
is **empty**, yet `shaders/deadrisingepilogue-sc.big` holds 265 value sets; the rule finds
289 choices for 81 materials of 13 CW models (`zombie_showgirl_mtl_caps1…4` and other DR2
names have no model in CW). The executables name the list
(`data/datafile/tofix/zombie_pdv_variations.txt`) and `shaderconstantvariationmap.cpp`.
❓ Does CW's game use the choices (by name), or not at all; does CZ vary `_3`'s colours.

**Prop states.** Some props keep states as shapes (slot machines: `slot_logo` /
`slot_logo_dmg`, `slot_screen_staticWin`, `slot_screen_staticOff`, `LOD_slot_machine`),
others as files (`cashregister_dmg.big`, `military_hummwv_hummwv_stage2/3.big`,
`chair_1…9.big`). ~~Counts by name over both games: 70 models with on/off/win/open-style
shape names, 11 with damaged or broken shapes, 9 with `LOD_` shapes.~~ (Retracted
2026-10-10: those counts matched `window`, `wings` and similar names. By twin shapes — a
state shape whose base name is also a shape — only CZ's two slot machines keep states
as shapes; `dr2 census --variants`.) Environment pieces with burnt, damaged or LOD-like
shape names (CZ 0, CW 66, mostly `lod_large`/`lod_small` pieces of Case West's zones)
are listed by the census, not classified.

**Chuck's outfits.** `data/datafile.big/outfits.csv` (`outfit_name, headwear_piece, head,
facewear, chest_piece, hands, leg_piece, feet_piece`) lists the part model per slot
(`OUTFIT_BOWLING_SHIRT_JEANS,NONE,naked,NONE,Bowling_Shirt_Jeans,naked,…`);
`clothingdatabase.csv` marks which body slots each part covers (`Hair, Head, Facewear,
Shoulders, Chest, Arms…`). Not used by the toolkit yet.

## Rig matching (which skeleton file a model was made for) ✅

Measured 2026-10-09 over every model of both games (`index.build.link_rigs`; listing:
`dr2 library` and Studio's Library). A model carries its own copy of its rig, so the
skeleton file it was made for has the same bones. Facts:

- **The rig families share their bone names.** `player`, `female`, `large`, `child` and
  their cutscene versions (`cineplayer`…) all have the same 98 names (`longcloak` 112).
  Matching by name alone put every character on `childfullbody`; the **rest pose**
  decides: a model's bones sit within 1 mm of their place in exactly one family.
- **Characters (`npcs.big`), first match:** CZ 66 `playerfullbody`, 13 `femalefullbody`,
  2 `largefullbody`, 1 `childfullbody` (Katey), 9 on `zombiefullbody` with other
  proportions (cutscene zombies); CW 144 + 1 `playerfullbody`, 19 `femalefullbody`, 1
  `largefullbody`, 1 `longcloakfullbody`. Every character has a match in both games.
- **Zombies** share the 30-bone `zombiefullbody` names; most variants have their own
  proportions (CZ 32 of 36, CW all 31 differ by more than 1 mm), so they are listed as
  "same bone names, other proportions" (rank 1).
- A cutscene twin (`cineplayer`) has the same pose to float precision as the full rig;
  ties go to the `…fullbody` file. Identical files (`skeleton/` and `preload4.big`) count once.
- Models with fewer than 8 bones (props with a door or a wheel) are not linked; props
  and level pieces with more have their own rigs (no skeleton file matches).

## Engine limits (what the game's files can hold) ✅

Measured over every model of both games, 2026-10-09 (CZ 1,397, CW 1,495 models; every
draw decoded), plus the shader limit found in phase 3:

| Limit | Value | How we know |
|---|---|---|
| Vertices one draw can address | **65,536** (16-bit indices); for a character part, its whole shape: the parts of a shape share its own vertex buffer, so the importer refuses a shape over 65,536 (`model_import`), the writer a draw past index 0xFFFF (`scene_write.MAX_INDEX`) | every index buffer is 16-bit (`Combined Indices 2`, `>H`) |
| Bones per draw (palette) | **61** consecutive skeleton nodes | `gWorldMatrix[183]` = 61 × 3 rows in the skinning shader (phase 3); largest shipped palette 56 (CZ) / 60 (CW). The importer splits a mesh into several draws when needed |
| Bone influences per vertex | **4** (weights `UBYTE4N`, one byte each, summing to 255) | every skinned declaration; the importer keeps the 4 strongest |
| UV sets per draw | up to 6 (shipped); set 0 is always `FLOAT2` (any range), sets 1+ are `FLOAT2` or `SHORT2N` (**−1…1 only**) | declarations of every draw |
| UV range of set 0 on characters | 0…1 (CZ 2,075 / 2,075 draws; CW 2,382 / 2,384, the exceptions are two hats at −1.29…2.29); environments tile freely (up to ±10⁷) | decoded |
| Largest shipped draw | 40,618 vertices / 85,573 strip indices (CZ), 48,822 / 72,545 (CW): environment pieces | decoded |
| Largest shipped model | 62,817 vertices (CW environment piece); characters up to 18,593 (CZ `boss_mechanic`) / 12,646 (CW) | decoded |
| Skeleton nodes in a model | up to 119 (characters 98) | node tables |
| Materials per model / texture slots per material | up to 33 (CZ) / 49 (CW); 10 slots | `MatArray`, `MatTextureInfoArray` |
| Shapes per model / draws per shape | up to 124 / 38 (characters: one draw per shape) | mesh descriptions |
| Textures | up to 2048×2048; DXT1, DXT5, DXN, A8R8G8B8, L8 | §Textures, index |

What the game *does* with more than its own content (a 50,000-vertex character, many
2048 textures) is not measured: memory and frame time are the unknowns. The toolkit's
own v1 rules add: models are changed by replacing existing shapes (no new shapes,
materials or bones), a texture keeps its size and format, a sound keeps its length.

## Levels: zones, placements, level text files 🟡

Researched 2026-10-11 for phase 10 (`phase10-kickoff.md`). **Read by the toolkit since
phase 10 step 1** (2026-10-11): `dr2kit/formats/level.py` (zone list, placements) and
`dr2kit/convert/level.py` (a zone as one `.glb`), checked by `dr2 census --levels` on
every zone of both games. The level text files are still research only (step 2).

**Layout.** A level is `data/models/environment/<level>/`: a `zonelist.big` and one
archive per **zone** `<level>_zNN.big` (CZ `prologue` z01-z11, CW levels z00-z09). A zone
holds, per piece, `<piece>.big` (one entry, `_COMP_<piece>.big`, an ordinary scene that
`convert.model.read_scene` reads), `<piece>.tex` and `<piece>_LOD.tex` (its textures
full size and small: the same names, a quarter of the size); plus
`ZONE_ORGANIZATION.big`, `MERGED_COLLISION.big`, `ZONE_ORGANIZATION(_LOD).tex` /
`MERGED_COLLISION(_LOD).tex` (not archives) and `COMMON_TEXTURE.tex`: textures several
pieces of the zone share, in 31 zones (CZ 8, CW 23; up to 52 textures, CW
`living_research_z01`), empty in the others. *Retraction (step 5, 2026-10-11):* the
research called `COMMON_TEXTURE.tex` "empty in every zone checked", and step 1 said the
small packs add `.bct` to the names; names end in `.bct` in every small pack but also in
many full-size ones (CZ 1,125 of 3,835, CW 7,662 of 9,030 names), so the ending says
nothing about the size. The texture finder ignores it.

Levels found (`dr2 level list`): CZ `prologue` (11 zones), `prologue_menu` (5: the title
screen's street, its zone archives named `prologue_z01`… like the street's),
`prologue_menu2` (1); CW `living_research`, `storage_pens`, `secure_laboratory`,
`safehouse` (10 zones each), `main_menu` (one zone named `main_menu`) and four cutscene
sets `cine_*` (1 zone each).

**`zonelist.big`**: `NumZones` (be32) and `ZoneList`, `NumZones` × 132 bytes:
`char name[64]` (`prologue/prologue_z05`; Case West writes a backslash,
`living_research\living_research_z01`), `f32 min[3], max[3], centre[3], radius`, an
`i32` (−1, or 1 / 2 for CZ's z10 / z11, two small interiors ❓), 24 zero bytes. Each
zone's own `ZONE_ORGANIZATION.big/_ZONEINFO_` (10 floats) holds the same bounds: 60 of
62 zones; CW `cine_exterior_before_z01` and `living_research_z05` differ (census note).

**`ZONE_ORGANIZATION.big/ModelInstanceArray`**: `NumModelInstance` × 208 bytes (every
record of both games is 208 bytes; `ModelInstanceArray_Dynamic` is empty in all zones):

```
+0    char name[32]; char name2[32]      the piece (both names equal in every record)
+64   f32 scale[3]                       1,1,1 on 1,870 of 1,894; 24 others (CZ 0.542…)
+76   f32 rotation[4]                    quaternion x,y,z,w (unit length but one, below)
+92   f32 position[3]
+104  f32 bounds_min[3], bounds_max[3], centre[3], radius     world space
+144  u32 flags                          0, or 0x20 on 71 placements ❓
+148  f32 draw distance (20…110)
+152  u32 0, 0, 0xFFFFFFFF, 0            the same in every record [meaning unknown ❓]
+168  f32 (5…20, a LOD distance?)
+172  24 zero bytes
+196  u32 the piece's number in the zone
+200  8 zero bytes
```

*Retraction (2026-10-11, step 1):* the research put the piece's number at +200; it is at
+196 (+200…+207 are zeros), and +144 is a flags word, not a float 0: its only other
value, 0x20, marks trees, foliage, spinning fans, some lights and ceiling beams (CZ 54,
CW 17; perhaps "moves" ❓).

**The placement maths, confirmed** (step 1, 2026-10-11): a piece's mesh is stored around
its centre, and **world = rotation × (scale × local) + position**, with the quaternion
used as stored (x, y, z, w, as glTF; its conjugate puts CZ `z05_glass08` 3.8 m off).
How it was checked:

* *Census* (`dr2 census --levels`): for every placement, the piece's shape bounds
  (each shape's stored box, through its node, `Scene.rigid_node`) placed this way give
  the record's world bounds: 1,868 of 1,894 placements within 8 mm. 23 others hold
  pieces whose shapes store bounds that don't fit their own vertices (CZ's street
  signs and shop-window glass, CW cutscene skies): their **vertices**, placed, lie
  inside the record's bounds. 3 are unexplained and named: CZ `prologue_menu`
  `z03_hotel_top_billboard` (vertices 5.6 m outside), CW `cine_exterior_before`
  `817_sky08` (1.4 m) and `living_research_z00` `z00_decalA_01` (0.47 m).
* *Pictures*: CZ `prologue_z05` (the bowling alley, inside and out), the whole of CZ
  `prologue` and CW `living_research`, assembled and rendered in Blender: walls, roofs,
  floors, lanes and signs meet with no gaps.
* One record, CW `safehouse_z00` `glower_fl`, has a quaternion of length 1.017 (and
  scale 1, 1, 0.774); the toolkit normalises it.

Every record writes back to the stored bytes (`Placement.to_bytes`, census). Every
placement names a piece of its zone and every piece is placed exactly once, in both
games (1,894 placements, no piece placed twice). Assembled: CZ `prologue` 662 pieces,
1.70 M triangles as exported (the research's 1.26 M came from a throwaway script whose
method wasn't kept); CW `living_research` 370 pieces, 1.53 M triangles; ~22 s each with
the small textures.

**Textures.** 31,075 texture names in the pieces of both games; all found but 15 different names
(CZ: `brass_trim_CM`/`_SM`, `page_map_shinblue_cm`, `page_pendant_yellow_cm`,
`photo_paper_colour_cm`, `tiles_ceramic_sm`, `glass_store_rm`; both: `cubemap_colorgloss`,
`~Mirror`; CW: `relfection_2_dots`, `glassrefl`, `reflections`,
`metal_beams_holes_2_sm`, `grating_pitcover01_sm`, `safehouse_01`): not in the game data
at all (searched every archive). *Fixed 2026-10-11:* before phase 10, a level piece's
`.glb` took its textures from the **small** `_LOD` pack (the zone lists `<piece>_LOD.tex`
before `<piece>.tex`, and the finder didn't see `<piece>.tex` as the piece's own pack
because the scene is `_COMP_<piece>.big`). `TextureFinder` now ranks `_LOD` packs last.

**The in-game map picture** ✅ (step 5, 2026-10-11): `frontend/map.tex/map_prologue.bct`
(CZ) and `map_all.bct` (CW), 1,480 × 1,200, span exactly their level's `fe_map_points`
rectangle, x to the right and z downwards. Checked on CZ by the map areas' centres (the
bowling alley, the department store, the theatre within 20 px) and on CW by a top-down
render of `living_research` over the same rectangle (its outline is the blueprint's
lower block). **Other floors** (stretch, 2026-10-11): `map_prologue_2f` (CZ), `map_2f` and
`map_b1` (CW) are drawn over the main picture when the player is above the level's
second-floor height or below its basement height (`fe_map_points` columns 8-9: CZ
−100 / 8.0, CW −2.5 / 4.0). Where they sit, in the main picture's pixels: CZ 2f at
(238, 584) ×1, CW 2f at (168, 76) ×2, CW b1 at (688, 509) ×1, measured by fitting each
picture: the CZ 2f and CW 2f to the main map's outlines (the octagon, the outer walls),
the CW b1 to a top-down render of `storage_pens_z09`'s tunnel pieces (an exact fit). The
in-game layout files (`ingame.big/map_*.txt`) give other numbers: those widgets sit under
parents whose scale we didn't resolve (the CW 2f is off by ×0.82 there). The positions
are profile data (`map_floors`).

**The sky** ✅ (stretch, read from the `Skybox` pixel shader `db040ae0`): no texture; a
gradient by the view direction's elevation t (asin, 0 at the horizon, 1 at the zenith):
`mSkyColor1` at the horizon, `mSkyColor2` at t = `mSkyMidPoint`, `mSkyColor3` at the
zenith, linear in between, then the frame's tone curve. `skybox.big` (both games) is the
dome it is drawn on. CZ's `fortune_exterior_sky(_n)` and `fortune_exterior_canyon(_n)`
name textures (`fortune_sky`, `fortune_terrain_dirt01/02`) that are nowhere in the game
data: leftovers the game can't draw; the distant hills are pieces of zone z01.

**Which copy of a texture the game uses** ✅ (in game, 2026-10-11). A texture name
often sits in several packs of one zone, always with the same bytes (CZ 457 names, 660
extra copies; CW 1,217 and 1,803). The game takes the name from the **first pack of the
zone that has it**, whichever piece uses it: a blue `metal_corrugated_gray_cm` in
`pro_z02_shed_floor.tex` left the shed's (the safehouse bathroom's) walls grey in a recomp
capture; the same PNG in `pro_z02_garage_walls.tex`, earlier in the zone archive, turned
them blue (seen by the user in game). So the toolkit's texture finder goes by archive
order in a zone, and the mod build puts a level texture on every identical copy in the
zone (`mods.build.level_texture_copies`).

~~`MERGED_COLLISION.big` parses as a scene but has no drawable mesh (the collision
geometry is in its `persistent.big` in a form not read ❓).~~ *Read 2026-10-11, next.*

**Collision** ✅ read (stretch, 2026-10-11; `formats/collision.py`,
`convert.level.zone_collision`). `MERGED_COLLISION.big` is a scene whose skeleton has one
node per piece that has collision (named like the piece) and whose `persistent.big` holds
**Havok triangle meshes**, one group of entries per shape, `mesh<name>`:

| Entry | What it holds |
|---|---|
| `mesh<name>` (60 bytes) | 8 big-endian words, then radius, bounds min, bounds max (the shape's own vertices' box). Words 0, 2–5 are 0 everywhere; word 7 is 1; **word 1 (= word 6) is a node number of the collision scene**, 0 for none |
| `… hkCollisionShapeMesh` (44) | word 0: vertex count, word 1: triangle count; the rest kept |
| `… CollisionVertices` | vertex count × 3 big-endian floats |
| `… CollisionIndices` | triangle count × 3 indices: **1 byte each when the shape has at most 256 vertices, else 2** (big-endian; true for every shape of both games) |
| `… CollisionMaterials` | one u32 per triangle: a surface type ❓ |
| `… hkpMoppCode` | Havok's search tree ("MOPP"). **Its first 12 bytes are 3 little-endian floats, the tree's origin**: the lowest corner of the shape's vertices (5 mm below at most), then a little-endian float scale (2²⁴ / the largest extent), a little-endian u32 code size (= the entry's size − 21), one byte, the code (not read). Little-endian inside big-endian data, like the `.big` header (rule 1). Checked on every shape: CZ 465, CW 1,049 (`dr2 census --levels`, 2026-10-11) |
| `… WeldingHeader`, `WeldingInfo` | edge welding: kept, not read |

`_COLLISIONLIST_` lists the shapes; `SceneDescription` lists the nodes, then the shapes in
node order. Most names are `COL_<node>`; 3 CZ and 41 CW shapes aren't
(`z03_COL_camera_only02`, `z04_floor_COL_loco`, `wash_collision`): names that suggest
collision only the camera, or only walkers ("locomotion"), bump into ❓. **A shape is found
by its `hkCollisionShapeMesh` part, never by the `meshCOL_` prefix**: a first reader that
went by the prefix left out 45 shapes (465 / 1,049 now, CZ / CW).

**Where a shape goes** (measured on every shape; no field says it outright):

1. Its **piece**: a piece of the zone with a node of the shape's name (`<name>`, or a part
   `piece.<name>`: `z05_glass08.z05_glass01`), else of its name without a trailing `_a` /
   `_b` (CZ splits shapes that way), else the piece named by the collision node that
   word 1 points to.
2. The vertices are in that **piece's own space, node offsets included** (CW
   `z01_winglass02` lies at z = −19.3, where its node is), *or* already in world space
   (CZ `pro_z02_tank_a`), and nothing tells which ❓. The toolkit takes the placement when
   the placed shape lands inside the zone's placed pieces (their bounds, 1 m around) or
   the stored one doesn't, else the stored vertices. *Retracted on the way: the node's
   rest matrix applied on top (it counts the offset twice), and word 7 as the node.*
3. A shape with no piece is in world space (CZ 125, CW 150: grounds, fences, "decal"
   floors).

Measured: 330 CZ / 899 CW shapes placed by their piece, 130 / 150 in world space. **5 CZ
shapes are left out and named** (`pro_237`, `pro_331`, `pro_109`, `z09_object`, menu
`pro_12`: local-looking, no piece names them, word 1 is 0); and CW `storage_pens`'
`z00_COL_floor_loco` (world-looking, outside the level) is probably local too ❓. Checks:
the ground under every spawn point (CZ 18 of 20, the two misses on the menu levels; CW 29
of 35, misses on cinematic / menu levels and three in `storage_pens`), the Maps view
against the buildings in both games, and `dr2 census --levels` (every shape read, counts
by rule, the left-out shapes named).

**Materials** ✅ (step 3, 2026-10-11; read from the level shaders with XenosRecomp: a
draw's shader name, `UsedShaders.txt`, is the hash of a `deadrising*-sd.big/<hash>.sdo`
shader description listing its vertex / pixel shader pairs, one per render pass).
Level materials name a colour map, a **lightmap** (`AO_<piece>` in CZ, `LM_<piece>` in
CW, sometimes `…_NE`: baked light) and the engine's shadow / exposure samplers.

* **Lightmaps.** The `…LM…` shaders (`CM_LM`, `CM_NM_RMX_LM`, `CM_SM_NM_RM_LM_SPEC`…)
  compute, in linear light, `colour² × (lightmap² + key light × gMiscParameters.x)`
  (then fog and the frame's tone curve): the lightmap is the lighting. It is read with
  the draw's **last UV set**, always `SHORT2N` (every lightmapped draw of both games;
  the vertex shader passes it through unchanged). Lightmap and `LM` shader go together
  on every draw: CZ 3,033 and CW 6,579 draws have both (the `SHORT2N` counts above), no
  draw has one without the other.
  Every `LM_`/`AO_` name is a lightmap whatever it ends with; *fixed:* 639 slots ending
  `_NE`, `_si`, `_det`, `_sm` were read as normal, self-illumination, detail or specular
  maps (`texture_role` now says `lightmap`).
* **Blends.** `CM2DDU…` mixes the base colour map (UV 0) and an overlay (the 2nd texture,
  UV 1) by a mask's **green** channel squared (the 3rd texture, UV 2):
  `mix(base², overlay², mask.g²) × lightmap²` (CZ 72 draws, CW 10). `CM2DDX…` (CZ 1,
  CW 105) mixes by the overlay's own **alpha** (not squared) and has no mask.
* The `.glb` carries the lightmap as the material's occlusion texture on that UV set
  (`extras.dr2.lightmap` names it) and a blend in `extras.dr2.blend` (overlay, mask, UV
  sets, rule). Blender shows the colour map only; DR2 Studio's views draw both as the
  shaders do (`web/levelmaterials.js`).
* *Checked* (2026-10-11): CZ's safehouse bathroom drawn in the Maps tab from the camera of
  a recomp capture (`c0`–`c3` of Chuck's vertex shader dump: eye −294.17, 5.44, −47.31,
  53° vertical): same walls, door and framing, and the lightmap's shading where the game
  has it. The game is warmer and brighter (exposure and the time-of-day light, not drawn).

**Level text files** (`datafile.big`, not digest-checked): blocks
`cClass Name { Key = "value" }`, nested, positions `"x,y,z"`, rotations `"x,y,z,w"`.
**Read since step 2** (2026-10-11) by `dr2kit/formats/levelscript.py`, which keeps every
line so a file writes back byte for byte (census: every level script's `.txt`,
`waypoint_`, `nm_` file, `items.txt` and `missions.txt` of both games, 36 files), and
interpreted by `dr2kit/convert/placed.py`. The grammar, measured on every `.txt` of both
`datafile.big`: a header line (`cClass Name`, or a bare word such as `Vertices`), `{` and
`}` on lines of their own, `Key = "value"` (also unquoted, and with a `// comment` after
it), bare `"value"` lines (nav meshes), `//` and `#` comment lines. Five `.txt` files of
`datafile.big` are other formats (`curves.txt`, `padmap.txt`, the INI-style
`zombie_pdv_variations.txt`, CW's `sgraph_d.txt` / `sgraph_zombie_d.txt`).

A **level script** is one set `<x>.txt` + `waypoint_<x>.txt` (+ `nm_<x>.txt`): CZ
`prologue`, `prologue_safehouse` (on the `prologue` geometry: a script whose name starts
with a level folder's name uses that folder), `prologue_menu`, `prologue_menu2`; CW one
per level folder. 0 classes outside the list below in either game.

| File | Classes (CZ `prologue` / CW `living_research`) |
|---|---|
| `<level>.txt` | `cItemPlacement` 886 / 902 (`ItemName`, `Location`, `Rotation`, optional `PropState`, `IsStatic`), `cDoorPlacement` 38 / 51, `cItemWithAttachedPropsPlacement` – / 21, `cSpawnPoint` 18 / 9, `cZombieWarehouse` 24 / 11 (polygons), `cPolygonSmall` 14 / 19 (map areas; `Text` = string id), `cPolygonLarge`, `cLightContextVolume` (→ a lighting `.csv`) |
| `waypoint_<level>.txt` | `cTriggerVolume` (`Level`, `LevelSpawnPoint`: doors between levels), `cEnvironmentVolume`, `cEnvironmentAcoustics`, `cAudioMaterial`, `cWaypoint` |
| `nm_<level>.txt` | the navigation mesh: `Vertices { "x,y,z" … }` then polygons |
| `fe_map_points*.csv`, `fe_map_*_f1/f2/b1.csv` | the in-game map: each level's map rectangle; rooms (string ids) and points (safehouse, workbenches, save points) |
| `prologue.csv`, CW `epilogue_*.csv` | light by hour (24 columns): spherical-harmonic ambient matrices (`mSHRenderMatrixRed.00`… 4×4 per colour: irradiance = nᵀMn, n = (x, y, z, 1)), fog (`mFogColour`, `mFogStart`, `mFogEnd`, `mFogMax`), key light colour and direction, the sky (`mSkyColor1/2/3`, `mSkyMidPoint`), tint, exposure, bloom, depth of field… A level's `cLightContextVolume`s say which table lights which area (`QuadName` polygon; CW also a `DarkContextFileName`, presumably with the power off ❓) |
| `zombiesets.txt` | zombie types and counts per level and time of day |

**Zombie spawns are in `missions.txt`**, not the level files (researched for phase 11,
2026-10-11): inside each `cMissionDefinition` → `cMissionLevelReady`,
`cMissionZombieFactory` (CZ 33 / CW 72: `ZombieWarehouseName`, `Type0…`/`Amount0…`,
clumping), `cMissionSpawnZombie` (137 / 155: `SpawnPoint`, one-angle `Rotation`,
`ZombieType`, `SpawnWithItem`), `cMissionSpawnZombieCrate` (23 / 60: respawns),
`cMissionZombieRemoval` (44 / 29), `cMissionAdjustZombieTuning` (2 / 7:
`MaxNumUpdatingZombies` = 120 in CZ's street). A factory's area is a `cZombieWarehouse`
of the level file (all of CZ's exist; CW names one undefined, `ArenaStairs`).
Drawn (phase 10 stretch): every factory of a level resolves its type (`zombies.big/<type>.big`,
detail `_2`/`_3`/`_4`) and its area in both games: CZ `prologue` 22 crowds, CW
`living_research` 32 (9 types).
`zombiesets.txt` (generated, "do not edit by hand") lists the zombie types each level
loads, by time of day, with a memory cost per type. The text files use CRLF, tabs and
alphabetically sorted keys.

**Writing blocks in the tool's style** (phase 11 step 1, 2026-10-11; measured on every
block-format `.txt` of both games, `levelscript.render`): one tab per nesting level,
`Key = "value"` (one space each side of `=`), keys sorted **ignoring case**
(`REMOVE_BEFORE_SHIP` before `ShowInDebugMenu`; plain ASCII order would put it first and
fails on 399 CZ `items.txt` blocks), properties before child blocks, no blank line between
the last key and the first child, one blank line after each child (also after the last,
before the parent's `}`), one blank line between top-level blocks (two between
`missions.txt`'s missions; `prologue_menu.txt` mixes 1 and 2). No block name holds a `/`
or a space, so a block is addressed by its **path** `cls name/cls name/…`; a path names
one block except in nav meshes (unnamed `PolyhedronEdges`) and the hand-written
`sgraph.txt` / `animated_postfx_events.txt`. `render` writes back every block of the
files a mod can edit (the scripts' three files, `missions.txt`, `items.txt`) exactly as
shipped, **except** CZ `items.txt` `cBikeItem BrokenBike` (one key out of order) and the
hand-written `zombiesets.txt` (its own key order and `// cost` comments): CZ 5,468 blocks
written back / 11 not, CW 7,447 / 29 (`dr2 census --levels`). Those blocks are only ever
changed key by key, and a changed value keeps the line's `// comment`.

**Level edits as mods** ✅ (phase 11 step 1, 2026-10-11; `formats/leveledits.py`): a mod's
`replace/data/datafile.big/<file>.txt.edits.json` holds `set` (path → keys; `null`
removes a key), `add` (path → keys, nested objects are child blocks, `@after` places it)
and `remove` (paths). The build applies every mod's edits over the copy underneath (the
recomp's `game_patched` one when it has the file, so the CZ co-op changes to
`missions.txt` stay; checked on a real build 2026-10-11), lowest priority first; the same
key of the same block in two mods at one priority is a conflict. Gate (census):
for 30 blocks spread over each editable file, an edit that changes a key, removes the
block, adds a key and removes a key, each applied and then reversed with `diff`, gives
the original: CZ 1,003 byte for byte + 37 the same apart from blank lines, CW 1,476 + 84,
0 different. `convert/levelcheck.py` checks what the edits mean (an `ItemName` of
`items.txt`, a zombie type of `zombies.big`, a factory's area in the level file, a type
not in the level's load set → warning, quaternions of length 1…).

**Level edits in game** ✅ (phase 11 step 2, Case Zero recomp, 2026-10-11; the user played
each build, a headless bisect named the cause of the one that failed):

| Change (all as `.edits.json`) | In game | An old save |
|---|---|---|
| Items added to `prologue.txt` (`SledgeHammer`, `Workbench`, `MilitaryBarrier`) | the hammer is picked up and used, the workbench combines, the barrier (`cUtilityItem`, `Unmoveable`, `CollisionType 3`) **blocks the player**: an item with engine-made collision works as a wall | loads |
| A save point added to `waypoint_prologue.txt` (a clone of `UncleBills_SaveTrigger`, `ActionType 4`, moved) | the prompt shows, saving works | loads |
| Values and new keys in the game's mission blocks (all 22 street crowds' `Type<n>` and 125 single zombies' `ZombieType` → `zombie_fat`, then `zombie_cop`; crates' `ZombiesPerSpawnTime 0`; a new `Type3`/`Amount3`) | the whole street showed the new type | loads |
| **A block added inside one of the game's missions** (a `cMissionSpawnZombie` in `PrologueZombies/PrologueZombieReady`, any zombie type) | **a new game stalls when it first writes the save** (headless: nothing after `save:\DR2P000.DSF`; the user's run crashed, guest fault at address 8) | **doesn't load** |
| A mission of the mod's own (a new top-level `cMissionDefinition` with the keys of `PrologueZombies`, a `cMissionLevelReady` and spawns) | **runs in a new game** (both packs of 8 showed); **doesn't run** from a save made without it | loads |
| A zombie type the level doesn't load (`pro_zombie_cop` in `LEVEL_PROLOGUE`, 8 at once) | **showed** (no crash) | — |
| A spawn point added to `prologue.txt` (a clone of `BowlingExit`) and the safehouse's exit trigger pointed at it (`LevelSpawnPoint`) | leaving the safehouse puts Chuck there | loads |
| A door to another level added to `waypoint_prologue.txt` (a clone of `Safehouse_entrance`, `ActionType 3`, `Level` / `LevelSpawnPoint` set) | the prompt shows, pressing it goes into the safehouse | loads |
| **A save made while a mod's own mission runs, loaded without that mission** (no mods, or another mod) | **crashes while loading** (guest fault at address `0x78`, right after reading `DR2P000.DSF`) | — |
| A new item: a new pack `streamedassets.big/Dr2kitHammer.big` (the sledgehammer's, its scene and texture packs renamed) + a new `items.txt` block, placed in `prologue.txt` | first **an endless loading screen** (the new entry declared `flags` 0); with its siblings' 2048 it **shows, is picked up and works** | loads |

So a save made with a mod's own mission needs it from then on (the toolkit warns,
`levelcheck.SAVE_NEEDS`; a "keep my save" mod is that mission with no zombies). The save
holds the state of every mission, in a form that a block added inside a
mission breaks (two missions of the same structure plus one: likely a fixed layout or
count ❓), while it simply doesn't know a new mission (never started from that save).
The toolkit refuses a block added inside a game mission (`levelcheck.SAVE_BREAK`) and puts
new mission things in the mod's own mission, saying they need a new game. **Case West** (new game, the Storage Pens, 2026-10-11): an added Katana, a new item
(`Dr2kitKatana`, a Katana pack copy with a red texture, by recipe), a workbench, a save
point cloned from `LabsSave1` (its world-space corners moved with it) and the Humvee
blocker all work; every crowd and single zombie retyped to `zombie_fat` shows. Not seen:
whether the mod's own mission's 8 `zombie_security` showed (unchecked), the save-loading
rules (CZ facts until CW agrees, rule 7). A placed item stands by its *origin*: the
Humvee's is its middle, so it sank; Studio now drops a newly placed item onto the floor by
its bottom. **The CZ recomp's `game_patched/data/datafile.big` differs
from the shipped one in `missions.txt` and `outfits.csv`** (its co-op edits); CW's recomp
has no `game_patched`.

**Piece edits** ✅ (phase 11 step 4, Case Zero recomp, 2026-10-11/12; the user played
each build; `formats/pieceedits.py`). A mod changes a zone's **buildings** (level
pieces) with `ZONE_ORGANIZATION.big.pieces.json` next to the zone's
`ZONE_ORGANIZATION.big` (per piece name: `position`, `rotation`, `scale`, `hidden`;
`copies`: new records), and their **collision** with `MERGED_COLLISION.big.pieces.json`
next to `MERGED_COLLISION.big` (per shape group `meshCOL_…`: `move` in the shape's own
space, `hidden`). A hidden piece keeps its record, moved 1,000 m under the level (no
record moves, the count stays); a copy is a new record appended (`NumModelInstance`
grows) with the piece's name and number. World bounds of a changed record are worked out
again (the shipped box taken back to the piece's space and placed anew). A collision
shape is moved by adding the offset to its vertices, its search tree's origin (above)
and its header bounds; the tree itself is left as it is, so collision can be **moved or
sent away, never turned or resized** (that needs Havok's tool).

| Change | In game |
|---|---|
| A sign hidden (its record parked), a car moved 4 m and made 1.5× bigger, a building (`z04_gen_e_structure`) hidden, all by record only | the pieces went or moved, no crash; **the hidden building's collision stayed** (an invisible wall), and so did its boarded windows and writing (other pieces: `_details`, `_decals`) |
| A copy of a van (a new record) | **shows, but has no collision** (walked through) |
| The store hidden as a whole building: its 3 pieces parked and its 2 collision shapes (`pro_351` world-space, `z04_camera`) sent 1,000 m down | **all gone, collision too**: walked through where it stood |
| The next building (`z04_gen_f_*`, 3 pieces) moved 4 m toward the street with its 2 world-space shapes | walls and collision at the new place (checked by the user, 2026-10-12) |
| The sheriff's office hidden as a whole (15 pieces, 29 shapes, many stored in their piece's space) | all gone, collision too |

So **collision is not tied to a piece's placement record**: the engine places every
shape from its own vertices (a world-space shape like `pro_351`), and a shape stored in its
piece's space is not moved by the piece's record either (the sheriff's interior shapes
went away only when they were sent away themselves). Studio therefore moves and hides a
building's collision with it. Not measured: whether a copy can get collision (it would
need new shapes in `persistent.big` and `_COLLISIONLIST_`).

**New pieces** (phase 14, built 2026-10-12; **in game: test T4a**, `phase14-kickoff.md`).
A piece the game doesn't have is three new entries of the zone archive, made by copy
recipes from a game piece (`mods/newitem.py`): `<new>.big` (the piece archive, its scene
`_COMP_<new>.big` renamed with it, the modder's `.glb` shape fitted into the template's
first shape: `convert/weapon_fit.fitted_glb`), `<new>.tex` and `<new>_LOD.tex` (the
template's texture packs with the modder's picture, full size and the `_LOD` size). **The
picture gets a texture name of its own** (`texture_names`: the `.bct` entry and the
material slot's name at +4…+0x37; the word at +0x38 is the sampler's hash and stays),
because a zone shows the first texture of a name it finds (above). Its record is a `new`
entry of the `.pieces.json`: the record of a `like` piece (unknown bytes, flags, LOD
distance) renamed, numbered past the zone's highest piece number (+196 is **not** the
piece's place in the archive: z05's 19 pieces carry numbers 2…20 in another order, z03's
126 numbers up to 205), its own box placed for the world bounds, centre and radius, and
its `draw_distance`. Template used by the test: `z02_hardware` (shader `LIT_CM`: lit,
colour map only, **no lightmap**: 40 such pieces in CZ's street; 256 use `CM_LM`, whose
lightmap a new shape has no UVs for).

**Buildings** (`convert/buildings.py`, 2026-10-11/12). The game has no building object: a
building is several pieces (walls, boarded windows, writing, roof units) and one or more
collision shapes, often with no name in common (the store's walls are `pro_351`). The
toolkit groups them, a guess checked on CZ's street: pieces biggest first; a piece joins
the smallest building whose box (1 m larger) holds 80 % of its box, or whose first piece's
name shares its stem and overlaps 30 %, or on whose top it rests (its footprint inside,
its bottom within 0.5 m of the top: the store's air unit, left floating by the first
grouping), and it must touch the building's collision (0.5 m) when the building has some
(a car park's fence holds the cars in its box but doesn't touch them); a building whose
collision it touches comes first. Pieces over 60 m wide, or flat (under 2.5 m high and
over 8 m wide: slabs, car parks), never lead a building. A collision shape belongs to its
piece's building, or to the smallest building whose box holds it. Counts (census): CZ
`prologue` 297 buildings, 115 with collision, 221 single pieces; CW 247, 72, 187. Big
enclosures (CW's lab rooms) take their contents: the modder can move a piece to another
building or on its own in Studio (kept in the config folder, `buildings.json`).

CZ's levels in these files are `LEVEL_PROLOGUE`, `_SAFEHOUSE`, `_BOWLING`, `_DEPARTMENT`,
`_MENU`: several share the `prologue` geometry.

**Items → models** (step 2, 2026-10-11: **every placed item and door of both games
resolves**, CZ 1,060, CW 1,835, and each model parses; `convert.placed.ItemModels`).
`ItemName` names a block of `items.txt`, which may give `MergedFilename`
(`data/dynamicprops/arifle`) and `AssetFilename` (`m16`, or a path). The model is a
**pack** `data/streamedassets.big/<X>.big`, X being the first found of: the
`MergedFilename`'s name, the item's own name (CZ `Chair_3.big`, `CardboardBox.big`), the
`AssetFilename`'s name. The pack is either the scene itself (it has a `SceneHeader`: CZ
`HotDog.big`, `atm.big`) or holds it as `<AssetFilename's name>.big` (CZ `arifle.big` →
`m16.big`; `Beer.big` → `beerbottle.big`), else the entry named like the pack, else its
only scene; beside it are `<name>.tex`, `<name>_LOD.tex` and an icon `w_<name>.bct`.
*Retraction:* the research's "CZ: 577 of 1,059 resolve" looked for `<AssetFilename's
name>.big` at the top of `streamedassets.big`; CZ's packs are named after the item.
**Texture variants:** some packs hold empty `.big` entries beside the scene
(`adboard_cafe.big`, `pool_ball_blue.big`, `door_standardknob_burnt.big`) and a `.tex`
per variant; placements choose one with `TextureSubType` (1…7) ❓ (the toolkit shows the
default texture).

What the classes hold (counts: CZ `prologue` / CW `living_research`):

* `cItemPlacement` (891 / 923 with nested and attached-prop ones): `ItemName`,
  `Location`, `Rotation` (quaternion, same convention as the zone placements: items
  rendered on their tables and shelves), optional `PropState` (−8…4), `IsStatic`,
  `TextureSubType`, `SpawnPropFromCategory` (a random item of a category ❓). Placements
  **nest** (CZ `HotDog3` holds 5 more, world positions too). `cItemWithAttachedPropsPlacement`
  adds `AttachedProp0…5` (item names put on the item's locators ❓; not drawn yet).
* `cDoorPlacement` (38 / 51): as items, plus `InitialState`, `Level` / `LevelSpawnPoint`
  (doors to other levels), `SiblingDoorName`, `KeyItem`, `LockedMessage`.
* `cSpawnPoint` (18 / 9): `Location0` (player 1; `Location1…3` in a few: other players),
  `Rotation0` an angle about Y in **radians**, `CameraHeading` / `CameraPitch` in degrees;
  a few have a second `Location` (CZ `184.750,3.734,-319.031`, far outside the street ❓).
* `cZombieWarehouse` (24 / 11): named floor polygons (`cPolygonSmall`/`Large` children).
* `cPolygonSmall` / `cPolygonLarge`: `Vertex0…N` (the keys are sorted as text, so
  `Vertex10` comes before `Vertex2`), `Height` (a prism upwards), `Text` or
  `LevelRegionText` = a string id: **map areas** (`PR102` = 1712 "Junkyard"). A
  polygon named by a `cLightContextVolume`'s `QuadName` is that **lighting area**
  (`ContextFileName = "/prologue.csv"`), not a map area.
* `cTriggerVolume` (13 / 34): `Location`, `Rotation`, a unit quad `Vertex1…4` and
  `Height` or a `Radius`, `ActionType` (3: go to `Level` at `LevelSpawnPoint`; 4, 28, 36,
  57, 58 ❓), `DisplayName` (a string id).
* `cEnvironmentVolume` (223 / 178): boxes (`Translation`, `Rotation`, `Scale`) that pick
  the acoustics (`AcousticsName`); `cEnvironmentAcoustics`, `cAudioMaterial`: reverb
  settings; `cWaypoint`: two per file, at the origin.
* `nm_<x>.txt`: `Vertices { "x,y,z" … }`, `Polyhedrons { PolyhedronEdges { mask = "3"
  "12" "13" … } … }` (each a polygon of vertex numbers, all in range), `Connections { }`
  (empty everywhere). CZ `prologue` 729 polygons, CW `living_research` 690.
* `fe_map*.csv`: map rectangles per `LEVEL_*` (`fe_map_points*.csv`: `min_x, max_x,
  min_z, max_z` in columns 4-7, then the basement / second-floor heights), room rows
  (`pr101, 1709, …`: string ids), and **points**: `workbench_1, -186.4, 3.4, -114.2,
  LEVEL_PROLOGUE` (workbenches, save points, the safehouse).

### Level slots: the executable's level table 🟡 (phase 14, 2026-10-12)

Level ids (`LEVEL_PROLOGUE`, `LEVEL_FOOD_BARN`) are an enum compiled into the executable,
with two tables of 82 pointers in the same order (CZ `default_image.bin`): **script
names** at `0x829D4DFC` (a second copy at `0x829DBB64`): `americana_casino.txt`,
`arena_backstage.txt`… `prologue.txt`, `prologue_bowling.txt`, `prologue_menu2.txt`,
`prologue_menu.txt`, `prologue_safehouse.txt`… `food_barn.txt`, `fortune_exterior.txt`…
16 × `testlevel.txt` at the end; and **zone lists** (relative to
`data/models/environment/`) at `0x829D5F7C`: `americana_casino/zonelist.big`…
`prologue/zonelist.big` (twice: the street and the safehouse **share** it),
`prologue_bowling/zonelist.big`, `food_barn/zonelist.big`, `fortune_exterior/
zonelist_rooftop_hotel.big`… and 16 developers' test levels (`z_frank/zonelist.big`,
`z_vincent/…`, all with `testlevel.txt`). Case Zero ships the files of 4 slots
(`prologue`, `_safehouse`, `_menu`, `_menu2`); the others are **empty slots**.

What a level is made of, read from the shipped ones:

* `data/datafile.big/<script>.txt` (spawn points, items, doors, zombie areas),
  `waypoint_<script>.txt` (trigger volumes: doors, save points), `nm_<script>.txt` (the
  navigation mesh);
* its zone list; **a zone list names its zones as `folder/zone`** (`prologue/prologue_z05`),
  so a slot's zone list can name another level's zones: the safehouse script plays on
  the street's zones this way;
* named by level id elsewhere: `zombiesets.txt` (`cZombieLoadSet LEVEL_<X>`, also in
  `persistent_filecache.big` and `preload4.big`'s copy), `fe_map_points_<level>.csv` (the
  in-game map), `missions.txt` (`LevelRequiredToStartName`), cutscenes
  (`PreferedLevel`).

**A map of one's own** (test T5, built 2026-10-12, not yet in game): the slot's script
files as copies (new entries of `datafile.big`), its zone list as a **new file**, and a
door (`cTriggerVolume`, `ActionType 3`, `Level = LEVEL_<SLOT>`) to it.

**`layout.bin`** (the game root, opened first: CZ `0x82786230` reads it) is the game's
table of loose files: 238 records (CZ) of 152 bytes: the path (128 bytes), a hash word,
the size (big-endian, +132), the file's position on the disc (64-bit, +136: each file
starts where the one before ends, rounded up to 0x800, but for 11), 8 zero bytes. The game
**works each name's hash out itself** when it reads the table (and keeps its own when the
stored one differs), then looks files up by it; the size pins how much is read (phase 13:
a grown file is cut short). The build writes a record for each **new** file (hash 0, its
size, a position after every other file: `mods.build.new_layout_record`). Whether the game
needs the record, or reads a file missing from the table at all: test T5.

### Zombie types: a table in each executable 🟡 (phase 15 research, 2026-10-12)

A zombie type is a model name of `data/models/zombies.big` (`zombiesets.txt` and
`missions.txt` name them), and each program holds its **own table of type names** (with
a debug "override" list next to it): **Case Zero 32 types**, Dead Rising 2's whole list
(`zombie_fat`… `zombie_waitress`, `looter`, `mercenary`, `mercenary_army`,
`mercenary_pheno`, `mercenary_tk`, `soldier`, `zombie_gas`, `pro_zombie_bowling`,
`pro_zombie_trucker`, `pro_zombie_cop`), of which it ships models for 12; **Case West 10**
(`zombie_fat`, `zombie_fat_female`, `zombie_skinny`, `zombie_skinny_female`,
`zombie_gas`, `security_heavy`, `security_lab`, `security_light`, `security_light_hat`,
`zombie_security`), all shipped. Both programs carry `GasZombie` code. Found by the
strings' pointer arrays (CZ near `0x829DD2C4`, CW `0x829F03C0`); whether a type with no
model of its own works when given one: `phase15-kickoff.md` U2.

**What a type is in the data** (phase 15 step 4, 2026-10-13): besides its table name, a
type is (1) its model pack `zombies.big/<type>.big`: detail levels `<type>_2/_3/_4` (`.big`
scene + `.tex` + `_LOD.tex`, some empty), (2) a `cZombieClassItem <type>` block of
`items.txt` (health, damage multipliers, `BehaviourNames<n>` / `ChanceOfBehaviour<n>`):
**Case Zero has one for all 32 names**, shipped or not; Case West for its 10, (3) the
`cZombieBehaviourItem` blocks it names (Case West adds `EnemyRanged`, `EnemyHazardUnit`,
`EnemyZombieController`; Case Zero's program knows the class), (4) its entries in the
levels' load sets (`zombiesets.txt`, with a cost per type: CZ 752-6,176, CW 768-5,556; a
level's `total_cost` peaks at CZ 18,304 / CW 23,436). `zombiesets.txt` has byte-identical
copies in `data/datafile/persistent_filecache.big` and `preload4.big`'s copy of that
archive; which one the game reads ❓ (test U2). **Growing Case West's table is more than a
count:** the five functions that walk it (CW `sub_822FC948`, `sub_82499870`,
`sub_82585158`, `sub_82587190`, `sub_82588390`; CZ `sub_82300068`, `sub_82490780`,
`sub_825B3670`, `sub_825B5B98`, `sub_825B6FC8`) are the same code apart from the count
(10 / 32), but the object they work on keeps per-type arrays **inline**: a byte per type at
CW `+700` / CZ `+2196`, and its later fields sit at CW `+1812…` / CZ `+3352…`, about 70
bytes more per type, so Case West's object would have to be re-laid out (2026-10-13).
Deferred, written up for a contributor: [`TODO.md`](TODO.md) #1. *Retraction (2026-10-13):*
the phase 15 note that the type is "checked against 31" (CZ `0x823000BC`, CW `0x822FC99C`)
misread the name → type lookup: that compare is on a byte of the looked-up name's string
object (inline text or a pointer), so no engine limit on the number of types is proven.
**Case West's types in Case Zero, headless** (2026-10-13, a copy of the user's save, every
street crowd and single zombie retyped): `security_light`, `security_heavy` and the gas
zombie (each in an empty slot, its load-set entry added) load into gameplay; together
(gas + `security_light`) too. Whether they show, walk, fight and gas: the user's test U2
(the night street near the safehouse shows no zombie in view even unmodded).

**Shaders across the games** (same research): a model's shader descriptions
(`-sd.big`) are shared by name between the games (CZ 223, CW 231, 222 in common), the
shader programs they list are compiled differently in each; the descriptions models use
that the other game lacks: CW `ZombieGlow`, `ZombieClothRGBSpec`,
`ZombieClothRGBReflective`, `CM_SIX`, `Larvae` and CZ `Larvae` (`phase15-kickoff.md`).

### Across the games: shader banks 🟡 (phase 15, 2026-10-12)

Measured over every entry of both games' `data/shaders/deadrising{prologue,epilogue}-*.big`
and every scene's `UsedShaders.txt` (`tools/crossgame_table.py` writes the lists to
`dr2kit/profiles/crossgame.toml`):

| Bank | CZ | CW | Same name | Same bytes |
|---|---|---|---|---|
| `-sd` descriptions `.sdo` | 223 | 231 | 222 | 46 |
| `-vs` vertex shaders `.vo` | 143 | 146 | 143 | **0** |
| `-vd` `.vdo` | 143 | 146 | 143 | 143 |
| `-ps` pixel shaders `.po` | 1,280 | 1,338 | 45 | **0** |
| `-pd` `.pdo` | 1,279 | 1,337 | 44 | 38 |
| `-sc` value sets `.scv` | 149 | 265 | 149 | 0 |
| `-ss` `strings.bin` | 1 | 1 | 1 | 0 |

All seven banks are also inside `data/preload4.big` (like the effects: the build evicts
the nested copy of a bank it changes).

* **A description** (`.sdo`, named by the hash models put in `UsedShaders.txt` and the
  draws' `0x3C`/`0x3F` commands): `u32 hash, u32 link, u32 n`, then `n` pass records
  `{0, flags, vertex shader hash, 0, pixel shader hash, 0}` (`0xFFFFFFFF`: no pixel
  shader), then its name (`u32 length` with the NUL, text: `ZombieGlow`), `Default` and
  lists of numbers. `link` is `0xFFFFFFFF` or (CZ 106, CW 105, the `CM_…` level shaders)
  a hash that names no bank entry, the same in both games (`CM_LM`: `d55e4300`) ❓.
  Shared names mostly carry the same hash (only `Larvae` differs: CW `0064b9a0`, CZ
  `630cee60`), but the programs they list are compiled differently in each game: a
  vertex shader of the same name never has the same bytes. Every program a description
  names is in its game's banks (census).
* **Value sets** name their pixel shader by hash (§Materials), so a Case West material
  points at a Case West pixel shader: Case Zero has only 45 of their names.
* **`.pdo`** (one per pixel shader): `u32 hash, u32 n`, `n` parameters, `u32 word` (0
  or a hash ❓), `u32 hash` again. A parameter: its name (`u32 length` with the NUL, padded
  to 4: `gGlowScale`), a hash (`c1a23fc0`: the same in both games, and the hash a value
  set's record carries), a **parameter number**, `0`, a type (1-4: float … float4), a
  register count, 4 flag bytes; when flag byte 1 is set a slider follows: `1 + 3 × type`
  words (a word, then min, default and max per component) and a label (`Glow Scale`).
  **`.vdo`**: a vertex-input header, then the same `hash, n, parameters, word` without
  the trailing hash. The numbers are a **registry per game and stage**: in the pixel
  files each number has one name (CZ 100 numbers, CW 109); vertex and pixel files reuse
  numbers for different names (`17`). 41 of the 99 pixel names both games use have
  another number (`gDiffuseColourControl` CZ 157, CW 159), and CW's `gGlowScale` 187 is
  CZ's `gBodyPart4Colour`: a pixel shader brought across gets the target's numbers, and
  a free number for a name the target lacks ❓ (in-game test U3).
* **`strings.bin`**: `u32 count`, then `count` entries `{u32 length, the text, NUL,
  padded to 4}`, the first one empty: shader file names (`PosUVFullScreen.bvd`,
  `CM_LM.bpd`, `LT-ZombieGlow.bpd`) and parameter names. CW has 26 more (its own shaders
  and their parameters), CZ one CW lacks. ❓ who reads it, and by number or by text.
* **Engine samplers** named differently: on `ProtoSkinnedEye`, `ProtoSkinnedLens`,
  `ProtoSkinnedClothReflective`, `ZombieEye(LOD2)` the reflection cube slot is
  `gCubeEnvMapSampler` (`e9196ce0`) in CZ and `gReflectionTexture` (`1f61c700`) in CW
  (slot record +0x38 word; the draws bind it with command `0x33` and the same hash).

**The engine's limit on pixel shaders: the "Shader Constant Sets" pool** (measured
2026-10-12, Case Zero, headless loads of a copy of the user's save). Adding Case West
pixel shaders to Case Zero's `-ps.big` (its `preload4.big` copy evicted, `layout.bin`
re-pinned): 1, 20 and 26 more load to the street; 29 crash while the street loads, 33,
40 and 45 crash right after the game opens the bank, on the assert
`INVALID_HANDLE != shader_constant_set_handle && "Shader constant set overflow."`
(`shaderconstantsetstack.cpp`, CZ `sub_827B0BB8` → free list `sub_82195EF8` returns -1).
Bringing the vertex shaders alone, and with them evicting and re-reading the banks,
loads fine. The renderer builds its pools from a **table of sizes in the executable's
data**: CZ `0x829ED7F0` = `192, 384, 768, 18, 13824, 128, 8, 128, 256, -1, 1024, 512`,
CW `0x82A00D30` the same but **`1340`** in place of `384`: Case West ships 1,337 pixel
shaders, and the second value builds the pool kept at renderer `+3492` (CZ `0x827BEF48`:
`lwz r4, 0x829ED7F4`). So the pool holds one constant set per loaded pixel shader (CZ:
~358 used of 384, CW: ~1,337 of 1,340) ❓ the exact count used. **Bringing shaders past
this needs the pool grown** (a recomp change: the value set at boot), in both games.
*Retracted 2026-10-12 (the same day): Case Zero's pool is not 384.* The boot budget
function `sub_825D37C8` (called unconditionally) stores **1300** over both `0x829ED7EC`
(420 in the image) and `0x829ED7F4` (384) before the renderer reads them, so CZ runs
1,280 pixel shaders against 1,300 sets (~20 free, which fits the 26 / 29 measured above);
Case West's 1,340 is its image's own (no store to it). **Two pools limit brought pixel
shaders**: the constant sets (CZ `0x829ED7F4`, renderer `+3492`; CW `0x82A00D34`, `+3504`)
and the pool beside them (CZ `0x829ED7EC`, `+3480`; CW `0x82A00D2C`, 1,340, `+3492`).
Case West showed the second: with only the first grown, 14 brought pixel shaders faulted
while the save loaded (a failed allocation, then a read of address `0x1C`), 1 loaded.
**Grown in both recomps to 4,096 each (2026-10-12)**: each hooks its renderer's pool
builder (CZ `sub_827BE658`, CW `sub_8275A168`) and raises both words just before it reads
them; off switch `CZ_/CW_NO_SHADER_POOL_GROWTH=1`, log `[shaderpool] … 1300 -> 4096`.
Checked headless on copies of the user's saves: the Laser Sword (45 Case West pixel
shaders) plays in Case Zero; 14 Case Zero pixel shaders, and the Parasol with them, play
in Case West. (ARCHITECTURE.md §Recomp integration 4; the recomps' gotchas 643 / 332.)
**A third pool: one per shader description** (2026-10-13): CZ `0x829ED7E4` (128 in the
image, the boot stores **228**; 223 descriptions shipped), renderer `+3472`; CW
`0x82A00D24` (the boot, `sub_825A6000`, stores **231**: exactly its 231 descriptions,
none free), `+3484`. Case West's gas zombie brings 8 descriptions: Case Zero's free list
returned -1 in `sub_827D4CD8` and the fallback faulted at guest `0x8` while the title
drew. Grown to 4,096 with the other two in both recomps. A pool sized 192
(CZ `0x829ED7F0`, CW `0x82A00D30`; renderer CZ `+3488`) sits beside them; its size is
close to the vertex shader counts (143 / 146) ❓ not measured, not grown.

### Across the games: constant registers ✅ read and moved (phase 15, 2026-10-13)

**A shader parameter's number is its constant register.** In every pixel shader of a
game, a parameter's register in the program's constant table (the D3DX table inside the
`.po` container) is its `.pdo` number (census: 1,280 CZ and 1,338 CW pixel shaders, every
name one register, the same as the `.pdo` registry). Each engine writes its parameters at
its own numbers, and the programs were compiled against them. The games differ on **41
of the 95 pixel parameter names they share**: Case West inserted `gPowerOffParameter` at
c17, so its `gBumpLightParameters` (18), `gFogParameters` (19), `gShaderDebugParameters`
(21), `gPointLight0Parameters` (22), `gKeyLightParameters` (24),
`gCascadedShadowLightMatrices` (29), … are one higher than Case Zero's (17, 18, 20, 21,
23, 28); the shift grows further up (Case West's `gBodyPart1Colour` 191, Case Zero's
184). **Vertex shaders agree** (53 names, the same registers), **texture slots agree**
(samplers are per program, the same in both games' programs of a description), and no
program of either game uses bool or integer constants.

So a program brought from the other game must read the target's registers:
`dr2kit/formats/xenos.py` walks the microcode (the control-flow exec blocks and their
sequence bits, as the hardware and XenosRecomp do), finds each ALU instruction's constant
operands (a source whose select bit is 0; `src3` of the scalar `mulsc`/`addsc`/`subsc`
ops always) and renumbers them; the constant table's entries move with them, so the
recomps' translator names them right. Every constant register any program reads is named
by its table or is one of its own literals (c248-c255): **0 unnamed** over all 2,907
programs of both games. Names only the source game has (Case West's `gPowerOffParameter`,
`gGlowScale`, `gGlowSpeed`, `gGlowWaveLengthScale`, `gMultiplierGlowSI`,
`gSpecularScale`, `gReflectionScale`, `gCharRimLightIntensity`, `gCamHUDFXParameters`,
`gCameraTexParameters`) get registers no program of the target reads, in the gaps below
the target's highest (Case Zero: 43, 51-59), and the brought `.pdo` names the same
numbers (`shadercarry.number_map`). All 1,337 Case West pixel shaders move into Case
Zero's registers, and all 1,279 Case Zero ones into Case West's, without a clash. ❓ how
the engine fills a register only the brought shaders read (the value set's value at the
`.pdo` number, or nothing): U1/U3.

The descriptions differ too ❓: Case West's `LIT_CM2DDL_NM_RMX_SPEC` has 30 passes, Case
Zero's 28 (Case West adds a pass with flags `0x210` after `0x200`, and one more shadow
pass); whether the engine picks a pass by its flags or by its place is not known (the
brought description keeps Case West's passes).

**Scenes: `_BONEHIERARCHY_` is Case Zero's, and its program needs it** (2026-10-12).
Every streamed item scene of Case Zero has the chunk (192 of 192; 1,485 scenes in all) and
**no scene of Case West does** (0 of 237 item scenes, 0 anywhere): Case West's program
copes without it. Case Zero's does not: placing an item whose scene lacks it **hangs the
load** on the loading screen, no fault: the main thread loops in `sub_827ACAD8`, which
walks a node's parents through the (index, parent) pairs (found by attaching `gdb` to the
stuck recomp; the recompiled functions are native frames named `sub_…`), while two
threads wait on locks it holds. Bisected on the Laser Sword (headless): its block with
Case Zero's Broadsword pack loads, Case West's pack hangs with or without its shaders,
move bank and sounds. So a Case West scene going into Case Zero gets the chunk written
from its node records (`convert/crossgame.fit_scenes`, profile `scene_hierarchy`), right
after them, stored, `flags` 4, as Case Zero's own; the Laser Sword then plays. Pair
order: Case Zero writes parents first, sorted by (depth, parent, index) in 1,473 of 1,485
scenes (the other 12, two-root rigs, parents first in another order;
`Skeleton.hierarchy_pairs`). Case Zero's scenes going into Case West keep theirs (both
programs name the chunk; the Parasol plays in Case West with it).

All of it is read and written by `dr2kit/formats/shaderbank.py`; `dr2 census` checks every
description, parameter file and string table of both games writes back byte for byte (0
problems, 2026-10-12).

*Decision (user, 2026-10-12):* a model brought from the other game draws with **its own
game's shaders**, copied into the target's banks (not remapped to the nearest one), and
the recomps translate them (both already translate a shader they meet for the first
time, at the first draw that binds it).

**The PC games** (phase 16 research): the same `.big` index; compressed entries are zlib
behind a 4-byte big-endian uncompressed size; payloads little-endian (a skeleton node
record is the console's byte-swapped); `.bct` headers differ (`phase16-kickoff.md`).

## Weapons: `items.txt` blocks, elements, effect numbers 🟡

Phase 12 (2026-10-12). A weapon is a `cPlayerWeaponItem` (or `cFirearmItem`,
`cExplosiveItem`, `cSprayItem`…) block of `data/datafile.big/items.txt`; its keys are
listed in `docs/phase12-kickoff.md` §What the research found. Measured here:

### Effect numbers: one table in the executable ✅

Every `EffectOnVictim<n>`, `EffectOnImpact<n>`, `EffectOnWeapon<n>`, `PyroEffect<n>`,
`ThrowEffectOn*` and `zombie_effects.txt` number is **a 1-based index into one table of
particle effects compiled into the executable** (0 = none): 12-byte records `{char*
name, u32, u32}`, CZ 371 at file offset `0x9D24F0` of `default_image.bin`, CW 414 at
`0x9E69A0`; **the first 370 are the same in both**, then CZ's 371 is `roadflare_env_c_1` and CW's 371 `groundblast_wpn_dbs_1` (retracted 2026-10-12, phase 13: "the first 371 are the same" — `tools/effect_table.py --check` compared every name). The names are kept as data in `dr2kit/catalog/effects.toml` (`dr2 effects`). The two u32 of each record read `0xFFFFFFFF` in the image (filled in at run time ❓). Checked by meaning: `PyroEffect 141` of
the Fire Extinguisher = `fireextinguisher_wpn_dc_2`, 123 of the Electric Rake =
`elecrake_wpn_dbs_3_unq`, 181 of the Freezer Bomb = `freezebomb_wpn_bs_4_unq`, 57 of the
Flamethrower = `flamethrower_wpn_dc_3`, 249 (the rake's `EffectOnVictim`) =
`elecrakedmg_wpn_bs_1`, 13 (sharp weapons' victim effect) = `victim_bld_dbm_3` (blood),
280 (impact) = `impact_bld_dbs_2`. The effects themselves are `EFFECT_Common<k>` entries
of `data/models/effects.big`, **sorted by name, so `k` is not the effect number**.
How found: a pointer to the string `fireextinguisher_wpn_dc_2` inside an array of
same-shaped records (image base `0x82000000`). **So these numbers only change what is
seen**, never what happens to the zombie (checked in game, below).

### Elements on a weapon ✅ (in game, CZ, 2026-10-12)

| Element | What gives it | Checked |
|---|---|---|
| **Shock** (chain lightning) | `Can_Electrocute = "true"` on the weapon | Chef Knife: melee hits shock |
| **Fire** (the zombie burns) | a child block `cPropHitZombieInfoItem <name> { DR2 = "true" PropHitZombieEffect = "0" Support = "true" }` (as CW's Tiki Torch `Tiki_light_on_fire`) | Bowie Knife: melee hits set zombies on fire |
| **Freeze** | the same child block with `PropHitZombieEffect = "1"` (as CW's Snowball) | Bowie Knife: melee hits freeze; Broadsword: a **thrown** sword freezes the zombie it sticks in (break it to get the sword back) |

Not enough on their own: `Fire = "true"` (only the effect particles showed, no burning)
and `Can_Freeze = "true"` (no freezing); both are kept by the game's fire and freeze
weapons and may matter for something else ❓. `PropHitZombieEffect` 2 (CW Electric Prod,
Laser Gun explosion) and 3 (CZ Pitchfork) are untested ❓.

A sword still **slices** (kills in one cut) with its `HitReaction<n>` / `FatalHitReaction<n>`
set to a club's and `Arbitraty_Slice = "false"`, even at `AttackDamage 5`: what makes
it slice is something else (`WeaponType 4`? `Is_Sharp`?) ❓. **No key gives a melee attack
an area of effect**: damage in an area comes only from explosives (`ExplodeRadius`,
`HeavyDamageRadius`, `MediumDamageRadius`; CW's Freezer Bomb freezes its blast with
`Can_Freeze`).

### Combo cards of one's own ✅ (in game, CZ, 2026-10-12)

A `cComboCardItem` added inside an existing weapon's block (`BowieKnife`) with
`Weapon_1 = "Broadsword"`, `Weapon_2 = "FireExtinguisher"`, a free `CardIndexNumber`
(3: CZ's cards use 0, 1, 2, 4, 13, 24, 26, 46, 48), `IconAsset = "comboc_defiler"` (a Dead
Rising 2 card picture CZ ships in `frontend/combocards.tex` but no CZ card uses) and the
Defiler's string ids: at a workbench the two items made the Bowie Knife, and the card
showed with that picture and label. The card's texts are the string ids' text **in the
game's language** (the user's French game showed "Profanateur", the French Defiler, as
the test changed only `str_en.bcs`): a mod's names must be written in every language.
Not yet tried: a card number past 50 (a fixed table ❓), a new card picture, a card for a
new item.

### A weapon of one's own on a carrier item ✅ (in game, CZ, 2026-10-12)

"Frostmourne" (a model from the user's own WoW install, a local test only) was put on the
**Lead Pipe**, an item CZ ships but never places, with **replacements only** (no added
file): its scene from a `.glb` (`leadpipe.big.glb`, 1,179 vertices), its colour textures
from PNGs, the Broadsword's move keys (`AnimBankName = Sword`, the attack names and every
per-attack key) copied into its block, a freeze block, a combo card, and its name in
`str_en` / `str_fr` / `str_lg`. In game: textured, swung with the Broadsword's moves,
froze zombies, made at a workbench from Broadsword + Fire Extinguisher.

* **Borrowed moves work:** another weapon's `AnimBankName` and attack keys give its swings.
* **The hands follow the model's own grip nodes** (`LOC_rhand`, `IK_lhand` of the Lead
  Pipe) even with the Sword bank, whose own weapons use `LOC_WEP_<x>_R/_L`: the mesh is
  what has to be placed. With the sword's guard at `y = -0.13` (model space, blade along
  +y) the hand went through the guard; at `y = -0.06` (the right-hand node at
  `y = -0.207`, the left at `-0.306`) it held the handle right.
* **Effects on the weapon itself:** `PropEffectsOnCondition<n>` = **30** (always, while
  held) and **31** (while swinging) with `PyroEffect<n>`, `PropEffectLocator<n> = 16`,
  `PropEffectLocatorIndex<n> = 0` (as CW's Tiki Torch and Blazing Aces): **they work in
  CZ** although CZ's own items use conditions up to 29 only. `dryice_env_c_3` (286) is a
  level fog (far too big); `snowtrail_wpn_bs_1` (215) and `snowball_elm_bs_1` (225) are
  small.
* **The inventory icon** is the pack's `w_<name>.bct`: 128×64 DXT1, a see-through
  background, the weapon lying diagonally (handle top left, tip bottom right). It kept
  the Lead Pipe's picture (not replaced yet). In **Case West** the icon is the pack's
  `<name>.bct` (`katana.bct`, `IconFilename = "katana"`): in both games the pack holds
  exactly one loose `.bct`, the one `IconFilename` names (phase 13, every kind's pack of
  both games).
* **A combo card's picture** is replaced in place (`comboc_defiler.bct` and `_no`, 364×512
  DXT1; the small square top left at x 21-59, y 18-57 holds a 36×36 icon).

### A weapon's line: handle end, grip nodes ✅ (phase 13)

The weapon wizard lays a new shape where the game weapon lies
(`dr2kit/convert/weapon_fit.py`): the model's longest direction (principal axes of its
vertices) and which end is the handle. Measured on 18 weapons of both games (Broadsword,
Katana, Bowie Knife, Chef Knife, Baseball Bat, Crowbar, Lead Pipe, Sledgehammer, Large
Wrench, Broom Handle, Leaf Rake, Pitchfork, Acoustic Guitar, Power Drill, Reaper, Shovel,
Laser Sword, Sickle, Bone Saw): the nodes named `…blood`, `FX…`, `LOC_slice`,
`…stuck`, `LOC_particle_pos`, `EFF_…`, `LOC_collision…` sit at the **striking end** in
every one, so the handle is the other end. The right-hand node alone misleads: the
Sledgehammer's `LOC_rhand` is at y = 0.60 of a 0.99 m handle whose head is at y = 0.99
(its `IK_lhand` at 0.07 is at the handle's end). Grip node names: `LOC_rhand`,
`LOC_rhand1`, `LOC_rhand_frank`, `IK_lhand`, `LOC_lhand`, `LOC_WEP_<x>_R` / `_L`
(names are `geo_<model>.<node>` in the scene).

### Locators and the effect point ✅ (in game, CZ, 2026-10-12)

A model's `LocatorArray` (with `NumLocatorArray`, a count) holds 52-byte big-endian records:
`u32 type`, position `3f`, rotation `4f` (x y z w), then five words (0, an offset into the
nested `__STRING_STORAGE__`, 0, 0, 0). The strings name a default effect per locator
(`<None>`, or `beersplat_elm_bs_2` for the Broadsword's type 16). Types seen on the
Broadsword and CW's Katana: 9 (right hand), 27 (left hand), 30 (slice), **16 (the particle
point, `LOC_particle_pos`)**, 19 (stuck); the Lead Pipe has 27, 16, 9. Each record repeats
a node record (same position and rotation). **There are two copies:** in the model
archive and in its nested `persistent.big`, and **the game reads the `persistent.big`
copy**: moving only the first one changed nothing in game; moving both did.

**Several locators of one type, and which one holds the item** (phase 15, 2026-10-13):
Case West's Impact Hammer has three type-9 (right hand) records, their number in the 3rd
of the five trailing words: 0, 1 (the player's) and 2 (the hazmat suit's), turned
differently. Case West picks one through the item's `AttachmentItemName` →
`cPropCharacterAttachmentItem {Locator = 9, LocatorID = 1}`, a class Case Zero's program
doesn't know; Case Zero then held the hammer by record 0, **upside down** (user, in game).
The importer copies the chosen record into every record of that type (recipe `scene` +
`locators`). Case West items picking a record other than 0 this way: `ImpactHammer`,
`ImpactHammerBFG`, `Shovel`, `WaterBottle_fromcooler` (1), `PoolCueBroken` (3).

`PropEffectLocator<n> = 16` puts an `items.txt` effect at locator type 16. The
Broadsword's (and the Katana's) is mid-blade, **turned 180° about the blade**, so its +y
points across the blade: the Flaming Sword's flame (its box 0 → 0.7 m along +y) hung
straight down from a held Broadsword-based sword. The weapon wizard moves it to 0.10 m
above the right-hand grip with +y toward the tip (`convert.weapon_fit.effect_locator`,
the pack recipe's `locators`, `mods.newitem.set_locators`, both copies): the flame then ran
along the blade in game (user, windowed, 2026-10-12).

**Material values.** `MatArray` records (36 bytes) hold four floats at +16
(`Material.params`). On `LIT_CM2DDL_NM_RMX_SPEC` weapons: Broadsword (911.1, 0.7, 1.0, 1),
Lead Pipe (4244.4, 0.2, 0.15, 1), Baseball Bat (400, 0, 0.5, 1), Sledgehammer (200, 0.7,
2.0, 1). The 3rd looks like the reflection of the `reflection_basic` sky map ❓: with
the Broadsword's values, WoW Frostmourne's dark picture came out black and gold in the
sunset; the same picture on the Lead Pipe (phase 12) looked right. The wizard's *Shine*
copies one weapon's four values (`newweapon.SHINES`, recipe `material_params`).

### Combo card pictures: the shared frame ✅ (phase 13)

Every card of a game shares its frame, the corner arrow, "X2 PP!", the drawing panel
with its rays and "+": the per-pixel **median** of all of a game's cards (CZ 51, CW 66;
the `_no` ones apart: CZ 51, CW 59) is a clean empty card, and the spread between them
outlines the parts that differ: the **portrait window** (a slanted four-sided shape,
x 26-337, top edge y 40 → 26, bottom edge y 287 → 266) and the two **drawing boxes**
(x 35-166 and 199-332, y 361-483). Chuck's hair pokes out of the window on some cards.
The wizard draws new cards on the empty card (`dr2kit/convert/icon.py`).

### Particle effects (`data/models/effects.big`) ✅ read, written, changed and added in game (CZ, headless, 2026-10-12)

Layout in `dr2kit/formats/effect.py` (census: CZ 448 effects / 2,221 emitters, CW 506 /
2,516, all written back byte for byte). An effect: version `0x1D` (CZ) / `0x20` (CW), a
0x80-byte name, the emitter count, 4 (CZ) / 3 (CW) header words, then the emitters: 0x190
bytes of fields, the particle picture's name (0x20), 8 zero bytes, then a tail by the
shape word at +0x30 (0 none, 1/2 six floats, 3 five floats): 440, 464 or 460 bytes. The
colour keys (five RGBA at +0x64, times at +0x54) **are the particles' colours**: the
Flaming Sword's flame recoloured green showed green in game. Other fields: guesses
(`FIELDS`, status "?").

**How the game loads them (measured, CZ):**
* from `data/preload4.big`'s copy (`data/models/effects.big` is never opened). Re-encoding
  inside `preload4.big` crashes the boot (memory.cpp), as the CZ recomp found for
  `fecmn.big`; the build **evicts** the nested copy instead (index hash `^ 0xDEADBEEF`, 4
  bytes changed) and the game then reads the loose `effects.big` (profile `preload_evict`,
  also `effects.tex`). `preload4.big` holds copies of 86 files (CZ all identical; CW 59).
* **`layout.bin` pins every file's size** (152-byte records, BE size at +132); a 4 KB larger
  `effects.big` crashed when opened. The build now writes a re-pinned `layout.bin` when a
  built file changed size (`mods.build.repin_layout`); the user's own mods load with it.
* only the effects listed in the scene's `SceneDescription` (kind 13) and counted in
  `SceneHeader` word 3 load; an added effect must be listed (`register_in_scene`).
* **free slots:** 36 names of the effect table have no effect (`unused`, `wip_1`…, the
  same in both games). An effect added under one of these names shows with that number:
  effect 69 (`wip_1`), the Flaming Sword copied and turned blue, showed blue in game.
* particle pictures of one's own, added to `effects.tex` (named without `.bct`), show in
  game.

**Case West (headless, 2026-10-12):** a CW mod with a wizard weapon (the Katana's pack
copied), an own effect (slot 6), a changed Flaming Sword and new card pictures loads into
gameplay from a copy of the user's save (Storage Bay), no fault: the CW build's eviction
and `layout.bin` re-pin work there too. The effects themselves not yet seen in CW.

**The user's in-game test U1/U2 (2026-10-13, Case Zero, windowed)**: the Laser Sword swings
and sounds right but its handle had **no texture** and the blade no glow; the Impact
Hammer was there, untextured, and **didn't attack properly**; the street's crowds retyped
to Case West's types stayed **empty** (only scattered native zombies). Found since:
* **Animations live in the graph, not only in the move bank.** An item's
  `AnimationAttackChooserValue<n>` (→ chooser `ATTACKWEAPONTYPE`), `WeaponImpactAnimation`
  (`WEAPONIMPACT`) and `AnimationChooserValueForThrow` (`THROWTYPE`) select entries of
  `sgraph.txt` (measured: every value of every item of both games in that one chooser
  type). Case Zero's graph has the Laser Sword's attacks (Dead Rising 2's) but not the
  Impact Hammer's; `convert/graphcarry.py` brings the entries and their `cAnimRef` blocks.
  Animation block ids (`cAnimRef`, `cAnimGroup`) are dense, 0-4407 in Case Zero, 0-5021 in
  Case West; state numbers are another space and **differ between the games** (CW 482 =
  `WEAPONIMPACT`, CZ 493).
* **`sgraph.txt` opens with `# <class> <count>` lines, exactly the file's block counts**
  (131 classes CZ, 130 CW, all exact). With blocks added and the old counts Case Zero
  **faulted at boot** (a null call while reading the graph); the build now rewrites them
  after edits (`leveledits.recount`). Its reader is also strict about style (numbers
  unquoted, keys in file order): carried blocks are written as their source text
  (`"@text"` adds).
* **Gas zombies need their voice banks too** (2026-10-13): Case Zero's sound list
  (`data/datafile.big/scenegraph.txt`, `cVoiceTalentEntry … Source = "fx_gzombieakalem"`)
  names six gas zombie voices and the looters' `fx_looter`, but Case Zero ships none of
  their banks (`data/streamedassets.big/fx_gzombie<voice>1.big` / `2.big`, Case West's). With
  gas zombies in the street's load set the load asked for
  `data/audio/fx_gzombieakalem2.big` (the loose fallback name) and faulted at guest `0x1C`
  ❓ (a guard was in the same build: see below). `importzombie.voice_banks` brings every bank of a voice the
  target's list names and lacks.
* **Gas zombies need `data/anim/gaszombies.big`**, which only Case West ships; Case Zero's
  program asks for it and **its graph names all 69 of its moves** (Case Zero is ready for
  gas zombies). The guards' moves are not: of Case West's 154 extra `mercs.big` moves,
  Case Zero's graph names 2 (a merge of graph *states*, not done).
* **Brought shaders drew without textures: found 2026-10-13, the constant registers**
  (§Across the games: constant registers). The same Impact Hammer pack drawn with Case
  Zero's own same-named descriptions showed its yellow and black textures; with the
  brought Case West descriptions and programs it was flat white. Not the textures (byte 9,
  names, hashes), not the samplers (the same slots in both games' programs). Reading the
  programs (XenosRecomp) showed why: a Case West pixel shader reads
  `gShaderDebugParameters` at register c21, which Case Zero's engine fills with
  `gPointLight0Parameters`; with `.x > 0` the program takes its debug branch and outputs
  flat lighting. Brought pixel shaders now read Case Zero's registers
  (`formats/xenos.py`, `shadercarry.move_registers`). ❓ in game: U1 again.

**`PropAudioType` is a bit set each program reads up to its own bits** (2026-10-13): Case
Zero's items use bits 0-11 (`0xF77`), Case West's add bits 13 and 17 (`0x22F72`). Case
West's Impact Hammer (`132096` = bit 17 + 1024) placed in Case Zero **faults the load**
(found by bisecting the block's keys headless, 7 rounds; the fault's `r28` held
`0x00020400`). The importer keeps only the target's bits (`importitem`; 3 Case West items,
2 Case Zero ones the other way).

**The two games' layouts (phase 15, 2026-10-13):** Case Zero's four header words are Case
West's three with a **0 inserted third** (Case Zero has it 1 on 7 of its 445 named effects:
`firecracker_wpn_c_2_unq`, `lawnmower_bld_dc_3_unq`…; Case West dropped it); emitters are
the same layout, byte-identical in 398 of the 412 effects both games name with the same
emitter count (the rest are other content). So an effect of the other game is converted
by the version word and that third word (`Effect.as_version`); checked on every shared
effect (`tests/test_effects.py`). The importer brings an effect the target lacks into a
free slot this way, with the particle pictures the target's `effects.tex` lacks
(`importitem._bring_effect`): Case West → Case Zero needs 27 effects (51 uses), within
Case Zero's 36 free slots; Case Zero → Case West needs none.

**Emitter fields, one value at a time (CZ, headless, 2026-10-12, phase 13):** nine copies
of the Flaming Sword's flame emitter (turned blue, ×3 size), each with one field changed,
lined up in view with the street-light trick (`phase13-kickoff.md` §Start here), compared
in two frames. `count_20` ×10 (3 → 30): a dense, bright cloud, so it is **how many
particles** (alive at once or per second ❓). `colour_times` ×4: a cloud four times
taller and bigger, so the last key time is **the particles' life**. `i_164` 3 → 30: the
emitter **vanished** ❓. `f_18` ×10, `count_1c` ×10, `f_138[3]` ×10: **no visible
change**. `f_40` ×10 and `f_14` ×5: hidden behind the HUD, not judged. Kept in
`formats/effect.py` `FIELDS`.

**From WoW 3.3.5 (`tools/wow_import.py`, local only):** an `.m2`'s `M2Particle` (0x1DC
bytes: flags, position, bone, texture index into the model's textures, blend, emitter
type, six `M2Track<float>` (speed, its variation, vertical and horizontal range, gravity,
lifespan), lifespan variation, rate track and variation, area length / width / z
tracks, colour / alpha / scale `FBlock`s on 0-32767 times, …; read and checked on
Frostmourne's seven emitters, the struct ending exactly at 0x1DC) becomes a DR2 emitter:
colour and alpha keys sampled at 0, ¼, ½, ¾, 1 of the life → `colours`; life ×(¼…1) →
`colour_times`; scale → `sizes`; rate → `count_20` (clamped 1-30); position and area →
`offset` and the box (y along the model's longest axis, from its lowest point); gravity
→ −`gravity` y (WoW's positive gravity pulls down, DR2's flames rise with +y). Its
pictures (BLP, additive) become see-through pictures of one's own (alpha from the
brightness). The other fields come from the base emitter (the Flaming Sword's smoke).

### New items' files load ✅ (headless, CZ, 2026-10-12, phase 13)

*Phase 12 wrote:* "a test mod adding five weapon packs to `streamedassets.big`, two
textures to `frontend/combocards.tex` and six new string ids made the street's load stop
after zone z10 every time (headless, a copy of the user's save), even with no
`items.txt` changes and no placements." **Not reproduced (phase 13):** that mod (kept at
the time), the same mod rebuilt with its items, card pictures and placements, and the
same with the mods the user had on, all **load into gameplay** headless on a copy of the
user's save; frames dumped during the run (`CZ_VK_FRAME_DUMP`) show Chuck in the street.
The phase 12 check misread the log: a good load also ends its file list with
`prologue_z10.big`, `Prologue.txt` and `combocards.tex` (the last files opened before
gameplay), so the list can't tell a stall from a finished load; look at a frame. (Also:
with the synthetic presses `START,A,A` held on `A`, the save loads, Chuck dies to the
street's zombies about a minute later and the held `A` picks *Load* or an ending: use
`START,A,A,A,A,NONE` and stop pressing.) A wizard weapon (a new pack from a recipe, new
string ids, new card pictures, its block, five placements at the save's spawn point)
loaded and showed: the sample sword standing in the street, textured. The user's windowed
runs of phase 12 are not explained ❓ (two crashes loading `zombies.big` with a co-op
player present).

## Animations (`.anm`) ✅ every key read (phase 13.2 first frames, phase 14 every key)

Implemented by `dr2kit/formats/anim.py` (reader, `decode`, `census`), used by
`dr2kit/convert/holding.py` (Chuck in an idle, his moves played, glTF animations).

**Where.** `data/anim/default.big` holds one archive per skeleton part: `fullbody.big`
(1,371 in CZ), `root.big` (the same names), `hand.big` (170: finger poses), `upperbody.big`
(33), `facial.big` (46); also `zombies.big`, `mercs.big`, `battle/`, `cinematic/`,
`survivor_custom/`, `weapon/`. A weapon's moves are `streamedassets.big/anm_<AnimBankName>.big`
with `root.big` and `fullbody.big` inside; its `items.txt` block names them
(`AnimationAttackName0…`, e.g. the Broadsword's `male_attack_sword_6_to_1_a`).

**Which rig.** The first word is the **skeleton id**, the same number a skeleton file
stores as word 1 of its `_ANIMCHANNELINFO_` (word 0 = its node count): fullbody
`0x24F628C0` = `data/skeleton/playerfullbody.big` (98 nodes; the child, female and large
full bodies share it), root `0xAD2B0240` = `playerroot.big` (`dummy01.root`, `arrow`),
hand `0x70CB2D80` = `playerhand.big` (30 finger nodes), upper body `0xDA1D8000`, face
`0xADC1BFE0`, **zombies `0x45E6F8E0` = `zombiefullbody.big`** (30 nodes: zombies' and
mercs' full-body moves), cutscene casts `0xDDEA5800` (`cineplayer.big`…), props
`0xE23F8460`, cameras `0x1C5D5480`. The game refuses a mismatch ("*** the anim data does
not match the skeleton that it is being played on! ***", CZ `0x827BB5F8`). **Track numbers
are node indices of that skeleton file.** *Checked:* every skeleton file of CZ searched for
the ids (2026-10-12).

**Layout** (big-endian):

| Offset | Type | Meaning |
|---|---|---|
| 0x00 | u32 | skeleton id (above) |
| 0x04 | f32 | length in seconds = (frames − 1) / rate |
| 0x08 | f32 | frames per second (30, 29.86, 60…) |
| 0x0C | u16 | key mask offset = 0x16 + 2 × tracks |
| 0x0E | u16 | first keys' offset = the mask's end rounded up to 4; **0 when that is past 0xFFFF** (26 long cutscenes of both games: `701_chuck_arrives_in_town~chuck.anm`…) |
| 0x10 | u16 | frames |
| 0x12 | u16 | tracks |
| 0x14 | tracks × (u8 node, u8 kind) | **in the decoder's kind order**: `0x22`, `0x02`, `0x01`, `0x05`, `0x11`, `0x12`, `0x31` (every file of both games) |
| | `FF 00` | end of the table (every file) |
| mask | frames × ⌈tracks / 8⌉ bytes | bit *t* of frame *f*: track *t* has a key at frame *f*; every track has keys at the first two and last two frames |
| keys | | the first key of every track, in track order; then the later keys (below) |

Track kinds and their keys (the scales are floats in the executable, CZ `0x820B28C4`…):

| Kind | What | First key | Later key |
|---|---|---|---|
| `0x01` | rotation, animated | **8 bytes**, one 64-bit number: x = bits 62-47 (16 bits, /32767), y = bits 46-32 (15 bits, /16383), z = bits 31-16, w = bits 15-0 (/32767) | **top bit 0**: 8 bytes as the first key; **top bit 1**: 4 bytes, a **change from the previous key**: x = bits 30-23 (/12700), y = bits 22-16 (7 bits, /6300), z = bits 15-8, w = bits 7-0 (/12700). Either way the result is scaled by 1.5 − \|q\|²/2 |
| `0x02` | translation, animated | three floats (metres) | **top bit 1**: 8 bytes, three 21-bit signed numbers (bits 62-42, 41-21, 20-0) × 300 / (2²⁰ − 1), the position itself; top bit 0: three floats |
| `0x12` | translation, fixed | three floats | none |
| `0x31` | rotation, fixed | four signed 16-bit (/32767), x y z w, normalised | none |
| `0x05` | a camera (`…~cameras.anm`) | 32 bytes: a float quaternion, a position, one float (field of view ❓) | 32 bytes |
| `0x22` | cutscenes only (65 tracks in CZ) ❓ | three floats | three floats |
| `0x11` | (none in either game) | four floats | a signed 16-bit number × 9.5877e-05 (the fourth value) |

**The order of the later keys.** The game steps through the frames (CZ `0x827B5090`): at
frame *f*, for every track in table order with a key at *f*, it reads that track's **next**
key (the next frame whose mask bit is set), 4-aligned (2 for `0x11`). So a key follows
when the key before it on the same track is reached, not frame by frame. Between keys the
toolkit turns rotations the short way (nlerp) and moves positions in a straight line.

*How it was found:* the first keys from the hand poses (`male_hand_hold_2x4_pose.anm`: 30
fixed rotations end exactly after 30 × 8 bytes) and the skeletons' rest values (`jiggle`
(−½, −½, −½, ½), offset (0.034, 0.175, −0.003)); the later keys from the game's own
decoder (2026-10-12, read with the CZ recomp's `tools/gdis.py`): `0x8279B0B0` reads the
first keys, `0x827B5090` steps a frame, `0x8279AB98` reads a rotation key (4 or 8 bytes by
its top bit), `0x8279AF68` a translation key (8 or 12 bytes), `0x8279AEA8` a fixed
rotation. **Census (`dr2 census --anims`): every `.anm` of both games is read to its last
byte** (CZ 5,785 files, 601,403 frames, 6,655,401 keys; CW 6,268 files, 585,326 frames,
6,850,259 keys), and every rotation key is within 0.0002 of unit length before the
rescale; the empty entries are named (CZ 7, CW 3: helicopter props,
`zombie_hitreaction_auger_idle`).

**Retraction (phase 13.2 → 14):** the first key's x and y were read as two 15-bit numbers
/16384, with "each word's top bit a flag ❓". The game reads **x as 16 bits across the two
words** (that "flag" is x's lowest bit) **and y as 15 bits /16383**; the old reading was off
by less than 1/16384, which is why it passed the unit-length check. Also retracted: "an
animated translation's later keys are 8 bytes, ×≈2.9e-4 of the first key's scale" (the
scale is 300 / (2²⁰ − 1), absolute; a top bit of 0 means three floats).

**Root motion.** `root.big`'s move of the same name moves `dummy01.root`: where the hips
are and how far the move carries him (`male_sword_a_2_to_8_360` travels 2.08 m forward,
`male_attack_sword_6_to_1_a` 1.83 m). Studio's *In place* takes that straight line out.

### Which idle the game plays for an item ✅ (from the game's files)

`data/datafile.big/sgraph.txt` is the game's **animation graph**: `cGenericAnimState`
blocks holding `cAnimGroup`s, each with a chooser (`cCategoryChooser` with a
`ChooserType`, or `cRandomChooser`) of `cChooserEntryInt <name>` / `cChooserEntryFloat`
entries (`Anim` = a group or `cAnimRef` number in the same container or above, `Value` =
the number that picks it, or a random weight). A `cAnimRef`'s `File` is the engine hash
of `<name>.anm` (lower case) as a **signed** 32-bit number: `-159364033` =
`male_idle_samurai_sword.anm`.

* The standing idle is the `IDLEHOLDTYPE` chooser whose plain choice (value 0, `Chuck` in
  `CHARACTERTYPE`, `CANPLAYAMBIENTIDLES` 0) is `male_idle_combat.anm` and that has the
  most entries (CZ state 21; others are for doors, the injured idle, transitions). Its
  value is the item's **`AnimationChooserValueForIdle`**: 0 one-hand items →
  `male_idle_combat`; 1 guns → `FIREARMTYPE` (`male_idle_rifle`, `male_idle_shotgun`);
  4 large objects (`HandlingStyle` 5: acetylene tank, garbage can) → `male_lgbox_idle`;
  5 cart; 7 hamster ball; 8 chair; 9 chainsaw / mechanical → `WEAPONON` (`male_idle_mech`,
  `male_idle_chainsaw` when running); 10 paddlesaw; 13 small objects and chairs held in
  both hands → `male_idle_smallbox` (or the lawnmower when on); 14 poles and spears →
  `male_idle_thrust`; 15 `male_idle_samurai_sword`; 16 `male_idle_pistol`; -1 nothing
  held. Items of CZ use -1, 0, 1, 4, 9, 13, 14 (`items.txt`).
* The fingers: the `HANDTYPE` chooser, value **`AnimationChooserValueForHand`**: 0
  `male_hand_idle_pose`, 1 `male_hand_right_hold_pole_pose` (Katana, Lead Pipe), 2
  `…hold_smallbox_pose`, 8 `…hold_pole_pose` (Broadsword, push broom), 15
  `…hold_scissors_pose` (Sledgehammer!), 23 `…hold_6shooter_pose`… Value 11
  (`male_hand_M16_pose`) names a file neither game ships.
* `root.big` holds an animation of the same name for each full-body one: the hips'
  place and turn (`male_idle_combat`: 0.977 m high, the rig's rest 1.012).

**Chuck posed** (`convert/holding.py`): the full-body idle's first frame, then the root
one, then the hand pose, on `playerfullbody.big`'s rig by node name; every part of his
outfit (`outfits.csv` `OUTFIT_DEFAULT`: CZ `young_chuck`, CW `default` / `base` /
`naked`) is drawn on that one rig, skinned from its own rest pose. **Parts' rest poses
differ a little** (the boots' ankles sit 2.4 cm higher than the rig's): posing each part
with its own rest offsets left the boots 18 cm below the legs, so every node gets the
rig's posed transform. An item hangs from `dummy01.r_hand_prop` with its right-hand grip
node on it, turned the same way (item = hand prop × grip⁻¹): the Broadsword, the Lead
Pipe, the push broom, the acetylene tank, the propane tank, the chainsaw, the shotgun
(CZ) and the Katana (CW) all come out held in his hand as the game shows them standing
still (pictures, 2026-10-12) ❓ **not yet compared with a screenshot of the game**. The
left hand is not moved to the item's `IK_lhand` (the game does that, by IK ❓).

## Strings (`.bcs`) ✅

Implemented by `dr2kit/formats/bcs.py`. Every text the games show (menus, subtitles,
case files, item descriptions, tutorials) is a **string id** looked up in the bank of
the current language, `data/frontend/str_<lang>.bcs`. Layouts and scripts name ids
(`Text="10611 …"` in the frontend layouts), never the text.

Layout, **little-endian** like the `.big` index (checked on all 8 banks of both games):

```
u32 n
u32 ids[n]        strictly increasing, 1 .. 99999
u32 offsets[n]    from the file start; offsets[0] = 4 + 8n
strings           UTF-8, NUL-terminated, in id order, back to back (no gaps)
zero padding      to a size shared by all banks of the game
```

- **Same ids, same size.** All banks of a game hold the same ids (CZ 7,599, CW 2,469)
  and have the same file size (CZ 441,496 B, CW 120,418 B): each is zero-padded to the
  size of the largest, `str_lg` (which has no padding). The writer keeps that size when
  the edited text fits, so an unedited bank comes back byte-identical (census: 16/16),
  and writes unpadded when it doesn't. The game loads unpadded and larger banks: the CZ
  recomp's `gen_pc_options.py` and KB/M tools ship rebuilt banks of other sizes, and the
  toolkit's in-game check below used an unpadded bank (built on the recomp's
  `game_patched` copy, 384,959 B).
- **The banks.** `en`, `fr`, `it`, `es`, `ja`, `ko`: the six languages a player can pick
  (CZ recomp, `localization-and-bootskip-plan.md`; console language 1 en, 2 ja, 4 fr,
  5 es, 6 it, 7 ko). `str_id.bcs` holds each id's **label** (`IDS_START_DEMO`,
  `IDS_PRESS_START`); `str_lg.bcs` is legal and pre-language-select text in several
  languages. There is no German bank.
- **Markup.** `[RRGGBBAA,text]` draws `text` in a colour (`[00CC00FF,golf club]`);
  `[@name]` draws an icon (`[@x_button_ig]`, `[@world_icon_food]`). **Every string that
  uses either starts with `@`** (all 8 banks of both games; 643 strings in CZ English):
  the `@` switches markup on and isn't shown. Some `@` strings have no markup (9 in CZ
  English). One shipped French string (CZ id 2546) has an unbalanced `[`.
- **Placeholders.** `%s`, `%d`, `%0`, `%1`, `%.1f`… are filled in by the game. A mod that
  drops or adds one gets a note (`bcs.apply`): the game may show garbage or crash.
- **The last id.** CZ's last string is id 99999, labelled
  `IDS_LAST_LETTER_OF_LAST_STRING_IS_ALWAYS_MISSING` (text "Yeap, its always missing."):
  the developers' reminder that the reader drops the last character of the last string.
  The toolkit refuses new ids above a bank's last id. (Not measured in game. The CZ
  recomp's `gen_pc_options.py` adds ids 100000-100004 after it, so if the reminder is
  true, its last string, "Borderless", loses its last letter.)
- **JSON** (`bcs.to_json`, `dr2 strings export`): `{"format": "dr2kit strings v1",
  "bank": vpath, "strings": {"<id>": text}, "labels": {"<id>": "IDS_…"}}`. A mod's
  `replace/data/frontend/str_<lang>.bcs.json` holds only the strings it changes, by id
  or label; several mods' files merge by id (`mods/build.plan_mods`).

**In-game check (2026-10-09, both recomps):** a mod setting `IDS_PRESS_START` (10611) to
`DR2KIT STRINGS OK` in `str_en.bcs.json`, deployed with `dr2 mod deploy`; the VFS
logged `str_en.bcs served from the MODS overlay` and the title screen showed the new
text in both games (procedure: `dev/recomp-integration.md` §Phase 6).

## Digest-checked files ✅

The executables verify a few data files when they load them and crash on an edited copy
(an assert in `digestmanager.cpp`, "Bad file digest"; CZ checked in game, §Audio scene
scripts). The list is the XEX's `Digest` resource (optional header `0x000002FF` names
the resources; the bytes are in the decrypted image, which a recomp keeps as
`assets/game/default_image.bin`). Layout, measured on both games
(`tools/xex_digests.py`):

```
be32 count
count × { be32 key; u8 sha1[20] }
```

`key` is the engine's name hash (`dr2kit.hashing.name_hash`, case kept) of the path as
the game writes it; `sha1` is SHA-1 over the file's bytes followed by its length as a
big-endian u32. Every digest matched a file of the game:

| Game | Checked files |
|---|---|
| Case Zero (1) | `data/audio/Prologue.txt` |
| Case West (6) | `data/audio/Safehouse.txt`, `data/audio/scenegraph.txt`, `data/audio/audiomixer.txt`, `data/audio/curves.txt`, `data/controls/padmap.txt`, `data/models/zombies/zombie_pdv_variations.txt` |

The lists are in the game profiles (`digest_checked`); `dr2 mod check/build` refuses an
override of these files and DR2 Studio opens them read-only.

## Movies (`.bik`, Case West) ✅ read

Ten Bink movies in CW's `data/movies` (Bink 1: ffmpeg's `binkvideo`,
`binkaudio_dct`): the intro (`800a_intro.bik`, 1280×720, 39 s), three logo movies, and
six 512×512 security-monitor loops without sound (25-114 s). Read through PyAV
(`dr2kit/convert/video.py`).

- **Audio tracks:** a movie with 5.1 sound has four Bink tracks: stereo + mono + mono +
  stereo = front L/R, centre, LFE, surround L/R. Measured on `800a_intro.bik`: track 2
  has 90 % of its energy under 200 Hz and is nearly silent (LFE); track 1 is quiet with
  a high centroid (centre). `DR_LOGO_shortLoop.bik` has one stereo track.
- **Census** (`dr2 census cw --audio`): all 10 decode, every frame (count = length × fps
  ±1) and the sound (as long as the pictures ±0.25 s), 7.7 minutes.
- **Replacing** a movie needs RAD's Bink encoder, which can't be redistributed: not done.

## Case West differences (phase 1 census)

Same container, same compression, same hash rule, same flag values: nothing in the `.big`
format differs between the games. What differs is content:

- **154 `.big` files** against CZ's 146, plus extra loose files: 10 `.bik` movies (Bink;
  the guest decodes them), 15 `.csv`, 6 `.ini`, 8 more `.txt`. Extra folders:
  `data/controls`, `data/dynamicprops`, `data/models/zombies/`, `shaders/settings`.
- 172,322 entries at all depths (CZ 124,932); 21,354 compressed (CZ 10,754). Far more
  `.bct`-named textures (18,254 vs 6,060).
- `data/preload4.big` keeps the same 86 entries but **27 of them are empty** (the
  `00 00 00 00` compressed form above).
- Fonts: 6 of 11 `.bcf` are `.big` archives (CZ: 9 of 11); `arial.bcf`,
  `480/handwritten36.bcf` and `720/handwritten36.bcf` switched to the `04 03 02 01`
  container.
- Duplicate names: 44 entries in 8 archives (CZ: 12 in 2).

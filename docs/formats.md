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
| scene (model / skeleton) | `models/**/*.big`, `skeleton/*.big`, props, environments | ✅ read + write | `dr2kit/formats/scene.py`, `vertex.py`. Every scene of both games parses and every draw decodes; buffers and bone palettes checked against the running game; exports to glTF. **Written back** (phase 4): every chunk rewrites identically, `.glb` → model, new meshes and rigs; checked in game |
| `.xma` audio | `audio/*.big` | 🟡 | raw XMA, decoded on the host by the recomp through ffmpeg; header and rate source ❓ |
| audio scene scripts `.txt` | `audio/Prologue.txt`, `datafile.big` | ✅ text | `cAudioScene` / `cAudioJukebox` tree, `Asset = "music.big/<name>"` |
| `.bcs` string bank | `frontend/str_<lang>.bcs` | ✅ | `gen_pc_options.patch_bcs` reads and patches it |
| `.bcf` font | `system/**` | 🟡 | 9 of 11 in CZ and 6 of 11 in CW are plain `.big` archives (read by the census); the rest start `04 03 02 01`, an unknown sibling container ❓ |
| `.anm` / anim `.big` | `anim/**`, `skeleton/*.anm` | ❓ | |
| ragdoll `.dat` | `skeleton/*_ragdoll.dat` | ❓ | Havok likely (`hkp*` RTTI in the XEX) |
| shader banks `.vo/.po/.vdo/.pdo/.sdo/.scv` | `shaders/*-{vs,ps,vd,pd,sc,sd,ss}.big` | 🟡 | `.vo`/`.po` are standard 360 D3D shader containers (`10 2A 11 01`, XenosRecomp translates them); `.sdo` = a shader name's permutations (`5cef4d20.sdo` → `ProtoSkinnedClothRGB`). Models carry their **own** vertex declarations, so the decoder doesn't need `-vd.big` (phase 0 guessed it did) |
| mission / data `.txt`, `.csv` | `datafile.big`, CW loose `.csv` | ✅ text | engine scripting; edited for co-op in the CZ recomp |
| `.bik` | **CW only**, `data/movies` | ✅ (Bink) | ffmpeg decodes it; replacing it needs a Bink encoder |

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
- **`compression` (the last index word; `resv` in the recomp's tools)** is `2` on every
  LZX-compressed entry and `0` on every stored one; no other value occurs. For stored
  entries `size == size2` always. mariokart64n's MaxScript says `1` means zlib on PC;
  never seen on 360, but the reader supports it.
- **`hash`** is the engine's string hash (`dr2kit/hashing.py`) **of the lower-cased
  name**, for all 124,932 (CZ) + 172,322 (CW) entries. Recompute it for new entries.
- **`flags`**: meaning still unknown, so it is **preserved on write**. Values and where they occur:

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
0x09  u8   0x23 (every CZ texture) / 0x24 (all but 4 CW textures): writer version?
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
| `_BONEHIERARCHY_` | 8·n | (u32 index, s32 parent) pairs: the **same pairs as the node records, in a parents-first order** (✅ every scene; equal to the records' order in characters, different in 158 CZ props) |
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
its suffix (`_cm` colour, `_nm` normal, `_sm` specular, `_mask` tint mask; a trailing
digit is allowed: `mech_eye_cm1`).

**A draw names its material by id: RenderStrip word 0 = id − 1** (✅). *Found the hard
way:* phase 3 first read word 0 as a position in `MatArray`, which is right for Chuck's
parts (stored in id order) and wrong for `boss_mechanic.big` (ids 5, 4, 10, 1, 3, 11, …):
his apron wore the shoes texture. The user spotted it in a DR2 Studio screenshot
that had already been reviewed and passed as correct. With the id
rule every mesh gets its own texture (apron → `mech_apron_cm`, head → `mech_head_cm`);
the census checks that every draw of both games finds exactly one material with that id.

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
| SHORT2N | `0x2C2159` | TEXCOORD 1-5 | 3,033 | 6,579 | two 16-bit signed normalised, **x = low half of the BE word** |
| UBYTE4N | `0x1A2086` | BLENDWEIGHT | 2,121 | 2,452 | 4 bytes / 255, **x = low byte of the BE word** (the four sum to 255 on every vertex) |
| UBYTE4 | `0x1A2286` | BLENDINDICES | 2,121 | 2,452 | 4 bytes, x = low byte |
| D3DCOLOR | `0x182886` | COLOR4 | 4 | 1 | `0xAARRGGBB` |

**Byte order:** every element is read as big-endian 32-bit words and component *x* is in
the **low** bits. This is how the CZ recomp's renderer fetches vertices (it draws both
games correctly), and the skin weights only sum to 255 this way round.

**Signed normalised values are not clamped** (phase 4). A *b*-bit field holds *q* and
decodes to *q* / (2^(b−1) − 1). The lowest code, −2^(b−1), gives slightly less than −1
(−1.002 for 10 bits); the GPU clamps it to −1. The games store −1.0 **that way** on most
fields (DEC4N x/y/z never use −511), while HEND3N also has −(2^(b−1) − 1) in places, and
the 2-bit tangent w uses `11` (−1), never `10`. Phase 3's decoder clamped to −1, which
made two codes decode alike, so the encoder could not give the stored bits back
(60,537 CZ and 701,150 CW tangents, 129,755 / 1,139,556 normals). *Retraction
(2026-10-08):* "clamped to −1" is gone; with the unclamped rule, every element of
every vertex of both games re-encodes to its stored bytes (census below).

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

- `.xma` entries hold raw XMA (8,916 entries in CZ, 11,735 in CW; in banks such as `charvocals.big` with 985 entries,
  `music.big` with 16 licensed tracks, and `cinematics.big` at 110 MB). The payload is
  0x800-aligned. The first bytes (`40 00 01 00 …`, `48 00 01 00 …`) look like XMA packet
  headers rather than a RIFF container. **There is no `RIFF`/`XMA2` header, so channels and
  sample rate must come from elsewhere:** the audio scene scripts, a bank table such as
  `cache.big`, or the recomp's runtime log of the XMA contexts it decodes.
- `runtime/audio/xma_decoder.cpp` (CZ recomp) shows the ffmpeg `xma2` setup:
  34-byte XMA2 extradata, block size 0x10000.
- Audio scene scripts (`audio/Prologue.txt`) map events to banks and assets, e.g.
  `BigFile = "fx_mechanic.big"`, `Asset = "music.big/Celldweller_TheBestItsGonnaGet_…"`.
  That gives the index human-readable names for sounds.

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

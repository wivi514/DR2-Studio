# File formats

Status key: **✅ cracked** (verified against an oracle or census) · **🟡 partial** · **❓ unknown**.
"Verified" names the check. Unless stated, facts come from Case Zero and still need a
Case West census before they count as rules (CLAUDE.md rule 7).

| Format | Where | Status | Notes |
|---|---|---|---|
| `.big` container | everywhere, nested (up to 3 levels) | ✅ read + write | `dr2kit/container/big.py`. Every archive of both games round-trips byte-identically (phase 1 census, below) |
| LZX compressed entry | inside `.big` | ✅ decode + encode | `dr2kit/container/xcompress.py`, `lzx/`. Every compressed entry of both games decodes (two independent decoders agree) and re-encodes |
| `.bct` texture | loose, inside `.tex` | 🟡 | header + tiling known; magic is `05 01 01` + a flags byte (retraction below); format-code table and mips not yet |
| `.tex` texture pack | next to every model `.big` | ✅ | a `.big` whose entries are `.bct`, named without extension |
| scene (model / skeleton) | `models/**/*.big`, `skeleton/*.big` | 🟡 | chunk table known; bone records ✅; vertices ❓ |
| `.xma` audio | `audio/*.big` | 🟡 | raw XMA, decoded on the host by the recomp through ffmpeg; header and rate source ❓ |
| audio scene scripts `.txt` | `audio/Prologue.txt`, `datafile.big` | ✅ text | `cAudioScene` / `cAudioJukebox` tree, `Asset = "music.big/<name>"` |
| `.bcs` string bank | `frontend/str_<lang>.bcs` | ✅ | `gen_pc_options.patch_bcs` reads and patches it |
| `.bcf` font | `system/**` | 🟡 | 9 of 11 in CZ and 6 of 11 in CW are plain `.big` archives (read by the census); the rest start `04 03 02 01`, an unknown sibling container ❓ |
| `.anm` / anim `.big` | `anim/**`, `skeleton/*.anm` | ❓ | |
| ragdoll `.dat` | `skeleton/*_ragdoll.dat` | ❓ | Havok likely (`hkp*` RTTI in the XEX) |
| shader banks `.vo/.po/.vdo/.pdo/.sdo/.scv` | `shaders/*-{vs,ps,vd,pd,sc,sd,ss}.big` | 🟡 | 98.6% of microcode located; `-vd` = vertex declarations, which the vertex decoder needs |
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
  holds several `Combined Vertices` entries" as the example; those are numbered
  (`Combined Vertices 0`, `… 1`) and are not duplicates.
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

A `.tex` file is a `.big` holding one or more `.bct` payloads, named without extension
(e.g. `goretech_head_combine_cm`). The name suffix gives the role: `_cm` colour map; other
suffixes (`_nm`, `_sm`, …) still need a census.

`.bct` header, 48 bytes, big-endian:

```
0x00  05 01 01 xx        magic 05 01 01, then a flags-like byte (see retraction below)
0x04  u16 width, u16 height
0x08  24 bytes           Xenos GPUTEXTURE_FETCH_CONSTANT-like words (format, tiling, pitch, mip info)
0x20  …                  more header words (seen: 0x00000018, 0, 0x30 = data offset?, sizes)
0x30  payload            tiled; DXT payloads are 16-bit-word big-endian (swap16 before decoding)
```

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

All 13 values have bit `0x02` set; it looks like a flags byte (phase 2). 11 `.bct` entries
in CZ's `streamedassets.big` weapon models are empty (0 bytes).

Examples: `grid.bct` 128×128; `goretech_head_combine_cm` 512×512; `cc_03.bct`
1024×32 = a 32³ colour-grading LUT unrolled into a 2D strip.

**TODO (phase 1):** decode the fetch-constant words into (format, endian, tiled, pitch,
mip levels, packed mips, dimension/cube), using the recomp's `vk_renderer.cpp` texture
path as the reference, then run a census over every `.bct` in both games: format
histogram, cube count, mip presence, zero unparsed.

## Scene container (models and skeletons)

A model or skeleton is a `.big` of named chunks. All chunk payloads are big-endian.
Chunks seen:

| Chunk | Size seen | Meaning (status) |
|---|---|---|
| `SceneHeader` | 20 | 5×u32, e.g. `1, 2, 2, 0x21, 2` (❓; 0x21 = 33 matches the head model's total node count) |
| `SceneDescription` | 1188 / 3528 | node list: fixed 32-byte name + u32 type (2 seen), then `…Shape` / `COL_…Shape` shape names (Maya export) (🟡) |
| `_BONEHIERARCHY_` | 8·n | pairs of (BE u32 node index, BE s32 parent), `-1` = root (✅ by inspection) |
| `_BONENAMES_` | | NUL-padded names, 31-32 bytes each (🟡 confirm stride) |
| `<root>.<bone>` or `<bone>` | **52 each** | one per node: the transform record below (✅) |
| `Combined Vertices` | several | vertex streams (❓ layout, from the vertex declaration) |
| `Combined Indices` | | index buffer (❓ 16-bit BE likely; strips or lists?) |
| `MatArray` | 36·n | per material: u32 id, u32 shader hash, … floats (`0.7`, `0.5`, `1.0`), `0xFFFFFFFF` terminator (🟡) |
| `MatTextureInfoArray` | 100·n? | per slot: u32 index, 52-byte NUL-padded texture name, u32 hash, u32s… Includes engine samplers (`gCascadedShadowMapTexture`, `gExposureTexture`, `gAttenuatedShadowMapTexture`) next to the model's own textures (🟡) |
| `UsedShaders.txt` | text | `0xE9EA5720 : LIT_CM`, shader hash to name |
| `_ATTRIBUTE_`, `_ANIMCHANNELINFO_`, `_COLLPRIMS_`, `NumLocatorArray` | small | ❓ |
| `persistent.big` | nested | a nested container; in PC DR2 it holds collision (per the fandom wiki) (❓ on 360) |

Skeleton files (`data/skeleton/*.big`) have the **same chunks with empty material
arrays and no geometry.** So one reader serves both.

### Node transform record — 52 bytes, BE ✅

```
0x00 u32  node index
0x04 s32  parent index (-1 = root)
0x08 u32  flag: 1 on 3,414 records, 0 on 60 (❓ meaning; preserve it)
0x0C f32×3 scale        (1,1,1 typical)
0x18 f32×3 translation
0x24 f32×4 rotation quaternion (x, y, z, w)
```

**Verified 2026-10-08:** every record in all 76 skeleton files of CZ and CW together
(3,474 records) has a unit-norm quaternion, and no parent index points at a missing node.
Rig families: `player`, `female`, `large`, `child`, `longcloak`, `tiger`, `zombie`, each split
into `fullbody` / `upperbdy` / `face` / `hand` / `root`, plus `cine*` variants, `camera`,
`stage` and `prop`. Bone names look like `dummy01.l_thigh`, `dummy01.r_clavicle`,
`dummy01.l_eyebrowcorner`.

**Open (phase 3):** vertex layout, the per-mesh bone palette (the old community
blocker), how meshes reference materials, how LODs are stored, what `persistent.big`
holds on 360.

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

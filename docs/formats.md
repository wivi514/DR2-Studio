# File formats

Status key: **✅ cracked** (verified against an oracle or census) · **🟡 partial** · **❓ unknown**.
"Verified" names the check. Unless stated, facts come from Case Zero and still need a
Case West census before they count as rules (CLAUDE.md rule 7).

| Format | Where | Status | Notes |
|---|---|---|---|
| `.big` container | everywhere, nested | ✅ | CZ recomp `docs/big-archive-format.md` |
| LZX compressed entry | inside `.big` | ✅ decode + encode | `big_decompress.cpp`, `gen_pc_options.lzx_encode_stream` |
| `.bct` texture | loose, inside `.tex` | 🟡 | header + tiling known; full format-code table and mips not yet |
| `.tex` texture pack | next to every model `.big` | ✅ | a `.big` whose entries are `.bct`, named without extension |
| scene (model / skeleton) | `models/**/*.big`, `skeleton/*.big` | 🟡 | chunk table known; bone records ✅; vertices ❓ |
| `.xma` audio | `audio/*.big` | 🟡 | raw XMA, decoded on the host by the recomp through ffmpeg; header and rate source ❓ |
| audio scene scripts `.txt` | `audio/Prologue.txt`, `datafile.big` | ✅ text | `cAudioScene` / `cAudioJukebox` tree, `Asset = "music.big/<name>"` |
| `.bcs` string bank | `frontend/str_<lang>.bcs` | ✅ | `gen_pc_options.patch_bcs` reads and patches it |
| `.bcf` font | `system/**` | ❓ | |
| `.anm` / anim `.big` | `anim/**`, `skeleton/*.anm` | ❓ | |
| ragdoll `.dat` | `skeleton/*_ragdoll.dat` | ❓ | Havok likely (`hkp*` RTTI in the XEX) |
| shader banks `.vo/.po/.vdo/.pdo/.sdo/.scv` | `shaders/*-{vs,ps,vd,pd,sc,sd,ss}.big` | 🟡 | 98.6% of microcode located; `-vd` = vertex declarations, which the vertex decoder needs |
| mission / data `.txt`, `.csv` | `datafile.big`, CW loose `.csv` | ✅ text | engine scripting; edited for co-op in the CZ recomp |
| `.bik` | **CW only**, `data/movies` | ✅ (Bink) | ffmpeg decodes it; replacing it needs a Bink encoder |

## `.big` container — summary

Full spec with history: `../Dead_Rising_2_Case_Zero_Xenon_Recomp/docs/big-archive-format.md`.

```
LE header: magic 06 05 04 03 | data_start | total_size | entry_count | 0x18 | names_offset
LE index, 28 bytes/entry: name_offset | hash | size(stored) | size2(uncompressed) | data_offset | flags | resv
names: NUL-terminated, variable length, read from each entry's name_offset
```

- `resv == 2` ⇔ compressed (1,671/1,671 in CZ), `resv == 0` ⇔ stored.
- `flags` is `0x80` in the shader banks, `0x4` for scene chunks and `0x800` in audio banks.
  Meaning unknown: **preserve it on write.**
- The `hash` is the engine's string hash of the name (`tools/name_hash.py`); recompute
  it for new entries.
- Payload alignment differs by archive (0x800 for audio and model packs, 4 or tighter
  for scene chunks). Preserve each archive's alignment on write.
- **Nesting:** `npcs.big` → `boss_mechanic.big` (a scene) → `persistent.big` (another
  container). Virtual paths address any level.
- Duplicate names exist within one archive (a scene holds several `Combined Vertices`
  entries). Index entries by **position**, not only by name.
- Mariokart64n's MaxScript notes a flag value 1 = **zlib** (seen in the PC games).
  Support it in the reader even though no 360 entry is known to use it.

### Compressed entry stream (BE)

```
u32 uncompressed_size (== size2) | u32 window (0x8000)
repeat: per-chunk header (0xFF, BE u16 unc_len, BE u16 comp_len) + independent LZX stream
```

The game rejects stored entries where it expects compression, and degenerate LZX
streams. Re-encode with the real encoder, then decode the result and compare.

## Textures: `.tex` and `.bct`

A `.tex` file is a `.big` holding one or more `.bct` payloads, named without extension
(e.g. `goretech_head_combine_cm`). The name suffix gives the role: `_cm` colour map; other
suffixes (`_nm`, `_sm`, …) still need a census.

`.bct` header, 48 bytes, big-endian:

```
0x00  05 01 01 E2        magic (every loose .bct and every decoded one)
0x04  u16 width, u16 height
0x08  24 bytes           Xenos GPUTEXTURE_FETCH_CONSTANT-like words (format, tiling, pitch, mip info)
0x20  …                  more header words (seen: 0x00000018, 0, 0x30 = data offset?, sizes)
0x30  payload            tiled; DXT payloads are 16-bit-word big-endian (swap16 before decoding)
```

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

- `.xma` entries hold raw XMA (in banks such as `charvocals.big` with 985 entries,
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

## Case West differences (to fill in during phase 1)

- Extra `.bik` movies (Bink; the guest decodes them).
- `data/controls`, `data/dynamicprops`, `data/models/zombies/`, `shaders/settings`.
- 154 archives against CZ's 146. Run every census on both.

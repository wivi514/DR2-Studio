# Phase 2 kickoff: textures, index, first GUI, first mod

> **Historical.** Phase 2 was completed on 2026-10-08 (devlog, "Phase 2"); the next
> handoff is [`phase3-kickoff.md`](phase3-kickoff.md). Kept as the record of the plan.
> Corrected since: the `.bct` header holds no fetch constant (`formats.md` §Textures),
> and the in-game gate used Chuck's own outfit textures, not a generic `npcs.big` one.

A handoff for the session that starts phase 2. Read `CLAUDE.md` first (especially the
documentation rules), then this. Scope and gate: `roadmap.md` §Phase 2. What phase 1
built: `dev/code-tour.md`; what it learned: `devlog.md` (2026-10-08, "Phase 1").

## What phase 1 gives you

- `BigArchive` read/edit/write with byte-identical round trips on every archive of both
  games, and `BigEntry.set_data()`, which re-encodes LZX when the entry was compressed.
- `AssetTree` + vpaths to reach any texture, e.g.
  `data/models/npcs.big/boss_mechanic.tex/mech_apron_cm` (two levels deep, both
  compressed on the way: `npcs.big` stores `boss_mechanic.tex` compressed).
- `dr2 census`: add texture counters there (step 2) rather than writing a new walker.

## Order of work

1. **`.bct` header decode** (`dr2kit/formats/bct.py`). Sources:
   - `../Dead_Rising_2_Case_Zero_Xenon_Recomp/tools/tex_decode.py`: `tiled2d()`
     (`Tiled2DOffset`, from the XDK's `XGAddress2DTiledOffset` via
     `runtime/gpu/vk_renderer.cpp`), DXT1/DXT5 block decoders, and the BE 16-bit-word
     swap.
   - The texture fetch-constant path in `runtime/gpu/vk_renderer.cpp` (format codes,
     pitch, mip and packed-mip rules). Also `tools/packed_mip_derive.py`.
   - `formats.md` §Textures. **The 4th magic byte varies** (13 values, `E2` in over 80%;
     table in `formats.md`); find what each bit means. `dr2 census` prints its histogram.
2. **Census of every texture in both games**: format, size, mips, cube, the magic
   byte, zero unparsed. Textures are `.bct` entries **and** extension-less entries in
   `.tex` packs (mostly `flags 0x10`): 12,224 in CZ and 23,126 in CW, counted by the
   census's `05 01 01` oracle.
3. **Decode to PNG** (`dr2kit/convert/texture.py`), numpy fast path + pure-Python
   fallback. `dr2 export-texture` (or extend `extract --convert`).
4. **SQLite index** (`dr2kit/index/`), schema in `ARCHITECTURE.md` §The asset index.
5. **DR2 Studio v0** (PySide6): tree, search, texture viewer, extract. Write
   `dev/studio.md`.
6. **Texture replacement** (same size and format): PNG → DXT → tile → `.bct` → `.tex` →
   LZX → archive. Gate: decode then re-encode gives back the original block data for
   lossless cases.
7. **Recomp `game_mods/` VFS layer**, in both recomps (approved; `ARCHITECTURE.md`
   §Recomp integration). The overlay chain is in each recomp's `runtime/kernel/vfs.cpp`
   (`game_bootskip`, `game_kbm`, `game_patched`). Follow each recomp's own CLAUDE.md:
   an off switch (`CZ_NO_MODS=1` / `CW_NO_MODS=1`), a log line per served file, a gotcha
   entry. Write `dev/recomp-integration.md`.
8. **First mod package** + the in-game gate: a recoloured texture inside a
   *compressed* `.tex` (e.g. one in `npcs.big`) shows up in both recomps and disappears
   with the off switch. This is also the first proof that the game accepts our LZX
   encoder's streams; nothing before this has shown it.
9. Guides: `modding/03-browsing.md`, `04-extracting.md` (textures part),
   `05-first-mod-texture.md`, `06-mod-packages.md`, the start of `asset-catalogue.md`.

## Facts to keep in mind

- Textures in `.tex` packs: payloads aligned to 16 (sometimes 0x800); keep each entry's
  `alignment` (the writer already does).
- Our encoder's streams are 7% larger than the shipped ones and use verbatim blocks
  (plus uncompressed blocks for chunks that don't compress). The game's encoder mostly
  uses *aligned offset* blocks. If the game rejects our output, compare block types
  first (`formats.md`, "Compressed entry stream").
- The CZ recomp found that `preload4.big`'s boot preload rejected its re-encodes, while
  `datafile.big`'s path accepted a 7-chunk stream. Test the in-game gate on a normal
  model `.tex` before anything in `preload4.big`.
- CW's `preload4.big` has 27 empty entries (`00 00 00 00`). The writer reproduces them;
  don't "fix" them.

## Test data policy (unchanged)

Unit tests build tiny synthetic textures in code (a 64×64 DXT1 made by our own encoder
is fine). Census and decode tests read the real games through the profiles and skip with
a message when a game is absent. No game textures, thumbnails or PNGs in the repository.

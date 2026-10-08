# Phase 1 kickoff: core container and census

A handoff for the session that starts phase 1. Read `CLAUDE.md` first (especially the
documentation rules), then this. Scope and gate: `roadmap.md` §Phase 1.

## Order of work

1. **Project skeleton.** `pyproject.toml` (Python ≥ 3.11, package `dr2kit`, console script
   `dr2`), `dr2kit/__init__.py`, `tests/`, `.github/workflows/ci.yml` (matrix:
   windows-latest, ubuntu-22.04, macos-14; unit tests only). Dev dependencies: pytest.
   Runtime: `platformdirs`; numpy optional. Write `docs/dev/setup.md` and the first
   `docs/dev/code-tour.md` at the same time.
2. **Game profiles + data discovery** (`dr2kit/profiles/`): `cz.toml`, `cw.toml`; discover
   `../Dead_Rising_2_Case_{Zero,West}_Xenon_Recomp/assets/game/`, or take a user-given
   `data/` folder. STFS extraction can come later in the phase; port it from the CZ
   recomp's `tools/extract_stfs.py`.
3. **`.big` reader** (`dr2kit/container/big.py`), from these sources:
   - `../Dead_Rising_2_Case_Zero_Xenon_Recomp/tools/big_list.py` (listing, variable-length names)
   - `../Dead_Rising_2_Case_Zero_Xenon_Recomp/tools/gen_pc_options.py` `read_big` (line ~70), `write_big` (~87)
   - spec: `../Dead_Rising_2_Case_Zero_Xenon_Recomp/docs/big-archive-format.md`

   Requirements: entries addressed by position *and* name (duplicate names exist);
   preserve `flags`, `resv`, hash, alignment and name-table layout so writes can be
   byte-identical; nested archives through vpaths (`dr2kit/container/vpath.py`,
   case-insensitive).
4. **`dr2 ls` / `dr2 census`** on the reader, then **run the census on both games**. Record
   in `formats.md`: the CW totals (archive count, entry count, extension histogram,
   compressed count, flag/resv values) next to CZ's.
5. **`.big` writer**, then the **round-trip gate** on every archive in both games.
6. **LZX decode:** native library + ctypes loader (`native/lzx/`, `dr2kit/container/lzx/`).
   Gate: every compressed entry in both games decodes to its `size2`.
7. **LZX encode:** port `lzx_encode_stream` (~line 262) + `verify_fake_lzx` (~469) from
   `gen_pc_options.py`. Gate: re-encoding then decoding gives back the input for every
   compressed entry (the game-acceptance proof comes in phase 2, through `game_mods/`).
8. **`dr2 extract [--decompress]`**, then `docs/modding/02-game-data.md`,
   `docs/dev/adding-a-format.md` and `docs/dev/testing.md`, then a devlog entry.

## Licensing of reused code (checked 2026-10-08)

| Source | License | How to reuse |
|---|---|---|
| CZ/CW recomp tools (`big_list.py`, `gen_pc_options.py`, `tex_decode.py`, `extract_stfs.py`, …) | PolyForm Noncommercial 1.0.0, © wivi514 | Same author, so they can be re-licensed into this project. Note the origin in each module docstring. |
| XenonRecomp `lzxDecompress` wrapper (`XenonUtils/xex_patcher.cpp`) | MIT (hedge-dev) | Keep the copyright notice. |
| libmspack `lzxd.c` (the actual LZX decoder, in `XenonRecomp/thirdparty/libmspack`) | **LGPL-2.1** | Fine as a **separate shared library** loaded through ctypes. Ship its source and license, and let users swap the library. **Do not** translate `lzxd.c` line by line into the pure-Python fallback (that would make the fallback LGPL too). Write the fallback from the LZX format description, or accept the fallback as LGPL in its own module and say so. |

Create `THIRD_PARTY.md` listing each one when the first piece of third-party code lands.

## Facts to keep in mind (all in `formats.md`)

- LE header and index; BE compressed streams and payloads.
- `resv == 2` ⇔ compressed; `size` = stored length, `size2` = uncompressed length.
- `flags`: 0x80 (shader banks), 0x4 (scene chunks), 0x800 (audio). Meaning unknown: preserve it.
- Stored replacements for compressed entries crash the game. So do degenerate LZX streams.
- 146 archives / 12,481 entries / 1,671 compressed in CZ (counted by the recomp's
  `big_list`). CW not yet counted.

## Test data policy

Unit tests build tiny synthetic `.big` files in code. Census and round-trip tests read
the real games through the profiles and **skip with a clear message** when a game is
missing. CI has no game data, so only unit tests run there.

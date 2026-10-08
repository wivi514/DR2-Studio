# Third-party code

What this toolkit contains or derives from other people's work, under which license,
and how it is used. Checked 2026-10-08 (docs/phase1-kickoff.md, "Licensing of reused code").

| Component | Where | License | How it is used |
|---|---|---|---|
| **libmspack** `lzxd.c` and its headers, © Stuart Caie and contributors | `native/lzx/libmspack/` (unmodified copy of libmspack commit `3059077`, taken from XenonRecomp's `thirdparty/libmspack` submodule) | **LGPL-2.1** (`native/lzx/libmspack/COPYING.LIB`) | Compiled into the **separate shared library** `dr2lzx` (`.so` / `.dll` / `.dylib`), which dr2kit loads at run time through ctypes. The rest of the toolkit does not link it. You may rebuild that library from this source, or from a modified libmspack, and drop it in place (`DR2KIT_LZX_LIBRARY`, see `docs/dev/setup.md`). |
| XenonRecomp `lzxDecompress` (in-memory `mspack_system`) © 2025 hedge-dev and contributors, adapted from Xenia © 2023 Ben Vanik | the approach in `native/lzx/dr2lzx.c` | MIT (XenonRecomp), BSD (Xenia) | `dr2lzx.c` is a fresh, smaller C wrapper written the same way; the notices are kept in its header comment. |
| Case Zero recomp tools: `big_list.py`, `gen_pc_options.py` (`read_big`, `write_big`, `lzx_encode_stream`, `huffman_lengths`, `canonical_codes`), `extract_stfs.py`, `name_hash.py` | ported into `dr2kit/container/big.py`, `lzx/encode.py`, `xcompress.py`, `stfs.py`, `dr2kit/hashing.py` | PolyForm Noncommercial 1.0.0, © wivi514 | Same author; re-licensed into this project under its `LICENSE`. Each module's docstring names its origin. |
| Xenia-Canary `xcontent_container_device.cc` | format description behind `dr2kit/container/stfs.py` | BSD | Read as a format reference by the original `extract_stfs.py`; no code copied. |
| UnleashedRecomp `install/xcontent_file_system.cpp` | consulted for `stfs.py` | GPLv3 | Format reference only; no code copied. |

## Not copied, on purpose

- **The pure-Python LZX decoder** (`dr2kit/container/lzx/pydecode.py`) was written from
  the published LZX format description, **not** translated from `lzxd.c`, so it is not
  LGPL. Please keep it that way: don't port code from `lzxd.c` into it.

## Optional run-time dependencies (not shipped)

| Package | License | Used for |
|---|---|---|
| `platformdirs` | MIT | per-OS config folder |
| `numpy` (optional) | BSD | fast paths from phase 2 |
| `pytest` (dev) | MIT | tests |
| `av` / PyAV (later phases) | BSD; its bundled ffmpeg is LGPL | XMA and Bink decoding |

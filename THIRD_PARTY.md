# Third-party code

What this toolkit contains or derives from other people's work, under which license,
and how it is used. Checked 2026-10-08 (docs/phase1-kickoff.md, "Licensing of reused code").

| Component | Where | License | How it is used |
|---|---|---|---|
| **libmspack** `lzxd.c` and its headers, © Stuart Caie and contributors | `native/lzx/libmspack/` (unmodified copy of libmspack commit `3059077`, taken from XenonRecomp's `thirdparty/libmspack` submodule) | **LGPL-2.1** (`native/lzx/libmspack/COPYING.LIB`) | Compiled into the **separate shared library** `dr2lzx` (`.so` / `.dll` / `.dylib`), which dr2kit loads at run time through ctypes. The rest of the toolkit does not link it. You may rebuild that library from this source, or from a modified libmspack, and drop it in place (`DR2KIT_LZX_LIBRARY`, see `docs/dev/setup.md`). |
| XenonRecomp `lzxDecompress` (in-memory `mspack_system`) © 2025 hedge-dev and contributors, adapted from Xenia © 2023 Ben Vanik | the approach in `native/lzx/dr2lzx.c` | MIT (XenonRecomp), BSD (Xenia) | `dr2lzx.c` is a fresh, smaller C wrapper written the same way; the notices are kept in its header comment. |
| Case Zero recomp tools: `big_list.py`, `gen_pc_options.py` (`read_big`, `write_big`, `lzx_encode_stream`, `huffman_lengths`, `canonical_codes`), `extract_stfs.py`, `name_hash.py` | ported into `dr2kit/container/big.py`, `lzx/encode.py`, `xcompress.py`, `stfs.py`, `dr2kit/hashing.py` | PolyForm Noncommercial 1.0.0, © wivi514 | Same author; re-licensed into this project under its `LICENSE`. Each module's docstring names its origin. |
| CZ recomp `tools/tex_decode.py` (`tiled2d`, DXT1/DXT5 block decode) and `runtime/gpu/vk_renderer.cpp` (`Tiled2DOffset`, `PackedLevelOffset`, texture format table) | `dr2kit/formats/bct.py` (`tiled_offset`, `packed_level_offset`), `dr2kit/convert/dxt.py` | PolyForm Noncommercial 1.0.0, © wivi514 | Same author; re-licensed here. `Tiled2DOffset` is the XDK's `XGAddress2DTiledOffset` behaviour as transcribed by the recomp. |
| Xenia `src/xenia/gpu/texture_util.cc` (`GetPackedMipOffset`, `GetGuestTextureLayout` mip sizing) | the packed-mip offset rule and the power-of-two mip sizing in `dr2kit/formats/bct.py`, via the CZ recomp's transcription | BSD-3-Clause | A ~20-line layout rule, recorded here per the recomp's rule; verified against real texture data (`formats.md` §Textures). |
| Xenia-Canary `xcontent_container_device.cc` | format description behind `dr2kit/container/stfs.py` | BSD | Read as a format reference by the original `extract_stfs.py`; no code copied. |
| UnleashedRecomp `install/xcontent_file_system.cpp` | consulted for `stfs.py` | GPLv3 | Format reference only; no code copied. |

| **three.js** 0.186.1 (`build/three.module.js`, `three.core.js`, `examples/jsm/loaders/GLTFLoader.js`, `controls/OrbitControls.js`, `utils/BufferGeometryUtils.js`, `utils/SkeletonUtils.js`), © 2010-2026 three.js authors | `dr2kit/studio/web/vendor/three/` (unmodified files from the npm package `three-0.186.1.tgz`, sha1 `6d50f70c2c437f844179bbb56d6f5b774e1ca38a`, with its `LICENSE`) | MIT | Loaded by DR2 Studio's 3D view page; shipped so Studio works offline. |
| XenosRecomp (hedge-dev) | used once, outside the repo, to translate the game's `ProtoSkinnedClothRGB` vertex shader to HLSL | MIT | Read to learn how weights pair with bone indices (`formats.md` §Skinning); nothing copied. |

## Not copied, on purpose

- **The pure-Python LZX decoder** (`dr2kit/container/lzx/pydecode.py`) was written from
  the published LZX format description, **not** translated from `lzxd.c`, so it is not
  LGPL. Please keep it that way: don't port code from `lzxd.c` into it.

## Optional run-time dependencies (not shipped)

| Package | License | Used for |
|---|---|---|
| `platformdirs` | MIT | per-OS config folder |
| `numpy` (optional) | BSD | fast paths from phase 2 (untiling, DXT decode/encode, PNG filters) |
| `PySide6` (optional, `[studio]`) | LGPL-3.0 | DR2 Studio, the GUI; used as an unmodified, dynamically loaded library |
| `Pillow` (optional) | HPND (MIT-like) | faster PNG reading, and interlaced PNGs; the toolkit's own pure-Python PNG reader is used without it |
| `pytest` (dev) | MIT | tests |
| `av` / PyAV (optional, `[audio]`, `[studio]`) | BSD; the ffmpeg its wheels bundle reports **LGPL-3.0+** (`--enable-version3`), and the wheels also carry **x264 and x265, which are GPL** (checked on PyAV 19.0.1, Linux x86_64: `av._core.library_meta`, `av.libs/`) | XMA decoding (phase 5: preview, WAV export, the census, fitting sound mods); Bink movies (phase 6: preview, `.mp4` export with ffmpeg's own LGPL `mpeg4` and `aac` encoders; the toolkit never uses x264/x265). Used unmodified, as a dynamically loaded library. **Packaging note:** a release bundle that includes these wheels ships GPL libraries; see `docs/dev/packaging.md` |
| Qt Multimedia (part of PySide6) | LGPL-3.0 | DR2 Studio's audio playback (`QAudioSink`) |

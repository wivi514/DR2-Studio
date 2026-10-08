# dr2lzx: the native LZX decoder

A small shared library with one job: decode one LZX stream fast. dr2kit loads it through
ctypes (`dr2kit/container/lzx/native.py`) and falls back to pure Python when it is
missing, so building it is optional, but the Python decoder is roughly 30x slower.

| File | What |
|---|---|
| `dr2lzx.c` | the wrapper: an in-memory libmspack "system" and `dr2lzx_decompress()` |
| `libmspack/` | unmodified libmspack sources (`lzxd.c` + headers), **LGPL-2.1**, see `COPYING.LIB` |
| `CMakeLists.txt` | builds `libdr2lzx.so` / `dr2lzx.dll` / `libdr2lzx.dylib` |

Build (any OS with CMake and a C compiler):

```
cmake -S native/lzx -B native/lzx/build -DCMAKE_BUILD_TYPE=Release
cmake --build native/lzx/build --config Release
```

dr2kit finds the result in `native/lzx/build/` by itself; `dr2 doctor` confirms it.
Why it is a separate library, and what the license means for you: `THIRD_PARTY.md`.
Full setup guide: `docs/dev/setup.md`.

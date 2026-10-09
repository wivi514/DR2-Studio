# Developer setup

How to get a working copy of the toolkit on **Windows, Linux or macOS**, run the tests,
and build the native LZX library. If you only want to *use* the toolkit to mod, read
[`../modding/02-game-data.md`](../modding/02-game-data.md) instead.

## What you need

| | Why | Required? |
|---|---|---|
| Python **3.11 or newer** | the toolkit is Python | yes |
| git | to get the code | yes |
| CMake 3.16+ and a C compiler | to build the fast LZX decoder | no (a pure-Python fallback is used without it, roughly 30x slower) |
| One of the games | for game-data tests and real work | no for unit tests |

C compilers: Visual Studio Build Tools ("Desktop development with C++") on Windows,
Xcode command-line tools (`xcode-select --install`) on macOS, `gcc` or `clang` on Linux.

## Get the code and install it

```
git clone <the repository URL>
cd DR2_CZ_CW_Modding
python -m venv .venv
```

Activate the virtual environment:

- Windows (PowerShell): `.venv\Scripts\Activate.ps1`
- Linux / macOS: `source .venv/bin/activate`

Then install the toolkit in *editable* mode (your code changes apply without
reinstalling), with the test tools:

```
python -m pip install -e ".[dev]"
```

This gives you the `dr2` command. `python -m dr2kit` does the same if `dr2` isn't on
your PATH.

Optional extras (phase 2):

```
python -m pip install -e ".[dev,studio]"   # + PySide6 and numpy: DR2 Studio (`dr2 studio`)
python -m pip install numpy pillow         # just the fast paths (texture work ~50x faster)
```

Everything works without numpy and Pillow (pure-Python fallbacks, tested in CI), just
slower: the texture census and the index build want numpy.

## Build the native LZX library (recommended)

About one entry in eight is LZX-compressed (glossary: [LZX](../glossary.md)). The native
decoder reads them fast; without it, dr2kit uses its pure-Python decoder and says so.

```
cmake -S native/lzx -B native/lzx/build -DCMAKE_BUILD_TYPE=Release
cmake --build native/lzx/build --config Release
```

On macOS, add `-DCMAKE_OSX_ARCHITECTURES="arm64;x86_64"` to the first command for one
library that runs on both Apple Silicon and Intel Macs.

Check that it's picked up:

```
dr2 doctor
```

should print `LZX decoder: native (…/native/lzx/build/libdr2lzx.so)` (or `dr2lzx.dll`,
`libdr2lzx.dylib`). The loader looks, in order, at:

1. the file named by the `DR2KIT_LZX_LIBRARY` environment variable;
2. `dr2kit/container/lzx/_native/` (where release builds will put a prebuilt library);
3. `native/lzx/build/` and its `Release/`, `RelWithDebInfo/`, `Debug/` subfolders.

`DR2KIT_LZX=python` forces the pure-Python decoder, which is useful to test it.

**macOS note:** a library you build yourself runs fine. A *downloaded* unsigned library
may be blocked by Gatekeeper; dr2kit then falls back to Python and `dr2 doctor` says why.

## Point it at the games

If the Case Zero / Case West recomps sit next to this checkout
(`../Dead_Rising_2_Case_Zero_Xenon_Recomp`, `../Dead_Rising_2_Case_West_Xenon_Recomp`),
nothing is needed: `dr2 games` finds them. Otherwise see
[`../modding/02-game-data.md`](../modding/02-game-data.md) (`dr2 games set`,
`dr2 unpack`, or the `DR2_CZ_DATA` / `DR2_CW_DATA` environment variables).

## Run the tests

```
python -m pytest -q                      # everything; game-data tests skip without a game
python -m pytest -q -m "not gamedata"    # unit tests only (what CI runs)
python -m pytest -q -m "not slow"        # skip the full-game census tests (~30 s)
```

The phase gates that take minutes, or need Blender or a recomp, are not tests; run them
by hand:

```
dr2 census --reencode --python-lzx          # phase 1: LZX (~20 min)
dr2 census --textures                       # phase 2: every texture re-encodes (~10 min)
dr2 census --models                         # phase 3: every model draw decodes (~2 min)
python tools/blender_skeleton_gate.py       # phase 3: rigs through Blender (needs Blender)
python tools/capture_gate.py <capture dir>  # phase 3: reader vs a recomp capture
```

The capture recipe is in [`recomp-integration.md`](recomp-integration.md) §Phase 3.

What each kind of test proves: [`testing.md`](testing.md).

## Where things are

[`code-tour.md`](code-tour.md) walks through every package and module. Before
changing code, read the "Definition of done" in [`README.md`](README.md): docs are
updated in the same commit as the code.

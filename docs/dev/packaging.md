# Packaging: building a DR2 Studio release

A release is a folder (`DR2Studio/`) holding two executables, DR2 Studio and `dr2`,
with Python and every library inside, so a player installs nothing. It ships as the
recomps ship theirs: `DR2Studio-linux-x86_64.AppImage` and `.tar.zst`,
`DR2Studio-windows-x86_64.zip`, `DR2Studio-macos-arm64.zip`, each with a `.sha256`, plus
the Blender add-on `io_dr2-<version>.zip`. Player-side instructions:
[`../modding/01-install.md`](../modding/01-install.md).

## What is in a release

```
DR2Studio/
  DR2Studio(.exe)      the GUI (PyInstaller, windowed)
  dr2(.exe)            the CLI (same code)
  _internal/           Python, dr2kit, PySide6/Qt, numpy, Pillow, PyAV + LGPL ffmpeg,
                       the native LZX library (dr2kit/container/lzx/_native/)
  python/dr2kit/       the toolkit's sources (with the native LZX library), for the
                       Blender add-on's "Toolkit folder" (dev/blender-addon.md)
  blender/io_dr2-*.zip the Blender add-on (GPL)
  docs/                docs/modding/ and the glossary
  README.txt  LICENSE  THIRD_PARTY.md  licenses/ (every bundled licence text,
                       ffmpeg-SOURCE.txt: which ffmpeg, from where, built how)
```

macOS: `DR2 Studio.app` (the GUI, with `dr2` inside `Contents/MacOS/`), next to the
other folders in the zip; signed ad hoc only (no Apple developer account yet), so the
first start needs right-click → Open.

## The icon

`dr2kit/studio/icon/dr2studio.svg` is the only source: our own drawing (a combination
wrench on a blood-red tile with drips; no game logo or artwork), made in phase 7 at the
user's request. Studio loads the SVG for its windows (`studio.app.app_icon`). For
releases, `tools/release/make_icons.py` renders it with Qt's SVG renderer into
`build/icon/`: PNGs from 16 to 1024 px (the AppImage and `.desktop` icon), an `.ico`
(Windows executables) and an `.icns` (the macOS app), written by Pillow;
`build_release.py bundle` runs it before PyInstaller, and the spec passes them on.

## Why an own ffmpeg (the licence gate)

PyAV's wheels on PyPI link `libavcodec` against **x264 and x265, which are GPL**
(`readelf -d libavcodec*.so` lists both; checked on PyAV 19.0.1). A release that
bundled that wheel would ship GPL libraries inside a non-commercial-licensed program.
The CZ recomp met the same problem and builds its own LGPL ffmpeg; so does the
toolkit:

1. `tools/release/build_ffmpeg_lgpl.sh` builds ffmpeg 8.1.2 as shared libraries with
   `--disable-everything --disable-autodetect` and only what dr2kit uses: the `xma1`,
   `xma2`, Bink, PCM, MP3, Vorbis, Opus and FLAC decoders, the WAV, Bink, Ogg, FLAC and
   MP3 demuxers, the `mpeg4` and `aac` encoders, the MP4 and WAV muxers, the few filters
   PyAV's resampler and picture conversion use. It stops if `config.h` says GPL or
   nonfree. 43 s on 16 cores; without `nasm` it builds without x86 assembly (correct
   but slower decoding; CI installs nasm).
2. PyAV is built from source against it:
   `PKG_CONFIG_PATH=build/ffmpeg-lgpl/lib/pkgconfig LDFLAGS=-Wl,-rpath,… pip install
   --no-binary av av==19.0.1`.
3. `tools/build_release.py bundle` refuses to start if the venv's PyAV is the PyPI wheel
   or reports a GPL ffmpeg, and after PyInstaller it **refuses the bundle** if any file
   is named like a GPL library (x264, x265, xvid, postproc, vvenc…) or if the bundled
   `dr2 doctor` doesn't report an LGPL ffmpeg with the XMA and Bink decoders and the
   native LZX library, or if the bundled `dr2 help` can't show the guides (the help), or if the 3D view's page
   or any module it imports (three.js) is missing (`model_view.viewer_files`).

Development installs keep using the PyPI wheel (`pip install av`): nothing is
redistributed there. Qt Multimedia brings its own ffmpeg (LGPL 2.1+, inside PySide6);
it is used only for playback and doesn't link x264.

The gate earned its place on the first run: PyInstaller analyses each library's
dependencies through the system's search path, and ffmpeg's own libraries carry no
RUNPATH, so on Fedora (whose ffmpeg 8 has the same sonames and links x264, x265, xvid
and vvenc) it analysed the system `libavcodec` and collected those four. The builder now
puts the LGPL build's `lib/` first in `LD_LIBRARY_PATH` (`DYLD_LIBRARY_PATH` on macOS,
`PATH` on Windows) while PyInstaller runs.

## Building one (Linux, as tested 2026-10-09)

```
cmake -S native/lzx -B native/lzx/build -DCMAKE_BUILD_TYPE=Release && cmake --build native/lzx/build
tools/release/build_ffmpeg_lgpl.sh                       # -> build/ffmpeg-lgpl
uv venv build/release-venv --python 3.14                 # or python -m venv
PKG_CONFIG_PATH=$PWD/build/ffmpeg-lgpl/lib/pkgconfig LDFLAGS="-Wl,-rpath,$PWD/build/ffmpeg-lgpl/lib" \
  uv pip install --python build/release-venv/bin/python --no-binary av "av==19.0.1"
uv pip install --python build/release-venv/bin/python ".[studio]" pyinstaller pillow
build/release-venv/bin/python tools/build_release.py bundle    # ~1 min, then the gate
build/release-venv/bin/python tools/build_release.py archive   # tar.zst (zip elsewhere)
build/release-venv/bin/python tools/build_release.py appimage  # Linux
```

`appimage` wraps the bundle the way the recomps do: an AppDir (`AppRun`, a `.desktop`
file, the app icon), `mksquashfs -comp zstd`, and the
type-2 AppImage runtime (downloaded once to `build/appimage/`, or `DR2_APPIMAGE_RUNTIME`;
checked for the `AI\x02` magic). `DR2Studio-linux-x86_64.AppImage` starts the GUI;
`… .AppImage dr2 <args>` runs the CLI.

Results (Fedora 44, Python 3.14, PySide6 6.12, PyInstaller 6.22): bundle 700 MB (Qt
WebEngine is most of it), AppImage 263 MB, tar.zst 222 MB. Checked: the licence gate
passes; the bundled and the AppImage's `dr2` extract a sound as WAV, a movie as MP4, a
model as `.glb` and a texture as PNG, show strings, and check a mod; DR2 Studio starts
(offscreen); the LGPL PyAV passes `dr2 census --audio` on both games (every sound and
movie decodes; 9 minutes without nasm, against about 1.5 with the PyPI wheel).

**The help inside the bundle.** PyInstaller runs from the repository, so it collects the
package's data files from the source checkout, where the guides live in `docs/modding/`,
not in `dr2kit/help/en/` as in an installed package (`setup.py` copies them there). The
first test builds (2026-10-10) had no help, and Studio then showed no asset at all (its
"How to mod this" box reads the help, and the error was invisible without a console).
The spec now adds the guides itself, the gate runs the bundled `dr2 help`, and Studio
reports unexpected errors in its log, an error box and `studio-errors.log` in the cache
folder.

**three.js was not in git.** The root `.gitignore` said `build/`, which also matched
`dr2kit/studio/web/vendor/three/build/` (`three.module.js`, `three.core.js`). Linux builds
come from the working folder, which had the files, so they worked; the Windows build comes
from a git clone, and its 3D view stayed at "loading…" (a module that can't be fetched
gives no error). The rule is now `/build/`, the files are committed, a test checks git
tracks every module the page imports, the gate checks the bundle, and the page itself
says when its files are missing. After a `.gitignore` change, check `git status --ignored`
for package files.

**MP4 bitrate.** The movie export asks ffmpeg's `mpeg4` encoder for 8 Mb/s; with x86
assembly (PyPI's PyAV, the Windows build) it lands at ~3 Mb/s for `dr2_logo.bik`, without
it (a Linux build where `nasm` was missing) at ~6.7 Mb/s, from the same frames. Both play;
CI installs `nasm`, so releases match Windows.

## Building one on Windows (as done 2026-10-10, on the build laptop)

The recomps' Windows laptop (`ssh czwin`; their `docs/windows-build-setup.md` is the
runbook: MSVC Build Tools, CMake, Ninja, MSYS2, `C:\cz\vc.bat` wraps `vcvars64`). The
toolkit's tree is `C:\dr2kit\src`, cloned from a `git bundle` (no GitHub remote yet) with
`core.autocrlf=false`: with CRLF line endings, bash can't run the ffmpeg script.

```
vc.bat cmake -S native\lzx -B native\lzx\build -G Ninja -DCMAKE_BUILD_TYPE=Release && vc.bat cmake --build native\lzx\build
:: ffmpeg, from MSYS2's bash inside the MSVC environment (MSYS2_PATH_TYPE=inherit keeps cl.exe):
set MSYS2_PATH_TYPE=inherit & set DR2_FFMPEG_EXTRA=--toolchain=msvc
vc.bat C:\msys64\usr\bin\bash.exe -lc "cd /c/dr2kit/src && tools/release/build_ffmpeg_lgpl.sh /c/dr2kit/ffmpeg-lgpl"
py -3.13 -m venv build\release-venv
:: inside vcvars64; PyAV takes the ffmpeg folder directly (no pkg-config needed):
build\release-venv\Scripts\python -m pip install -U pip setuptools wheel cython
build\release-venv\Scripts\python -m pip install --no-binary av --no-build-isolation "av==19.0.1" -C"--build-option=--ffmpeg-dir=C:/dr2kit/ffmpeg-lgpl"
build\release-venv\Scripts\python -m pip install ".[studio]" pyinstaller pillow
set DR2_FFMPEG_PREFIX=C:\dr2kit\ffmpeg-lgpl
build\release-venv\Scripts\python tools\build_release.py bundle
build\release-venv\Scripts\python tools\build_release.py archive
```

What the first Windows build needed (all now in the scripts):

- **MSVC crashes on ffmpeg's `libavformat/cbs.c`** (`C1001: Internal compiler error`,
  after `C4034: sizeof returns 0`): with no AV1/APV bitstream reader enabled its table is
  empty. `build_ffmpeg_lgpl.sh` adds `--enable-bsf=av1_frame_split` for MSVC builds.
- **Import libraries in `bin\`**: an MSVC ffmpeg installs `avformat.lib`… next to the
  DLLs; the script copies them to `lib\`, where PyAV's `--ffmpeg-dir` looks.
- **Python doesn't search `PATH` for DLLs** (3.8+): `build_release.py` adds the ffmpeg
  `bin\` to the DLL search for its PyAV check, and **copies the LGPL DLLs next to PyAV's
  modules** before PyInstaller runs. Without that, PyInstaller couldn't import PyAV,
  left it out, and the licence gate refused the bundle ("PyAV not installed").

Result (Windows 11, Python 3.13, MSVC 19.44): `DR2Studio-windows-x86_64.zip` 276 MB;
the licence gate passes; the unpacked release's `dr2.exe` exports a model `.glb`, a WAV, a
CW movie as MP4, builds a CZ index with every model picture (411 s), passes `dr2 library
--check`, and exports the Music group and a model folder. The GUI was handed to the user
to try.

**glibc floor.** A Linux bundle runs only on systems whose glibc is at least the build
machine's. A local Fedora 44 build is for testing; releases are built by CI on Ubuntu
22.04 (glibc 2.35), the recomps' "old base" choice.

## CI

`.github/workflows/release.yml` (on a `v*` tag, or by hand): jobs `addon`, `linux`
(Ubuntu 22.04: AppImage + tar.zst), `macos` (macos-14, arm64: zip of the ad-hoc-signed
app), `windows` (ffmpeg built with MSVC from MSYS2: zip); a tag run drafts a GitHub
release with everything. **Not run yet**: the repository has no GitHub remote. The
Windows ffmpeg step is the least certain; expect to adjust it on the first run. The
bundles are only checked with `dr2 doctor` there (no game data on CI): try each build
on a real game before publishing the draft.

## Not done

- Code signing and notarisation (macOS), an installer or code signature (Windows).
- An x86_64 macOS build (add `macos-13` to the workflow if wanted).
- Making the bundle smaller (Qt WebEngine is only needed for the 3D view).

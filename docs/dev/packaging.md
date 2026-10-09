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
   native LZX library.

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
file, our own icon drawn by `make_icon`, no game art), `mksquashfs -comp zstd`, and the
type-2 AppImage runtime (downloaded once to `build/appimage/`, or `DR2_APPIMAGE_RUNTIME`;
checked for the `AI\x02` magic). `DR2Studio-linux-x86_64.AppImage` starts the GUI;
`… .AppImage dr2 <args>` runs the CLI.

Results (Fedora 44, Python 3.14, PySide6 6.12, PyInstaller 6.22): bundle 700 MB (Qt
WebEngine is most of it), AppImage 263 MB, tar.zst 222 MB. Checked: the licence gate
passes; the bundled and the AppImage's `dr2` extract a sound as WAV, a movie as MP4, a
model as `.glb` and a texture as PNG, show strings, and check a mod; DR2 Studio starts
(offscreen); the LGPL PyAV passes `dr2 census --audio` on both games (every sound and
movie decodes; 9 minutes without nasm, against about 1.5 with the PyPI wheel).

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

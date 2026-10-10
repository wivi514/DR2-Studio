#!/usr/bin/env bash
# Build the small LGPL ffmpeg that DR2 Studio releases bundle (docs/dev/packaging.md).
#
# WHY: PyAV's wheels from PyPI link libavcodec against x264 and x265, which are GPL
# (`readelf -d libavcodec*.so` lists both). Shipping that wheel inside a release would
# put GPL code in a bundle under the toolkit's non-commercial licence. The CZ recomp
# met the same problem and builds its own LGPL ffmpeg (its tools/build_ffmpeg_lgpl.sh);
# this script does the same for the toolkit, and tools/build_release.py builds PyAV
# from source against it. Development installs keep using the PyPI wheel: nothing is
# redistributed there.
#
# WHAT IT ENABLES: only what dr2kit asks ffmpeg for (grep `av.` in dr2kit/convert/):
#   decoders  xma1 xma2 (sounds), bink binkaudio_dct binkaudio_rdft (CW movies),
#             pcm_* mp3float vorbis opus flac (a modder's WAV/OGG/FLAC/MP3)
#   demuxers  wav bink ogg flac mp3
#   encoders  mpeg4 aac pcm_s16le (dr2 extract --mp4)        muxers  mp4 mov wav
#   filters   the ones PyAV's AudioResampler and frame conversion build graphs from
#             (buffer sources and sinks are always built)
#   libraries avcodec avformat avfilter avdevice swresample swscale avutil (PyAV links
#             all seven; avdevice gets no devices)
# No --enable-gpl, no --enable-nonfree, no external libraries (--disable-autodetect).
#
# Usage:  tools/release/build_ffmpeg_lgpl.sh [prefix]       (default: build/ffmpeg-lgpl)
# Env:    DR2_FFMPEG_WORK  download/build folder (default: build/ffmpeg-work)
#         DR2_FFMPEG_SRC   an unpacked ffmpeg-$VERSION source tree to use as is
set -euo pipefail

VERSION=8.1.2
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PREFIX=${1:-$ROOT/build/ffmpeg-lgpl}
WORK=${DR2_FFMPEG_WORK:-$ROOT/build/ffmpeg-work}
mkdir -p "$WORK"

SRC=${DR2_FFMPEG_SRC:-$WORK/ffmpeg-$VERSION}
if [ ! -x "$SRC/configure" ]; then
    TARBALL=$WORK/ffmpeg-$VERSION.tar.xz
    if [ ! -f "$TARBALL" ]; then
        echo "==> fetching ffmpeg $VERSION"
        curl -fL --retry 3 -o "$TARBALL.part" "https://ffmpeg.org/releases/ffmpeg-$VERSION.tar.xz"
        mv "$TARBALL.part" "$TARBALL"
    fi
    echo "==> unpacking"
    tar -C "$WORK" -xf "$TARBALL"
    SRC=$WORK/ffmpeg-$VERSION
fi

# x86 SIMD needs nasm; without it the decoders are built from C (correct, slower), and
# the script says so instead of deciding quietly.
ASM=""
if command -v nasm >/dev/null; then
    echo "==> assembler: $(command -v nasm)"
else
    echo "==> no nasm: building without x86 assembly (slower decoding, same output)"
    ASM="--disable-x86asm"
fi

# MSVC (Windows): libavformat/cbs.c, built for the mp4 muxer, holds a table of the AV1
# and APV bitstream readers; with neither enabled it is an empty array, and cl 19.44
# crashes on it ("fatal error C1001: Internal compiler error", after "C4034: sizeof
# returns 0"; gcc and clang compile it). One small AV1 bitstream filter fills the table.
case "${DR2_FFMPEG_EXTRA:-}" in
    *msvc*) MSVC_FIX="--enable-bsf=av1_frame_split" ;;
    *) MSVC_FIX="" ;;
esac

BUILD=$WORK/build
rm -rf "$BUILD" && mkdir -p "$BUILD"
cd "$BUILD"
"$SRC/configure" --prefix="$PREFIX" \
    --enable-shared --disable-static --disable-programs --disable-doc \
    --disable-autodetect --disable-everything --disable-network $ASM \
    --enable-avcodec --enable-avformat --enable-avfilter --enable-avdevice \
    --enable-swresample --enable-swscale \
    --enable-decoder=xma1,xma2,bink,binkaudio_dct,binkaudio_rdft \
    --enable-decoder=pcm_s16le,pcm_s16be,pcm_s24le,pcm_s32le,pcm_f32le,pcm_f64le,pcm_u8 \
    --enable-decoder=mp3float,mp3,vorbis,opus,flac \
    --enable-demuxer=wav,bink,ogg,flac,mp3 \
    --enable-parser=mpegaudio,vorbis,opus,flac \
    --enable-encoder=mpeg4,aac,pcm_s16le \
    --enable-muxer=mp4,mov,wav \
    --enable-filter=aresample,aformat,anull,format,scale,null \
    --enable-protocol=file \
    $MSVC_FIX ${DR2_FFMPEG_EXTRA:-}

grep -q '^#define CONFIG_GPL 0' config.h || { echo "FAIL: this ffmpeg is not LGPL" >&2; exit 1; }
grep -q '^#define CONFIG_NONFREE 0' config.h || { echo "FAIL: nonfree enabled" >&2; exit 1; }
make -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
make install
echo "==> LGPL ffmpeg $VERSION in $PREFIX ($(sed -n 's/^#define FFMPEG_LICENSE "\(.*\)"/\1/p' config.h))"

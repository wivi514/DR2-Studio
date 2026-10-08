#!/usr/bin/env python3
"""Check that the installed PyAV (ffmpeg) can decode the games' audio and video.

Why: dr2kit plans to decode XMA audio (phase 5) and Case West's Bink movies (phase 6)
through PyAV, whose wheels bundle ffmpeg on Windows, Linux and macOS. That only works if
those bundled builds include the decoders. CI runs this on all three OSes
(.github/workflows/ci.yml, job "pyav-codecs"); the result is recorded in
docs/ARCHITECTURE.md, "Platforms".

Exit code 0 when every needed decoder is present, 1 otherwise (it names the missing).

    pip install av && python tools/check_pyav_codecs.py
"""

import platform
import sys

NEEDED = {
    "xma1": "XMA audio, version 1",
    "xma2": "XMA audio, version 2 (what the recomps feed ffmpeg)",
    "binkvideo": "Bink video (Case West movies)",
    "binkaudio_dct": "Bink audio (DCT)",
    "binkaudio_rdft": "Bink audio (RDFT)",
}


def main() -> int:
    try:
        import av
    except ImportError:
        print("PyAV is not installed (pip install av)")
        return 1
    print(f"PyAV {av.__version__}, ffmpeg {getattr(av, 'ffmpeg_version_info', '?')}, "
          f"{platform.system()} {platform.machine()}")
    missing = []
    for name, what in NEEDED.items():
        try:
            av.codec.Codec(name, "r")
            print(f"  ok       {name:16} {what}")
        except Exception as e:  # noqa: BLE001 - report every failure
            print(f"  MISSING  {name:16} {what} ({type(e).__name__})")
            missing.append(name)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())

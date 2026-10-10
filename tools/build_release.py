"""Build a DR2 Studio release: the add-on zip, the app bundle, its archives.

Steps (docs/dev/packaging.md has the why of each):

    python tools/build_release.py addon     build/release/io_dr2-<version>.zip
    python tools/build_release.py bundle    build/release/DR2Studio/ (PyInstaller, staged)
    python tools/build_release.py archive   DR2Studio-<os>-<arch>.zip / .tar.zst (+ .sha256)
    python tools/build_release.py appimage  DR2Studio-linux-x86_64.AppImage (+ .sha256)
    python tools/build_release.py all       all of the above that fit this OS

``bundle`` must run in a venv holding: dr2kit installed **not** editable
(``pip install .[studio]``), PyInstaller, Pillow, and PyAV **built from source against
the LGPL ffmpeg** of ``tools/release/build_ffmpeg_lgpl.sh`` (PyPI's PyAV wheels link
GPL x264/x265; the licence gate below refuses them). The native LZX library must be
built first (``native/lzx/build``).

The licence gate (``check_licences``): no file in the bundle may be a GPL library
(x264, x265, …), and the bundled ``dr2 doctor`` must report an LGPL ffmpeg with the XMA
and Bink decoders. A release that fails it is not written.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "release"
ADDON = ROOT / "blender" / "io_dr2"
NAME = "DR2Studio"
GPL_LIBS = re.compile(r"(x264|x265|xvid|postproc|vidstab|rubberband|frei0r|vvenc)",
                      re.IGNORECASE)
APPIMAGE_RUNTIME_URL = ("https://github.com/AppImage/type2-runtime/releases/download/"
                        "continuous/runtime-x86_64")


def say(msg: str) -> None:
    print(f"==> {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def platform_tag() -> str:
    """``linux-x86_64``, ``windows-x86_64``, ``macos-arm64``: the recomps' naming."""
    osname = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    arch = platform.machine().lower()
    arch = {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}.get(arch, arch)
    return f"{osname}-{arch}"


def sha256_file(path: Path) -> Path:
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    out = path.with_name(path.name + ".sha256")
    out.write_text(f"{h}  {path.name}\n")
    say(f"{path.name}: {path.stat().st_size / 1e6:.1f} MB, sha256 {h[:16]}…")
    return out


# ---- the Blender add-on ---------------------------------------------------------------

def addon_version() -> str:
    m = re.search(r'^version = "([^"]+)"', (ADDON / "blender_manifest.toml").read_text(),
                  re.MULTILINE)
    return m.group(1)


def build_addon() -> Path:
    """The add-on zip, laid out as Blender's ``extension build`` makes it (files at the
    top, no folder), with fixed timestamps so the same sources give the same bytes."""
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / f"io_dr2-{addon_version()}.zip"
    files = sorted(p for p in ADDON.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            info = zipfile.ZipInfo(p.relative_to(ADDON).as_posix(), (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, p.read_bytes())
    say(f"add-on: {dest} ({len(files)} files)")
    return dest


# ---- the bundle -----------------------------------------------------------------------

def native_library() -> Path:
    names = {"win32": "dr2lzx.dll", "darwin": "libdr2lzx.dylib"}.get(sys.platform, "libdr2lzx.so")
    for sub in ("", "Release"):
        p = ROOT / "native" / "lzx" / "build" / sub / names
        if p.is_file():
            return p
    fail(f"no {names} in native/lzx/build: build it first (docs/dev/setup.md)")


def ffmpeg_prefix() -> Path:
    """Where the LGPL ffmpeg is (tools/release/build_ffmpeg_lgpl.sh): $DR2_FFMPEG_PREFIX
    or build/ffmpeg-lgpl."""
    return Path(os.environ.get("DR2_FFMPEG_PREFIX", ROOT / "build" / "ffmpeg-lgpl"))


def check_environment() -> None:
    import dr2kit
    here = Path(dr2kit.__file__).resolve()
    if here.parent == ROOT / "dr2kit":
        fail(f"dr2kit is imported from the checkout ({here}); install it into the release "
             f"venv with `pip install .[studio]` (not -e), so the bundle doesn't depend on "
             f"this folder")
    if sys.platform == "win32":
        # Python on Windows doesn't look for an extension's DLLs on PATH (3.8+): point
        # it at the LGPL ffmpeg PyAV was built against (the bundle carries them itself)
        dlls = ffmpeg_prefix() / "bin"
        if dlls.is_dir():
            os.add_dll_directory(str(dlls))
    try:
        import av._core as core
    except ImportError as e:
        fail(f"PyAV can't be imported in this venv ({e}); install it from source against "
             f"the LGPL ffmpeg (docs/dev/packaging.md)")
    lic = core.library_meta["libavcodec"].get("license", "")
    if "GPL" in lic and "LGPL" not in lic:
        fail(f"this PyAV's ffmpeg is {lic}")
    import av
    if sys.platform == "win32":
        # PyInstaller analyses PyAV by importing it in a fresh process, where the DLL
        # directory above doesn't apply; without this it leaves PyAV out (the bundled
        # `dr2 doctor` then says "PyAV not installed", seen 2026-10-10). A DLL next to
        # the .pyd is always found, and PyInstaller collects it with the package, as a
        # delvewheel-repaired wheel would. Only the LGPL build's DLLs are copied.
        pkg = Path(av.__file__).parent
        for dll in (ffmpeg_prefix() / "bin").glob("*.dll"):
            if not (pkg / dll.name).is_file() or \
                    (pkg / dll.name).stat().st_size != dll.stat().st_size:
                shutil.copy2(dll, pkg / dll.name)
        say(f"ffmpeg DLLs next to PyAV: {', '.join(sorted(p.name for p in pkg.glob('*.dll')))}")
    libs = Path(av.__file__).parent.parent / "av.libs"
    bad = [p.name for p in libs.glob("*")] if libs.is_dir() else []
    bad = [n for n in bad if GPL_LIBS.search(n)]
    if bad:
        fail(f"this PyAV is the PyPI wheel, which links GPL libraries ({', '.join(bad)}). "
             f"Build ffmpeg with tools/release/build_ffmpeg_lgpl.sh and PyAV from source "
             f"(docs/dev/packaging.md)")


def build_bundle() -> Path:
    check_environment()
    native = OUT / "native"
    shutil.rmtree(native, ignore_errors=True)
    native.mkdir(parents=True)
    shutil.copy2(native_library(), native)
    say("icons")
    icons().get("png")
    say("PyInstaller (a few minutes)")
    # PyInstaller follows each library's dependencies through the system's search
    # path. ffmpeg's own libraries (libavformat → libavcodec…) carry no RUNPATH, so
    # without this a system ffmpeg of the same version (Fedora's, which links x264)
    # is what gets analysed, and its GPL dependencies are collected (seen 2026-10-09).
    ffmpeg_lib = ffmpeg_prefix() / ("bin" if sys.platform == "win32" else "lib")
    var = {"win32": "PATH", "darwin": "DYLD_LIBRARY_PATH"}.get(sys.platform, "LD_LIBRARY_PATH")
    env = {**os.environ, var: os.pathsep.join(filter(None, [str(ffmpeg_lib),
                                                             os.environ.get(var, "")]))}
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(OUT), "--workpath", str(OUT / "pyi-work"),
                    str(ROOT / "packaging" / "dr2studio.spec")], check=True, env=env)
    bundle = OUT / NAME
    stage(bundle)
    check_licences(bundle)
    return bundle


def stage(bundle: Path) -> None:
    """Put next to the executables what a player and a modder need besides them."""
    say("staging docs, licences, the add-on and the toolkit sources")
    shutil.copy2(ROOT / "packaging" / "README.txt", bundle / "README.txt")
    shutil.copy2(ROOT / "LICENSE", bundle / "LICENSE")
    shutil.copy2(ROOT / "THIRD_PARTY.md", bundle / "THIRD_PARTY.md")
    blender = bundle / "blender"
    blender.mkdir(exist_ok=True)
    shutil.copy2(build_addon(), blender)
    py = bundle / "python"
    shutil.rmtree(py, ignore_errors=True)
    shutil.copytree(ROOT / "dr2kit", py / "dr2kit",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    native = py / "dr2kit" / "container" / "lzx" / "_native"   # for Blender's Python
    native.mkdir(parents=True, exist_ok=True)
    shutil.copy2(native_library(), native)
    docs = bundle / "docs"
    shutil.rmtree(docs, ignore_errors=True)
    shutil.copytree(ROOT / "docs" / "modding", docs / "modding")
    shutil.copy2(ROOT / "docs" / "glossary.md", docs / "glossary.md")
    collect_licences(bundle / "licenses")


def collect_licences(dest: Path) -> None:
    """The licence texts of what the bundle carries (THIRD_PARTY.md lists them)."""
    from importlib import metadata
    dest.mkdir(parents=True, exist_ok=True)
    for dist in ("av", "numpy", "pillow", "PySide6", "PySide6-Essentials", "PySide6-Addons",
                 "shiboken6", "platformdirs", "pyinstaller"):
        try:
            d = metadata.distribution(dist)
        except metadata.PackageNotFoundError:
            continue
        for f in d.files or []:
            name = f.name.lower()
            if any(k in name for k in ("license", "copying", "notice")) and \
                    not name.endswith((".py", ".pyc")):
                src = Path(d.locate_file(f))
                if src.is_file():
                    shutil.copy2(src, dest / f"{d.metadata['Name']}-{f.name}")
    shutil.copy2(ROOT / "native" / "lzx" / "libmspack" / "COPYING.LIB",
                 dest / "libmspack-COPYING.LIB")
    shutil.copy2(ROOT / "dr2kit" / "studio" / "web" / "vendor" / "three" / "LICENSE",
                 dest / "three.js-LICENSE")
    work = Path(os.environ.get("DR2_FFMPEG_WORK", ROOT / "build" / "ffmpeg-work"))
    src = next(work.glob("ffmpeg-*/COPYING.LGPLv2.1"), None)
    if src:
        shutil.copy2(src, dest / "ffmpeg-COPYING.LGPLv2.1")
    script = ROOT / "tools" / "release" / "build_ffmpeg_lgpl.sh"
    version = re.search(r"^VERSION=(\S+)", script.read_text(), re.MULTILINE).group(1)
    (dest / "ffmpeg-SOURCE.txt").write_text(
        f"The ffmpeg libraries in this bundle are ffmpeg {version}, LGPL-2.1-or-later,\n"
        f"built unmodified from https://ffmpeg.org/releases/ffmpeg-{version}.tar.xz with\n"
        f"tools/release/build_ffmpeg_lgpl.sh of the toolkit (the configure line is in\n"
        f"that script). They are separate shared libraries: you may replace them with\n"
        f"your own build of the same version.\n")
    lic = Path(sys.base_prefix) / "LICENSE.txt"
    for cand in (lic, Path(sys.base_prefix) / "lib" / f"python{sys.version_info[0]}."
                 f"{sys.version_info[1]}" / "LICENSE.txt"):
        if cand.is_file():
            shutil.copy2(cand, dest / "Python-LICENSE.txt")
            break


def check_licences(bundle: Path) -> None:
    """Refuse a bundle that carries a GPL library or an ffmpeg without our decoders."""
    bad = [str(p.relative_to(bundle)) for p in bundle.rglob("*")
           if p.is_file() and GPL_LIBS.search(p.name)]
    if bad:
        fail(f"GPL libraries in the bundle: {bad[:5]}")
    exe = bundle / ("dr2.exe" if sys.platform == "win32" else "dr2")
    out = subprocess.run([str(exe), "doctor"], capture_output=True, text=True,
                         env={**os.environ, "DR2KIT_LZX_LIBRARY": ""}).stdout
    print(out)
    av_line = next((ln for ln in out.splitlines() if ln.startswith("audio/movies:")), "")
    if "LGPL" not in av_line or "MISSING" in av_line:
        fail(f"the bundled dr2 doctor says: {av_line or out}")
    if "LZX decoder: native" not in out:
        fail("the bundled dr2 doesn't load its native LZX library")
    # The help is the guides (dr2kit/help/en): Studio reads it for every asset it shows
    helped = subprocess.run([str(exe), "help"], capture_output=True, text=True)
    if helped.returncode != 0 or "Install DR2 Studio" not in helped.stdout:
        fail(f"the bundled dr2 has no help: {(helped.stderr or helped.stdout)[-300:]}")
    say("licence gate passed: no GPL library, LGPL ffmpeg with XMA and Bink, native LZX; "
        "the help is inside")


# ---- archives -------------------------------------------------------------------------

def build_archive() -> Path:
    bundle = OUT / NAME
    if not bundle.is_dir():
        fail("no bundle: run `build_release.py bundle` first")
    tag = platform_tag()
    if sys.platform == "linux":
        dest = OUT / f"{NAME}-{tag}.tar.zst"
        tar = OUT / f"{NAME}-{tag}.tar"
        with tarfile.open(tar, "w") as t:
            t.add(bundle, arcname=NAME)
        subprocess.run(["zstd", "-19", "-T0", "-f", "-q", str(tar), "-o", str(dest)], check=True)
        tar.unlink()
    else:
        dest = OUT / f"{NAME}-{tag}.zip"
        src = OUT / "DR2 Studio.app" if sys.platform == "darwin" else bundle
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(src.rglob("*")):
                if p.is_file():
                    z.write(p, (Path(src.name) / p.relative_to(src)).as_posix())
            if sys.platform == "darwin":       # the CLI, docs and add-on beside the app
                for p in sorted(bundle.rglob("*")):
                    rel = p.relative_to(bundle)
                    if p.is_file() and rel.parts[0] in ("python", "blender", "docs",
                                                        "licenses") or \
                            rel.as_posix() in ("README.txt", "LICENSE", "THIRD_PARTY.md"):
                        z.write(p, (Path(NAME) / rel).as_posix())
    sha256_file(dest)
    return dest


# ---- AppImage (Linux) -----------------------------------------------------------------

APPRUN = """#!/bin/sh
# DR2 Studio AppImage. `DR2Studio-linux-x86_64.AppImage` starts the GUI;
# `DR2Studio-linux-x86_64.AppImage dr2 <args>` runs the command line.
HERE="$(dirname "$(readlink -f "$0")")"
if [ "$1" = "dr2" ]; then
    shift
    exec "$HERE/usr/dr2" "$@"
fi
exec "$HERE/usr/DR2Studio" "$@"
"""

DESKTOP = """[Desktop Entry]
Type=Application
Name=DR2 Studio
Comment=Modding toolkit for Dead Rising 2: Case Zero and Case West
Exec=DR2Studio
Icon=dr2studio
Categories=Development;Graphics;
Terminal=false
"""


def runtime_file() -> Path:
    path = Path(os.environ.get("DR2_APPIMAGE_RUNTIME", ROOT / "build" / "appimage" /
                               "runtime-x86_64"))
    if not path.is_file():
        say("fetching the AppImage runtime")
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["curl", "-fL", "--retry", "3", "-o", str(path), APPIMAGE_RUNTIME_URL],
                       check=True)
    data = path.read_bytes()
    if data[8:11] != b"AI\x02":
        fail(f"{path} is not a type-2 AppImage runtime (no AI\\x02 at offset 8)")
    say(f"runtime {path.name}, sha256 {hashlib.sha256(data).hexdigest()[:16]}…")
    return path


def build_appimage() -> Path:
    if sys.platform != "linux":
        fail("AppImages are built on Linux")
    bundle = OUT / NAME
    appdir = OUT / f"{NAME}.AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    shutil.copytree(bundle, appdir / "usr", symlinks=True)
    (appdir / "AppRun").write_text(APPRUN)
    (appdir / "AppRun").chmod(0o755)
    (appdir / "dr2studio.desktop").write_text(DESKTOP)
    icon = appdir / "dr2studio.png"
    icon.write_bytes(icons()["png"].read_bytes())
    (appdir / ".DirIcon").write_bytes(icon.read_bytes())
    squash = OUT / f"{NAME}.squashfs"
    squash.unlink(missing_ok=True)
    subprocess.run(["mksquashfs", str(appdir), str(squash), "-root-owned", "-noappend",
                    "-comp", "zstd", "-quiet"], check=True)
    dest = OUT / f"{NAME}-{platform_tag()}.AppImage"
    with open(dest, "wb") as f:
        f.write(runtime_file().read_bytes())
        f.write(squash.read_bytes())
    dest.chmod(0o755)
    squash.unlink()
    sha256_file(dest)
    return dest


def icons() -> dict:
    """The app icon as PNG / ICO / ICNS in build/icon (tools/release/make_icons.py,
    from dr2kit/studio/icon/dr2studio.svg: our own drawing, no game art)."""
    sys.path.insert(0, str(ROOT / "tools" / "release"))
    import make_icons
    return make_icons.make(ROOT / "build" / "icon")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("step", choices=["addon", "bundle", "archive", "appimage", "all"])
    a = ap.parse_args(argv)
    if a.step in ("addon",):
        build_addon()
    if a.step in ("bundle", "all"):
        build_bundle()
    if a.step in ("archive", "all"):
        build_archive()
    if a.step == "appimage" or (a.step == "all" and sys.platform == "linux"):
        build_appimage()
    return 0


if __name__ == "__main__":
    sys.exit(main())

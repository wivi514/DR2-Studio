# PyInstaller spec for a DR2 Studio release: two executables in one folder.
#
#   DR2Studio[.exe]   the GUI (windowed: no console on Windows)
#   dr2[.exe]         the command line, same code (`dr2 doctor`, `dr2 mod deploy`, ...)
#
# Built by tools/build_release.py (docs/dev/packaging.md), which first puts the native
# LZX library where dr2kit looks for a prebuilt one (dr2kit/container/lzx/_native/) and
# checks afterwards that no GPL library slipped in. Run it from a venv that has dr2kit
# installed (not editable), PySide6, numpy, Pillow and the LGPL PyAV build.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

HERE = Path(SPECPATH)
LZX = [(str(p), "dr2kit/container/lzx/_native")
       for p in (HERE.parent / "build" / "release" / "native").glob("*dr2lzx*")]
datas = collect_data_files("dr2kit", excludes=["**/__pycache__/*"])
hidden = collect_submodules("dr2kit", filter=lambda m: ".tests" not in m)
excludes = ["tkinter", "pytest", "PyInstaller"]


def analysis(script):
    return Analysis([str(HERE / script)], pathex=[], binaries=LZX, datas=datas,
                    hiddenimports=hidden, excludes=excludes, noarchive=False)


studio = analysis("entry_studio.py")
cli = analysis("entry_cli.py")
studio_exe = EXE(PYZ(studio.pure), studio.scripts, [], exclude_binaries=True,
                 name="DR2Studio", console=False, upx=False)
cli_exe = EXE(PYZ(cli.pure), cli.scripts, [], exclude_binaries=True,
              name="dr2", console=True, upx=False)
coll = COLLECT(studio_exe, studio.binaries, studio.datas,
               cli_exe, cli.binaries, cli.datas,
               name="DR2Studio", upx=False)
if sys.platform == "darwin":
    app = BUNDLE(coll, name="DR2 Studio.app", bundle_identifier="org.dr2kit.studio",
                 info_plist={"NSHighResolutionCapable": True})

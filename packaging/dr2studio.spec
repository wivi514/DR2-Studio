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
# The in-app help: the modding guides, as setup.py copies them into an installed package
# (dr2kit/help/<lang>/). collect_data_files reads the package PyInstaller imports, which
# is the source checkout (it runs from the repository), where the guides live in
# docs/modding/ instead: without this, releases had no help, and Studio couldn't show
# an asset (its "How to mod this" box reads the help; found on 2026-10-10).
MODDING = HERE.parent / "docs" / "modding"
datas = [d for d in datas if not d[1].startswith("dr2kit/help/")]
for lang, src in [("en", MODDING)] + [(d.name, d) for d in MODDING.iterdir()
                                       if d.is_dir() and len(d.name) == 2]:
    datas += [(str(f), f"dr2kit/help/{lang}") for f in sorted(src.glob("*"))
              if f.suffix in (".md", ".toml")]
    gloss = src / "glossary.md"
    datas.append((str(gloss if gloss.is_file() else HERE.parent / "docs" / "glossary.md"),
                  f"dr2kit/help/{lang}"))
hidden = collect_submodules("dr2kit", filter=lambda m: ".tests" not in m)
excludes = ["tkinter", "pytest", "PyInstaller"]


def analysis(script):
    return Analysis([str(HERE / script)], pathex=[], binaries=LZX, datas=datas,
                    hiddenimports=hidden, excludes=excludes, noarchive=False)


studio = analysis("entry_studio.py")
cli = analysis("entry_cli.py")
ICONS = HERE.parent / "build" / "icon"          # tools/release/make_icons.py
ICON = str(ICONS / ("dr2studio.ico" if sys.platform == "win32" else "dr2studio.icns"))
studio_exe = EXE(PYZ(studio.pure), studio.scripts, [], exclude_binaries=True,
                 name="DR2Studio", console=False, upx=False, icon=ICON)
cli_exe = EXE(PYZ(cli.pure), cli.scripts, [], exclude_binaries=True,
              name="dr2", console=True, upx=False, icon=ICON)
coll = COLLECT(studio_exe, studio.binaries, studio.datas,
               cli_exe, cli.binaries, cli.datas,
               name="DR2Studio", upx=False)
if sys.platform == "darwin":
    app = BUNDLE(coll, name="DR2 Studio.app", bundle_identifier="org.dr2kit.studio",
                 icon=str(ICONS / "dr2studio.icns"),
                 info_plist={"NSHighResolutionCapable": True})

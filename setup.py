"""Build hook: put the modding guides inside the package as the in-app help.

The guides are written once, in ``docs/modding/`` (plus ``docs/glossary.md``); the
help in DR2 Studio and ``dr2 help`` reads them (`dr2kit.help`). A source checkout reads
them where they are; a built package (a pip install, a release) gets a copy in
``dr2kit/help/<lang>/``, made here. One folder per language: English is
``docs/modding/``, a translation would be ``docs/modding/<lang>/``.
Everything else about the package is in pyproject.toml.
"""

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).resolve().parent
MODDING = ROOT / "docs" / "modding"


class BuildWithHelp(build_py):
    def run(self):
        super().run()
        out = Path(self.build_lib) / "dr2kit" / "help"
        langs = {"en": MODDING}
        langs.update({d.name: d for d in MODDING.iterdir()
                      if d.is_dir() and len(d.name) == 2})
        for lang, src in langs.items():
            dest = out / lang
            dest.mkdir(parents=True, exist_ok=True)
            for f in src.glob("*"):
                if f.suffix in (".md", ".toml"):
                    shutil.copy2(f, dest / f.name)
            glossary = (src / "glossary.md") if (src / "glossary.md").is_file() else \
                ROOT / "docs" / "glossary.md"
            shutil.copy2(glossary, dest / "glossary.md")


setup(cmdclass={"build_py": BuildWithHelp})

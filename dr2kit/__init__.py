"""dr2kit: the core library of the DR2 Case Zero / Case West modding toolkit.

Every front end (the `dr2` command line, DR2 Studio, the Blender add-on) calls this one
library, so all knowledge about the game's file formats lives here and nowhere else.
Start with `docs/dev/code-tour.md` for a map of the packages.

Sub-packages:
    dr2kit.container  the `.big` archive, LZX compression, virtual paths, STFS packages
    dr2kit.profiles   per-game settings (`cz`, `cw`) and finding the game data
    dr2kit.formats    the game's own formats: textures, scenes, vertices, sounds, scripts
    dr2kit.convert    to and from everyday formats: PNG, glTF, WAV
    dr2kit.index      the SQLite asset index (search, relations)
    dr2kit.mods       mod folders: build, deploy (sound mods: dr2kit.mods.audio)
    dr2kit.studio     DR2 Studio, the GUI
    dr2kit.census     reading every archive of a game and reporting what it found
    dr2kit.cli        the `dr2` command
"""

__version__ = "0.1.0.dev0"

DR2 Studio and the dr2 command — DR2 CZ/CW Modding Toolkit
==========================================================

A modding toolkit for Dead Rising 2: Case Zero and Dead Rising 2: Case West (the Xbox
360 games, as run by the Case Zero / Case West recomps, Xenia or a console).

You need your own copy of the games. This download holds no game data.

What is in this folder
----------------------
  DR2Studio (DR2Studio.exe)   the graphical tool: browse, view, play, extract, make mods
  dr2 (dr2.exe)               the same toolkit on the command line (dr2 --help)
  blender/io_dr2-*.zip        the Blender add-on (install it from Blender's Preferences)
  python/dr2kit/              the toolkit's source code, for the Blender add-on
                              (point the add-on's "Toolkit folder" at the python folder)
  docs/                       the modding guides (start with docs/modding/01-install.md)
  LICENSE                     the toolkit's licence: free, non-commercial; mods must be free
  THIRD_PARTY.md              the libraries inside, and their licences
  licenses/                   their licence texts

First start
-----------
1. Start DR2Studio. The "Game folders" window opens: choose each game's folder (a
   folder that contains data/, such as a recomp's assets/game), or "Unpack package…"
   to unpack the game's Xbox 360 package file.
2. Click "Build / refresh index" once per game (about a minute).
3. Browse, search, and make mods: docs/modding/README.md lists the guides.

Command line: open a terminal in this folder and run `dr2 doctor`, then `dr2 --help`.

Licence
-------
Free to use, copy, change and share. Nobody may sell the toolkit, and nobody may sell
or paywall mods made for these games (see LICENSE). The Blender add-on is GPL-3.0 (see
the LICENSE file inside its zip). The bundled libraries keep their own licences
(THIRD_PARTY.md); none is GPL.

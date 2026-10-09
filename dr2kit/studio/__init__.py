"""DR2 Studio: the graphical browser (PySide6). Start it with ``dr2 studio``.

v0 (phase 2): browse both games as a tree, search the index, look at textures (zoom,
channels, mip levels, cube faces), see which models use a texture, extract assets (raw
or PNG), and build a mod: "Replace with PNG…" drops the file into the open mod folder,
"Build && deploy" puts it in the recomp's ``game_mods/``. Structure: docs/dev/studio.md.

Later phases added the 3D view (3), the audio view (5), and text editing, string
tables, movies and the mod manager (6).

Modules:
    app          the main window, the tree/search/viewer/details panes, background jobs
    viewers      the texture viewer and the plain-asset viewer
    model_view   the 3D view (QtWebEngine + three.js)
    audio_view   waveform and playback
    text_view    text editor with diff, string-bank table
    video_view   Bink movie player
    mod_manager  the mod library window
"""

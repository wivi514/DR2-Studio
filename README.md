# DR2 CZ/CW Modding Toolkit

Browse, preview, extract and replace assets in **Dead Rising 2: Case Zero** and
**Dead Rising 2: Case West** (Xbox 360), built for the two Xenon recomps.

- See every texture as a thumbnail, and which models use it.
- Listen to any sound before extracting it.
- Export models **and skeletons** to Blender (glTF), and put rigged models back in.
- Package changes as small mods that build against your own copy of the game.

Runs on **Windows, Linux and macOS**.

**Status:** phases 1-6 done (phase 6: strings, text, movies, mod manager, Blender
add-on, release packaging, built on Linux so far). Phase 7 (mostly done): the guides
inside the app (F1), a Welcome checklist, **▶ Play** (deploy + start the recomp), mods
shared as one `.dr2mod` file, editing in your own image editor or Blender with automatic
re-import, and textures from Substance Painter and other programs imported in one step. Every file of both games can be read, searched and
extracted; every texture can be viewed and exported as PNG, and replaced by a mod that
loads in both recomps (tested in game). Every model and skeleton can be viewed in 3D and
exported to Blender (`.glb`) with its bones, skin weights and textures, and an edited or
brand-new mesh rigged to the game's skeleton goes back into the game as a mod (checked
in game: fingers and face follow). Every sound can be played and saved as WAV, and a
mod can replace music, voices or effects with your own audio, played by the recomps
(checked in game in both). DR2 Studio, the window-based app, does all of that without
typing commands. Phase 6 added in-game text and translations (string banks), editing
the game's text files with a diff, Case West's movies (play, export MP4), a mod manager
(several mods, load order, conflicts), a Blender add-on, and release builds
([roadmap](docs/roadmap.md)).

```
dr2 studio                                  # the app: browse, search, view, make mods
dr2 index build                             # the searchable catalogue (once, ~1 min/game)
dr2 index search young shirt --kind texture # find assets
dr2 extract --png data/models/npcs.big/chest_young_chuck.tex/young_cr_shirt_cm -o out
dr2 extract --glb data/models/npcs.big/boss_mechanic.big -o out   # model -> Blender
dr2 model check edited.glb data/models/npcs.big/chest_young_chuck.big   # Blender -> game?
dr2 extract --wav data/audio/music.big/HB_Indemnify.xma -o out    # sound -> WAV (needs PyAV)
dr2 mod new my_mod                          # then put PNGs / .glbs / audio under my_mod/replace/<vpath>.png|.glb|.wav
dr2 mod deploy my_mod -g cz                 # build it into the recomp's game_mods/
dr2 strings set my_mod IDS_PRESS_START "PRESS START TO SURVIVE"   # change in-game text
dr2 mod install my_mod && dr2 mod deploy -g cz   # the mod manager: every switched-on mod
dr2 play -g cz                              # deploy the switched-on mods and start the recomp
dr2 mod import-textures my_mod <model vpath> painter_export/   # Substance Painter -> mod
dr2 help 14                                 # the guides, here or in DR2 Studio (F1)
```

Start at [`docs/README.md`](docs/README.md): modding guides (begin with
[installing](docs/modding/01-install.md) and
[getting your game data in](docs/modding/02-game-data.md)), developer guides, glossary,
and what's planned. Contributors: [`CONTRIBUTING.md`](CONTRIBUTING.md). Third-party code
and its licenses: [`THIRD_PARTY.md`](THIRD_PARTY.md).

You need your own legally obtained copy of the games. This repository contains no game data.

## License

Free to use, change and share; **not for sale**, and mods made for these games
must stay free: no selling them and no paywalls (Patreon, memberships, paid early access).
Voluntary donations are fine. See `LICENSE`.

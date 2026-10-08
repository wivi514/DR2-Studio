# DR2 CZ/CW Modding Toolkit

Browse, preview, extract and replace assets in **Dead Rising 2: Case Zero** and
**Dead Rising 2: Case West** (Xbox 360), built for the two Xenon recomps.

- See every texture as a thumbnail, and which models use it.
- Listen to any sound before extracting it.
- Export models **and skeletons** to Blender (glTF), and put rigged models back in.
- Package changes as small mods that build against your own copy of the game.

Runs on **Windows, Linux and macOS**.

**Status:** phase 2 of 6 done. Every file of both games can be read, searched and
extracted; every texture can be viewed and exported as PNG, and replaced by a mod that
loads in both recomps (tested in game). DR2 Studio, the window-based app, does all of
that without typing commands. Models and skeletons for Blender come next
([roadmap](docs/roadmap.md)).

```
dr2 studio                                  # the app: browse, search, view, make mods
dr2 index build                             # the searchable catalogue (once, ~1 min/game)
dr2 index search young shirt --kind texture # find assets
dr2 extract --png data/models/npcs.big/chest_young_chuck.tex/young_cr_shirt_cm -o out
dr2 mod new my_mod                          # then put PNGs under my_mod/replace/<vpath>.png
dr2 mod deploy my_mod -g cz                 # build it into the recomp's game_mods/
```

Start at [`docs/README.md`](docs/README.md): modding guides (begin with
[getting your game data in](docs/modding/02-game-data.md)), developer guides, glossary,
and what's planned. Contributors: [`CONTRIBUTING.md`](CONTRIBUTING.md). Third-party code
and its licenses: [`THIRD_PARTY.md`](THIRD_PARTY.md).

You need your own legally obtained copy of the games. This repository contains no game data.

## License

Free to use, change and share; **not for sale**, and mods made for these games
must stay free: no selling them and no paywalls (Patreon, memberships, paid early access).
Voluntary donations are fine. See `LICENSE`.

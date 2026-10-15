# DR2 Studio

Browse, preview, extract and replace assets in **Dead Rising 2: Case Zero** and
**Dead Rising 2: Case West** (Xbox 360), built for the two Xenon recomps.

**Development handoff — October 15, 2026:** the original developer has stopped active
development. Contributors are welcome to pick up the remaining work. Start with the
[handoff checklist](https://github.com/wivi514/DR2-Studio/issues/1), which links 30
issues covering known bugs, unfinished features and planned phases. Each issue includes
findings, source references, suggested next steps and completion criteria.

- Find things by what they are (characters, zombies, music, rigs…) with pictures, and
  export a model with all its textures and its rig, or a whole group, in one go.
- See every texture as a thumbnail, and which models use it.
- Listen to any sound before extracting it.
- Export models **and skeletons** to Blender (glTF), and put rigged models back in.
- Package changes as small mods that build against your own copy of the game.

Targets **Windows, Linux and macOS**. Release packaging has been built and tried on
Linux; [Windows/macOS package validation remains open](https://github.com/wivi514/DR2-Studio/issues/24).

Implemented features include the asset Library, texture and model previews, Blender
export/import, audio replacement, text editing, the mod manager, `.dr2mod` sharing,
in-app guides and **▶ Play**. Later phases added variants, the Maps viewer/editor,
weapon and effect tools, animation playback/export, and imports between Case Zero and
Case West. Some gameplay and usability checks remain unfinished; see the
[handoff checklist](https://github.com/wivi514/DR2-Studio/issues/1) for current status.

**Custom maps remain experimental.** Importing Still Creek (Case Zero's `prologue`)
into Case West's `w_mall` has unresolved loading hangs, heap crashes and invisible
collision walls. The latest attempts did not establish a working fix. Loading a title
screen or passing a headless check does not establish that an imported map is playable.

- [Infinite loading](https://github.com/wivi514/DR2-Studio/issues/2) and
  [invisible collision walls](https://github.com/wivi514/DR2-Studio/issues/3).
- Heap failures in [Case West](https://github.com/wivi514/DR2-Studio/issues/4) and
  [Case Zero](https://github.com/wivi514/DR2-Studio/issues/5).
- Increasing Case West's [level capacity](https://github.com/wivi514/DR2-Studio/issues/6)
  and [zombie type capacity](https://github.com/wivi514/DR2-Studio/issues/7).
- [Investigation handoff and preserved runtime experiment](https://github.com/wivi514/DR2-Studio/issues/9).

Remaining plans include completing [new building](https://github.com/wivi514/DR2-Studio/issues/15)
and [new map](https://github.com/wivi514/DR2-Studio/issues/16) tools from phase 14,
finishing [cross-game map integration](https://github.com/wivi514/DR2-Studio/issues/10)
and [boss imports](https://github.com/wivi514/DR2-Studio/issues/12) in phase 15, and
adding PC Dead Rising 2 / Off the Record as sources in phase 16:
[format readers](https://github.com/wivi514/DR2-Studio/issues/28),
[game profiles](https://github.com/wivi514/DR2-Studio/issues/29) and
[imports](https://github.com/wivi514/DR2-Studio/issues/30). Phase 16 has not started.
The [roadmap](docs/roadmap.md) and phase kickoff documents hold the research history;
the GitHub handoff issues record the latest known status.

```
dr2 studio                                  # the app: browse, search, view, make mods
dr2 index build                             # the searchable catalogue (once, ~3-4 min/game)
dr2 library                                 # the games by what things are: characters, music, rigs…
dr2 export characters -g cz -o exports      # every character: .glb, textures, rig, info, one folder each
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

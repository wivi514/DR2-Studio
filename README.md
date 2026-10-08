# DR2 CZ/CW Modding Toolkit

Browse, preview, extract and replace assets in **Dead Rising 2: Case Zero** and
**Dead Rising 2: Case West** (Xbox 360), built for the two Xenon recomps.

- See every texture as a thumbnail, and which models use it.
- Listen to any sound before extracting it.
- Export models **and skeletons** to Blender (glTF), and put rigged models back in.
- Package changes as small mods that build against your own copy of the game.

Runs on **Windows, Linux and macOS**.

**Status:** phase 1 of 6 done. The `dr2` command can read, list, search and extract
every file of both games (archives, nested archives, compressed entries), and write
archives back byte for byte. Textures, the DR2 Studio app and the first mods come next
([roadmap](docs/roadmap.md)).

```
dr2 games                                   # where are my games?
dr2 ls data/models/npcs.big                 # look inside an archive
dr2 find mech_apron                         # search every archive
dr2 extract data/datafile.big -r -o out     # copy files out (decompressed)
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

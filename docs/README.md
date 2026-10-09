# Documentation

Pick the section for what you want to do.

| I want to… | Read |
|---|---|
| **Make a mod** (change textures, models, sounds, text) | [`modding/`](modding/README.md): step-by-step guides, no programming needed |
| **Understand or change the toolkit's code** | [`dev/`](dev/README.md): code tour, how to add a format, standards |
| **Know how the toolkit is designed** | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| **Know how a game file format works** | [`formats.md`](formats.md) |
| **See what is planned and what is done** | [`roadmap.md`](roadmap.md) |
| **Start the next phase of work** | [`phase5-kickoff.md`](phase5-kickoff.md) (earlier handoffs, for history: [`phase4-kickoff.md`](phase4-kickoff.md), [`phase3-kickoff.md`](phase3-kickoff.md), [`phase2-kickoff.md`](phase2-kickoff.md), [`phase1-kickoff.md`](phase1-kickoff.md)) |
| **See what was done, when, and why** | [`devlog.md`](devlog.md) |
| **Look up a word** (`.big`, LZX, tiling, bone palette, vpath…) | [`glossary.md`](glossary.md) |
| **Know what tools existed before this one** | [`prior-art.md`](prior-art.md) |

Phases 1-3 are done: the `dr2` command and DR2 Studio read every file of both games,
show every texture, build texture mods that load in both recomps, show every model and
skeleton in 3D, and export them to Blender (`.glb`). Start with
[`modding/02-game-data.md`](modding/02-game-data.md), then
[your first mod](modding/05-first-mod-texture.md); for models,
[`modding/04-extracting.md`](modding/04-extracting.md) and
[`modding/07-blender-setup.md`](modding/07-blender-setup.md). [`modding/README.md`](modding/README.md)
lists each guide with its status.

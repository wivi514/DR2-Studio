# Documentation

Pick the section for what you want to do.

| I want to… | Read |
|---|---|
| **Make a mod** (change textures, models, sounds, text) | [`modding/`](modding/README.md): step-by-step guides, no programming needed |
| **Understand or change the toolkit's code** | [`dev/`](dev/README.md): code tour, how to add a format, standards |
| **Know how the toolkit is designed** | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| **Know how a game file format works** | [`formats.md`](formats.md) |
| **See what is planned and what is done** | [`roadmap.md`](roadmap.md) |
| **Start the next phase of work** | Phases 1-9 are done; what is still owed: [`phase9-kickoff.md`](phase9-kickoff.md) §Status (variants: the in-game check), [`phase8-kickoff.md`](phase8-kickoff.md) §Status (the Library and export all) and [`phase7-kickoff.md`](phase7-kickoff.md) §Status; earlier handoffs, for history: [`phase6-kickoff.md`](phase6-kickoff.md), [`phase5-kickoff.md`](phase5-kickoff.md), [`phase4-kickoff.md`](phase4-kickoff.md), [`phase3-kickoff.md`](phase3-kickoff.md), [`phase2-kickoff.md`](phase2-kickoff.md), [`phase1-kickoff.md`](phase1-kickoff.md) |
| **See what was done, when, and why** | [`devlog.md`](devlog.md) |
| **Look up a word** (`.big`, LZX, tiling, bone palette, vpath…) | [`glossary.md`](glossary.md) |
| **Know what tools existed before this one** | [`prior-art.md`](prior-art.md) |

Phase 9 (done, 2026-10-10) added **variants**: a zombie shows one look (one head, one
shirt…) chosen in DR2 Studio, and exports as that look or with every part sorted into
groups for Blender ([`modding/17-variants.md`](modding/17-variants.md)).
Phase 8 (done) added the **Library**: everything sorted by what it is, with pictures,
and a model, a selection or a whole group exported in one go
([`modding/16-library.md`](modding/16-library.md)). Phase 7 put the guides inside the
app and added Play, `.dr2mod` sharing and texturing-program imports.
Phase 6 (done) added text and translations
([`modding/11-text.md`](modding/11-text.md)), the mod manager
([`modding/06-mod-packages.md`](modding/06-mod-packages.md)), the Blender add-on
([`modding/13-blender-addon.md`](modding/13-blender-addon.md)) and release builds
([`modding/01-install.md`](modding/01-install.md), [`dev/packaging.md`](dev/packaging.md)).
Phases 1-5 are done: the `dr2` command and DR2 Studio read every file of both games,
show every texture, build texture mods that load in both recomps, show every model and
skeleton in 3D, export them to Blender (`.glb`), put edited or new rigged meshes back
into the game, play every sound and replace sounds through the recomps
([`modding/10-audio.md`](modding/10-audio.md)). Start with
[`modding/02-game-data.md`](modding/02-game-data.md), then
[your first mod](modding/05-first-mod-texture.md); for models,
[`modding/04-extracting.md`](modding/04-extracting.md) and
[`modding/07-blender-setup.md`](modding/07-blender-setup.md), then
[`modding/08-edit-a-model.md`](modding/08-edit-a-model.md) and
[`modding/09-new-model.md`](modding/09-new-model.md). [`modding/README.md`](modding/README.md)
lists each guide with its status.

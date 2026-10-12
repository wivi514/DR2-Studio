# CLAUDE.md — DR2 CZ/CW Modding Toolkit

A modding toolkit for **Dead Rising 2: Case Zero** and **Dead Rising 2: Case West**
(Xbox 360 XBLA titles, Blue Castle Games engine) as run by the two Xenon recomps.

Goal: make modding easy. Browse every asset in both games, **see** what a texture is
and **hear** a sound before extracting it, export models and skeletons to Blender, and
put edited or new models back into the game when their bones match the game's rig.

**Status: phases 1-6 done (phase 6, 2026-10-09: string banks and `.bcs.json` mods,
text editing with a diff, CW Bink movies, the mod manager, digest-checked files refused,
the GPL Blender add-on that never bundles dr2kit, release packaging with an own LGPL
ffmpeg and a licence gate, built and tried on Linux only). Phase 7 (user-set 2026-10-09) mostly done the same day: the guides
are the in-app help (`dr2kit/help`, F1, "How to mod this", Help on errors, Welcome,
`dr2 help`), Edit in image editor / Open in Blender / drag and drop, Share (`.dr2mod`)
and Install windows, Play (`mods/play.py`, `dr2 play`), mod sets, the app icon; the
make→share→install→Play chain passed in game in CZ and CW (`tools/newcomer_gate.py`).
Owed: the gate run by a person, `.dr2mod` file associations, the carried-over items in
`docs/phase7-kickoff.md`. Also added: texturing-program imports (`mods/texture_import.py`,
guide 14) and the measured engine limits (guide 15, `formats.md` §Engine limits).
Phase 8 (user-set 2026-10-09) done the same day: the **Library** (Studio's first tab,
`dr2kit/catalog/groups.toml`, `dr2 library`), model pictures rendered while indexing
(`convert/render.py`), model → rig links by bone names and rest pose, and export
everything at once (`catalog/export.py`, *Export all…*, `dr2 export`); gate passed in both
games. Fixed 2026-10-10 from the user's tests: model colours (shader bakes, see-through
hair/opacity maps), rigid parts placed by their node, Play's renderer for source builds,
Open in Blender. Owed: `docs/phase8-kickoff.md` §Status and `phase7-kickoff.md` §Status.
Phase 9 (user-set 2026-10-10, variants, commit `89d8862`) done the same day: `convert/variants.py` (the game's
shape-group table as profile data, looks, hide mask, colour choices), the Variants panel,
default-look pictures, detail levels folded in the Library, as-shown / organised exports
(Blender collections, `KHR_materials_variants`), `dr2 variants`, `census --variants`; gate
passed in Studio and Blender in both games. Owed: the in-game zombie capture and how the
game picks a look, and the user's own test of Studio (started 2026-10-11)
(`docs/phase9-kickoff.md` §Status). Phase 10 (user-set 2026-10-11, Maps) done the same day: levels read and assembled
(`formats/level.py`, `convert/level.py`, `census --levels`), the level text files kept byte
for byte and every placed item's model found (`formats/levelscript.py`, `convert/placed.py`),
Studio's **Maps** tab (`studio/maps_view.py`, `web/maps.js`, lightmaps and blends as the
shaders draw them), level export (`catalog/level_export.py`, `dr2 export <level>`, the
add-on's Import zone), and **With my mods** (`mods/preview.py`, Ctrl+M). Fixed on the way:
`SHORT2N` decoded transposed, lightmaps taken for normal maps, level pieces using their
`_LOD` textures, a zone's first texture copy rule (checked in game). Checked in both games
(CW by eye by the user). Stretch done the same day: upper floor / basement map pictures,
zombies in their areas, time of day and the sky, the collision mesh (`formats/collision.py`).
Owed: the user's own test of Maps (`docs/phase10-kickoff.md` §Status). Editing
levels is phase 11, done; the user started testing Studio 2026-10-11, their findings first (`docs/phase11-kickoff.md`: edit objects and zombie spawns, and add your own
things from prefabs: save points, usable items, zombies, buildings), started 2026-10-11 with every proposed
default decision taken, built the same day: `.edits.json` level edits by block path
(`formats/leveledits.py`, `convert/levelcheck.py`, `mods/leveledit.py`, `dr2 level show|edit|diff`), the Maps
tab's editor for items, doors and zombies (`studio/maps_edit.py`), prefabs (`catalog/prefabs.py`), items of
your own (`mods/newitem.py`: a recipe, `add/` new entries), guide 19; checked in game in CZ (all) and CW
(items, prefabs, zombie retypes). Measured: a block added inside a game mission breaks saves (refused); a mod's
own mission runs in a new game only and its saves need it; a `.big` entry's `flags` is its declared
alignment. Step 4 done 2026-10-11/12 (user: "closer to a real editor like Unity"): buildings
(pieces grouped with their collision, `convert/buildings.py`) hidden / moved / resized /
copied as `.pieces.json` (`formats/pieceedits.py`, `mods/pieceedit.py`), collision moved
with them (`collision.move_shapes`: the Havok tree's origin), checked in CZ; every Studio
panel a dock window (`studio/docks.py`), Inspector, Hierarchy, Place with drag and drop
(`studio/maps_panels.py`), arrow-key nudging. Owed: CW building checks, collision for
copies (`docs/phase11-kickoff.md` §Status). Phase 12 (user-set 2026-10-12) ended the same day with its in-game tests
(`docs/phase12-kickoff.md` §Status): shock = `Can_Electrocute`, fire / freeze = a child
`cPropHitZombieInfoItem` (`PropHitZombieEffect` 0 / 1), effect numbers = an index into the
executable's effect table, borrowed moves, hands at the model's grip nodes, effects on the
weapon (conditions 30/31), a combo card of one's own; "Frostmourne" played on a carrier
item with replacements only, as new files (packs, card textures, string ids) stalled the
load. Phase 13 (user-set 2026-10-12, started the same day: `docs/phase13-kickoff.md` §Status):
the stall was a misread headless check (new files load); the weapon wizard
(`mods/newweapon.py`, Studio *New weapon…*, `dr2 mod new-weapon`, any `.glb` fitted to the
hands, the icon and combo card drawn from the model, effects by name: `dr2 effects`,
guide 20) built and checked headless; effects of one's own built too (`formats/effect.py`,
`mods/neweffect.py`, Studio *Effects…*, `dr2 mod effect|new-effect|effect-picture`; own effects
in the table's 36 free slots, checked headless). Mod builds now evict `preload4.big`'s copy of
the effects and re-pin `layout.bin` sizes (formats.md §Particle effects). Then (same day)
guides 21 (effects) and 22 (other games), WoW models and particles through a local tool
(`tools/wow_import.py`) into `local_only` mods that Share refuses, emitter fields measured
in game, the gate scripted through Studio's own windows in both games
(`tools/weapon_gate.py`), Case West loading with them. Owed: the user's windowed checks
(`docs/phase13-kickoff.md` §Start here). In game with the user the same day: the aura runs
along the blade once the wizard moves the effect point (locator 16) in both
`LocatorArray` copies (the game reads `persistent.big`'s); *Shine* and *Weapon effects
start* added. Phase 13.2 (user-set 2026-10-12) built the same day: `.anm` read to its first frame
(`formats/anim.py`, `census --anims`), each item kind's idle from the game's animation graph
`sgraph.txt` (`convert/holding.py`), Chuck posed holding the weapon in a 3D view with its
effects playing and drag handles (`studio/hold_view.py`, `web/hold.js`, in *New weapon…*
and *Effects…*), `dr2 hold`. Owed: the comparison with the game by the user
(`docs/phase13-kickoff.md` §Status 13.2). Phase 14
(user-set 2026-10-12, "Do phase 14", started the same day: `docs/phase14-kickoff.md`):
**animations played** done (every key of every `.anm` read as the game's decoder does,
census to the last byte in both games; Chuck swings the weapon in Studio's 3D view, any
`.anm` plays in the asset browser on its rig, `.glb` Actions for Blender); **buildings**
(a new level piece + an invisible collision item) and **maps** (the executable's empty
level slots, `LEVEL_FOOD_BARN`) have their in-game tests T4a, T4b, T5 built
(`~/.cache/dr2kit-p14/`) with the toolkit pieces they need (`.pieces.json` `new`, level
piece / plain-file copy recipes, new files with `layout.bin` records); owed: the tests
run by the user (away since 2026-10-12 evening; they play them when back), then the tools (`docs/phase14-kickoff.md` §Start here).
Phases 15 (Case West ↔ Case Zero: items, zombies, bosses, whole maps, assigned
automatically so nothing crashes; a requirements file for XenonLive) and 16 (the same
from the PC Dead Rising 2 and Off the Record) are researched and planned, not started:
`docs/phase15-kickoff.md`, `docs/phase16-kickoff.md`.** Read these before writing code:

| Doc | What it holds |
|---|---|
| `docs/ARCHITECTURE.md` | Components, data flow, the asset index, the mod package format, stack choices |
| `docs/formats.md` | Everything known about every file format, with a status per format (cracked / partial / unknown) |
| `docs/phase15-kickoff.md` | Phase 15 (planned): the other game's items, zombies, bosses and maps, auto-assigned (empty slots, type maps, shaders, classes), the importer's checker, the requirements file (`[requires]`, `requirements.json`) for XenonLive; research facts, tests U1-U6, plan, decisions |
| `docs/phase16-kickoff.md` | Phase 16 (planned): the same from PC Dead Rising 2 / Off the Record: PC formats first look, DR2 maps into CZ's own DR2 slots |
| `docs/phase14-kickoff.md` | Phase 14 (animations played: done; buildings and maps of your own: in-game tests T4a, T4b, T5 built, not yet run): research (level pieces, item collision, the executable's level slots, `layout.bin`), the tests and what each answer gives, plan, decisions, gate, §Status, §Start here |
| `docs/phase13-kickoff.md` | Phase 13 and 13.2 (Chuck holding it in 3D: §Status 13.2; steps 1-6.4 built; next steps in §Start here: weapons made easy, effects of one's own, the icon from the model, phase 12's tools): what phase 12 proved, plan, decisions, gate, §Status, handoff (where phase 12's working files are) |
| `docs/phase12-kickoff.md` | Phase 12 (ended: your own weapons with effects, combo weapons, buildings, maps): research (weapon keys, combo cards, grip locators, level slots), unknowns and the in-game tests to do first, plan, decisions, gate, §Status |
| `docs/phase11-kickoff.md` | Phase 11 (edit levels: zombie spawns, objects; add your own things from prefabs; saved as `.edits.json` mods): research, plan, gate, §Status (what was measured in game, what it still owes) |
| `docs/phase10-kickoff.md` | Phase 10 (Maps: see a whole level, extract it, see your mods in it without the game): research, plan, gate, and §Status (what it still owes) |
| `docs/phase9-kickoff.md` | Phase 9 (variants: one look per model, export as shown or organized): research, plan, gate, and §Status (what it still owes) |
| `docs/phase8-kickoff.md` | Phase 8 (the Library, export everything at once): decisions, gate, and §Status (what it still owes) |
| `docs/phase7-kickoff.md` | Phase 7 handoff and §Status: what phase 7 did and still owes |
| `docs/dev/packaging.md` | Release builds: the bundle, the LGPL ffmpeg and licence gate, AppImage, CI |
| `docs/dev/blender-addon.md` | The GPL Blender add-on and why it doesn't contain dr2kit |
| `docs/dev/code-tour.md` | Every module of `dr2kit` and how a read flows through them |
| `THIRD_PARTY.md` | Reused code and its licenses (libmspack is LGPL: keep it in its own library) |
| `docs/roadmap.md` | Phases, what each phase delivers, and the gate that proves it works |
| `docs/README.md` | Docs index: modder guides (`docs/modding/`), developer guides (`docs/dev/`), glossary, devlog |
| `docs/prior-art.md` | Community tools (ProBoards, wiki, Gibbed, mariokart64n's MaxScript, Chrrox) and what to learn or avoid from each |

## Documentation rules (user requirement, 2026-10-08)

**Document everything we do**, so people can understand the code and the docs, and can
learn to mod with the toolkit. Documentation is part of done, not a follow-up task.
Every change, however small, updates whichever of these it affects, **in the same commit**:

| What changed | Update |
|---|---|
| Any code | Module docstring (purpose, *why*, key facts, link to `formats.md`), public docstrings + type hints, `docs/dev/code-tour.md` for new modules |
| A format fact | `docs/formats.md` (keep retractions; state how it was verified) |
| Something a modder can now do, or do differently | A guide in `docs/modding/` (template in `docs/modding/README.md`) and its status row there; `asset-catalogue.md` / `12-troubleshooting.md` when relevant |
| A new term | `docs/glossary.md`, in plain words |
| A decision or design change | `docs/ARCHITECTURE.md` and/or `docs/roadmap.md` |
| Every work session | A `docs/devlog.md` entry: done, why, learned, docs updated, next |

Write for a newcomer: plain words, define jargon or link the glossary, explain *why*
before *how*, and show real examples. Modder guides need no programming knowledge and
give the Studio (GUI) steps first, then the `dr2` CLI equivalent. Full style and the
definition-of-done checklist: `docs/dev/README.md`. Docs index: `docs/README.md`.

## Where the games live

Both recomps sit next to this repo. They are separate repos with their own CLAUDE.md
files and conventions. Treat them as **read-only references**, except for the two
approved integration changes (a `game_mods/` VFS layer and PCM audio substitution,
`docs/ARCHITECTURE.md` §Recomp integration). Make those in each recomp following its own
CLAUDE.md, and keep CZ and CW in step.

| | Case Zero | Case West |
|---|---|---|
| Recomp repo | `../Dead_Rising_2_Case_Zero_Xenon_Recomp` | `../Dead_Rising_2_Case_West_Xenon_Recomp` |
| Unpacked game data | `…/assets/game/data/` (146 `.big`, 832 MB) | `…/assets/game/data/` (154 `.big`, 1.2 GB) |
| Title ID | `58410A8D` | `58410B00` |
| XBLA package | `…/assets/package/58410A8D/000D0000/` (256 files) | `…/assets/package/58410B00/000D0000/` (305 files) |
| Extra content vs CZ | — | `.bik` movies (Bink), `controls/`, `dynamicprops/`, more `.csv` |
| Runtime VFS overlays | `assets/game_bootskip`, `game_kbm`, `game_patched` | `game_kbm`, `game_patched` |

The game data is **copyrighted**. Never commit it, never copy it into this repo, never
put extracted assets in test fixtures. Tests that need real data locate it through the
game profile config and **skip, saying so,** when it is absent.

## Prior work to reuse (in the CZ recomp's `tools/`)

The CZ recomp already cracked a lot. Port it here, don't rediscover it. Phase 1 ported
`big_list.py`, `read_big`/`write_big`, the LZX encoder, `name_hash.py` and
`extract_stfs.py` (`THIRD_PARTY.md` maps each to its module); the rest is still to port. Its docs record
*why* each detail is the way it is, including retractions; read them before changing
behaviour.

| Existing | What it gives us |
|---|---|
| `docs/big-archive-format.md` | The `.big` container: layout, the variable-length names, the compression, two retractions |
| `tools/big_list.py` | Listing and extracting `.big` entries (stored bytes) |
| `tools/big_decompress.cpp` | LZX decode of compressed entries, linked from XenonRecomp's `lzxDecompress` (which wraps libmspack's **LGPL-2.1** `lzxd.c`, so keep it a separate shared library), checked against an oracle |
| `tools/gen_pc_options.py` | `read_big` / `write_big`, a **real pure-Python LZX encoder** (`lzx_encode_stream`), `verify_fake_lzx`, a `.bcs` string-bank patcher |
| `tools/patch_coop_ending_bike.py` | A worked example of re-packing a modified entry that the game accepted |
| `tools/tex_decode.py` | Xenos `Tiled2DOffset` untiling + DXT1/DXT5 decode (ported in phase 2) |
| `tools/vsdump_skin.py`, `CZ_CAPTURE_DUMP_VS` | Draw dumps (constants + stream bytes) of one shader; the toolkit's `tools/capture_gate.py` reads them (phase 3) |
| `tools/name_hash.py` | The engine's string hash (`h = h*33 ^ c`); `.big` entries are looked up by hash |
| `runtime/audio/xma_decoder.cpp` | How to feed raw XMA to ffmpeg's `xma2` decoder (the 34-byte XMA2 extradata); `runtime/kernel/audio.cpp` holds the audio substitution added in phase 5 |
| `runtime/kernel/vfs.cpp` | The overlay layers; the `game_mods/` layer was added here in phase 2 (both recomps) |

## Hard-won rules (inherited from the recomp work, all measured)

1. **Endianness flips inside one file.** The `.big` header and index are **little-endian**;
   the compressed stream inside an entry, and every payload (textures, models,
   skeletons), is **big-endian**. Choose byte order per structure, never per file.
2. **`.big` names are variable-length.** Read each name up to the NUL from its own
   `name_offset`. A fixed width only holds within the shader banks.
3. **`size` is the stored length, `size2` the uncompressed length; `resv == 2` marks
   compression.** 1,671 entries of CZ's `.big` files are compressed (10,754 counting
   nested archives; CW 21,354). An empty compressed entry is just `00 00 00 00`.
4. **Compressed entries must be re-encoded, not stored.** The game asserts and crashes on
   a stored replacement where it expects compression, and crashes on degenerate LZX
   streams that other decoders accept. Use the real encoder and verify by decoding.
5. **Shipped textures are tiled.** Untile with `Tiled2DOffset` before you look at them, and
   re-tile before you write them back.
6. **Name what you could not parse.** A tool that silently skips what it can't read gives
   confident wrong answers (the first `big_list` dropped 95 of 146 archives). Every
   reader reports unknown chunks, unknown formats and leftover bytes.
7. **A structural constant seen in one family of files belongs to that family** until a
   second family agrees. Check a format claim against more than one archive *and* both
   games before writing it down as a rule.

## Verification gates (use these, not eyeballing)

- **Round-trip identity.** `read → write` with no edits must produce byte-identical
  output for every archive in both games. This is the first test of every writer.
- **Decode oracles.** LZX output must have the right `size2` and the expected magic
  (`05 01 01` for `.bct`; the 4th byte varies, so `05 01 01 E2` was a retracted claim).
  Two independent LZX decoders (native libmspack, pure Python) must agree. Decoded
  skeleton quaternions must have unit norm.
- **Cross-game census.** A format change is not done until a census over *all* entries of
  that type in CZ and CW reports zero unparsed entries (or names each one).
- **In-game proof.** A replacement counts only once it loads in the recomp. The
  recomp's `game_patched` overlay is the existing path for that.

## Commands

```
python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"   # setup (docs/dev/setup.md)
cmake -S native/lzx -B native/lzx/build -DCMAKE_BUILD_TYPE=Release && cmake --build native/lzx/build
python -m pytest -q                       # unit + game-data tests (game tests skip if absent)
dr2 doctor                                # LZX backend in use, games found
dr2 census                                # both games: counts + round-trip/decode gates (~30 s)
dr2 census --reencode --python-lzx        # the slow LZX gates (~20 min, all CPUs)
dr2 census --textures                     # the texture re-encode gate (~4 min CZ, ~6 min CW)
dr2 census --models                       # decode every draw of every model (~40 s / ~70 s)
dr2 census --reimport                     # + .glb re-import and shape rebuild gates (~4 / ~8 min)
dr2 extract --glb <model vpath> -o out    # model or skeleton -> .glb for Blender
dr2 census --audio                        # decode every sound, check lengths (~30 / ~42 s; PyAV)
dr2 extract --wav <sound vpath> -o out    # .xma -> WAV (pip install av)
dr2 model check <file.glb> <model vpath>  # rig validator (import: dr2 model import … -o)
python tools/blender_skeleton_gate.py     # skeleton round trip through Blender (~25 s)
dr2 index build                           # the asset index + model pictures (~3-4.5 min per game)
dr2 library [group] / dr2 library --check            # the Library: groups, items, the count gate
dr2 export <group|vpath…> -g cz -o out [--wav|--png|--glb…]   # export all (one folder per model)
dr2 variants <model vpath> [--variant head=2,shirt=1] [--parts]  # a model's looks (phase 9)
dr2 extract --glb --variant "head=2" --variants shown|all <model> -o out
dr2 census --variants                     # classify every model's parts as the game does (~30 / ~50 s)
python tools/variant_table.py <recomp>/assets/game/default_image.bin --check cz   # table = exe?
python tools/blender_variants_gate.py     # phase 9 gate in Blender (~20 s)
dr2 level list|info|things -g cz          # levels: zones, placements, what the text files place
dr2 level show|edit|diff <file> …          # phase 11: a mod's level edits (.edits.json, guide 19)
dr2 mod new-item <mod> <Name> --like <item> [--glb] [--texture N=png]   # an item of your own (recipe)
dr2 mod new-weapon <mod> <Name> --kind sword --glb sample|file [--element freeze --held N --combo A+B] -g cz
dr2 effects [words] [--group ice] [--kinds] [--show NAME --out p.png] -g cz   # effects by name, kinds
dr2 mod effect <mod> <effect> --hue 210 [--size 1.5]   /   dr2 mod new-effect <mod> <effect> --hue 210 [--slot wip_1]
dr2 mod effect-picture <mod> <name> <png>                              # a particle picture of your own
dr2 effects --free -g cz                  # the effect table's free slots (own effects go there)
python tools/weapon_gate.py cz|cw --out ~/.cache/dr2kit-gate13/cz [--install-user]   # phase 13 gate via Studio
python tools/wow_import.py extract|model|effect …   # WoW 3.3.5 → .glb / an own effect (local only, guide 22)
python tools/effect_table.py <recomp>/assets/game/default_image.bin --check cz   # effects.toml = exe?
dr2 census --levels                       # every zone, placement, level text file, item model (~50 s / game)
dr2 census --anims                        # every .anm: every key, to the last byte (~30 s / game)
dr2 hold Broadsword -g cz -o out --png    # Chuck in the item's idle holding it (.glb + picture);
dr2 hold FrostBlade --mod my-mod -o out   #   or a mod's wizard weapon
dr2 hold Broadsword --moves -g cz -o out  # + every attack as a glTF animation (Blender Action)
dr2 extract --glb -g cz <.anm vpath> -o out   # an animation on Chuck (or its rig's bones)
dr2 export prologue [--zone z05] [--whole] [--zombies] [--collision] -g cz -o out   # a level for Blender
dr2 studio                                # the GUI (pip install -e ".[studio]")
dr2 help [page] / dr2 help --search <words>          # the guides (= Studio's help)
dr2 play -g cz [--no-mods] [--deploy-only]           # deploy switched-on mods, start the recomp
dr2 mod import-textures <mod> <model vpath> <export folder> [-n]   # Painter/Blender exports -> mod
dr2 mod status | link | sets save/use NAME           # what's in the game, linked mods, mod sets
python tools/newcomer_gate.py cz --frames ~/.cache/dr2kit-gate7/cz   # phase 7 gate (on disk!)
dr2 strings search <words> / set <mod> <id> <text>   # string banks (phase 6)
dr2 mod list|install|enable|move|conflicts|pack     # the mod manager (phase 6)
dr2 extract --mp4 -g cw data/movies/dr2_logo.bik -o out   # Bink -> MP4
blender --command extension build --source-dir blender/io_dr2 --output-dir build/addon
BLENDER_USER_RESOURCES=<tmp> blender -b --factory-startup --python tools/blender_addon_gate.py -- build/addon/io_dr2-0.1.0.zip . <mod>
tools/release/build_ffmpeg_lgpl.sh && python tools/build_release.py bundle|archive|appimage  # release (dev/packaging.md)
```

## Clean up after yourself (user requirement, 2026-10-09)

When a task or gate is done, delete what you made for it: scratchpad files, recomp
frame dumps and captures, copied saves, test mods (undeploy, remove the empty
`game_mods/`), throwaway Blender user folders, one-off build output (`build/release`).
Keep the build caches the docs name (`build/ffmpeg-lgpl`, `build/ffmpeg-work`,
`build/release-venv`, `native/lzx/build`). In `/tmp/claude-1000`, only delete folders
that no running Claude session uses. Say what you removed.

## Conventions

- Language: **Python 3.11+** for the core library, CLI and GUI. Pure Python plus optional
  numpy, so the same core imports inside Blender's bundled Python. The only native code
  is the LZX decoder (a small C shared library loaded through ctypes, with a pure-Python
  fallback). See `docs/ARCHITECTURE.md` §Stack.
- Paths inside archives are written `data/models/npcs.big/chest_default.tex/chest_default_cm`
  (archive path, then `/` for each nesting level). This "virtual path" is the asset's
  identity everywhere: the index, mod manifests, the CLI and the GUI.
- Every format module has a reader, a writer (once supported), a census command and a
  section in `docs/formats.md`. When a fact changes, update that doc in the same commit,
  and keep a retraction in place rather than silently rewriting history.
- **Windows, Linux and macOS are all supported** (core, CLI, PySide6 Studio). `pathlib`
  only, case-insensitive virtual paths, `platformdirs` for user folders, no shelling out
  to Unix tools, and a pure-Python fallback for every native piece. Data must be
  obtainable without a recomp (the STFS package). Details: `docs/ARCHITECTURE.md` §Platforms.
- License: `LICENSE`, free and non-commercial. The toolkit can't be sold, and mods for these
  games can't be sold or paywalled. Don't add dependencies whose licenses conflict
  with distributing the toolkit for free (LGPL/MIT/BSD/Apache are fine; PySide6 is LGPL).
- Game profiles (`cz`, `cw`) are data, not branches in code. Format differences between
  the games go into the profile.

## Host environment (as of 2026-10-08)

Fedora 44, Python 3.14 (system), Blender 5.2.1 LTS at `/usr/bin/blender`, ffmpeg with
`xma1`/`xma2` and Bink decoders. No `xxd` (use `od`). `vgmstream-cli` not installed.
`uv` is available (it also provides Python 3.11/3.12 for compatibility checks). Dev venv:
`.venv/` (`uv venv .venv --python 3.14 && uv pip install -e ".[dev,studio]"`; PyAV, numpy,
PySide6 6.12 and Pillow installed there too). DR2 Studio runs headless with
`QT_QPA_PLATFORM=offscreen` (screenshots via `window.grab()`). CMake + Ninja + gcc/clang present; the native LZX library is built in
`native/lzx/build/`. `/tmp` is RAM-backed (32 GB, shared with old session scratchpads):
put recomp frame dumps on disk (`~/.cache/...`). No `nasm` (the LGPL ffmpeg builds
without x86 assembly). Release venv: `build/release-venv` (PyAV built from source).
Python 3.14 uses the *forkserver* start method, so any script that
runs `dr2 census --reencode` (a process pool) needs an `if __name__ == "__main__"` guard.

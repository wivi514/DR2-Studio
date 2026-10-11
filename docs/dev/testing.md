# Testing

How the toolkit proves that it reads and writes the game's files correctly. The short
version: **we compare against something we did not write** (the original bytes, an
independent decoder, the game itself), never against the code's own idea of right.

## Three kinds of checks

| Kind | Runs where | Data | Command |
|---|---|---|---|
| **Unit tests** | everywhere, CI included (Windows, Linux x64/arm64, macOS) | tiny synthetic files built in the test | `python -m pytest -m "not gamedata"` |
| **Game-data tests** (marker `gamedata`) | your machine, if a game is installed | the real game, found through the profiles | `python -m pytest -m gamedata` |
| **Gates** (slow) | your machine, before calling a phase or format done | every entry of both games | `dr2 census --reencode --python-lzx`, `dr2 census --textures` |

Game-data tests **skip with a message** when a game is missing (`SKIPPED … cw game data
not available: …`). A skip is not a pass: before claiming a format works, make sure the
game-data tests actually ran for both games.

### Never commit game data

The games are copyrighted. Tests must not contain game files, pieces of them, or
anything extracted from them (CLAUDE.md). Numbers *about* the data are fine (counts, a
hash value from an index, an offset). Unit tests build their inputs in code, for example
with `make_archive()` from `tests/conftest.py`:

```python
from conftest import make_archive
from dr2kit.container.big import LZX

arc = make_archive(("notes.txt", b"hello " * 100, LZX), ("tex_cm", b"\x05\x01\x01\xe2"))
raw = arc.to_bytes()
```

## The verification gates

These come from `CLAUDE.md` ("Verification gates") and each phase's gate in
[`../roadmap.md`](../roadmap.md).

1. **Round-trip identity.** `read → write` with no edits gives byte-identical output.
   The census does this for every archive in both games, nested ones included. It is the
   first test of every writer.
2. **Decode oracles.** Every compressed entry decodes to exactly its `size2`, and the
   chunk framing adds up with no leftover bytes.
3. **Independent decoders agree.** The native decoder (libmspack) and the pure-Python
   one were written by different people from the same format description. `dr2 census
   --python-lzx` decodes every compressed entry with both and compares. The unit tests
   also feed both decoders streams built by hand (`tests/test_lzx.py`: a literal-only
   block, and an *aligned offset* block, a type our encoder never writes).
4. **Encode, then decode.** `dr2 census --reencode` compresses every decoded entry again
   with the toolkit's encoder and checks it decodes back. (Whether the *game* accepts a
   re-encoded entry is a separate proof: the in-game gate, phase 2.)
5. **Cross-game census.** A format claim counts only when a census over *all* entries of
   that type in **both** games reports zero problems (or names each one).
6. **In-game proof.** A replacement counts once it loads in a recomp. Phase 2 adds the
   `game_mods/` folder for that. A *reader* is checked against the running game too:
   phase 3 compares decoded models with draws captured from the recomp. Sounds are
   checked by recording what the recomp sends to the speakers (phase 5).

### Phase 1 results (2026-10-08)

| Gate | Case Zero | Case West |
|---|---|---|
| Archives round-trip byte-identically (on disk + nested) | 7,413 / 7,413 | 8,017 / 8,017 |
| Compressed entries decode to `size2` | 10,754 / 10,754 | 21,354 / 21,354 |
| Pure-Python decoder agrees with native | 10,754 / 10,754 | 21,354 / 21,354 |
| Re-encoded entries decode back | 10,754 / 10,754 | 21,354 / 21,354 |
| Index hash = engine hash of the lower-cased name | 124,932 / 124,932 | 172,322 / 172,322 |
| Unparsed entries or archives | 0 | 0 |
| XBLA package unpacks to the recomp's files, byte for byte | 256 / 256 files | 305 / 305 files |

### Phase 2 results (2026-10-08)

| Gate | Case Zero | Case West |
|---|---|---|
| Textures parse (header, known format, layout fits the payload) | 12,237 / 12,237 | 23,139 / 23,139 |
| Every level decoded → re-encoded (reference blocks) → re-tiled gives the identical file (`dr2 census --textures`, ~4 / ~6 min) | 12,237 / 12,237 | 23,139 / 23,139 |
| Payload size equals the layout model (informational; the rest are larger, never smaller) | 12,186 | 23,038 |
| Index built with no unparsed asset (`dr2 index build`) | 125,166 assets, 0 problems, ~90 s | 172,603 assets, 0 problems, 67 s |
| Model → texture links found (slots naming a texture found nowhere) | 80,230 (56) | 494,475 (93) |
| **In-game gate**: recoloured texture in a compressed `.tex`, via `game_mods/` | `young_cr_shirt_cm`: green "04" shirt at frame 12864; orange with `CZ_NO_MODS=1` | `cr_jacket_cm`: green IJIEK jacket at frame 6144; yellow with `CW_NO_MODS=1` |
| Recomp log | 1 "served from the MODS overlay" line (npcs.big); 0 with the off switch | same |

The in-game runs are headless (`*_NO_WINDOW=1 *_VKDRAW=1 *_VK_FRAME_DUMP=…`, scripted
START,A,A into a *copy* of the save); the recipe is in
[`recomp-integration.md`](recomp-integration.md). They are the first proof that the game
accepts entries re-encoded by the toolkit's LZX encoder (verbatim blocks), for model
texture packs in `npcs.big`. `preload4.big` (read at boot, where the CZ recomp once saw
re-encodes rejected) is **still unproven**.

Visual checks (by eye, on decoded PNGs): DXT1 faces and clothing, DXT5 UI icons with
alpha, DXN normal maps, L8 font pages, cube-map faces. A8R8G8B8 is checked numerically
on the identity colour LUT `cc_00.bct` (R = x mod 32, G = y, B = slice; mean error 0.5).

Unit tests run with and without numpy/Pillow (CI does both); DR2 Studio has an
off-screen smoke test that skips when PySide6 is missing.

### Phase 3 results (2026-10-08)

| Gate | Case Zero | Case West |
|---|---|---|
| Scenes parse (`dr2 census`) | 1,510 (1,397 models, 113 skeletons) | 1,639 (1,495, 144) |
| Every draw of every model decodes, every draw finds its material (`dr2 census --models`, ~40 / ~70 s) | 6,954 / 6,954 | 10,548 / 10,548 |
| Skin weights sum to 1 / normals unit length (or zero) | all / all | all / all |
| **Skeleton gate**: `data/skeleton` rig → `.glb` → Blender 5.2 import → export → records (`tools/blender_skeleton_gate.py`) | 3,474 / 3,474 node records bit-identical, 75 rigs, both games together | |
| Same, every scene with a skeleton (`--all-scenes`) | 41,184 / 41,209 (the 25 others carry a rest scale Blender bones can't hold; [`gltf-mapping.md`](gltf-mapping.md)) | |
| **In-game gate** (`tools/capture_gate.py` on a CZ capture of Chuck) | 30 draws match the game data byte for byte (vertices + indices); 79 draw pairs sharing a bone get identical matrices, 0 with a shifted palette; bone lengths within 0.01 mm (median); skinned + projected vertices land on Chuck in the frame | not captured |

Visual checks: the mechanic boss, Chuck's shirt and the bike rendered in Blender and in
Studio's 3D view (textures, normals, shirt print not mirrored); bones posed in Blender
deform arms, head and fingers cleanly. The mechanic check caught a bug the numbers
couldn't: draws took their material by position instead of by id (fixed; formats.md
§Materials). The capture procedure is in [`recomp-integration.md`](recomp-integration.md)
§Phase 3.

Game-data tests added: the scene counts in the census test, a slow "every model draw
decodes" test, and three reference exports (Chuck's chest part and the mechanic in CZ,
the default chest in CW) that must find every texture.

### Phase 4 results (2026-10-08)

| Gate | Case Zero | Case West |
|---|---|---|
| Every chunk the reader interprets rewrites identically (`dr2 census`) | 1,510 / 1,510 scenes | 1,639 / 1,639 |
| Every vertex element re-encodes to its stored bytes (`dr2 census --models`) | 6,954 / 6,954 draws | 10,548 / 10,548 |
| **No-op gate**: model → `.glb` → import, byte-identical (`dr2 census --reimport`, ~4 / ~8 min) | 1,397 / 1,397 models | 1,495 / 1,495 |
| Every shape rebuilt from its own geometry decodes the same (`--reimport`) | 6,953 draws + 1 vertex-animated skipped | 10,547 + 1 |
| Blender 5.2 round trip of `chest_young_chuck.big` | every shape rebuilt, same triangles, palettes and weights; positions within 1 µm | |
| **In-game gate** (gate model from `tools/blender_gate_model.py`, deployed as a mod, captured; `tools/capture_gate.py --root <game_mods>`) | 32 / 32 dumped skinning draws match the mod build byte for byte (rebuilt shirt, inflated arms, both draws of the new mesh); 80 draw pairs sharing a bone agree, 0 disagree; the new mesh gets the head's exact matrices for 34 face bones (21 moving) and follows fingers bent up to 45°; the picture shows it (side by side with `CZ_NO_MODS=1`) | not run |

Unit tests added: `test_scene_write.py` (encoders incl. the lowest snorm codes, rewrite,
strips with winding, weights, palette splitting, replacing own and combined shapes),
`test_model_import.py` (no-op identity, reordered bones, unknown bone and unweighted
errors, influence merge, material fallback, a mod with a `.glb` override), and the
Studio test now runs *Replace with .glb…*. The procedure for the capture is in
[`recomp-integration.md`](recomp-integration.md) §Phase 4.

### Phase 5 results (2026-10-09)

| Gate | Case Zero | Case West |
|---|---|---|
| Every `.xma` decodes to the length its metadata says (`dr2 census --audio`, needs PyAV; ~30 / ~42 s) | 8,916 / 8,916 (3.17 h) | 11,735 / 11,735 (3.82 h) |
| Every `.sfx` parses; tracks resolve in their bank | 4,745; all but 22 recordings the data lacks | 5,194; all but 1 |
| Packet-by-packet decode = whole-file decode (mono, stereo, each stream of 5.1) | checked on 3 sounds, max difference one 16-bit step | |
| **In-game gate**: title music replaced by another track, recorded with SDL's disk driver, vs `CZ_NO_AUDIO_MODS=1` / `CW_NO_AUDIO_MODS=1` | with the mod the recording follows the replacement at the right positions (1 s windows up to 0.94 normalised correlation) and not the original; without, the original | same (0.50-0.57 at the right positions) |
| Editing `Prologue.txt` (the planned easy remap) | the game crashes on the digest check: ruled out | not tested (same digest manager) |

Unit tests added: `test_audio.py` (XMA2 `fmt` round trip, RIFF wrap/parse and its
errors, loop info with the 384-sample delay, packet headers, stream starts, the FNV-1a
test vectors, stream tables with the case-kept hash, `.sfx` tracks, scene-script
references with their trigger context, parse errors with line numbers, WAV round trip,
`conform`, `split_streams`, the length rules). `test_index.py` checks sounds and their
links on a synthetic game; `test_studio.py` the audio view. Game-data tests:
`test_every_sound_decodes_to_its_length` (both games), `test_music_metadata_and_decode`,
`test_audio_mod_build` (every packet's position in the table equals PyAV's). The
procedure for the in-game check is in
[`recomp-integration.md`](recomp-integration.md#testing-it-the-phase-5-in-game-gate).

### Phase 6 results (2026-10-09)

| Gate | Case Zero | Case West |
|---|---|---|
| Every string bank parses and re-writes byte-identically (`dr2 census`, always on) | 8 / 8 (7,599 ids each) | 8 / 8 (2,469 ids each) |
| Every digest of the XEX matches a file of the game (`tools/xex_digests.py`) | 1 / 1 | 6 / 6 |
| Every Bink movie decodes: all frames, and the sound as long as the pictures (`census --audio`) | (no movies) | 10 / 10 (7.7 min) |
| **In-game gate**: `IDS_PRESS_START` changed through a `.bcs.json`, deployed with `dr2 mod deploy`, title screen captured headless | shows the new text; VFS logs `str_en.bcs served from the MODS overlay` | same |

| Blender add-on, whole flow in Blender 5.2 (`tools/blender_addon_gate.py`: install, search, import `chest_young_chuck`, check, edit, check, export to mod) | passes in ~6 s; `dr2 mod check` accepts the mod | |
| Release bundle (Linux, `tools/build_release.py`): licence gate (no GPL library, LGPL ffmpeg with XMA and Bink, native LZX) | passes (after the fix in `packaging.md`: it first caught 4 GPL libraries) | |
| The LGPL PyAV build decodes every sound and movie (`dr2 census --audio` in the release venv) | 8,916 / 8,916 | 11,735 / 11,735, 10 / 10 movies |
| Bundled `dr2` and the AppImage: WAV, MP4, `.glb`, PNG, strings, mod check; Studio starts | ✅ | ✅ |

Unit tests added: `test_bcs.py` (banks laid out by hand: padded and unpadded round trips,
reader errors, padding kept when the text fits, `apply` notes and the last-id rule, JSON
and labels, the strings helpers, string mods merging by id with priorities, whole bank
vs strings conflicts, digest-checked files refused, the `dr2 strings` commands);
`test_library.py` (install, order, switches, the plan's winners, priorities on install,
hand-copied folders, pack and install a zip, zip-slip refused, the `dr2 mod` library
commands); `test_studio.py` (text editor with CRLF and diff, the strings table, the mod
manager, the game folders window); `test_blender_addon.py` (the add-on's
`toolkit`/`core` without Blender, licence markers); `test_userdirs.py` (the fallback
folders equal platformdirs'); `test_release.py` (deterministic add-on zip, the licence
gate's names, the icon). Game-data tests: `test_string_banks`, `test_digest_checked_files_exist`,
`test_movies_probe`.

### Phase 7 results (2026-10-09)

| Gate | Case Zero | Case West |
|---|---|---|
| **In game, scripted** (`tools/newcomer_gate.py`): a mod made in library A (red shirt / jacket, `IDS_PRESS_START` changed), shared as `.dr2mod`, installed into an empty library B, **Play** (deploy + start the recomp, headless), then **Remove mods from game** | title shows "DR2KIT PHASE 7 OK"; the loaded save shows Chuck in a red shirt; `game_mods/` gone afterwards | title text shown; Chuck's jacket red in the title scene (the save didn't finish loading in the 170 s) |
| *Open in Blender*'s script in Blender 5.2 (headless) | imports `chest_young_chuck` into a collection tagged `dr2_game`/`dr2_vpath` | |
| The built wheel carries the help (`uv build`) | 16 pages + `context.toml` + the icon | |
| Studio screenshots on real data (main window with the mod's texture, Welcome, Help, Share, Install, mod manager, Game folders) | looked at; fixed a clipped help box and help scrolling | |

**Texturing and limits** (2026-10-09): Painter-style exports of `chest_young_chuck`
(2048 px, a DirectX-style normal map, a Roughness file) imported into a mod: matched,
resized, green flipped (the result's green correlates 0.997 with the game's own normal
map), Roughness skipped; `dr2 mod check` accepts the mod. Not yet done in Substance
Painter itself. The limits and conventions in `formats.md` were measured over every
model and texture of both games. Unit tests: `test_texture_import.py` (names, the
`$mesh_` prefix, sizes, skips, metal/roughness, a `.glb` source, the green test on a
synthetic bump).

**Still owed** (the gate as written is a person, not a script): someone new follows only
the in-app help on a clean profile, without a terminal, in both games.

Unit tests added: `test_help.py` (pages in the guides' order, search, context help,
fallback language, `dr2 help`, error → help, **every link between guides resolves**,
every context entry names a guide); `test_library.py` (linked and new mods, mod sets,
update summaries, preview/readme, Play: deploy, status, removal, finding and starting
the recomp with mods off); `test_studio.py` (only applicable buttons shown).
`conftest.py` now gives every test its own user folders (`userdirs`), and turns
Studio's dialogs and welcome window off: a phase 7 test run had linked test mods into
the developer's real mod library before that.

### Phase 8 results (2026-10-09)

| Gate | Case Zero | Case West |
|---|---|---|
| Index build with scene facts, thumbnails, rigs, Library (`dr2 index build`, from scratch) | 183 s; 1,510 models/skeletons read, 1,397 thumbnails, 0 unparsed | 266 s; 1,639 read, 1,495 thumbnails, 0 unparsed |
| **Count gate** (`dr2 library --check`): every model, skeleton, sound, texture, string bank and movie in a group; stored groups = the rules; copies point at shown items | 0 problems (text: 1,400 inside models not shown) | 0 problems after adding `zombie_pdv_variations.txt` to Game data (the gate found it) |
| **From the Library only** (Studio driven headless: Library tab → Characters → a model → *Export all…*; group → *Export…*) | `chest_young_chuck`: 13 files; Music: 16 WAVs; Characters: 91 folders, 1,671 files in 97 s | `chest_default_frank`: 16 files; Music: 35 WAVs; Characters: 166 folders, 2,257 files in 176 s |
| The `.glb` in Blender 5.2 (headless import of the single export + 3 random characters per game) | 98-bone armature, every mesh skinned, every material textured; a render shows the textured shirt | the same; Frank's jacket and camera rendered with textures |
| Rig links (every character has one) | 66 player, 13 female, 2 large, 1 child, 9 zombie (other proportions) | 145 player, 19 female, 1 large, 1 longcloak |
| Thumbnails looked at (contact sheets of every group) | characters, zombies, items, props, level pieces | the same |
| Model colours in the pictures (after the user spotted red/green/purple zombies, green glasses, red eyes): every character and zombie, close-ups at 768 px | natural; Katey's lashes dark, the pawnshop owner's glasses grey with a light lens | natural; sunglasses dark; zombie hair brown |

After the gate (2026-10-10): `dr2 census --reimport` on both games after rigid parts
moved under their nodes: every model byte-identical (CZ 1,397, CW 1,495). Open in
Blender checked in a windowed Blender 5.2 (the background run used by the tests takes
another path: the first version imported only an Icosphere in a window).

Exports re-run into the same folder skip every file (resume). 10 of the 257 character
folders name a texture slot found nowhere in the game (`cin_zombie_james_leg_nm`, a slot
literally named `{`): the index's known unresolved slots, listed in `info.txt`.

Unit tests added: `test_catalog.py` (path globs, rules → group / sub-group / label,
unknown keys refused, the shipped rules on known assets, the index's Library, copies,
rig links by pose, scene facts and thumbnails, the count gate and a stale index, the
renderer and its lattice, export layout and name clashes, a model folder, resume,
output filters, cancel, `dr2 library` and `dr2 export`); `test_studio.py` (the Library
tab: groups, filter, a model's rig and textures, *Export all…* and a group export).

### Phase 9 results (2026-10-10)

| Gate | Case Zero | Case West |
|---|---|---|
| **Variant census** (`dr2 census --variants`): every shape of every model classified as the game does; no shape with two numbers of one slot; misplaced digits named; colour choices found; the game's list = the name rule | 43 zombie models, 2 with prop states, 1,352 without variants; 2 misplaced digits (`zombie_soldier_3`); 219 colour choices for 62 materials, all 129 listed ones given by the rule; 0 problems; 32 s | 42 zombie models; 4 misplaced digits (`zombie_security_2`/`_3`); 289 colour choices for 81 materials (CW's list is empty); 66 environment pieces with LOD/burnt-like names listed; 0 problems; 49 s |
| Profile table = the executable (`tools/variant_table.py <image> --check`) | agrees (groups at `0x829DF718`, slots at `0x8208A2E0`) | agrees (`0x829F25D0`, `0x82084AE0`) |
| Index rebuilt (schema 5, pictures of the default look) + **count gate** (`dr2 library --check`) | 230 s; 1,397 pictures; 0 problems | 356 s; 1,495 pictures; 0 problems |
| **Studio** (driven headless on the real index, screenshots looked at): pick a zombie in the Library → Variants panel; change head, hat, shirt, a colour; switch Detail | `zombie_skinny_2`: 15 of 94 parts by default; head 3 / no hat / shirt 2 / shirt1 colour 2 shown at once, the colour re-baked keeping the camera; Detail → `_3` with the same look | `zombie_gas_2`: head 2, no tumour; Detail → `_3` |
| **Blender** (`tools/blender_variants_gate.py`: Studio's own Open-in-Blender script, Blender 5.2 headless) | as shown: exactly the look's 18 parts; organised: 18 group collections, only the look's parts visible, 39 colour choices in glTF Variants, `shirt2 3` switches the shirt's material | as shown: 20 parts; organised: 28 collections, only the look visible, 14 colour choices, `cleavgshirt 2` switches |
| **Add-on** (`tools/blender_addon_gate.py`, now with a zombie) | `zombie_skinny_2` imports into 18 group collections with 79 parts hidden; a visible shirt pushed out 2 cm checks OK (the hidden parts kept) and exports; `dr2 mod check` accepts | — |
| Library pictures (contact sheet of every zombie item, both games) | one look each, no overlapping clothes | the same |
| **In game** (captured zombies draw one choice per slot) | **not done**: the capture save starts in the safehouse bathroom, with no zombie in view (a run on 2026-10-10 confirmed it); needs a save outside or a person playing | not done |

Earlier evidence for the in-game behaviour is the CZ recomp's own measurement (a live
hide mask that drew a bare-headed soldier): `tests/test_variants.py` checks that the
toolkit's rule gives exactly that soldier for that mask.

Unit tests added: `test_variants.py` (the profile table against the slots, the game's
prefix matcher, a skinny-like model's slots / default look / hide mask / mask → look, the
recomp's measured mask, look text round trip and errors, misplaced digits, props and
people not classified, prop states, the colour name rule and list parser, `.glb` extras /
left-out parts / `KHR_materials_variants`, the Library's detail levels; on game data:
one choice per slot in the default look of 7 zombies, CZ's list = the name rule, organised
and one-look exports import back byte-identical); `test_studio.py` (the Variants panel);
`test_catalog.py` (labels, detail rules).

## Writing a test for new code

- One test file per module (`tests/test_<module>.py`).
- Test the format against bytes laid out **by hand from the spec**, not only against
  your own writer (see `hand_built()` in `tests/test_big.py`), or a reader and writer
  can agree on the same mistake.
- Test failure paths: a damaged input must raise `FormatError` with a message naming
  the problem (`pytest.raises(FormatError, match=...)`). Rule 6 in `CLAUDE.md`: never
  skip silently.
- If the module reads a game format, add a game-data test or a census counter, and
  record the result in [`../formats.md`](../formats.md).

## CI

`.github/workflows/ci.yml` runs on every push:

- **tests**: Windows, Ubuntu 22.04 (x64 and arm64) and macOS 14, Python 3.11 and 3.13.
  Builds the native library first, checks `dr2 doctor` reports it, runs the unit tests,
  then reruns the LZX and archive tests with `DR2KIT_LZX=python` (fallback only).
  The built libraries are kept as artifacts.
- **pyav-codecs**: checks that PyAV's bundled ffmpeg has the XMA and Bink decoders on
  Windows, Linux, and both Mac architectures (`tools/check_pyav_codecs.py`).

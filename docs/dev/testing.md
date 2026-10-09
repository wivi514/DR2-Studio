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

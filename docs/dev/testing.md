# Testing

How the toolkit proves that it reads and writes the game's files correctly. The short
version: **we compare against something we did not write** (the original bytes, an
independent decoder, the game itself), never against the code's own idea of right.

## Three kinds of checks

| Kind | Runs where | Data | Command |
|---|---|---|---|
| **Unit tests** | everywhere, CI included (Windows, Linux x64/arm64, macOS) | tiny synthetic files built in the test | `python -m pytest -m "not gamedata"` |
| **Game-data tests** (marker `gamedata`) | your machine, if a game is installed | the real game, found through the profiles | `python -m pytest -m gamedata` |
| **Gates** (slow) | your machine, before calling a phase or format done | every entry of both games | `dr2 census --reencode --python-lzx` |

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
   `game_mods/` folder for that.

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

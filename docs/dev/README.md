# Developer guide

For people who want to **understand or change the toolkit's code**. Read
[`ARCHITECTURE.md`](../ARCHITECTURE.md) first for the big picture.

## Pages

| Page | What it covers | Status |
|---|---|---|
| [`code-tour.md`](code-tour.md) | Every package and module: what it does, which modules it calls, where to start reading | ✅ written (phase 1), kept current |
| [`setup.md`](setup.md) | Dev environment on Windows/Linux/macOS, running tests, building the native LZX library | ✅ written (phase 1) |
| [`adding-a-format.md`](adding-a-format.md) | Step by step: reader → census → `formats.md` section → writer → round-trip test → converter → GUI viewer | ✅ written (phase 1, from `.big`); refine with `.bct` in phase 2 |
| [`testing.md`](testing.md) | Unit tests on synthetic data vs census tests on real game data; the verification gates; phase results | ✅ written (phase 1) |
| `studio.md` | DR2 Studio's structure: viewers, the index, background jobs | phase 2 |
| `blender-addon.md` | The `io_dr2` add-on and how it reuses `dr2kit` | phase 6 |
| `recomp-integration.md` | The `game_mods/` layer and PCM substitution in the recomps, and how to test them | phase 2 / 5 |
| `releasing.md` | Building and packaging for each OS | phase 6 |

## How code is documented

Docs for people come in layers, and each layer has one job:

1. **Module docstring (top of every `.py`):** what the module is for, **why** it exists, and
   the key facts a reader must know before editing (e.g. "the index is little-endian but
   payloads are big-endian"). Link the `formats.md` section it implements.
2. **Public function and class docstrings:** what it takes, what it returns, what it raises,
   and a short example when the use isn't obvious. Type hints on every public signature.
3. **Inline comments:** only for *why*, never for *what*: a surprising byte order, a
   workaround, a measured fact (with where it was measured). If a comment just restates the
   code, delete it.
4. **Format knowledge lives in `formats.md`**, not scattered across comments. Code links
   to it; it links back to the module.
5. **Names are documentation.** `read_bone_record()`, not `rd52()`. Constants get names
   (`BONE_RECORD_SIZE = 52`) with a comment saying how the value is known.

Example of the expected style:

```python
"""Skeleton bone records (52 bytes each, big-endian).

Every node of a scene (model or skeleton) is stored as its own `.big` entry holding one
record. Layout and how it was verified: docs/formats.md §"Node transform record".
"""

BONE_RECORD_SIZE = 52  # verified on all 3,474 records in CZ + CW (2026-10-08)


def read_bone_record(data: bytes) -> Bone:
    """Decode one 52-byte record.

    Raises FormatError if the rotation isn't a unit quaternion, which means either
    a corrupt file or a record that isn't a bone (report it; never skip it silently).
    """
```

## Definition of done (every change)

A change is finished when **all** of these hold:

- [ ] Code has module and public-API docstrings in the style above.
- [ ] Tests cover it (synthetic data); census tests pass on both games if a format changed.
- [ ] `formats.md` is updated if any format fact changed (retractions kept, not erased).
- [ ] The user-facing guide in `docs/modding/` is written or updated if modders can now
      do something new, or do it differently.
- [ ] `glossary.md` has any new term.
- [ ] `code-tour.md` lists any new module.
- [ ] `devlog.md` has an entry; `roadmap.md` status is updated.

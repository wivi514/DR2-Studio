# Devlog

What was done, when, and **why**: newest first. One entry per work session or
milestone. Each entry links the commits, docs and guides it touched. This is the
narrative; `formats.md` and `roadmap.md` hold the current state.

Entry template:

```
## YYYY-MM-DD — short title
**Done:** what changed, in plain words.
**Why:** the problem it solves or the decision behind it.
**Learned:** anything surprising about the games or tools (and where it is now documented).
**Docs updated:** list of files.
**Next:** what this unblocks.
```

---

## 2026-10-08 — Documentation rules
**Done:** set up the documentation layout: `docs/README.md` (index), `glossary.md`, this
devlog, `modding/` (modder guides), `dev/` (contributor guides), `CONTRIBUTING.md`, and a
"Documentation rules" section in `CLAUDE.md`.
**Why:** the project must be easy to understand both for people who want to mod and
for people who want to work on the code. Documentation is part of "done" for every change.
**Docs updated:** all of the above.
**Next:** phase 1 (archive container + census).

## 2026-10-08 — Decisions: license, platforms, recomp integration
**Done:** added a free non-commercial `LICENSE` (no selling the toolkit, no selling or
paywalling mods). Committed to Windows/Linux/macOS support for PySide6 Studio. Approved a
`game_mods/` VFS layer and PCM audio substitution for both recomps (not implemented yet).
**Why:** user decisions (see `roadmap.md` §Decisions).
**Docs updated:** `LICENSE`, `README.md`, `CLAUDE.md`, `ARCHITECTURE.md` (§Platforms,
§Recomp integration), `roadmap.md`.

## 2026-10-08 — Phase 0: planning
**Done:** surveyed both games' data and the Case Zero recomp's existing tools, and wrote
`CLAUDE.md`, `ARCHITECTURE.md`, `formats.md`, `prior-art.md` and `roadmap.md`.
**Learned:**
- The 52-byte bone record layout, verified on all 3,474 bones in both games.
- Skeleton files share the model layout.
- Models list their textures by name in `MatTextureInfoArray`.
- Audio is raw XMA without a header.
- Case West adds Bink movies.
- The old community tools (Gibbed, mariokart64n's MaxScript, Chrrox) are PC- and 3ds
  Max-only, and stalled on bone palettes and on finger and face weights.

**Docs updated:** all initial docs (commit `0fa498f`).

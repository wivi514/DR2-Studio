# Troubleshooting

Problems and fixes, collected as the toolkit grows. Each guide has its own "If
something went wrong" table; this page gathers them, plus problems that don't belong to
one guide. Search the page for the error text you see.

## Getting the game data in (phase 1)

| Symptom | Cause | Fix |
|---|---|---|
| `error: Dead Rising 2: Case Zero: game data not found.` (or Case West) | The toolkit doesn't know where the game is | [`02-game-data.md`](02-game-data.md): `dr2 games set`, or `dr2 unpack` the XBLA package first. |
| `the configured folder … has no game data any more` | The folder you set was moved or deleted | `dr2 games set cz <new folder>` |
| `no 'data' folder with .big files there` | Wrong folder given to `dr2 games set` | Give the folder that **contains** `data`, or `data` itself. |
| `not an XContent package` | `dr2 unpack` was given something other than the package | Use the large file with a 42-character hex name inside `…/<TitleID>/000D0000/`. |
| `dr2: command not found` / `'dr2' is not recognized` | The toolkit's Python environment isn't active | Activate it ([`../dev/setup.md`](../dev/setup.md)) or run `python -m dr2kit …`. |
| Everything is slow; `dr2 doctor` says `LZX decoder: python (slow fallback …)` | The fast decoder library isn't built, or the OS blocked it (macOS Gatekeeper) | It still works. To speed it up, build it: [`../dev/setup.md`](../dev/setup.md). |
| `no entry named …` | A typo, or the file is inside another archive | `dr2 ls <archive>` to see exact names, or `dr2 find <part of name>`. |
| An extracted texture doesn't open as a picture | Phase 1 extracts the game's own formats | Texture conversion to PNG comes in phase 2. |

## Reporting a problem

Include the output of `dr2 doctor` and the exact command and error text. Never attach
game files.

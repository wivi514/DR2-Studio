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
| An extracted texture doesn't open as a picture | `dr2 extract` writes the game's own format by default | Add `--png` ([`04-extracting.md`](04-extracting.md)), or use **Export PNG…** in DR2 Studio. |

## Textures, the index and DR2 Studio (phase 2)

| Symptom | Cause | Fix |
|---|---|---|
| `DR2 Studio needs PySide6` | The GUI extras aren't installed | `pip install -e ".[studio]"` in the toolkit's environment. |
| DR2 Studio's tree is empty | The game isn't indexed yet | **Build / refresh index**, or `dr2 index build`. |
| `… (The index may be out of date: rebuild it.)` | Game files changed (a recomp update, another unpack) | Rebuild the index; only changed files are re-read. |
| A texture looks purple, rainbow-coloured or black-and-white | Normal map (`_nm`), specular (`_sm`), mask (`_mask`) or a font page | Normal; edit the `_cm` (colour) texture for colours. |
| `interlaced PNG; save it without interlacing, or install Pillow` | Your editor saved an interlaced ("Adam7") PNG | Save again with interlacing off, or `pip install pillow`. |

## Mods (phase 2)

| Symptom | Cause | Fix |
|---|---|---|
| `the image is WxH; this texture needs exactly …` | The PNG's size changed | Resize it back; size changes come later. Cube maps need all six faces side by side. |
| `no asset '…' in cz` | Wrong path under `replace/`, or the asset only exists in the other game | Copy the vpath from DR2 Studio; limit `games` in `mod.toml`. |
| `… is not a texture, so a PNG can't replace it` | A `.png` was placed next to something that isn't a texture | Only textures take PNGs; other assets are replaced by a file with their exact name. |
| `replaced by both a and b at the same priority` | Two mods change the same asset | Raise one mod's `priority`. |
| Mod deployed but nothing changes in game | The outfit/object on screen uses another texture, `CZ_NO_MODS`/`CW_NO_MODS` is set, or the recomp predates `game_mods/` | Check the recomp log for `served from the MODS overlay`; check which texture the model uses (`dr2 index textures-of`). |
| `warning: … the recomp's game_kbm layer also has this file` | Your mod and a recomp option layer change the same file | While the mod is installed, the mod's copy wins (keyboard prompts or the logo skip may revert for that file). |
| The game crashes or hangs after deploying | Possibly an archive the game reads at boot (`preload4.big`) rejecting a re-compressed entry; not yet proven safe | `dr2 mod undeploy -g cz`, then report it with the mod and the recomp log. Textures in model packs (`npcs.big`) are tested and work. |

## Models and Blender (phase 3)

| Symptom | Cause | Fix |
|---|---|---|
| `… is not a model or skeleton (no SceneHeader)` | `--glb` was given a texture pack, a sound bank or a folder | Give the model's `.big` (e.g. `data/models/npcs.big/boss_mechanic.big`). |
| `note: texture '…' not found` | The texture lives in an archive the model doesn't sit in | `dr2 index build` once; exports then search the whole game. |
| Studio's 3D view says it needs QtWebEngine | Your PySide6 lacks the WebEngine add-on (or `DR2_STUDIO_NO_3D` is set) | `pip install PySide6-Addons`, or use **Export .glb…** and Blender. |
| Studio's 3D view says "no WebGL here" | No GPU/OpenGL for the web view (some virtual machines, remote desktops) | Use **Export .glb…** and Blender. |
| A mesh has the wrong texture | A bug the toolkit had before 2026-10-08 (materials picked by position, not id) | Update the toolkit and export again. If it still happens, report the model's vpath. |
| In Blender, only bones and no mesh | A skeleton file (`data/skeleton/`), or `--skeleton` | Expected: export the model itself for meshes. |
| A few prop bones differ after a trip through Blender | Their rest pose has a scale, which Blender bones can't hold | Known limit (25 prop bones in both games, none on characters). |

## Reporting a problem

Include the output of `dr2 doctor` and the exact command and error text. Never attach
game files.

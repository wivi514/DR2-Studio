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

## Model replacement (phase 4)

The model check (`dr2 model check`, Studio's **Replace with .glb…**, and `dr2 mod check`
for `.glb` files in a mod) names each problem. Errors stop the build; warnings don't.

| Message or symptom | Cause | Fix |
|---|---|---|
| `object '…' matches no shape of the model` | An object whose name is not a part of this model (renamed, or new) | Name it exactly like the part it replaces (`geo_tshirtShape`); `.001` endings are ignored. New parts can't be added yet. |
| `no object of the file matches a shape of the model` | The whole file belongs to another model, or every object was renamed | Check the model you picked; see the warning `this file was exported from …`. |
| `vertices are weighted to bone '…', which the game skeleton doesn't have` | A bone you added, or a renamed bone | Move the weights to a game bone; don't rename bones. |
| `N of M vertices have no bone weight` | New vertices with no weights | Weight Paint, or **Ctrl+P → With Automatic Weights**. |
| `the material's shader is rigid …` | The part uses a material whose shader takes one bone per draw | Another material, or weight the whole part to one bone. |
| `the material's shader is skinned, but the part has no bone weights` | The mesh isn't rigged | Parent it to the armature with weights. |
| `a triangle uses nodes A..B, more than 61 apart` | One triangle weighted to bones from far-apart groups | Re-weight that area so no triangle mixes e.g. finger and face bones. |
| `… vertices; a shape holds at most 65,536` | Too many vertices in one part | Decimate. |
| `primitive mode … (only triangles …)` / `sparse accessors are not supported` | Lines/points, or shape keys in the export | Triangulate; apply or remove shape keys before export. |
| `more than 4 bone weights` (warning) | The game uses 4 per vertex | Fine as is (the 4 strongest are kept), or **Weights → Limit Total**. |
| `material '…' is not one of this model's` (warning) | New or renamed material | Use the model's own materials; the part keeps its original material otherwise. |
| `bone(s) are not where the game's skeleton has them` (warning) | Bones moved, or the armature object moved or scaled | Bone edits aren't written: undo them, keep the armature at the origin. |
| `this file was exported from …, not from …` (warning) | The `.glb` came from another model | Pick the right model. |
| `vertex-animated (run-time stream); replacing it is not supported` | The larva model animates its vertices without bones | Not replaceable yet. |

## Reporting a problem

Include the output of `dr2 doctor` and the exact command and error text. Never attach
game files.

## Model colours

| Symptom | Cause | Fix |
|---|---|---|
| A model is white or partly white in DR2 Studio or Blender (toolkit before 2026-10-09: Case West's final boss, loose props in `data/dynamicprops/`) | Its colour textures are named `_dm` or `_cm<hex>`, or its texture pack is a separate file next to it | Update the toolkit. Still white: run **Build / refresh index** (textures shared from another folder are found through the index), or the texture isn't in the game data (the log says "texture '…' not found"). |
| Zombie clothes look red, green or purple in DR2 Studio or Blender (toolkit before 2026-10-09) | Their `_cm1` texture is a weight map; the colours are shader settings | Update the toolkit and export again: these colours are now baked (`_baked` textures). To recolour such clothing, the colours are in the material's value set, not the texture (not editable by mods yet). |

## Sounds (phase 5)

| Symptom | Cause | Fix |
|---|---|---|
| `decoding XMA needs PyAV` / `replacing sounds needs PyAV` / Studio: "Install PyAV to hear sounds" | PyAV (the XMA decoder) isn't installed | `pip install av` in the toolkit's environment. |
| "No audio output device" under the waveform | Qt Multimedia can't open a sound device | **Export WAV…** and listen in another player. |
| A voice line is silent | 15 (CZ) / 20 (CW) voice entries are 0.1 s silent placeholders in the game | Expected. |
| `raw XMA packets with no stream-table record` | A sound in `data/audio/` without its `cache.big` entry (a modified game, or a new bank) | Use the shipped `data/audio/cache.big`; report it with the sound's path. |
| A sound mod does nothing; no `[xma] audio mods:` line in the recomp log | The recomp predates audio mods, `CZ_NO_AUDIO_MODS` / `CW_NO_AUDIO_MODS` / `*_NO_MODS` is set, or nothing deployed | Update the recomp, unset the variable, `dr2 mod deploy` again. Sound mods don't work on Xenia or a console. |
| The table loads but `… plays …` never appears | The game didn't play that sound in your session | Go where it plays (Studio shows its events under Related). |
| `ctxN decodes 2 channel(s) but … has 1` in the recomp log | The table and the game disagree about a sound (an old build) | Build and deploy the mod again. |
| Your song is cut short | The game plays a sound for the original's length; the build cuts yours to fit | Expected for now; pick a sound at least as long as your audio, or edit your audio to fit. |
| The game crashes when gameplay starts after editing `data/audio/Prologue.txt` | Case Zero checks that file against a fingerprint in the game | Remove the edited script from the mod; use a sound replacement ([`10-audio.md`](10-audio.md#why-not-edit-the-audio-scripts)). |

## Text, strings and the mod manager (phase 6)

| Symptom | Cause | Fix |
|---|---|---|
| Brackets show in game: `[00CC00FF,Zombrex]` | A string with markup doesn't start with `@` | Start it with `@` ([`11-text.md`](11-text.md#rules-for-a-string)). |
| `the game checks … against a digest and crashes on an edited copy` | You replaced a file the game verifies | It can't be modded; the list is in [`11-text.md`](11-text.md#files-you-cant-change). |
| A string mod made the keyboard prompts say "PRESS START" again | The recomp's keyboard layer edits `str_en.bcs` too, and the mod's bank is used instead | Known limit (deploy prints a warning). |
| `dr2 mod deploy` with no folder says "none enabled in the library" | Nothing installed or switched on | `dr2 mod list`, then `dr2 mod install` / `dr2 mod enable`, or give mod folders. |
| A mod you copied into the library doesn't deploy | Hand-copied folders start switched off | Tick it in the mod manager, or `dr2 mod enable <id>`. |
| A movie has no sound in Studio | No audio output device, or the monitor loops (they have none) | Export MP4 and play it elsewhere. |
| `Bink movies need PyAV` | PyAV not installed | `pip install av`. |

## Installing and the Blender add-on (phase 6)

See the tables in [`01-install.md`](01-install.md#if-something-went-wrong) (downloads,
AppImage, unsigned programs, game folders) and
[`13-blender-addon.md`](13-blender-addon.md#if-something-went-wrong) ("Toolkit not
found", no index, rig check failures).

## Texturing programs and limits (phase 7)

See the tables in [`14-texturing-tools.md`](14-texturing-tools.md#if-something-went-wrong)
(texture sets not found, wrong shape, normal maps lit the wrong way, transparency) and
the limits in [`15-limits.md`](15-limits.md) (vertices, bones, weights, UVs, sizes).

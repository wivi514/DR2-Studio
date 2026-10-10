# Limits: what Dead Rising 2 (and the toolkit) can take

**You will:** know the limits to respect before you model, rig, texture or record, so
your mod goes in the first time.   **Time:** ~5 min to read.   **Games:** both.
**You need:** nothing; keep this page open while you work.

Two kinds of limits: the **game's** (what its files and shaders can hold; going over
them can't work) and the **toolkit's v1 rules** (what this version can rebuild; later
versions may lift them). Every number below was measured on the games' own files
([`../formats.md`](../formats.md) §Engine limits).

## Models and rigs

| Limit | Value | Kind | What happens if you go over |
|---|---|---|---|
| Vertices in one part (shape) | **65,536** | game (16-bit indices into the part's vertex buffer) | `dr2 model check` refuses the part. Reduce it (Blender: *Decimate*); splitting into more objects of the same part doesn't help, they share the buffer. The game's own parts stay under 8,000. |
| Bones one draw can use | **61**, and they must be a run of consecutive skeleton nodes | game (shader) | The toolkit splits a part into several draws by itself; nothing to do. |
| Bone weights per vertex | **4** | game | The 4 strongest are kept and renormalised (the check warns). In Blender: *Weights → Limit Total* = 4. |
| Bones that exist | the model's own skeleton (98 for characters) | game + v1 | Weights on a bone the model doesn't have are refused. Use the game's rig ([`09-new-model.md`](09-new-model.md)). |
| New parts, materials or bones | not possible yet | v1 | A `.glb` object replaces the game part with the same name; extra objects are reported and ignored. |
| How big a character can be | the game's own: up to ~18,600 vertices for a whole character (the mechanic boss), 1,000-8,000 per part | measured, not a hard limit | Larger may work; memory and frame rate in game are untested. Stay near these numbers. |

## UVs

| Limit | Value | Kind |
|---|---|---|
| UV tiles | **one tile, 0 to 1** for characters (every character part but two hats); environments repeat | game practice; texturing programs: UDIM **off** |
| UV set 0 (the one textures use) | any range, full precision | game |
| Extra UV sets (lightmaps, detail) | some are stored as −1…1 numbers | game: the importer keeps the original's format |

## Textures

| Limit | Value | Kind |
|---|---|---|
| Size | **the same as the texture you replace** (export bigger: the import resizes; same shape needed) | v1 |
| Largest in the games | 2048×2048 | game |
| Formats | DXT1 (no or on/off alpha), DXT5 (smooth alpha), DXN (normal maps), uncompressed for a few | game; a replacement keeps the original's format |
| Transparency | only on textures that already have it, and only hair (and lashes) use it as see-through. On clothes and skin a DXT5 colour map's alpha is a mask, not transparency: **keep the original alpha** when you repaint them ([`../formats.md`](../formats.md) §Texture conventions) | game + v1 |
| Normal maps | OpenGL-style (green up) | game ([`14-texturing-tools.md`](14-texturing-tools.md)) |
| Maps that exist | colour, normal, specular (+ masks, lighting maps); **no** roughness, metallic, height | game |
| Edges | DXT stores 4×4-pixel blocks with 4 colours each: sharp small details and smooth gradients band a little | game |

## Sounds, text, other files

| Limit | Value | Kind |
|---|---|---|
| Sound length | **the original's**: longer audio is cut, shorter is padded with silence | game decides; v1 |
| Sound format | any WAV/OGG/FLAC/MP3; fitted to the sound's channels and rate | toolkit |
| Sounds outside a recomp | not possible (no XMA encoder): recomps only | toolkit |
| Movies (Case West) | can't be replaced (no Bink encoder) | toolkit |
| Strings | change any; new ids only below the last; markup needs a leading `@`; keep `%s`/`%d` | game ([`11-text.md`](11-text.md)) |
| Locked files | `Prologue.txt` (CZ) and six files in CW: the game checks them and crashes on a change | game ([`11-text.md`](11-text.md#files-you-cant-change)) |

## Check it worked

- `dr2 model check <your.glb> <model>` (or **Check rig** in Blender's DR2 tab, or the
  check Studio runs when you add a `.glb`) says `OK`.
- **Import textures…** lists no "skipped" file you meant to use.

## Going further

- The measurements and how they were made: [`../formats.md`](../formats.md) §Engine
  limits, §Texture conventions.
- Troubleshooting by symptom: [`12-troubleshooting.md`](12-troubleshooting.md).

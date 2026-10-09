# Prior art: existing Dead Rising 2 modding tools

Surveyed 2026-10-08. Almost everything targets the **PC** releases of Dead Rising 2 and
Off the Record (OTR), dates from about 2010-2013, is closed-source Windows software, and
is spread across forum posts and dead MediaFire/SkyDrive links. **Nothing supports
Blender, nothing previews audio, and none of it is a single browser.** That gap is what
this project fills.

## Hubs

- **DEAD RISING Forum (ProBoards)**, the main community:
  [Tools & Tutorials board](https://deadrising2mods.proboards.com/board/97/dead-rising-2-tools-tutorials)
- **Dead Rising Wiki "Mod:" pages**:
  [Import Models](https://deadrising.fandom.com/wiki/Mod:Import_Models),
  [Model Swap](https://deadrising.fandom.com/wiki/Mod:Model_Swap),
  [Create Reskins](https://deadrising.fandom.com/wiki/Mod:Create_Reskins),
  [Gibbed tool](https://deadrising.fandom.com/wiki/Mod:Gibbed_tool_for_opening_and_recompiling_files),
  [Collision](https://deadrising.fandom.com/wiki/Mod:Collision)
- ResHax (successor to XeNTaX/ZenHAX) has 3D-model research threads, including at least
  one about Case Zero on 360. Worth a manual look; it did not show up in search.

## Tools

| Tool | Author | What it does | Lessons for us |
|---|---|---|---|
| **Gibbed.DeadRising2.Tools** (Unpack/Pack, rev 11) — [thread](https://deadrising2mods.proboards.com/thread/3045/rising-unpacker-repacker-gibbed-tools), [older thread](https://deadrising2mods.proboards.com/thread/21/tools-extract-big-rebuild-gibbed) | Rick "gibbed" | `.big` extract/rebuild for PC. The community's standard tool. | Source not on gibbed's GitHub. Our container code comes from the CZ recomp, verified on 360 data. |
| **MaxScript Model Importer/Exporter** — [thread](https://deadrising2mods.proboards.com/thread/1035/maxscript-model-exporter) | mariokart64n | 3ds Max: import NPC models with skeleton, weights and UVs; export vertex edits or all-new geometry; pack/unpack `.big`/`.tex`. Supports OTR (360 and PC) and DR2. | Proves the model format can be written back. **Limits we must beat:** only `npcs.big` models, broken finger and face weights, no new materials. *Phase 4:* any model (own or shared buffers), finger and face weights checked in game (`formats.md` §In-game check (phase 4)); new materials still to come. Records compression flags 0 = stored, 1 = zlib, 2 = XMem (LZX), and that 360 textures are tiled. |
| **Dead Rising 2.ms + Dr2TextureConvert.bms** — [thread](https://deadrising2mods.proboards.com/thread/354/dead-rising-npcs-model-converter?page=2) | Chrrox | Max import script and a QuickBMS texture converter. | Chrrox: "the model format is very easy except for one thing, how the bone palette works." **The bone palette is the known hard part;** plan for it explicitly (roadmap phase 3). *Solved in phase 3:* each draw's palette is a run of consecutive skeleton nodes named in its `RenderStrip` record, verified against the running game (`formats.md` §Skinning). |
| **Geo → OBJ converter** — [same thread](https://deadrising2mods.proboards.com/thread/354/dead-rising-npcs-model-converter?page=2) | bluearms | Dumps `geo_*Shape Vertices` streams to OBJ (no skin). | The PC build names vertex chunks per shape. *Phase 3:* the 360 builds use both: characters keep per-shape `geo_*Shape Vertices N` buffers, props and levels share `Combined Vertices <stride>` ones. |
| **Model import workflow** — [thread](https://deadrising2mods.proboards.com/thread/1590/model-imports-dr2) | community | Rig in Max against an OTR model, export into the DR2 model's `persistent.big`, repack `npcs.big`. | DR2 and OTR skeletons differ and swapping them crashes the game. Geometry names must match what the target expects (no `…deformed` pieces where the target has none). Our rig check must catch both before build. *Phase 4:* `dr2 model check` refuses bones the target skeleton lacks and parts whose names match no shape of the target. |
| **TexMod / WTV** — [Using TexMod](https://deadrising2mods.proboards.com/thread/172/using-texmod), [direct skins](https://deadrising2mods.proboards.com/thread/4/create-direct-skins-texmod-outdated) | — | Runtime texture injection on PC; Woody's Texture Viewer to identify DXT formats. | Users wanted "what texture is this" **in game**. The recomp could offer this natively (F9 census to texture vpath). |
| **Music swap** — [thread](https://deadrising2mods.proboards.com/thread/398/swap-game-music) | — | Edit the audio `.txt` scene scripts to point an event at another asset. | Script-level audio remapping needs no encoder. Offer it as the easy path next to true audio replacement. |
| **BIK movies** — [thread](https://deadrising2mods.proboards.com/thread/589/bik-movies-work-easily) | — | Swap `.bik` files directly (PC). | Applies to Case West, which ships Bink. |
| **DR2 Weapon Creator**, **Greene Menu** trainer | — | Combo-weapon data editing; internal trainer. | Out of scope for now. The weapon creator shows how much the community wants data editing (`datafile.big` text). |
| **Blender** — [thread](https://deadrising2mods.proboards.com/thread/288) | — | Requests for a Blender import/export script. **None was ever made.** | That gap is our main deliverable. |

## Adjacent, but not for this engine

- [RE Mesh Editor](https://github.com/NSACloud/RE-Mesh-Editor) (Blender, RE Engine) is
  used for **Dead Rising Deluxe Remaster**, a different engine. Still a good UX
  reference for a game-specific Blender add-on: a rig/mesh validation panel, drag-and-drop
  import, export straight into a mod folder.
- Noesis has no known DR2 plugin.
- vgmstream: no known DR2-specific parser. Our XMA path follows the recomp's ffmpeg
  setup instead.

## Takeaways

1. The `.big` and texture side is easy and known. The **community never solved bone
   palettes, finger and face weights, or adding materials**. Budget phase 3 for that.
2. Mod distribution used to mean "replace the whole `npcs.big`". Users shared huge
   archives that conflicted with each other. Our mod format ships small source files and
   builds per install, which is the main usability gain besides Blender.
3. Keep PC compatibility in mind (byte order, tiling, zlib), because the old PC
   community's knowledge and files could then carry over.

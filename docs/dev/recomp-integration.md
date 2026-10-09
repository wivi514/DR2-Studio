# Recomp integration: the `game_mods/` layer and audio substitution

How the two recomps load mods built by this toolkit, and how to test that they do.
Decision and design: [`../ARCHITECTURE.md`](../ARCHITECTURE.md) §Recomp integration.
Two runtime changes, both approved: the `game_mods/` file layer (phase 2, below) and
[PCM audio substitution](#audio-substitution) (phase 5). The capture procedures used as
in-game gates (phases 3 to 5) are at the end.

## What the runtime does

Both recomps resolve every file the game opens through one function,
`VfsResolveExisting()` in `runtime/kernel/vfs.cpp`. It already checked overlay folders
next to the game folder (`assets/game`) before the shipped file:

```
assets/game_bootskip/   CZ only: fecmn.big with the intro logos skipped (launcher toggle)
assets/game_kbm/        keyboard-prompt glyphs (on while the native keyboard is used)
assets/game_patched/    the recomp's own patches: PC options menu, string banks, ...
assets/game/            the shipped data
```

Phase 2 added **`assets/game_mods/`, checked first**. For each path the game opens
(e.g. `game:\data\models\npcs.big`):

1. If `CZ_NO_MODS` / `CW_NO_MODS` is set, skip the layer entirely.
2. If `assets/game_mods/` exists and holds the same relative path (exact case first,
   then case-insensitively), serve that file and log
   `VFS: 'game:\data\models\npcs.big' served from the MODS overlay -> … (CZ_NO_MODS=1 turns mods off)`.
3. Otherwise fall through to the existing layers, unchanged.

The result is cached per path, like every other answer of the resolver, so the layer
costs one directory check per distinct file opened.

**The runtime only swaps whole files.** All format work (nested archives, LZX, tiling)
happens in the toolkit at build time (`dr2kit/mods/build.py`). That keeps the C++ change
to ~40 lines per recomp and puts every format rule in one place.

### Why first, and the conflict rule

A mod is something a player chose to install, so it wins. Two consequences, both handled
by the toolkit rather than the runtime:

- **`game_patched` files.** If a mod touches a file the recomp has patched (e.g.
  `datafile.big`, `frontend/fecmn.big`), serving the mod's copy would drop the recomp's
  patch. So `dr2 mod deploy` builds the mod **on top of `game_patched`'s copy** when one
  exists (`--base`, on by default for a recomp; `--no-patched-base` to opt out).
- **Toggle layers** (`game_kbm`, `game_bootskip`) are switched at run time, so the
  toolkit can't know which copy to build on. If a mod carries one of their files,
  deploy prints a warning: while the mod is installed, its copy is used.

## Where it lives

| | Case Zero | Case West |
|---|---|---|
| Code | `runtime/kernel/vfs.cpp`, block "THE MODS OVERLAY" before the boot-skip overlay | same file, before the keyboard-prompt overlay |
| Off switch | `CZ_NO_MODS=1` | `CW_NO_MODS=1` |
| Docs | `docs/instruments.md` (mods overlay section), `docs/gotchas.md` #634 | `docs/gotchas.md` #330 |

Both recomps follow their own CLAUDE.md conventions: an off switch, a log line per
served file, a gotcha entry. `CZ_NO_PATCHED_ASSETS` / `CW_NO_PATCHED_ASSETS` do **not**
turn mods off, so each layer can be A/B-tested alone.

## Testing it (the phase 2 in-game gate)

The gate: a recoloured texture inside a **compressed** `.tex` shows up in both recomps,
and disappears with the off switch. Being inside a compressed entry, it also proves the
game accepts the toolkit's LZX encoder's output (nothing had shown that before).

Headless, with the recomp's own instruments (no window, scripted button presses, a PPM
of every 64th frame). Use a **copy of the save folder** (`CZ_SAVE_DIR`), because the
scripted presses play the game:

```
dr2 mod deploy my_mod -g cz
cp -r <recomp>/assets/save /tmp/save_copy
cd <recomp>/runtime/build
CZ_SAVE_DIR=/tmp/save_copy CZ_NO_WINDOW=1 CZ_VKDRAW=1 CZ_VK_FRAME_DUMP=/tmp/on \
  CZ_FAKE_START_MS=8000 CZ_FAKE_PRESS_SEQ=START,A,A timeout 170 ./cz_runtime > on.log 2>&1
CZ_NO_MODS=1 CZ_SAVE_DIR=/tmp/save_copy CZ_NO_WINDOW=1 CZ_VKDRAW=1 CZ_VK_FRAME_DUMP=/tmp/off \
  CZ_FAKE_START_MS=8000 CZ_FAKE_PRESS_SEQ=START,A,A timeout 170 ./cz_runtime > off.log 2>&1
grep "MODS overlay" on.log off.log        # one line per modded file in on.log, none in off.log
dr2 mod undeploy -g cz                    # leave the recomp as it was
```

Case West: the same with `CW_` names and `./cw_runtime`.

`START,A,A` walks title → menu → *Continue*, so the run loads the latest save: the
texture you test must be on screen in it. With the save used on 2026-10-08, Case Zero's
Chuck wears his default orange "04" shirt (`npcs.big/chest_young_chuck.tex/young_cr_shirt_cm`),
and Case West's Chuck his default jacket (`npcs.big/chest_default.tex/cr_jacket_cm`).
`dr2 index textures-of data/models/npcs.big/chest_young_chuck.big` is how the shirt
texture was found.

### Results (2026-10-08)

See [`../devlog.md`](../devlog.md) (phase 2 entry) and [`testing.md`](testing.md)
§Phase 2 results for the frames and log lines of each run.

## Audio substitution

The second approved runtime change (phase 5). It lets a mod replace any sound with
audio the player has, although nobody can make XMA (the encoder is in the Xbox 360 SDK
and can't be redistributed).

### The idea

The recomps decode XMA on the host: `XmaDecodeOnePacket` in `runtime/kernel/audio.cpp`
hands one 2 KB packet at a time to ffmpeg (one decoder per hardware context, i.e. per
XMA stream) and copies the PCM into the context's output ring, which the game's mixer
reads. Substitution changes **only that PCM**: after each decode call, if the packet
belongs to a replaced sound, the samples it produced are overwritten with the mod's
samples for the same positions. Buffers, read offsets, sample counts, loop handling and
timing are untouched, so the game cannot tell.

### Recognising a packet: fingerprints with positions

The hard part was named in `ARCHITECTURE.md`: mapping a guest XMA buffer back to the
`.big` entry it came from. Tracking file reads through the VFS would mean following
data through the game's own streaming buffers (music is streamed through re-armed
128 KB buffers; sound banks are loaded whole and copied). Instead, **each packet
identifies itself**: `dr2 mod build` lists every packet of every replaced stream by its
64-bit FNV-1a hash, with the decoded-sample position where that packet's output begins.
The positions come from decoding the stream packet by packet with the same ffmpeg
decoder (`dr2kit.convert.audio.stream_packets`), which gives the same samples as a
whole-file decode (`formats.md` §Decoding packet by packet).

So the runtime needs no state to know where it is. Loops (the hardware rewinds to packet
0), streaming through new buffers, a context reused for another sound, a sound started
part-way: each packet still says which samples it stands for.

**Collisions.** If some other sound of the game contains an identical packet, that
packet must not start a substitution. The build compares every listed packet with every
packet of every other sound of the game (a few seconds) and marks those *continue
only* (`c`): they are used only when the context is already playing that replaced
stream and expects exactly that position. Measured: stream-first packets are unique
except the identical silent placeholders and one twin sound.

### What the build writes (deployed into `game_mods/`)

```
game_mods/dr2kit_audio/substitutions.txt
game_mods/dr2kit_audio/<12 hex of the vpath's SHA-1>_<stream>.wav   (one per stream)
```

```
# dr2kit audio substitutions v1. …
sound 0 2 5375744 a192bdc62c86_0.wav  # data/audio/music.big/PressStartPrologue.xma stream 0
0c83e7a2cb3cbc68 0 0 u
da3cf14964d8899b 0 960 u
da4986c2ae7f7d9b 0 6080 u
…
```

- `sound <n> <channels> <samples> <file>`: replaced stream *n*. The WAV is 16-bit PCM
  with the stream's channels (1 or 2; a 5.1 sound is three stereo streams), at the
  sound's rate, exactly `samples` long: the build cuts or pads the modder's audio to the
  original's decoded length, because the game decides how long a sound plays.
- `<fnv1a64> <n> <start> <u|c>`: one packet of stream *n*; its output begins at decoded
  sample `start`. `u` may start a substitution, `c` only continues one.

### The runtime (both recomps, `runtime/kernel/audio.cpp`)

| Piece | What it does |
|---|---|
| `XmaSubstLoad()` | Called once when the decode thread starts. Reads `<game root>_mods/dr2kit_audio/substitutions.txt` (the root from `VfsTranslate("game:")`) and every WAV it names (16-bit PCM only; a file that doesn't load is logged and that sound plays unmodded). Logs `[xma] audio mods: N sound stream(s), M packets from …`. Does nothing when the file is absent. |
| `XmaSubstApply()` | Called after every successful decode call with the PCM it appended. Hashes the packet; picks the table entry that continues the context's current stream at the expected position, else the first `u` entry; overwrites the new samples with the replacement's (zeros past its end). A channel-count mismatch is logged and skipped. Logs each (re)start (`ctx0 plays … from sample 0 (start #1)`, the first three, then every 100th). |
| `XmaHostCtx` | Three new fields: the stream being substituted (-1: none), the position expected next, a packet counter. Reset when the decoder is re-created or the context released. |

Commits: CZ `54b5283` (master), CW `dea8734` (xlive-integration).
Off switches: `CZ_NO_AUDIO_MODS=1` / `CW_NO_AUDIO_MODS=1` (the table is never read), and
`CZ_NO_MODS=1` / `CW_NO_MODS=1` turn audio mods off together with the file layer. Docs
in the recomps: CZ `docs/gotchas.md` #635 and `docs/instruments.md` (audio mods
section); CW `docs/gotchas.md` #331. Cost: one FNV-1a over 2 KB per decoded packet when
a table is loaded (about 25 packets a second per playing voice), nothing otherwise.

### Testing it (the phase 5 in-game gate)

The gate: one music swap is audible. The title-screen music plays without any input, so
a 90 s headless boot is enough. SDL's **`disk` audio driver** writes what the game sends
to the speakers into a file (raw 32-bit float stereo at 48 kHz), so the test makes no
sound and leaves a recording to compare and to listen to:

```
dr2 extract --wav data/audio/music.big/HB_Indemnify.xma -o work
dr2 mod new swap --id title_swap                       # games = ["cz"] in mod.toml
mkdir -p swap/replace/data/audio/music.big
cp work/data/audio/music.big/HB_Indemnify.xma.wav \
   swap/replace/data/audio/music.big/PressStartPrologue.xma.wav
dr2 mod deploy swap -g cz
pgrep -x cz_runtime                                    # nothing else running
cp -r <recomp>/assets/save /tmp/save_copy
cd <recomp>/runtime/build
CZ_BUG_REPORTS=0 CZ_SAVE_DIR=/tmp/save_copy CZ_NO_WINDOW=1 CZ_VKDRAW=1 \
  SDL_AUDIODRIVER=disk SDL_DISKAUDIOFILE=/tmp/on.raw timeout -s KILL 90 ./cz_runtime > on.log 2>&1
CZ_NO_AUDIO_MODS=1 CZ_BUG_REPORTS=0 … SDL_DISKAUDIOFILE=/tmp/off.raw … ./cz_runtime > off.log 2>&1
grep "audio mods" on.log off.log        # "plays … from sample 0" in on.log; nothing in off.log
dr2 mod undeploy -g cz                  # then remove the empty assets/game_mods/
```

Then compare each recording with the decoded tracks (normalised cross-correlation of
1 s windows: the recording should follow the replacement at the right positions with
the mod, the original without). Case West: the same with `CW_` names, `./cw_runtime`
and `PressStartDR2.xma`. Use `timeout -s KILL`: one Case West run ignored SIGTERM at
exit (with substitution off, so unrelated). Set both `SDL_AUDIODRIVER` and
`SDL_AUDIO_DRIVER` (and `SDL_DISKAUDIOFILE` / `SDL_AUDIO_DISK_OUTPUT_FILE`) if the
system's SDL2 is sdl2-compat over SDL3. Results: `formats.md` §In-game check (phase 5).

### Script-level remapping does not work (Case Zero, checked)

Pointing an event at another sound by editing the audio scene script needs no runtime
change, but Case Zero verifies `data/audio/Prologue.txt` against a SHA-1 digest built
into the executable. Checked in game (2026-10-09): an edited copy deployed through
`game_mods/` is served, the digest check runs on it (`CZ_DIGEST_PROBE=1` prints
`[digest] verify 'data/audio/Prologue.txt' …`), and the game crashes at once (`guest
fault: signal 11`). Getting past that would mean changing the executable's digest
table, which is not one of the approved integration changes. Use a substitution with
the other sound's audio instead (`dr2 extract --wav` it, put it under `replace/`).

## Phase 3: capturing draws to check the model reader

The CZ recomp can dump, for one captured frame, every draw made with a given vertex
shader: the shader constants (camera, bone matrices), the raw vertex stream and the
indices (`CZ_CAPTURE_DUMP_VS`, CZ `docs/instruments.md`). `tools/capture_gate.py` matches
those draws with the game data and checks the reader (`formats.md` §In-game check).

```
cp -r <recomp>/assets/save /tmp/save_copy                  # the presses play the game
cd <recomp>/runtime/build
SEQ=START,A,A,A,A,A,NONE,NONE,NONE,NONE,NONE,NONE,NONE,NONE,NONE,NONE,NONE,NONE,NONE,NONE,F9,NONE,NONE,NONE
# 1. a capture to find the shader: the census lists every draw with its vs= hash
CZ_BUG_REPORTS=0 CZ_SAVE_DIR=/tmp/save_copy CZ_NO_WINDOW=1 CZ_VKDRAW=1 CZ_CAPTURE_KEY=/tmp/cap \
  CZ_FAKE_START_MS=8000 CZ_FAKE_PRESS_SEQ=$SEQ timeout 240 ./cz_runtime > cap.log 2>&1
grep -E "verts=(2785|447) " /tmp/cap/capture_f*.census   # Chuck's T-shirt / shirt bottom
# 2. the same with the dump armed for that hash (2026-10-08: c3d6d30111313392, main pass)
CZ_BUG_REPORTS=0 … CZ_CAPTURE_DUMP_VS=c3d6d30111313392 CZ_CAPTURE_KEY=/tmp/cap2 … ./cz_runtime
python tools/capture_gate.py /tmp/cap2 --overlay overlay.png
```

Things learned running it:

- **`CZ_BUG_REPORTS=0` is required.** F9 (scripted or not) also writes a bug-report
  capture into the XenonLive launcher's folder (`~/.config/XenonLive/captures/`), which
  is capped at 256 MB / 40 captures **by deleting the oldest one**. The first phase 3
  run did exactly that to one of the user's existing captures before this was known.
- `START,A,A` with a quiet sequence afterwards stops on the title menu; the extra `A`s
  get through *Continue*. F9 at ~170 s lands in play with this save.
- Don't add `CZ_VK_FRAME_DUMP` to a capture run: the frame dumps filled the temporary
  folder's quota within seconds. Delete the `*_snap_*.ppm` files after a capture; only
  the census, the `vsdump_*.bin` files and `capture_*.ppm` are needed.
- The dumped constants are taken **before** the recomp's widescreen patch. To project
  onto the captured picture, multiply projection row 1 by k = 9W/16H and use the whole
  width (the recomp widens the game's field of view, then narrows it back in the
  renderer; CZ `vk_renderer.cpp`, `WideFovFactor`).
- A second set of the same draws appears (two passes); the shadow passes use other vertex
  shaders (`eae0f9b607fcbe92` in that frame).

## Phase 4: checking a replaced model in game

The gate: a model rebuilt from a `.glb` that went through Blender loads, an edited part
shows its edit, and a new rigged mesh follows the bones, fingers and face included. The
same capture as phase 3, with the models read from the mod instead of the game:

```
dr2 extract --glb data/models/npcs.big/chest_young_chuck.big -o work
blender -b --factory-startup --python tools/blender_gate_model.py -- \
    work/data/models/npcs.big/chest_young_chuck.big.glb gate.glb
dr2 mod new gate_mod --id phase4_gate                      # games = ["cz"] in mod.toml
mkdir -p gate_mod/replace/data/models/npcs.big
cp gate.glb gate_mod/replace/data/models/npcs.big/chest_young_chuck.big.glb
dr2 mod check gate_mod -g cz && dr2 mod deploy gate_mod -g cz
cp -r <recomp>/assets/save /tmp/save_copy
cd <recomp>/runtime/build
CZ_BUG_REPORTS=0 CZ_SAVE_DIR=/tmp/save_copy CZ_NO_WINDOW=1 CZ_VKDRAW=1 CZ_CAPTURE_KEY=/tmp/cap \
  CZ_CAPTURE_DUMP_VS=c3d6d30111313392 CZ_FAKE_START_MS=8000 CZ_FAKE_PRESS_SEQ=$SEQ \
  timeout 240 ./cz_runtime > cap.log 2>&1                  # $SEQ as in phase 3
rm /tmp/cap/*_snap_*.ppm
python tools/capture_gate.py /tmp/cap --root <recomp>/assets/game_mods --overlay overlay.png
# the same run with CZ_NO_MODS=1 for a side-by-side picture
dr2 mod undeploy -g cz                                    # then remove the empty game_mods/
```

`--root` makes the gate look for the dumped draws in the mod's files, so "same bytes"
proves the game drew the replacement. A draw that starts past vertex 0 of its stream
(the second draw of a split mesh) is matched at its offset in the dumped stream.

Learned running it (2026-10-08):

- The shader hash `c3d6d30111313392` (main pass) also covers the arms' skin shader in
  that frame: 32 dumps, two passes of 16 draws.
- `npcs.big` with one model replaced builds in about a second (only that entry is
  re-compressed); the recomp logs `served from the MODS overlay` once.
- Pose differs a little between two runs (timing), so compare pictures by eye, not by
  pixel difference.

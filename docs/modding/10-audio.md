# Replace music, voices and sound effects

**You will:** listen to the game's sounds, save them as WAV, and make a mod that plays
your own audio in place of one of them (the title-screen music in the example).
**Time:** ~10 min.   **Games:** both (the example uses Case Zero).
**You need:** the toolkit set up and pointed at your game
([`02-game-data.md`](02-game-data.md)) with **PyAV** installed (`pip install av`; DR2
Studio's install includes it), your replacement audio as WAV, OGG, FLAC or MP3, and a
Case Zero or Case West **recomp** to hear it in game.

The games store every sound as **XMA**, the Xbox 360's own audio format
([glossary](../glossary.md#xma)). The toolkit can turn XMA into WAV, but nobody can turn
WAV back into XMA without Microsoft's Xbox 360 SDK. So a sound mod doesn't change the
game files: it gives the **recomp** your audio, and the recomp plays it at the moment the
game plays the original ([how](../dev/recomp-integration.md#audio-substitution)).
That is also why sound mods work in the recomps only, not on Xenia or a console.

## Steps

### In DR2 Studio

1. Start DR2 Studio (`dr2 studio`). If you indexed the game before this version, click
   **Build / refresh index** once: sounds and their names are new in the index.
2. Pick the game (Case Zero), click the **Search** tab, choose **audio** in the kind box
   and type `PressStart`. Click `data/audio/music.big/PressStartPrologue.xma`, the
   title-screen music.
3. The middle shows the waveform (one lane per channel: L and R here). Click **Play** to
   listen, click anywhere on the waveform to jump there, **Stop** to stop. A shaded area
   is the part the game loops; tick **Loop** to hear it repeat.
   The right panel says what it is (stereo, 48000 Hz) and, under **Related**, which game
   events play it. For sound effects, the related list shows the `.sfx` that use the
   recording; double-click one to see its event names.
4. To keep a copy, click **Export WAV…**.
5. Click **New mod…** at the bottom and give it a name, e.g. `Title music` (Studio keeps
   it in your mod library). (Or **Open mod…** for an existing mod folder.)
6. With the sound still selected, click **Replace with audio…** and pick your file
   (WAV, OGG, FLAC or MP3). The mod's file list shows
   `data/audio/music.big/PressStartPrologue.xma.wav` (or `.ogg`…).
7. Click **▶ Play**. The log says what the build did to fit your audio, e.g.
   `cut from 180.00 s to the original's 112.00 s`, and where it went (the recomp's
   `assets/game_mods/dr2kit_audio/`).
8. Start the recomp. The title screen plays your music.

### With the `dr2` command

```
dr2 info data/audio/music.big/PressStartPrologue.xma          # stereo, 48000 Hz, 112 s
dr2 extract --wav data/audio/music.big/PressStartPrologue.xma -o sounds   # listen to it
dr2 mod new title_music
mkdir -p title_music/replace/data/audio/music.big
cp my_song.ogg title_music/replace/data/audio/music.big/PressStartPrologue.xma.ogg
dr2 mod check title_music -g cz      # "audio  data/audio/music.big/PressStartPrologue.xma"
dr2 mod deploy title_music -g cz
```

The file name under `replace/` is the sound's **virtual path** (ending in `.xma`) plus
your file's own extension. `dr2 extract --wav` works on whole banks too
(`dr2 extract --wav -r data/audio/music.big -o sounds`).

To find a sound: search names in Studio or with `dr2 index search --kind audio <words>`;
sound effects are easiest found through their `.sfx` (`--kind sfx`), whose name is
what the game calls the sound (`FEError.sfx` → the "error" beep, which plays
`cursorError43a_01a.xma`). [`asset-catalogue.md`](asset-catalogue.md#sounds) lists where
each kind of sound lives.

## What your audio becomes

The game decides how long a sound plays and how it is mixed; your audio is fitted to
the original:

- **Length:** cut, or padded with silence, to exactly the original's length. A longer
  song stops where the original would have ended; a looping original loops your audio
  over the same span. (Making a sound longer than the original isn't possible yet.)
- **Channels:** converted to the original's: mono effects and voices, stereo music,
  5.1 cutscene sound (stereo becomes the front pair of a 5.1 sound).
- **Rate:** converted to the original's (48000 Hz, give or take a few).
- Volume, 3D position, reverb: the game applies its own, as for the original.

The build prints a note for each of these it had to do.

## Check it worked

- You hear your audio where the original played.
- The recomp's log has `[xma] audio mods: 1 sound stream(s), … packets from …` when it
  starts, and `[xma] audio mods: ctx0 plays <file> from sample 0` when the sound plays.
- Compare with the original: start the recomp with `CZ_NO_AUDIO_MODS=1` (Case West:
  `CW_NO_AUDIO_MODS=1`). `CZ_NO_MODS=1` turns off all mods, sounds included.
- Undo: **Remove mods from game** in Studio, or `dr2 mod undeploy -g cz`.

## Why not edit the audio scripts?

The PC version of Dead Rising 2 could swap music by editing the audio scene scripts
(`data/audio/Prologue.txt`: `Asset = "music.big/…"`). **Don't do that in Case Zero:**
the game checks that file against a fingerprint stored in the game itself and crashes on
an edited copy (checked in the recomp). Case West has the same check; which of its files
it covers isn't known, so don't edit its scripts either. To make an event play a
different track of the game, use a replacement made from that track: `Export WAV…` (or
`dr2 extract --wav`) the track you want, and use that file in **Replace with audio…**.

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| `replacing sounds needs PyAV` / `decoding XMA needs PyAV` | PyAV isn't installed | `pip install av` in the toolkit's environment. |
| Studio says "Install PyAV to hear sounds" | Same | Same. |
| "No audio output device" under the waveform | Qt can't open a sound device | The waveform still works; **Export WAV…** and listen in another player. |
| `…: not an audio file ffmpeg can read` | The file is damaged, or not audio | Open it in an audio player; save it again as WAV. |
| `no asset '…' in cz` | The path under `replace/` doesn't name a sound | Copy the sound's path from Studio; keep the `.xma` before your extension (`X.xma.wav`). |
| Nothing changes in game, no `audio mods` line in the log | The recomp predates audio mods, or `CZ_NO_AUDIO_MODS` / `CZ_NO_MODS` is set, or the mod isn't deployed | Update the recomp; unset the variable; deploy again. |
| `audio mods: … loaded … plays …` never appears, though the table loaded | The game didn't play that sound in your session | Check the sound's **Related** events in Studio; try the place where it plays. |
| `note: …: N of M packets also occur in other sounds` | Parts of the original are identical to parts of another sound | Harmless: those parts only continue your audio once it started. |
| `note: … starts the same way, so the recomp will play the replacement for it too` | Another sound is a copy of the same recording (common for silent placeholders) | Both will play your audio. |
| `every packet also occurs in other sounds, so the recomp can't recognise it` | The sound is identical to another one (e.g. a silent placeholder) | Replace the other one, or both; they're the same sound. |
| The game crashed after editing `Prologue.txt` | The script is checked by the game | Remove it from `replace/`; see [above](#why-not-edit-the-audio-scripts). |

More in [`12-troubleshooting.md`](12-troubleshooting.md#sounds-phase-5).

## Going further

- Voice lines (`data/audio/charvocals.big`, `chuck.big`) are numbered, not named: the
  game's dialogue tables only use numbers. Listen in Studio to find the one you want.
- What a mod folder holds, several mods at once: [`06-mod-packages.md`](06-mod-packages.md).
- How sounds are stored, lengths, the stream tables: [`../formats.md`](../formats.md) §Audio.
- How the recomp plays your audio: [`../dev/recomp-integration.md`](../dev/recomp-integration.md#audio-substitution).

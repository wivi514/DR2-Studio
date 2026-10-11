# Find things by what they are, and export them all at once

**You will:** find a character, a sound or a rig in DR2 Studio's **Library** without
knowing where the game stores it, and export one model with everything it uses, or a
whole group (every character, all the music), in one go.   **Time:** ~5 min.
**Games:** both.   **You need:** DR2 Studio and a built index
([`03-browsing.md`](03-browsing.md)); for sounds, PyAV (in the release already).

The game stores things the way it loads them: a character's model in one archive, its
textures in a pack next to it, its skeleton in another folder, a footstep inside a sound
bank inside another archive. The **Library** shows them by what they are instead:

| Section | Groups |
|---|---|
| Models | Characters (outfit parts, survivors, bosses, cutscene characters), Zombies & enemies (by type, plus gore pieces), Weapons & items, Cutscene props, Crowd, Environments (by area and zone) |
| Skeletons | Rigs (the ones characters are animated with), Other skeletons |
| Sounds | Music, Voices, Cutscene audio, Ambience, Footsteps, Zombie sounds, Common effects, Weapon, item & vehicle sounds |
| Textures | Menus & HUD, Character textures, Item & prop textures, World textures (each by role: colour, normal maps, specular…) |
| Text | On-screen text (one bank per language), Game data, Cutscene scripts, Menu & HUD scripts, Audio scripts, Settings |
| Movies | Case West's Bink movies |

Models show a small picture of themselves, textures their thumbnail. Things the game
ships twice with the same bytes (a skeleton in `skeleton/` and again in `preload4.big`)
are shown once; the details say where the other copies are ("also in…").

Each zombie is **one** item: its three files (`zombie_cop_2` high detail, `_3` medium,
`_4` low, which the game swaps by distance) are behind its **Detail** choice in the
**Variants** panel, and its picture shows **one look** (one head, one shirt…), not every
part at once. Choosing a look: [`17-variants.md`](17-variants.md). Exporting a zombie
or the group still writes all three detail levels, each with every part organised.

## Steps: find a character and export everything it uses

1. Start DR2 Studio. It opens on the **Library** tab (left). If it says "Nothing here
   yet", click **Build / refresh index** in the toolbar and wait (a few minutes the first
   time: it also draws the model pictures).
2. In the group list, open **Models → Characters → Outfit parts**. The grid below shows
   each part with its picture and name: *Young Chuck's orange 04 shirt (chest)* is
   `chest_young_chuck`.
   Type in **filter** to narrow the grid (`shirt`, `chuck`).
3. Click the shirt. The centre shows it in 3D. On the right:
   - **Details**: where it is in the Library and in the game, its bones, parts and
     vertices, against the game's limits ([`15-limits.md`](15-limits.md));
   - **rig**: the skeleton file it matches (`playerfullbody.big`, *same bones and pose*);
   - **Related**: every texture its materials use, with a picture and its role
     (*colour*, *normal*, *specular*, *mask*). Double-click one to open it.
4. Click **Export all…** and choose a folder. DR2 Studio makes a folder named after the
   model in it:

   ```
   chest_young_chuck/
       chest_young_chuck.glb    the model: meshes, bones, skin, textures inside
       textures/                every texture as a PNG, named as in the game
           young_cr_shirt_cm.png, young_cr_shirt_nm.png, …
           textures.txt         which texture is colour / normal / specular, for which material
       skeleton.glb             the rig alone
       info.txt                 where it comes from, its counts, its rig, how to open it
   ```

   Open the `.glb` in Blender (*File → Import → glTF 2.0*; or **Open in Blender** in
   Studio) or Substance Painter, and use the PNGs as your starting maps. In Blender, press
   **`Z` → Material Preview** to see the textures, and untick **Bones** in the **Viewport
   Overlays** dropdown to hide the skeleton
   ([more](07-blender-setup.md#seeing-the-model-clearly-textures-and-bones)).

## Steps: export a whole group

1. Select a group or a sub-group in the list (for example **Sounds → Music**, or
   **Models → Zombies & enemies → zombie_cop**).
2. To export only some items, select them in the grid (Ctrl-click, Shift-click);
   with nothing selected, the whole group is exported.
3. Click **Export…** under the grid and choose a folder. A progress bar shows each item;
   **Cancel** stops after the current one.
4. The files land in `<your folder>/<game>/<group>/<sub-group>/`, for example
   `exports/cz/music/HB_Indemnify.wav` or `exports/cz/characters/outfit-parts/chest_young_chuck/`.
   Each game gets its own folder, so Case Zero and Case West never mix.

What each kind becomes:

| Kind | Exported as |
|---|---|
| Model | a folder: `.glb` with textures and bones, `textures/*.png`, `skeleton.glb`, `info.txt` |
| Skeleton | a folder: `<name>.glb` (an armature in Blender), `info.txt` |
| Sound | `<name>.wav` |
| Movie | `<name>.mp4` |
| String bank | `<name>.bcs.json` (the format a text mod uses, [`11-text.md`](11-text.md)) |
| Texture | `<name>.png` |
| Text file | the file as it is |

**Exporting again continues where it stopped**: files that are already there are
skipped. To export a fresh copy, delete the old folder first (or choose another one).

## The same in a terminal

```
dr2 library -g cz                         # the groups and their counts
dr2 library characters -g cz              # one group's items, with their names
dr2 export data/models/npcs.big/chest_young_chuck.big -o exports      # one model, everything
dr2 export characters -g cz -o exports    # every character, one folder each
dr2 export music -g cw -o exports         # all of Case West's music as WAV
dr2 export zombies/zombie_cop -o exports  # one sub-group (every detail level)
dr2 export zombies -o exports --variants shown      # only each zombie's default look
dr2 export sounds --wav -o exports        # a whole section; --wav/--png/--glb/--mp4/--json limit the files
dr2 export environments --list -o exports # only show what would go where
```

## Check it worked

- The model's `.glb` opens in Blender with its textures showing (*Material Preview*) and
  an armature; `skeleton.glb` opens as the armature alone.
- `textures/` holds one PNG per texture listed in `textures.txt`.
- The summary in the log says `0 failed` (Studio) or the command ends with no `FAILED`
  line.

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| The Library says "Nothing here yet" | The index isn't built, or was built by an older toolkit | **Build / refresh index** (`dr2 index build`) |
| Models have no picture | numpy isn't installed, or the index was built with `--no-thumbs` | `pip install numpy`, then rebuild the index |
| A model's picture is grey | Its colour comes from the shader, not a texture (some props), or its texture wasn't found | Nothing to do: the `.glb` export bakes such colours ([`04-extracting.md`](04-extracting.md)) |
| Sounds fail with "install PyAV" | Sounds need PyAV to decode | `pip install av` (the release has it) |
| An export skipped everything | The files are already in that folder (exports continue where they stopped) | Delete the folder or pick another |
| `info.txt` says *rig: its own* | No skeleton file has the same bones (props with a few bones, level pieces) | Use `skeleton.glb` from the same folder |
| Environments take very long | Levels are hundreds of pieces, tens of MB | Export one zone (a sub-group) instead of the whole group |

## Going further

- Edit the exported model: [`08-edit-a-model.md`](08-edit-a-model.md); texture it:
  [`14-texturing-tools.md`](14-texturing-tools.md).
- Where things are in the game's own folders: [`asset-catalogue.md`](asset-catalogue.md),
  and the **Files** tab (the archive tree, for advanced use).
- How the groups are decided (a rules file you can extend):
  `dr2kit/catalog/groups.toml`, [`../dev/code-tour.md`](../dev/code-tour.md).

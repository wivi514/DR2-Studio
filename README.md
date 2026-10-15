# DR2 Studio

A modding app and command-line toolkit for **Dead Rising 2: Case Zero** and
**Dead Rising 2: Case West** (Xbox 360), built for their Xenon recompilations.
Browse the games, make your own weapons and combo weapons, edit textures and models,
change levels, and package your work as mods.

**Development handoff — October 15, 2026:** the original developer has stopped active
development. Contributors are welcome. The [handoff checklist](https://github.com/wivi514/DR2-Studio/issues/1)
links 30 issues with known bugs, unfinished work, research and future plans.

[Install](#install) · [First launch](#first-launch) · [First mod](#make-your-first-mod) ·
[Weapons and combos](#create-your-own-weapon-or-combo-weapon) · [Level editing](#edit-a-level) ·
[Sharing mods](#install-share-and-turn-off-mods) · [Troubleshooting](#help-and-troubleshooting)

## What can I make?

| What you want to do | What Studio provides | Guide |
|---|---|---|
| **Create a weapon** | A wizard with your own `.glb` model or a sample sword, borrowed moves, adjustable damage/durability, fire/freeze/shock, an inventory icon and names | [Make a weapon](docs/modding/20-make-a-weapon.md) |
| **Create a combo weapon** | Choose two ingredients, the resulting custom weapon, combo-card text and a generated or custom card picture | [Combo weapon steps](docs/modding/20-make-a-weapon.md#steps-dr2-studio) |
| Make custom effects | Recolour or resize particles, change their lifetime and pictures, and put a new effect on your weapon | [Effects](docs/modding/21-effects.md) |
| Recolour outfits and objects | Texture thumbnails, editing in your image editor, automatic re-import and live mod previews | [First texture mod](docs/modding/05-first-mod-texture.md) |
| Edit or replace models | Textured 3D previews, Blender export/import, rigs, skin weights and validation | [Edit a model](docs/modding/08-edit-a-model.md), [new meshes](docs/modding/09-new-model.md) |
| Edit levels | Move/add/remove items, change zombie spawns, place prefabs such as save points and workbenches, and edit existing buildings | [Maps](docs/modding/18-maps.md), [level editing](docs/modding/19-edit-a-level.md) |
| Change sounds and text | Preview/export audio, replace music/voices/effects through the recomps, edit strings/translations and text files | [Audio](docs/modding/10-audio.md), [text](docs/modding/11-text.md) |
| Explore and export assets | Library groups, search, model/texture/rig links, variants, animation playback/export, zone exports and Case West movie previews | [Browsing](docs/modding/03-browsing.md), [Library](docs/modding/16-library.md) |
| Use the other game's content | Import items between CZ/CW and supported Case West zombie types into Case Zero; both source games are required | [Cross-game imports](docs/modding/23-other-game.md) |
| Share and manage mods | `.dr2mod` packages, install previews, enable/disable, load order, conflicts, mod sets and **▶ Play** | [Mod packages](docs/modding/06-mod-packages.md) |

Weapon creation uses an existing weapon's behavior and animations as a starting point.
The tools are implemented, but some gameplay checks remain unfinished, including
custom icon/card checks and parts of the Case West weapon workflow. Effects and
hand-placement previews also have [known limitations](https://github.com/wivi514/DR2-Studio/issues/19).
See [known issues](#experimental-features-and-known-issues) before attempting whole-map imports.

## Install

### What you need

- **Python 3.11 or newer** and **Git** for the source installation below.
- Your own legally obtained **Case Zero and/or Case West game data**: a recomp's
  `assets/game` folder, an unpacked game folder, or the game's Xbox 360 XBLA package.
- A compatible [Case Zero recomp](https://github.com/wivi514/Dead_Rising_2_Case_Zero_Xenon_Recomp)
  or [Case West recomp](https://github.com/wivi514/Dead_Rising_2_Case_West_Xenon_Recomp)
  to play through Studio. Install and set up the recomp separately; Studio does not
  include a game or runtime. Browsing/exporting only needs the game data.
- Optional: **Blender 4.2+** for making/editing models, and an image editor such as
  GIMP, Krita, Paint.NET or Photoshop for textures.

Studio targets **Windows, Linux and macOS**. Release packaging has been built and
tried on Linux; [Windows/macOS package validation remains open](https://github.com/wivi514/DR2-Studio/issues/24).
There are no published GitHub releases as of October 15, 2026, so use source installation.
Future packaged builds will appear on the [Releases page](https://github.com/wivi514/DR2-Studio/releases);
the [installation guide](docs/modding/01-install.md) describes their layout.

### Install from source

Clone the repository and create a virtual environment:

```sh
git clone https://github.com/wivi514/DR2-Studio.git
cd DR2-Studio
python -m venv .venv
```

On Linux/macOS, use `python3` if `python` is unavailable. On Windows, `py -3` can be
used to create the environment instead.

Activate it on **Windows PowerShell**:

```powershell
.venv\Scripts\Activate.ps1
```

Or on **Linux/macOS**:

```sh
source .venv/bin/activate
```

Install the app and start it:

```sh
python -m pip install -e ".[studio]"
dr2 studio
```

The `studio` extra installs the GUI, numerical acceleration and audio support. If
`dr2` is not found, use `python -m dr2kit studio` in the activated environment.
On Windows, you can also run `.venv\Scripts\python.exe -m dr2kit studio` without activation.

**Recommended for faster indexing:** with CMake and a C compiler installed, build
the optional native LZX decompressor:

```sh
cmake -S native/lzx -B native/lzx/build -DCMAKE_BUILD_TYPE=Release
cmake --build native/lzx/build --config Release
dr2 doctor
```

Without it, Studio uses a slower Python fallback. See [developer setup](docs/dev/setup.md)
for compiler requirements and platform details.

To update a source installation, close Studio, run `git pull` in the checkout, then
repeat `python -m pip install -e ".[studio]"` in the activated environment.

## First launch

1. Open **Game folders…** from the Welcome window or toolbar. For each game you own,
   choose the folder that contains `data/`, usually the recomp's `assets/game`.
   If you only have the Xbox 360 package, use **Unpack package…** and choose an output
   folder. See [game data setup](docs/modding/02-game-data.md).
2. In the same window, choose the **recomp program** if it was not detected:
   `cz_runtime` or `cw_runtime` (`.exe` on Windows), or the supported recomp AppImage.
   You can also choose Blender and your image editor here.
3. Select your game and click **Build / refresh index**. Allow several minutes per
   game, longer with the Python decompressor. This builds search, thumbnails and asset links.
4. Open **Library** to browse by category, **Search** to find names, or **Browse** to
   inspect the archives. Click a texture, model, sound or animation to preview it.
5. Press **F1** for the guides inside Studio. **New mod…** creates a place for your
   changes; **Open mod…** resumes an existing project.

Studio links mods you create or open into its mod library. Check **Mod manager…**
before using **▶ Play**: it deploys all enabled mods for the selected game, then starts
the recomp. Original game files remain separate from the generated `game_mods/` overlay.

## Make your first mod

A texture recolour is a useful first check that editing and Play are set up correctly:

1. Select **Case Zero**, search for `young_cr_shirt`, and choose
   `chest_young_chuck.tex/young_cr_shirt_cm`. In **Case West**, search for `cr_jacket_cm`
   in `chest_default.tex` instead.
2. Click **Edit in image editor…** and create a mod when prompted.
3. Change the colours, keep the original image dimensions, and save over the same PNG.
   Studio imports the edit into your mod automatically.
4. Use **With my mods** / **Ctrl+M** to compare your edit with the original in Studio.
5. Click **▶ Play** and check the appropriate outfit in game.

The [first-mod guide](docs/modding/05-first-mod-texture.md) explains each step and
common mistakes. For models, use **Open in Blender** or export `.glb`, keep the
required rig/part names, and validate the edited model before importing it.
The [optional Blender add-on](docs/modding/13-blender-addon.md) provides browsing,
rig checking and export-to-mod tools inside Blender.

## Create your own weapon or combo weapon

You can start with **the included sample sword**, keep a game's weapon model, or
bring your own model exported from Blender as **glTF Binary (`.glb`)**.

1. Pick the target game, open/create a mod, and click **New weapon…**.
2. Give it a unique item name such as `FrostBlade` and the name the player will see.
   Choose **Swings like** to borrow a weapon kind's moves, sounds and handling.
3. Choose the model. In **Chuck holding it (3D)**, adjust its length, turn and slide
   until the handle lines up with the hands. Use **Move**, **Pause** and the time slider
   to preview attacks.
4. Set **Damage per hit**, **Durability**, and an optional **Fire**, **Freeze** or
   **Shock** element. Pick effects for impacts, hit zombies, holding and swinging;
   adjust **Weapon effects start** to position an aura or trail.
5. Choose a generated inventory icon, the original icon, or your own PNG.
6. To make a **combo weapon**, tick **Combo weapon**, choose the **two ingredient items**,
   and enter the card text. Studio can generate the combo-card picture from your model,
   or use your own picture. For example: **Broadsword + Fire Extinguisher → FrostBlade**.
7. Click **Make weapon**. Place it in a level using the **Maps** tab's **Add item…**,
   or make it at a workbench using its combo recipe. Click **▶ Play** to check it.

Open the weapon again from the wizard's **Weapon** list to edit it. Weapon mods target
**one game at a time**; create a separate mod for the other game. Previewing a weapon
does not replace checking its attacks, icon, recipe and card in game.

For an effect of your own, open **Effects…**, select a starting effect, change its
colour, size, lifetime or particle PNG, then choose **Make my own from this**.
It uses a free effect slot and appears in the weapon wizard's effect lists.
**Change in my mod** instead changes the existing effect wherever the game uses it.

Full instructions: [weapons and combo cards](docs/modding/20-make-a-weapon.md),
[custom effects](docs/modding/21-effects.md), [engine limits](docs/modding/15-limits.md).

## Edit a level

Open a level in **Maps**, open/create a mod, and enable **Edit the level** in the
**Inspector**. Select an item to move or turn it, or use **Place** to add items,
zombies and prefabs such as workbenches, save points, doors and blockers.
**Hierarchy** helps locate objects; **Ctrl+Z** undoes edits.

Existing buildings can be moved or hidden with their grouped collision, but collision
rotation/scaling is unsupported and **copied buildings have no collision**. Custom
missions/maps can make saves depend on the mod; use copies of saves when experimenting.
See the [level editing guide](docs/modding/19-edit-a-level.md) for supported operations
and save restrictions. Full **New building…** / **New map…** workflows remain unfinished.

## Install, share and turn off mods

- **Install:** drag a `.dr2mod` onto Studio or use **Mod manager… → Install mod file…**.
  Read its requirements and enable it for the correct game.
- **Manage:** use **Mod manager…** to enable/disable mods, inspect conflicts and change
  load order. Save a **mod set** to switch between collections of enabled mods.
- **Play:** **▶ Play** builds/deploys enabled mods and starts the recomp. Cross-game
  imports need both games' source data and a compatible runtime.
- **Share:** open your mod, click **Share…**, fill in its description/version and save
  a `.dr2mod`. Share your own files and recipes, never original game archives or assets.
  Mods marked `local_only` cannot be packaged for sharing.
- **Disable:** use **Play without mods** for a comparison, or **Remove mods from game**
  to remove the deployed overlay. Keep mods needed by your saves available.

Details: [mod packages, requirements and conflicts](docs/modding/06-mod-packages.md).

## Useful commands

The GUI is optional. In an activated source environment, `dr2 --help` lists commands;
`cz` means Case Zero and `cw` means Case West.

```sh
dr2 doctor                                    # versions, decoders and game setup
dr2 games set cz "/path/to/cz/assets/game"      # replace with your actual game folder
dr2 games set-recomp cz "/path/to/cz_runtime"   # replace with your runtime program
dr2 index build cz                            # index the selected game
dr2 studio                                    # open the app
dr2 library -g cz                             # browse categories in the terminal
dr2 export characters -g cz -o exports         # export a group of models and rigs
dr2 effects --kinds -g cz                      # supported weapon kinds
dr2 mod list                                  # installed/linked mods
dr2 mod check -g cz                            # check enabled mods
dr2 mod conflicts -g cz                        # inspect overlapping changes
dr2 play -g cz                                # deploy enabled mods and launch
dr2 play -g cz --no-mods                       # launch without mods
dr2 mod undeploy -g cz                         # remove the deployed overlay
dr2 help 20                                   # weapon guide in the terminal
```

Example: create a freezing combo sword using the sample model, then link it into the
library. The weapon must still be placed in a level or built at a workbench:

```sh
dr2 mod new frostblade-mod
dr2 mod new-weapon frostblade-mod FrostBlade --kind sword --glb sample --name-en "Frost Blade" --damage 150 --element freeze --combo Broadsword+FireExtinguisher --card-text-en "A blade of ice." -g cz
dr2 mod link frostblade-mod
dr2 studio --mod frostblade-mod --weapon FrostBlade
```

## Help and troubleshooting

| Problem | First thing to check |
|---|---|
| No game data found | In **Game folders…**, select the folder containing `data/`, not an archive or the runtime executable. |
| **Play** cannot find the game program | Set the recomp executable in **Game folders…**; Studio does not install the recomp for you. |
| Indexing is very slow | Run `dr2 doctor`; build the optional native LZX library if it reports the Python fallback. |
| An edit does not appear | Check the selected game, enabled mod, conflicts, outfit/item, and the runtime's mod-overlay log lines. |
| A texture replacement is rejected | Keep the original dimensions and follow the reported format/size requirements. |
| A model or grip looks wrong | Check the rig/part names, weapon handle direction and fit; see the model and weapon guides. |
| A 3D preview is blank | Check graphics/QtWebEngine setup; export `.glb` and inspect it in Blender. |
| A custom map hangs or crashes | See the unresolved issues below; whole-map imports are experimental. |

Use **F1**, the full [troubleshooting guide](docs/modding/12-troubleshooting.md), and
[asset catalogue](docs/modding/asset-catalogue.md). When reporting a bug, include the
game, runtime/toolkit versions, enabled mods, reproduction steps and relevant log
excerpts. Do not upload copyrighted game files or personal saves.

## Experimental features and known issues

**Whole-map imports are not reliably playable.** Importing Still Creek (Case Zero's
`prologue`) into Case West's `w_mall` has unresolved loading hangs, heap crashes and
invisible walls. The latest attempts did not establish a working fix. A title screen
or a successful headless check does not prove that an imported map is playable.

- [Infinite loading](https://github.com/wivi514/DR2-Studio/issues/2),
  [invisible collision walls](https://github.com/wivi514/DR2-Studio/issues/3), and heap
  failures in [Case West](https://github.com/wivi514/DR2-Studio/issues/4) and
  [Case Zero](https://github.com/wivi514/DR2-Studio/issues/5).
- Increasing Case West's [level capacity](https://github.com/wivi514/DR2-Studio/issues/6)
  and [zombie type capacity](https://github.com/wivi514/DR2-Studio/issues/7).
- Completing [new building](https://github.com/wivi514/DR2-Studio/issues/15) and
  [new map](https://github.com/wivi514/DR2-Studio/issues/16) authoring, plus
  [cross-game map integration](https://github.com/wivi514/DR2-Studio/issues/10) and
  [boss imports](https://github.com/wivi514/DR2-Studio/issues/12).
- **PC Dead Rising 2 / Off the Record imports are planned, not implemented**:
  [readers](https://github.com/wivi514/DR2-Studio/issues/28),
  [profiles](https://github.com/wivi514/DR2-Studio/issues/29),
  [imports](https://github.com/wivi514/DR2-Studio/issues/30).

## Documentation and contributing

Start with the [modding guides](docs/modding/README.md), [documentation index](docs/README.md)
or [developer setup](docs/dev/setup.md). The [roadmap](docs/roadmap.md) and phase kickoff
documents preserve research history; the [GitHub handoff checklist](https://github.com/wivi514/DR2-Studio/issues/1)
records the latest known status, and [issue #9](https://github.com/wivi514/DR2-Studio/issues/9)
preserves the runtime investigation handoff.

Anyone can fork and open a pull request. Merging into `main` requires one approval
from another collaborator with write access or higher; the owner can add trusted
reviewers. See [CONTRIBUTING.md](CONTRIBUTING.md) and [CLAUDE.md](CLAUDE.md) for the
project's documentation and verification requirements.

## License

You need your own legally obtained copy of the games. This repository contains no game data.

Free to use, change and share; **not for sale**, and mods made for these games must stay
free: no selling them and no paywalls (Patreon, memberships, paid early access).
Voluntary donations that gate nothing are allowed. See [LICENSE](LICENSE).
Third-party code and its licenses: [THIRD_PARTY.md](THIRD_PARTY.md).

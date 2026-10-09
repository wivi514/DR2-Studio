# Install DR2 Studio on Windows, Linux or macOS

**You will:** download DR2 Studio, start it, point it at your games and build its
index, ready for every other guide.   **Time:** ~10 min (plus a minute or two per game
for the index).   **Games:** both.
**You need:** a 64-bit Windows 10/11, a Linux with glibc 2.35 or newer (Ubuntu 22.04,
Fedora 36, Steam Deck… and later), or a Mac with Apple Silicon; about 1 GB of disk; and
your own copy of Case Zero and/or Case West (a recomp's game folder, or the game's
Xbox 360 package file).

DR2 Studio is one download with everything inside: the window-based app, the `dr2`
command line, the Blender add-on and these guides. No Python or other install needed.

> Status (2026-10-09): the Linux build was made and tried on Fedora 44. The Windows and
> macOS builds are produced by the release workflow, which hasn't run yet; until a
> release exists, install from source (end of the steps).

## Steps

### 1. Download

From the toolkit's releases page, take the file for your system:

| System | File | Check it (optional) |
|---|---|---|
| Linux | `DR2Studio-linux-x86_64.AppImage` (one file), or `DR2Studio-linux-x86_64.tar.zst` (a folder) | `sha256sum -c DR2Studio-linux-x86_64.AppImage.sha256` |
| Windows | `DR2Studio-windows-x86_64.zip` | PowerShell: `Get-FileHash DR2Studio-windows-x86_64.zip` and compare with the `.sha256` file |
| macOS (Apple Silicon) | `DR2Studio-macos-arm64.zip` | `shasum -a 256 -c DR2Studio-macos-arm64.zip.sha256` |

### 2. Unpack and start

- **Linux, AppImage:** make it executable (file manager: Properties → Permissions →
  "Allow executing", or `chmod +x DR2Studio-linux-x86_64.AppImage`) and double-click it.
  The command line is inside too: `./DR2Studio-linux-x86_64.AppImage dr2 doctor`.
- **Linux, tar.zst:** `tar --zstd -xf DR2Studio-linux-x86_64.tar.zst`, then run
  `DR2Studio/DR2Studio` (the command line: `DR2Studio/dr2`).
- **Windows:** right-click the zip → **Extract All…**, open the `DR2Studio` folder,
  double-click `DR2Studio.exe`. Windows may say "Windows protected your PC" (the
  program isn't signed): **More info → Run anyway**. The command line is `dr2.exe` in
  the same folder (open a terminal there: Shift+right-click → "Open in Terminal").
- **macOS:** double-click the zip, then **right-click `DR2 Studio.app` → Open** the
  first time (it isn't notarised by Apple; a plain double-click refuses). The command
  line is `DR2 Studio.app/Contents/MacOS/dr2`.

### 3. Point it at your games

On the first start the **Game folders** window opens (later: **Game folders…** in the
toolbar). For each game:

- If you have a **recomp**: **Choose folder…** and pick its `assets/game` folder (the
  one that contains `data`).
- If you have a folder with the game's `data` in it: **Choose folder…** and pick it.
- If you have only the **Xbox 360 package** (a file with a long hex name, inside
  `58410A8D/000D0000/` for Case Zero or `58410B00/000D0000/` for Case West):
  **Unpack package…**, pick the file, then an empty folder to unpack into (about 1 GB).

Each line turns into ✔ and the folder. Close the window. More about the three forms:
[`02-game-data.md`](02-game-data.md).

### 4. Build the index

Pick a game in the toolbar and click **Build / refresh index** (one to three minutes per
game; the log at the bottom shows progress). The index is what search, thumbnails and
"which model uses this texture" run on. Do it again after a toolkit update that asks for
it.

### The command line instead

The `dr2` command does everything the app does. In the `DR2Studio` folder:

```
dr2 doctor                          # what it sees: version, decoders, games
dr2 games set cz D:\games\cz_recomp\assets\game
dr2 unpack <package file> D:\dr2\cw && dr2 games set cw D:\dr2\cw
dr2 index build
```

### The Blender add-on

`blender/io_dr2-<version>.zip` in the download: install it in Blender and set its
**Toolkit folder** to the download's `python` folder
([`13-blender-addon.md`](13-blender-addon.md)).

### From source (developers, or a system without a release)

Python 3.11+: `pip install "dr2kit[studio] @ git+<repository URL>"` or a checkout with
`pip install -e ".[studio]"` ([`../dev/setup.md`](../dev/setup.md)), then `dr2 studio`.

## Check it worked

- `dr2 doctor` (or the app's log) shows `LZX decoder: native`, `audio/movies: PyAV …
  (LGPL …)` and both games with their folders.
- After the index build, the **Browse** tab shows `data` with folders and archives, and
  clicking a texture shows it.

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| Linux: nothing happens on double-click, or "FUSE" errors | The AppImage needs FUSE 2 | Install it (`sudo apt install libfuse2` on Ubuntu), or use the `.tar.zst`. |
| Linux: `GLIBC_2.xx not found` | Your system is older than the build's baseline | Use a newer distribution, or run from source. |
| Windows: "Windows protected your PC" | The program isn't signed | **More info → Run anyway**. |
| macOS: "cannot be opened because the developer cannot be verified" | Not notarised | Right-click → **Open**, then **Open**. |
| Game folders: `no 'data' folder with .big files there` | You picked the wrong level of folder | Pick the folder that *contains* `data` (a recomp's `assets/game`). |
| The 3D view stays empty | Your graphics driver or a remote session blocks it | Export the model with **Export .glb…** and open it in Blender. |
| `dr2 doctor` says `LZX decoder: python (slow fallback…)` | The native library couldn't load (antivirus, blocked file) | Everything still works, slower; unblock the download (Windows: Properties → Unblock). |

## Going further

Next: [`02-game-data.md`](02-game-data.md) (the game's files), then
[`03-browsing.md`](03-browsing.md) and [`05-first-mod-texture.md`](05-first-mod-texture.md),
your first mod.

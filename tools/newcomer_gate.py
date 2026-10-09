"""Phase 7 gate, scripted: make a mod, share it, install it elsewhere, Play, look.

The gate (docs/roadmap.md §Phase 7) is about a person following the in-app help; this
script runs the same toolkit functions DR2 Studio's buttons call, in the same order, so
the chain is checked in game on its own:

1. **New mod…** (`ModLibrary.create`) in library A; the shirt texture made red (what
   *Edit in image editor…* would save) and ``IDS_PRESS_START`` changed (the strings
   table);
2. **Share…** (`Mod.save` with a name and readme, `pack`): one ``.dr2mod`` file;
3. on a "second setup" (library B, empty): **Install mod…** (`ModLibrary.install`);
4. **▶ Play** (`play.deploy_library` + `play.launch`) with the recomp run headless,
   pressing START, A, A to load the latest save, dumping frames to ``--frames``;
5. afterwards **Remove mods from game** (`play.undeploy_all`).

Every user folder (config, libraries) is a temporary one; the recomp's save is copied.
Look at the last frames: the title screen shows the new text, and Chuck wears red.

Usage: python tools/newcomer_gate.py <cz|cw> --frames ~/.cache/dr2kit-gate7/cz
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import sys
import tempfile
import time
from pathlib import Path

SHIRT = {"cz": "data/models/npcs.big/chest_young_chuck.tex/young_cr_shirt_cm",
         "cw": "data/models/npcs.big/chest_default.tex/cr_jacket_cm"}
TEXT = "DR2KIT PHASE 7 OK"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("game", choices=["cz", "cw"])
    ap.add_argument("--frames", required=True, help="folder for frame dumps (on disk!)")
    ap.add_argument("--seconds", type=int, default=170)
    a = ap.parse_args()
    game, P = a.game, a.game.upper()
    work = Path(tempfile.mkdtemp(prefix="dr2gate7-"))
    os.environ["XDG_CONFIG_HOME"] = str(work / "cfg")      # isolated toolkit settings
    os.environ["XDG_DATA_HOME"] = str(work / "data")
    from dr2kit.container.vpath import AssetTree
    from dr2kit.convert import png, strings as cstr
    from dr2kit.convert.texture import to_image
    from dr2kit.formats.bct import Bct
    from dr2kit.mods import play
    from dr2kit.mods.library import ModLibrary, pack
    from dr2kit.mods.manifest import Mod
    from dr2kit.profiles import locate
    tree = AssetTree(locate(game).root)

    # 1. make the mod
    lib_a = ModLibrary(work / "library_a")
    mod = lib_a.create("Phase 7 gate", games=(game,))
    img = to_image(Bct.parse(tree.resolve(SHIRT[game]).data()))
    px = bytearray(img.rgba)
    for i in range(0, len(px), 4):
        px[i], px[i + 1], px[i + 2] = 230, px[i + 1] // 4, px[i + 2] // 4
    dest = mod.root / "replace" / (SHIRT[game] + ".png")
    dest.parent.mkdir(parents=True)
    png.write(dest, png.Image(img.width, img.height, bytes(px)))
    labels = cstr.load_labels(tree)
    bank = cstr.load_bank(tree, "en")
    cstr.set_mod_strings(mod.root, "en", {10611: TEXT}, labels, bank.strings)
    print("1. mod made:", [rel for rel, _ in Mod.load(mod.root).files()], flush=True)

    # 2. share it
    m = Mod.load(mod.root)
    m.author, m.description = "gate", "Red shirt and a new title-screen text."
    (m.root / "README.md").write_text("# Phase 7 gate\n\nRed shirt, new PRESS START text.\n")
    m.save()
    (work / "shared").mkdir()
    package = pack(m.root, work / "shared")
    print("2. shared:", package.name, f"{package.stat().st_size / 1e6:.2f} MB", flush=True)

    # 3. install on a second setup
    lib_b = ModLibrary(work / "library_b")
    installed = lib_b.install(package)
    print("3. installed:", installed.id, "on:", [e.mod.id for e in lib_b.entries() if e.enabled],
          flush=True)

    # 4. Play (headless)
    files, _ = play.deploy_library(game, lib_b)
    print("4. deployed:", files, "|", play.deployed(game).describe(), flush=True)
    frames = Path(a.frames).expanduser()
    shutil.rmtree(frames, ignore_errors=True)
    frames.mkdir(parents=True)
    recomp = play.recomp_folder(game)
    save = work / "save"
    shutil.copytree(recomp / "assets" / "save", save)
    env = {f"{P}_BUG_REPORTS": "0", f"{P}_SAVE_DIR": str(save), f"{P}_NO_WINDOW": "1",
           f"{P}_VKDRAW": "1", f"{P}_VK_FRAME_DUMP": str(frames),
           f"{P}_FAKE_START_MS": "8000", f"{P}_FAKE_PRESS_SEQ": "START,A,A"}
    proc = play.launch(game, extra_env=env)
    print(f"   started {play.find_recomp(game)} (pid {proc.pid}); {a.seconds} s…", flush=True)
    try:
        proc.wait(a.seconds)
    except Exception:  # noqa: BLE001 - the expected timeout
        pass
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        time.sleep(1)

    # 5. remove the mod from the game, clean the temporary setup
    removed = play.undeploy_all(game)
    print("5. removed from the game:", removed, "|", play.deployed(game).describe(), flush=True)
    shutil.rmtree(work)
    print("frames:", len(list(frames.glob("*.ppm"))), "in", frames)
    return 0


if __name__ == "__main__":
    sys.exit(main())

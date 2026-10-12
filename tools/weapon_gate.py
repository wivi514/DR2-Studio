"""Phase 13 gate, scripted through DR2 Studio's own windows: Frostmourne made only in
Studio, shared, installed on a clean library, ready to play.

The gate (docs/phase13-kickoff.md §Gate): a weapon with the toolkit's sample model (not
WoW's), the Broadsword's moves (CZ; the Katana's in CW), freeze, a frost aura of its own
(a recoloured game effect) and a combo card, shared as one ``.dr2mod``, installed on a
clean library, played. This script drives the real dialogs offscreen
(``QT_QPA_PLATFORM=offscreen``), in the order a modder clicks:

1. **New mod…** (`ModLibrary.create` in library A, a temporary folder);
2. **Effects…** (`studio.effects_dialog.EffectsDialog`): ``flamingsword_wpn_c_3_unq``
   selected, *Hue* 200, *Saturation* ×1.30, *Make my own from this*;
3. **New weapon…** (`studio.weapon_dialog.WeaponDialog`): *Frostmourne*, English and
   French names, *Sword*, *The sample sword*, *Freeze*, the aura in *while held*, a
   combo (Broadsword / Katana + Fire Extinguisher) with its card texts, *Make weapon*;
4. **Maps → Add item…** (the same `leveledit.TextEdits` the Maps editor saves): one placed
   at the save's start (``--at``);
5. **Share…** (`library.pack` after the share check) → one ``.dr2mod``;
6. **Install mod…** on a clean library B, and the mod's files listed.

The link Studio makes to the temporary mod in the user's library is removed. Then, with
``--install-user``, the ``.dr2mod`` is installed into the *user's* library
and deployed (``play.deploy_library``) for the windowed check by a person: pick it up,
swing it, the icon, the card at a workbench, the French name. Without it, everything is
temporary and removed.

Usage: python tools/weapon_gate.py cz --out ~/.cache/dr2kit-gate13 [--install-user]
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Where it lies: on floor measured from the zone collision (CZ street 3.36 m, CW 0), 3 cm
# above it, flat: a wizard weapon's blade runs along the model's +z, so a turn of 90°
# about z puts its flat side down (a turn about x stood it on its tip, sunk in the street)
START = {"cz": ("prologue.txt", "-278.5,3.39,-36.5"),          # the street, by the safehouse
         "cw": ("storage_pens.txt", "-83.9,0.03,110.3")}        # by the Storage Bay save point
FLAT = "0,0,0.7071068,0.7071068"
PARTNER = {"cz": "Broadsword", "cw": "Katana"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("game", choices=["cz", "cw"])
    ap.add_argument("--out", required=True, help="where the .dr2mod and pictures go")
    ap.add_argument("--install-user", action="store_true",
                    help="install the shared mod into your library and deploy it")
    a = ap.parse_args()
    game = a.game
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="dr2gate13-"))
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from dr2kit.container.vpath import AssetTree
    from dr2kit.mods.leveledit import TextEdits
    from dr2kit.mods.library import ModLibrary, pack
    from dr2kit.mods.manifest import Mod
    from dr2kit.profiles import locate
    from dr2kit.studio.app import MainWindow
    from dr2kit.studio.effects_dialog import EffectsDialog
    from dr2kit.studio.weapon_dialog import SAMPLE, WeaponDialog

    app = QApplication.instance() or QApplication([])
    win = MainWindow(work / "index.sqlite")
    win.set_game(game)
    errors = []
    win.error = lambda text: errors.append(text)          # a dialog box would block

    # 1. New mod…
    lib_a = ModLibrary(work / "library_a")
    mod = lib_a.create("Frostmourne", games=(game,))
    win._set_mod(mod.root)
    print("1. mod:", mod.id, flush=True)

    # 2. Effects… → the Flaming Sword turned icy blue, made our own
    fx = EffectsDialog(win, mod.root)
    fx.search.setText("flamingsword_wpn_c_3")
    item = next(fx.list.item(i) for i in range(fx.list.count())
                if "flamingsword_wpn_c_3_unq" in fx.list.item(i).text())
    fx.list.setCurrentItem(item)
    fx.hue.setValue(200)
    fx.sliders["saturation"].setValue(130)
    fx.make_own()
    win.wait_for_jobs(120)
    aura = int(fx.notes.text().split("number ")[1].split(":")[0])
    fx.grab().save(str(out / "effects_window.png"))
    fx.close()
    print("2. own effect:", aura, "|", fx.notes.text(), flush=True)

    # 3. New weapon…
    wd = WeaponDialog(win, mod.root)
    wd.name.setText("Frostmourne")
    wd.name_en.setText("Frostmourne")
    wd.name_fr.setText("Deuillegivre")
    wd.kind.setCurrentIndex(wd.kind.findData("sword"))
    wd.model.setCurrentText(SAMPLE)
    wd.element.setCurrentIndex(wd.element.findData("freeze"))
    wd.fx["held"].set_number(aura)
    wd.combo.setChecked(True)
    wd.item1.setCurrentText(PARTNER[game])
    wd.item2.setCurrentText("FireExtinguisher")
    wd.card_en.setText("A runeblade of ice: it freezes what it cuts.")
    wd.card_fr.setText("Une lame runique de glace : elle gèle ce qu'elle tranche.")
    wd.refresh_preview()
    win.wait_for_jobs(300)
    wd.grab().save(str(out / "weapon_window.png"))
    wd.make()
    win.wait_for_jobs(600)
    print("3. weapon:", wd.notes.text().replace("\n", " | "), flush=True)
    wd.close()
    if errors:
        print("ERRORS:", errors)
        return 1

    # 4. Maps → Add item… (what the editor saves)
    tree = AssetTree(locate(game).root)
    level, at = START[game]
    ed = TextEdits(mod.root, level, tree)
    ed.doc.add(None, "cItemPlacement", "Gate13_Frostmourne",
               [("ItemName", "Frostmourne"), ("Location", at),
                ("Rotation", FLAT)])
    ed.save()
    print("4. placed in", level, "at", at, flush=True)

    # 5. Share…
    m = Mod.load(mod.root)
    m.author, m.description = "phase 13 gate", "Frostmourne: a runeblade of ice (sample model)."
    (m.root / "README.md").write_text("# Frostmourne\n\nA sword that freezes zombies, with a "
                                      "frost aura and a combo card. Made in DR2 Studio.\n")
    m.save()
    package = pack(m.root, out)
    print("5. shared:", package, f"{package.stat().st_size / 1e6:.2f} MB", flush=True)

    # 6. Install mod… on a clean library
    lib_b = ModLibrary(work / "library_b")
    installed = lib_b.install(package)
    print("6. installed on a clean library:", installed.id,
          [rel for rel, _ in Mod.load(installed.root).files()][:4], "…", flush=True)

    # Studio links the mod it opens into the user's library: forget that link (the
    # temporary folder goes away), whatever happens next
    lib = ModLibrary()
    for e in lib.entries():
        if e.mod.root.resolve().is_relative_to(work.resolve()):
            lib.remove(e.mod.id)
    if a.install_user:
        from dr2kit.mods import play
        user = lib.install(package)
        lib.enable(user.id)
        files, _ = play.deploy_library(game, lib)
        print("7. in your library and deployed:", user.id, files, flush=True)
    win.close()
    del app
    shutil.rmtree(work)
    return 0


if __name__ == "__main__":
    sys.exit(main())

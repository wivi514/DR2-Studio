"""Editing with your own programs, without the round trips: image editor and Blender.

Before phase 7 a texture edit was: Export PNG…, find the file, edit, save, Replace with
PNG…, find the file again. Now:

* **Edit in image editor…** (`TextureEdit`): Studio writes the texture as a PNG into a
  work folder (`edits_dir`, per user, never inside the mod), opens it with the user's
  image editor (the system's default for PNG, or the one chosen in Studio and saved as
  ``[tools] image_editor``), and **watches the file**: every time it is saved, Studio
  checks it and puts it in the open mod, and the texture view shows the result as the
  game will get it. If the mod already replaces the texture, editing starts from the
  mod's picture.
* **Open in Blender** (`open_in_blender`): Studio exports the model (or the mod's
  ``.glb`` of it) into the work folder and starts Blender with a short script that
  imports it into a collection tagged like the DR2 add-on's imports (``dr2_game``,
  ``dr2_vpath``) and, when the add-on is enabled, sets its mod folder: *Check rig* and
  *Export to mod* work at once. Blender is found through ``[tools] blender`` in the
  config, the PATH, or the usual install folders.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QProcess, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices

from ..errors import Dr2Error
from ..profiles import get_config


def edits_dir() -> Path:
    """The per-user work folder for files being edited in other programs."""
    from ..userdirs import data_dir
    return data_dir() / "edits"


def work_file(game: str, vpath: str, suffix: str) -> Path:
    p = edits_dir() / game / (vpath + suffix)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


class TextureEdit(QObject):
    """One texture being edited in an image editor. ``saved(path)`` fires (once per
    save, after the file stops changing) while the session is open."""
    saved = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path: Path | None = None
        self.vpath = ""
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._changed)
        self.watcher.directoryChanged.connect(self._changed)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(600)          # editors write in several steps
        self._timer.timeout.connect(self._settled)
        self._last = None

    def start(self, game: str, vpath: str, png_bytes: bytes) -> Path:
        """Write the PNG into the work folder, open it in the editor, start watching."""
        self.stop()
        self.vpath = vpath
        self.path = work_file(game, vpath, ".png")
        self.path.write_bytes(png_bytes)
        self._last = self._stamp()
        self.watcher.addPath(str(self.path))
        self.watcher.addPath(str(self.path.parent))   # editors that replace the file
        open_with_editor(self.path)
        return self.path

    def stop(self) -> None:
        for p in self.watcher.files() + self.watcher.directories():
            self.watcher.removePath(p)
        self.path = None

    def _stamp(self):
        try:
            st = self.path.stat()
            return st.st_mtime_ns, st.st_size
        except OSError:
            return None

    def _changed(self, _p: str) -> None:
        if self.path is not None:
            if str(self.path) not in self.watcher.files() and self.path.is_file():
                self.watcher.addPath(str(self.path))
            self._timer.start()

    def _settled(self) -> None:
        stamp = self._stamp() if self.path else None
        if stamp is None or stamp == self._last:
            return
        self._last = stamp
        self.saved.emit(str(self.path))


def open_with_editor(path: Path) -> None:
    """Open ``path`` in the chosen image editor, or the system's default program."""
    editor = get_config("tools", "image_editor")
    if editor and Path(editor).exists():
        if sys.platform == "darwin" and editor.endswith(".app"):
            QProcess.startDetached("open", ["-a", editor, str(path)])
        else:
            QProcess.startDetached(editor, [str(path)])
        return
    if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
        raise Dr2Error(f"no program opens PNG files here; choose an image editor "
                       f"(the file is {path})")


def find_blender() -> str | None:
    """Blender's program: ``[tools] blender`` in the config, the PATH, or the usual
    install folders; None if not found."""
    chosen = get_config("tools", "blender")
    if chosen and Path(chosen).exists():
        return chosen
    found = shutil.which("blender")
    if found:
        return found
    candidates = []
    if sys.platform == "win32":
        for base in (Path("C:/Program Files/Blender Foundation"),):
            candidates += sorted(base.glob("Blender*/blender.exe"), reverse=True)
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/Blender.app/Contents/MacOS/Blender"))
    else:
        candidates += [Path("/usr/bin/blender"), Path("/snap/bin/blender")]
    return next((str(c) for c in candidates if c.exists()), None)


BLENDER_SCRIPT = '''\
# Written by DR2 Studio: import a game model and tag it for the DR2 add-on.
# The import runs from a timer, once Blender's window is up: run straight from
# --python in a windowed Blender, the glTF importer fails ("'Context' object has no
# attribute 'object'") and leaves only its bone-shape Icosphere (user report,
# 2026-10-10). The start-up scene is emptied through bpy.data, not read_homefile,
# which would leave this script with a stale context.
import json, bpy
job = json.loads({job!r})


def run():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    coll = bpy.data.collections.new(job["name"])
    bpy.context.scene.collection.children.link(coll)
    coll["dr2_game"], coll["dr2_vpath"] = job["game"], job["vpath"]
    bpy.context.view_layer.active_layer_collection = \\
        bpy.context.view_layer.layer_collection.children[coll.name]
    # no sphere on every bone (the importer's bone shapes): the model stays readable
    props = bpy.ops.import_scene.gltf.get_rna_type().properties
    extra = dict(disable_bone_shape=True) if "disable_bone_shape" in props else dict()
    bpy.ops.import_scene.gltf(filepath=job["glb"], **extra)
    arm = next((o for o in coll.objects if o.type == "ARMATURE"), None)
    if arm is not None:
        bpy.context.view_layer.objects.active = arm
    # variants (phase 9): parts go into one collection per group (Head 1, Head 2, Shirt 1…);
    # the parts the chosen look doesn't show are hidden (H / Alt+H, or the eye icons)
    groups = dict()
    for obj in list(coll.objects):
        group = obj.get("dr2_group")
        if group is None:
            continue
        sub = groups.get(group)
        if sub is None:
            sub = groups[group] = bpy.data.collections.new(group)
            coll.children.link(sub)
        sub.objects.link(obj)
        coll.objects.unlink(obj)
        if not obj.get("dr2_shown", True):
            obj.hide_set(True)
            obj.hide_render = True
    # an animation (phase 14): the timeline spans the move, so Space plays all of it
    if bpy.data.actions:
        ranges = [a.frame_range for a in bpy.data.actions]
        bpy.context.scene.frame_start = int(min(r[0] for r in ranges))
        bpy.context.scene.frame_end = int(max(r[1] for r in ranges))
    # show the textures: Material Preview in every 3D view (Solid view draws grey)
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.shading.type = "MATERIAL"
    try:
        bpy.context.scene.dr2.game = job["game"]
        if job["mod"]:
            bpy.context.scene.dr2.mod_folder = job["mod"]
    except AttributeError:
        pass  # the DR2 add-on isn't enabled: the model is still imported
    return None


if bpy.app.background:
    run()
else:
    bpy.app.timers.register(run, first_interval=0.5)
'''


def open_in_blender(game: str, vpath: str, glb: bytes, mod_dir: Path | None) -> Path:
    """Start Blender with the model imported (see the module docstring). Returns the
    ``.glb`` written into the work folder."""
    blender = find_blender()
    if blender is None:
        raise Dr2Error("Blender was not found. Install Blender 4.2 or newer, or tell DR2 "
                       "Studio where it is (Game folders… → Blender).")
    path = work_file(game, vpath, ".glb")
    path.write_bytes(glb)
    job = json.dumps({"game": game, "vpath": vpath, "glb": str(path),
                      "name": vpath.rsplit("/", 1)[-1],
                      "mod": str(mod_dir) if mod_dir else ""})
    script = path.with_suffix(".py")
    script.write_text(BLENDER_SCRIPT.format(job=job), "utf-8")
    if not QProcess.startDetached(blender, ["--python", str(script)]):
        raise Dr2Error(f"could not start {blender}")
    return path

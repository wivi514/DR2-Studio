"""DR2 Studio's **Maps** tab (phase 10 step 3): a level in 3D, its items and markers.

Two widgets, wired by `app.MainWindow`:

* `MapsList`, the left tab: the game's levels, each with its zones (double-click a zone
  to fly there).
* `MapsView`, the centre: the Maps page (``web/maps.html`` + ``maps.js``, three.js in a
  QWebEngineView, the same ``dr2:`` scheme as the 3D view, `model_view`) and a side
  panel: which level script's items to show, the **Layers** (pieces, items and doors,
  spawn points, zombie / map / lighting areas, triggers, sound areas, map points, the
  navigation mesh, the zombies, the collision mesh), **Go to** (a spawn point, a map area, a map point, a zone) and what
  was clicked, with *Open in Library*, *Open in Blender* and *Export .glb…* for a piece
  or an item.

How a level loads: `MapsView.open_level` sends the page `convert.mapdata.overview`
(zones, markers, start). The page asks for each zone's **pieces** and **items** (and,
when their layers are on, **zombies** and **collision**: one size only) (``dr2:want``), nearest the camera first, with small textures far away and full-size
ones near; `_Builder` (one worker thread, its own `AssetTree`) makes each file with
`convert.mapdata.MapCache` (cached on disk, so a second visit is instant) and the page
gets its URL (``dr2://studio/maps/…``). A level change bumps a generation number, so
requests of the previous level are dropped, never shown.

**Editing** (phase 11, `studio.maps_edit`): with *Edit* ticked, a clicked item or door
gets move / turn handles and its name, place and turn in the panel; every change goes into
the **mod being edited** (the bottom bar's open mod) as ``.edits.json`` through
`maps_edit.LevelEditor`, and the page is told what changed (``dr2.itemState``) instead of
rebuilding the level. The file watcher's refresh that follows a save swaps the trees
without reloading the level (`use_tree`, ``_own_write_until``).

Without QtWebEngine the tab shows a note (like the 3D view); `dr2 level` and the exports
still work.
"""

from __future__ import annotations

import json
import math
import os
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtWidgets import (QCheckBox, QComboBox, QCompleter, QDoubleSpinBox, QFileDialog,
                               QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QPushButton, QTextBrowser, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..container.vpath import AssetTree
from ..errors import Dr2Error
from . import model_view

PAGE_URL = "dr2://studio/maps.html"
ROLE = Qt.UserRole + 1

# The layers in the order the panel lists them, with whether they start on.
LAYER_ORDER = [("pieces", "Buildings (level pieces)", True),
               ("items", "Items and doors", True),
               ("spawn", "Spawn points", True),
               ("map_area", "Map areas", True),
               ("map_point", "Map points (workbenches, save points)", True),
               ("zombie_area", "Zombie areas", False),
               ("zombies", "Zombies (crowds the missions put in the areas)", False),
               ("trigger", "Triggers (doors to other levels…)", False),
               ("navmesh", "Navigation mesh", False),
               ("collision", "Collision (what the player bumps into)", False),
               ("light_area", "Lighting areas", False),
               ("sound_area", "Sound areas", False),
               ("acoustics", "Acoustics points", False),
               ("overview", "In-game map (corner; click to go there)", True)]


class MapsList(QWidget):
    """The left tab: levels and their zones. Emits ``chosen(level, zone or "")``."""

    chosen = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.note = QLabel("The game's levels in 3D: pick one. Its buildings, items, "
                           "doors and spawn points load around you.")
        self.note.setWordWrap(True)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Level", "Zones"])
        self.tree.itemActivated.connect(self._activated)
        self.tree.itemClicked.connect(self._clicked)
        lay.addWidget(self.note)
        lay.addWidget(self.tree, 1)

    def set_levels(self, levels: list) -> None:
        """``levels``: `convert.level.Level` objects (main levels first)."""
        self.tree.clear()
        for L in levels:
            top = QTreeWidgetItem([_level_title(L.name), str(len(L.zones))])
            top.setData(0, ROLE, (L.name, ""))
            top.setToolTip(0, L.vpath)
            for z in L.zones:
                c = QTreeWidgetItem([z.zone, ""])
                c.setData(0, ROLE, (L.name, z.zone))
                top.addChild(c)
            self.tree.addTopLevelItem(top)
        self.tree.resizeColumnToContents(0)

    def _clicked(self, item, _col) -> None:
        if item.parent() is None:                 # a level: open it with one click
            self.chosen.emit(*item.data(0, ROLE))

    def _activated(self, item, _col) -> None:
        self.chosen.emit(*item.data(0, ROLE))


_TITLES = {"prologue": "Fortune City (the street)", "prologue_menu": "Title screen street",
           "prologue_menu2": "Title screen (2)", "living_research": "Living quarters & research",
           "storage_pens": "Storage pens", "secure_laboratory": "Secure laboratory",
           "safehouse": "Safehouse", "main_menu": "Title screen"}


def _level_title(name: str) -> str:
    t = _TITLES.get(name.lower())
    if t is None and name.lower().startswith("cine_"):
        t = "Cutscene: " + name[5:].replace("_", " ")
    return f"{t} ({name})" if t else name


def level_sort_key(L) -> tuple:
    """Main levels first, then title screens, then cutscene sets."""
    n = L.name.lower()
    return (n.startswith("cine_"), "menu" in n, n)


BUILDERS = 3          # zone files built at once (zlib and numpy let threads overlap)


class _Generation:
    """The level shown now, as a number every builder can read."""
    value = 0


class _Builder(QObject):
    """Builds zone files in its own thread, one request at a time. Each builder has its
    own `MapCache` (and so its own `AssetTree`): the trees' archive caches are not
    shared between threads."""
    built = Signal(dict, str, str)           # request, file path ("" = nothing), error

    def __init__(self, generation: _Generation):
        super().__init__()
        self.cache = None
        self.gen = generation

    @Slot(dict)
    def build(self, req: dict) -> None:
        cache = self.cache
        if req.get("generation") != self.gen.value or cache is None:
            return                            # a request of a level no longer shown
        try:
            if req["part"] == "zombies":
                path = cache.zombies(req["level"], req["zone"], req["script"], req["detail"]) \
                    if req.get("script") else None
            elif req["part"] == "collision":
                path = cache.collision(req["level"], req["zone"])
            elif req["part"] == "items":
                path = cache.items(req["level"], req["zone"], req["script"], req["detail"]) \
                    if req.get("script") else None
            else:
                path = cache.pieces(req["level"], req["zone"], req["detail"])
            self.built.emit(req, str(path) if path else "", "")
        except Dr2Error as e:
            self.built.emit(req, "", str(e))
        except Exception:  # noqa: BLE001 - shown to the user, never swallowed
            self.built.emit(req, "", traceback.format_exc(limit=4))


class MapsView(QWidget):
    """The centre pane of the Maps tab (module docstring)."""

    status = Signal(str)
    open_asset = Signal(str)                  # a vpath to show in the Library's viewer

    def __init__(self, window=None, parent=None):
        super().__init__(parent)
        self.window = window
        self.game: str | None = None
        self.tree: AssetTree | None = None
        self.cache = None
        self.level: str | None = None
        self.meta: dict | None = None
        self.ready = False
        self._pending_js: list[str] = []
        self._served = 0
        self.picked: dict | None = None
        self.camera: dict | None = None
        self.last_message = ""
        self.last_status = ""
        self.view = None

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        if model_view.WEB_ENGINE and model_view._registered:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            self._profile, self._handler = model_view._profile_and_handler()
            self.view = QWebEngineView(self)
            self._page = _MapsPage(self._profile, self._message, self.view)
            self.view.setPage(self._page)
            self.view.load(QUrl(PAGE_URL))
            outer.addWidget(self.view, 1)
        else:
            why = model_view.WEB_ENGINE_ERROR or "the dr2: scheme could not be registered"
            from types import SimpleNamespace
            self._handler = SimpleNamespace(files={})   # what the page would be served
            note = QLabel("The Maps view needs PySide6's QtWebEngine (" + why + ").\n\n"
                          "dr2 level and the exports still work.")
            note.setWordWrap(True)
            outer.addWidget(note, 1)

        side = QWidget()
        side.setMaximumWidth(330)
        sl = QVBoxLayout(side)
        self.title = QLabel("<b>Maps</b><br>Pick a level on the left.")
        self.title.setWordWrap(True)
        sl.addWidget(self.title)
        sl.addWidget(QLabel("Items and markers from:"))
        self.script_box = QComboBox()
        self.script_box.setToolTip("A level can have several sets of items: Case Zero's "
                                   "street has the story's and the safehouse's")
        self.script_box.currentIndexChanged.connect(self._script_changed)
        sl.addWidget(self.script_box)
        sl.addWidget(QLabel("<b>Layers</b>"))
        grid = QGridLayout()
        self.layer_boxes: dict[str, QCheckBox] = {}
        for i, (kind, text, on) in enumerate(LAYER_ORDER):
            b = QCheckBox(text)
            b.setChecked(on)
            b.toggled.connect(lambda v, k=kind: self._js(f"dr2.setLayer({json.dumps(k)}, {str(v).lower()})"))
            self.layer_boxes[kind] = b
            grid.addWidget(b, i, 0)
        sl.addLayout(grid)
        trow = QHBoxLayout()
        self.time_box = QCheckBox("Time of day")
        self.time_box.setToolTip("The game's light for the hour: sky, fog, sun or moon, "
                                 "ambient light (from the level's lighting table)")
        self.time_box.setChecked(True)
        from PySide6.QtWidgets import QSlider
        self.hour = QSlider(Qt.Horizontal)
        self.hour.setRange(0, 23)
        self.hour.setValue(12)
        self.hour_label = QLabel("12:00")
        trow.addWidget(self.time_box)
        trow.addWidget(self.hour, 1)
        trow.addWidget(self.hour_label)
        sl.addLayout(trow)
        self.hour.valueChanged.connect(self._hour_changed)
        self.time_box.toggled.connect(lambda _v: self._hour_changed(self.hour.value()))
        sl.addWidget(QLabel("<b>Go to</b>"))
        self.goto_box = QComboBox()
        self.goto_box.activated.connect(self._goto)
        sl.addWidget(self.goto_box)
        sl.addWidget(QLabel("<b>What is this?</b> (click in the view)"))
        self.info = QTextBrowser()
        self.info.setOpenLinks(False)
        sl.addWidget(self.info, 1)
        self._build_edit_panel(sl)
        row = QHBoxLayout()
        self.btn_library = QPushButton("Open in Library")
        self.btn_library.setToolTip("Show this model on its own, with its textures and actions")
        self.btn_library.clicked.connect(self._open_in_library)
        self.btn_blender = QPushButton("Open in Blender")
        self.btn_blender.clicked.connect(self._open_in_blender)
        row.addWidget(self.btn_library)
        row.addWidget(self.btn_blender)
        sl.addLayout(row)
        self.btn_export = QPushButton("Export .glb…")
        self.btn_export.setToolTip("This piece or item alone, as glTF for Blender")
        self.btn_export.clicked.connect(self._export_glb)
        sl.addWidget(self.btn_export)
        row = QHBoxLayout()
        self.btn_export_zone = QPushButton("Export zone…")
        self.btn_export_zone.setToolTip("The zone you stand in as .glb for Blender: buildings "
                                        "placed, items and doors, markers; and the level's "
                                        "text files")
        self.btn_export_zone.clicked.connect(lambda: self.export(whole_level=False))
        self.btn_export_level = QPushButton("Export level…")
        self.btn_export_level.setToolTip("Every zone of the level, one .glb each")
        self.btn_export_level.clicked.connect(lambda: self.export(whole_level=True))
        row.addWidget(self.btn_export_zone)
        row.addWidget(self.btn_export_level)
        sl.addLayout(row)
        self.btn_help = QPushButton("How to use Maps")
        self.btn_help.clicked.connect(lambda: self.window.open_help("18-maps.md")
                                      if hasattr(self.window, "open_help") else None)
        sl.addWidget(self.btn_help)
        self.btn_copy = QPushButton("Copy camera position")
        self.btn_copy.setToolTip("x, y, z of the camera, for notes or a bug report")
        self.btn_copy.clicked.connect(self._copy_position)
        sl.addWidget(self.btn_copy)
        outer.addWidget(side)
        self._set_actions(None)

        self._gen = _Generation()
        self._workers: list[tuple[QThread, _Builder, object]] = []
        self._next = 0
        for _ in range(BUILDERS):
            th = QThread(self)
            b = _Builder(self._gen)
            b.moveToThread(th)
            relay = _Ask()
            relay.ask.connect(b.build)            # queued: runs in the builder's thread
            b.built.connect(self._built)
            th.start()
            self._workers.append((th, b, relay))

    # ---- setup -----------------------------------------------------------------------

    @property
    def available(self) -> bool:
        return self.view is not None

    def set_game(self, game: str, root: Path | str, db_path=None) -> list:
        """Use ``game`` (its data at ``root``); returns its levels, sorted for the list."""
        from ..convert import level as clevel
        from ..convert import mapdata
        self.game = game
        self.tree = AssetTree(root, cache_size=16)          # this view's own: thread-safe
        self._gen.value += 1
        for _th, b, _r in self._workers:
            b.cache = mapdata.MapCache(AssetTree(root, cache_size=24), game, db_path=db_path)
        self.cache = self._workers[0][1].cache if self._workers else None
        self._ui_cache = mapdata.MapCache(self.tree, game, db_path=db_path)
        self.level = None
        return sorted(clevel.list_levels(self.tree), key=level_sort_key)

    def use_tree(self, make_tree) -> None:
        """Give every builder a tree made by ``make_tree(root)`` (the mods view, step 5).
        Right after the editor saved (the file watcher's refresh), the trees are swapped
        but the level isn't reloaded: the page already shows the change."""
        if self.cache is None:
            return
        quiet = time.monotonic() < self._own_write_until
        self._gen.value += 1
        for _th, b, _r in self._workers:
            b.cache = type(b.cache)(make_tree(b.cache.tree.root), self.game,
                                    db_path=b.cache.db_path)
        self.tree = make_tree(self.tree.root)
        self._ui_cache = type(self._ui_cache)(self.tree, self.game,
                                              db_path=self._ui_cache.db_path)
        if not quiet:
            self.reload()

    def reload(self) -> None:
        """Drop what is shown and load it again (mods switched on or off)."""
        if self.level:
            self.open_level(self.level, keep_camera=True)

    def open_level(self, level: str, zone: str = "", keep_camera: bool = False) -> None:
        """Show ``level`` (and fly to ``zone`` if given)."""
        from ..convert import mapdata
        if self.cache is None:
            return
        same = level == self.level
        self.level = level
        self._gen.value += 1
        script = self.script_box.currentData() if same else None
        try:
            self.meta = mapdata.overview(self._ui_cache, level, script)
        except Dr2Error as e:
            self.status.emit(str(e))
            return
        if not same:
            self.script_box.blockSignals(True)
            self.script_box.clear()
            for s in self.meta["scripts"]:
                self.script_box.addItem(s, s)
            if not self.meta["scripts"]:
                self.script_box.addItem("(no item files for this level)", None)
            self.script_box.blockSignals(False)
        self._fill_goto()
        self.title.setText(f"<b>{_level_title(level)}</b><br>{len(self.meta['zones'])} "
                           f"zones · {len(self.meta.get('items', []))} items and doors · "
                           f"{sum(1 for m in self.meta['markers'] if m['kind'] == 'spawn')} "
                           f"spawn points")
        self._handler.files.clear() if self.view else None
        meta = dict(self.meta, generation=self._gen.value)
        if meta.get("map") and self.view is not None:
            png = self._map_png(meta["map"]["vpath"])
            if png:
                url = f"/maps/overview-{self.game}.png"
                self._handler.files[url] = png
                floors = []
                for k, f in enumerate(meta["map"].get("floors", [])):
                    fpng = self._map_png(f["vpath"])
                    if fpng:
                        furl = f"/maps/overview-{self.game}-floor{k}.png"
                        self._handler.files[furl] = fpng
                        floors.append(dict(f, url=f"dr2://studio{furl}"))
                meta["map"] = dict(meta["map"], url=f"dr2://studio{url}", floors=floors)
        self._js(f"dr2.openLevel({json.dumps(meta)}, {str(keep_camera and same).lower()})")
        for kind, box in self.layer_boxes.items():
            self._js(f"dr2.setLayer({json.dumps(kind)}, {str(box.isChecked()).lower()})")
        self._hour_changed(self.hour.value())
        if zone:
            self.go_to_zone(zone)

    def _map_png(self, vpath: str) -> bytes | None:
        """The in-game map picture as PNG (made once per game and mod state)."""
        cache = self.__dict__.setdefault("_map_pngs", {})
        key = (self.game, vpath, id(self.tree))
        if key not in cache:
            try:
                from ..convert.model import texture_png
                cache[key] = texture_png(self.tree.resolve(vpath).data(), vpath, 1)
            except Dr2Error:
                cache[key] = None
        return cache[key]

    def go_to_zone(self, zone: str) -> None:
        if not self.meta:
            return
        for z in self.meta["zones"]:
            if z["name"].lower() == zone.lower():
                c = z["centre"]
                self._js(f"dr2.goTo({c[0]}, {z['min'][1] + 2}, {c[2]}, null)")

    def _hour_changed(self, h: int) -> None:
        self.hour_label.setText(f"{h:02d}:00")
        self._js(f"dr2.setHour({h if self.time_box.isChecked() else 'null'})")

    def _script_changed(self, _i) -> None:
        if self.level:
            self.open_level(self.level, keep_camera=True)

    def _fill_goto(self) -> None:
        self.goto_box.clear()
        self.goto_box.addItem("(choose a place)", None)
        for m in self.meta["markers"]:
            p = m.get("position")
            if m["kind"] == "spawn" and p:
                self.goto_box.addItem(f"Spawn point: {m['name']}", (p, m.get("rotation")))
        for m in self.meta["markers"]:
            if m["kind"] == "map_area" and m.get("polygon"):
                poly = m["polygon"]
                c = [sum(v[i] for v in poly) / len(poly) for i in range(3)]
                name = (m.get("label") or m["name"])
                import re
                name = re.sub(r"@\[[^\]]*\]\s*", "", name)
                self.goto_box.addItem(f"Map area: {name}", (c, None))
        for m in self.meta["markers"]:
            if m["kind"] == "map_point" and m.get("position"):
                self.goto_box.addItem(f"Map point: {m.get('label') or m['name']}",
                                      (m["position"], None))
        for z in self.meta["zones"]:
            c = z["centre"]
            self.goto_box.addItem(f"Zone: {z['name']}", ([c[0], z["min"][1] + 2, c[2]], None))

    def _goto(self, i: int) -> None:
        data = self.goto_box.itemData(i)
        if not data:
            return
        (x, y, z), rot = data
        heading = "null"
        if rot:
            heading = repr(2 * math.atan2(rot[1], rot[3]))
        self._js(f"dr2.goTo({x}, {y}, {z}, {heading})")

    # ---- page messages -----------------------------------------------------------------

    def _js(self, code: str) -> None:
        if self.view is None:
            return
        if self.ready:
            self.view.page().runJavaScript(code)
        else:
            self._pending_js.append(code)

    def _message(self, text: str) -> None:
        self.last_message = text
        word, _, rest = text.partition(" ")
        if word == "ready":
            self.ready = True
            for code in self._pending_js:
                self.view.page().runJavaScript(code)
            self._pending_js.clear()
        elif word == "status":
            self.last_status = rest
            self.status.emit(rest)
        elif word == "want":
            req = json.loads(rest)
            req["level"] = self.level
            req["generation"] = self._gen.value
            if self._workers:
                _th, _b, relay = self._workers[self._next % len(self._workers)]
                self._next += 1
                relay.ask.emit(req)
        elif word == "pick":
            self._picked(json.loads(rest))
        elif word == "camera":
            self.camera = json.loads(rest)
        elif word == "edit":
            self._edit(json.loads(rest))
        elif word == "place":
            self._place(json.loads(rest))

    @Slot(dict, str, str)
    def _built(self, req: dict, path: str, err: str) -> None:
        if req.get("generation") != self._gen.value:
            return
        zone, part, detail = (json.dumps(req[k]) for k in ("zone", "part", "detail"))
        if err:
            self.status.emit(f"Maps: {req['zone']} ({req['part']}): {err.splitlines()[-1]}")
            self._js(f"dr2.zoneFailed({zone}, {part}, {detail}, {json.dumps(err.splitlines()[-1])})")
            return
        if not path:
            self._js(f"dr2.zoneReady({zone}, {part}, {detail}, null)")
            return
        self._served += 1
        url_path = f"/maps/{self._served}-{Path(path).name}"
        self._handler.files[url_path] = Path(path)
        self._js(f"dr2.zoneReady({zone}, {part}, {detail}, 'dr2://studio{url_path}')")

    # ---- what was clicked ------------------------------------------------------------

    def _picked(self, info: dict) -> None:
        self.picked = info
        t = info.get("type")
        rows = []
        if t == "none":
            self.info.setHtml("Nothing there (sky or a hidden layer).")
            self._set_actions(None)
            return
        if t == "piece":
            rows = [("A level piece", info.get("name")), ("Zone", info.get("zone")),
                    ("File", info.get("vpath"))]
        elif t == "zombie":
            rows = [("A zombie", info.get("name")), ("Model", info.get("vpath")),
                    ("Crowd of the area", info.get("area")),
                    ("Put there by mission", info.get("mission")),
                    ("In", f"missions.txt, line {info.get('line')}"),
                    ("Note", "the game spreads a crowd itself: these spots are examples")]
        elif t in ("item", "door"):
            rows = [("An item" if t == "item" else "A door", info.get("item")),
                    ("Placed as", info.get("name")),
                    ("Placed by", f"{info.get('file')}" + (f", line {info['line']}"
                                                           if info.get("line") else
                                                           " (by your mod)")),
                    ("Model", info.get("vpath"))]
        else:
            from ..convert.placed import LAYERS
            kind = info.get("kind", "")
            rows = [(LAYERS.get(kind, kind).rstrip("s"), info.get("label") or info.get("name")),
                    ("Name", info.get("name")),
                    ("Placed by", f"{info.get('file')}, line {info.get('line')}")]
            for k, v in (info.get("props") or {}).items():
                if not k.startswith("Vertex"):
                    rows.append((k, v))
        pv = getattr(self.window, "preview", None)
        if pv is not None and info.get("vpath"):
            by = pv.changed(info["vpath"])
            if by:
                rows.insert(1, ("Changed by mod", ", ".join(by) + (
                    "" if self.window.mods_action.isChecked() else " (not shown: Ctrl+M)")))
        if info.get("point"):
            rows.append(("Clicked at", " ".join(f"{c:.2f}" for c in info["point"])))
        self.info.setHtml("<table>" + "".join(
            f"<tr><td><b>{_esc(k)}</b>&nbsp;</td><td>{_esc(v)}</td></tr>" for k, v in rows
            if v not in (None, "")) + "</table>")
        self._set_actions(info.get("vpath") if t in ("piece", "item", "door", "zombie") else None)
        self._show_edit_target(info if t in ("item", "door") else None)

    def _set_actions(self, vpath: str | None) -> None:
        for b in (self.btn_library, self.btn_blender, self.btn_export):
            b.setEnabled(vpath is not None)

    def _open_in_library(self) -> None:
        if self.picked and self.picked.get("vpath"):
            self.open_asset.emit(self.picked["vpath"])

    def _export_glb(self) -> None:
        if not (self.picked and self.picked.get("vpath")):
            return
        vp = self.picked["vpath"]
        stem = (self.picked.get("item") or self.picked.get("name") or "model")
        path, _ = QFileDialog.getSaveFileName(self, "Export glTF binary", stem + ".glb",
                                              "glTF binary (*.glb)")
        if not path:
            return
        from ..convert.model import export_glb
        Path(path).write_bytes(export_glb(self.tree, vp, game=self.game, mode="shown"))
        self.status.emit(f"exported {vp} -> {path}")

    def _open_in_blender(self) -> None:
        if not (self.picked and self.picked.get("vpath")):
            return
        vp = self.picked["vpath"]
        from ..convert.model import export_glb
        from .edit_tools import open_in_blender
        try:
            glb = export_glb(self.tree, vp, game=self.game)
            mod_dir = getattr(self.window, "mod_dir", None)
            open_in_blender(self.game, vp, glb, mod_dir)
        except Dr2Error as e:
            self.status.emit(str(e))
            return
        self.status.emit(f"Blender is starting with {vp}")

    def current_zone(self) -> str | None:
        """The zone the camera is in (the smallest holding it), or None."""
        if not (self.level and self.camera and self._ui_cache):
            return None
        from ..convert import level as clevel
        L = self._ui_cache.level(self.level)
        z = clevel.zone_of(self.camera["position"], L.zones)
        return z.zone if z else None

    def export(self, whole_level: bool, folder: str | None = None) -> None:
        """*Export zone… / Export level…*: `catalog.level_export` into a folder, in the
        background (the log says what is written)."""
        if not self.level:
            return
        zone = None if whole_level else self.current_zone()
        if not whole_level and zone is None:
            self.status.emit("Maps: fly into a zone first (or use Export level…)")
            return
        if folder is None:
            folder = QFileDialog.getExistingDirectory(self, "Export the level into")
            if not folder:
                return
        game, level, root = self.game, self.level, self.tree.root
        script = self.script_box.currentData()
        layers = {k for k, b in self.layer_boxes.items() if b.isChecked()}
        from ..catalog.level_export import DEFAULT_MARKERS
        markers = tuple(k for k in DEFAULT_MARKERS + ("light_area", "sound_area")
                        if k in layers)
        items = "items" in layers

        def work(progress):
            from ..catalog.level_export import export_level
            return export_level(AssetTree(root, cache_size=32), game, level, folder,
                                zones=[zone] if zone else None, script=script,
                                items=items, markers=markers,
                                progress=lambda d, t, w: progress(f"export {level}: "
                                                                  f"[{d + 1}/{t}] {w}"))

        def done(res, err):
            if err:
                self.status.emit(f"export failed: {err.splitlines()[-1]}")
                if hasattr(self.window, "error"):
                    self.window.error(err)
                return
            self.status.emit(f"exported {len(res.files)} files to {res.folder}")
            if hasattr(self.window, "say"):
                self.window.say(f"Maps: exported {level} ({zone or 'every zone'}): "
                                f"{len(res.files)} files, {res.pieces} pieces, {res.items} "
                                f"items, {res.markers} markers -> {res.folder}")
                for a, b in res.failed:
                    self.window.say(f"  not exported: {a}: {b}")
        if hasattr(self.window, "run_job"):
            self.window.run_job(work, done)
        else:                                     # no window (tests): right away
            try:
                done(work(lambda _t: None), None)
            except Dr2Error as e:
                done(None, str(e))

    def _copy_position(self) -> None:
        from PySide6.QtWidgets import QApplication
        if self.camera:
            p = self.camera["position"]
            text = f"{p[0]:.2f}, {p[1]:.2f}, {p[2]:.2f}"
            QApplication.clipboard().setText(text)
            self.status.emit(f"camera position copied: {text}")

    # ---- editing (phase 11) -------------------------------------------------------------

    def _build_edit_panel(self, sl) -> None:
        self._own_write_until = 0.0
        self.editor = None                        # maps_edit.LevelEditor of the open mod
        self._editor_key = None
        self._target: dict | None = None          # {file, name} being edited
        self._adding: str | None = None           # the item waiting for dr2:place
        self._usable: list[str] | None = None
        sl.addWidget(QLabel("<b>Edit</b>"))
        self.edit_box = QCheckBox("Edit items and doors (move, turn, add, delete)")
        self.edit_box.setToolTip("Click an item or door, then drag its handles (T move, "
                                 "R turn, F onto the floor, Delete, Ctrl+D copy, Ctrl+Z "
                                 "undo). Saved into the mod open in the bottom bar.")
        self.edit_box.toggled.connect(self._edit_toggled)
        sl.addWidget(self.edit_box)
        self.edit_mod = QLabel()
        self.edit_mod.setWordWrap(True)
        sl.addWidget(self.edit_mod)
        grid = QGridLayout()
        self.ed_item = QLineEdit()
        self.ed_item.setToolTip("What it is: an item of items.txt (a bench → Chair_3…)")
        self.ed_item.editingFinished.connect(self._item_typed)
        grid.addWidget(QLabel("Item"), 0, 0)
        grid.addWidget(self.ed_item, 0, 1, 1, 3)
        self.ed_pos = []
        for i, axis in enumerate("xyz"):
            sb = QDoubleSpinBox()
            sb.setRange(-5000, 5000)
            sb.setDecimals(3)
            sb.setSingleStep(0.1)
            sb.setToolTip(f"{axis} in metres (y is up)")
            sb.editingFinished.connect(self._fields_changed)
            grid.addWidget(sb, 1, i + 1)
            self.ed_pos.append(sb)
        grid.addWidget(QLabel("Place"), 1, 0)
        self.ed_turn = QDoubleSpinBox()
        self.ed_turn.setRange(-360, 360)
        self.ed_turn.setDecimals(1)
        self.ed_turn.setSingleStep(15)
        self.ed_turn.setSuffix("°")
        self.ed_turn.setToolTip("Its turn about the up axis")
        self.ed_turn.editingFinished.connect(self._fields_changed)
        grid.addWidget(QLabel("Turn"), 2, 0)
        grid.addWidget(self.ed_turn, 2, 1)
        sl.addLayout(grid)
        row = QHBoxLayout()
        self.btn_floor = QPushButton("Onto floor")
        self.btn_floor.setToolTip("Drop it onto the floor below (the collision mesh): F")
        self.btn_floor.clicked.connect(lambda: self._js("window.dispatchEvent(new KeyboardEvent"
                                                        "('keydown', {code: 'KeyF'}))"))
        self.btn_dup = QPushButton("Copy")
        self.btn_dup.setToolTip("Another one beside it: Ctrl+D")
        self.btn_dup.clicked.connect(lambda: self._target and self._edit(
            {"op": "duplicate", **self._target}))
        self.btn_del = QPushButton("Delete")
        self.btn_del.setToolTip("Take it out of the level: Delete")
        self.btn_del.clicked.connect(lambda: self._target and self._edit(
            {"op": "delete", **self._target}))
        for b in (self.btn_floor, self.btn_dup, self.btn_del):
            row.addWidget(b)
        sl.addLayout(row)
        row = QHBoxLayout()
        self.btn_add = QPushButton("Add item…")
        self.btn_add.setToolTip("Choose an item, it goes where the middle of the view "
                                "meets the floor")
        self.btn_add.clicked.connect(self._add_item)
        self.btn_undo = QPushButton("Undo")
        self.btn_undo.clicked.connect(lambda: self._edit({"op": "undo"}))
        self.btn_redo = QPushButton("Redo")
        self.btn_redo.clicked.connect(lambda: self._edit({"op": "redo"}))
        for b in (self.btn_add, self.btn_undo, self.btn_redo):
            row.addWidget(b)
        sl.addLayout(row)
        self._refresh_edit_panel()

    def _mod_dir(self):
        return getattr(self.window, "mod_dir", None)

    def _get_editor(self):
        """The editor of the open mod (made again when the mod or the game changes)."""
        from ..mods.deploy import recomp_folders
        from .maps_edit import LevelEditor
        mod = self._mod_dir()
        if mod is None or self.tree is None:
            self.editor = None
            return None
        key = (str(mod), self.game)
        if self.editor is None or self._editor_key != key:
            root = self.tree.root
            patched = recomp_folders(root)["patched"]
            self.editor = LevelEditor(AssetTree(root), mod,
                                      [patched] if patched.is_dir() else [])
            self._editor_key = key
        return self.editor

    def _refresh_edit_panel(self) -> None:
        mod = self._mod_dir()
        on = self.edit_box.isChecked()
        if mod is None:
            self.edit_mod.setText("Open or create a mod (bottom bar) to save edits.")
        else:
            n = self.editor.count() if self.editor is not None else 0
            self.edit_mod.setText(f"Saved into the mod <b>{Path(mod).name}</b>"
                                  + (f": {n} change{'s' if n != 1 else ''} to the level "
                                     f"files" if n else ""))
        has = on and self._target is not None
        for w in (self.ed_item, self.ed_turn, self.btn_floor, self.btn_dup, self.btn_del,
                  *self.ed_pos):
            w.setEnabled(has)
        self.btn_add.setEnabled(on and mod is not None and bool(self.level))
        ed = self.editor
        self.btn_undo.setEnabled(on and ed is not None and ed.can_undo())
        self.btn_redo.setEnabled(on and ed is not None and ed.can_redo())

    def _edit_toggled(self, on: bool) -> None:
        if on and self._mod_dir() is None:
            ensure = getattr(self.window, "ensure_mod", None)
            if ensure is None or not ensure():
                self.edit_box.blockSignals(True)
                self.edit_box.setChecked(False)
                self.edit_box.blockSignals(False)
                self._refresh_edit_panel()
                return
        if on:
            self._get_editor()
        self._js(f"dr2.setEditing({str(on).lower()})")
        if not on:
            self._target = None
        self._refresh_edit_panel()

    def _show_edit_target(self, info: dict | None) -> None:
        """Fill the edit fields with what was clicked (an item or a door)."""
        self._target = None
        ed = self.editor if self.edit_box.isChecked() else None
        if ed is not None and info and info.get("file") and info.get("name"):
            try:
                st = ed.state(info["file"], info["name"])
            except Dr2Error:
                st = None
            if st is not None:
                self._target = {"file": info["file"], "name": info["name"]}
                self._fill_fields(st)
        self._refresh_edit_panel()

    def _fill_fields(self, st) -> None:
        from .maps_edit import yaw_of
        self.ed_item.setText(st.item or "")
        for sb, v in zip(self.ed_pos, st.position or (0, 0, 0)):
            sb.blockSignals(True)
            sb.setValue(v)
            sb.blockSignals(False)
        self.ed_turn.blockSignals(True)
        self.ed_turn.setValue(round(yaw_of(st.rotation or (0, 0, 0, 1)), 1))
        self.ed_turn.blockSignals(False)
        self._shown_turn = self.ed_turn.value()
        if self.ed_item.completer() is None and self.editor is not None:
            c = QCompleter(sorted(b.name for b in self.editor.models.blocks.values()), self)
            c.setCaseSensitivity(Qt.CaseInsensitive)
            c.setFilterMode(Qt.MatchContains)
            self.ed_item.setCompleter(c)

    def _fields_changed(self) -> None:
        """Place or turn typed in the panel."""
        if not self._target or self.editor is None:
            return
        from .maps_edit import yaw_quaternion
        st = self.editor.state(**self._target)
        if st is None:
            return
        pos = tuple(sb.value() for sb in self.ed_pos)
        rot = st.rotation
        delta = self.ed_turn.value() - getattr(self, "_shown_turn", self.ed_turn.value())
        if abs(delta) > 1e-6:                     # turn by the difference: keep any tilt
            qy = yaw_quaternion(delta)
            rot = _qmul(qy, rot)
        if all(abs(a - b) < 5e-4 for a, b in zip(pos, st.position or pos)) and rot == st.rotation:
            return
        self._edit({"op": "move", **self._target, "position": pos, "rotation": rot})

    def _item_typed(self) -> None:
        if not self._target or self.editor is None:
            return
        text = self.ed_item.text().strip()
        st = self.editor.state(**self._target)
        if st is None or not text or text.lower() == (st.item or "").lower():
            return
        self._edit({"op": "item", **self._target, "item": text})

    def usable_items(self) -> list[str]:
        """Items whose model ships in this game, by name (for *Add item…*)."""
        if self._usable is None:
            ed = self._get_editor()
            if ed is None:
                return []
            self._usable = sorted((b.name for b in ed.models.blocks.values()
                                   if ed.models.resolve(b.name)), key=str.lower)
        return self._usable

    def _add_item(self) -> None:
        names = self.usable_items()
        if not names:
            return
        item, ok = QInputDialog.getItem(self, "Add an item", "Item (type to search):",
                                        names, 0, True)
        if not ok or not item:
            return
        self._adding = item
        self._js("dr2.askPlace()")

    def _place(self, msg: dict) -> None:
        if not self._adding:
            return
        item, self._adding = self._adding, None
        script = self.script_box.currentData() or self.level
        self._edit({"op": "add", "file": f"{script}.txt", "item": item,
                    "position": msg["point"]})

    def _edit(self, msg: dict) -> None:
        """One change from the page or the panel: apply, save, tell the page."""
        ed = self._get_editor() if self.edit_box.isChecked() else None
        if ed is None:
            return
        op = msg.get("op")
        try:
            if op == "move":
                states = ed.move(msg["file"], msg["name"], msg["position"], msg.get("rotation"))
            elif op == "delete":
                states = ed.delete(msg["file"], msg["name"])
            elif op == "duplicate":
                name, states = ed.duplicate(msg["file"], msg["name"])
                self._target = {"file": msg["file"], "name": name}
            elif op == "add":
                name, states = ed.add(msg["file"], msg["item"], msg["position"])
                self._target = {"file": msg["file"], "name": name}
            elif op == "item":
                states = ed.set_item(msg["file"], msg["name"], msg["item"])
            elif op == "undo":
                states = ed.undo()
            elif op == "redo":
                states = ed.redo()
            else:
                return
        except Dr2Error as e:
            self.status.emit(f"Maps: {e}")
            if self._target:
                st = ed.state(**self._target)
                if st is not None:                # put the page back where the file is
                    self._send_states([st])
            return
        self._own_write_until = time.monotonic() + 5.0
        self._send_states(states)
        if self._target:
            st = ed.state(**self._target)
            if st is None:
                self._target = None
            else:
                self._fill_fields(st)
        what = {"move": "moved", "delete": "deleted", "duplicate": "copied", "add": "added",
                "item": "changed", "undo": "undone", "redo": "redone"}[op]
        names = ", ".join(s.name for s in states) or "nothing"
        self.status.emit(f"Maps: {what} {names} (saved into {Path(ed.mod_dir).name})")
        self._refresh_edit_panel()
        if hasattr(self.window, "_refresh_mod"):      # the bottom bar's list of changes
            self.window._refresh_mod()

    def _send_states(self, states) -> None:
        from .maps_edit import item_glb
        out = []
        for st in states:
            d = st.to_dict()
            if st.new_model and not st.removed:
                data = item_glb(AssetTree(self.tree.root), self.game, st)
                if data:
                    self._served += 1
                    url_path = f"/maps/{self._served}-edit-{st.name}.glb"
                    self._handler.files[url_path] = data
                    d["url"] = f"dr2://studio{url_path}"
                else:
                    self.status.emit(f"Maps: {st.item}: no model in this game, so it can't "
                                     f"be shown")
            out.append(d)
        if out:
            self._js(f"dr2.itemState({json.dumps(out)})")

    def shutdown(self) -> None:
        """Stop the builder threads (the window is closing): what they are building is
        finished (a few seconds at most), then they end."""
        self._gen.value += 1
        for th, _b, _r in self._workers:
            th.quit()
        for th, _b, _r in self._workers:
            th.wait(30000)
        self._workers.clear()


if model_view.WEB_ENGINE:
    from PySide6.QtWebEngineCore import QWebEnginePage

    class _MapsPage(QWebEnginePage):
        """The ``dr2:`` lines go to the view; the page's own errors (a shader that
        doesn't compile, a file that doesn't load) are kept in ``errors`` and shown."""
        def __init__(self, profile, on_message, parent):
            super().__init__(profile, parent)
            self._on_message = on_message
            self.errors: list[str] = []

        def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802
            if message.startswith("dr2:"):
                self._on_message(message[4:])
            elif level != QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel:
                self.errors.append(f"{source.rsplit('/', 1)[-1]}:{line}: {message}")
                del self.errors[:-50]


class _Ask(QObject):
    """Sends one builder its requests (a signal per builder, so each request goes to
    exactly one thread)."""
    ask = Signal(dict)


def _esc(v) -> str:
    import html
    return html.escape(str(v))


def _qmul(a, b):
    """The quaternion ``a × b`` (turn by ``b``, then by ``a``), ``x, y, z, w``."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)

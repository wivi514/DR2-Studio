"""DR2 Studio's **Maps** tab (phase 10 step 3): a level in 3D, its items and markers.

Two widgets, wired by `app.MainWindow`:

* `MapsList`, the left tab: the game's levels, each with its zones (double-click a zone
  to fly there).
* `MapsView`: the Maps page (``web/maps.html`` + ``maps.js``, three.js in a
  QWebEngineView, the same ``dr2:`` scheme as the 3D view, `model_view`) and four panels
  the window puts in dock windows of their own (each can be moved, resized, or floated
  as a window): ``tools_panel`` (*Map*), ``inspector``, ``hierarchy`` and ``palette``
  (*Place*; `maps_panels`). *Map*: which level script's items to show, the **Layers**
  (pieces, items and doors,
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

**Editing** (phase 11, `studio.maps_edit`): with *Edit* ticked, a clicked item, door,
zombie or building gets move / turn (/ size, buildings) handles and its name, position,
rotation and size in the **Inspector**; arrow keys nudge it. Every change goes into the
**mod being edited** (the bottom bar's open mod) as ``.edits.json`` (items, doors,
zombies) or ``.pieces.json`` (buildings) through `maps_edit.LevelEditor`, and the page is
told what changed (``dr2.itemState``, ``dr2.pieceState``) instead of rebuilding the
level. **Place** rows are dragged onto the 3D view (an event filter on the view takes the
drop and asks the page for the floor point under the mouse, ``dr2.placeAt``) or
double-clicked; the **Hierarchy** lists what the level holds and flies to a clicked row
(``dr2.focus``). The file watcher's refresh that follows a save swaps the trees without
reloading the level (`use_tree`, ``_own_write_until``).

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

from PySide6.QtCore import QEvent, QObject, Qt, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtWidgets import (QCheckBox, QComboBox, QCompleter, QDoubleSpinBox, QFileDialog,
                               QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QPushButton, QTextBrowser, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..container.vpath import AssetTree
from ..errors import Dr2Error
from . import model_view

PAGE_URL = "dr2://studio/maps.html"
ZOMBIE_OPS = ("zmove", "zdelete", "zset", "crowd", "zadd")
PIECE_OPS = ("pmove", "phide", "pshow", "prestore", "pcopy")
ROLE = Qt.UserRole + 1

# The layers in the order the panel lists them, with whether they start on.
LAYER_ORDER = [("pieces", "Buildings (level pieces)", True),
               ("items", "Items and doors", True),
               ("spawn", "Spawn points", True),
               ("map_area", "Map areas", True),
               ("map_point", "Map points (workbenches, save points)", True),
               ("zombie_area", "Zombie areas", False),
               ("zombies", "Zombies (crowds the missions put in the areas)", False),
               ("zombie_spawn", "Zombie spawns (single zombies, respawns, clearings)", False),
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
            self.view.setAcceptDrops(True)
            self.view.installEventFilter(self)       # drops from the Place panel
            self.view.loadFinished.connect(self._watch_drops)
            outer.addWidget(self.view, 1)
        else:
            why = model_view.WEB_ENGINE_ERROR or "the dr2: scheme could not be registered"
            from types import SimpleNamespace
            self._handler = SimpleNamespace(files={})   # what the page would be served
            note = QLabel("The Maps view needs PySide6's QtWebEngine (" + why + ").\n\n"
                          "dr2 level and the exports still work.")
            note.setWordWrap(True)
            outer.addWidget(note, 1)

        from .maps_panels import HierarchyPanel, PlacePanel
        self.tools_panel = QWidget()             # "Map": layers, go to, what is this
        sl = QVBoxLayout(self.tools_panel)
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
        self.inspector = QWidget()               # the selected thing, editable
        il = QVBoxLayout(self.inspector)
        self._build_edit_panel(il)
        il.addStretch(1)
        self.hierarchy = HierarchyPanel()
        self.hierarchy.chosen.connect(self.focus)
        self.palette = PlacePanel()
        self.palette.place.connect(lambda spec: self.start_place(spec))
        self.palette.arm.connect(lambda spec: self.start_place(spec, arm=True))
        self._level_zones: dict[str, object] | None = None   # zone name -> ZoneData
        self._hier_timer = QTimer(self)
        self._hier_timer.setSingleShot(True)
        self._hier_timer.setInterval(250)
        self._hier_timer.timeout.connect(self.fill_hierarchy)
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
        self._level_zones = None
        self.palette.set_source(self.place_rows, self.picture)
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
        if not same:
            self._level_zones = None
            self.palette.forget("piece")
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
        if self.edit_box.isChecked():
            self.sync_edits()
        self._hier_timer.start()

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
        elif word == "drop":                       # a Place row dropped on the view
            msg = json.loads(rest)
            self.start_place(msg["spec"], point=msg["point"])
        elif word == "placecancel":
            self._adding = None

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
        elif t == "marker" and info.get("kind") == "zombie_spawn":
            p = info.get("props") or {}
            what = {"single": "Single zombie(s)", "crate": "Respawns zombies",
                    "removal": "Clears zombies"}.get(info.get("spawn"), "Zombies")
            rows = [(what, p.get("ZombieType") or p.get("ShapeName") or ""),
                    ("How many", p.get("NumberOfZombies") or p.get("ZombiesPerSpawnTime")),
                    ("Holds", p.get("SpawnWithItem")), ("Radius", p.get("Radius")),
                    ("Mission", info.get("mission")),
                    ("When", "after a timer or a cinematic of the mission"
                     if info.get("when") else "when the level is ready"),
                    ("In", f"missions.txt, line {info.get('line')}")]
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
        if t == "piece":
            self._target = None
            self._show_piece_target(info)
        else:
            self._ptarget = None
            self._show_edit_target(info if t in ("item", "door") else None)
        self._show_zombie_target(info)
        self._btarget = None
        if self.edit_box.isChecked() and t == "marker" and info.get("cls") in (
                "cTriggerVolume", "cSpawnPoint") and info.get("file") and info.get("name"):
            self._btarget = {"file": info["file"], "path": f"{info['cls']} {info['name']}",
                             "added": bool(info.get("added"))}
            self.btn_del.setEnabled(self._btarget["added"])
            self.btn_settings.setEnabled(True)

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
        self._ptarget: dict | None = None         # {zone, name}: a building being edited
        self._adding: str | None = None           # the item waiting for dr2:place
        self._usable: list[str] | None = None
        self.edit_box = QCheckBox("Edit the level (move, turn, add, delete)")
        self.edit_box.setToolTip("Click an item, door, zombie or building, then drag its "
                                 "handles or use the keys: arrows nudge it, Page Up / Down "
                                 "up and down, [ ] turn, - = size (buildings); T move, R "
                                 "turn, G size, F onto the floor, Delete, Ctrl+D copy, "
                                 "Ctrl+Z undo. Shift: bigger steps, Alt: smaller. Saved "
                                 "into the mod open in the bottom bar.")
        self.edit_box.toggled.connect(self._edit_toggled)
        sl.addWidget(self.edit_box)
        self.edit_mod = QLabel()
        self.edit_mod.setWordWrap(True)
        sl.addWidget(self.edit_mod)
        self.sel_label = QLabel("Nothing selected: click something in the 3D view or "
                                "the Hierarchy.")
        self.sel_label.setWordWrap(True)
        sl.addWidget(self.sel_label)
        grid = QGridLayout()
        self.ed_item = QLineEdit()
        self.ed_item.setToolTip("What it is: an item of items.txt (a bench → Chair_3…)")
        self.ed_item.editingFinished.connect(self._item_typed)
        self.ed_item_label = QLabel("Item")
        grid.addWidget(self.ed_item_label, 0, 0)
        grid.addWidget(self.ed_item, 0, 1, 1, 3)

        def spin(lo, hi, decimals, step, tip, suffix=""):
            sb = QDoubleSpinBox()
            sb.setRange(lo, hi)
            sb.setDecimals(decimals)
            sb.setSingleStep(step)
            sb.setSuffix(suffix)
            sb.setToolTip(tip)
            sb.setKeyboardTracking(False)
            sb.editingFinished.connect(self._fields_changed)
            return sb
        self.ed_pos = [spin(-5000, 5000, 3, 0.1, f"{a} in metres (y is up); the arrow keys "
                            f"in the 3D view nudge it too") for a in "xyz"]
        self.ed_rot = [spin(-360, 360, 1, 15, f"Turn about {a} in degrees" + (
            " (its heading)" if a == "y" else " (a tilt)"), "°") for a in "xyz"]
        self.ed_turn = self.ed_rot[1]              # the heading (zombies have only this)
        self.ed_scale = [spin(0.01, 100, 3, 0.1, f"Size along {a} (1 = as the game has it; "
                              f"buildings only: the game's items have no size)")
                         for a in "xyz"]
        for r, (label, boxes) in enumerate((("Position", self.ed_pos),
                                            ("Rotation", self.ed_rot),
                                            ("Size", self.ed_scale)), start=1):
            grid.addWidget(QLabel(label), r, 0)
            for i, sb in enumerate(boxes):
                grid.addWidget(sb, r, i + 1)
        self.same_size = QCheckBox("Same size in every direction")
        self.same_size.setChecked(True)
        grid.addWidget(self.same_size, 4, 1, 1, 3)
        sl.addLayout(grid)
        row = QHBoxLayout()
        self.mode_btns = {}
        for mode, text, key in (("translate", "Move", "T"), ("rotate", "Turn", "R"),
                                ("scale", "Size", "G")):
            b = QPushButton(f"{text} ({key})")
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setToolTip(f"The handles in the 3D view {text.lower()} the selection (key {key})")
            b.clicked.connect(lambda _c=False, m=mode: self._js(f"dr2.setGizmo('{m}')"))
            self.mode_btns[mode] = b
            row.addWidget(b)
        self.mode_btns["translate"].setChecked(True)
        sl.addLayout(row)
        self.whole_box = QCheckBox("Whole building (all its parts and its collision)")
        self.whole_box.setChecked(True)
        self.whole_box.setToolTip("A building is several pieces (walls, boarded windows, signs, "
                                  "writing…) and a collision shape: on, a click selects all of "
                                  "it and they move, hide and copy together. Off: one piece "
                                  "alone (its collision stays)")
        self.whole_box.toggled.connect(lambda _on: self._reselect_piece())
        sl.addWidget(self.whole_box)
        self.part_of_row = QWidget()
        prow = QHBoxLayout(self.part_of_row)
        prow.setContentsMargins(0, 0, 0, 0)
        prow.addWidget(QLabel("Part of"))
        self.part_of = QComboBox()
        self.part_of.setToolTip("Which building this piece belongs to. Studio guesses from "
                                "shapes and names; put it right here (kept for next time)")
        self.part_of.activated.connect(self._part_of_changed)
        prow.addWidget(self.part_of, 1)
        self.part_of_row.setVisible(False)
        sl.addWidget(self.part_of_row)
        self.tilt_box = QCheckBox("Turn handles tilt too (every axis)")
        self.tilt_box.setToolTip("Off: the turn handle only turns about the up axis, which "
                                 "is what most things need")
        self.tilt_box.toggled.connect(lambda on: self._js(f"dr2.setRotateAll({str(on).lower()})"))
        sl.addWidget(self.tilt_box)
        row = QHBoxLayout()
        self.btn_floor = QPushButton("Onto floor")
        self.btn_floor.setToolTip("Drop it onto the floor below (the collision mesh): F")
        self.btn_floor.clicked.connect(lambda: self._js("window.dispatchEvent(new KeyboardEvent"
                                                        "('keydown', {code: 'KeyF'}))"))
        self.btn_dup = QPushButton("Copy")
        self.btn_dup.setToolTip("Another one beside it: Ctrl+D")
        self.btn_dup.clicked.connect(self._copy_clicked)
        self.btn_del = QPushButton("Delete")
        self.btn_del.setToolTip("Take it out of the level (a building is hidden): Delete")
        self.btn_del.clicked.connect(self._delete_clicked)
        self.btn_putback = QPushButton("Put back")
        self.btn_putback.setToolTip("A building back as the game has it (shown, in its place, "
                                    "its size)")
        self.btn_putback.clicked.connect(self._put_back)
        for b in (self.btn_floor, self.btn_dup, self.btn_del, self.btn_putback):
            row.addWidget(b)
        sl.addLayout(row)
        self.z_panel = QWidget()
        zg = QGridLayout(self.z_panel)
        zg.setContentsMargins(0, 0, 0, 0)
        self.z_type = QLineEdit()
        self.z_type.setToolTip("Which zombie (a model of data/models/zombies.big)")
        self.z_type.editingFinished.connect(self._zombie_fields)
        from PySide6.QtWidgets import QSpinBox
        self.z_count = QSpinBox()
        self.z_count.setRange(0, 200)
        self.z_count.setToolTip("How many (0: none; the game's own zombies are taken out "
                                "this way, which keeps saves working)")
        self.z_count.editingFinished.connect(self._zombie_fields)
        self.z_item = QLineEdit()
        self.z_item.setToolTip("An item it holds (HandGun…), empty for none")
        self.z_item.editingFinished.connect(self._zombie_fields)
        zg.addWidget(QLabel("Zombie"), 0, 0)
        zg.addWidget(self.z_type, 0, 1)
        zg.addWidget(QLabel("×"), 0, 2)
        zg.addWidget(self.z_count, 0, 3)
        zg.addWidget(QLabel("Holds"), 1, 0)
        zg.addWidget(self.z_item, 1, 1, 1, 3)
        sl.addWidget(self.z_panel)
        self.crowd_panel = QWidget()
        cg = QVBoxLayout(self.crowd_panel)
        cg.setContentsMargins(0, 0, 0, 0)
        self.crowd_label = QLabel()
        self.crowd_label.setWordWrap(True)
        self.crowd_types = QLineEdit()
        self.crowd_types.setToolTip("Types and how many: zombie_fat 15, zombie_skinny 10")
        self.crowd_types.editingFinished.connect(self._crowd_typed)
        cg.addWidget(self.crowd_label)
        cg.addWidget(self.crowd_types)
        sl.addWidget(self.crowd_panel)
        self._ztarget: dict | None = None         # {kind: single|removal|crowd, path}
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
        self.btn_add_zombie = QPushButton("Add zombie…")
        self.btn_add_zombie.setToolTip("New zombies where the middle of the view meets the "
                                       "floor. They go in your mod's own mission, so they "
                                       "appear in a new game (docs: 19-edit-a-level)")
        self.btn_add_zombie.clicked.connect(self._add_zombie)
        sl.addWidget(self.btn_add_zombie)
        row = QHBoxLayout()
        self.btn_prefab = QPushButton("Add from prefab…")
        self.btn_prefab.setToolTip("A save point, a workbench, a door to another level, a "
                                   "spawn point, a blocker… copied from the game's own, "
                                   "so it works like them")
        self.btn_prefab.clicked.connect(self._add_prefab)
        self.btn_settings = QPushButton("Settings…")
        self.btn_settings.setToolTip("Every setting of the selected thing as text (a door's "
                                     "Level, an item's flags…)")
        self.btn_settings.clicked.connect(self._settings)
        self.btn_save_prefab = QPushButton("Save as prefab…")
        self.btn_save_prefab.setToolTip("Keep the selected item (with its settings) as your "
                                        "own prefab, to place again or share")
        self.btn_save_prefab.clicked.connect(self._save_prefab)
        for b in (self.btn_prefab, self.btn_settings, self.btn_save_prefab):
            row.addWidget(b)
        sl.addLayout(row)
        self.btn_new_item = QPushButton("New item from this…")
        self.btn_new_item.setToolTip("Your own item, made from the selected one: a new name, "
                                     "its own model (optionally the shape of a .glb from "
                                     "Blender); placed beside it")
        self.btn_new_item.clicked.connect(self._new_item)
        sl.addWidget(self.btn_new_item)
        self._btarget: dict | None = None         # {file, path}: a picked trigger / spawn
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
                                      [patched] if patched.is_dir() else [], game=self.game)
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
                                  + (f": {n} change{'s' if n != 1 else ''} to the level"
                                     if n else ""))
        has = on and self._target is not None
        piece = self._ptarget if on else None
        z = self._ztarget if on else None
        self.ed_item.setEnabled(has)
        self.ed_item.setVisible(not piece)
        self.ed_item_label.setVisible(not piece)
        self.btn_dup.setEnabled(has or piece is not None)
        movable = has or piece is not None or (z is not None and z["kind"] in ("single", "removal"))
        for w in (self.btn_floor, *self.ed_pos):
            w.setEnabled(movable)
        self.ed_turn.setEnabled(has or piece is not None or (z is not None and z["kind"] == "single"))
        for w in (self.ed_rot[0], self.ed_rot[2]):
            w.setEnabled(has or piece is not None)
        for w in (*self.ed_scale, self.same_size):
            w.setEnabled(piece is not None)
        self.mode_btns["scale"].setEnabled(piece is not None)
        hidden = False
        if piece is not None and self.editor is not None:
            st = self._piece_state()
            hidden = bool(st and st.hidden)
        self.btn_del.setText("Show" if hidden else "Delete")
        self.btn_del.setEnabled(has or piece is not None or (z is not None and z["kind"] == "single"))
        self.btn_putback.setVisible(piece is not None)
        self.btn_putback.setEnabled(piece is not None and "#" not in piece["name"])
        self.whole_box.setEnabled(piece is not None or on)
        self.z_panel.setVisible(z is not None and z["kind"] == "single")
        self.crowd_panel.setVisible(z is not None and z["kind"] == "crowd")
        self.btn_add_zombie.setEnabled(on and mod is not None and bool(self.level))
        self.btn_prefab.setEnabled(on and mod is not None and bool(self.level))
        self.btn_settings.setEnabled(on and (self._target is not None or
                                             self._btarget is not None))
        self.btn_save_prefab.setEnabled(on and self._target is not None)
        self.btn_new_item.setEnabled(on and self._target is not None)
        self.btn_add.setEnabled(on and mod is not None and bool(self.level))
        ed = self.editor
        self.btn_undo.setEnabled(on and ed is not None and ed.can_undo())
        self.btn_redo.setEnabled(on and ed is not None and ed.can_redo())
        if not on:
            self.sel_label.setText("Tick <b>Edit the level</b> to change what you select.")
        elif piece is not None and piece.get("group"):
            b = self._building()
            self.sel_label.setText(f"<b>Building</b> {_esc(piece['name'])} (zone "
                                   f"{_esc(piece['zone'])}): {len(b.parts) if b else 1} parts, "
                                   f"{len(b.shapes) if b else 0} collision shapes"
                                   + (" — hidden" if hidden else ""))
        elif piece is not None:
            self.sel_label.setText(f"<b>Building part</b> {_esc(piece['name'])} (zone "
                                   f"{_esc(piece['zone'])})" + (" — hidden" if hidden else "")
                                   + "<br><small>its collision stays where it is</small>")
        elif has:
            self.sel_label.setText(f"<b>Placed</b> {_esc(self._target['name'])} "
                                   f"({_esc(self._target['file'])})")
        elif z is not None:
            self.sel_label.setText({"single": "<b>Single zombie(s)</b>",
                                    "removal": "<b>Clearing</b> (removes zombies around it)",
                                    "crowd": "<b>Zombie crowd</b>"}.get(z["kind"], ""))
        else:
            self.sel_label.setText("Nothing selected: click something in the 3D view or "
                                   "the Hierarchy, or drag something from Place.")

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
        if on:
            self.sync_edits()
        if not on:
            self._target = None
            self._ptarget = None
        self._refresh_edit_panel()
        self._hier_timer.start()

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
                self._ptarget = None
                self._fill_fields(st)
        self._refresh_edit_panel()

    def _set_boxes(self, boxes, values) -> None:
        for sb, v in zip(boxes, values):
            sb.blockSignals(True)
            sb.setValue(v)
            sb.blockSignals(False)

    def _fill_fields(self, st) -> None:
        from .maps_edit import euler_of
        self.ed_item.setText(st.item or "")
        self._set_boxes(self.ed_pos, st.position or (0, 0, 0))
        self._shown_rot = tuple(round(a, 1) for a in euler_of(st.rotation or (0, 0, 0, 1)))
        self._set_boxes(self.ed_rot, self._shown_rot)
        self._set_boxes(self.ed_scale, (1, 1, 1))
        self._shown_turn = self.ed_turn.value()
        if self.ed_item.completer() is None and self.editor is not None:
            c = QCompleter(sorted(b.name for b in self.editor.models.blocks.values()), self)
            c.setCaseSensitivity(Qt.CaseInsensitive)
            c.setFilterMode(Qt.MatchContains)
            self.ed_item.setCompleter(c)

    def _rotation_typed(self, current):
        """The rotation the fields ask for, or ``current`` when they show it unchanged
        (so a quaternion isn't rounded through degrees for nothing)."""
        from .maps_edit import quat_of_euler
        rot = tuple(sb.value() for sb in self.ed_rot)
        if all(abs(a - b) < 0.05 for a, b in zip(rot, getattr(self, "_shown_rot", rot))):
            return current
        return quat_of_euler(*rot)

    def _fields_changed(self) -> None:
        """Position, rotation or size typed in the Inspector."""
        z = self._ztarget
        if z and z["kind"] in ("single", "removal") and self.editor is not None:
            pos = [sb.value() for sb in self.ed_pos]
            yaw = math.radians(self.ed_turn.value()) if z["kind"] == "single" else None
            self._edit({"op": "zmove", "path": z["path"], "position": pos, "yaw": yaw})
            return
        if self._ptarget and self.editor is not None:
            st = self._piece_state()
            if st is None:
                return
            sender = self.sender()
            scale = [sb.value() for sb in self.ed_scale]
            if self.same_size.isChecked() and sender in self.ed_scale:
                scale = [sender.value()] * 3
                self._set_boxes(self.ed_scale, scale)
            pos = [sb.value() for sb in self.ed_pos]
            rot = self._rotation_typed(st.rotation)
            if (all(abs(a - b) < 5e-4 for a, b in zip(pos, st.position))
                    and rot == st.rotation
                    and all(abs(a - b) < 5e-4 for a, b in zip(scale, st.scale))):
                return
            self._edit({"op": "pmove", **self._ptarget, "position": pos,
                        "rotation": list(rot), "scale": scale})
            return
        if not self._target or self.editor is None:
            return
        st = self.editor.state(**self._target)
        if st is None:
            return
        pos = tuple(sb.value() for sb in self.ed_pos)
        rot = self._rotation_typed(st.rotation)
        if all(abs(a - b) < 5e-4 for a, b in zip(pos, st.position or pos)) and rot == st.rotation:
            return
        self._edit({"op": "move", **self._target, "position": pos, "rotation": rot})

    # ---- buildings (level pieces) --------------------------------------------------------

    def zone_vpath(self, zone: str) -> str:
        """``data/models/environment/<level>/<zone>.big`` of the open level."""
        L = self._ui_cache.level(self.level)
        return f"{L.vpath}/{L.find_zone(zone).zone}.big"

    def level_zones(self) -> dict:
        """The open level's zones as `convert.level.ZoneData` (read once per level)."""
        if self._level_zones is None:
            self._level_zones = {}
            if self.level:
                L = self._ui_cache.level(self.level)
                for z in L.zones:
                    try:
                        self._level_zones[z.zone] = L.zone(z)
                    except Dr2Error as e:
                        self.status.emit(f"Maps: {e}")
        return self._level_zones

    def _piece_state(self):
        p = self._ptarget
        if p is None or self.editor is None:
            return None
        return self.editor.piece_state(self.zone_vpath(p["zone"]), p["name"])

    def _show_piece_target(self, info: dict) -> None:
        self._ptarget = None
        ed = self.editor if self.edit_box.isChecked() else None
        if ed is not None and info.get("type") == "piece" and info.get("zone") and info.get("name"):
            self._ptarget = {"zone": info["zone"], "name": info["name"]}
            self._clicked_piece = dict(self._ptarget)
            if self.whole_box.isChecked() and "#" not in info["name"]:
                b = self._building()
                if b is not None:
                    self._ptarget = {"zone": info["zone"], "name": b.name, "group": True}
                    self._js(f"dr2.selectGroup({json.dumps(info['zone'])}, "
                             f"{json.dumps(b.name)}, {json.dumps(b.parts)})")
            st = self._piece_state()
            if st is None:
                self._ptarget = None
            else:
                self._target = None
                self._fill_piece(st)
        self._fill_part_of()
        self._refresh_edit_panel()

    def _building(self):
        """The building of the selected piece (`convert.buildings.Building`), or None."""
        p = self._ptarget
        if p is None or self.editor is None:
            return None
        try:
            return self.editor.zone(self.zone_vpath(p["zone"])).building(p["name"])
        except Dr2Error:
            return None

    def _reselect_piece(self) -> None:
        """Whole building switched on or off: select the clicked piece again."""
        c = getattr(self, "_clicked_piece", None)
        if c and self._ptarget:
            if not self.whole_box.isChecked():
                self._js(f"dr2.selectPiece({json.dumps(c['zone'])}, {json.dumps(c['name'])})")
            self._show_piece_target({"type": "piece", **c})

    def _fill_piece(self, st) -> None:
        from .maps_edit import euler_of
        self._set_boxes(self.ed_pos, st.position)
        self._shown_rot = tuple(round(a, 1) for a in euler_of(st.rotation))
        self._set_boxes(self.ed_rot, self._shown_rot)
        self._set_boxes(self.ed_scale, st.scale)

    def _copy_clicked(self) -> None:
        if self._ptarget:
            self._edit({"op": "pcopy", **self._ptarget})
        elif self._target:
            self._edit({"op": "duplicate", **self._target})

    def _put_back(self) -> None:
        if self._ptarget:
            self._edit({"op": "prestore", **self._ptarget})

    def _item_typed(self) -> None:
        if not self._target or self.editor is None:
            return
        text = self.ed_item.text().strip()
        st = self.editor.state(**self._target)
        if st is None or not text or text.lower() == (st.item or "").lower():
            return
        self._edit({"op": "item", **self._target, "item": text})

    # ---- zombies (step 3) ---------------------------------------------------------------

    def _script(self) -> str:
        return self.script_box.currentData() or self.level or ""

    def _show_zombie_target(self, info: dict) -> None:
        """A clicked single zombie, clearing, zombie figure or zombie area → the panel."""
        self._ztarget = None
        ed = self.editor if self.edit_box.isChecked() else None
        if ed is not None and info:
            t = info.get("type")
            if t == "marker" and info.get("kind") == "zombie_spawn" and info.get("path") \
                    and info.get("spawn") in ("single", "removal"):
                self._ztarget = {"kind": info["spawn"], "path": info["path"]}
            elif t == "zombie" and info.get("path"):
                self._ztarget = {"kind": "crowd", "path": info["path"]}
            elif t == "marker" and info.get("kind") == "zombie_area":
                area = (info.get("parent") or info.get("name", "")).split("/")[0].lower()
                crowds = [c for c in ed.zombies(self._script())["crowds"]
                          if c["area"].lower() == area]
                if crowds:
                    self._ztarget = {"kind": "crowd", "path": crowds[0]["path"]}
        if self._ztarget:
            self._target = None
            self._ptarget = None
            self._fill_zombie()
        self._refresh_edit_panel()

    def _zombie_now(self) -> dict | None:
        """The selected zombie block as the mod has it now."""
        z = self._ztarget
        if z is None or self.editor is None:
            return None
        b = self.editor.session("missions.txt").doc.get(z["path"])
        return None if b is None else {p.key: p.value for p in b.props}

    def _fill_zombie(self) -> None:
        props = self._zombie_now() or {}
        z = self._ztarget
        if z["kind"] in ("single", "removal"):
            v = props.get("SpawnPoint") or props.get("Location") or "0,0,0"
            try:
                pos = [float(c) for c in v.split(",")]
            except ValueError:
                pos = [0.0, 0.0, 0.0]
            for sb, c in zip(self.ed_pos, pos):
                sb.blockSignals(True)
                sb.setValue(c)
                sb.blockSignals(False)
            self.ed_turn.blockSignals(True)
            try:
                self.ed_turn.setValue(math.degrees(float(props.get("Rotation", "0"))))
            except ValueError:
                self.ed_turn.setValue(0)
            self.ed_turn.blockSignals(False)
            self.z_type.setText(props.get("ZombieType", ""))
            self.z_count.blockSignals(True)
            try:
                self.z_count.setValue(int(props.get("NumberOfZombies", "1")))
            except ValueError:
                self.z_count.setValue(1)
            self.z_count.blockSignals(False)
            self.z_item.setText(props.get("SpawnWithItem", ""))
            if self.z_type.completer() is None:
                from ..convert.levelcheck import ZOMBIES
                try:
                    arc = AssetTree(self.tree.root).open_archive(ZOMBIES)
                    names = sorted(e.name[:-4] for e in arc.entries
                                   if e.name.lower().endswith(".big"))
                except Dr2Error:
                    names = []
                c = QCompleter(names, self)
                c.setCaseSensitivity(Qt.CaseInsensitive)
                c.setFilterMode(Qt.MatchContains)
                self.z_type.setCompleter(c)
        else:
            amounts = []
            for k, v in props.items():
                if k.lower().startswith("type") and k[4:].isdigit():
                    amounts.append((int(k[4:]), v, props.get(f"Amount{k[4:]}", "0")))
            amounts.sort()
            self.crowd_types.setText(", ".join(f"{t} {n}" for _i, t, n in amounts
                                               if n not in ("0", "")))
            self.crowd_label.setText(f"<b>Crowd</b> in the area "
                                     f"<b>{props.get('ZombieWarehouseName', '?')}</b> "
                                     f"(mission {z['path'].split('/')[0].split(' ', 1)[-1]}). "
                                     f"Types and how many:")

    def _zombie_fields(self) -> None:
        z = self._ztarget
        if not z or z["kind"] != "single":
            return
        props = self._zombie_now() or {}
        keys = {}
        t = self.z_type.text().strip()
        if t and t != props.get("ZombieType"):
            keys["ZombieType"] = t
        n = str(self.z_count.value())
        if n != props.get("NumberOfZombies", "1"):
            keys["NumberOfZombies"] = n
        item = self.z_item.text().strip()
        if item != props.get("SpawnWithItem", ""):
            if item:
                keys["SpawnWithItem"] = item
            elif "SpawnWithItem" in props and self.editor.is_own(z["path"]):
                keys["SpawnWithItem"] = None
        if keys:
            self._edit({"op": "zset", "path": z["path"], "keys": keys})

    def _crowd_typed(self) -> None:
        z = self._ztarget
        if not z or z["kind"] != "crowd":
            return
        amounts = []
        for part in self.crowd_types.text().split(","):
            bits = part.split()
            if not bits:
                continue
            try:
                n = int(bits[1]) if len(bits) > 1 else 1
            except ValueError:
                self.status.emit(f"Maps: {part.strip()!r}: write a type and a number "
                                 f"(zombie_fat 15)")
                return
            amounts.append((bits[0], n))
        if amounts:
            self._edit({"op": "crowd", "path": z["path"], "amounts": amounts})

    def _add_zombie(self) -> None:
        if self.editor is None and self._get_editor() is None:
            return
        from ..convert.levelcheck import ZOMBIES
        try:
            arc = AssetTree(self.tree.root).open_archive(ZOMBIES)
            names = sorted(e.name[:-4] for e in arc.entries if e.name.lower().endswith(".big"))
        except Dr2Error:
            names = []
        ztype, ok = QInputDialog.getItem(self, "Add zombies", "Zombie type (they appear in "
                                         "a new game):", names, 0, True)
        if not ok or not ztype:
            return
        self._adding = "zombie:" + ztype
        self._js("dr2.askPlace()")

    # ---- prefabs and settings (step 5) ---------------------------------------------------

    def _delete_clicked(self) -> None:
        if self._ptarget:
            st = self._piece_state()
            self._edit({"op": "pshow" if st is not None and st.hidden else "phide",
                        **self._ptarget})
        elif self._ztarget:
            self._edit({"op": "zdelete", **self._ztarget})
        elif self._btarget and self._btarget.get("added"):
            self._edit({"op": "bremove", "file": self._btarget["file"],
                        "path": self._btarget["path"]})
            self._btarget = None
        elif self._target:
            self._edit({"op": "delete", **self._target})

    def prefabs(self) -> list:
        """The shipped prefabs this game has an example of, then the modder's own."""
        from ..catalog import prefabs as pf
        return [p for p in pf.load() if p.for_game(self.game)] + pf.load_own()

    def _add_prefab(self) -> None:
        if self._get_editor() is None:
            return
        items = self.prefabs()
        labels = [f"{p.group}: {p.name}" + ("" if p.checked else "  (not checked in game "
                                                                 "yet)") for p in items]
        choice, ok = QInputDialog.getItem(self, "Add from prefab", "What to add (it goes "
                                          "where the middle of the view meets the floor):",
                                          labels, 0, False)
        if not ok:
            return
        self._adding = ("prefab", items[labels.index(choice)])
        self._js("dr2.askPlace()")

    def _settings(self) -> None:
        ed = self.editor
        if ed is None:
            return
        if self._target:
            file, path = self._target["file"], None
            b = ed.placement(file, self._target["name"])
            path = f"{b.cls} {b.name}"
        elif self._btarget:
            file, path = self._btarget["file"], self._btarget["path"]
        else:
            return
        b = ed.session(file).doc.find(path)
        before = {p.key: p.value for p in b.props}
        text = "\n".join(f"{k} = {v}" for k, v in before.items())
        new, ok = QInputDialog.getMultiLineText(
            self, "Settings", f"{path} ({file}), one setting per line, Key = value:", text)
        if not ok:
            return
        after = {}
        for line in new.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                if k.strip():
                    after[k.strip()] = v.strip().strip('"')
        keys = {k: v for k, v in after.items() if before.get(k) != v}
        keys.update({k: None for k in before if k not in after})
        if keys:
            self._edit({"op": "keys", "file": file, "path": path, "keys": keys})

    def _save_prefab(self) -> None:
        from ..catalog import prefabs as pf
        if not self._target or self.editor is None:
            return
        b = self.editor.placement(self._target["file"], self._target["name"])
        name, ok = QInputDialog.getText(self, "Save as prefab", "Its name in the list:",
                                        text=b.get("ItemName") or b.name)
        if not ok or not name:
            return
        props = {p.key: p.value for p in b.props}
        path = pf.save_own(pf.own_folder() / name, name, "level",
                           [{"cls": b.cls, "name": b.name, "props": props}],
                           b.floats("Location") or (0, 0, 0))
        self.status.emit(f"Maps: saved the prefab {name} ({path}); Add from prefab… lists it")

    def sync_edits(self) -> None:
        """Show on the page everything the mod being edited changes in this level (its
        items, the triggers and spawn points it adds, its zombies), whatever the
        *With my mods* view shows."""
        from .maps_edit import _snapshot
        ed = self._get_editor()
        script = self._script()
        if ed is None or not script:
            return
        states = []
        for fname in (f"{script}.txt",):
            try:
                s = ed.session(fname)
            except Dr2Error:
                continue
            states += ed._states(fname, _snapshot(s.original), _snapshot(s.doc))
        from ..mods.pieceedit import pieces_path
        for zname in self.level_zones():
            zv = self.zone_vpath(zname)
            if zv.lower() in ed.zones or pieces_path(ed.mod_dir, zv).is_file():
                try:
                    states += ed._piece_states(ed.zone(zv), {})
                except Dr2Error as e:
                    self.status.emit(f"Maps: {e}")
        self._send_states(states)
        self._send_markers()
        self._js(f"dr2.setZombies({json.dumps(ed.zombies(script))})")

    def _new_item(self) -> None:
        from ..mods import newitem
        ed = self.editor
        if not self._target or ed is None:
            return
        st = ed.state(**self._target)
        if st is None or not st.item:
            return
        name, ok = QInputDialog.getText(self, "New item", f"A new item made from {st.item}. "
                                        f"Its name (letters, digits, _):",
                                        text=f"My{st.item}")
        if not ok or not name:
            return
        glb, _ = QFileDialog.getOpenFileName(self, "Its shape (optional: Cancel keeps "
                                             f"{st.item}'s)", "", "glTF binary (*.glb)")
        # the mod gets a recipe (copy this pack, with my .glb), never the game's bytes
        try:
            newitem.new_item(AssetTree(self.tree.root), ed.mod_dir, name, st.item,
                             glb or None, ed.base_dirs)
        except Dr2Error as e:
            self.status.emit(f"Maps: {e}")
            if hasattr(self.window, "error"):
                self.window.error(str(e))
            return
        ed.forget("items.txt")
        ed.reload_models()
        self._usable = None
        self.palette.forget("item")
        pos = [c + o for c, o in zip(st.position or (0, 0, 0), (1.0, 0.0, 0.0))]
        self._edit({"op": "add", "file": self._target["file"], "item": name, "position": pos})
        self.status.emit(f"Maps: {name} is your mod's own item (placed beside {st.item}); "
                         f"change its textures with PNGs, its shape in Blender")

    def _send_markers(self) -> None:
        from .maps_edit import added_markers
        if self.editor is not None:
            self._js(f"dr2.setEditedMarkers({json.dumps(added_markers(self.editor, self._script()))})")

    def usable_items(self) -> list[str]:
        """Items whose model ships in this game, by name (for *Add item…*)."""
        if self._usable is None:
            ed = self._get_editor()
            if ed is None:
                return []
            self._usable = sorted((b.name for b in ed.models.blocks.values()
                                   if ed.models.resolve(b.name)), key=str.lower)
        return self._usable

    # ---- Place and Hierarchy (maps_panels) ---------------------------------------------

    def start_place(self, spec: dict, at: tuple[float, float] | None = None, *,
                    point=None, arm: bool = False) -> None:
        """Put what a Place row names into the level: at the floor ``point`` (a drop the
        page took), at page pixel ``at``, with the next click in the view (``arm``), or
        where the middle of the view meets the floor. Editing starts if it was off."""
        if not self.level:
            self.status.emit("Maps: open a level first (the Maps tab on the left)")
            return
        if not self.edit_box.isChecked():
            self.edit_box.setChecked(True)
            if not self.edit_box.isChecked():           # no mod chosen
                return
        kind, name = spec.get("kind"), spec.get("name", "")
        if kind == "prefab":
            pre = self._prefab_rows[spec["prefab"]] if spec.get("prefab") is not None and \
                spec["prefab"] < len(getattr(self, "_prefab_rows", [])) else None
            if pre is None:
                return
            self._adding = ("prefab", pre)
        elif kind == "zombie":
            self._adding = "zombie:" + name
        elif kind == "piece":
            self._adding = ("piece", spec["zone"], name, bool(spec.get("group")))
        else:
            self._adding = name
        if point is not None:
            self._place({"point": point})
        elif arm:
            self._js(f"dr2.startPlacing({json.dumps(name or kind)})")
        elif at is None:
            self._js("dr2.stopPlacing(); dr2.askPlace()")
        else:
            self._js(f"dr2.placeAt({at[0]:.1f}, {at[1]:.1f})")

    def place_rows(self, kind: str) -> list[dict]:
        """The Place panel's rows of one kind (`maps_panels.PlacePanel`)."""
        if self.tree is None:
            return []
        if kind == "prefab":
            self._prefab_rows = self.prefabs()
            return [{"kind": "prefab", "name": p.name, "prefab": i, "label": p.name,
                     "tip": f"{p.group}: {p.name}" + ("" if p.checked else
                                                      " (not checked in game yet)")}
                    for i, p in enumerate(self._prefab_rows)]
        if kind == "item":
            models = self.editor.models if self.editor is not None else self._item_models()
            out = []
            for b in sorted(models.blocks.values(), key=lambda b: b.name.lower()):
                vp = models.resolve(b.name)
                if vp:
                    out.append({"kind": "item", "name": b.name, "vpath": vp,
                                "tip": f"{b.name} ({b.cls})\n{vp}"})
            return out
        if kind == "zombie":
            from ..convert.levelcheck import ZOMBIES
            try:
                arc = AssetTree(self.tree.root).open_archive(ZOMBIES)
            except Dr2Error:
                return []
            return [{"kind": "zombie", "name": e.name[:-4],
                     "tip": f"{e.name[:-4]}: goes in your mod's own mission (a new game)"}
                    for e in sorted(arc.entries, key=lambda e: e.name.lower())
                    if e.name.lower().endswith(".big")]
        if kind == "piece":
            out = []
            for zname, zd in self.level_zones().items():
                for b in self.zone_buildings(zname):
                    out.append({"kind": "piece", "name": b.name, "zone": zname,
                                "vpath": zd.pieces.get(b.name), "label": b.name,
                                "group": True,
                                "tip": f"{b.name} (zone {zname}): {len(b.parts)} parts. A "
                                       f"copy has no collision, and stays with its zone"})
            return out
        return []

    def zone_buildings(self, zone: str) -> list:
        """A zone's buildings (`convert.buildings`): the mod's own when editing, else the
        game's (read once per level)."""
        if self.editor is not None and self.edit_box.isChecked():
            return self.editor.zone(self.zone_vpath(zone)).buildings()
        cache = self.__dict__.setdefault("_zone_buildings", {})
        key = (self.level, zone, id(self.tree))
        if key not in cache:
            from ..convert import buildings as cb
            from ..convert import level as cl
            zd = self.level_zones()[zone]
            cache[key] = cb.zone_buildings(zd, cl.zone_shapes(self.tree, zd),
                                           cb.corrections(self.game, zone))
        return cache[key]

    def _part_of_changed(self, i: int) -> None:
        """The modder put the selected part into another building (or alone): kept in
        the config folder (`convert.buildings.set_correction`), used from now on."""
        from ..convert import buildings as cb
        p = getattr(self, "_clicked_piece", None)
        target = self.part_of.itemData(i)
        if p is None or i < 0 or target == "?":
            return
        cb.set_correction(self.game, p["zone"], p["name"], target)
        self.__dict__.pop("_zone_buildings", None)
        if self.editor is not None:
            self.editor.zone(self.zone_vpath(p["zone"]))._buildings = None
        self.palette.forget("piece")
        self._hier_timer.start()
        self.status.emit(f"Maps: {p['name']} is now " + (
            "a building of its own" if target == "" else "as Studio guesses" if target is None
            else f"part of {target}"))
        self._fill_part_of()

    def _fill_part_of(self) -> None:
        """The *Part of* list: the buildings of the selected part's zone, nearest first."""
        p = getattr(self, "_clicked_piece", None)
        self.part_of.blockSignals(True)
        self.part_of.clear()
        show = bool(self._ptarget and not self._ptarget.get("group") and p
                    and "#" not in p["name"])
        self.part_of_row.setVisible(show)
        if show:
            from ..convert import buildings as cb
            bs = self.zone_buildings(p["zone"])
            mine = cb.building_of(bs, p["name"])
            here = next((x.centre for x in bs if mine is x), (0, 0, 0))
            self.part_of.addItem(f"{mine.name if mine else '?'} (now)", "?")
            self.part_of.addItem("(a building of its own)", "")
            self.part_of.addItem("(as Studio guesses)", None)
            for b in sorted(bs, key=lambda b: math.dist(b.centre, here)):
                if b is not mine:
                    self.part_of.addItem(f"{b.name} ({len(b.parts)} parts)", b.name)
        self.part_of.blockSignals(False)

    def _item_models(self):
        from ..convert import placed
        if getattr(self, "_models_tree", None) is not self.tree:
            self._models = placed.ItemModels(self.tree)
            self._models_tree = self.tree
        return self._models

    def picture(self, vpath: str) -> bytes | None:
        """The Library's picture of a model (None when the index has none)."""
        con = getattr(self.window, "con", None)
        if con is None:
            return None
        from ..index import query
        try:
            row = query.get(con, self.game, vpath)
            return query.picture(con, row["id"]) if row is not None else None
        except Exception:  # noqa: BLE001 - a missing picture is only a missing icon
            return None

    def focus(self, target: dict) -> None:
        """Fly to a Hierarchy row and select it once it is loaded (``dr2.focus``): a
        building by its first piece (the Inspector selects all of it), a part alone, a
        collision shape by flying there with the collision layer shown."""
        if target.get("position") is None:
            return
        t = {k: v for k, v in target.items() if k != "children"}
        if t["kind"] == "building":
            self.whole_box.setChecked(True)
            t["kind"] = "piece"
        elif t["kind"] == "piece" and "#" not in t["name"]:
            self.whole_box.setChecked(False)
        elif t["kind"] == "collision":
            self.layer_boxes["collision"].setChecked(True)
            t["kind"] = "marker"
        self._js(f"dr2.focus({json.dumps(t)})")

    def fill_hierarchy(self) -> None:
        """What the open level holds, as the mod being edited has it (when editing)."""
        if not self.level or not self.meta:
            self.hierarchy.fill({})
            return
        ed = self.editor if self.edit_box.isChecked() else None
        rows: dict[str, list[dict]] = {"item": [], "piece": [], "zombie": [], "marker": []}
        script = self._script()
        if ed is not None and script:
            from .maps_edit import ITEM_CLASSES
            try:
                sess = ed.session(f"{script}.txt")
                shipped = {b.name.lower() for b in sess.original.blocks}
                for b in sess.doc.blocks:
                    if b.cls in ITEM_CLASSES and b.floats("Location"):
                        rows["item"].append({"kind": "door" if b.cls == "cDoorPlacement"
                                             else "item", "name": b.name,
                                             "what": b.get("ItemName") or "",
                                             "position": list(b.floats("Location")),
                                             "added": b.name.lower() not in shipped})
            except Dr2Error:
                pass
        else:
            rows["item"] = [{"kind": i["kind"], "name": i["name"], "what": i.get("item") or "",
                             "position": i["position"]} for i in self.meta.get("items", [])]
        for zname, zd in self.level_zones().items():
            ze = ed.zone(self.zone_vpath(zname)) if ed is not None else None
            centres = {p.piece.lower(): p.centre for p in zd.organization.placements}
            copies = [st for st in (ze.states() if ze else []) if st.copy]
            shapes = {}
            if ze is not None:
                ze.buildings()
                shapes = ze._shapes or {}
            for b in self.zone_buildings(zname):
                kids = [{"kind": "piece", "name": n, "zone": zname, "what": "part",
                         "position": list(centres.get(n.lower(), b.centre)),
                         "hidden": bool(ze and ze.hidden(n))} for n in b.parts]
                kids += [{"kind": "piece", "name": c.name, "zone": zname, "what": "copy",
                          "position": list(c.position), "added": True}
                         for c in copies if c.piece.lower() in {n.lower() for n in b.parts}]
                for mesh in b.shapes:
                    col = (ze.edits.collision.get(mesh) if ze else None) or {}
                    ps = shapes.get(mesh.lower())
                    pos = [(lo + hi) / 2 for lo, hi in zip(*ps.bounds)] if ps else list(b.centre)
                    kids.append({"kind": "collision", "name": mesh, "zone": zname,
                                 "label": mesh.removeprefix("mesh").removeprefix("COL_"),
                                 "what": "collision" + (" (hidden)" if col.get("hidden") else
                                                        " (moved)" if col.get("move") else ""),
                                 "position": pos})
                rows["piece"].append({"kind": "building", "name": b.name, "zone": zname,
                                      "what": f"{len(b.parts)} parts, {len(b.shapes)} "
                                              f"collision · {zname}",
                                      "position": list(b.centre),
                                      "hidden": bool(ze and ze.building_hidden(b.name)),
                                      "children": kids})
        zs = ed.zombies(script) if ed is not None and script else self.meta
        for z in zs.get("zombie_spawns") or []:
            if z.get("position") and z.get("path"):
                p = z.get("props") or {}
                rows["zombie"].append({"kind": "zombie", "name": z["path"],
                                       "what": (p.get("ZombieType") or z.get("spawn") or "")
                                       + (f" ×{p['NumberOfZombies']}"
                                          if p.get("NumberOfZombies") else ""),
                                       "position": z["position"]})
        for z in rows["zombie"]:
            z["label"] = z["name"].rsplit("/", 1)[-1]
        for m in self.meta.get("markers", []):
            if m.get("position") and m["kind"] in ("spawn", "map_point", "trigger"):
                rows["marker"].append({"kind": "marker", "name": m.get("label") or m["name"],
                                       "what": {"spawn": "spawn point", "map_point": "map point",
                                                "trigger": "trigger"}[m["kind"]],
                                       "position": m["position"]})
        self.hierarchy.fill(rows)

    def _watch_drops(self, _ok=True) -> None:
        """The page's own widget (QtWebEngine's focus proxy) gets the drag events: watch
        it too."""
        fp = self.view.focusProxy() if self.view is not None else None
        if fp is not None and fp is not getattr(self, "_drop_proxy", None):
            fp.setAcceptDrops(True)
            fp.installEventFilter(self)
            self._drop_proxy = fp

    def eventFilter(self, obj, ev):  # noqa: N802 - Qt's name
        """A drag from the Place panel is let through to the page: it takes the drop
        itself (exact page coordinates, ``dr2:drop``). Converting the mouse position in
        Qt put the ring beside the mouse on a scaled screen, and on Wayland the drop
        didn't arrive (2026-10-12)."""
        if ev.type() == QEvent.ChildAdded and obj is self.view:
            QTimer.singleShot(0, self._watch_drops)
        return super().eventFilter(obj, ev)

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
        if isinstance(item, tuple) and item[0] == "piece":     # a copy of a building
            _k, zone, name, group = item
            self._edit({"op": "pcopy", "zone": zone, "name": name, "position": msg["point"],
                        "group": group})
            z = next((z for z in (self.meta or {}).get("zones", []) if z["name"] == zone), None)
            if z and not all(lo - 1 <= c <= hi + 1 for c, lo, hi in
                             zip(msg["point"], z["min"], z["max"])):
                self.status.emit(f"Maps: {name} belongs to zone {zone}: the game shows the "
                                 f"copy only while that zone is loaded (put it near its zone)")
            return
        if isinstance(item, tuple):                # a prefab
            self._edit({"op": "prefab", "prefab": item[1], "position": msg["point"]})
            return
        if item.startswith("zombie:"):
            self._edit({"op": "zadd", "type": item[7:], "position": msg["point"]})
            return
        script = self.script_box.currentData() or self.level
        self._edit({"op": "add", "file": f"{script}.txt", "item": item,
                    "position": msg["point"]})

    def _edit(self, msg: dict) -> None:
        """One change from the page or the panel: apply, save, tell the page."""
        ed = self._get_editor() if self.edit_box.isChecked() else None
        if ed is None:
            return
        op = msg.get("op")
        if op in ZOMBIE_OPS:
            return self._zombie_edit(ed, msg)
        if op in PIECE_OPS:
            return self._piece_edit(ed, msg)
        done: list[str] = []
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
                for s in states:
                    s.snap = True
            elif op == "item":
                states = ed.set_item(msg["file"], msg["name"], msg["item"])
            elif op == "prefab":
                from ..catalog import prefabs as pf
                pre = msg["prefab"]
                names, states = pf.place(ed, pre, self.game, self._script(), msg["position"])
                done = names
                for s in states:
                    s.snap = True
                if pre.file == "level" and states:
                    self._target = {"file": pre.file_for(self._script()), "name": names[0]}
                if pre.file == "waypoint" or pre.id == "spawn_point":
                    kind = "spawn" if pre.id == "spawn_point" else "trigger"
                    if kind in self.layer_boxes:
                        self.layer_boxes[kind].setChecked(True)
                if not pre.checked:
                    self.status.emit(f"Maps: {pre.name} hasn't been checked in game yet")
            elif op == "keys":
                states = ed.set_keys(msg["file"], msg["path"], msg["keys"])
            elif op == "bremove":
                states = ed.remove_block(msg["file"], msg["path"])
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
        if op in ("undo", "redo") and self._ptarget:          # it may have been a building
            st = self._piece_state()
            if st is None:
                self._ptarget = None
            else:
                self._fill_piece(st)
        if op in ("undo", "redo"):                # it may have been a zombie change
            self._js(f"dr2.setZombies({json.dumps(ed.zombies(self._script()))})")
            if self._ztarget and self._zombie_now() is None:
                self._ztarget = None
            elif self._ztarget:
                self._fill_zombie()
        if self._target:
            st = ed.state(**self._target)
            if st is None:
                self._target = None
            else:
                self._fill_fields(st)
        if op in ("prefab", "keys", "bremove", "undo", "redo"):
            self._send_markers()
        what = {"move": "moved", "delete": "deleted", "duplicate": "copied", "add": "added",
                "item": "changed", "undo": "undone", "redo": "redone", "prefab": "added",
                "keys": "changed", "bremove": "removed"}[op]
        names = ", ".join(done or [s.name for s in states if s.name]) or "nothing"
        self.status.emit(f"Maps: {what} {names} (saved into {Path(ed.mod_dir).name})")
        self._after_edit()

    def _after_edit(self) -> None:
        self._refresh_edit_panel()
        self._hier_timer.start()
        if hasattr(self.window, "_refresh_mod"):      # the bottom bar's list of changes
            self.window._refresh_mod()

    def _piece_edit(self, ed, msg: dict) -> None:
        """A building hidden, shown, moved, put back or copied (`maps_edit.LevelEditor`)."""
        op, name = msg["op"], msg["name"]
        if msg.get("group"):
            return self._building_edit(ed, msg)
        try:
            zv = self.zone_vpath(msg["zone"])
            if op == "pmove":
                states = ed.piece_move(zv, name, msg.get("position"), msg.get("rotation"),
                                       msg.get("scale"))
                what = "moved"
            elif op in ("phide", "pshow"):
                states = ed.piece_hide(zv, name, op == "phide")
                what = "hidden" if op == "phide" and "#" not in name else (
                    "removed" if op == "phide" else "shown again")
                if "#" in name:
                    self._ptarget = None
            elif op == "prestore":
                states = ed.piece_restore(zv, name)
                what = "put back as the game has it"
            else:
                pos = msg.get("position")
                if pos is None:                            # Ctrl+D: beside it
                    p = ed.zone(zv).placement(name)
                    r = max(abs(a - b) for a, b in zip(p.bounds_max, p.bounds_min))
                    pos = [p.position[0] + max(1.0, r / 2), p.position[1], p.position[2]]
                new, states = ed.piece_copy(zv, name, pos, msg.get("rotation"),
                                            msg.get("scale"))
                self._ptarget = {"zone": msg["zone"], "name": new}
                self._js(f"setTimeout(() => dr2.selectPiece({json.dumps(msg['zone'])}, "
                         f"{json.dumps(new)}), 50)")
                what, name = "copied", f"{name} → {new}"
                self.status.emit("Maps: copies of buildings aren't checked in game yet")
        except Dr2Error as e:
            self.status.emit(f"Maps: {e}")
            st = self._piece_state()
            if st is not None:                    # put the page back where the file is
                self._send_states([st])
            return
        self._own_write_until = time.monotonic() + 5.0
        self._send_states(states)
        st = self._piece_state()
        if st is not None:
            self._fill_piece(st)
        self.status.emit(f"Maps: {what} {name} (saved into {Path(ed.mod_dir).name})")
        self._after_edit()

    def _zombie_edit(self, ed, msg: dict) -> None:
        op = msg["op"]
        try:
            if op == "zmove":
                ed.zombie_move(msg["path"], msg["position"], msg.get("yaw"))
            elif op == "zdelete":
                ed.remove_zombie(msg["path"])
                if ed.session("missions.txt").doc.get(msg["path"]) is None:
                    self._ztarget = None
            elif op == "zset":
                ed.zombie_set(msg["path"], msg["keys"])
            elif op == "crowd":
                ed.crowd_amounts(msg["path"], msg["amounts"])
            elif op == "zadd":
                path = ed.add_zombie(self._script(), msg["type"], msg["position"])
                self._ztarget = {"kind": "single", "path": path}
                self.status.emit(f"Maps: added {msg['type']} into your mod's own mission: "
                                 f"they appear in a new game")
        except Dr2Error as e:
            self.status.emit(f"Maps: {e}")
            return
        self._own_write_until = time.monotonic() + 5.0
        self._js(f"dr2.setZombies({json.dumps(ed.zombies(self._script()))})")
        if self._ztarget:
            if self._zombie_now() is None:
                self._ztarget = None
            else:
                self._fill_zombie()
        if op != "zadd":
            self.status.emit(f"Maps: zombies changed (saved into {Path(ed.mod_dir).name})")
        self._after_edit()

    def _building_edit(self, ed, msg: dict) -> None:
        """A whole building moved, hidden, shown, put back or copied, with its collision."""
        op, name, zone = msg["op"], msg["name"], msg["zone"]
        warn: list[str] = []
        try:
            zv = self.zone_vpath(zone)
            if op == "pmove":
                states, warn = ed.building_move(zv, name, msg.get("position"),
                                                msg.get("rotation"), msg.get("scale"))
                what = "moved (with its collision)"
            elif op in ("phide", "pshow"):
                states = ed.building_hide(zv, name, op == "phide")
                what = "hidden with its collision" if op == "phide" else "shown again"
            elif op == "prestore":
                states = ed.building_restore(zv, name)
                what = "put back as the game has it"
            else:
                pos = msg.get("position")
                lead = ed.zone(zv).placement(name)
                if pos is None:                            # Ctrl+D: beside it
                    b = ed.zone(zv).building(name)
                    w = max(hi - lo for lo, hi in zip(b.bounds_min, b.bounds_max)) if b else 2
                    pos = [lead.position[0] + max(2.0, w), lead.position[1], lead.position[2]]
                else:                                      # dropped: stand it on the point
                    b = ed.zone(zv).building(name)
                    if b is not None:
                        pos = [pos[0], pos[1] + lead.position[1] - b.bounds_min[1], pos[2]]
                names, states = ed.building_copy(zv, name, pos)
                what = f"copied as {names[0]} ({len(names)} parts; a copy has no collision)"
                self._ptarget = None
                self._js(f"setTimeout(() => dr2.selectPiece({json.dumps(zone)}, "
                         f"{json.dumps(names[0])}), 50)")
        except Dr2Error as e:
            self.status.emit(f"Maps: {e}")
            return
        self._own_write_until = time.monotonic() + 5.0
        self._send_states(states)
        if self._ptarget and self._ptarget.get("group"):
            b = self._building()
            st = self._piece_state()
            if st is not None:
                self._fill_piece(st)
            if b is not None and not (st and st.hidden):
                self._js(f"dr2.selectGroup({json.dumps(zone)}, {json.dumps(b.name)}, "
                         f"{json.dumps(b.parts)})")
        self.status.emit(f"Maps: {name} {what} (saved into {Path(ed.mod_dir).name})"
                         + ("; " + " ".join(warn) if warn else ""))
        self._after_edit()

    def _send_states(self, states) -> None:
        from ..mods.pieceedit import PieceState
        from .maps_edit import item_glb
        pieces = [st.to_dict() for st in states if isinstance(st, PieceState)]
        if pieces:
            self._js(f"dr2.pieceState({json.dumps(pieces)})")
        states = [st for st in states if not isinstance(st, PieceState)]
        out = []
        for st in states:
            d = st.to_dict()
            if st.new_model and not st.removed:
                data = item_glb(self.editor.mod_tree if self.editor else
                                AssetTree(self.tree.root), self.game, st)
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


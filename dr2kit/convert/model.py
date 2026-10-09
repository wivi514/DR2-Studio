"""Model export: a scene's vpath → ``.glb``, with its textures found and embedded.

`dr2kit.convert.gltf` turns a parsed `Scene` into glTF; this module does the parts that
need the game data around it:

* `TextureFinder` looks a material's texture up **by name**, closest first: the model's
  own pack (``npcs.big/chest_young_chuck.big`` → ``npcs.big/chest_young_chuck.tex``),
  then any texture or ``.tex`` pack in the archives that contain the model (nearest
  archive first), then the asset index (``dr2 index build``) if there is one. A name
  that is not found is reported, never silently replaced.
* `export_glb` / `export_skeleton_glb` read a vpath and return the ``.glb`` bytes.

Used by ``dr2 extract --glb`` and DR2 Studio's 3D view.
"""

from __future__ import annotations

from ..container.big import BigArchive, is_big
from ..container.vpath import AssetTree, join, split
from ..errors import Dr2Error
from ..formats.bct import is_bct
from ..formats.scene import Scene
from . import gltf


def texture_png(data: bytes, source: str = "<bct>") -> bytes:
    """A texture's level 0 as PNG bytes (RGB, or RGBA when it has alpha)."""
    from ..formats.bct import Bct
    from . import png
    from .texture import png_mode, to_image
    tex = Bct.parse(data, source)
    img = to_image(tex, 0)
    return png.encode(img, png_mode(tex, img))


class TextureFinder:
    """``finder(name)`` → PNG bytes of the texture called ``name``, or None."""

    def __init__(self, tree: AssetTree, model_vpath: str, game: str | None = None,
                 db_path=None):
        self.tree, self.game, self.db_path = tree, game, db_path
        self.vpath = model_vpath
        self.found: dict[str, str] = {}          # name -> vpath it was read from
        self._scanned: list[dict[str, tuple[str, bytes]]] | None = None

    def _containers(self) -> list[str]:
        """The archives holding the model, nearest first (excluding the model itself)."""
        parts = split(self.vpath)
        out = []
        for i in range(len(parts) - 1, 0, -1):
            vp = join(*parts[:i])
            if vp.lower().endswith(".big") or vp.lower().endswith(".tex"):
                out.append(vp)
        return out

    def _scan(self) -> list[dict[str, tuple[str, bytes]]]:
        """Name → (vpath, bct bytes) for each container, the model's own pack first."""
        if self._scanned is not None:
            return self._scanned
        self._scanned = []
        parts = split(self.vpath)
        stem = parts[-1].rsplit(".", 1)[0].lower()
        for cvp in self._containers():
            try:
                arc = self.tree.open_archive(cvp)
            except Dr2Error:
                continue
            own: dict[str, tuple[str, bytes]] = {}
            other: dict[str, tuple[str, bytes]] = {}
            for e in arc.entries:
                lname = e.name.lower()
                if lname.endswith(".tex"):
                    data = e.data()
                    if not is_big(data):
                        continue
                    pack = BigArchive.parse(data, join(cvp, e.name))
                    target = own if lname[:-4] == stem else other
                    for t in pack.entries:
                        key = t.name.lower().removesuffix(".bct")
                        target.setdefault(key, (join(cvp, e.name, t.name), t))
                elif lname.endswith(".bct") or e.ext == "":
                    other.setdefault(lname.removesuffix(".bct"), (join(cvp, e.name), e))
            if own:
                self._scanned.append(own)
            self._scanned.append(other)
        self._scanned += self._scan_folder(stem)
        return self._scanned

    def _scan_folder(self, stem: str) -> list[dict[str, tuple[str, object]]]:
        """Texture packs (``.tex`` files) next to the model's file on disk.

        Loose models (``data/dynamicprops/special/missingprop.big``) keep their pack as a
        separate file in the same folder; the model's own ``<stem>.tex`` first. Nested
        models get the folder of the file on disk that holds them, after their archives.
        """
        parts = split(self.vpath)
        here = self.tree.root
        folder_parts = []
        for p in parts:
            nxt = next((c for c in here.iterdir() if c.name.lower() == p.lower()), None) \
                if here.is_dir() else None
            if nxt is None or not nxt.is_dir():
                break
            here = nxt
            folder_parts.append(nxt.name)
        own: dict = {}
        other: dict = {}
        for f in sorted(here.glob("*")) if here.is_dir() else []:
            if f.suffix.lower() != ".tex" or not f.is_file():
                continue
            vp = join(*folder_parts, f.name)
            try:
                pack = self.tree.open_archive(vp)
            except Dr2Error:
                continue
            target = own if f.stem.lower() == stem else other
            for t in pack.entries:
                target.setdefault(t.name.lower().removesuffix(".bct"), (join(vp, t.name), t))
        return [d for d in (own, other) if d]

    def _from_index(self, name: str) -> tuple[str, bytes] | None:
        if self.game is None:
            return None
        try:
            from ..index import query
            from ..index.build import connect, default_db_path
            from pathlib import Path
            path = Path(self.db_path) if self.db_path else default_db_path()
            if not path.exists():
                return None
            con = connect(path)
        except Exception:  # noqa: BLE001 - the index is optional; say nothing, fall back
            return None
        try:
            rows = [r for r in query.search(con, name, game=self.game, kind="texture", limit=50)
                    if r["name"].lower().removesuffix(".bct") == name.lower()]
        finally:
            con.close()
        for r in rows:
            try:
                return r["vpath"], self.tree.resolve(r["vpath"]).data()
            except Dr2Error:
                continue
        return None

    def bct(self, name: str) -> tuple[str, bytes] | None:
        """``(vpath, .bct bytes)`` of the texture called ``name``, or None."""
        key = name.lower()
        for table in self._scan():
            hit = table.get(key)
            if hit is not None:
                vp, entry = hit
                data = entry.data()
                if is_bct(data):
                    self.found[name] = vp
                    return vp, data
        hit = self._from_index(name)
        if hit is not None and is_bct(hit[1]):
            self.found[name] = hit[0]
            return hit
        return None

    def image(self, name: str):
        """The texture called ``name`` decoded to a `png.Image` (level 0), or None."""
        hit = self.bct(name)
        if hit is None:
            return None
        from ..formats.bct import Bct
        from .texture import to_image
        return to_image(Bct.parse(hit[1], hit[0]), 0)

    def __call__(self, name: str) -> bytes | None:
        hit = self.bct(name)
        return None if hit is None else texture_png(hit[1], hit[0])

    def baker(self, scene: Scene):
        """The ``base_colour`` hook for `gltf.model_to_glb`: bakes materials whose colour
        is in shader constants (`convert.material`), None for the others."""
        from . import material as cmat
        from . import png
        shaders = cmat.ShaderLibrary(self.tree)

        def base_colour(m):
            rec = cmat.recipe(scene, m, shaders)
            if rec is None:
                return None
            img = cmat.bake(rec, self.image)
            if img is None:
                return None
            return f"{rec.diffuse}_baked", png.encode(img, "RGB"), rec.family
        return base_colour


def read_scene(tree: AssetTree, vpath: str) -> Scene:
    node = tree.resolve(vpath)
    data = node.data()
    if not is_big(data):
        raise Dr2Error(f"{node.vpath} is not a scene (not a .big archive)")
    return Scene.parse(data, node.vpath)


def export_glb(tree: AssetTree, vpath: str, *, game: str | None = None, textures: bool = True,
               db_path=None, stats: gltf.ExportStats | None = None) -> bytes:
    """The model at ``vpath`` as ``.glb`` bytes (skeleton, meshes, skin, textures)."""
    scene = read_scene(tree, vpath)
    finder = TextureFinder(tree, scene.source, game, db_path) if textures else None
    return gltf.model_to_glb(scene, finder, stats=stats,
                             base_colour=finder.baker(scene) if finder else None)


def export_skeleton_glb(tree: AssetTree, vpath: str) -> bytes:
    """Only the skeleton of the scene at ``vpath``, as ``.glb`` bytes."""
    return gltf.skeleton_to_glb(read_scene(tree, vpath))

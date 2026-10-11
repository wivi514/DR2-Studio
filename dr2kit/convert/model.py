"""Model export: a scene's vpath → ``.glb``, with its textures found and embedded.

`dr2kit.convert.gltf` turns a parsed `Scene` into glTF; this module does the parts that
need the game data around it:

* `TextureFinder` looks a material's texture up **by name**, closest first: the model's
  own pack (``npcs.big/chest_young_chuck.big`` → ``npcs.big/chest_young_chuck.tex``),
  then any texture or ``.tex`` pack in the archives that contain the model (nearest
  archive first), then the asset index (``dr2 index build``) if there is one. A name
  that is not found is reported, never silently replaced. A level piece's scene is
  ``<piece>.big/_COMP_<piece>.big``, so its own pack is ``<piece>.tex``. **Small copies
  come last:** ``<name>_LOD.tex`` packs hold the same names at a quarter of the size
  (the game's textures for far away); before phase 10 they were found first for level
  pieces, which exported blurry. ``lod=True`` asks for them first (the Maps tab's far
  zones). **In a level zone** the game takes a texture by name from the first pack of
  the zone that has it, whichever piece uses it (checked in game 2026-10-11: a mod on
  the shed's copy of a shared wall texture didn't show, on the earlier garage pack's
  copy it did), so there the finder goes by archive order, not own pack first.
* `export_glb` / `export_skeleton_glb` read a vpath and return the ``.glb`` bytes.
* `model_glb` (phase 9) is the one place a model becomes a ``.glb`` in a **look**
  (`convert.variants`): every part sorted into groups (``mode="all"``) or only the
  look's parts (``mode="shown"``), its colour choices baked by `TextureFinder.bake`.

Used by ``dr2 extract --glb`` and DR2 Studio's 3D view.
"""

from __future__ import annotations

from ..container.big import BigArchive, is_big
from ..container.vpath import AssetTree, join, split
from ..errors import Dr2Error
from ..formats.bct import is_bct
from ..formats.scene import Scene
from . import gltf


def texture_png(data: bytes, source: str = "<bct>", level: int = 6) -> bytes:
    """A texture's level 0 as PNG bytes (RGB, or RGBA when it has alpha). ``level`` is
    the zlib level: 6 for files people keep, 1 for the Maps tab's cache (3× faster)."""
    from ..formats.bct import Bct
    from . import png
    from .texture import png_mode, to_image
    tex = Bct.parse(data, source)
    img = to_image(tex, 0)
    return png.encode(img, png_mode(tex, img), level)


class TextureFinder:
    """``finder(name)`` → PNG bytes of the texture called ``name``, or None."""

    def __init__(self, tree: AssetTree, model_vpath: str, game: str | None = None,
                 db_path=None, lod: bool = False, shared: dict | None = None):
        self.tree, self.game, self.db_path = tree, game, db_path
        self.vpath = model_vpath
        self.lod = lod                           # the small _LOD copies first
        # `shared`: one dict handed to every finder of a batch (a level's pieces share
        # their wall and floor textures): parsed packs and PNGs, made once per batch
        self.shared = shared if shared is not None else {}
        self.found: dict[str, str] = {}          # name -> vpath it was read from
        self._scanned: list[dict[str, tuple[str, bytes]]] | None = None
        self._shaders = None                     # convert.material.ShaderLibrary, on demand
        self._baked: dict[tuple, tuple | None] = {}   # (material, value set, suffix) -> bake

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
        stem = self._stem()
        zone_vp = self.zone_archive()
        small: list[dict] = []                   # _LOD packs: after everything else
        for cvp in self._containers():
            try:
                arc = self.tree.open_archive(cvp)
            except Dr2Error:
                continue
            zone = zone_vp is not None and cvp.lower() == zone_vp.lower()
            own: dict[str, tuple[str, bytes]] = {}
            own_lod: dict[str, tuple[str, bytes]] = {}
            other: dict[str, tuple[str, bytes]] = {}
            other_lod: dict[str, tuple[str, bytes]] = {}
            for e in arc.entries:
                lname = e.name.lower()
                if lname.endswith(".tex"):
                    pack = self._pack(join(cvp, e.name), e)
                    if pack is None:
                        continue
                    pstem = lname[:-4]
                    is_lod = pstem.endswith("_lod")
                    # a level zone: the game takes a name from the FIRST pack of the zone
                    # that has it, whichever piece uses it (checked in game, phase 10):
                    # no own-pack priority there, archive order decides
                    mine = pstem.removesuffix("_lod") == stem and not zone
                    target = ((own_lod if mine else other_lod) if is_lod
                              else (own if mine else other))
                    for t in pack.entries:
                        key = t.name.lower().removesuffix(".bct")
                        target.setdefault(key, (join(cvp, e.name, t.name), t))
                elif lname.endswith(".bct") or e.ext == "":
                    other.setdefault(lname.removesuffix(".bct"), (join(cvp, e.name), e))
            if self.lod:
                self._scanned += [d for d in (own_lod, own, other_lod, other) if d]
            else:
                self._scanned += [d for d in (own, other) if d]
                small += [d for d in (own_lod, other_lod) if d]
        self._scanned += self._scan_folder(stem) + small
        return self._scanned

    def _pack(self, vpath: str, entry) -> BigArchive | None:
        """A ``.tex`` pack entry parsed (once per batch, `shared`), or None."""
        packs = self.shared.setdefault("packs", {})
        key = vpath.lower()
        if key not in packs:
            data = entry.data()
            packs[key] = BigArchive.parse(data, vpath) if is_big(data) else None
        return packs[key]

    def zone_archive(self) -> str | None:
        """The level zone archive holding this model (``…/environment/<level>/<zone>.big``),
        or None."""
        parts = split(self.vpath)
        low = [p.lower() for p in parts]
        if "environment" in low:
            i = low.index("environment")
            if len(parts) > i + 3 and low[i + 2].endswith(".big"):
                return join(*parts[:i + 3])
        return None

    def _stem(self) -> str:
        """The model's name as its own texture pack is named: ``chest_default`` for
        ``…/chest_default.big``; ``z05_bowling_struc`` for a level piece's
        ``…/z05_bowling_struc.big/_COMP_z05_bowling_struc.big``."""
        parts = split(self.vpath)
        stem = parts[-1].rsplit(".", 1)[0].lower()
        if stem.startswith("_comp_") and len(parts) > 1:
            outer = parts[-2].rsplit(".", 1)[0].lower()
            if outer == stem[len("_comp_"):]:
                return outer
        return stem

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
        lod_own: dict = {}
        lod_other: dict = {}
        for f in sorted(here.glob("*")) if here.is_dir() else []:
            if f.suffix.lower() != ".tex" or not f.is_file():
                continue
            vp = join(*folder_parts, f.name)
            try:
                pack = self.tree.open_archive(vp)
            except Dr2Error:
                continue
            low = f.stem.lower()
            is_lod = low.endswith("_lod")
            if is_lod != self.lod:               # the copies not asked for: last
                target = lod_own if low.removesuffix("_lod") == stem else lod_other
            else:
                target = own if low.removesuffix("_lod") == stem else other
            for t in pack.entries:
                target.setdefault(t.name.lower().removesuffix(".bct"), (join(vp, t.name), t))
        return [d for d in (own, other, lod_own, lod_other) if d]

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
        if hit is None:
            return None
        pngs = self.shared.setdefault("png", {})
        key = hit[0].lower()
        if key not in pngs:
            pngs[key] = texture_png(hit[1], hit[0], self.shared.get("png_level", 6))
        return pngs[key]

    def baker(self, scene: Scene, colours: dict | None = None):
        """The ``base_colour`` hook for `gltf.model_to_glb`: bakes materials whose colour
        is in shader constants (`convert.material`), None for the others.

        ``colours`` maps a material index to a value set swapped in for it (a colour
        choice, `convert.variants`); those materials bake with it."""
        colours = colours or {}

        def base_colour(m):
            i = next((k for k, x in enumerate(scene.materials) if x is m), -1)
            return self.bake(scene, m, colours.get(i))
        return base_colour

    def bake(self, scene: Scene, m, valueset=None, suffix: str = ""):
        """``(image name, png bytes, family)`` of material ``m`` baked (with ``valueset``
        instead of its own, if given), or None when it has nothing to bake. Remembered,
        so an export that bakes for the ``.glb`` and for ``textures/`` bakes once."""
        from . import material as cmat
        from . import png
        key = (id(m), valueset.name if valueset is not None else None, suffix)
        if key in self._baked:
            return self._baked[key]
        if self._shaders is None:
            self._shaders = cmat.ShaderLibrary(self.tree)
        rec = cmat.recipe(scene, m, self._shaders, valueset)
        out = None
        img = cmat.bake(rec, self.image) if rec is not None else None
        if img is not None:
            mode = "RGBA" if rec.family in ("lens", "hair") else "RGB"   # these keep opacity
            out = f"{rec.diffuse}_baked{suffix}", png.encode(img, mode), rec.family
        self._baked[key] = out
        return out


def read_scene(tree: AssetTree, vpath: str) -> Scene:
    node = tree.resolve(vpath)
    data = node.data()
    if not is_big(data):
        raise Dr2Error(f"{node.vpath} is not a scene (not a .big archive)")
    return Scene.parse(data, node.vpath)


MODES = ("all", "shown")     # every part sorted into groups / only the chosen parts


def model_glb(tree: AssetTree, scene: Scene, *, game: str | None = None, finder=None,
              textures: bool = True, db_path=None, stats: gltf.ExportStats | None = None,
              variant=None, mode: str = "all", colour_variants: bool = True,
              variants=None) -> bytes:
    """``.glb`` bytes of a parsed model, showing one look (`convert.variants`).

    * ``variant``: a `variants.Choice`, or choice text (``"head=2 colour.jersey=3"``),
      on top of the model's default look; None is the default look.
    * ``mode="all"``: every shape, each node tagged with its group and whether the look
      shows it (``dr2_group``, ``dr2_shown``, and ``dr2_part``: the mesh index, which
      Studio's 3D view uses to hide parts); with ``colour_variants`` and textures, every
      colour choice as a ``KHR_materials_variants`` variant. ``mode="shown"``: only the
      shapes the look shows, in its colours.
    * ``variants``: a `variants.ModelVariants` already read (else read here).
    """
    from . import variants as cvar
    if mode not in MODES:
        raise Dr2Error(f"unknown export mode {mode!r} (expected {' or '.join(MODES)})")
    if finder is None and textures:
        finder = TextureFinder(tree, scene.source, game, db_path)
    mv = variants or cvar.read_variants(tree, scene, game or "cz")
    choice = variant if isinstance(variant, cvar.Choice) else mv.parse(variant)
    bank = cvar.ColourBank(tree, game or "cz") if mv.colours and finder else None
    swaps = {}
    if bank is not None:
        for i, name in mv.colour_options(choice).items():
            vs = bank.valueset(name)
            if vs is not None:
                swaps[i] = vs
    shown = mv.shown(choice)
    parts = include = None
    if mv.has_choices:
        if mode == "shown":
            include = {i for i, s in enumerate(shown) if s}
        else:
            parts = [{"dr2_group": p.group, "dr2_shown": s, "dr2_part": p.index}
                     for p, s in zip(mv.parts, shown)]
    extra_variants = None
    if mode == "all" and colour_variants and bank is not None:
        extra_variants = []
        for col in mv.colours:
            for n, name in enumerate(col.options, 1):
                vs = bank.valueset(name)
                if vs is None:
                    continue
                mats = {}
                for i in col.materials:
                    baked = finder.bake(scene, scene.materials[i], vs, suffix=f"_{col.key}{n}")
                    if baked is not None:
                        mats[i] = baked
                if mats:
                    extra_variants.append((f"{col.key} {n}", mats))
    extras = {"dr2_variant": choice.text(), "dr2_mode": mode} if mv.has_choices else None
    return gltf.model_to_glb(scene, finder, stats=stats,
                             base_colour=finder.baker(scene, swaps) if finder else None,
                             parts=parts, include=include, colour_variants=extra_variants,
                             extras=extras)


def export_glb(tree: AssetTree, vpath: str, *, game: str | None = None, textures: bool = True,
               db_path=None, stats: gltf.ExportStats | None = None, variant=None,
               mode: str = "all") -> bytes:
    """The model at ``vpath`` as ``.glb`` bytes (skeleton, meshes, skin, textures), in
    the look ``variant`` (default: the game's default look; `model_glb`)."""
    scene = read_scene(tree, vpath)
    return model_glb(tree, scene, game=game, textures=textures, db_path=db_path,
                     stats=stats, variant=variant, mode=mode)


def export_skeleton_glb(tree: AssetTree, vpath: str) -> bytes:
    """Only the skeleton of the scene at ``vpath``, as ``.glb`` bytes."""
    return gltf.skeleton_to_glb(read_scene(tree, vpath))

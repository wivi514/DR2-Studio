"""DR2 Studio's 3D view: models and skeletons, drawn by three.js in a QWebEngineView.

Why a web view: the 3D preview shows the very ``.glb`` that ``dr2 extract --glb`` writes
for Blender (`dr2kit.convert.gltf`), so there is one export path to keep right, and
three.js's glTF loader does skinning, textures and an orbit camera for free
(docs/ARCHITECTURE.md §Stack). three.js (MIT) is vendored, unmodified, under
``web/vendor/three/`` so Studio works offline.

How the page gets its files: a custom ``dr2:`` URL scheme (`register_scheme`, which must
run before the QApplication exists) is served by `_SchemeHandler` from the package's
``web/`` folder, plus ``dr2://studio/model.glb``, the current model, straight from
memory. A custom scheme rather than ``file://`` because Chromium refuses ES modules from
``file://`` pages.

The page needs every module it imports (`viewer_files` follows the imports). A missing
one leaves the page at "loading…" with no error from Chromium, so `viewer.html` says so
itself, a test checks that git tracks them all, and the release gate checks the bundle
(a ``.gitignore`` rule once kept three.js's ``build/`` folder out of git, so a release
built from a clone had no 3D view).

If QtWebEngine is missing (it is a separate PySide6 add-on on some platforms) or the
environment variable ``DR2_STUDIO_NO_3D`` is set, `ModelViewer` shows a note instead and
the rest of Studio works as before; *Export .glb…* still gives the file for Blender.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QUrl, Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .variant_panel import VariantPanel

WEB_DIR = Path(__file__).with_name("web")
SCHEME = b"dr2"
PAGE_URL = "dr2://studio/viewer.html"
MODEL_PATH = "/model.glb"

MIME = {".html": b"text/html", ".js": b"text/javascript", ".glb": b"model/gltf-binary",
        ".json": b"application/json", "": b"application/octet-stream"}

# `import … from './x.js'`, `import './x.js'`, `<script src="./x.js">`
_IMPORT = re.compile(r"\b(?:import|from)\s*['\"]([^'\"]+)['\"]|\bsrc=\"([^\"]+)\"")


def viewer_files(web_dir: Path = WEB_DIR) -> tuple[list[Path], list[str]]:
    """The files the 3D page loads, found by following its imports from ``viewer.html``
    (the import map's ``three`` included): ``(found, missing)``, paths relative to
    ``web_dir`` in ``missing``."""
    html = (web_dir / "viewer.html").read_text(encoding="utf-8")
    bare = dict(re.findall(r'"([\w/-]+)"\s*:\s*"([^"]+)"', html.split("importmap", 1)[-1]
                           .split("</script>", 1)[0]))
    found: list[Path] = []
    missing: list[str] = []
    todo = [(web_dir / "viewer.html", html)]
    seen = {web_dir / "viewer.html"}
    while todo:
        here, text = todo.pop()
        found.append(here)
        for m in _IMPORT.finditer(text):
            spec = next(g for g in m.groups() if g)
            if spec in bare:
                target = web_dir / bare[spec]
            elif spec.startswith("."):
                target = here.parent / spec
            else:
                continue                       # a comment's example (three/addons/…)
            target = Path(os.path.normpath(target))
            if target in seen:
                continue
            seen.add(target)
            if target.is_file():
                todo.append((target, target.read_text(encoding="utf-8")
                             if target.suffix == ".js" else ""))
            else:
                missing.append(target.relative_to(web_dir).as_posix())
    return found, missing


try:
    if os.environ.get("DR2_STUDIO_NO_3D"):
        raise ImportError("DR2_STUDIO_NO_3D is set")
    from PySide6.QtWebEngineCore import (QWebEnginePage, QWebEngineProfile, QWebEngineUrlScheme,
                                         QWebEngineUrlSchemeHandler)
    from PySide6.QtWebEngineWidgets import QWebEngineView
    WEB_ENGINE = True
    WEB_ENGINE_ERROR = ""
except ImportError as e:  # pragma: no cover - depends on the PySide6 install
    WEB_ENGINE = False
    WEB_ENGINE_ERROR = str(e)

_registered = False


def register_scheme() -> bool:
    """Declare the ``dr2:`` scheme to Qt. Call before the QApplication is created;
    returns False (and the 3D view stays off) if that is too late or WebEngine is absent."""
    global _registered
    if _registered or not WEB_ENGINE:
        return _registered
    from PySide6.QtWidgets import QApplication
    if QApplication.instance() is not None:
        return False
    s = QWebEngineUrlScheme(SCHEME)
    s.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    flags = (QWebEngineUrlScheme.Flag.SecureScheme | QWebEngineUrlScheme.Flag.LocalScheme
             | QWebEngineUrlScheme.Flag.LocalAccessAllowed | QWebEngineUrlScheme.Flag.CorsEnabled)
    # three.js loads the .glb with fetch(), which Chromium allows on a custom scheme only
    # with this flag (Qt 6.6+; older Qt has no flag and the load fails with a message).
    fetch = getattr(QWebEngineUrlScheme.Flag, "FetchApiAllowed", None)
    if fetch is not None:
        flags |= fetch
    s.setFlags(flags)
    QWebEngineUrlScheme.registerScheme(s)
    _registered = True
    return True


def resource(path: str, model: bytes | None) -> tuple[bytes, bytes] | None:
    """What the ``dr2:`` scheme serves for a URL path: (MIME type, bytes), or None.

    ``/model.glb`` is the current model; anything else is a file under ``web/``
    (never outside it).
    """
    if path == MODEL_PATH:
        return (MIME[".glb"], model) if model is not None else None
    target = (WEB_DIR / path.lstrip("/")).resolve()
    if WEB_DIR.resolve() not in target.parents or not target.is_file():
        return None
    return MIME.get(target.suffix, MIME[""]), target.read_bytes()


if WEB_ENGINE:
    class _SchemeHandler(QWebEngineUrlSchemeHandler):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.model: bytes | None = None

        def requestStarted(self, job):  # noqa: N802 - Qt's name
            found = resource(job.requestUrl().path(), self.model)
            if found is None:
                job.fail(job.Error.UrlNotFound)
                return
            mime, data = found
            buf = QBuffer(job)             # lives as long as the request
            buf.setData(QByteArray(data))
            buf.open(QIODevice.ReadOnly)
            job.reply(mime, buf)

    class _Page(QWebEnginePage):
        """Forwards the page's ``dr2:`` console lines to the widget."""
        def __init__(self, profile, on_message, parent):
            super().__init__(profile, parent)
            self._on_message = on_message

        def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802
            if message.startswith("dr2:"):
                self._on_message(message[4:])


_shared: tuple | None = None


def _profile_and_handler():
    """One off-the-record profile and scheme handler for the whole application. They are
    parented to the QApplication so they outlive every page (Qt warns, and can crash, when
    a profile goes before its pages)."""
    global _shared
    if _shared is None:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        profile = QWebEngineProfile(app)                 # off the record: no disk cache
        handler = _SchemeHandler(app)
        profile.installUrlSchemeHandler(SCHEME, handler)
        _shared = (profile, handler)
    return _shared


class ModelViewer(QWidget):
    """The centre pane for models and skeletons: an orbit view of a ``.glb``."""

    status = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        self.skeleton = QCheckBox("Skeleton")
        self.wireframe = QCheckBox("Wireframe")
        self.reset = QPushButton("Reset view")
        self.info = QLabel("")
        for w in (self.skeleton, self.wireframe, self.reset):
            bar.addWidget(w)
        bar.addWidget(self.info, 1)
        lay.addLayout(bar)
        self.ready = False
        self._pending: str | None = None
        self._serial = 0
        self.last_message = ""
        self.view = None
        # variants (phase 9): the panel beside the view, for models with choices
        self.variants = VariantPanel(self)
        self.variants.hide()
        body = QHBoxLayout()
        lay.addLayout(body, 1)
        if WEB_ENGINE and _registered:
            self._profile, self._handler = _profile_and_handler()
            self.view = QWebEngineView(self)
            self._page = _Page(self._profile, self._message, self.view)   # keep a reference
            self.view.setPage(self._page)
            self.view.load(QUrl(PAGE_URL))
            body.addWidget(self.view, 1)
            body.addWidget(self.variants)
            self.skeleton.toggled.connect(lambda on: self._js(f"dr2.setSkeleton({str(on).lower()})"))
            self.wireframe.toggled.connect(lambda on: self._js(f"dr2.setWireframe({str(on).lower()})"))
            self.reset.clicked.connect(lambda: self._js("dr2.resetView()"))
        else:
            why = WEB_ENGINE_ERROR or "the dr2: scheme could not be registered"
            note = QLabel("The 3D view needs PySide6's QtWebEngine (" + why + ").\n\n"
                          "Use “Export .glb…” and open the file in Blender instead.")
            note.setWordWrap(True)
            body.addWidget(note, 1)
            body.addWidget(self.variants)
            for w in (self.skeleton, self.wireframe, self.reset):
                w.setEnabled(False)

    @property
    def available(self) -> bool:
        return self.view is not None

    def set_title(self, title: str) -> None:
        """The text next to the buttons (e.g. "exporting…" while a model is prepared)."""
        self.info.setText(title)

    def show_glb(self, data: bytes, title: str = "", keep_view: bool = False,
                 shown: list[bool] | None = None) -> None:
        """Show a ``.glb`` (bytes from `dr2kit.convert.gltf`). ``keep_view`` keeps the
        camera (a re-baked colour choice); ``shown``: which parts show (variants)."""
        self.info.setText(title)
        if self.view is None:
            return
        self._handler.model = data
        self._serial += 1                       # a new URL each time: no stale cache
        call = (self._shown_call(shown) + ";" +
                f"dr2.load('dr2://studio{MODEL_PATH}?{self._serial}', {str(keep_view).lower()})")
        if self.ready:
            self._js(call)
        else:
            self._pending = call

    @staticmethod
    def _shown_call(shown: list[bool] | None) -> str:
        if shown is None:
            return "dr2.setShown(null)"
        return "dr2.setShown([" + ",".join("1" if s else "0" for s in shown) + "])"

    def set_shown(self, shown: list[bool] | None) -> None:
        """Show part ``i`` of the current model when ``shown[i]`` (instant, no reload)."""
        self._js(self._shown_call(shown))

    def _js(self, code: str) -> None:
        if self.view is not None and self.ready:
            self.view.page().runJavaScript(code)

    def _message(self, text: str) -> None:
        self.last_message = text
        if text == "ready":
            self.ready = True
            if self._pending:
                self._js(self._pending)
                self._pending = None
            return
        self.status.emit(text)

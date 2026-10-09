"""Render DR2 Studio's icon (``dr2kit/studio/icon/dr2studio.svg``) for packaging.

The icon is our own drawing (a wrench on a blood-red tile; no game art). Studio loads
the SVG itself; releases need bitmaps: PNGs for Linux (AppImage, ``.desktop``), an
``.ico`` for the Windows executables and an ``.icns`` for the macOS app. Qt's SVG
renderer (PySide6, already in the release venv) draws each size; Pillow writes the
``.ico`` and ``.icns``.

Usage: python tools/release/make_icons.py [out_dir]      (default: build/icon)
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SVG = ROOT / "dr2kit" / "studio" / "icon" / "dr2studio.svg"
SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)


def render(size: int) -> bytes:
    """The icon as PNG bytes at ``size`` × ``size``."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QBuffer, QIODevice, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    _app = QGuiApplication.instance() or QGuiApplication([])
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(str(SVG)).render(p)
    p.end()
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def make(out: Path) -> dict[str, Path]:
    """Write ``dr2studio-<size>.png``, ``dr2studio.ico``, ``dr2studio.icns``."""
    from PIL import Image
    out.mkdir(parents=True, exist_ok=True)
    pngs = {}
    for s in SIZES:
        data = render(s)
        (out / f"dr2studio-{s}.png").write_bytes(data)
        pngs[s] = Image.open(io.BytesIO(data))
    big = pngs[1024]
    big.save(out / "dr2studio.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    big.save(out / "dr2studio.icns")
    return {"png": out / "dr2studio-256.png", "ico": out / "dr2studio.ico",
            "icns": out / "dr2studio.icns"}


if __name__ == "__main__":
    for kind, path in make(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "icon").items():
        print(f"{kind}: {path}")

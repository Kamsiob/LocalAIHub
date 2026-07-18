"""Render the app SVG icon into the PNG sizes Linux icon themes expect.

Usage: render_icon.py <svg_path> <hicolor_dir>
Writes <hicolor_dir>/<size>x<size>/apps/local-ai-hub.png for each standard size.
Uses the venv's Qt (QtSvg) — no external converter needed.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

SIZES = [16, 24, 32, 48, 64, 128, 256, 512]
NAME = "local-ai-hub"


def main() -> int:
    svg_path = sys.argv[1]
    hicolor = sys.argv[2]
    app = QGuiApplication(sys.argv)  # noqa: F841 (needed for Qt image stack)
    renderer = QSvgRenderer(svg_path)
    if not renderer.isValid():
        print(f"invalid SVG: {svg_path}", file=sys.stderr)
        return 1
    for size in SIZES:
        img = QImage(size, size, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        renderer.render(painter)
        painter.end()
        out_dir = os.path.join(hicolor, f"{size}x{size}", "apps")
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, f"{NAME}.png")
        img.save(out, "PNG")
        print(f"  wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

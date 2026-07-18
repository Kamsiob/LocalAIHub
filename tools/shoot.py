"""Render an HTML file headlessly and save a PNG, for visual verification.

Usage: shoot.py <html_path> <out_png> [theme] [width] [height] [wait_ms]
Uses the offscreen platform + software rendering so it needs no display.
"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --disable-software-rasterizer=0 --no-sandbox"

from PySide6.QtCore import QUrl, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402

html = sys.argv[1]
out = sys.argv[2]
theme = sys.argv[3] if len(sys.argv) > 3 else None
w = int(sys.argv[4]) if len(sys.argv) > 4 else 760
h = int(sys.argv[5]) if len(sys.argv) > 5 else 900
wait_ms = int(sys.argv[6]) if len(sys.argv) > 6 else 1600

app = QApplication(sys.argv)
view = QWebEngineView()
view.resize(w, h)
view.show()


def after_load(ok):
    def do_theme():
        if theme:
            view.page().runJavaScript(
                f"document.documentElement.dataset.theme='{theme}';"
                f"localStorage.setItem('theme','{theme}');", lambda _: None)
        QTimer.singleShot(wait_ms, grab)

    def grab():
        pix = view.grab()
        pix.save(out, "PNG")
        print(f"saved {out} ({pix.width()}x{pix.height()}) loadOk={ok}")
        app.quit()

    QTimer.singleShot(600, do_theme)


view.loadFinished.connect(after_load)
view.load(QUrl.fromLocalFile(os.path.abspath(html)))
QTimer.singleShot(15000, app.quit)  # safety
app.exec()

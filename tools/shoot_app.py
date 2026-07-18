"""Render the REAL app (with live Backend + QWebChannel) headlessly to a PNG.

Usage: shoot_app.py <out_png> [theme] [wait_ms]
Confirms real service status + model data reaches the UI through the bridge.
"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --no-sandbox"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import app as appmod  # noqa: E402

out = sys.argv[1]
theme = sys.argv[2] if len(sys.argv) > 2 else "dark"
wait = int(sys.argv[3]) if len(sys.argv) > 3 else 3800

application = QApplication(sys.argv)
win = appmod.MainWindow()
win.resize(760, 900)
win.show()


def capture():
    # Click chevrons one at a time, re-querying each time (each click re-renders
    # the card list, so a cached NodeList would go stale — same as a real user).
    win.view.page().runJavaScript(
        f"document.documentElement.dataset.theme='{theme}';"
        "(function(){var n=document.querySelectorAll('.chevron').length;"
        "for(var i=0;i<n;i++){(function(k){setTimeout(function(){"
        "var c=document.querySelectorAll('.chevron')[k]; if(c) c.click();},k*250);})(i);}})();",
        lambda _: None)
    QTimer.singleShot(1600, lambda: (
        win.view.grab().save(out, "PNG"),
        print(f"saved {out}"),
        application.quit(),
    ))


QTimer.singleShot(wait, capture)
QTimer.singleShot(wait + 8000, application.quit)
application.exec()

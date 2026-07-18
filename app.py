#!/usr/bin/env python3
"""local-ai-hub — PySide6 + QtWebEngine desktop app.

The UI is a local web front-end (web/) rendered in a QWebEngineView. Backend
wiring (service control, live status, model management, theme persistence) is
added over QWebChannel in a later step; this shell just hosts the page.
"""
import os
import sys
from pathlib import Path

# Software rendering keeps the simple UI robust across GPU/driver quirks.
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Local AI Hub")
        self.resize(760, 760)
        self.view = QWebEngineView(self)
        self.view.load(QUrl.fromLocalFile(str(WEB / "index.html")))
        self.setCentralWidget(self.view)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Local AI Hub")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

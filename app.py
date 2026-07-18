#!/usr/bin/env python3
"""local-ai-hub — PySide6 + QtWebEngine desktop app.

The UI is a local web front-end (web/) rendered in a QWebEngineView and wired to
Python over QWebChannel. This step exposes live, read-only state (real service
status + the real Ollama model list) and opens the browse links in a real
browser. Active controls (start/stop, model update) and theme persistence are
added in Phase 4.
"""
import json
import os
import sys
import threading
from pathlib import Path

os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PySide6.QtCore import QObject, QUrl, Signal, Slot  # noqa: E402
from PySide6.QtGui import QDesktopServices  # noqa: E402
from PySide6.QtWebChannel import QWebChannel  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT))

from hub.services import ComfyUIService, OllamaService, OpenWebUIService  # noqa: E402


class Backend(QObject):
    """Exposed to JS as `backend` over QWebChannel."""

    state_changed = Signal(str)   # JSON: {services:{...}, models:[...]}
    notify = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.ollama = OllamaService()
        self.openwebui = OpenWebUIService()
        self.comfyui = ComfyUIService()

    # --- state collection ----------------------------------------------------
    def _collect(self) -> dict:
        services: dict = {}
        for key, svc in (
            ("ollama", self.ollama),
            ("openwebui", self.openwebui),
            ("comfyui", self.comfyui),
        ):
            try:
                st = svc.status()
                services[key] = {"active": st.active, "serving": st.serving}
            except Exception:
                services[key] = {"active": False, "serving": False}

        # Ollama extras: loaded-in-memory model + installed model list
        loaded = None
        models: list = []
        if services["ollama"]["active"]:
            try:
                loaded = self.ollama.loaded_model()
            except Exception:
                loaded = None
            try:
                models = [m.to_dict() for m in self.ollama.list_models()]
            except Exception:
                models = []
        services["ollama"]["loaded"] = loaded
        return {"services": services, "models": models}

    def _refresh_async(self) -> None:
        def work() -> None:
            payload = self._collect()
            self.state_changed.emit(json.dumps(payload))
        threading.Thread(target=work, daemon=True).start()

    # --- slots callable from JS ---------------------------------------------
    @Slot()
    def request_refresh(self) -> None:
        self._refresh_async()

    @Slot(str)
    def open_url(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Local AI Hub")
        self.resize(760, 760)

        self.view = QWebEngineView(self)
        self.backend = Backend()
        self.channel = QWebChannel()
        self.channel.registerObject("backend", self.backend)
        self.view.page().setWebChannel(self.channel)

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

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
import time
from pathlib import Path

os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot  # noqa: E402
from PySide6.QtGui import QDesktopServices  # noqa: E402
from PySide6.QtWebChannel import QWebChannel  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT))

from hub import config  # noqa: E402
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
        self._services = {
            "ollama": self.ollama,
            "openwebui": self.openwebui,
            "comfyui": self.comfyui,
        }

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

        # ComfyUI extras: models are a disk scan (shown even when stopped);
        # "generating" is only meaningful while the service is up and a job runs.
        services["comfyui"]["generating"] = (
            self.comfyui.is_generating() if services["comfyui"]["active"] else False
        )
        try:
            comfyui_models = self.comfyui.list_models()
        except Exception:
            comfyui_models = []

        return {"services": services, "models": models, "comfyui_models": comfyui_models}

    def _refresh_async(self) -> None:
        def work() -> None:
            payload = self._collect()
            self.state_changed.emit(json.dumps(payload))
        threading.Thread(target=work, daemon=True).start()

    # --- slots callable from JS ---------------------------------------------
    @Slot()
    def request_refresh(self) -> None:
        self._refresh_async()

    @Slot(str, bool)
    def set_service(self, key: str, turn_on: bool) -> None:
        """Start/stop a real service, then stream status updates as it settles."""
        svc = self._services.get(key)
        if svc is None:
            return

        def work() -> None:
            try:
                ok = svc.start() if turn_on else svc.stop()
                verb = "started" if turn_on else "stopped"
                self.notify.emit(f"{svc.display_name} {verb}" if ok
                                 else f"{svc.display_name} failed to {verb[:-4] or 'change'}")
            except Exception as exc:  # noqa: BLE001
                self.notify.emit(f"{svc.display_name}: {exc}")
            # Emit a few refreshes so the UI reflects starting -> running/stopped.
            for _ in range(10):
                self.state_changed.emit(json.dumps(self._collect()))
                time.sleep(1)

        threading.Thread(target=work, daemon=True).start()

    @Slot(str)
    def pull_model(self, name: str) -> None:
        """Pull/update a model via the real Ollama API, reporting progress."""
        def work() -> None:
            last = [-1]

            def cb(status: str, frac: float) -> None:
                pct = int(frac * 100)
                # Throttle: only surface at ~20% steps or on named phases.
                if pct >= last[0] + 20 or status in ("pulling manifest", "verifying sha256 digest", "success"):
                    last[0] = pct
                    msg = f"{name}: {status}" + (f" {pct}%" if 0 < pct < 100 and "pulling" in status else "")
                    self.notify.emit(msg)

            try:
                self.notify.emit(f"Updating {name}…")
                self.ollama.pull_model(name, progress_cb=cb)
                self.notify.emit(f"{name} is up to date")
            except Exception as exc:  # noqa: BLE001
                self.notify.emit(f"Update failed for {name}: {exc}")
            self.state_changed.emit(json.dumps(self._collect()))

        threading.Thread(target=work, daemon=True).start()

    @Slot(result=str)
    def get_theme(self) -> str:
        return config.get("theme") or ""

    @Slot(str)
    def set_theme(self, theme: str) -> None:
        if theme in ("light", "dark"):
            config.set_("theme", theme)

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

        # Keep the UI in sync with reality (service crashes, models loading, etc.)
        # even when the user isn't clicking anything.
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(5000)
        self.refresh_timer.timeout.connect(self.backend.request_refresh)
        self.refresh_timer.start()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Local AI Hub")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

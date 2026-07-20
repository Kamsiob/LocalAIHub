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

# When frozen by PyInstaller, bundled data (web/, added via --add-data) lives
# under sys._MEIPASS; running from source it sits next to this file.
if getattr(sys, "frozen", False):
    ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT))

from hub import config  # noqa: E402
from hub.guide import GUIDE  # noqa: E402
from hub.services import ComfyUIService, OllamaService, OpenWebUIService  # noqa: E402
from hub.services import comfy_models  # noqa: E402
from hub.services import setup_check  # noqa: E402


class Backend(QObject):
    """Exposed to JS as `backend` over QWebChannel."""

    state_changed = Signal(str)   # JSON: {services:{...}, models:[...]}
    notify = Signal(str)
    setup_result = Signal(str)    # JSON of a fresh setup-check run (after a fix)
    download_progress = Signal(str)  # JSON: {active, label, fraction, stage}

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
        self._last_failed: dict = {}   # for one-shot "stopped unexpectedly" alerts
        self._ollama_updates: dict = {}   # model name -> last update-check result

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
                services[key] = {"active": st.active, "serving": st.serving,
                                 "failed": st.failed, "result": st.result,
                                 "present": st.present}
            except Exception:
                services[key] = {"active": False, "serving": False, "failed": False,
                                 "present": True, "result": ""}

            # One-shot alert when a service transitions into the failed state.
            is_failed = services[key].get("failed")
            if is_failed and not self._last_failed.get(key):
                self.notify.emit(f"{svc.display_name} stopped unexpectedly — check its log")
            self._last_failed[key] = is_failed

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
        # Attach the cached update-check result (checks happen only on demand,
        # never on the periodic refresh — no unsolicited registry calls).
        for m in models:
            m["update"] = self._ollama_updates.get(m["name"])
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
        # Enrich each ComfyUI model with its known source + last cached update
        # check (no network here — checks happen only on explicit request).
        manifest = comfy_models.load_manifest()
        mroot = self.comfyui.models_dir
        for m in comfyui_models:
            # Enrichment must never hide a model or break the list: a bad manifest
            # entry degrades that one row to "no tracking", nothing more.
            try:
                abs_path = str((mroot / m["category"] / m["name"]).resolve())
                src = manifest.get(abs_path)
                src = src if isinstance(src, dict) else {}
                m["path"] = abs_path
                m["source"] = src.get("source")
                m["update"] = src.get("last_check")
                m["untracked"] = bool(src.get("untracked")) and not src.get("source")
            except Exception:
                m.setdefault("path", "")
                m["source"] = None
                m["update"] = None
                m["untracked"] = False

        return {"services": services, "models": models, "comfyui_models": comfyui_models}

    # --- ComfyUI model provenance + updates ---------------------------------
    def _emit_state(self) -> None:
        self.state_changed.emit(json.dumps(self._collect()))

    @Slot(str)
    def comfy_identify(self, path: str) -> None:
        """Auto-identify a model on Civitai by hashing it (may take a while)."""
        def work() -> None:
            self.notify.emit(f"Identifying {Path(path).name} on Civitai… (hashing)")
            try:
                res = comfy_models.identify_civitai(path)
                self.notify.emit(res.get("detail", "done"))
            except Exception as exc:  # noqa: BLE001
                self.notify.emit(f"Identify failed: {exc}")
            self._emit_state()
        threading.Thread(target=work, daemon=True).start()

    @Slot(str, str)
    def comfy_set_hf(self, path: str, repo: str) -> None:
        def work() -> None:
            try:
                res = comfy_models.resolve_hf(path, repo)
                self.notify.emit(res.get("detail", "done"))
            except Exception as exc:  # noqa: BLE001
                self.notify.emit(f"Hugging Face link failed: {exc}")
            self._emit_state()
        threading.Thread(target=work, daemon=True).start()

    @Slot(str, str)
    def comfy_set_url(self, path: str, url: str) -> None:
        def work() -> None:
            try:
                res = comfy_models.set_url(path, url)
                self.notify.emit(res.get("detail", "done"))
            except Exception as exc:  # noqa: BLE001
                self.notify.emit(f"URL link failed: {exc}")
            self._emit_state()
        threading.Thread(target=work, daemon=True).start()

    @Slot(str)
    def comfy_check(self, path: str) -> None:
        def work() -> None:
            try:
                st = comfy_models.check_update(path)
                comfy_models.set_source(path, {"last_check": {
                    "available": st["available"], "detail": st["detail"],
                    "latest": st["latest"], "error": st["error"]}})
                self.notify.emit(f"{Path(path).name}: {st['detail']}")
            except Exception as exc:  # noqa: BLE001
                self.notify.emit(f"Check failed: {exc}")
            self._emit_state()
        threading.Thread(target=work, daemon=True).start()

    @Slot(str)
    def comfy_update(self, path: str) -> None:
        def work() -> None:
            label = f"Updating {Path(path).name}"

            def cb(stage: str, frac: float) -> None:
                self._progress(True, label, frac, stage)

            self._progress(True, label, 0.0, "starting")
            try:
                res = comfy_models.update_model(path, progress_cb=cb)
                self.notify.emit(res.get("reason", "done"))
                if res.get("updated"):
                    comfy_models.set_source(path, {"last_check": {"available": False, "detail": "Up to date"}})
            except Exception as exc:  # noqa: BLE001
                self.notify.emit(f"Update failed: {exc}")
            finally:
                self._progress(False, "", 1.0, "done")
            self._emit_state()
        threading.Thread(target=work, daemon=True).start()

    def _progress(self, active: bool, label: str, fraction: float, stage: str) -> None:
        self.download_progress.emit(json.dumps(
            {"active": active, "label": label, "fraction": fraction, "stage": stage}))

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
                action = "start" if turn_on else "stop"
                self.notify.emit(f"{svc.display_name} {verb}" if ok
                                 else f"{svc.display_name} failed to {action}")
            except Exception as exc:  # noqa: BLE001
                self.notify.emit(f"{svc.display_name}: {exc}")
            # Emit a few refreshes so the UI reflects starting -> running/stopped.
            for _ in range(10):
                self.state_changed.emit(json.dumps(self._collect()))
                time.sleep(1)

        threading.Thread(target=work, daemon=True).start()

    @Slot(str)
    def check_ollama_update(self, name: str) -> None:
        def work() -> None:
            try:
                st = self.ollama.check_update(name)
                self._ollama_updates[name] = st
                self.notify.emit(f"{name}: {st['detail']}")
            except Exception as exc:  # noqa: BLE001
                self.notify.emit(f"Check failed: {exc}")
            self._emit_state()
        threading.Thread(target=work, daemon=True).start()

    @Slot()
    def check_ollama_updates(self) -> None:
        """Check every installed Ollama model for updates (used by Refresh)."""
        def work() -> None:
            try:
                names = [m.name for m in self.ollama.list_models()]
            except Exception:
                names = []
            for name in names:
                try:
                    self._ollama_updates[name] = self.ollama.check_update(name)
                except Exception:
                    pass
            self.notify.emit("Checked models for updates")
            self._emit_state()
        threading.Thread(target=work, daemon=True).start()

    @Slot(str)
    def pull_model(self, name: str) -> None:
        """Pull/update a model via the real Ollama API, reporting progress."""
        def work() -> None:
            label = f"Updating {name}"

            def cb(status: str, frac: float) -> None:
                self._progress(True, label, frac, status)

            self._progress(True, label, 0.0, "starting")
            try:
                self.ollama.pull_model(name, progress_cb=cb)
                self.notify.emit(f"{name} is up to date")
                self._ollama_updates[name] = {"available": False, "detail": "Up to date"}
            except Exception as exc:  # noqa: BLE001
                self.notify.emit(f"Update failed for {name}: {exc}")
            finally:
                self._progress(False, "", 1.0, "done")
            self.state_changed.emit(json.dumps(self._collect()))

        threading.Thread(target=work, daemon=True).start()

    @Slot(result=str)
    def get_theme(self) -> str:
        return config.get("theme") or ""

    @Slot(str)
    def set_theme(self, theme: str) -> None:
        if theme in ("light", "dark"):
            config.set_("theme", theme)

    @Slot(str, result=str)
    def get_log(self, key: str) -> str:
        """Last log lines for a service, shown after a crash."""
        svc = self._services.get(key)
        if svc is None:
            return "(unknown service)"
        try:
            return svc.logs(40)
        except Exception as exc:  # noqa: BLE001
            return f"(could not read log: {exc})"

    @Slot(result=str)
    def get_guide(self) -> str:
        return json.dumps(GUIDE)

    @Slot(str)
    def set_civitai_key(self, key: str) -> None:
        config.set_("civitai_api_key", key.strip())
        self.notify.emit("Civitai API key saved" if key.strip() else "Civitai API key cleared")

    @Slot(result=str)
    def run_setup_check(self) -> str:
        try:
            return json.dumps(setup_check.run_checks())
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"applies": False, "error": str(exc), "platform": {}, "checks": []})

    @Slot(str)
    def apply_setup_fix(self, fix_id: str) -> None:
        def work() -> None:
            self.notify.emit("Applying fix…")
            try:
                res = setup_check.apply_fix(fix_id)
                self.notify.emit(res.get("message", "done"))
            except Exception as exc:  # noqa: BLE001
                self.notify.emit(f"Fix failed: {exc}")
            try:
                self.setup_result.emit(json.dumps(setup_check.run_checks()))
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    @Slot(str)
    def open_url(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    @Slot(result=bool)
    def in_flatpak(self) -> bool:
        """True in the Flatpak build — the UI uses this to be upfront that log
        viewing isn't available in the sandbox (crash detection still works)."""
        return bool(os.environ.get("FLATPAK_ID"))


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
    # Associates the window with local-ai-hub.desktop so KDE/Wayland groups it
    # under the launcher icon and it can be pinned to the taskbar.
    app.setDesktopFileName("local-ai-hub")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

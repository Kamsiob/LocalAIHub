"""Render the README / MetaInfo screenshots from representative demo data.

Screenshots of this app are screenshots of somebody's machine: the second group
lists exactly what they self-host, by name and port, and an expanded Hermes card
prints the endpoint it talks to. That is a homelab inventory, and it does not
belong in a public repository just because it was convenient to capture.

So the shots are taken against a fixed demo payload instead — the same approach
the front-end already takes for its no-backend SAMPLE data. Nothing here is read
from the machine running it, which also means the pictures stay identical
whatever is installed on the release box.

Usage: shoot_readme.py <out.png> <light|dark> <width> <height>
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --no-sandbox"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import app as appmod  # noqa: E402


def service(active=True):
    return {"active": active, "serving": active, "failed": False,
            "present": True, "result": ""}


def app_entry(name, kind, port):
    return {"key": f"container:{name.lower().replace(' ', '-')}.service",
            "unit": f"{name.lower().replace(' ', '-')}.service",
            "name": name, "kind": kind, "container": name.lower(),
            "active": True, "serving": True, "port": port,
            "bound_host": "127.0.0.1",
            "reachable": [{"kind": "loopback", "url": f"http://127.0.0.1:{port}",
                           "meaning": "Only on this computer"}]}


# A plausible, entirely generic homelab. Five entries keeps the group expanded
# (the collapse threshold is six) so the layout is what the picture shows.
DEMO = {
    "services": {"ollama": service(), "openwebui": service(), "comfyui": service()},
    "models": [],
    "comfyui_models": [],
    "addresses": {"loopback": {"host": "127.0.0.1", "meaning": "Only on this computer"}},
    "layers": [{
        "key": "hermes", "name": "Hermes Agent",
        "tagline": "Agent harness", "depends_on": "ollama",
        "active": True, "serving": True, "failed": False, "present": True,
        # The card renders folded, so none of this is visible; it is here only
        # so the card has the shape it has in real use.
        "info": {"reachable": True, "version": "0.20.0", "gateway": "running",
                 "gateway_running": True, "active_agents": 0, "auth_required": True,
                 "model": "", "context": None, "backend_url": "",
                 "dashboard_url": "http://127.0.0.1:9119",
                 "api_url": "http://127.0.0.1:8642", "unavailable": []},
        "dependency": {"key": "ollama", "name": "Ollama", "active": True, "present": True},
        "model_state": {"known": False},
    }],
    "apps": {"supported": True, "limit": None, "items": [
        app_entry("Jellyfin", "Media", 8096),
        app_entry("Nextcloud", "Files", 8080),
        app_entry("Paperless-ngx", "Documents", 8000),
        app_entry("Uptime Kuma", "Monitoring", 3001),
        app_entry("Vaultwarden", "Passwords", 8222),
    ]},
}


def main() -> int:
    out, theme = sys.argv[1], sys.argv[2]
    width = int(sys.argv[3]) if len(sys.argv) > 3 else 768
    height = int(sys.argv[4]) if len(sys.argv) > 4 else 1210

    qapp = QApplication(sys.argv)
    win = appmod.MainWindow()
    win.resize(width, height)
    win.show()

    def go():
        # The live backend would otherwise push this machine's real state over
        # the demo payload a second or two after it is injected.
        win.refresh_timer.stop()
        try:
            win.watcher.changed.disconnect()
        except Exception:
            pass
        win.view.page().runJavaScript(
            f"document.documentElement.dataset.theme='{theme}';"
            f"window.__applyState({json.dumps(DEMO)});",
            lambda _r: None)
        QTimer.singleShot(1400, lambda: (
            win.view.grab().save(out, "PNG"), print(f"saved {out}"), qapp.quit()))

    # Long enough for QtWebEngine to have loaded and wired the channel.
    QTimer.singleShot(6500, go)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())

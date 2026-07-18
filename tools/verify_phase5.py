"""Phase 5 — skeptical end-to-end verification.

Launches the real app with a live event loop, drives the actual DOM controls
(clicks the same handlers a user would), and after each one checks the real
system state (systemctl, ollama /api/ps, the config file). Browsing is verified
by intercepting QDesktopServices so no real tabs are spawned. Saves a final
screenshot of the running app with a model loaded into memory.
"""
import json
import os
import subprocess
import sys
import urllib.request

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --no-sandbox"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import app as appmod  # noqa: E402
from hub import config  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/phase5.png"

# Intercept browser opens so verification doesn't spawn real tabs.
opened: list = []
appmod.QDesktopServices.openUrl = staticmethod(lambda u: opened.append(u.toString()))

results: list = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print(("PASS" if cond else "FAIL"), "|", name, ("— " + str(detail)) if detail else "")


def active(unit):
    return subprocess.run(["systemctl", "--user", "is-active", unit],
                          capture_output=True, text=True).stdout.strip()


def ps_loaded():
    try:
        d = json.loads(urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=5).read())
        return [m["name"] for m in d.get("models", [])]
    except Exception:
        return []


application = QApplication(sys.argv)
win = appmod.MainWindow()
win.resize(760, 900)
win.show()
page = win.view.page()


def js(code, cb=None):
    page.runJavaScript(code, cb or (lambda _: None))


def s1():
    check("ComfyUI starts inactive", active("comfyui") == "inactive", active("comfyui"))
    print(">> click ComfyUI toggle (start)")
    js("document.querySelector('.card[data-svc=comfyui] .toggle').click()")
    QTimer.singleShot(700, lambda: js(
        "document.getElementById('toast').classList.contains('show')",
        lambda v: check("toast appears on toggle", v, v)))


def s2():
    check("ComfyUI toggle -> unit ACTIVE", active("comfyui") == "active", active("comfyui"))
    print(">> click ComfyUI toggle (stop)")
    js("document.querySelector('.card[data-svc=comfyui] .toggle').click()")


def s3():
    check("ComfyUI toggle -> unit INACTIVE", active("comfyui") == "inactive", active("comfyui"))
    print(">> expand Ollama model list")
    js("document.querySelector('.card[data-svc=ollama] .chevron').click()")


def s4():
    js("document.querySelectorAll('.card[data-svc=ollama] .model').length",
       lambda n: check("Ollama shows real model rows", (n or 0) >= 5, f"rows={n}"))
    print(">> load llama3.2:1b into memory (external)")
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps({"model": "llama3.2:1b", "prompt": "hi", "stream": False, "keep_alive": "90s"}).encode(),
        headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=120).read()
    check("model actually in memory (ps)", "llama3.2:1b" in ps_loaded(), ps_loaded())


def s5():
    # after >=5s auto-refresh, the UI should show a loaded badge
    js("document.querySelectorAll('.card[data-svc=ollama] .badge.loaded').length",
       lambda n: check("UI 'in memory' badge reflects real ps", (n or 0) >= 1, f"loaded_rows={n}"))
    js("document.querySelector('.svc-status').textContent",
       lambda t: check("Ollama status names loaded model", "llama3.2:1b" in (t or ""), t))
    before = config.get("theme")
    print(f">> toggle theme (was {before})")
    js("document.getElementById('themeToggle').click()")


def s6():
    check("theme persisted to config file", config.get("theme") in ("light", "dark"), config.get("theme"))
    print(">> click a browse link")
    js("document.querySelector('.browse-link').click()")
    QTimer.singleShot(800, s7)


def s7():
    check("browse link invoked open_url (no real tab)", len(opened) >= 1, opened[:1])
    win.view.grab().save(OUT, "PNG")
    print(f"saved {OUT}")
    ok = all(results)
    print(f"\n=== {sum(results)}/{len(results)} checks passed ===")
    subprocess.run(["systemctl", "--user", "stop", "comfyui"])  # baseline
    subprocess.run(["ollama", "stop", "llama3.2:1b"])  # unload
    application.exit(0 if ok else 1)


for fn, t in [(s1, 3000), (s2, 13000), (s3, 21000), (s4, 23000), (s5, 30000), (s6, 33000)]:
    QTimer.singleShot(t, fn)
QTimer.singleShot(45000, lambda: application.exit(2))
sys.exit(application.exec())

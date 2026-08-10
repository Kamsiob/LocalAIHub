#!/usr/bin/env python3
"""End-to-end: does the running app's state actually flip when a tool vanishes?

Drives the real Backend (the same object the UI is bound to over QWebChannel),
points ComfyUI at a scratch folder, and watches the JSON that gets pushed to the
front-end while that folder is created and deleted underneath it. Proves the
"Not installed" card would appear and disappear without an app restart.

The real ComfyUI install is never touched — COMFYUI_HOME is redirected first.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SCRATCH = Path(tempfile.mkdtemp(prefix="lah-live-"))
os.environ["COMFYUI_HOME"] = str(SCRATCH / "ComfyUI")

from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402

import app as hub_app  # noqa: E402
from hub.services.watch import ChangeWatcher  # noqa: E402

COMFY = SCRATCH / "ComfyUI"
seen: list[bool] = []


def main() -> int:
    qapp = QCoreApplication(sys.argv)
    backend = hub_app.Backend()
    # The machine running this test has a real, running comfyui.service, and
    # "running" correctly outranks every on-disk check — which would mask the
    # very logic under test. Point this instance at a unit that does not exist so
    # the marker is what decides, and leave the user's actual service alone.
    backend.comfyui.unit = "lah-presence-probe"
    watcher = ChangeWatcher(backend._services)
    watcher.changed.connect(backend.request_refresh)

    def on_state(payload: str) -> None:
        present = json.loads(payload)["services"]["comfyui"]["present"]
        seen.append(present)
        print(f"    -> app state says comfyui present={present}")

    backend.state_changed.connect(on_state)
    backend.notify.connect(lambda m: print(f"    -> toast: {m}"))

    steps = [
        ("baseline (folder absent)", lambda: None),
        ("install: create ComfyUI/main.py", lambda: (
            COMFY.mkdir(parents=True, exist_ok=True),
            (COMFY / "main.py").write_text("# probe\n"))),
        ("uninstall: delete the folder", lambda: shutil.rmtree(COMFY, ignore_errors=True)),
    ]
    marks: list[tuple[str, list[bool]]] = []
    idx = {"i": 0}

    def run_next():
        i = idx["i"]
        if i > 0:
            marks.append((steps[i - 1][0], list(seen)))
        seen.clear()
        if i >= len(steps):
            return finish()
        label, fn = steps[i]
        idx["i"] += 1
        print(f"\n[{i + 1}] {label}")
        fn()
        if i == 0:
            backend.request_refresh()
        QTimer.singleShot(2500, run_next)

    def finish():
        print("\n" + "-" * 62)
        ok = True
        expected = [False, True, False]
        for (label, got), want in zip(marks, expected):
            final = got[-1] if got else None
            good = final is want
            ok &= good
            print(f"{'PASS' if good else 'FAIL'}  {label:<34} present={final} (want {want})")
        print("-" * 62)
        shutil.rmtree(SCRATCH, ignore_errors=True)
        qapp.exit(0 if ok else 1)

    QTimer.singleShot(400, run_next)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())

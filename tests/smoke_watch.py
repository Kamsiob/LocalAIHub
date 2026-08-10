#!/usr/bin/env python3
"""Prove the install/uninstall watcher fires on real events, not on a timer.

Runs three live scenarios against the actual machine and reports which mechanism
caught each one:

  1. a unit file appearing and disappearing in ~/.config/systemd/user
  2. a daemon-reload (the systemd D-Bus path)
  3. a ComfyUI-shaped folder being created and deleted

Nothing here touches the user's real services: the unit file is a dummy name and
the folder is a temporary COMFYUI_HOME. Run it with the venv python from the
repo root.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402

TMP_COMFY = Path(tempfile.mkdtemp(prefix="lah-watch-")) / "ComfyUI"
os.environ["COMFYUI_HOME"] = str(TMP_COMFY)

from hub.services import ComfyUIService, OllamaService, OpenWebUIService  # noqa: E402
from hub.services.watch import ChangeWatcher  # noqa: E402

UNIT_DIR = Path.home() / ".config" / "systemd" / "user"
DUMMY_UNIT = UNIT_DIR / "lah-watch-probe.service"

hits: list[str] = []


def main() -> int:
    app = QCoreApplication(sys.argv)
    services = {"ollama": OllamaService(), "openwebui": OpenWebUIService(),
                "comfyui": ComfyUIService()}
    w = ChangeWatcher(services)
    w.changed.connect(lambda reason: hits.append(reason))

    mech = w.mechanisms()
    print(f"systemd D-Bus armed : {mech['systemd_dbus']}")
    print(f"filesystem armed    : {mech['filesystem']} ({len(mech['watched_paths'])} dirs)")
    for p in mech["watched_paths"]:
        print(f"    {p}")
    print()

    steps = []

    def step(label, fn):
        steps.append((label, fn))

    def write_unit():
        UNIT_DIR.mkdir(parents=True, exist_ok=True)
        DUMMY_UNIT.write_text("[Unit]\nDescription=watcher probe\n[Service]\nExecStart=/bin/true\n")

    def reload_systemd():
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, timeout=20)

    def remove_unit():
        DUMMY_UNIT.unlink(missing_ok=True)

    def make_comfy():
        TMP_COMFY.mkdir(parents=True, exist_ok=True)
        (TMP_COMFY / "main.py").write_text("# probe\n")

    def drop_comfy():
        shutil.rmtree(TMP_COMFY, ignore_errors=True)

    step("write a unit file", write_unit)
    step("daemon-reload", reload_systemd)
    step("remove the unit file", remove_unit)
    step("create a ComfyUI folder with main.py", make_comfy)
    step("delete the ComfyUI folder", drop_comfy)

    results: list[tuple[str, list[str]]] = []
    idx = {"i": 0}

    def run_next():
        i = idx["i"]
        if i > 0:
            label = steps[i - 1][0]
            results.append((label, list(hits)))
            hits.clear()
        if i >= len(steps):
            finish()
            return
        label, fn = steps[i]
        idx["i"] += 1
        hits.clear()
        fn()
        # Comfortably past the watcher's 700 ms debounce.
        QTimer.singleShot(1600, run_next)

    def finish():
        print("event                                     caught  by")
        print("-" * 70)
        ok = 0
        for label, got in results:
            caught = "yes" if got else "NO"
            if got:
                ok += 1
            by = got[0] if got else "-"
            print(f"{label:<41} {caught:<7} {by}")
        print("-" * 70)
        print(f"{ok}/{len(results)} events caught")
        comfy = ComfyUIService()
        print(f"\nComfyUI presence after delete: "
              f"is_installed(unit_loaded=True, active=False) = "
              f"{comfy.is_installed(True, False)}")
        shutil.rmtree(TMP_COMFY.parent, ignore_errors=True)
        DUMMY_UNIT.unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, timeout=20)
        app.exit(0 if ok == len(results) else 1)

    QTimer.singleShot(300, run_next)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

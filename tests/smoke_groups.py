#!/usr/bin/env python3
"""The two-group layout's edge cases, driven through the real front-end.

Checks the states that are easy to get wrong and hard to hit by hand: a homelab
big enough to collapse, a machine with no non-AI services at all, a build that
cannot look for them, and the lopsided mixes in between.
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

THRESHOLD = 6


def svc(active=True, present=True):
    return {"active": active, "serving": active, "failed": False,
            "present": present, "result": ""}


def app_item(i):
    return {"key": f"container:svc{i}.service", "unit": f"svc{i}.service",
            "name": f"Service {i}", "kind": "", "container": f"svc{i}",
            "active": True, "serving": True, "port": 9000 + i,
            "bound_host": "127.0.0.1",
            "reachable": [{"kind": "loopback", "url": f"http://127.0.0.1:{9000+i}",
                           "meaning": "Only on this computer"}]}


AI_ALL = {"ollama": svc(), "openwebui": svc(), "comfyui": svc()}
AI_NONE = {"ollama": svc(False, False), "openwebui": svc(False, False),
           "comfyui": svc(False, False)}

CASES = [
    ("both, small homelab", AI_ALL, [app_item(i) for i in range(3)], True,
     {"appsHidden": False, "collapsed": False}),
    ("both, heavy homelab (over the threshold)", AI_ALL,
     [app_item(i) for i in range(THRESHOLD + 4)], True,
     {"appsHidden": False, "collapsed": True}),
    ("exactly at the threshold stays open", AI_ALL,
     [app_item(i) for i in range(THRESHOLD)], True,
     {"appsHidden": False, "collapsed": False}),
    ("only AI, nothing else self-hosted", AI_ALL, [], True,
     {"appsHidden": True}),
    ("only non-AI services", AI_NONE, [app_item(i) for i in range(2)], True,
     {"appsHidden": False, "collapsed": False}),
    ("build can't look (sandboxed)", AI_ALL, [], False,
     {"appsHidden": False, "hasNote": True}),
]

failures: list[str] = []


def main() -> int:
    qapp = QApplication(sys.argv)
    win = appmod.MainWindow()
    win.resize(768, 900)
    win.show()

    results: list[tuple[str, dict, dict]] = []
    idx = {"i": 0}

    def run_next(_prev=None):
        i = idx["i"]
        if i >= len(CASES):
            return finish()
        label, services, items, supported, want = CASES[i]
        idx["i"] += 1
        payload = {
            "services": services, "models": [], "comfyui_models": [], "layers": [],
            "addresses": {"loopback": {"host": "127.0.0.1",
                                       "meaning": "Only on this computer"}},
            "apps": {"supported": supported, "items": items,
                     "limit": None if supported else {
                         "what": "Your other self-hosted services",
                         "why": "the sandbox has no route to the container runtime."}},
        }
        win.view.page().runJavaScript(
            # appsCollapsed is sticky once the user has toggled it, so each case
            # resets it to "decide from the count" the way a fresh launch would.
            "window.__resetApps && window.__resetApps();"
            f"window.__applyState({json.dumps(payload)});",
            lambda _r: QTimer.singleShot(350, lambda: measure(label, want)))

    def measure(label, want):
        win.view.page().runJavaScript(
            "JSON.stringify({"
            "appsHidden: document.getElementById('groupApps').hidden,"
            "collapsed: document.getElementById('groupApps').classList.contains('collapsed'),"
            "cards: document.querySelectorAll('#apps .card').length,"
            "hasNote: !document.getElementById('appsNote').hidden})",
            lambda r: record(label, want, r))

    def record(label, want, raw):
        got = json.loads(raw)
        results.append((label, want, got))
        QTimer.singleShot(120, run_next)

    def finish():
        print(f"{'case':<44} {'result'}")
        print("-" * 78)
        for label, want, got in results:
            bad = [k for k, v in want.items() if got.get(k) != v]
            if bad:
                failures.append(f"{label}: wanted {want}, got {got}")
            detail = ", ".join(f"{k}={got.get(k)}" for k in want)
            print(f"{'PASS' if not bad else 'FAIL':<5}{label:<39} {detail}")
        print("-" * 78)
        print(f"collapse threshold: more than {THRESHOLD} services")
        if failures:
            for f in failures:
                print("FAIL ", f)
        qapp.exit(1 if failures else 0)

    QTimer.singleShot(7000, run_next)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Prove the version check is genuinely user-triggered.

The claim in the About panel is absolute: with the button never pressed, the app
makes no version-check request for its entire lifetime. That is only worth
saying if it is tested, so this runs the real app for a while — full launch,
About panel opened, periodic refresh and the install watcher both live — with
every outbound HTTP call to github.com recorded, and asserts the count is zero.

Then it presses the button and asserts exactly one call happens.
"""
from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --no-sandbox"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

github_calls: list[str] = []
_real_urlopen = urllib.request.urlopen


def _spy(req, *a, **kw):
    url = req.full_url if hasattr(req, "full_url") else str(req)
    if "github.com" in url or "githubusercontent" in url:
        github_calls.append(url)
    return _real_urlopen(req, *a, **kw)


urllib.request.urlopen = _spy

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import app as appmod  # noqa: E402

RUN_MS = 14000       # long enough for several refresh ticks and watcher events
failures: list[str] = []


def main() -> int:
    application = QApplication(sys.argv)
    win = appmod.MainWindow()
    win.resize(760, 780)
    win.show()

    def open_about():
        # Opening the panel must not check either — it only reads local metadata.
        win.view.page().runJavaScript(
            "(function(){var b=document.getElementById('aboutBtn');"
            "if(b) b.click(); return !!document.getElementById('aboutScreen');})()",
            lambda r: print(f"[{RUN_MS // 1000 - 6}s] About panel opened: {r}"))

    def check_idle():
        n = len(github_calls)
        print(f"\nidle phase: app ran {RUN_MS / 1000:.0f}s, About panel opened, "
              f"refresh timer + watcher live")
        print(f"  github requests made: {n}")
        if n:
            failures.append(f"{n} unsolicited github request(s): {github_calls}")
        else:
            print("  PASS  nothing was checked without a press")
        press()

    def press():
        print("\npressing the button…")
        win.view.page().runJavaScript(
            "(function(){var b=document.getElementById('verBtn');"
            "if(!b) return 'no button'; b.click(); return 'clicked';})()",
            lambda r: print(f"  {r}"))
        QTimer.singleShot(9000, after_press)

    def after_press():
        n = len(github_calls)
        print(f"  github requests after the press: {n}")
        if n != 1:
            failures.append(f"expected exactly 1 request after the press, got {n}")
        else:
            print(f"  PASS  exactly one request: {github_calls[0]}")

        win.view.page().runJavaScript(
            "(document.getElementById('verResult')||{}).innerText || '(empty)'",
            lambda r: finish(r))

    def finish(result_text):
        print(f"\nresult shown in the panel:\n  {str(result_text).strip()}")
        print("\n" + "-" * 62)
        if failures:
            for f in failures:
                print("FAIL ", f)
        else:
            print("PASS  version check is user-triggered only")
        print("-" * 62)
        application.exit(1 if failures else 0)

    QTimer.singleShot(RUN_MS - 6000, open_about)
    QTimer.singleShot(RUN_MS, check_idle)
    return application.exec()


if __name__ == "__main__":
    sys.exit(main())

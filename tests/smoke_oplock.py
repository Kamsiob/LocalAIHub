#!/usr/bin/env python3
"""The operation lock is the foundation every safety guarantee rests on.

Two removals must never interleave, and the 5 second background scan must not
read state that an operation in flight is about to change. Both properties come
from one lock, so this proves that one lock actually behaves.

Nothing here touches a real service. It drives Backend's own primitives.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QCoreApplication  # noqa: E402

import app as appmod  # noqa: E402

failures: list[str] = []


def check(label: str, got, want) -> None:
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<52} got={got!r} want={want!r}")
    if not ok:
        failures.append(label)


def main() -> int:
    QCoreApplication(sys.argv)
    b = appmod.Backend()

    notes: list[str] = []
    b.notify.connect(notes.append)

    started = threading.Event()
    release = threading.Event()

    def slow_op() -> None:
        started.set()
        release.wait(5)

    print("\n1. a second operation is refused while the first holds the lock")
    check("first operation starts", b._run_exclusive("a test operation", slow_op), True)
    started.wait(2)
    check("second operation refused", b._run_exclusive("another one", lambda: None), False)
    check("user was told, not silently ignored",
          any("Busy with a test operation" in n for n in notes), True)

    print("\n2. the background scan skips while an operation holds the lock")
    # Counted at the source rather than observed through a Qt signal: a queued
    # signal needs a running event loop, so "no signal arrived" would pass just
    # as readily when the mechanism is broken as when it works.
    collects: list[int] = []
    real_collect = b._collect
    b._collect = lambda: (collects.append(1), {"services": {}})[1]

    b._refresh_async()
    time.sleep(1.2)
    check("_collect not called during the operation", len(collects), 0)

    print("\n3. the lock is released and normal service resumes")
    release.set()
    time.sleep(0.6)
    check("lock free after the operation", b._op_lock.acquire(blocking=False), True)
    b._op_lock.release()
    check("operation name cleared", b._op_name, "")

    b._refresh_async()
    deadline = time.time() + 10
    while not collects and time.time() < deadline:
        time.sleep(0.1)
    check("_collect runs once the lock is free", len(collects), 1)
    b._collect = real_collect

    print("\n4. the lock is released even when an operation raises")
    def boom() -> None:
        # The traceback printed above this line is expected: it proves the
        # failure really propagated rather than being swallowed.
        raise RuntimeError("deliberate")
    b._run_exclusive("a failing operation", boom)
    time.sleep(0.6)
    check("lock free after an exception", b._op_lock.acquire(blocking=False), True)
    b._op_lock.release()

    print("\n" + "-" * 74)
    print("FAILURES: " + ", ".join(failures) if failures else "all operation-lock checks passed")
    print("-" * 74)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

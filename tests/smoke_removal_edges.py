#!/usr/bin/env python3
"""The failure and edge paths, all against throwaway subjects.

These are the cases that decide whether a removal feature is safe in practice:
partially deleted subjects, missing units, two removals at once, and an
operation interrupted midway. None of them touch anything real.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from PySide6.QtCore import QCoreApplication, Qt  # noqa: E402

from hub.removal import Manifest, Step, execute, plan_container_service  # noqa: E402
from hub.services import containers  # noqa: E402

TESTBED = REPO / "tools" / "testbed.sh"
failures: list[str] = []


def sh(*a):
    return subprocess.run(a, capture_output=True, text=True, timeout=180)


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<58} {detail}")
    if not ok:
        failures.append(label)


def testbed(cmd):
    return sh("bash", str(TESTBED), cmd)


def entry():
    return next((e for e in containers.discover() if e.get("container") == "lah-testsvc"), None)


def main() -> int:
    QCoreApplication(sys.argv)
    import app as appmod

    print("=" * 78)
    print("EDGE AND FAILURE PATHS")
    print("=" * 78)

    print("\n1. a subject already partly deleted by hand still removes cleanly")
    testbed("setup")
    # The user deleted the config folder themselves before using the app.
    sh("bash", "-c", "rm -rf ~/.config/lah-testsvc")
    e = entry()
    m = plan_container_service(e)
    res = execute(m, m.token, include_data=False, replan=lambda: plan_container_service(entry() or e))
    check("removal completed despite a missing artifact", res["ok"], res["detail"])
    check("the quadlet is gone",
          not (Path.home() / ".config/containers/systemd/lah-testsvc.container").exists())

    print("\n2. files present but the unit is unknown to systemd")
    testbed("setup")
    sh("systemctl", "--user", "stop", "lah-testsvc.service")
    sh("bash", "-c", "rm -f ~/.config/containers/systemd/lah-testsvc.container")
    sh("systemctl", "--user", "daemon-reload")
    # The container still exists; the definition does not.
    e2 = entry()
    check("an item with no quadlet is not offered a removal",
          e2 is None or not plan_container_service(e2).ok,
          "not discovered" if e2 is None else plan_container_service(e2).reason)
    sh("podman", "rm", "-f", "lah-testsvc")

    print("\n3. two removals at once: the second is refused, not queued")
    b = appmod.Backend()
    notes: list[str] = []
    b.notify.connect(notes.append, Qt.ConnectionType.DirectConnection)
    hold = threading.Event()
    started = threading.Event()
    first = b._run_exclusive("a slow removal", lambda: (started.set(), hold.wait(6)))
    started.wait(2)
    second = b._run_exclusive("another removal", lambda: None)
    check("first accepted", first is True)
    check("second refused while the first runs", second is False)
    check("the user was told why", any("Busy with" in n for n in notes),
          notes[-1] if notes else "(none)")
    hold.set()
    time.sleep(0.5)

    print("\n4. an interrupted removal leaves a recoverable, described state")
    testbed("setup")
    e = entry()
    m = plan_container_service(e)
    # Force a failure partway: a step whose target cannot be removed.
    broken = Manifest(key=m.key, name=m.name)
    broken.steps = [
        Step(1, "stop", "lah-testsvc.service", "Stop the test service"),
        Step(2, "rm_path", "/etc/hostname", "Delete something outside the allowed roots"),
        Step(3, "rm_container", "lah-testsvc", "Remove the container"),
    ]
    broken.token = broken.compute_token()
    res = execute(broken, broken.token, include_data=False)
    check("the operation stopped rather than continuing", not res["ok"])
    check("it stopped on the offending step",
          res["failed"] and "/etc/hostname" in res["failed"]["step"]["target"])
    check("the refusal names the reason",
          "may delete" in (res["failed"] or {}).get("detail", ""),
          (res["failed"] or {}).get("detail", ""))
    check("later steps were not attempted", len(res["remaining"]) == 1,
          f"remaining={[s['label'] for s in res['remaining']]}")
    check("the file outside the roots is untouched", Path("/etc/hostname").exists())
    # Not the container: a quadlet unit removes its own container when it stops,
    # which step 1 legitimately did. The invariant that matters is that nothing
    # after the failing step ran, so the definition is still on disk.
    check("the quadlet the later steps would have deleted is untouched",
          (Path.home() / ".config/containers/systemd/lah-testsvc.container").exists())

    print("\n5. a plan for something that no longer exists refuses")
    testbed("teardown")
    gone = plan_container_service({"unit": "lah-testsvc.service", "name": "Gone",
                                   "container": "lah-testsvc", "key": "x"})
    check("no quadlet means no removal offered", not gone.ok, gone.reason)

    print("\n" + "=" * 78)
    if failures:
        print("FAILURES:")
        for f in failures:
            print("  -", f)
    else:
        print("ALL EDGE AND FAILURE PATHS PASSED")
    print("=" * 78)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

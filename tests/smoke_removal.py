#!/usr/bin/env python3
"""Removal, exercised only against throwaway subjects.

Nothing the user actually runs is ever a target here. Every subject is named
lah-test* and is created and destroyed by this file.

The centerpiece is the data-volume survival test. A software removal must leave
a named volume and its contents untouched, and that is proven by reading the
canary file back byte for byte afterwards, not by observing that a volume of the
same name still appears in a list.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from hub.removal import (execute, plan_container_service,  # noqa: E402
                         validate_path, is_own_path)
from hub.services import containers  # noqa: E402

TESTBED = REPO / "tools" / "testbed.sh"
CANARY = "precious-user-data-do-not-delete"
failures: list[str] = []


def sh(*args, **kw):
    return subprocess.run(args, capture_output=True, text=True, timeout=180, **kw)


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<58} {detail}")
    if not ok:
        failures.append(label)


def testbed(cmd):
    return sh("bash", str(TESTBED), cmd)


def volume_exists(name):
    return sh("podman", "volume", "exists", name).returncode == 0


def read_canary(volume="lah-testdata"):
    cp = sh("podman", "run", "--rm", "-v", f"{volume}:/d",
            "docker.io/library/alpine:latest", "cat", "/d/canary.txt")
    return cp.stdout.strip() if cp.returncode == 0 else None


def entry_for(container):
    for e in containers.discover():
        if e.get("container") == container:
            return e
    return None


def software_artifacts_present():
    home = Path.home()
    return {
        "quadlet": (home / ".config/containers/systemd/lah-testsvc.container").exists(),
        "config": (home / ".config/lah-testsvc").exists(),
        "cache": (home / ".cache/lah-testsvc").exists(),
        "desktop": (home / ".local/share/applications/lah-testsvc.desktop").exists(),
        "icon": (home / ".local/share/icons/hicolor/scalable/apps/lah-testsvc.svg").exists(),
        "container": sh("podman", "container", "exists", "lah-testsvc").returncode == 0,
        "unit": sh("systemctl", "--user", "is-active", "lah-testsvc.service").stdout.strip(),
    }


def main() -> int:
    print("=" * 80)
    print("REMOVAL TESTS, throwaway subjects only")
    print("=" * 80)

    # ---------------------------------------------------------------- 1
    print("\n1. THE DATA VOLUME SURVIVES A SOFTWARE REMOVAL")
    testbed("setup")
    before = read_canary()
    check("canary readable before removal", before == CANARY, repr(before))

    e = entry_for("lah-testsvc")
    if not e:
        check("test subject discovered", False, "not found by containers.discover()")
        testbed("teardown")
        return 1
    m = plan_container_service(e)
    check("plan is offered", m.ok, m.reason)
    check("the volume is a data step, not a software step",
          any(s.target == "lah-testdata" for s in m.data_steps())
          and not any(s.target == "lah-testdata" for s in m.software_steps()))

    res = execute(m, m.token, include_data=False, replan=lambda: plan_container_service(entry_for("lah-testsvc") or e))
    check("software removal completed", res["ok"], res["detail"])

    after = read_canary()
    print(f"\n      canary before : {before!r}")
    print(f"      canary after  : {after!r}")
    check("VOLUME STILL EXISTS", volume_exists("lah-testdata"))
    check("CANARY CONTENTS UNCHANGED", after == CANARY, repr(after))

    art = software_artifacts_present()
    print(f"      software artifacts after: {json.dumps(art)}")
    for name in ("quadlet", "config", "cache", "desktop", "icon", "container"):
        check(f"software gone: {name}", art[name] is False)
    check("systemd no longer reports the unit active", art["unit"] != "active", art["unit"])
    check("the kept list explains the volume was left",
          any("data was not included" in k["why"] for k in res.get("kept", [])))

    # ---------------------------------------------------------------- 2
    print("\n2. THE DATA VOLUME IS REMOVED ONLY WHEN EXPLICITLY INCLUDED")
    testbed("setup")
    e = entry_for("lah-testsvc")
    m = plan_container_service(e)
    res = execute(m, m.token, include_data=True, replan=lambda: plan_container_service(entry_for("lah-testsvc") or e))
    check("removal with data completed", res["ok"], res["detail"])
    check("volume is gone when it was asked for", not volume_exists("lah-testdata"))

    # ---------------------------------------------------------------- 3
    print("\n3. A SHARED VOLUME IS NEVER REMOVED AS PART OF REMOVING ONE USER")
    testbed("setup")
    sh("podman", "create", "--name", "lah-testsvc2", "-v", "lah-testdata:/data",
       "docker.io/library/alpine:latest", "true")
    e = entry_for("lah-testsvc")
    m = plan_container_service(e)
    shared_kept = [k for k in m.kept if "lah-testdata" in k["what"]]
    check("shared volume moved out of the data steps",
          not any(s.target == "lah-testdata" for s in m.data_steps()))
    check("shared volume reported as kept, naming the other user",
          bool(shared_kept) and "lah-testsvc2" in shared_kept[0]["why"],
          shared_kept[0]["why"] if shared_kept else "(not reported)")
    res = execute(m, m.token, include_data=True, replan=lambda: plan_container_service(entry_for("lah-testsvc") or e))
    check("volume survived even with data included, because it is shared",
          volume_exists("lah-testdata"))
    check("canary intact", read_canary() == CANARY)
    sh("podman", "rm", "-f", "lah-testsvc2")

    # ---------------------------------------------------------------- 4
    print("\n4. THE SHARED IMAGE IS NEVER REMOVED")
    check("image still present after both removals",
          sh("podman", "image", "exists", "docker.io/library/alpine:latest").returncode == 0)

    # ---------------------------------------------------------------- 5
    print("\n5. A CHANGED SYSTEM REFUSES A STALE CONFIRMATION")
    testbed("setup")
    e = entry_for("lah-testsvc")
    m = plan_container_service(e)
    stale_token = m.token
    (Path.home() / ".config/lah-testsvc-extra").mkdir(exist_ok=True)
    sh("bash", "-c", "rm -rf ~/.cache/lah-testsvc")      # the system moves on
    res = execute(m, stale_token, include_data=False,
                  replan=lambda: plan_container_service(entry_for("lah-testsvc") or e))
    check("stale confirmation refused, nothing removed",
          not res["ok"] and not res["done"], res["detail"])
    check("the quadlet is still there after the refusal",
          (Path.home() / ".config/containers/systemd/lah-testsvc.container").exists())
    (Path.home() / ".config/lah-testsvc-extra").rmdir()

    # ---------------------------------------------------------------- 6
    print("\n6. THE APP REFUSES TO REMOVE ITSELF")
    check("its own config directory is recognized",
          is_own_path(Path.home() / ".config/local-ai-hub"))
    check("its own launcher is recognized",
          is_own_path(Path.home() / ".local/share/applications/local-ai-hub.desktop"))

    testbed("teardown")
    print("\n" + "=" * 80)
    if failures:
        print("FAILURES:")
        for f in failures:
            print("  -", f)
    else:
        print("ALL REMOVAL TESTS PASSED")
    print("=" * 80)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Memory reporting and the guards around releasing it.

Nothing here loads or unloads a real model. The one destructive-adjacent path,
release, is exercised against a spy so the refusal logic can be proven without
touching anything the user is running.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QCoreApplication, Qt  # noqa: E402

from hub import memory  # noqa: E402
from hub.sizes import human  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<56} {detail}")
    if not ok:
        failures.append(label)


def main() -> int:
    QCoreApplication(sys.argv)
    import app as appmod

    print("\n1. hardware detection reports something true about this machine")
    hw = memory.hardware()
    check("kind is one of the four known answers",
          hw["kind"] in ("unified", "discrete", "cpu_only", "unknown"), hw["kind"])
    check("system memory total was read", bool(hw["ram_total"]), human(hw["ram_total"]))
    check("available memory is not greater than total",
          not hw["ram_available"] or hw["ram_available"] <= hw["ram_total"],
          f"{human(hw['ram_available'])} of {human(hw['ram_total'])}")
    if hw["kind"] == "unified":
        check("unified memory is labeled as shared, not added to the total",
              "part of the total" in hw["note"])
        check("graphics memory is smaller than system memory, as a carveout must be",
              bool(hw["vram_total"]) and hw["vram_total"] < hw["ram_total"],
              f"{human(hw['vram_total'])} carved from {human(hw['ram_total'])}")

    print("\n2. figures that cannot be determined are omitted, never zeroed")
    check("no figure is reported as a bare zero",
          all(v is None or v > 0 for v in
              (hw["ram_total"], hw["ram_available"], hw["vram_total"])))

    print("\n3. release refuses when the model is not resident")
    b = appmod.Backend()
    calls: list[str] = []
    real_release = memory.release_ollama_model
    real_loaded = memory.loaded_models
    memory.release_ollama_model = lambda name, **kw: calls.append(name) or {"detail": "x"}
    memory.loaded_models = lambda: []          # nothing is in memory
    notes: list[str] = []
    # Direct, because notify is emitted from the operation thread and this
    # test runs no event loop to deliver a queued connection.
    b.notify.connect(notes.append, Qt.ConnectionType.DirectConnection)

    b.release_memory("some-model")
    import time
    time.sleep(1.2)
    check("Ollama was never asked to unload anything", calls == [], f"calls={calls}")
    check("the user was told why", any("not in memory" in n for n in notes),
          notes[-1] if notes else "(no message)")

    print("\n4. release acts only on the model that was named")
    calls.clear(); notes.clear()
    memory.loaded_models = lambda: [{"name": "picked", "size": 1, "size_vram": 1,
                                     "on_gpu": True, "expires_at": ""}]
    b.release_memory("picked")
    time.sleep(1.2)
    check("exactly one model was acted on", calls == ["picked"], f"calls={calls}")

    memory.release_ollama_model = real_release
    memory.loaded_models = real_loaded

    print("\n" + "-" * 78)
    print("FAILURES: " + ", ".join(failures) if failures else "all memory checks passed")
    print("-" * 78)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

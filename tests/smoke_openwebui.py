"""Standalone smoke test for hub.services.openwebui against the real container.

Stops then restarts Open WebUI and restores it to serving (its original state).
"""
import sys
import time

sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from hub.services.openwebui import OpenWebUIService  # noqa: E402

o = OpenWebUIService()


def wait_serving(target: bool, timeout: float = 60) -> bool:
    for _ in range(int(timeout)):
        if o.is_serving() is target:
            return True
        time.sleep(1)
    return o.is_serving() is target


print("=== status() ===")
print(o.status().to_dict())

print("\n=== stop() ===")
print("  stop ok:", o.stop())
print("  reached not-serving:", wait_serving(False))
print("  is_active:", o.is_active(), "| serving:", o.is_serving())

print("\n=== start() — restore to running ===")
print("  start ok:", o.start())
print("  reached serving:", wait_serving(True))
s = o.status().to_dict()
print("  final status:", s)
assert s["active"] and s["serving"], "Open WebUI did not return to serving!"
print("\nOPEN WEBUI CHECKS DONE — restored to serving")

"""Standalone smoke test for hub.services.comfyui against the real service.

Starts ComfyUI, confirms it serves on 8188, stops it, confirms it's down.
Leaves it stopped (the on-demand baseline).
"""
import sys
import time

sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from hub.services.comfyui import ComfyUIService  # noqa: E402

c = ComfyUIService()


def wait_serving(target: bool, timeout: float = 90) -> bool:
    for _ in range(int(timeout)):
        if c.is_serving() is target:
            return True
        time.sleep(1)
    return c.is_serving() is target


print("=== status() before ===")
print(o := c.status().to_dict())

print("\n=== start() ===")
print("  start ok:", c.start())
print("  reached serving:", wait_serving(True))
print("  status:", c.status().to_dict())

print("\n=== stop() — back to on-demand baseline ===")
print("  stop ok:", c.stop())
print("  reached not-serving:", wait_serving(False))
s = c.status().to_dict()
print("  final status:", s)
assert not s["active"] and not s["serving"], "ComfyUI did not stop cleanly!"
print("\nCOMFYUI CHECKS DONE — left stopped")

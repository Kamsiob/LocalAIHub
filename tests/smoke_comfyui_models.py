"""Standalone smoke test for ComfyUI generic model detection.

Lists whatever is actually installed in the standard folders, with real sizes,
and reports the activity (generating) state. Asserts nothing about specific
filenames — it just prints what the scan finds on this machine.
"""
import sys

sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from hub.services.comfyui import ComfyUIService, MODEL_CATEGORIES  # noqa: E402

c = ComfyUIService()
print("ComfyUI root:", c.root)
print("models dir exists:", c.models_dir.is_dir())

models = c.list_models()
print(f"\nfound {len(models)} model files across standard folders:")
by_cat: dict = {}
for m in models:
    by_cat.setdefault(m["category_label"], []).append(m)
for _, label in MODEL_CATEGORIES:
    items = by_cat.get(label, [])
    print(f"\n  {label} ({len(items)}):")
    for m in items:
        print(f"    {m['size_human']:>9}  [{m['format']:>11}]  {m['name']}")

print("\nis_generating():", c.is_generating(), "(service running:", c.is_active(), ")")
print("\nSCAN IS GENERIC — no filenames assumed; came entirely from the filesystem.")

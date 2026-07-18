"""Standalone smoke test for hub.services.ollama against the real Ollama service.

Safe by design: only touches a tiny throwaway model (all-minilm ~45MB) for
pull/remove, and only loads llama3.2:1b (non-critical) for memory-detection.
The user's real models (qwen3-coder:30b, gemma4:31b, gemma4:26b,
nomic-embed-text) are never pulled or removed.
"""
import sys
import urllib.request
import json

sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from hub.services.ollama import OllamaService  # noqa: E402

THROWAWAY = "all-minilm"      # tiny (~45MB) — safe to pull + delete
MEMTEST = "llama3.2:1b"       # non-critical — safe to load into memory
PROTECTED = {"qwen3-coder:30b", "gemma4:31b", "gemma4:26b", "nomic-embed-text:latest"}

o = OllamaService()


def hr(t):
    print(f"\n=== {t} ===")


hr("status()")
print(o.status().to_dict())

hr("list_models() — installed with size on disk")
for m in o.list_models():
    print(f"  {m.name:28} {m.size_human:>9}  loaded={m.loaded}")

hr("loaded_model() before loading anything")
print("  loaded:", o.loaded_model())

hr(f"pull_model({THROWAWAY!r}) — fresh pull with progress")
seen = set()
def cb(status, frac):
    key = f"{status} {int(frac*100)//25*25}%"
    if key not in seen:
        seen.add(key)
        print(f"  [{int(frac*100):3d}%] {status}")
o.pull_model(THROWAWAY, progress_cb=cb)
print("  -> pulled")

hr(f"pull_model({THROWAWAY!r}) AGAIN — update mechanism (already current)")
o.pull_model(THROWAWAY, progress_cb=lambda s, f: print(f"  {s}") if s in ("pulling manifest", "success") else None)
print("  -> update path ok")

hr("list_models() now includes throwaway")
names = [m.name for m in o.list_models()]
print("  present:", THROWAWAY in " ".join(names) or any(THROWAWAY in n for n in names))

hr(f"loaded detection — load {MEMTEST} into memory")
req = urllib.request.Request(
    "http://127.0.0.1:11434/api/generate",
    data=json.dumps({"model": MEMTEST, "prompt": "hi", "stream": False, "keep_alive": "30s"}).encode(),
    headers={"Content-Type": "application/json"}, method="POST",
)
urllib.request.urlopen(req, timeout=120).read()
print("  loaded_model() now:", o.loaded_model())
for m in o.list_models():
    if m.loaded:
        print(f"  IN MEMORY: {m.name}  vram={m.to_dict()['vram_human']}")

hr(f"remove_model({THROWAWAY!r})")
print("  removed:", o.remove_model(THROWAWAY))
after = [m.name for m in o.list_models()]
print("  throwaway gone:", not any(THROWAWAY in n for n in after))

hr("protected models still present")
present = set(after)
print("  all protected intact:", PROTECTED.issubset(present), "| have:", sorted(present))

hr("unload memtest (keep_alive=0)")
req = urllib.request.Request(
    "http://127.0.0.1:11434/api/generate",
    data=json.dumps({"model": MEMTEST, "prompt": "", "stream": False, "keep_alive": 0}).encode(),
    headers={"Content-Type": "application/json"}, method="POST",
)
urllib.request.urlopen(req, timeout=30).read()
print("  loaded_model() after unload:", o.loaded_model())
print("\nALL OLLAMA CHECKS DONE")

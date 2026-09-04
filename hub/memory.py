"""What is holding memory right now, and how to let it go.

A control panel, not a system monitor: a few honest figures, no graphs, no
history. Every figure here is either measured or omitted. None is estimated.

The hardware question has to be answered at runtime rather than assumed. On the
machine this was built against, the GPU's memory is carved out of the same DRAM
as system memory, so VRAM and RAM are not separate pools and adding them would
overstate the machine by the size of the carveout. On a discrete card they are
separate and both are real. The detector below tells those apart, and reports
"unknown" rather than guessing when it can tell neither.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

DRM = Path("/sys/class/drm")
OLLAMA_HOST = "http://127.0.0.1:11434"

# Shown next to the release control. The promise has to be checkable, so it
# describes the mechanism rather than reassuring about the outcome.
RELEASE_EXPLAINER = (
    "Asks Ollama to unload this model. Ollama finishes any request already in "
    "progress before it unloads, so nothing in flight is cut off. The service "
    "keeps running and the model stays installed on disk."
)


def _read_int(path: Path):
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def _meminfo() -> dict:
    out = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            parts = rest.split()
            if parts:
                try:
                    out[key] = int(parts[0]) * 1024
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def _gpu_card():
    """The first amdgpu-style card exposing memory information, or None."""
    try:
        cards = sorted(DRM.glob("card*/device"))
    except OSError:
        return None
    for dev in cards:
        if (dev / "mem_info_vram_total").exists():
            return dev
    return None


def hardware() -> dict:
    """RAM, and VRAM when the machine actually has a separate pool of it.

    `kind` is one of unified, discrete, cpu_only or unknown. On unified the
    VRAM figure is reported but flagged, because it is carved out of the RAM
    total rather than being additional to it, and a reader who adds them gets a
    machine that does not exist.
    """
    mem = _meminfo()
    ram_total = mem.get("MemTotal")
    ram_available = mem.get("MemAvailable")

    card = _gpu_card()
    if card is None:
        return {"kind": "cpu_only" if ram_total else "unknown",
                "ram_total": ram_total, "ram_available": ram_available,
                "vram_total": None, "vram_used": None,
                "note": "No GPU reporting memory was found, so figures are system memory only."}

    vram_total = _read_int(card / "mem_info_vram_total")
    vram_used = _read_int(card / "mem_info_vram_used")

    # A BIOS UMA carveout directory exists only on an APU that steals its video
    # memory from system RAM. It is the definitive signal, needs no dependency,
    # and is world readable. This module only ever reads it.
    unified = (card / "uma" / "carveout").exists()
    if not unified:
        # Fallback for kernels without the uma directory: a card with dedicated
        # memory names its memory vendor and reports its own memory-controller
        # utilization. An APU has neither.
        has_vendor = (card / "mem_info_vram_vendor").exists()
        has_mem_busy = (card / "mem_busy_percent").exists()
        unified = not (has_vendor or has_mem_busy)

    if unified:
        note = ("This machine shares one pool of memory between the processor "
                "and the graphics chip. The graphics figure is part of the "
                "total, not extra.")
    else:
        note = ""
    return {"kind": "unified" if unified else "discrete",
            "ram_total": ram_total, "ram_available": ram_available,
            "vram_total": vram_total, "vram_used": vram_used,
            "note": note}


def _get(path: str, timeout: float = 4.0) -> dict:
    req = urllib.request.Request(f"{OLLAMA_HOST}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def loaded_models(strict: bool = False):
    """Models Ollama currently holds in memory, from its own /api/ps.

    With strict=True an unreadable answer returns None rather than an empty
    list. A caller deciding whether a model is safe to delete must be able to
    tell "nothing is loaded" apart from "Ollama did not answer"; the empty list
    told it the first when it meant the second.
    """
    try:
        data = _get("/api/ps")
    except Exception:
        return None if strict else []
    out = []
    for m in data.get("models", []):
        size = int(m.get("size") or 0)
        vram = int(m.get("size_vram") or 0)
        out.append({
            "name": m.get("name") or m.get("model") or "?",
            "size": size,
            "size_vram": vram,
            # On unified memory this ratio still says where the work runs, which
            # is the useful part; it does not imply a second pool of memory.
            "on_gpu": bool(size and vram >= size),
            "expires_at": m.get("expires_at") or "",
        })
    return out


def comfy_busy(comfyui) -> bool | None:
    """True, False, or None when it cannot be determined.

    None is not False. A caller that cannot tell whether work is running must
    refuse, not proceed.
    """
    try:
        return bool(comfyui.is_generating())
    except Exception:
        return None


def release_ollama_model(name: str, timeout: float = 20.0) -> dict:
    """Ask Ollama to unload one model. This is what `ollama stop` does.

    A generate request with keep_alive 0 tells the scheduler to drop the runner.
    The scheduler is reference counted, so it defers the unload until requests
    already in flight have finished. That is what makes this safe to offer even
    though Ollama publishes no way to see those requests: the unload cannot
    interrupt work, it can only be delayed by it.

    Because the app cannot see in-flight requests, it must never report that it
    checked. It reports what it asked for and what it observed afterwards.
    """
    body = json.dumps({"model": name, "keep_alive": 0}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate", data=body, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
    except Exception as exc:
        return {"ok": False, "released": False,
                "detail": f"Ollama did not accept the request ({exc})."}
    still = any(m["name"] == name for m in loaded_models())
    if still:
        return {"ok": True, "released": False,
                "detail": "Still in use. It will unload when the current request finishes."}
    return {"ok": True, "released": True, "detail": f"{name} released."}

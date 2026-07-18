"""ComfyUI service control + generic installed-model detection.

ComfyUI runs as the `comfyui` --user unit (GPU env from the validated launch
script, bounded restart). The web UI serves on 127.0.0.1:8188 and takes a few
seconds to warm up (torch/ROCm import), so `active` precedes `serving`.

Model detection is a plain filesystem scan of ComfyUI's standard model folders —
it lists whatever files are actually present (any name, any quantization, any of
the recognized extensions), never a fixed set of filenames. Unlike Ollama there
is no "loaded in memory" state: a model only occupies VRAM while a generation is
running, so activity is reported as "generating" (via the /queue API) only while
a job is in progress — it is not attached to individual models.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from .base import Service

COMFYUI_HOST = "http://127.0.0.1:8188"

# ComfyUI install root — override with COMFYUI_HOME; defaults to the standard ~/ComfyUI.
COMFYUI_ROOT = Path(os.environ.get("COMFYUI_HOME", Path.home() / "ComfyUI"))
MODELS_DIR = COMFYUI_ROOT / "models"

# Standard model folders to scan (label shown in the UI).
MODEL_CATEGORIES = [
    ("diffusion_models", "Diffusion models"),
    ("checkpoints", "Checkpoints"),
    ("text_encoders", "Text encoders"),
    ("vae", "VAE"),
    ("loras", "LoRAs"),
]

# Recognized model file extensions -> display label for the format.
MODEL_EXTS = {
    ".safetensors": "safetensors",
    ".gguf": "GGUF",
    ".ckpt": "ckpt",
    ".pt": "pt",
}


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit in ("B", "KB") else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class ComfyUIService(Service):
    def __init__(self) -> None:
        super().__init__(
            unit="comfyui",
            display_name="ComfyUI",
            health_url=f"{COMFYUI_HOST}/",
        )
        self.root = COMFYUI_ROOT
        self.models_dir = MODELS_DIR

    # --- generic installed-model scan ---------------------------------------
    def list_models(self) -> list[dict]:
        """Whatever model files are actually present in the standard folders.

        Returns one dict per file: {category, category_label, name, size_bytes,
        size_human, format}. Recurses into subfolders (people organize LoRAs,
        etc.). Never assumes specific filenames. Independent of the service
        running — models on disk are listed even when ComfyUI is stopped.
        """
        results: list[dict] = []
        for key, label in MODEL_CATEGORIES:
            base = self.models_dir / key
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*")):
                if not path.is_file():
                    continue
                ext = path.suffix.lower()
                if ext not in MODEL_EXTS:
                    continue
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                rel = path.relative_to(base).as_posix()
                results.append(
                    {
                        "category": key,
                        "category_label": label,
                        "name": rel,
                        "size_bytes": size,
                        "size_human": _human_size(size),
                        "format": MODEL_EXTS[ext],
                    }
                )
        return results

    # --- activity (only meaningful while a job runs) -------------------------
    def is_generating(self) -> bool:
        """True if ComfyUI is actively running a generation (from /queue)."""
        try:
            req = urllib.request.Request(f"{COMFYUI_HOST}/queue", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8") or "{}")
            return bool(data.get("queue_running"))
        except Exception:
            return False

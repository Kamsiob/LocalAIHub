"""ComfyUI service control.

ComfyUI runs as the `comfyui` --user unit created in Phase 1 (GPU env from the
validated launch script, bounded restart). Start/stop with no root; the web UI
serves on 127.0.0.1:8188 and takes a few seconds to warm up (torch/ROCm import),
so `active` precedes `serving`.
"""
from __future__ import annotations

from .base import Service

COMFYUI_HOST = "http://127.0.0.1:8188"


class ComfyUIService(Service):
    def __init__(self) -> None:
        super().__init__(
            unit="comfyui",
            display_name="ComfyUI",
            health_url=f"{COMFYUI_HOST}/",
        )

"""Ollama service control + model management via the local Ollama HTTP API.

Uses the REST API on 127.0.0.1:11434 (stdlib only, no `ollama` python dep):
  GET  /api/tags     -> installed models (name, size on disk, digest, modified)
  GET  /api/ps       -> models currently loaded into memory
  POST /api/pull     -> pull/update a model (streaming NDJSON progress)
  DELETE /api/delete -> remove a model
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from .base import Service

OLLAMA_HOST = "http://127.0.0.1:11434"


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit in ("B", "KB") else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@dataclass
class ModelInfo:
    name: str
    size_bytes: int
    size_human: str
    digest: str
    modified: str
    loaded: bool          # currently resident in memory (via /api/ps)
    vram_bytes: int = 0   # size in memory when loaded

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "size_bytes": self.size_bytes,
            "size_human": self.size_human,
            "digest": self.digest[:12],
            "modified": self.modified,
            "loaded": self.loaded,
            "vram_human": _human_size(self.vram_bytes) if self.vram_bytes else "",
        }


class OllamaService(Service):
    def __init__(self) -> None:
        super().__init__(
            unit="ollama",
            display_name="Ollama",
            health_url=f"{OLLAMA_HOST}/",
        )

    # --- HTTP helpers --------------------------------------------------------
    def _get(self, path: str, timeout: float = 10) -> dict:
        req = urllib.request.Request(f"{OLLAMA_HOST}{path}", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")

    def _loaded_map(self) -> dict:
        """digest -> vram size (bytes) for models currently in memory."""
        try:
            ps = self._get("/api/ps")
        except Exception:
            return {}
        loaded = {}
        for m in ps.get("models", []):
            loaded[m.get("digest", "")] = m.get("size_vram", m.get("size", 0))
        return loaded

    # --- model queries -------------------------------------------------------
    def list_models(self) -> list[ModelInfo]:
        """Installed models with size on disk, marking which are loaded in memory."""
        data = self._get("/api/tags")
        loaded = self._loaded_map()
        models: list[ModelInfo] = []
        for m in data.get("models", []):
            digest = m.get("digest", "")
            size = int(m.get("size", 0))
            vram = int(loaded.get(digest, 0))
            models.append(
                ModelInfo(
                    name=m.get("name", "?"),
                    size_bytes=size,
                    size_human=_human_size(size),
                    digest=digest,
                    modified=m.get("modified_at", ""),
                    loaded=digest in loaded,
                    vram_bytes=vram,
                )
            )
        models.sort(key=lambda x: x.name)
        return models

    def loaded_model(self) -> Optional[str]:
        """Name of the model currently loaded in memory, if any (first one)."""
        try:
            ps = self._get("/api/ps")
        except Exception:
            return None
        models = ps.get("models", [])
        return models[0].get("name") if models else None

    # --- model management ----------------------------------------------------
    def pull_model(
        self,
        name: str,
        progress_cb: Optional[Callable[[str, float], None]] = None,
        timeout: float = 3600,
    ) -> bool:
        """Pull/update a model. Streams NDJSON; progress_cb(status, fraction)."""
        body = json.dumps({"model": name}).encode("utf-8")
        req = urllib.request.Request(
            f"{OLLAMA_HOST}/api/pull",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                if progress_cb:
                    total = msg.get("total") or 0
                    completed = msg.get("completed") or 0
                    frac = (completed / total) if total else 0.0
                    progress_cb(msg.get("status", ""), frac)
                if msg.get("status") == "success":
                    return True
        return True

    def remove_model(self, name: str) -> bool:
        """Delete a model from disk. Returns True on success."""
        body = json.dumps({"model": name}).encode("utf-8")
        req = urllib.request.Request(
            f"{OLLAMA_HOST}/api/delete",
            data=body,
            method="DELETE",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status == 200
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"delete failed: {e.code} {e.read().decode('utf-8', 'ignore')}")

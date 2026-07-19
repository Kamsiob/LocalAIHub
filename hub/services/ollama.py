"""Ollama service control + model management via the local Ollama HTTP API.

Uses the REST API on 127.0.0.1:11434 (stdlib only, no `ollama` python dep):
  GET  /api/tags     -> installed models (name, size on disk, digest, modified)
  GET  /api/ps       -> models currently loaded into memory
  POST /api/pull     -> pull/update a model (streaming NDJSON progress)
  DELETE /api/delete -> remove a model
"""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

OLLAMA_REGISTRY = "https://registry.ollama.ai/v2"

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

    def check_update(self, name: str) -> dict:
        """Is a newer version of this model available in the Ollama registry?

        Compares the local manifest digest (from /api/tags) with the sha256 of
        the remote manifest. Returns {available, current, latest, detail};
        available is None when it can't be determined (e.g. a local-only model).
        """
        try:
            data = self._get("/api/tags")
        except Exception as exc:  # noqa: BLE001
            return {"available": None, "detail": f"error: {exc}"}
        local = ""
        for m in data.get("models", []):
            if m.get("name") == name:
                local = (m.get("digest") or "").split(":")[-1].lower()
                break
        if not local:
            return {"available": None, "detail": "not installed"}

        repo, tag = name.rsplit(":", 1) if ":" in name else (name, "latest")
        if "/" not in repo:
            repo = "library/" + repo
        url = f"{OLLAMA_REGISTRY}/{repo}/manifests/{tag}"
        req = urllib.request.Request(
            url, headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {"available": None, "detail": "not in registry (local-only model)"}
            return {"available": None, "detail": f"registry error {exc.code}"}
        except Exception as exc:  # noqa: BLE001
            return {"available": None, "detail": f"error: {exc}"}

        remote = hashlib.sha256(body).hexdigest().lower()
        available = remote != local
        return {"available": available, "current": local[:12], "latest": remote[:12],
                "detail": "Update available" if available else "Up to date"}

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

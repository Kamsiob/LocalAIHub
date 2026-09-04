"""What breaks if this goes away, answered from the running system.

No hardcoded map of anyone's stack. Relationships are read from the files and
container definitions that actually declare them, so another machine's setup
resolves just as well as this one's.

Two distinctions this module exists to keep straight:

  Pointing at a service is not using a model. Open WebUI carries OLLAMA_BASE_URL
  and lists whatever Ollama happens to have. It names no model, so removing a
  model does not break it in the way that removing Ollama would. Recording it as
  a consumer of every model would disable almost every trash button for no
  reason.

  A dependency is not a capability limit. Nothing here disables anything. It
  reports what would break so the user can decide, and where a dependent could
  be repointed instead of broken, it says so.

When a relationship cannot be read at all, that is reported as unknown. An
unknown is treated as risk, never as absence.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from .services.base import host_env, in_flatpak

HOME = Path.home()
QUADLET_DIR = HOME / ".config" / "containers" / "systemd"

# A URL in a container's environment, which is how one service names another.
_URL = re.compile(r"https?://([A-Za-z0-9_.\-]+):(\d+)")


def _podman(*args, timeout=25):
    exe = shutil.which("podman")
    if not exe or in_flatpak():
        return None
    try:
        return subprocess.run([exe, *args], capture_output=True, text=True,
                              timeout=timeout, env=host_env())
    except Exception:
        return None


def _quadlet_text(name: str) -> str:
    if not QUADLET_DIR.is_dir():
        return ""
    for q in QUADLET_DIR.rglob("*.container"):
        if q.stem == name:
            try:
                return q.read_text(errors="replace")
            except OSError:
                return ""
    return ""


def port_owners(apps: list, services: dict) -> dict:
    """port -> readable name, built from what is actually published.

    The AI services publish on known ports and the discovered apps report their
    own, so the map is assembled rather than declared.
    """
    owners = {}
    for key, port in (("ollama", 11434), ("openwebui", 3000),
                      ("comfyui", 8188), ("hermes", 9119), ("hermes", 8642)):
        if services.get(key) is not None:
            owners[port] = {"ollama": "Ollama", "openwebui": "Open WebUI",
                            "comfyui": "ComfyUI", "hermes": "Hermes Agent"}[key]
    for a in apps or []:
        if a.get("port"):
            owners[int(a["port"])] = a.get("name") or a.get("container") or "a service"
    return owners


def endpoint_consumers(target_ports: set, apps: list, exclude: str = "") -> list:
    """Services whose configuration names one of these ports.

    Read from the quadlet first, because that is what the user wrote, and from
    the container environment second, because an image can carry a default the
    quadlet does not repeat. Values are never returned, only the fact of a
    match: container environments hold API keys and database passwords here, and
    a preview that printed configuration would leak them.
    """
    found = []
    for a in apps or []:
        container = a.get("container") or ""
        if not container or container == exclude:
            continue
        blobs = [_quadlet_text(container)]
        cp = _podman("inspect", container, "--format",
                     "{{range .Config.Env}}{{println .}}{{end}}")
        if cp and cp.returncode == 0:
            blobs.append(cp.stdout)
        for blob in blobs:
            if any(int(port) in target_ports for _host, port in _URL.findall(blob or "")):
                found.append(a.get("name") or container)
                break
    return sorted(set(found))


def model_consumers(model: str, layers: list) -> tuple:
    """(consumers, unknowns) for one model name.

    A consumer is something that names this model, not something that merely
    points at the service hosting it. `unknowns` lists anything whose
    configuration could not be read, which the caller must treat as risk.
    """
    consumers, unknowns = [], []
    for layer in layers or []:
        info = layer.get("info") or {}
        name = layer.get("name") or layer.get("key") or "a harness"
        if info.get("model"):
            if info["model"] == model:
                ctx = info.get("context")
                consumers.append({
                    "name": name,
                    "detail": (f"{name} is configured to use this exact model"
                               + (f" with a {int(ctx):,} token context" if ctx else "")
                               + "."),
                    "repointable": True,
                })
        elif info.get("unavailable"):
            unknowns.append({
                "name": name,
                "detail": (f"{name}'s configuration could not be read, so it is "
                           f"not known whether it uses this model."),
            })
    return consumers, unknowns


def gguf_relationship(comfy_models: list, node_present: bool) -> dict:
    """The ComfyUI-GGUF node and the .gguf files that need it.

    Stated in both directions, because removing either one breaks the other and
    only one of those is obvious.
    """
    gguf = [m for m in comfy_models or []
            if str(m.get("name", "")).lower().endswith(".gguf")]
    return {
        "node_present": node_present,
        "gguf_count": len(gguf),
        "gguf_names": [m.get("name") for m in gguf][:20],
    }


def for_ollama_model(model: str, layers: list, apps: list, services: dict) -> dict:
    """Everything known about what depends on one Ollama model."""
    consumers, unknowns = model_consumers(model, layers)
    # Services that point at Ollama itself. They keep working without this
    # particular model, so they are context rather than breakage.
    endpoint = endpoint_consumers({11434}, apps)
    return {
        "consumers": consumers,
        "unknown": unknowns,
        "endpoint_users": endpoint,
        "endpoint_note": (
            "These point at Ollama rather than at this model, so they keep "
            "working. They will simply stop listing it."
            if endpoint else ""),
    }


def for_service(entry: dict, apps: list, services: dict) -> dict:
    """What else names this service's endpoint."""
    ports = set()
    if entry.get("port"):
        ports.add(int(entry["port"]))
    users = endpoint_consumers(ports, apps, exclude=entry.get("container", ""))
    return {"endpoint_users": users, "ports": sorted(ports)}

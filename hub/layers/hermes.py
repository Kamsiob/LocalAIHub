"""Hermes Agent (Nous Research) as a layer on top of Ollama.

Hermes runs as a rootless Podman quadlet, so the generated `hermes` user unit is
start/stoppable through exactly the same systemd path as the other services —
nothing new is needed for control, sandbox or otherwise.

Reading its *state* needs two different sources, because Hermes does not put
everything in one place:

  gateway + version   GET 127.0.0.1:9119/api/status on the dashboard. This is
                      the version's own status API — gateway_state, per-platform
                      connection state, active agents, auth_required — and it
                      answers without credentials. Preferred over guessing from
                      the unit, because a running container with a stopped
                      gateway is a real state the unit cannot express.

  model + context     Only in config.yaml inside the container's data volume.
                      ~/.hermes is mode 0700 owned by the container's mapped
                      uid under UserNS=keep-id, so the host user cannot read it
                      even though it lives in their home. The one way in is the
                      container's own interpreter, which needs podman — see
                      MODEL_UNAVAILABLE for what happens when that is missing.

Everything the app cannot see from where it is running is reported as such
rather than filled in with a plausible value.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from ..services.base import host_env, in_flatpak
from .base import Layer

DASHBOARD = "http://127.0.0.1:9119"
API_SERVER = "http://127.0.0.1:8642"
QUADLET = Path.home() / ".config" / "containers" / "systemd" / "hermes.container"

# config.yaml is only reachable through the container, and re-reading it on every
# 5-second refresh would mean spawning podman twelve times a minute for a value
# that changes when the user edits a config file. Cached, with the watcher and
# an explicit refresh able to clear it.
_CONFIG_TTL = 120.0

MODEL_UNAVAILABLE = {
    "what": "The model and context Hermes is configured against",
    "why": (
        "Hermes keeps them in config.yaml inside its container volume. "
        "~/.hermes is owned by the container's mapped user and readable only by "
        "it, so the value has to be read through podman — which the Flatpak "
        "sandbox has no access to."
    ),
    "options": [
        "Use the AppImage or a source run, where podman is available.",
        "Read it yourself with: podman exec hermes hermes status",
    ],
}


class HermesLayer(Layer):
    key = "hermes"
    depends_on = "ollama"
    tagline = "Agent harness · gateway :9119 · API :8642"

    def __init__(self) -> None:
        super().__init__(
            unit="hermes",
            display_name="Hermes Agent",
            health_url=f"{DASHBOARD}/api/health",
        )
        self._config_cache: tuple[float, dict] | None = None

    # --- presence ------------------------------------------------------------
    def install_markers(self) -> list[Path]:
        """The quadlet that defines the container, same rule as Open WebUI."""
        return [QUADLET]

    # --- status API ----------------------------------------------------------
    def _status_api(self) -> dict:
        """The dashboard's own status endpoint, or {} if it isn't answering."""
        try:
            req = urllib.request.Request(f"{DASHBOARD}/api/status", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read().decode("utf-8") or "{}")
        except Exception:
            return {}

    # --- model + context -----------------------------------------------------
    def _read_config(self) -> dict:
        """Model and context from config.yaml, via the container's interpreter.

        Returns {} when it cannot be read; the caller reports that as a stated
        limit, never as "no model configured".
        """
        now = time.monotonic()
        if self._config_cache and now - self._config_cache[0] < _CONFIG_TTL:
            return self._config_cache[1]

        result: dict = {}
        podman = shutil.which("podman")
        if podman and not in_flatpak():
            script = (
                "import yaml, json;"
                "d = yaml.safe_load(open('/opt/data/config.yaml')) or {};"
                "m = d.get('model') or {};"
                "cp = (d.get('custom_providers') or [{}])[0];"
                "models = cp.get('models') or {};"
                "name = m.get('default') or cp.get('model');"
                "ctx = (models.get(name) or {}).get('context_length');"
                "print(json.dumps({'model': name, 'context': ctx,"
                " 'backend_url': m.get('base_url') or cp.get('base_url'),"
                " 'provider': m.get('provider')}))"
            )
            try:
                cp = subprocess.run(
                    [podman, "exec", "hermes",
                     "/opt/hermes/.venv/bin/python", "-c", script],
                    capture_output=True, text=True, timeout=20, env=host_env(),
                )
                if cp.returncode == 0 and cp.stdout.strip():
                    result = json.loads(cp.stdout.strip())
            except Exception:
                result = {}

        self._config_cache = (now, result)
        return result

    def invalidate(self) -> None:
        self._config_cache = None

    # --- assembled view ------------------------------------------------------
    def layer_info(self) -> dict:
        api = self._status_api()
        cfg = self._read_config()
        unavailable: list[dict] = []

        if not cfg.get("model"):
            unavailable.append(MODEL_UNAVAILABLE)

        # gateway_state is the version's own vocabulary ("running"/"stopped");
        # absent means the status API didn't answer, which is different from the
        # gateway being off and is labelled that way.
        gateway = api.get("gateway_state") if api else None

        return {
            "reachable": bool(api),
            "version": api.get("version") or "",
            "gateway": gateway,
            "gateway_running": bool(api.get("gateway_running")),
            "active_agents": api.get("active_agents"),
            "auth_required": bool(api.get("auth_required")),
            "model": cfg.get("model") or "",
            "context": cfg.get("context"),
            "backend_url": cfg.get("backend_url") or "",
            "dashboard_url": DASHBOARD,
            "api_url": API_SERVER,
            "unavailable": unavailable,
        }

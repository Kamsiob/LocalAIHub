"""Open WebUI service control.

Open WebUI runs as a Podman *quadlet* — a generated `--user` systemd unit named
`open-webui` (from ~/.config/containers/systemd/open-webui.container). Start/stop
work with no root; `is-enabled` reports "generated" (its autostart is governed by
the .container file, not a wants-symlink), so start/stop is the control surface.
"""
from __future__ import annotations

from .base import Service

OPENWEBUI_HOST = "http://127.0.0.1:3000"


class OpenWebUIService(Service):
    def __init__(self) -> None:
        super().__init__(
            unit="open-webui",
            display_name="Open WebUI",
            health_url=f"{OPENWEBUI_HOST}/",
        )

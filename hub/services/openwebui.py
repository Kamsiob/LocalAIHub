"""Open WebUI service control.

Open WebUI runs as a Podman *quadlet* — a generated `--user` systemd unit named
`open-webui` (from ~/.config/containers/systemd/open-webui.container). Start/stop
work with no root; `is-enabled` reports "generated" (its autostart is governed by
the .container file, not a wants-symlink), so start/stop is the control surface.
"""
from __future__ import annotations

from pathlib import Path

from .base import Service

OPENWEBUI_HOST = "http://127.0.0.1:3000"

# Where Podman looks for rootless quadlets. The .container file here is what
# generates the open-webui unit, so its presence is what "installed" means.
QUADLET_DIR = Path.home() / ".config" / "containers" / "systemd"


class OpenWebUIService(Service):
    def __init__(self) -> None:
        super().__init__(
            unit="open-webui",
            display_name="Open WebUI",
            health_url=f"{OPENWEBUI_HOST}/",
        )

    def install_markers(self) -> list[Path]:
        """The quadlet file that defines the container.

        Removing Open WebUI means deleting open-webui.container (and reloading);
        the generated unit then stops existing too. Reading one file is cheaper
        and more reliable than shelling out to `podman ps` on every refresh.
        Not visible inside Flatpak, which falls back to the unit — see
        Service.is_installed.
        """
        return [QUADLET_DIR / "open-webui.container"]

"""Base service control via `systemctl --user` + an HTTP health check.

Every managed service (Ollama, Open WebUI, ComfyUI) is a *user* systemd unit, so
the whole surface works with no root. "active" means the unit's process is up;
"serving" means the HTTP port actually answers — the two differ during the seconds
a service takes to warm up, which the UI uses to show a "starting…" state.
"""
from __future__ import annotations

import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Optional

SYSTEMCTL = shutil.which("systemctl") or "systemctl"


def run_systemctl(*args: str, timeout: float = 20) -> subprocess.CompletedProcess:
    """Run `systemctl --user <args>` and return the completed process."""
    return subprocess.run(
        [SYSTEMCTL, "--user", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def http_probe(url: str, timeout: float = 3.0) -> bool:
    """True if the URL answers with any HTTP status (i.e. the port is serving)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status < 600
    except urllib.error.HTTPError:
        return True  # an HTTP error is still a response — the server is up
    except Exception:
        return False


@dataclass
class ServiceStatus:
    name: str
    unit: str
    active: bool
    serving: bool
    enabled: Optional[str]
    sub_state: str = ""
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Service:
    """A local service backed by a systemd --user unit."""

    def __init__(
        self,
        unit: str,
        display_name: str,
        health_url: Optional[str] = None,
    ) -> None:
        self.unit = unit
        self.display_name = display_name
        self.health_url = health_url

    # --- queries -------------------------------------------------------------
    def is_active(self) -> bool:
        return run_systemctl("is-active", self.unit).stdout.strip() == "active"

    def sub_state(self) -> str:
        cp = run_systemctl("show", self.unit, "-p", "SubState", "--value")
        return cp.stdout.strip()

    def enabled_state(self) -> Optional[str]:
        # Returns "enabled"/"disabled"/"generated"/"static"; None if unknown.
        out = run_systemctl("is-enabled", self.unit).stdout.strip()
        return out or None

    def is_serving(self) -> bool:
        if not self.health_url:
            return self.is_active()
        return http_probe(self.health_url)

    def status(self) -> ServiceStatus:
        active = self.is_active()
        return ServiceStatus(
            name=self.display_name,
            unit=self.unit,
            active=active,
            serving=self.is_serving() if active else False,
            enabled=self.enabled_state(),
            sub_state=self.sub_state(),
        )

    # --- control -------------------------------------------------------------
    def start(self) -> bool:
        return run_systemctl("start", self.unit).returncode == 0

    def stop(self) -> bool:
        return run_systemctl("stop", self.unit).returncode == 0

    def restart(self) -> bool:
        return run_systemctl("restart", self.unit).returncode == 0

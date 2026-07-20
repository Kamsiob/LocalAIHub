"""Base service control via `systemctl --user` + an HTTP health check.

Every managed service (Ollama, Open WebUI, ComfyUI) is a *user* systemd unit, so
the whole surface works with no root. "active" means the unit's process is up;
"serving" means the HTTP port actually answers — the two differ during the seconds
a service takes to warm up, which the UI uses to show a "starting…" state.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Optional

SYSTEMCTL = shutil.which("systemctl") or "systemctl"


def host_env() -> dict:
    """Environment for spawning host system tools (systemctl, journalctl, git…).

    In a frozen / AppImage build the process runs with LD_LIBRARY_PATH pointing at
    the bundled libraries. A host binary that inherits it loads our older bundled
    libs and fails (e.g. systemctl against a bundled libcrypto that lacks the
    host's OPENSSL symbols). Strip it so host tools run against the host's own
    libraries. A no-op when running from source.
    """
    env = os.environ.copy()
    if getattr(sys, "frozen", False):
        env.pop("LD_LIBRARY_PATH", None)
        env.pop("LD_PRELOAD", None)
    return env


def run_systemctl(*args: str, timeout: float = 20) -> subprocess.CompletedProcess:
    """Run `systemctl --user <args>` and return the completed process."""
    return subprocess.run(
        [SYSTEMCTL, "--user", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=host_env(),
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
    failed: bool = False        # unit entered the systemd "failed" state (a crash)
    result: str = ""            # systemd Result (exit-code / signal / success)
    present: bool = True        # the unit exists on this machine (LoadState=loaded)

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

    def show_props(self, *props: str) -> dict:
        args = ["show", self.unit]
        for p in props:
            args += ["-p", p]
        cp = run_systemctl(*args)
        out: dict = {}
        for line in cp.stdout.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                out[k] = v
        return out

    def logs(self, lines: int = 40) -> str:
        """Last N journal lines for this unit (for showing after a crash)."""
        journalctl = shutil.which("journalctl") or "journalctl"
        try:
            cp = subprocess.run(
                [journalctl, "--user", "-u", self.unit, "-n", str(lines),
                 "--no-pager", "-o", "short-precise"],
                capture_output=True, text=True, timeout=15,
                env=host_env(),
            )
            return (cp.stdout or cp.stderr or "").strip() or "(no log output)"
        except Exception as exc:  # noqa: BLE001
            return f"(could not read log: {exc})"

    def enabled_state(self) -> Optional[str]:
        # Returns "enabled"/"disabled"/"generated"/"static"; None if unknown.
        out = run_systemctl("is-enabled", self.unit).stdout.strip()
        return out or None

    def is_serving(self) -> bool:
        if not self.health_url:
            return self.is_active()
        return http_probe(self.health_url)

    def status(self) -> ServiceStatus:
        props = self.show_props("ActiveState", "SubState", "Result", "LoadState")
        active_state = props.get("ActiveState", "")
        active = active_state == "active"
        # LoadState=loaded means the unit exists here; not-found means the service
        # simply isn't installed on this machine (a stranger's fresh box), which we
        # surface honestly as "Not installed" rather than a misleading "Stopped".
        present = props.get("LoadState", "loaded") not in ("not-found", "")
        return ServiceStatus(
            name=self.display_name,
            unit=self.unit,
            active=active,
            serving=self.is_serving() if active else False,
            enabled=self.enabled_state(),
            sub_state=props.get("SubState", ""),
            failed=active_state == "failed",
            result=props.get("Result", ""),
            present=present,
        )

    # --- control -------------------------------------------------------------
    def start(self) -> bool:
        return run_systemctl("start", self.unit).returncode == 0

    def stop(self) -> bool:
        return run_systemctl("stop", self.unit).returncode == 0

    def restart(self) -> bool:
        return run_systemctl("restart", self.unit).returncode == 0

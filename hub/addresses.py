"""Which addresses this machine can actually be reached on.

The app has always opened services at 127.0.0.1, which is right on this machine
and useless from a phone. But the fix is not to guess a "better" address — it is
to report only what genuinely exists here, and to say what each one is for.

Three kinds, in the order a person needs them:

  loopback   127.0.0.1. Always present, only works on this machine.
  lan        A private-range address (192.168/16, 10/8, 172.16/12) that other
             devices on the same network can reach.
  tailscale  A 100.64.0.0/10 CGNAT address, plus the MagicDNS name when the
             tailscale CLI is there to tell us. Works from anywhere on the
             tailnet.

Interfaces are read with an ioctl over the stdlib rather than by shelling out to
`ip`, because there is no guarantee iproute2 exists inside a Flatpak runtime and
this needs no binary at all. Anything not detected is simply absent from the
result — nothing here invents an address.
"""
from __future__ import annotations

import fcntl
import ipaddress
import json
import shutil
import socket
import struct
import subprocess
import time

_SIOCGIFADDR = 0x8915
_CACHE_TTL = 30.0
_cache: tuple[float, dict] | None = None

# What each address means, in the app's own voice. Shown next to the value so a
# newer user doesn't have to already know which one works from where.
MEANING = {
    "loopback": "Only on this computer",
    "lan": "Other devices on your home network",
    "tailscale": "Your devices anywhere, over Tailscale",
}


def _iface_ipv4(name: str) -> str:
    """The IPv4 address bound to one interface, or "" if it has none."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        packed = struct.pack("256s", name[:15].encode())
        return socket.inet_ntoa(fcntl.ioctl(sock.fileno(), _SIOCGIFADDR, packed)[20:24])
    except OSError:
        return ""
    finally:
        sock.close()


def _classify(ip: str) -> str:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ""
    if addr.is_loopback:
        return "loopback"
    # Tailscale hands out addresses from the CGNAT range, which is exactly what
    # distinguishes it from an ordinary LAN address without asking Tailscale.
    if addr in ipaddress.ip_network("100.64.0.0/10"):
        return "tailscale"
    if addr.is_private:
        return "lan"
    return ""


def _magic_dns() -> str:
    """The MagicDNS name, if the tailscale CLI is available to report it.

    Absent inside Flatpak (no binary in the sandbox), in which case the tailnet
    address is still offered by IP — a working answer, just a less memorable one.
    """
    exe = shutil.which("tailscale")
    if not exe:
        return ""
    try:
        cp = subprocess.run([exe, "status", "--json"], capture_output=True,
                            text=True, timeout=6)
        if cp.returncode != 0:
            return ""
        data = json.loads(cp.stdout or "{}")
        if data.get("BackendState") != "Running":
            return ""
        name = (data.get("Self") or {}).get("DNSName") or ""
        return name.rstrip(".")
    except Exception:
        return ""


def detect(force: bool = False) -> dict:
    """{loopback, lan, tailscale} — only the ones that actually exist.

    lan/tailscale are {"host": ..., "meaning": ...} or absent entirely.
    """
    global _cache
    now = time.monotonic()
    if _cache and not force and now - _cache[0] < _CACHE_TTL:
        return _cache[1]

    found: dict = {"loopback": {"host": "127.0.0.1", "meaning": MEANING["loopback"]}}
    try:
        interfaces = socket.if_nameindex()
    except OSError:
        interfaces = []

    for _idx, name in interfaces:
        ip = _iface_ipv4(name)
        if not ip:
            continue
        kind = _classify(ip)
        # First one wins: a machine with several LAN interfaces (wifi + ethernet)
        # only needs one working answer, not a list to choose from.
        if kind in ("lan", "tailscale") and kind not in found:
            found[kind] = {"host": ip, "meaning": MEANING[kind], "iface": name}

    if "tailscale" in found:
        # Keep the numeric address before the name overwrites it: MagicDNS
        # resolution can be off on whichever device is doing the typing, and the
        # IP is the fallback that always works on the tailnet.
        found["tailscale"]["ip"] = found["tailscale"]["host"]
        name = _magic_dns()
        if name:
            found["tailscale"]["magic_dns"] = name
            found["tailscale"]["host"] = name

    _cache = (now, found)
    return found


def urls_for(port: int) -> list[dict]:
    """Every address this port is reachable at, loopback first.

    Loopback leads because it is the one that always works where the app is
    running; the rest are what you'd type on another device.
    """
    out = []
    addrs = detect()
    for kind in ("loopback", "lan", "tailscale"):
        entry = addrs.get(kind)
        if not entry:
            continue
        out.append({
            "kind": kind,
            "url": f"http://{entry['host']}:{port}",
            "meaning": entry["meaning"],
        })
    return out

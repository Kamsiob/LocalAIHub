"""Whatever else the user is self-hosting, found generically.

No list of supported services. The app asks Podman what is actually running and
shows it, so someone else's Jellyfin and Nextcloud appear here exactly as this
machine's FreshRSS and Immich do.

What counts as a service, and why:

  it carries a PODMAN_SYSTEMD_UNIT label   Quadlet stamps this on every container
      it generates, and it names the unit to start and stop. A container without
      it is something you ran by hand — a toolbox, a one-off `podman run` — and
      putting a start/stop toggle on those would be wrong. It is also what keeps
      dev containers out of the list without hardcoding their names.

  it publishes at least one port            Nothing to open, nothing to check for
      life, nothing a person thinks of as "a service they visit".

  pods collapse to one entry                Immich is five containers sharing one
      published port; five cards for one app would be noise. The pod's infra
      container carries the pod's unit name, so it stands in for the whole pod
      and the members are dropped.

Status is a real liveness check against the address the port is actually
published on — not merely "the container exists". A container can be up while
the thing inside it is broken, which is the same distinction the AI services
already draw between "active" and "serving".
"""
from __future__ import annotations

import json
import shutil
import subprocess

from .base import ServiceStatus, host_env, http_probe, in_flatpak

# Units already shown in the Local AI section; they must not appear twice.
AI_UNITS = {"ollama.service", "open-webui.service", "comfyui.service", "hermes.service"}

# Nicer names for images people commonly self-host. Matching is on a substring of
# the image reference, so a fork or a mirror still resolves. Anything unmatched
# is shown by its container name, which is honest and usually what the user
# called it anyway.
KNOWN = [
    ("immich", "Immich", "Photos"),
    ("jellyfin", "Jellyfin", "Media"),
    ("plex", "Plex", "Media"),
    ("freshrss", "FreshRSS", "RSS reader"),
    ("searxng", "SearXNG", "Search"),
    ("nextcloud", "Nextcloud", "Files"),
    ("vaultwarden", "Vaultwarden", "Passwords"),
    ("bitwarden", "Vaultwarden", "Passwords"),
    ("home-assistant", "Home Assistant", "Home automation"),
    ("homeassistant", "Home Assistant", "Home automation"),
    ("paperless", "Paperless-ngx", "Documents"),
    ("gitea", "Gitea", "Git hosting"),
    ("forgejo", "Forgejo", "Git hosting"),
    ("navidrome", "Navidrome", "Music"),
    ("audiobookshelf", "Audiobookshelf", "Audiobooks"),
    ("calibre", "Calibre-Web", "Books"),
    ("syncthing", "Syncthing", "File sync"),
    ("webdav", "WebDAV", "File share"),
    ("uptime-kuma", "Uptime Kuma", "Monitoring"),
    ("grafana", "Grafana", "Dashboards"),
    ("adguard", "AdGuard Home", "DNS filtering"),
    ("pihole", "Pi-hole", "DNS filtering"),
    ("qbittorrent", "qBittorrent", "Downloads"),
    ("mealie", "Mealie", "Recipes"),
    ("actual", "Actual Budget", "Budgeting"),
]

# The app cannot reach podman from inside the Flatpak sandbox, so rather than
# show an empty section it says why. Same treatment as the Hermes model read.
SANDBOX_LIMIT = {
    "what": "Your other self-hosted services",
    "why": ("Finding them means asking Podman what is running, and the Flatpak "
            "sandbox has no route to the container runtime."),
    "options": ["Use the AppImage or a source run, where podman is available."],
}


def available() -> bool:
    return bool(shutil.which("podman")) and not in_flatpak()


def _label(name: str, image: str) -> tuple[str, str]:
    """A readable title, without losing what makes two similar services different.

    Two containers off the same image — a Joplin WebDAV and a file-share WebDAV —
    must not both render as "WebDAV". So the known name replaces only the part of
    the container name it matches, and the rest of the name is kept: joplin-webdav
    becomes "Joplin WebDAV", while a container simply called webdav becomes
    "WebDAV".
    """
    haystack = f"{image} {name}".lower()
    for needle, nice, kind in KNOWN:
        if needle not in haystack:
            continue
        tokens = [t for t in name.replace("_", "-").split("-") if t]
        bare = "".join(tokens).lower()
        if bare == needle.replace("-", "") or not tokens:
            return nice, kind
        titled = [nice if t.lower() in (needle, needle.replace("-", "")) else t.title()
                  for t in tokens]
        # If the needle matched only the image, the container name never contained
        # it, so append the known name to say what the thing actually is.
        if nice not in titled:
            return f"{' '.join(t.title() for t in tokens)} ({nice})", kind
        return " ".join(titled), kind
    return name.replace("-", " ").replace("_", " ").title(), ""


def _ports(entry: dict) -> list[dict]:
    """Published ports as [{host, port}], de-duplicated, loopback-friendly.

    An empty or 0.0.0.0 host means "all interfaces", which from this machine is
    reachable at 127.0.0.1. A specific host (a Tailscale address, say) is kept as
    it is, because that is the only place the port actually answers.
    """
    out: list[dict] = []
    seen = set()
    for p in entry.get("Ports") or []:
        port = p.get("host_port")
        if not port:
            continue
        host = p.get("host_ip") or ""
        host = "127.0.0.1" if host in ("", "0.0.0.0", "::") else host
        key = (host, port)
        if key in seen:
            continue
        seen.add(key)
        out.append({"host": host, "port": int(port)})
    out.sort(key=lambda x: x["port"])
    return out


def _podman_ps() -> list[dict]:
    exe = shutil.which("podman")
    if not exe:
        return []
    try:
        cp = subprocess.run([exe, "ps", "-a", "--format", "json"],
                            capture_output=True, text=True, timeout=25, env=host_env())
        if cp.returncode != 0:
            return []
        return json.loads(cp.stdout or "[]")
    except Exception:
        return []


def discover() -> list[dict]:
    """One entry per self-hosted service, AI stack excluded."""
    if not available():
        return []

    entries = _podman_ps()
    # Group by pod *ID*: PodName is empty in current Podman's ps output, so the
    # ID is the only field that reliably links a pod's members together.
    pods_with_infra = {e.get("Pod") for e in entries
                       if e.get("IsInfra") and e.get("Pod")}

    found: list[dict] = []
    for e in entries:
        labels = e.get("Labels") or {}
        unit = labels.get("PODMAN_SYSTEMD_UNIT") or ""
        if not unit or unit in AI_UNITS:
            continue

        pod = e.get("Pod") or ""
        if pod and pod in pods_with_infra and not e.get("IsInfra"):
            continue

        ports = _ports(e)
        if not ports:
            continue

        names = e.get("Names") or ["?"]
        # For a pod, the unit is what names it: immich-pod.service -> immich.
        # The infra container is called immich-infra, which is plumbing, not a
        # name anyone chose.
        if pod and e.get("IsInfra"):
            raw_name = unit[:-len("-pod.service")] if unit.endswith("-pod.service") \
                else names[0].removesuffix("-infra")
        else:
            raw_name = names[0]
        image = e.get("Image") or ""
        nice, kind = _label(raw_name, image)

        found.append({
            "key": f"container:{unit}",
            "unit": unit,
            "container": raw_name,
            "name": nice,
            "kind": kind,
            "image": image,
            "running": (e.get("State") or "").lower() == "running",
            "ports": ports,
        })

    found.sort(key=lambda x: x["name"].lower())
    return found


def status_for(entry: dict) -> dict:
    """Real liveness, probed at the address the port is published on."""
    primary = entry["ports"][0]
    serving = http_probe(f"http://{primary['host']}:{primary['port']}/", timeout=1.5)
    return {"active": entry["running"], "serving": serving,
            "probe": f"{primary['host']}:{primary['port']}"}


def to_status(entry: dict) -> ServiceStatus:
    st = status_for(entry)
    return ServiceStatus(
        name=entry["name"], unit=entry["unit"], active=st["active"],
        serving=st["serving"], enabled=None, present=True,
    )

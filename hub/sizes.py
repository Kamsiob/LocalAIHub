"""How much disk the local AI stack is using. Read only, always.

Nothing in this module deletes, moves, or modifies anything. Removal happens
only through the uninstall flow, and this module is not part of it.

The performance rule here is not "never walk a directory". Measured on this
machine, walking ~/.ollama (92 GiB) takes about 3 ms and ~/ComfyUI/models
(43 GiB) about 2 ms, because the cost tracks inode count and those trees hold
43 and 39 files. The tree that actually hurts is Immich on an external spinning
disk: 533 GiB across 69,812 files, 51 s cold. So the rule is "never walk another
filesystem", which is enforced structurally in _walk_size by comparing st_dev
against home rather than by maintaining a list of paths to avoid.

Preference order for every figure:
  1. An API that already knows the answer (Ollama's /api/tags, podman system df).
  2. Data the app has already collected for another reason (ComfyUI's model scan
     already calls stat on every file).
  3. A bounded walk, on the home filesystem only.
  4. Nothing. An unknown figure is reported as unknown, never as zero.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .services.base import host_env, in_flatpak

# A walk is abandoned past this many entries. Nothing the app measures on the
# home filesystem comes close; a tree that does is reported as "unknown" rather
# than silently costing seconds on every refresh.
_MAX_WALK_ENTRIES = 60_000

# How long a computed figure stays fresh. Sizes change when a model is pulled or
# removed, which the change watcher already notices, so this is only a backstop.
_TTL = 180.0


def human(num_bytes) -> str:
    """Matches the size strings the rest of the app already prints."""
    if num_bytes is None:
        return ""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit in ("B", "KB") else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@dataclass
class Entry:
    """One measured figure. `state` is what the UI renders, not `bytes`."""
    key: str
    label: str
    state: str = "pending"          # pending | ready | unknown
    bytes: int | None = None
    source: str = ""                # how it was obtained, for the report
    note: str = ""                  # why it is unknown, when it is

    def to_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "state": self.state,
                "bytes": self.bytes, "human": human(self.bytes) if self.bytes is not None else "",
                "source": self.source, "note": self.note}


@dataclass
class Filesystem:
    """Free space belongs to a device, not to a tool.

    Five of this machine's six data locations share one filesystem. Reporting
    free space per tool would print the same number five times and imply that
    deleting models frees space for photos. So locations are grouped by st_dev
    and each device is reported once, naming what lives on it.
    """
    device: int
    mount: str
    total: int
    free: int
    holds: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"mount": self.mount, "total": self.total, "free": self.free,
                "total_human": human(self.total), "free_human": human(self.free),
                "used_pct": round(100 * (self.total - self.free) / self.total) if self.total else 0,
                "holds": sorted(self.holds)}


def _walk_size(root: Path) -> tuple[int | None, str]:
    """Bytes under root, or (None, reason).

    Refuses any path that is not on the same filesystem as the home directory.
    That single check is what keeps the external disk out: it is a different
    device, so no list of paths has to be kept correct as the machine changes.
    """
    try:
        home_dev = Path.home().stat().st_dev
        if not root.exists():
            return None, "not present"
        if root.stat().st_dev != home_dev:
            return None, "on another filesystem, not measured from here"
    except OSError as exc:
        return None, f"not readable ({exc.strerror or exc})"

    total = 0
    seen = 0
    seen_inodes: set = set()
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda _e: None):
        try:
            if os.stat(dirpath).st_dev != home_dev:
                dirnames[:] = []      # do not cross a mount point mid-walk
                continue
        except OSError:
            dirnames[:] = []
            continue
        for name in filenames:
            seen += 1
            if seen > _MAX_WALK_ENTRIES:
                return None, "too many files to measure quickly"
            try:
                st = os.lstat(os.path.join(dirpath, name))
            except OSError:
                continue
            # A file hard-linked into two model directories is one file on disk.
            if st.st_nlink > 1:
                if st.st_ino in seen_inodes:
                    continue
                seen_inodes.add(st.st_ino)
            total += st.st_size
    return total, ""


def _podman_df() -> dict:
    """Image, container and volume totals. No walk: podman already knows."""
    exe = shutil.which("podman")
    if not exe or in_flatpak():
        return {}
    try:
        cp = subprocess.run([exe, "system", "df", "--format", "json"],
                            capture_output=True, text=True, timeout=30, env=host_env())
        if cp.returncode != 0:
            return {}
        return {"raw": json.loads(cp.stdout or "[]")}
    except Exception:
        return {}


def _sum_podman(raw: list, types: set) -> tuple[int | None, int | None]:
    """(size, reclaimable) for the given podman df row types.

    RawSize and RawReclaimable are integers; Size and Reclaimable are
    preformatted strings for humans. Use the integers. Note the row is called
    "Local Volumes", not "Volumes", which a prefix match gets wrong.
    """
    total = 0
    reclaim = 0
    found = False
    for rec in raw or []:
        if not isinstance(rec, dict):
            continue
        if (rec.get("Type") or "") not in types:
            continue
        found = True
        try:
            total += int(rec.get("RawSize") or 0)
            reclaim += int(rec.get("RawReclaimable") or 0)
        except (TypeError, ValueError):
            return None, None
    return (total, reclaim) if found else (None, None)


# Host paths that are plumbing rather than user data. A quadlet binding
# /etc/localtime is stating a timezone, not storing anything.
_SYSTEM_PREFIXES = ("/etc", "/proc", "/sys", "/dev", "/run", "/usr", "/boot")

QUADLET_DIR = Path.home() / ".config" / "containers" / "systemd"


def declared_data_mounts() -> list:
    """(path, service) for every host directory a quadlet binds as data.

    Read from the quadlet files rather than from podman's mount list. Podman
    reports every mount a container has, including /sys, /dev/pts and the
    toolbox plumbing, which describes the container runtime rather than the
    user's data. A Volume= line in a quadlet is the user saying "my data lives
    here", which is exactly the question being asked.

    Without this the summary would describe the wrong device for the largest
    thing on the machine: this photo library is on an external disk, while
    everything else is on the internal one.
    """
    out = []
    if not QUADLET_DIR.is_dir():
        return out
    home = str(Path.home())
    for quadlet in sorted(QUADLET_DIR.rglob("*.container")):
        service = quadlet.stem
        try:
            text = quadlet.read_text(errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("Volume="):
                continue
            source = line[len("Volume="):].split(":", 1)[0].strip()
            source = source.replace("%h", home)
            if not source.startswith("/"):
                continue          # a named volume, counted by podman system df
            if source.startswith(_SYSTEM_PREFIXES):
                continue
            out.append((Path(source), service))
    return out


class DiskUsage:
    """Cached, background-computed disk figures.

    The collect loop reads `snapshot()`, which never blocks and never computes.
    Work happens in `refresh()` on its own thread, so a slow figure shows as
    pending and fills in later rather than delaying a frame.
    """

    def __init__(self, ollama, comfyui) -> None:
        self._ollama = ollama
        self._comfyui = comfyui
        self._lock = threading.Lock()
        self._entries: dict = {}
        self._filesystems: list = []
        self._stamp = 0.0
        self._running = False

    # --- read side, never blocks --------------------------------------------
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "entries": [e.to_dict() for e in self._entries.values()],
                "filesystems": [f.to_dict() for f in self._filesystems],
                "measured": bool(self._stamp),
            }

    def stale(self) -> bool:
        return (time.monotonic() - self._stamp) > _TTL

    def invalidate(self) -> None:
        with self._lock:
            self._stamp = 0.0

    # --- write side, background ---------------------------------------------
    def refresh_async(self) -> None:
        """Compute in the background. Concurrent calls collapse into one."""
        with self._lock:
            if self._running:
                return
            self._running = True
        threading.Thread(target=self._refresh, daemon=True).start()

    def _set(self, entry: Entry) -> None:
        with self._lock:
            self._entries[entry.key] = entry

    def _refresh(self) -> None:
        try:
            self._measure_ollama()
            self._measure_comfy()
            self._measure_podman()
            self._measure_filesystems()
            with self._lock:
                self._stamp = time.monotonic()
        finally:
            with self._lock:
                self._running = False

    def _measure_ollama(self) -> None:
        # /api/tags is authoritative and returns in about 6 ms. Summing it
        # matched the blob files on disk to within 11 KB, the difference being
        # one small config blob shared by two manifests.
        try:
            models = self._ollama.list_models()
            total = sum(m.size_bytes for m in models)
            self._set(Entry("ollama", "Ollama models", "ready", total,
                            "Ollama API"))
            return
        except Exception:
            pass
        root = Path(os.environ.get("OLLAMA_MODELS", Path.home() / ".ollama"))
        size, why = _walk_size(root)
        if size is None:
            self._set(Entry("ollama", "Ollama models", "unknown", None, "",
                            f"Ollama is not running and {root} is {why}."
                            if why else "Ollama is not running."))
        else:
            self._set(Entry("ollama", "Ollama models", "ready", size,
                            f"{root} on disk"))

    def _measure_comfy(self) -> None:
        # The model scan already stats every file for the list the UI shows, so
        # this is aggregation of data the app has, at no extra I/O.
        try:
            models = self._comfyui.list_models()
            total = sum(int(m.get("size_bytes") or 0) for m in models)
            self._set(Entry("comfyui", "ComfyUI models", "ready", total,
                            "ComfyUI model scan"))
        except Exception as exc:
            self._set(Entry("comfyui", "ComfyUI models", "unknown", None, "",
                            f"The model folders could not be read ({exc})."))

    def _measure_podman(self) -> None:
        df = _podman_df()
        raw = df.get("raw")
        if not raw:
            why = ("Podman is not available in this build."
                   if in_flatpak() or not shutil.which("podman")
                   else "Podman did not report its disk usage.")
            for key, label in (("images", "Container images"),
                               ("volumes", "Container volumes")):
                self._set(Entry(key, label, "unknown", None, "", why))
            return
        for key, label, types in (
            ("images", "Container images", {"Images"}),
            ("volumes", "Container volumes", {"Local Volumes"}),
        ):
            total, reclaim = _sum_podman(raw, types)
            if total is None:
                self._set(Entry(key, label, "unknown", None, "",
                                "Podman reported this in a format this app cannot total."))
                continue
            # A plain fact, not a suggestion. The app never proposes deletions.
            note = (f"{human(reclaim)} is not used by any container"
                    if key == "images" and reclaim else "")
            self._set(Entry(key, label, "ready", total, "podman system df", note))

    def _measure_filesystems(self) -> None:
        """One record per device, naming what the app knows lives on it."""
        locations = [
            (Path(os.environ.get("OLLAMA_MODELS", Path.home() / ".ollama")), "Ollama models"),
            (getattr(self._comfyui, "root", Path.home() / "ComfyUI"), "ComfyUI"),
            (Path.home() / ".local" / "share" / "containers", "Containers"),
            (Path.home(), "Home"),
        ]
        # Data a quadlet declares, so an external disk holding a photo library
        # is not simply missing from the summary.
        for src, name in declared_data_mounts():
            locations.append((src, name))
        by_dev: dict = {}
        for path, label in locations:
            try:
                if not path.exists():
                    continue
                dev = path.stat().st_dev
                usage = shutil.disk_usage(path)
            except OSError:
                continue
            fs = by_dev.get(dev)
            if fs is None:
                mount = path
                while mount != mount.parent:
                    try:
                        if mount.parent.stat().st_dev != dev:
                            break
                    except OSError:
                        break
                    mount = mount.parent
                fs = Filesystem(dev, str(mount), usage.total, usage.free)
                by_dev[dev] = fs
            if label not in fs.holds:
                fs.holds.append(label)
        with self._lock:
            self._filesystems = list(by_dev.values())

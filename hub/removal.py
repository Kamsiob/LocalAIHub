"""Planning and performing a removal, with the manifest as the only authority.

The shape of this module follows one rule: nothing is deleted that was not shown
to the user first. So planning and executing are separate, the plan is a value
the user sees in full, and the executor will only act on a plan it can prove is
the same one that was shown.

Three ideas carry most of the safety:

  A path is never constructed and deleted. It is resolved, checked to lie under
  an allowed root, checked not to be the root itself, and only then acted on. A
  symlink is unlinked as a link, never followed, so a link into someone else's
  data cannot be turned into a delete of that data.

  Software and data are different tiers and never share a confirmation. A
  container, a unit file and a config directory are software. A named volume is
  data, is excluded by default, and is only ever included when the caller
  explicitly asks for it.

  A shared artifact is never removed as part of removing one of its users. An
  image backing two containers, or a volume mounted by two services, is reported
  as deliberately kept, with the reason.

The executor stops at the first failure. A partial removal that keeps going is
how a system ends up in a state nobody can reason about.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .services.base import host_env, in_flatpak, run_systemctl

HOME = Path.home()
QUADLET_DIR = HOME / ".config" / "containers" / "systemd"
UNIT_DIR = HOME / ".config" / "systemd" / "user"
APPS_DIR = HOME / ".local" / "share" / "applications"
ICON_DIRS = [HOME / ".local" / "share" / "icons"]

# Every deletable path must resolve under one of these. Anything else is refused
# rather than reported, because a path outside them is a bug in the planner and
# a bug in a planner that deletes files should stop the operation.
ALLOWED_ROOTS = [
    QUADLET_DIR, UNIT_DIR, APPS_DIR,
    HOME / ".local" / "share" / "icons",
    HOME / ".config", HOME / ".cache",
]

SOFTWARE = "software"
DATA = "data"


# --------------------------------------------------------------------------- #
# path safety
# --------------------------------------------------------------------------- #
def validate_path(raw, roots=None) -> Path | None:
    """The resolved path, or None if it may not be touched.

    Refuses anything that does not exist, anything that resolves outside the
    allowed roots, and any root itself. A symlink is validated by where the link
    lives, not by where it points, and callers unlink it without following.
    """
    roots = roots or ALLOWED_ROOTS
    try:
        p = Path(raw)
    except TypeError:
        return None

    try:
        if p.is_symlink():
            # Validate the containing directory: the link is what gets removed.
            parent = p.parent.resolve(strict=True)
            resolved = parent / p.name
        else:
            resolved = p.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None

    for root in roots:
        try:
            rroot = root.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved == rroot:
            return None                     # never the root itself
        try:
            if os.path.commonpath([str(resolved), str(rroot)]) == str(rroot):
                return resolved
        except ValueError:
            continue
    return None


def _norm(p) -> str:
    """A path in one canonical form.

    Both sides of a self-protection check have to be normalized the same way.
    On an ostree system /home is a symlink to /var/home, so comparing a resolved
    path against an unresolved one never matches and the check silently passes
    everything. That is the failure this function exists to prevent.
    """
    path = Path(p)
    try:
        return str(path.resolve())
    except (OSError, RuntimeError):
        return str(path)


def app_own_paths() -> set:
    """Everything belonging to this app. It must never remove itself."""
    own = set()
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        own.add(_norm(appimage))
    own.add(_norm(HOME / ".config" / "local-ai-hub"))
    for name in ("local-ai-hub.desktop", "io.github.kamsiob.LocalAIHub.desktop"):
        own.add(_norm(APPS_DIR / name))
    try:
        own.add(_norm(Path(__file__).parent.parent))
    except OSError:
        pass
    return own


def is_own_path(p) -> bool:
    resolved = _norm(p)
    for own in app_own_paths():
        if resolved == own or resolved.startswith(own.rstrip("/") + "/"):
            return True
    return False


# --------------------------------------------------------------------------- #
# podman facts
# --------------------------------------------------------------------------- #
def _podman(*args, timeout=30):
    exe = shutil.which("podman")
    if not exe or in_flatpak():
        return None
    try:
        return subprocess.run([exe, *args], capture_output=True, text=True,
                              timeout=timeout, env=host_env())
    except Exception:
        return None


def _containers() -> list:
    cp = _podman("ps", "-a", "--format", "json")
    if not cp or cp.returncode != 0:
        return []
    try:
        return json.loads(cp.stdout or "[]")
    except Exception:
        return []


def image_users(image: str, exclude_container: str) -> list:
    """Other containers built on the same image. Never removes a shared image."""
    out = []
    for c in _containers():
        names = c.get("Names") or []
        if exclude_container in names:
            continue
        if (c.get("Image") or "") == image:
            out.extend(names)
    return out


def volume_users(volume: str, exclude_container: str) -> list:
    """Other containers mounting the same named volume."""
    out = []
    for c in _containers():
        names = c.get("Names") or []
        if exclude_container in names:
            continue
        cp = _podman("inspect", names[0], "--format",
                     "{{range .Mounts}}{{.Name}} {{end}}") if names else None
        if cp and cp.returncode == 0 and volume in cp.stdout.split():
            out.extend(names)
    return out


def volume_size(volume: str):
    cp = _podman("system", "df", "-v", "--format", "json")
    if not cp or cp.returncode != 0:
        return None
    try:
        data = json.loads(cp.stdout or "{}")
    except Exception:
        return None
    for rec in (data.get("Volumes") or []) if isinstance(data, dict) else []:
        if rec.get("VolumeName") == volume:
            try:
                return int(rec.get("Size") or 0)
            except (TypeError, ValueError):
                return None
    return None


# --------------------------------------------------------------------------- #
# the manifest
# --------------------------------------------------------------------------- #
@dataclass
class Step:
    order: int
    action: str            # stop | disable | rm_path | rm_container | rm_volume | reload
    target: str
    label: str
    tier: str = SOFTWARE
    size: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Manifest:
    key: str
    name: str
    ok: bool = True
    reason: str = ""                 # why removal is not offered, when ok is False
    steps: list = field(default_factory=list)
    kept: list = field(default_factory=list)          # {what, why}
    dependencies: list = field(default_factory=list)  # {what, breaks, options}
    notes: list = field(default_factory=list)
    token: str = ""

    def software_steps(self) -> list:
        return [s for s in self.steps if s.tier == SOFTWARE]

    def data_steps(self) -> list:
        return [s for s in self.steps if s.tier == DATA]

    def compute_token(self) -> str:
        """Binds an execution to the exact plan that was shown.

        The executor re-plans and compares. If anything about the item changed
        between the preview and the confirmation, the token differs and the
        operation is refused rather than carried out against a system that is no
        longer the one the user looked at.
        """
        body = json.dumps([s.to_dict() for s in self.steps], sort_keys=True)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {
            "key": self.key, "name": self.name, "ok": self.ok, "reason": self.reason,
            "steps": [s.to_dict() for s in self.steps],
            "software": [s.to_dict() for s in self.software_steps()],
            "data": [s.to_dict() for s in self.data_steps()],
            "kept": self.kept, "dependencies": self.dependencies,
            "notes": self.notes, "token": self.token,
        }


# --------------------------------------------------------------------------- #
# planning
# --------------------------------------------------------------------------- #
def _quadlet_for(unit: str) -> Path | None:
    """The single .container file behind a generated unit, or None.

    None when there is not exactly one. Two candidates means the app cannot say
    which file it would delete, and a removal it cannot describe exactly is a
    removal it does not offer.
    """
    stem = unit[:-len(".service")] if unit.endswith(".service") else unit
    if not QUADLET_DIR.is_dir():
        return None
    hits = [q for q in QUADLET_DIR.rglob("*.container") if q.stem == stem]
    return hits[0] if len(hits) == 1 else None


def _quadlet_volumes(quadlet: Path) -> tuple:
    """(named volumes, host bind sources) declared by a quadlet."""
    named, binds = [], []
    try:
        text = quadlet.read_text(errors="replace")
    except OSError:
        return named, binds
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("Volume="):
            continue
        source = line[len("Volume="):].split(":", 1)[0].strip()
        source = source.replace("%h", str(HOME))
        if source.startswith("/"):
            binds.append(source)
        elif source.endswith(".volume"):
            named.append(source[:-len(".volume")])
        elif source:
            named.append(source)
    return named, binds


def plan_container_service(entry: dict) -> Manifest:
    """A manifest for one quadlet-defined container service.

    entry is a record from containers.discover(), so this shares the discovery
    the rest of the app already uses instead of enumerating podman a second time.
    """
    unit = entry.get("unit") or ""
    name = entry.get("name") or unit
    container = entry.get("container") or ""
    m = Manifest(key=entry.get("key") or unit, name=name)

    if in_flatpak() or not shutil.which("podman"):
        m.ok = False
        m.reason = ("Removing services needs Podman, which this build has no "
                    "access to.")
        return m

    if is_own_path(QUADLET_DIR / f"{container}.container"):
        m.ok = False
        m.reason = "This app does not remove itself."
        return m

    quadlet = _quadlet_for(unit)
    if quadlet is None:
        m.ok = False
        m.reason = (f"{name} has no single quadlet file this app can point to, "
                    f"so it cannot describe exactly what it would delete.")
        return m

    # A pod member is not a single-container service. Its siblings would be left
    # half removed, which is worse than not offering the button.
    inspect = _podman("inspect", container, "--format", "{{.Pod}}")
    if inspect and inspect.returncode == 0 and inspect.stdout.strip():
        m.ok = False
        m.reason = (f"{name} is part of a pod of several containers. This app "
                    f"removes single-container services only.")
        return m

    order = 0

    def step(action, target, label, tier=SOFTWARE, size=None):
        nonlocal order
        order += 1
        m.steps.append(Step(order, action, target, label, tier, size))

    # Order matters: stop the unit before its files go, remove the container
    # before the quadlet that defines it, reload systemd before anything reads
    # unit state again.
    step("stop", unit, f"Stop {name}")
    step("rm_container", container, f"Remove the container {container}")

    qpath = validate_path(quadlet)
    if qpath is None:
        m.ok = False
        m.reason = (f"The quadlet file for {name} is not in a location this app "
                    f"will delete from.")
        return m
    step("rm_path", str(qpath), f"Delete {qpath}",
         size=qpath.stat().st_size if qpath.exists() else None)
    step("reload", "", "Reload systemd so the unit stops existing")
    # Without this the unit lingers in a failed state after its file is gone,
    # which is exactly the stale reference a clean removal is supposed to avoid.
    step("reset_failed", unit, f"Clear the leftover systemd state for {unit}")

    # Config, cache, launcher and icon, only on an exact name match and only
    # when they actually exist. Each is listed with its full path, because the
    # user is the one deciding whether that directory is really this service's.
    for base, kind in ((HOME / ".config", "configuration"),
                       (HOME / ".cache", "cache")):
        for candidate in {container, quadlet.stem}:
            d = base / candidate
            vp = validate_path(d)
            if vp and not is_own_path(vp):
                step("rm_path", str(vp), f"Delete the {kind} folder {vp}")
    for candidate in {container, quadlet.stem}:
        desktop = APPS_DIR / f"{candidate}.desktop"
        vp = validate_path(desktop)
        if vp and not is_own_path(vp):
            step("rm_path", str(vp), f"Delete the launcher entry {vp}")
        for icons in ICON_DIRS:
            if not icons.is_dir():
                continue
            for icon in icons.rglob(f"{candidate}.*"):
                vp = validate_path(icon)
                if vp and not is_own_path(vp):
                    step("rm_path", str(vp), f"Delete the icon {vp}")

    named, binds = _quadlet_volumes(quadlet)

    # The image is never removed. Even unshared, it is a download that other
    # things may want and removing it is not needed to remove this service.
    image = entry.get("image") or ""
    if image:
        others = image_users(image, container)
        m.kept.append({
            "what": f"The container image {image}",
            "why": (f"It is also used by {', '.join(others)}."
                    if others else
                    "Images are shared downloads, so this app never removes one "
                    "as part of removing a service."),
        })

    for host_path in binds:
        m.kept.append({
            "what": host_path,
            "why": ("This is a folder of yours that the service was reading. "
                    "It is outside the service and is left alone."),
        })

    for vol in named:
        others = volume_users(vol, container)
        if others:
            m.kept.append({
                "what": f"The volume {vol}",
                "why": f"It is also mounted by {', '.join(others)}, so it stays.",
            })
            continue
        size = volume_size(vol)
        step("rm_volume", vol,
             f"Permanently delete the volume {vol}, including everything in it",
             DATA, size)

    m.token = m.compute_token()
    return m


# --------------------------------------------------------------------------- #
# execution
# --------------------------------------------------------------------------- #
def _rm_validated(target: str) -> tuple:
    """Delete one already-validated path, re-validating first.

    Re-validation is not redundant. The preview may be minutes old, and between
    then and now the path could have become a symlink pointing somewhere else.
    A path that no longer validates stops the operation rather than being
    deleted on the strength of an older check.
    """
    p = Path(target)
    if not p.exists() and not p.is_symlink():
        return True, "already gone"
    if is_own_path(p):
        return False, "refused: this belongs to the app itself"
    vp = validate_path(p)
    if vp is None:
        return False, "refused: no longer a path this app may delete"
    try:
        if vp.is_symlink() or vp.is_file():
            vp.unlink()
        elif vp.is_dir():
            shutil.rmtree(vp)
        else:
            return False, "refused: not a regular file or directory"
    except OSError as exc:
        return False, f"{exc.strerror or exc}"
    return True, "removed"


def _run_step(step: Step) -> tuple:
    """(ok, detail). A step whose target is already gone counts as done."""
    if step.action == "stop":
        cp = run_systemctl("stop", step.target)
        if cp.returncode != 0 and "not loaded" not in (cp.stderr or ""):
            return False, (cp.stderr or "").strip() or "systemctl stop failed"
        return True, "stopped"

    if step.action == "rm_container":
        cp = _podman("container", "exists", step.target)
        if cp is None:
            return False, "podman is not available"
        if cp.returncode != 0:
            return True, "already gone"
        rm = _podman("rm", "-f", step.target, timeout=60)
        if rm is None or rm.returncode != 0:
            return False, (rm.stderr or "").strip() if rm else "podman rm failed"
        return True, "removed"

    if step.action == "rm_path":
        return _rm_validated(step.target)

    if step.action == "reset_failed":
        run_systemctl("reset-failed", step.target)
        return True, "cleared"          # nothing to clear is a fine outcome

    if step.action == "reload":
        cp = run_systemctl("daemon-reload")
        return cp.returncode == 0, "reloaded" if cp.returncode == 0 else "reload failed"

    if step.action == "rm_volume":
        cp = _podman("volume", "exists", step.target)
        if cp is None:
            return False, "podman is not available"
        if cp.returncode != 0:
            return True, "already gone"
        rm = _podman("volume", "rm", step.target, timeout=120)
        if rm is None or rm.returncode != 0:
            return False, (rm.stderr or "").strip() if rm else "podman volume rm failed"
        return True, "removed"

    return False, f"unknown action {step.action}"


def execute(manifest: Manifest, token: str, include_data: bool, replan=None,
            progress=None) -> dict:
    """Carry out a manifest, stopping at the first failure.

    `token` must match a freshly computed plan. If the system changed between
    the preview and the confirmation, the plan the user approved is not the plan
    that would run, so nothing runs.

    Data steps are performed only when include_data is true. That flag comes
    from its own confirmation and is never implied by approving the software
    removal.
    """
    if not manifest.ok:
        return {"ok": False, "done": [], "failed": None,
                "detail": manifest.reason, "remaining": []}

    if replan is not None:
        fresh = replan()
        if fresh is None or not fresh.ok or fresh.compute_token() != token:
            return {
                "ok": False, "done": [], "remaining": [s.to_dict() for s in manifest.steps],
                "failed": None,
                "detail": ("This changed since the preview, so nothing was removed. "
                           "Open the preview again to see the current plan."),
            }
        manifest = fresh

    if token != manifest.compute_token():
        return {"ok": False, "done": [], "failed": None, "remaining": [],
                "detail": "The confirmation did not match the preview, so nothing was removed."}

    planned = [s for s in manifest.steps
               if s.tier == SOFTWARE or (include_data and s.tier == DATA)]
    skipped = [s for s in manifest.steps if s.tier == DATA and not include_data]

    done, failed = [], None
    for i, step in enumerate(planned):
        if progress:
            progress(i, len(planned), step.label)
        ok, detail = _run_step(step)
        if not ok:
            failed = {"step": step.to_dict(), "detail": detail}
            break
        done.append({"step": step.to_dict(), "detail": detail})

    remaining = [s.to_dict() for s in planned[len(done) + (1 if failed else 0):]]
    return {
        "ok": failed is None,
        "done": done,
        "failed": failed,
        "remaining": remaining,
        "kept": manifest.kept + [
            {"what": s.label, "why": "Your data was not included in this removal."}
            for s in skipped
        ],
        "detail": ("Removed." if failed is None else
                   "Stopped at the first step that failed. Nothing after it was attempted."),
    }

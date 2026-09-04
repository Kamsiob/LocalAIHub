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
# Deliberately narrow. ~/.config and ~/.cache are NOT here: a container named
# "containers" resolves to ~/.config/containers, which holds the quadlet files
# for every service on the machine, and a container named after any desktop
# application resolves to that application's configuration. The app cannot prove
# it owns anything under those trees, so it does not delete there at all.
ALLOWED_ROOTS = [QUADLET_DIR, UNIT_DIR]

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

    # Containment by name is not containment on disk. shutil.rmtree recurses
    # into a mounted filesystem and destroys its contents before failing on the
    # final rmdir, so a bind mount or a symlinked root under an allowed root
    # would take data living on another device entirely. hub/sizes.py already
    # guards its read-only walk this way; the destructive path needs it more.
    try:
        home_dev = HOME.stat().st_dev
        if resolved.lstat().st_dev != home_dev:
            return None
    except OSError:
        return None

    for root in roots:
        try:
            rroot = root.resolve(strict=True)
            if rroot.stat().st_dev != home_dev:
                continue                    # a root that resolves off-device
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
    """True if p is, contains, or is contained by anything belonging to the app.

    The ancestor direction matters as much as the descendant one: deleting a
    directory that happens to contain the running app removes the app just as
    thoroughly as deleting the app itself.
    """
    resolved = _norm(p)
    for own in app_own_paths():
        if resolved == own:
            return True
        if resolved.startswith(own.rstrip("/") + "/"):
            return True
        if own.startswith(resolved.rstrip("/") + "/"):
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
    """Other containers built on the same image. The image is never removed
    either way, so this is disclosure rather than a safety decision."""
    out = []
    for c in _containers():
        names = c.get("Names") or []
        if exclude_container in names:
            continue
        if (c.get("Image") or "") == image:
            out.extend(names)
    return out


def volume_users(volume: str, exclude_container: str) -> tuple:
    """(other containers mounting this volume, whether that could be determined).

    Fails closed. A podman command that errors, times out, or is missing tells
    us nothing about who shares this volume, and "we could not ask" must never
    be read as "nobody else uses it". The caller keeps the volume in that case.
    """
    all_containers = _containers()
    if not all_containers:
        return [], False
    out = []
    for c in all_containers:
        names = c.get("Names") or []
        if not names or exclude_container in names:
            continue
        cp = _podman("inspect", names[0], "--format",
                     "{{range .Mounts}}{{.Name}} {{end}}")
        if cp is None or cp.returncode != 0:
            return [], False          # one unanswerable probe spoils the answer
        if volume in cp.stdout.split():
            out.extend(names)
    return out, True


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
            # A .volume quadlet's podman name is not simply the file stem, and
            # guessing it could name a different volume that belongs to
            # something else. Refuse rather than guess.
            binds.append("?" + source)
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
    # Fails closed: if podman cannot answer, the app does not know whether this
    # is a pod member, and removing one member of a pod leaves the rest half
    # configured.
    inspect = _podman("inspect", container, "--format", "{{.Pod}}")
    if inspect is None or inspect.returncode != 0:
        m.ok = False
        m.reason = (f"Podman could not say whether {name} is part of a pod, so "
                    f"this app will not remove it.")
        return m
    if inspect.stdout.strip():
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

    # No configuration, cache, launcher or icon is deleted. Those were matched
    # by name, which is a guess: the app never reads anything saying the service
    # owns ~/.config/<name>. A container named after a desktop application would
    # take that application's configuration, and one named "containers" would
    # take every quadlet on the machine. They are reported instead, so the user
    # can look and decide, which is the part the app can honestly do.
    for base, kind in ((HOME / ".config", "configuration"),
                       (HOME / ".cache", "cache")):
        for candidate in {container, quadlet.stem}:
            d = base / candidate
            if d.is_dir() and not is_own_path(d):
                m.kept.append({
                    "what": str(d),
                    "why": (f"This looks like it could be {name}'s {kind}, but "
                            f"nothing says so, so it is left alone. Remove it "
                            f"yourself if you know it belongs to this service."),
                })
    for candidate in {container, quadlet.stem}:
        desktop = APPS_DIR / f"{candidate}.desktop"
        if desktop.exists() and not is_own_path(desktop):
            m.kept.append({
                "what": str(desktop),
                "why": ("A launcher entry with a matching name. Left alone, "
                        "because a matching name is not proof of ownership."),
            })

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
        if host_path.startswith("?"):
            m.kept.append({
                "what": host_path[1:],
                "why": ("This is declared through a .volume file, and the app "
                        "cannot be certain which podman volume that names, so "
                        "it is left alone."),
            })
            continue
        m.kept.append({
            "what": host_path,
            "why": ("This is a folder of yours that the service was reading. "
                    "It is outside the service and is left alone."),
        })

    for vol in named:
        others, determined = volume_users(vol, container)
        if not determined:
            m.kept.append({
                "what": f"The volume {vol}",
                "why": ("Podman could not say whether anything else uses this "
                        "volume, so it is left alone."),
            })
            continue
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
        # rmtree deletes depth first, so a failure partway means part of the
        # tree is already gone. Saying only "Device or resource busy" would
        # leave the user believing nothing happened here.
        still = vp.exists()
        note = (" Part of this may already have been deleted."
                if still and vp.is_dir() else "")
        return False, f"{exc.strerror or exc}.{note}"
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
            return False, "podman did not answer, so nothing was changed"
        # `exists` returns 1 for absent and 125 for a storage error. Only the
        # first means the work is already done.
        if cp.returncode == 125:
            return False, "podman reported a storage error"
        if cp.returncode != 0:
            return True, "already gone"
        rm = _podman("rm", "-f", step.target, timeout=60)
        if rm is None or rm.returncode != 0:
            return False, (rm.stderr or "").strip() if rm else "podman rm failed"
        return True, "removed"

    if step.action == "rm_model":
        from .services.ollama import OllamaService
        try:
            OllamaService().remove_model(step.target)
        except Exception as exc:
            return False, str(exc)
        return True, "removed"

    if step.action == "rm_path":
        return _rm_validated(step.target)

    if step.action == "reset_failed":
        # Nothing to clear is a fine outcome, so this reports what happened
        # rather than asserting success it did not verify.
        cp = run_systemctl("reset-failed", step.target)
        return True, "cleared" if cp.returncode == 0 else "nothing to clear"

    if step.action == "reload":
        cp = run_systemctl("daemon-reload")
        return cp.returncode == 0, "reloaded" if cp.returncode == 0 else "reload failed"

    if step.action == "rm_volume":
        cp = _podman("volume", "exists", step.target)
        if cp is None:
            return False, "podman did not answer, so nothing was changed"
        if cp.returncode == 125:
            return False, "podman reported a storage error"
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
        try:
            ok, detail = _run_step(step)
        except Exception as exc:  # noqa: BLE001
            # An exception must not discard the record of what already ran. A
            # user told "nothing was removed" about a half-finished removal
            # cannot recover from it.
            ok, detail = False, f"stopped unexpectedly: {exc}"
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


def plan_ollama_model(name: str, size: int | None, resident: bool,
                      ollama_active: bool, dep: dict) -> Manifest:
    """A manifest for one Ollama model.

    A model is software rather than data: it is a download that can be fetched
    again by name. It still gets a full preview with its size, because 20 GB
    over a slow link is a real cost even when it is recoverable.
    """
    m = Manifest(key=f"ollama:{name}", name=name)
    if not ollama_active:
        m.ok = False
        m.reason = "Ollama is stopped, so its models cannot be removed. Start it to manage them."
        return m
    if resident is None:
        m.ok = False
        m.reason = ("Ollama did not say what is in memory, so this app cannot "
                    "tell whether this model is in use. It will not remove it "
                    "until it can.")
        return m
    if resident:
        m.ok = False
        m.reason = ("This model is in memory right now. Release it first, then "
                    "it can be removed.")
        return m

    m.steps.append(Step(1, "rm_model", name, f"Remove the model {name}", SOFTWARE, size))

    for c in dep.get("consumers", []):
        m.dependencies.append({
            "what": c["name"],
            "breaks": c["detail"],
            "options": (["Point it at a different installed model first",
                         "Remove the model anyway and reconfigure later"]
                        if c.get("repointable") else []),
        })
    for u in dep.get("unknown", []):
        m.dependencies.append({
            "what": u["name"], "breaks": u["detail"],
            "options": ["Treat this as risky: the app could not check it"],
        })
    users = dep.get("endpoint_users") or []
    if users:
        verb = "points" if len(users) == 1 else "point"
        m.notes.append(
            f"{', '.join(users)} {verb} at Ollama rather than at this model, so "
            f"{'it keeps' if len(users) == 1 else 'they keep'} working. "
            f"{'It' if len(users) == 1 else 'They'} will simply stop listing it.")
    m.token = m.compute_token()
    return m


def plan_comfy_model(path: str, models_root: Path, size, busy, gguf: dict) -> Manifest:
    """Not offered in 2.0. This returns a refusal, deliberately.

    Two reasons, and either alone would be enough. An Ollama model can always be
    fetched again by name; a ComfyUI model file often cannot, because a file
    pulled from a direct link or a gallery may have no recorded source to get it
    back from, which makes deleting one closer to deleting data than to
    uninstalling software. And the first version of this planner validated
    against the models folder while the executor validated against a different
    set of roots, so every deletion would have been promised in the preview and
    then refused at execution. A preview that cannot be honored is worse than no
    button.

    Sizes for these files are still shown. Only the deletion is withheld.
    """
    m = Manifest(key=f"comfy:{path}", name=Path(path).name)
    m.ok = False
    m.reason = ("Removing ComfyUI model files isn't offered yet. Some have no "
                "recorded source to download them again from, so deleting one "
                "can be permanent in a way that removing an Ollama model is "
                "not. You can delete the file yourself if you are sure.")
    return m

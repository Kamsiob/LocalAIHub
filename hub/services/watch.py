"""Notice when a tool is installed or removed, without polling for it.

The app already re-reads every service on a 5-second timer, which keeps *status*
(running, starting, crashed) live. That timer is a poor fit for install and
uninstall: those are rare, and reacting to them within five seconds is not worth
five seconds of rescanning forever. So this module watches for the two events
that actually mean "a tool appeared or disappeared" and reconciles on the edge,
leaving the periodic scan in place purely as a safety net.

Two mechanisms, both event-driven:

  systemd over D-Bus  — Subscribe() to the user manager, then listen for
      UnitNew / UnitRemoved / Reloading / JobRemoved. Covers units appearing and
      vanishing, which is how Ollama and the Open WebUI quadlet come and go. Runs
      in every build: the session bus is reachable natively and the Flatpak build
      already holds --talk-name=org.freedesktop.systemd1 for start/stop.

  QFileSystemWatcher  — inotify on the directories that hold the things whose
      existence defines "installed": ComfyUI's folder, ~/.config/systemd/user,
      and ~/.config/containers/systemd. Covers installs that never touch systemd
      at all, which is exactly the case that used to go unnoticed — a ComfyUI
      folder deleted and restored by hand.

Both funnel into one debounced `changed` signal, because an install typically
trips several watches at once (a unit file written, a directory created, a job
run) and the app only needs to reconcile once.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import SLOT, QObject, QTimer, Signal, Slot

_SYSTEMD = "org.freedesktop.systemd1"
_MANAGER_PATH = "/org/freedesktop/systemd1"
_MANAGER_IFACE = "org.freedesktop.systemd1.Manager"

# systemd churns through transient units (per-command scopes, session slices)
# constantly; reacting to every one of them would be the polling this module
# exists to avoid. Signals are kept only when they name a unit we manage.
_DEBOUNCE_MS = 700


class ChangeWatcher(QObject):
    """Emits `changed(reason)` when a managed tool may have been installed or
    removed. The reason string is for the log/report, not for the UI."""

    changed = Signal(str)

    def __init__(self, services: dict, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._services = services
        self._unit_names = set()
        for svc in services.values():
            unit = getattr(svc, "unit", "")
            if unit:
                self._unit_names.add(unit)
                self._unit_names.add(unit if unit.endswith(".service") else unit + ".service")

        self._reason = ""
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._fire)

        self._dbus_ok = False
        self._watched: set[str] = set()
        self._fs = None

        self._start_fs_watch()
        self._start_dbus_watch()

    # --- what actually armed, for the About panel and the release notes ------
    def mechanisms(self) -> dict:
        return {
            "systemd_dbus": self._dbus_ok,
            "filesystem": bool(self._watched),
            "watched_paths": sorted(self._watched),
        }

    # --- filesystem ----------------------------------------------------------
    def _watch_targets(self) -> set[Path]:
        """Directories whose contents decide whether a tool is installed.

        A directory is watched rather than a file because inotify on a path that
        does not exist yet is not possible — watching the parent is what lets an
        *appearing* ComfyUI folder or unit file register at all.
        """
        home = Path.home()
        # Where units and quadlets are written by hand — an install that adds a
        # unit file shows up here before systemd has been told about it.
        targets: set[Path] = {
            home / ".config" / "systemd" / "user",
            home / ".config" / "containers" / "systemd",
        }
        for svc in self._services.values():
            targets.update(svc.watch_dirs())
        return targets

    def _start_fs_watch(self) -> None:
        try:
            from PySide6.QtCore import QFileSystemWatcher
        except Exception:  # noqa: BLE001 - no Qt file watching available
            return
        self._fs = QFileSystemWatcher(self)
        self._fs.directoryChanged.connect(self._on_dir_changed)
        self._rearm_fs()

    def _rearm_fs(self) -> None:
        """(Re)subscribe to the directories that currently exist.

        Called again after every change because the interesting transitions are
        precisely the ones that create or destroy a watched directory: installing
        ComfyUI creates ~/ComfyUI, and inotify does not follow that for you.
        """
        if self._fs is None:
            return
        want = {str(p) for p in self._watch_targets() if p.is_dir()}
        stale = self._watched - want
        if stale:
            self._fs.removePaths(sorted(stale))
        fresh = want - self._watched
        if fresh:
            failed = set(self._fs.addPaths(sorted(fresh)))
            fresh -= failed
        self._watched = (self._watched - stale) | fresh

    @Slot(str)
    def _on_dir_changed(self, path: str) -> None:
        self._queue(f"filesystem: {path}")

    # --- systemd over D-Bus --------------------------------------------------
    def _start_dbus_watch(self) -> None:
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusInterface
        except Exception:  # noqa: BLE001 - QtDBus unavailable in this build
            return
        try:
            bus = QDBusConnection.sessionBus()
            if not bus.isConnected():
                return
            # Without Subscribe() the manager stays quiet for UnitNew/UnitRemoved.
            QDBusInterface(_SYSTEMD, _MANAGER_PATH, _MANAGER_IFACE, bus).call("Subscribe")
            # QDBusConnection.connect wants a receiver object plus a SLOT()
            # signature string; handing it a bound method raises, and handing it
            # a bare string loses the leading character Qt uses as the slot
            # marker. Both fail silently as "no signals ever arrive".
            ok = True
            for signal, slot in (
                ("UnitNew", "_on_unit_new(QString,QDBusObjectPath)"),
                ("UnitRemoved", "_on_unit_removed(QString,QDBusObjectPath)"),
                ("Reloading", "_on_reloading(bool)"),
                ("JobRemoved", "_on_job_removed(uint,QDBusObjectPath,QString,QString)"),
            ):
                ok &= bus.connect(_SYSTEMD, _MANAGER_PATH, _MANAGER_IFACE,
                                  signal, self, SLOT(slot))
            self._dbus_ok = ok
        except Exception:  # noqa: BLE001 - a bus failure must not break the app
            self._dbus_ok = False

    def _relevant(self, unit_id: str) -> bool:
        return unit_id in self._unit_names

    @Slot(str, "QDBusObjectPath")
    def _on_unit_new(self, unit_id: str, _path) -> None:
        if self._relevant(unit_id):
            self._queue(f"systemd: {unit_id} appeared")

    @Slot(str, "QDBusObjectPath")
    def _on_unit_removed(self, unit_id: str, _path) -> None:
        if self._relevant(unit_id):
            self._queue(f"systemd: {unit_id} removed")

    @Slot(bool)
    def _on_reloading(self, active: bool) -> None:
        # Fires false when a daemon-reload finishes, which is when newly written
        # or deleted unit files become real as far as systemd is concerned.
        if not active:
            self._queue("systemd: daemon-reload finished")

    @Slot("uint", "QDBusObjectPath", str, str)
    def _on_job_removed(self, _job_id, _path, unit_id: str, _result: str) -> None:
        if self._relevant(unit_id):
            self._queue(f"systemd: job finished on {unit_id}")

    # --- debounce ------------------------------------------------------------
    def _queue(self, reason: str) -> None:
        self._reason = reason
        self._debounce.start()

    def _fire(self) -> None:
        self._rearm_fs()
        self.changed.emit(self._reason)

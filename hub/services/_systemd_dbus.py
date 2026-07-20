"""Control systemd --user units over the session bus (for the Flatpak sandbox).

Inside a Flatpak there is no `systemctl`/`journalctl` binary, but the host user
systemd manager is reachable on the session bus at org.freedesktop.systemd1.
This module mirrors the handful of operations base.Service needs — start/stop/
restart, the status properties (ActiveState/SubState/LoadState/Result), and the
unit-file state — using QtDBus, which PySide6 already provides. No new dependency.

It is used ONLY when running inside Flatpak (FLATPAK_ID set). Native and AppImage
builds keep using the systemctl CLI, so nothing here changes those paths.

Note on crash detection: the "stopped unexpectedly" state is derived from the
unit's ActiveState (== "failed") and Result properties, both read here over
D-Bus — so crash detection and its alert work fully under Flatpak. Only the log
*detail* view (journalctl) is unavailable in the sandbox.
"""
from __future__ import annotations

from typing import Optional

_SYSTEMD = "org.freedesktop.systemd1"
_MANAGER_PATH = "/org/freedesktop/systemd1"
_MANAGER_IFACE = "org.freedesktop.systemd1.Manager"
_UNIT_IFACE = "org.freedesktop.systemd1.Unit"
_SERVICE_IFACE = "org.freedesktop.systemd1.Service"
_PROPS_IFACE = "org.freedesktop.DBus.Properties"


_UNIT_SUFFIXES = (".service", ".socket", ".target", ".timer", ".mount",
                  ".scope", ".slice", ".path", ".device", ".automount", ".swap")


def _full(unit: str) -> str:
    """The systemd D-Bus API wants a full unit name; the app uses bare names like
    "ollama" (the systemctl CLI auto-appends .service, the bus API does not)."""
    return unit if unit.endswith(_UNIT_SUFFIXES) else unit + ".service"


def _bus():
    from PySide6.QtDBus import QDBusConnection
    return QDBusConnection.sessionBus()


def _iface(path: str, interface: str):
    from PySide6.QtDBus import QDBusInterface
    return QDBusInterface(_SYSTEMD, path, interface, _bus())


def _ok(msg) -> bool:
    from PySide6.QtDBus import QDBusMessage
    return msg.type() != QDBusMessage.MessageType.ErrorMessage


def _unwrap(val):
    """Unwrap a QDBusVariant (what Properties.Get returns) to a plain value."""
    var = getattr(val, "variant", None)
    if callable(var):
        try:
            return var()
        except Exception:
            return val
    return val


# --- control ---------------------------------------------------------------- #
def _manager_call(method: str, *args) -> bool:
    return _ok(_iface(_MANAGER_PATH, _MANAGER_IFACE).call(method, *args))


def start_unit(unit: str) -> bool:
    return _manager_call("StartUnit", _full(unit), "replace")


def stop_unit(unit: str) -> bool:
    return _manager_call("StopUnit", _full(unit), "replace")


def restart_unit(unit: str) -> bool:
    return _manager_call("RestartUnit", _full(unit), "replace")


# --- queries ---------------------------------------------------------------- #
def _unit_path(unit: str) -> Optional[str]:
    # LoadUnit returns the object path even for an inactive or not-found unit
    # (the returned unit then has LoadState=not-found), mirroring `systemctl show`.
    msg = _iface(_MANAGER_PATH, _MANAGER_IFACE).call("LoadUnit", _full(unit))
    if not _ok(msg):
        return None
    args = msg.arguments()
    if not args:
        return None
    # LoadUnit returns a QDBusObjectPath — use .path(), not str() (which is a repr).
    obj = args[0]
    return obj.path() if hasattr(obj, "path") else str(obj)


def _get_prop(path: str, interface: str, prop: str) -> str:
    msg = _iface(path, _PROPS_IFACE).call("Get", interface, prop)
    if not _ok(msg):
        return ""
    args = msg.arguments()
    if not args:
        return ""
    val = _unwrap(args[0])
    return "" if val is None else str(val)


def unit_status(unit: str) -> dict:
    """Return {ActiveState, SubState, LoadState, Result} like `systemctl show`."""
    path = _unit_path(unit)
    if not path:
        return {"ActiveState": "", "SubState": "", "LoadState": "not-found", "Result": ""}
    return {
        "ActiveState": _get_prop(path, _UNIT_IFACE, "ActiveState"),
        "SubState": _get_prop(path, _UNIT_IFACE, "SubState"),
        "LoadState": _get_prop(path, _UNIT_IFACE, "LoadState"),
        "Result": _get_prop(path, _SERVICE_IFACE, "Result"),
    }


def unit_file_state(unit: str) -> Optional[str]:
    msg = _iface(_MANAGER_PATH, _MANAGER_IFACE).call("GetUnitFileState", _full(unit))
    if not _ok(msg):
        return None
    args = msg.arguments()
    return str(args[0]) if args else None

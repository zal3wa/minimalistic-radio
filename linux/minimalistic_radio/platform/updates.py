"""Updates through the Flatpak portal: a green arrow when a newer version is on Flathub or already installed.

The portal gives no version number, so the labels carry none. Any portal failure is ignored: no arrow.
"""
from __future__ import annotations

import os
from typing import Callable

try:
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
except (ImportError, ValueError):   # the pure part is tested where PyGObject is missing
    Gio = GLib = None

PORTAL = "org.freedesktop.portal.Flatpak"
PORTAL_PATH = "/org/freedesktop/portal/Flatpak"
MONITOR_IFACE = "org.freedesktop.portal.Flatpak.UpdateMonitor"
LATEST_VERSION = 2   # Spawn flag: start the newest installed version
STATUS_RUNNING, STATUS_EMPTY, STATUS_DONE, STATUS_ERROR = 0, 1, 2, 3   # Progress: EMPTY = nothing to install
TIMEOUT_MS = 3000


def update_state(info: dict[str, str]) -> str | None:
    """"restart": the new version is installed already; "update": it is only on the remote."""
    running, local, remote = info.get("running-commit"), info.get("local-commit"), info.get("remote-commit")
    if local and local != running:
        return "restart"
    if remote and remote != running and remote != local:
        return "update"
    return None


class UpdateMonitor:
    def __init__(self, app, flatpak_info: str = "/.flatpak-info") -> None:
        self.app = app
        self.flatpak_info = flatpak_info
        self.state: str | None = None
        self.monitor: str | None = None   # the portal's monitor object, once created
        self.checked = False              # the start-up conversation with the portal is over
        self._bus = None
        self._updating = False
        self._listeners: list[Callable[[str | None], None]] = []

    def connect_changed(self, listener: Callable[[str | None], None]) -> None:
        self._listeners.append(listener)

    def _set_state(self, state: str | None) -> None:
        if state != self.state:
            self.state = state
            for listener in self._listeners:
                listener(state)

    def start(self) -> None:
        if not os.path.exists(self.flatpak_info) or Gio is None:
            self.checked = True
            return
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self._bus.call(PORTAL, PORTAL_PATH, "org.freedesktop.DBus.Properties", "Get",
                           GLib.Variant("(ss)", (PORTAL, "version")), GLib.VariantType("(v)"),
                           Gio.DBusCallFlags.NONE, TIMEOUT_MS, None, self._version_known)
        except Exception:
            self.checked = True

    def _version_known(self, bus, result, _data=None) -> None:
        try:
            version = bus.call_finish(result).unpack()[0]
            if not isinstance(version, int) or version < 2:
                raise ValueError("the portal is too old")
            bus.call(PORTAL, PORTAL_PATH, PORTAL, "CreateUpdateMonitor", GLib.Variant("(a{sv})", ({},)),
                     GLib.VariantType("(o)"), Gio.DBusCallFlags.NONE, TIMEOUT_MS, None, self._monitor_created)
        except Exception:
            self.checked = True

    def _monitor_created(self, bus, result, _data=None) -> None:
        try:
            path = bus.call_finish(result).unpack()[0]
            bus.signal_subscribe(PORTAL, MONITOR_IFACE, None, path, None, Gio.DBusSignalFlags.NONE,
                                 self._signal)
            self.monitor = path
        except Exception:
            pass
        self.checked = True

    def _signal(self, _bus, _sender, _path, _iface, name, params, _data=None) -> None:
        info = params.unpack()[0]
        if name == "UpdateAvailable":
            self._set_state(update_state({k: v for k, v in info.items() if isinstance(v, str)}))
        elif name == "Progress" and self._updating:
            status = info.get("status", STATUS_RUNNING)
            if status == STATUS_RUNNING:
                return
            self._updating = False   # whatever the end, the arrow works again
            if status in (STATUS_EMPTY, STATUS_DONE):
                self._restart()      # EMPTY: the new version was installed already, e.g. by GNOME Software
            else:
                self._failed()

    def apply(self) -> None:
        """"Update" downloads and installs, then restarts; "Restart to update" only restarts."""
        if self.state == "restart":
            self._restart()
        elif self.state == "update" and self.monitor and not self._updating:
            self._updating = True
            try:
                self._bus.call(PORTAL, self.monitor, MONITOR_IFACE, "Update", GLib.Variant("(sa{sv})", ("", {})),
                               None, Gio.DBusCallFlags.NONE, TIMEOUT_MS, None, self._update_called)
            except Exception:
                self._updating = False
                self._failed()

    def _update_called(self, bus, result, _data=None) -> None:
        try:
            bus.call_finish(result)
        except Exception:
            self._updating = False
            self._failed()

    def _failed(self) -> None:
        window = self.app.window
        if window is not None:
            window.toast(self.app._("Couldn't update. Try again later."))

    def _restart(self) -> None:
        """The newest installed version, through the portal; this one quits once it is on its way."""
        argv = ["minimalistic-radio", "--updated"]
        controller = self.app.controller
        if controller is None or not controller.active:
            argv.append("--autostart")
        try:
            cwd = os.getcwd().encode() + b"\0"
            self._bus.call(PORTAL, PORTAL_PATH, PORTAL, "Spawn",
                           GLib.Variant("(ayaaya{uh}a{ss}ua{sv})",
                                        (cwd, [a.encode() + b"\0" for a in argv], {}, {}, LATEST_VERSION, {})),
                           None, Gio.DBusCallFlags.NONE, TIMEOUT_MS, None, self._spawned)
        except Exception:
            self._failed()

    def _spawned(self, bus, result, _data=None) -> None:
        try:
            bus.call_finish(result)
        except Exception:
            self._failed()
            return
        self.app.quit()

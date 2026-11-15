"""Resume from sleep and the network coming back, passed to the controller.

Both are debounced: the network often flaps several times when it returns.
"""
from __future__ import annotations

from typing import Any

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

DEBOUNCE_MS = 2000


class SessionWatcher:
    def __init__(self, controller: Any, monitor: Gio.NetworkMonitor | None = None) -> None:
        self.controller = controller
        self._pending: dict[str, int] = {}
        self._monitor = monitor if monitor is not None else Gio.NetworkMonitor.get_default()
        self._monitor_id = self._monitor.connect("network-changed", self._network_changed)
        self._bus: Gio.DBusConnection | None = None
        self._sleep_id = 0
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            self._sleep_id = self._bus.signal_subscribe(
                "org.freedesktop.login1", "org.freedesktop.login1.Manager", "PrepareForSleep",
                "/org/freedesktop/login1", None, Gio.DBusSignalFlags.NONE, self._prepare_for_sleep)
        except GLib.Error:
            self._bus = None   # no system bus (a container): resume is simply not noticed

    def _prepare_for_sleep(self, _bus, _sender, _path, _iface, _signal, params) -> None:
        if not params.unpack()[0]:
            self._later("resume", self.controller.resumed)

    def _network_changed(self, _monitor, available: bool) -> None:
        if available:
            self._later("network", self.controller.network_available)

    def _later(self, key: str, call) -> None:
        if key in self._pending:
            return

        def fire() -> bool:
            self._pending.pop(key, None)
            call()
            return GLib.SOURCE_REMOVE
        self._pending[key] = GLib.timeout_add(DEBOUNCE_MS, fire)

    def close(self) -> None:
        for source in self._pending.values():
            GLib.source_remove(source)
        self._pending.clear()
        self._monitor.disconnect(self._monitor_id)
        if self._bus is not None and self._sleep_id:
            self._bus.signal_unsubscribe(self._sleep_id)
            self._sleep_id = 0

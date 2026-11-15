"""Resume from sleep and the network coming back, passed to the controller.

Both are debounced: the network often flaps several times when it returns. Resume comes from logind
(development runs and the Snap); the Flatpak has no access to it, and there the network going down and
up across a suspend brings the radio back instead.
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
        self._network_timer = 0
        self._was_down = False   # the network was lost since it last settled (networkWasDown on Windows)
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
        """Every change starts the wait again (OnNetworkChanged on Windows)."""
        if not available:
            self._was_down = True
        if self._network_timer:
            GLib.source_remove(self._network_timer)
        self._network_timer = GLib.timeout_add(DEBOUNCE_MS, self._network_settled)

    def _network_settled(self) -> bool:
        """NetworkSettled on Windows: a playing station restarts only if the network was down in between."""
        self._network_timer = 0
        if not self._monitor.get_network_available():
            self._was_down = True
        else:
            was_down, self._was_down = self._was_down, False
            self.controller.network_available(was_down)
        return GLib.SOURCE_REMOVE

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
        if self._network_timer:
            GLib.source_remove(self._network_timer)
            self._network_timer = 0
        self._monitor.disconnect(self._monitor_id)
        if self._bus is not None and self._sleep_id:
            self._bus.signal_unsubscribe(self._sleep_id)
            self._sleep_id = 0

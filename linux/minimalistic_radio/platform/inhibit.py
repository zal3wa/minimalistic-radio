"""Keeps the computer from suspending while the radio plays, through xdg-desktop-portal.

Not Gtk.Application.inhibit(): its session-manager path crashes where there is no session manager.
Any failure is logged once and then ignored.
"""
from __future__ import annotations

import sys
from typing import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from .. import APP_NAME  # noqa: E402

PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SUSPEND = 4
TIMEOUT_MS = 3000


class SuspendInhibitor:
    def __init__(self, translate: Callable[[str], str] = lambda s: s) -> None:
        self._ = translate
        self._wanted = False
        self._pending = False     # an Inhibit call is on its way
        self._request: str | None = None
        self._warned = False

    def _warn(self, text: str) -> None:
        if not self._warned:
            self._warned = True
            print(f"{APP_NAME}: couldn't inhibit suspend: {text}", file=sys.stderr)

    def hold(self) -> None:
        self._wanted = True
        if self._request is not None or self._pending:
            return
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            options = {"reason": GLib.Variant("s", self._("Playing internet radio"))}
            self._pending = True
            bus.call(PORTAL, PORTAL_PATH, "org.freedesktop.portal.Inhibit", "Inhibit",
                     GLib.Variant("(sua{sv})", ("", SUSPEND, options)), GLib.VariantType("(o)"),
                     Gio.DBusCallFlags.NONE, TIMEOUT_MS, None, self._held, bus)
        except Exception as error:
            self._pending = False
            self._warn(str(error))

    def _held(self, bus: Gio.DBusConnection, result: Gio.AsyncResult, _data=None) -> None:
        self._pending = False
        try:
            path = bus.call_finish(result).unpack()[0]
        except Exception as error:
            self._warn(str(error))
            return
        if self._wanted:
            self._request = path
        else:
            self._close(bus, path)   # playback ended while the call was on its way

    def release(self) -> None:
        self._wanted = False
        path, self._request = self._request, None
        if path is None:
            return
        try:
            self._close(Gio.bus_get_sync(Gio.BusType.SESSION, None), path)
        except Exception as error:
            self._warn(str(error))

    def _close(self, bus: Gio.DBusConnection, path: str) -> None:
        bus.call(PORTAL, path, "org.freedesktop.portal.Request", "Close", None, None,
                 Gio.DBusCallFlags.NO_AUTO_START, TIMEOUT_MS, None, lambda *_args: None)

"""Start with the system. Flatpak asks the Background portal; Snap and the host write an autostart file.

The state is kept in the preference `Autostart`; the file (or the portal) is what makes it happen.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any

from .. import APP_ID, APP_NAME

COMMAND = "minimalistic-radio"
AUTOSTART_EXEC = COMMAND + " --autostart"
FLATPAK_INFO = "/.flatpak-info"
PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
REQUEST_IFACE = "org.freedesktop.portal.Request"
TIMEOUT_MS = 5000


def autostart_desktop_entry(exec_line: str) -> str:
    return ("[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={APP_NAME}\n"
            f"Exec={exec_line}\n"
            f"Icon={APP_ID}\n"
            "Terminal=false\n"
            "NoDisplay=true\n"
            "X-GNOME-Autostart-enabled=true\n")


def request_path(unique_name: str, token: str) -> str:
    """Where the portal answers a request made with `handle_token` = `token` (org.freedesktop.portal.Request)."""
    sender = unique_name.lstrip(":").replace(".", "_")
    return f"{PORTAL_PATH}/request/{sender}/{token}"


def _warn(text: str) -> None:
    print(f"{APP_NAME}: {text}", file=sys.stderr)


class Autostart:
    def __init__(self, controller: Any) -> None:
        self.controller = controller

    def enabled(self) -> bool:
        return self.controller.prefs.autostart

    def set(self, on: bool) -> None:
        if os.path.exists(FLATPAK_INFO):
            self._portal(on)   # the preference follows the portal's answer
        else:
            self._write_file(on)
            self.controller.set_autostart_preference(on)

    def _file(self) -> Path:
        snap_data = os.environ.get("SNAP_USER_DATA") if os.environ.get("SNAP") else None
        if snap_data:
            return Path(snap_data) / ".config" / "autostart" / (COMMAND + ".desktop")
        return Path.home() / ".config" / "autostart" / (APP_ID + ".desktop")

    def _write_file(self, on: bool) -> None:
        path = self._file()
        try:
            if on:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(autostart_desktop_entry(AUTOSTART_EXEC), encoding="utf-8")
            else:
                path.unlink(missing_ok=True)
        except OSError as error:
            _warn(f"couldn't update the autostart file: {error}")

    def _portal(self, on: bool) -> None:
        """Asks the Background portal. Its answer comes as a Response signal on the request's path, so that is
        subscribed to before the call. Only a granted "autostart" keeps the switch on; anything else turns it off."""
        subscriptions: list[int] = []
        try:
            import gi
            gi.require_version("Gio", "2.0")
            from gi.repository import Gio, GLib
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            token = "minimalistic_radio_" + uuid.uuid4().hex
            expected = request_path(bus.get_unique_name(), token)

            def finish(granted: bool) -> None:
                if not subscriptions:
                    return   # answered already
                for subscription in subscriptions:
                    bus.signal_unsubscribe(subscription)
                subscriptions.clear()
                self.controller.set_autostart_preference(granted)

            def answered(_bus, _sender, _path, _iface, _signal, params) -> None:
                response, results = params.unpack()
                finish(response == 0 and bool(results.get("autostart")))

            def listen(path: str) -> None:
                subscriptions.append(bus.signal_subscribe(PORTAL, REQUEST_IFACE, "Response", path, None,
                                                          Gio.DBusSignalFlags.NONE, answered))

            def called(source: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
                try:
                    handle = source.call_finish(result).unpack()[0]
                except GLib.Error as error:
                    _warn(f"the Background portal failed: {error.message}")
                    finish(False)
                    return
                if handle != expected and subscriptions:
                    listen(handle)   # an old portal answers on a path of its own

            listen(expected)
            options = {
                "handle_token": GLib.Variant("s", token),
                "reason": GLib.Variant("s", self.controller._("Start the radio with the system")),
                "autostart": GLib.Variant("b", on),
                "commandline": GLib.Variant("as", [COMMAND, "--autostart"]),
            }
            bus.call(PORTAL, PORTAL_PATH, "org.freedesktop.portal.Background", "RequestBackground",
                     GLib.Variant("(sa{sv})", ("", options)), GLib.VariantType("(o)"), Gio.DBusCallFlags.NONE,
                     TIMEOUT_MS, None, called)
        except Exception as error:
            _warn(f"couldn't ask the Background portal: {error}")
            subscriptions.clear()
            self.controller.set_autostart_preference(False)

"""Start with the system. Flatpak asks the Background portal; Snap and the host write an autostart file.

The state is kept in the preference `Autostart`; the file (or the portal) is what makes it happen.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from .. import APP_ID, APP_NAME

COMMAND = "minimalistic-radio"
AUTOSTART_EXEC = COMMAND + " --autostart"
REASON = "Start the radio with the system"


def autostart_desktop_entry(exec_line: str) -> str:
    return ("[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={APP_NAME}\n"
            f"Exec={exec_line}\n"
            f"Icon={APP_ID}\n"
            "Terminal=false\n"
            "NoDisplay=true\n"
            "X-GNOME-Autostart-enabled=true\n")


def _warn(text: str) -> None:
    print(f"{APP_NAME}: {text}", file=sys.stderr)


class Autostart:
    def __init__(self, controller: Any) -> None:
        self.controller = controller

    def enabled(self) -> bool:
        return self.controller.prefs.autostart

    def set(self, on: bool) -> None:
        if os.path.exists("/.flatpak-info"):
            self._portal(on)
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
        try:
            import gi
            gi.require_version("Gio", "2.0")
            from gi.repository import Gio, GLib
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            options = {
                "reason": GLib.Variant("s", REASON),
                "autostart": GLib.Variant("b", on),
                "commandline": GLib.Variant("as", [COMMAND, "--autostart"]),
            }
            bus.call("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                     "org.freedesktop.portal.Background", "RequestBackground",
                     GLib.Variant("(sa{sv})", ("", options)), None, Gio.DBusCallFlags.NONE, 5000, None,
                     lambda *_args: None)
        except Exception as error:
            _warn(f"couldn't ask the Background portal: {error}")

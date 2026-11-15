"""The station popup: a desktop notification when a media key or the tray menu changes the station."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib  # noqa: E402

from ..controller import Change  # noqa: E402

NOTIFICATION_ID = "station"
FIRST_TITLE_WINDOW = 15.0   # seconds after the switch in which the first title replaces the notification
COVER_PIXELS = 256          # plenty for a notification; the cover file itself is 600 px


def cover_icon(path: Path) -> Gio.Icon | None:
    """The cover at most 256 px on a side, as PNG bytes: no file the notification server might not be able to read."""
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(path), COVER_PIXELS, COVER_PIXELS)
        ok, data = pixbuf.save_to_bufferv("png", [], [])
    except GLib.Error:
        return None
    return Gio.BytesIcon.new(GLib.Bytes.new(data)) if ok else None


class StationNotifier:
    def __init__(self, app: Any) -> None:
        self.app = app
        self._switched_at: float | None = None
        self.last_title: str | None = None   # what was sent last (a GNotification can't be read back)
        app.controller.subscribe(self._changed)

    def close(self) -> None:
        self.app.controller.unsubscribe(self._changed)

    def _changed(self, change: Change) -> None:
        controller = self.app.controller
        if not controller.prefs.show_station_popup:
            return
        if change & Change.SWITCHED:
            self._switched_at = time.monotonic()
            self._send()
        elif change & Change.TRACK and self._switched_at is not None and controller.track:
            if time.monotonic() - self._switched_at <= FIRST_TITLE_WINDOW:
                self._send()
            self._switched_at = None

    def _send(self) -> None:
        controller = self.app.controller
        name = controller.station_name
        if not name:
            return
        self.last_title = name
        notification = Gio.Notification.new(name)
        notification.set_body(controller.track or self.app._("Connecting…"))
        cover = controller.cover_path
        icon = cover_icon(cover) if cover is not None and cover.exists() else None
        if icon is not None:
            notification.set_icon(icon)
        notification.set_default_action("app.show-panel")
        self.app.send_notification(NOTIFICATION_ID, notification)

"""The station popup: a desktop notification when a media key or the tray menu changes the station."""
from __future__ import annotations

import time
from typing import Any

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio  # noqa: E402

from ..controller import Change  # noqa: E402

NOTIFICATION_ID = "station"
FIRST_TITLE_WINDOW = 15.0   # seconds after the switch in which the first title replaces the notification


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
        if cover is not None and cover.exists():
            notification.set_icon(Gio.FileIcon.new(Gio.File.new_for_path(str(cover))))
        notification.set_default_action("app.show-panel")
        self.app.send_notification(NOTIFICATION_ID, notification)

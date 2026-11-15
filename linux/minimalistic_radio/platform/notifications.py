"""The station popup: a desktop notification when a media key or the tray menu changes the station."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib  # noqa: E402

from ..controller import Change, Status  # noqa: E402

NOTIFICATION_ID = "station"
FIRST_TITLE_WINDOW = 15.0   # seconds after the switch in which the first title, then its cover, replace it
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
    """Sent on the switch, then replaced (within FIRST_TITLE_WINDOW, for the same station) by the first title and
    once more by that title's cover. GNOME shows a banner for every replacement, so never more than that."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self._switched_at: float | None = None
        self._station = -1                   # the station switched to
        self._title: str | None = None       # the first title, sent; its cover is awaited
        self.last_title: str | None = None   # what was sent last (a GNotification can't be read back)
        self.last_body: str | None = None
        app.controller.subscribe(self._changed)

    def close(self) -> None:
        self.app.controller.unsubscribe(self._changed)

    def _changed(self, change: Change) -> None:
        controller = self.app.controller
        if not controller.prefs.show_station_popup:
            return
        if change & Change.SWITCHED:
            self._switched_at = time.monotonic()
            self._station = controller.current
            self._title = None
            self._send()
            return
        if self._switched_at is None:
            return
        if controller.current != self._station or time.monotonic() - self._switched_at > FIRST_TITLE_WINDOW:
            self._switched_at = None
            return
        if self._title is None:
            if change & Change.TRACK and controller.track:
                self._title = controller.track   # a new title never has its cover yet
                self._send()
        elif change & Change.TRACK and controller.track != self._title:
            self._switched_at = None           # the next song: the notification stays with the first
        elif change & Change.COVER and controller.cover_path is not None:
            self._send()
            self._switched_at = None

    def _body(self) -> str:
        """The song; else what the footer says (like the Windows card): connecting, or ready or stopped."""
        controller, _ = self.app.controller, self.app._
        if controller.track:
            return controller.track
        if controller.active:
            return _("Connecting…")
        if controller.status is Status.STOPPED:
            return controller.message or _("Stopped")
        return _("Ready to play")

    def _send(self) -> None:
        controller = self.app.controller
        name = controller.station_name
        if not name:
            return
        self.last_title = name
        self.last_body = self._body()
        notification = Gio.Notification.new(name)
        notification.set_body(self.last_body)
        cover = controller.cover_path
        icon = cover_icon(cover) if cover is not None and cover.exists() else None
        if icon is not None:
            notification.set_icon(icon)
        notification.set_default_action("app.show-panel")
        self.app.send_notification(NOTIFICATION_ID, notification)

    def withdraw(self) -> None:
        """On Quit: the notification goes with the app, like the Windows card."""
        self.app.withdraw_notification(NOTIFICATION_ID)

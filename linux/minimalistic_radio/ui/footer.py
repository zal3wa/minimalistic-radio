"""Below the station list: what's playing, the volume row (like Windows 11) and Play/Stop."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from ..controller import Change, RadioController, Status  # noqa: E402
from ..platform.menu_model import SLEEP_MINUTES  # noqa: E402

if TYPE_CHECKING:
    from .window import RadioWindow

COVER_SIZE = 42
FALLBACK_ICON = "audio-x-generic-symbolic"
BUBBLE_MS = 1000          # the volume bubble hides this long after the last change


def volume_icon(volume: int) -> str:
    if volume <= 0:
        return "audio-volume-muted-symbolic"
    if volume <= 33:
        return "audio-volume-low-symbolic"
    if volume <= 66:
        return "audio-volume-medium-symbolic"
    return "audio-volume-high-symbolic"


class Footer(Gtk.Box):
    def __init__(self, window: RadioWindow, controller: RadioController, _: Callable[[str], str]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                         margin_start=12, margin_end=12, margin_top=6, margin_bottom=12)
        self.window = window
        self.controller = controller
        self._ = _
        self._syncing = False                      # the slider is being set from the controller
        self._bubble_timer = 0
        self._cover: tuple[Path, Gdk.Texture] | None = None

        # Now playing: cover, caption and song, copy button.
        self.cover = Gtk.Image(css_classes=["now-cover"], overflow=Gtk.Overflow.HIDDEN)
        self.cover.set_size_request(COVER_SIZE, COVER_SIZE)
        self.caption = Gtk.Label(label=_("Now playing"), xalign=0, css_classes=["caption", "dim-label"])
        self.now_label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER, hexpand=True)
        text.append(self.caption)
        text.append(self.now_label)
        self.copy_button = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text=_("Copy title"),
                                      valign=Gtk.Align.CENTER, css_classes=["flat"])
        self.copy_button.connect("clicked", lambda _button: self.copy_track())
        card = Gtk.Box(spacing=10, css_classes=["card", "now-playing"])
        card.append(self.cover)
        card.append(text)
        card.append(self.copy_button)

        # Volume: the speaker (mute), the slider with its value bubble, the moon (sleep timer).
        self.volume_button = Gtk.Button(valign=Gtk.Align.CENTER, css_classes=["flat"])
        self.volume_button.connect("clicked", self._toggle_mute)
        self.volume_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.volume_scale.set_hexpand(True)
        self.volume_scale.set_draw_value(False)
        self.volume_scale.set_round_digits(0)
        self.volume_scale.update_property([Gtk.AccessibleProperty.LABEL], [_("Volume")])
        self.volume_scale.connect("value-changed", self._volume_moved)
        self.volume_bubble_label = Gtk.Label(css_classes=["numeric"])
        self.volume_bubble = Gtk.Popover(child=self.volume_bubble_label, autohide=False, can_focus=False,
                                         can_target=False, position=Gtk.PositionType.TOP,
                                         css_classes=["volume-bubble"])
        self.volume_bubble.set_parent(self.volume_scale)

        sleep_menu = Gio.Menu()
        for minutes in SLEEP_MINUTES:
            sleep_menu.append(_("{n} min").format(n=minutes), f"footer.sleep({minutes})")
        sleep_menu.append(_("Off"), "footer.sleep(0)")
        self.sleep_button = Gtk.MenuButton(icon_name="weather-clear-night-symbolic", tooltip_text=_("Sleep timer"),
                                           menu_model=sleep_menu, valign=Gtk.Align.CENTER, css_classes=["flat"])
        self._sleep_action = Gio.SimpleAction.new_stateful("sleep", GLib.VariantType("i"), GLib.Variant("i", 0))
        self._sleep_action.connect("change-state", self._sleep_chosen)
        actions = Gio.SimpleActionGroup()
        actions.add_action(self._sleep_action)
        self.insert_action_group("footer", actions)

        volume_row = Gtk.Box(spacing=4)
        volume_row.append(self.volume_button)
        volume_row.append(self.volume_scale)
        volume_row.append(self.sleep_button)
        self.sleep_label = Gtk.Label(xalign=0, visible=False, css_classes=["caption", "dim-label"])

        self.play_content = Adw.ButtonContent(icon_name="media-playback-start-symbolic", label=_("Play"))
        self.play_button = Gtk.Button(child=self.play_content, css_classes=["pill", "suggested-action"])
        self.play_button.connect("clicked", lambda _button: self.controller.toggle())

        self.append(card)
        self.append(volume_row)
        self.append(self.sleep_label)
        self.append(self.play_button)

    def release(self) -> None:
        """Called when the window is destroyed: no timer may fire on it afterwards."""
        self._hide_bubble()
        self.volume_bubble.unparent()

    # ---- From the controller ----

    def refresh(self, change: Change) -> None:
        c, _ = self.controller, self._
        if change & (Change.STATE | Change.STATIONS):
            self.play_content.set_label(_("Stop") if c.active else _("Play"))
            self.play_content.set_icon_name("media-playback-stop-symbolic" if c.active
                                            else "media-playback-start-symbolic")
            self.play_button.set_sensitive(c.active or bool(c.stations))
        if change & (Change.STATE | Change.TRACK):
            self._show_now()
        if change & Change.COVER:
            self._show_cover()
        if change & Change.VOLUME:
            self._show_volume()
        if change & Change.SLEEP:
            self._show_sleep()

    def _status(self) -> str:
        c, _ = self.controller, self._
        if c.status is Status.PLAYING:
            return _("The station doesn't send song titles")
        if c.status is Status.CONNECTING:
            return _("Connecting to the station…")
        if c.status is Status.RETRYING:
            return c.message or _("Connecting to the station…")
        if c.status is Status.STOPPED:
            return c.message or _("Stopped")
        return _("Ready to play")

    def _show_now(self) -> None:
        track = self.controller.track
        self.now_label.set_text(track or self._status())
        self.now_label.set_tooltip_text(track)
        self.copy_button.set_sensitive(bool(track))

    def _show_cover(self) -> None:
        path = self.controller.cover_path
        texture = None
        if path is not None:
            if self._cover is not None and self._cover[0] == path:
                texture = self._cover[1]
            else:
                try:
                    texture = Gdk.Texture.new_from_filename(str(path))
                    self._cover = (path, texture)
                except GLib.Error:
                    texture = None
        if texture is not None:
            self.cover.set_from_paintable(texture)
            self.cover.set_pixel_size(COVER_SIZE)
        else:
            self.cover.set_from_icon_name(FALLBACK_ICON)
            self.cover.set_pixel_size(24)

    def _show_volume(self) -> None:
        volume = self.controller.volume
        self._syncing = True
        try:
            self.volume_scale.set_value(volume)
        finally:
            self._syncing = False
        self.volume_button.set_icon_name(volume_icon(volume))
        self.volume_button.set_tooltip_text(self._("Unmute") if volume == 0 else self._("Mute"))

    def _show_sleep(self) -> None:
        c = self.controller
        self._sleep_action.set_state(GLib.Variant("i", c.sleep_minutes or 0))
        sleeping = c.sleep_at is not None
        self.sleep_label.set_visible(sleeping)
        if sleeping:
            self.sleep_label.set_text(self._("Stops at {time}").format(time=f"{c.sleep_at:%H:%M}"))
            self.sleep_button.add_css_class("accent")
        else:
            self.sleep_button.remove_css_class("accent")

    # ---- From the user ----

    def copy_track(self) -> None:
        """Copies the song title, with the toast "Copied" (the copy button, and the tray menu via the window)."""
        track = self.controller.track
        if not track:
            return
        self.get_clipboard().set_content(Gdk.ContentProvider.new_for_value(track))
        self.window.toast(self._("Copied"))

    def _toggle_mute(self, _button: Gtk.Button) -> None:
        self.controller.toggle_mute()

    def _volume_moved(self, scale: Gtk.Scale) -> None:
        if self._syncing:
            return   # moved for a change made elsewhere (the tray, media keys): no bubble
        value = round(scale.get_value())
        self.controller.set_volume(value)
        self._show_bubble(value)

    def _show_bubble(self, value: int) -> None:
        """The number over the slider's knob while it moves (dragged, scrolled or with keys)."""
        self.volume_bubble_label.set_text(str(value))
        trough = self.volume_scale.get_range_rect()
        start, end = self.volume_scale.get_slider_range()
        knob = max(0, end - start)
        spot = Gdk.Rectangle()
        spot.x = round(trough.x + knob / 2 + value / 100 * max(0, trough.width - knob))
        spot.y = trough.y
        spot.width = 1
        spot.height = max(1, trough.height)
        self.volume_bubble.set_pointing_to(spot)
        if not self.volume_bubble.get_visible():
            self.volume_bubble.popup()
        if self._bubble_timer:
            GLib.source_remove(self._bubble_timer)
        self._bubble_timer = GLib.timeout_add(BUBBLE_MS, self._bubble_timeout)

    def _bubble_timeout(self) -> bool:
        self._bubble_timer = 0
        self.volume_bubble.popdown()
        return GLib.SOURCE_REMOVE

    def _hide_bubble(self) -> None:
        if self._bubble_timer:
            GLib.source_remove(self._bubble_timer)
            self._bubble_timer = 0
        self.volume_bubble.popdown()

    def _sleep_chosen(self, _action: Gio.SimpleAction, value: GLib.Variant) -> None:
        minutes = value.get_int32()
        self.controller.set_sleep_timer(minutes or None)

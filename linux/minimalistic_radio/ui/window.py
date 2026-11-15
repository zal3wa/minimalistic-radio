"""The panel window: a navigation view whose first page is the station list with the footer.

Closing the window only hides it; the radio keeps playing. The history and settings pages are
placeholders filled by a later task (13).
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk  # noqa: E402

from .. import APP_NAME  # noqa: E402
from ..controller import Change, RadioController  # noqa: E402
from .footer import Footer  # noqa: E402
from .logos import LogoCache  # noqa: E402
from .search_page import SearchPage  # noqa: E402
from .station_dialog import StationDialog  # noqa: E402
from .stations_page import StationsPage  # noqa: E402

PAGES = ("stations", "search", "history", "settings")
EVERYTHING = Change.STATE | Change.STATIONS | Change.TRACK | Change.COVER | Change.VOLUME | Change.SLEEP

_styled_displays: list[Gdk.Display] = []


def _load_style() -> None:
    """The few looks libadwaita's classes don't cover (style.css), once per display."""
    display = Gdk.Display.get_default()
    if display is None or display in _styled_displays:
        return
    _styled_displays.append(display)
    provider = Gtk.CssProvider()
    provider.load_from_path(str(Path(__file__).with_name("style.css")))
    Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def _placeholder(tag: str, title: str) -> Adw.NavigationPage:
    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())
    return Adw.NavigationPage(tag=tag, title=title, child=toolbar)


class RadioWindow(Adw.ApplicationWindow):
    def __init__(self, controller: RadioController, _: Callable[[str], str] = lambda s: s,
                 application: Gtk.Application | None = None) -> None:
        super().__init__(application=application, title=APP_NAME, default_width=380, default_height=640,
                         resizable=True)
        self.set_hide_on_close(True)
        _load_style()
        self.controller = controller
        self._ = _
        self._toast: Adw.Toast | None = None
        self.logos = LogoCache(controller.paths.cache / "logos")

        self.footer = Footer(self, controller, _)
        self.stations_page = StationsPage(self, controller, self.logos, _)
        self.stations_page.toolbar.add_bottom_bar(self.footer)
        header = self.stations_page.header
        self.add_button = Gtk.Button(icon_name="list-add-symbolic", tooltip_text=_("Add a station"))
        self.add_button.connect("clicked", lambda _button: self.show_page("search"))
        header.pack_start(self.add_button)
        self.settings_button = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text=_("Settings"))
        self.settings_button.connect("clicked", lambda _button: self.show_page("settings"))
        header.pack_end(self.settings_button)
        self.history_button = Gtk.Button(icon_name="document-open-recent-symbolic", tooltip_text=_("Song history"))
        self.history_button.connect("clicked", lambda _button: self.show_page("history"))
        header.pack_end(self.history_button)
        self.update_arrow = Gtk.Button(icon_name="software-update-available-symbolic", visible=False,
                                       css_classes=["success"])   # Task 16 shows it
        header.pack_end(self.update_arrow)

        self.navigation = Adw.NavigationView()
        self.navigation.add(self.stations_page)
        self.search_page = SearchPage(self, controller, self.logos, _)
        self.navigation.add(self.search_page)
        for tag, title in (("history", _("Song history")), ("settings", _("Settings"))):
            self.navigation.add(_placeholder(tag, title))
        self.toasts = Adw.ToastOverlay(child=self.navigation)
        self.set_content(self.toasts)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._key_pressed)
        self.add_controller(keys)
        self.connect("destroy", self._destroyed)

        controller.subscribe(self._changed)
        self._changed(EVERYTHING)
        if controller.corrupt_stations:
            self.toast(_("Your station list couldn't be read. It was saved as stations.json.bad."))

    def _destroyed(self, _window: Gtk.Window) -> None:
        self.footer.release()
        self.stations_page.release()
        self.search_page.release()

    def _changed(self, change: Change) -> None:
        self.stations_page.refresh(change)
        self.search_page.refresh(change)
        self.footer.refresh(change)
        if change & Change.MESSAGE and self.controller.message:
            self.toast(self.controller.message)   # a file couldn't be saved

    # ---- What other parts call ----

    def show_page(self, tag: str) -> None:
        if tag not in PAGES:
            return
        visible = self.navigation.get_visible_page()
        shown = visible.get_tag() if visible is not None else None
        if shown == tag:
            return
        if tag == "stations":
            self.navigation.pop_to_tag("stations")
        elif shown == "stations":
            self.navigation.push_by_tag(tag)
        else:
            self.navigation.replace_with_tags(["stations", tag])

    def copy_track(self) -> None:
        """Copies the song title and shows "Copied" (the tray menu's song item calls it)."""
        self.footer.copy_track()

    def toast(self, text: str) -> None:
        """Shows `text` at the bottom of the window, in place of the previous toast."""
        if self._toast is not None:
            self._toast.dismiss()
        toast = Adw.Toast(title=text, use_markup=False)
        toast.connect("dismissed", self._toast_dismissed)
        self._toast = toast
        self.toasts.add_toast(toast)

    def _toast_dismissed(self, toast: Adw.Toast) -> None:
        if self._toast is toast:
            self._toast = None

    def edit_station(self, index: int) -> StationDialog | None:
        """Opens the station dialog for the station at that index."""
        if 0 <= index < len(self.controller.stations):
            return StationDialog(self, self.controller.stations[index],
                                 lambda station: self.controller.update_station(index, station), self._)
        return None

    def add_by_address(self) -> StationDialog:
        return StationDialog(self, None, self.controller.add_station, self._)

    # ---- Keys ----

    def _key_pressed(self, _keys: Gtk.EventControllerKey | None, keyval: int, _keycode: int,
                     _state: Gdk.ModifierType) -> bool:
        if keyval != Gdk.KEY_Escape:
            return False
        if self.stations_page.cancel_drag():
            return True
        visible = self.navigation.get_visible_page()
        if visible is not None and visible.get_tag() != "stations":
            self.navigation.pop()
        else:
            self.close()   # hides it: the radio keeps playing
        return True

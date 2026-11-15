"""The panel window: a navigation view whose first page is the station list with the footer.

Closing the window only hides it; the radio keeps playing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk  # noqa: E402

from .. import APP_NAME, main  # noqa: E402
from ..controller import Change, RadioController  # noqa: E402
from .footer import Footer  # noqa: E402
from .history_page import HistoryPage  # noqa: E402
from .logos import LogoCache  # noqa: E402
from .search_page import SearchPage  # noqa: E402
from .settings_page import SettingsPage  # noqa: E402
from .station_dialog import StationDialog  # noqa: E402
from .stations_page import StationsPage  # noqa: E402
from .statistics_page import StatisticsPage  # noqa: E402

PAGES = ("stations", "search", "history", "settings", "statistics")
OPENS_STATISTICS = ("settings", "history")   # Statistics opens over these, and back goes there
EVERYTHING = (Change.STATE | Change.STATIONS | Change.TRACK | Change.COVER | Change.VOLUME | Change.SLEEP
              | Change.STATISTICS)
HISTORY_ICON = "io.github.zal3wa.minimalistic-radio-history-symbolic"
WIDTH, HEIGHT = 412, 602

_styled_displays: list[Gdk.Display] = []


def icon_folders() -> list[Path]:
    """Where the app's own icons are: installed with the app, else in the source tree. The app icon (for About)
    also from where it was installed, for a prefix the desktop doesn't look in."""
    source = Path(__file__).resolve().parents[2] / "data" / "icons" / "hicolor"
    installed = Path(main.PKGDATADIR)
    return [installed / "icons", installed.parent / "icons" / "hicolor" / "scalable" / "apps",
            source / "symbolic" / "actions", source / "scalable" / "apps"]


def _load_style() -> None:
    """The few looks libadwaita's classes don't cover (style.css) and the app's icons, once per display."""
    display = Gdk.Display.get_default()
    if display is None or display in _styled_displays:
        return
    _styled_displays.append(display)
    provider = Gtk.CssProvider()
    provider.load_from_path(str(Path(__file__).with_name("style.css")))
    Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    theme = Gtk.IconTheme.get_for_display(display)
    for folder in icon_folders():
        if folder.is_dir():
            theme.add_search_path(str(folder))


class RadioWindow(Adw.ApplicationWindow):
    def __init__(self, controller: RadioController, _: Callable[[str], str] = lambda s: s,
                 application: Gtk.Application | None = None, logos: LogoCache | None = None) -> None:
        """`logos`: the application's cache, kept across windows so a rebuilt window has its logos at once."""
        super().__init__(application=application, title=APP_NAME, default_width=WIDTH, default_height=HEIGHT,
                         resizable=True)
        self.set_hide_on_close(True)
        _load_style()
        self.controller = controller
        self._ = _
        self._toast: Adw.Toast | None = None
        self.logos = logos if logos is not None else LogoCache(controller.paths.cache / "logos")

        self.footer = Footer(self, controller, _)
        self.stations_page = StationsPage(self, controller, self.logos, _)
        self.stations_page.toolbar.add_bottom_bar(self.footer)
        # The bar: [+ Station] [History] … (update) (settings) ✕
        header = self.stations_page.header
        self.add_button = Gtk.Button(child=Adw.ButtonContent(icon_name="list-add-symbolic", label=_("Station")),
                                     tooltip_text=_("Add a station"), css_classes=["raised"])
        self.add_button.connect("clicked", lambda _button: self.show_page("search"))
        header.pack_start(self.add_button)
        self.history_button = Gtk.Button(child=Adw.ButtonContent(icon_name=HISTORY_ICON, label=_("History")),
                                         tooltip_text=_("Song history"), css_classes=["raised"])
        self.history_button.connect("clicked", lambda _button: self.show_page("history"))
        header.pack_start(self.history_button)
        self.settings_button = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text=_("Settings"))
        self.settings_button.connect("clicked", lambda _button: self.show_page("settings"))
        header.pack_end(self.settings_button)
        self.update_arrow = Gtk.Button(icon_name="software-update-available-symbolic", visible=False,
                                       css_classes=["success"])   # shown by set_update()
        self.update_arrow.connect("clicked", lambda _button: self.activate_action("app.update", None))
        header.pack_end(self.update_arrow)

        self.navigation = Adw.NavigationView()
        self.navigation.add(self.stations_page)
        self.search_page = SearchPage(self, controller, self.logos, _)
        self.navigation.add(self.search_page)
        self.history_page = HistoryPage(self, controller, self.logos, _)
        self.navigation.add(self.history_page)
        self.settings_page = SettingsPage(self, controller, _)
        self.navigation.add(self.settings_page)
        self.statistics_page = StatisticsPage(self, controller, self.logos, _)
        self.navigation.add(self.statistics_page)
        self.toasts = Adw.ToastOverlay(child=self.navigation)
        self.set_content(self.toasts)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._key_pressed)
        self.add_controller(keys)
        self.connect("destroy", self._destroyed)

        controller.subscribe(self._changed)
        self._changed(EVERYTHING)
        if controller.corrupt_stations:
            controller.corrupt_stations = False   # told once per run: a window built again doesn't repeat it
            self.toast(_("Your station list couldn't be read. It was saved as stations.json.bad."))

    def _destroyed(self, _window: Gtk.Window) -> None:
        self.footer.release()
        self.stations_page.release()
        self.search_page.release()
        self.controller.unsubscribe(self._changed)

    def _changed(self, change: Change) -> None:
        self.stations_page.refresh(change)
        self.search_page.refresh(change)
        self.history_page.refresh(change)
        self.settings_page.refresh(change)
        self.statistics_page.refresh(change)
        self.footer.refresh(change)
        if change & Change.MESSAGE and self.controller.notice:
            self.toast(self.controller.notice)   # the station list couldn't be saved

    # ---- What other parts call ----

    def shown_pages(self) -> list[str]:
        """The tags of the pages in the navigation stack, the visible one last."""
        stack = self.navigation.get_navigation_stack()
        return [stack.get_item(i).get_tag() for i in range(stack.get_n_items())]

    def show_page(self, tag: str) -> None:
        """Opens `tag` with the pages it is reached through under it: Statistics opens over Song history or
        Settings, whichever is open (Settings otherwise), so back goes there."""
        if tag not in PAGES:
            return
        shown = self.shown_pages()
        if tag == "statistics":
            parent = shown[1] if len(shown) > 1 and shown[1] in OPENS_STATISTICS else "settings"
            wanted = ["stations", parent, tag]
        else:
            wanted = ["stations"] + ([tag] if tag != "stations" else [])
        if shown == wanted:
            return
        if shown[:len(wanted)] == wanted:
            self.navigation.pop_to_tag(tag)
        elif shown == wanted[:-1]:
            self.navigation.push_by_tag(tag)
        else:
            self.navigation.replace_with_tags(wanted)

    def autostart_enabled(self) -> bool:
        app = self.get_application()
        return app.autostart_enabled() if app is not None else self.controller.prefs.autostart

    def set_autostart(self, on: bool) -> None:
        app = self.get_application()
        if app is not None:
            app.set_autostart(on)
        else:
            self.controller.set_autostart_preference(on)

    def language_changed(self) -> None:
        """The language was chosen: the application builds this window again, on the settings page."""
        app = self.get_application()
        if app is not None:
            app.rebuild_window("settings")

    def quit_app(self) -> None:
        app = self.get_application()
        if app is not None:
            app.quit()

    def copy_track(self) -> None:
        """Copies the song title and shows "Copied" (the tray menu's song item calls it)."""
        self.footer.copy_track()

    def ask_to_copy(self) -> None:
        """The tray's song item, when the window never got the focus (Wayland): the Copy button can copy."""
        self.toast(self._("Press Copy to copy the song"))

    def set_update(self, label: str | None) -> None:
        """The green arrow: "Update" or "Restart to update"; hidden when there is nothing new."""
        self.update_arrow.set_visible(label is not None)
        self.update_arrow.set_tooltip_text(label)

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

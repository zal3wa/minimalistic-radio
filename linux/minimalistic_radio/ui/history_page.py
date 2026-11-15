"""The history page: the songs the radio played, newest first, each with its station's logo and a menu (copy,
search)."""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Callable
from urllib.parse import quote

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

from ..controller import Change, RadioController  # noqa: E402
from ..core.models import HistoryEntry  # noqa: E402
from ..core.statistics import find_logo  # noqa: E402
from .bars import subpage_bar  # noqa: E402
from .logos import LogoCache, LogoImage  # noqa: E402

if TYPE_CHECKING:
    from .window import RadioWindow

LOGO_SIZE = 40
STATISTICS_ICON = "io.github.zal3wa.minimalistic-radio-statistics-symbolic"   # in the app's icons (window.py)


def search_query(title: str) -> str:
    """The song title as search words: the artist separator dropped, everything percent-encoded."""
    return quote(title.replace(" – ", " ").replace(" - ", " "), safe="")


def spotify_uri(title: str) -> str:
    return "https://open.spotify.com/search/" + search_query(title)


def youtube_uri(title: str) -> str:
    return "https://www.youtube.com/results?search_query=" + search_query(title)


def time_text(entry: HistoryEntry) -> str:
    when = entry.time
    return when.strftime("%H:%M") if when.date() == date.today() else when.strftime("%d.%m, %H:%M")


class HistoryRow(Adw.ActionRow):
    def __init__(self, page: HistoryPage, entry: HistoryEntry) -> None:
        _ = page._
        super().__init__(title=entry.title, subtitle=f"{entry.station} · {time_text(entry)}",
                         use_markup=False, title_lines=0, subtitle_lines=1)
        self.entry = entry
        # The station's logo, by its name (all the history knows); the placeholder if it is gone from the list.
        self.logo = LogoImage(page.logos, LOGO_SIZE)
        self.logo.show_logo(find_logo(page.controller.stations, name=entry.station))
        self.add_prefix(self.logo)
        menu = Gio.Menu()
        menu.append(_("Copy"), "row.copy")
        menu.append(_("Search on Spotify"), "row.spotify")
        menu.append(_("Search on YouTube"), "row.youtube")
        self.menu_button = Gtk.MenuButton(icon_name="view-more-symbolic", menu_model=menu, tooltip_text=_("More"),
                                          valign=Gtk.Align.CENTER, css_classes=["flat"])
        self.menu_button.get_popover().set_halign(Gtk.Align.END)   # opens leftwards: stays inside the window
        self.add_suffix(self.menu_button)
        actions = Gio.SimpleActionGroup()
        for name, handler in (("copy", lambda: page.copy(entry)),
                              ("spotify", lambda: page.launch(spotify_uri(entry.title))),
                              ("youtube", lambda: page.launch(youtube_uri(entry.title)))):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _action, _param, handler=handler: handler())
            actions.add_action(action)
        self.insert_action_group("row", actions)


class HistoryPage(Adw.NavigationPage):
    def __init__(self, window: RadioWindow, controller: RadioController, logos: LogoCache,
                 _: Callable[[str], str]) -> None:
        super().__init__(tag="history", title=_("Song history"))
        self.window = window
        self.controller = controller
        self.logos = logos
        self._ = _
        self.rows: list[HistoryRow] = []

        self.empty = Gtk.Label(label=_("Songs the radio plays will show up here."), wrap=True,
                               justify=Gtk.Justification.CENTER, valign=Gtk.Align.CENTER, vexpand=True,
                               margin_start=24, margin_end=24, css_classes=["dim-label"])
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        self.clear_button = Gtk.Button(label=_("Clear history"), halign=Gtk.Align.START, css_classes=["flat"])
        self.clear_button.connect("clicked", lambda _button: controller.clear_history())
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12,
                       margin_start=12, margin_end=12)
        body.append(self.list)
        body.append(self.clear_button)
        self.scroller = Gtk.ScrolledWindow(child=Adw.Clamp(child=body, maximum_size=600), vexpand=True,
                                           hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.stack = Gtk.Stack()
        self.stack.add_named(self.empty, "empty")
        self.stack.add_named(self.scroller, "list")

        # [Statistics] left of the ✕, labelled like the stations page's buttons.
        bar = subpage_bar(self.get_title(), _)
        self.statistics_button = Gtk.Button(child=Adw.ButtonContent(icon_name=STATISTICS_ICON, label=_("Statistics")),
                                            css_classes=["raised"])
        self.statistics_button.connect("clicked", lambda _button: window.show_page("statistics"))
        bar.pack_end(self.statistics_button)
        toolbar = Adw.ToolbarView(content=self.stack)
        toolbar.add_top_bar(bar)
        self.set_child(toolbar)
        self._fill()

    def _fill(self) -> None:
        for row in self.rows:
            self.list.remove(row)
        self.rows = [HistoryRow(self, entry) for entry in self.controller.history]
        for row in self.rows:
            self.list.append(row)
        self.stack.set_visible_child_name("list" if self.rows else "empty")

    def refresh(self, change: Change) -> None:
        if change & Change.HISTORY:
            self._fill()
        elif change & Change.STATIONS:   # a station added, renamed or given another logo
            for row in self.rows:
                logo = find_logo(self.controller.stations, name=row.entry.station)
                if logo != row.logo.url:
                    row.logo.show_logo(logo)

    def copy(self, entry: HistoryEntry) -> None:
        self.get_clipboard().set_content(Gdk.ContentProvider.new_for_value(entry.title))
        self.window.toast(self._("Copied"))

    def launch(self, uri: str) -> None:
        Gtk.UriLauncher(uri=uri).launch(self.window, None, None)

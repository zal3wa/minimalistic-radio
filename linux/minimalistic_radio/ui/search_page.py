"""The search page: station search in radio-browser, and (with the box empty) suggestions.

Rows are the same for results and suggestions: logo, name, "country · format · genres", and a + button
(a check mark when the station is already on the list). Network requests run in worker threads.
"""
from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from ..controller import AddResult, Change, RadioController  # noqa: E402
from ..core import directory  # noqa: E402
from ..core.directory import DirectoryStation, DirectoryUnavailable  # noqa: E402
from ..core.share import is_share_link  # noqa: E402
from ..core.streams import same_stream  # noqa: E402
from ..i18n import languages_for, system_languages  # noqa: E402
from .bars import subpage_bar  # noqa: E402
from .logos import LogoCache, Texture  # noqa: E402

if TYPE_CHECKING:
    from .window import RadioWindow

LOGO_SIZE = 40
FALLBACK_ICON = "audio-x-generic-symbolic"
SEARCH_DELAY_MS = 350


class ResultRow(Adw.ActionRow):
    def __init__(self, page: SearchPage, entry: DirectoryStation) -> None:
        super().__init__(title=entry.name.strip(), subtitle=directory.subtitle(entry), use_markup=False,
                         title_lines=1, subtitle_lines=1)
        self.entry = entry
        self.logo = Gtk.Image(css_classes=["station-logo"], overflow=Gtk.Overflow.HIDDEN, valign=Gtk.Align.CENTER,
                              icon_name=FALLBACK_ICON, pixel_size=24)
        self.logo.set_size_request(LOGO_SIZE, LOGO_SIZE)
        self.add_prefix(self.logo)
        self.button = Gtk.Button(valign=Gtk.Align.CENTER, css_classes=["flat"])
        self.button.connect("clicked", lambda _button: page.add(entry))
        self.add_suffix(self.button)
        self.mark(False, page._)
        page.show_logo(self)

    def mark(self, known: bool, _: Callable[[str], str]) -> None:
        self.button.set_icon_name("object-select-symbolic" if known else "list-add-symbolic")
        self.button.set_tooltip_text(_("Already on your list") if known else _("Add to your stations"))
        self.button.set_sensitive(not known)

    def set_logo(self, texture: Texture | None) -> None:
        if texture is not None:
            self.logo.set_from_paintable(texture)
            self.logo.set_pixel_size(LOGO_SIZE)


class SearchPage(Adw.NavigationPage):
    def __init__(self, window: RadioWindow, controller: RadioController, logos: LogoCache,
                 _: Callable[[str], str]) -> None:
        super().__init__(title=_("Add a station"), tag="search")
        self.window = window
        self.controller = controller
        self.logos = logos
        self._ = _
        self.rows: list[ResultRow] = []
        self._generation = 0                       # a search that is no longer wanted has an old number
        self._search_timeout = 0
        self._suggested: tuple[list[DirectoryStation], list[DirectoryStation], str | None] | None = None
        self._loading = False
        self._failed = False
        self._released = False

        self.entry = Gtk.SearchEntry(hexpand=True, placeholder_text=_("Search"))
        self.entry.connect("activate", lambda _entry: self.search())
        self.entry.connect("notify::text", self._text_changed)
        self.entry.connect("stop-search", lambda _entry: window.navigation.pop())   # Escape in the box goes back
        self.search_button = Gtk.Button(label=_("Search"))
        self.search_button.connect("clicked", lambda _button: self.search())
        bar = Gtk.Box(spacing=6, margin_start=12, margin_end=12, margin_top=12)
        bar.append(self.entry)
        bar.append(self.search_button)
        self.address_button = Gtk.Button(label=_("Add by address"), halign=Gtk.Align.START, css_classes=["link"],
                                         margin_start=6)
        self.address_button.connect("clicked", lambda _button: window.add_by_address())
        self.status = Gtk.Label(wrap=True, xalign=0, visible=False, css_classes=["dim-label"],
                                margin_start=12, margin_end=12, margin_top=6)
        self.results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_start=12, margin_end=12,
                               margin_top=6, margin_bottom=12, valign=Gtk.Align.START)
        scrolled = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, child=self.results)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for widget in (bar, self.address_button, self.status, scrolled):
            body.append(widget)
        toolbar = Adw.ToolbarView(content=body)
        toolbar.add_top_bar(subpage_bar(self.get_title(), _))
        self.set_child(toolbar)
        self.connect("showing", self._showing)
        self.connect("hiding", lambda _page: self._cancel_search())

    def release(self) -> None:
        self._released = True
        self._cancel_search()

    # ---- Entering, typing ----

    def _showing(self, _page: Adw.NavigationPage) -> None:
        """Opening the page: an empty box and the suggestions."""
        self._cancel_search()
        self.entry.set_text("")
        self.show_suggestions()
        self.entry.grab_focus()

    def _open_link(self) -> bool:
        """A share link pasted into the box opens the Shared station page instead of a search."""
        text = self.entry.get_text().strip()
        if not is_share_link(text):
            return False
        self.entry.set_text("")
        self.window.open_link(text)
        return True

    def _text_changed(self, entry: Gtk.SearchEntry, _property: object) -> None:
        self._cancel_search()
        if self.window.navigation.get_visible_page() != self:
            return
        if entry.get_text().strip():
            self._search_timeout = GLib.timeout_add(SEARCH_DELAY_MS, self._search_after_pause)
        else:
            self.show_suggestions()

    # ---- Rendering ----

    def _clear(self) -> None:
        self.rows = []
        child = self.results.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self.results.remove(child)
            child = following

    def _say(self, text: str) -> None:
        self.status.set_label(text)
        self.status.set_visible(bool(text))

    def _section(self, title: str | None, entries: list[DirectoryStation]) -> None:
        if title is not None:
            self.results.append(Gtk.Label(label=title, xalign=0, css_classes=["heading"], margin_top=6))
        box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        for entry in entries:
            row = ResultRow(self, entry)
            self.rows.append(row)
            box.append(row)
        self.results.append(box)
        self.refresh(Change.STATIONS)

    def show_logo(self, row: ResultRow) -> None:
        url = row.entry.logo
        known, texture = self.logos.lookup(url)
        row.set_logo(texture)
        if not known:
            self.logos.load(url, lambda texture, row=row: row.set_logo(texture))

    def refresh(self, change: Change) -> None:
        """The station list changed: the + of a station that is on it turns into a check mark."""
        if change & Change.STATIONS:
            for row in self.rows:
                row.mark(any(same_stream(station.url, row.entry.url) for station in self.controller.stations),
                         self._)

    # ---- Search ----

    def _cancel_search(self) -> None:
        self._generation += 1
        if self._search_timeout:
            GLib.source_remove(self._search_timeout)
            self._search_timeout = 0

    def _search_after_pause(self) -> bool:
        self._search_timeout = 0
        self.search()
        return GLib.SOURCE_REMOVE

    def search(self) -> None:
        self._cancel_search()
        if self._open_link():
            return
        query = self.entry.get_text().strip()
        if not query:
            return
        generation = self._generation
        self._clear()
        self._say(self._("Searching…"))

        def work() -> None:
            try:
                found: list[DirectoryStation] | None = directory.search(query)
            except DirectoryUnavailable:
                found = None
            GLib.idle_add(self._found, generation, found)

        threading.Thread(target=work, daemon=True).start()

    def _found(self, generation: int, found: list[DirectoryStation] | None) -> bool:
        if generation != self._generation or self._released:
            return GLib.SOURCE_REMOVE
        if found is None:
            self._say(self._("Couldn't reach the station directory. Try again."))
        elif not found:
            self._say(self._("No results."))
        else:
            self._say("")
            self._section(None, found)
        return GLib.SOURCE_REMOVE

    # ---- Suggestions ----

    def _country(self) -> str | None:
        language = directory.language_of(languages_for(self.controller.prefs.language, system_languages()))
        return directory.country_for(language, directory.country_from_locale(os.environ))

    def show_suggestions(self) -> None:
        """With the box empty: Recommended and Popular, loaded once per run (a failure is tried again next time)."""
        self._clear()
        if self._suggested is not None:
            self._render_suggestions()
        elif self._loading:
            self._say(self._("Loading suggestions…"))
        else:
            self._load_suggestions()

    def _load_suggestions(self) -> None:
        self._loading = True
        self._say(self._("Loading suggestions…"))
        country = self._country()

        def work() -> None:
            try:
                found: tuple[list[DirectoryStation], list[DirectoryStation]] | None = directory.suggestions(country)
            except DirectoryUnavailable:
                found = None
            GLib.idle_add(self._suggestions_loaded, found, country)

        threading.Thread(target=work, daemon=True).start()

    def _suggestions_loaded(self, found: tuple[list[DirectoryStation], list[DirectoryStation]] | None,
                            country: str | None) -> bool:
        self._loading = False
        if self._released:
            return GLib.SOURCE_REMOVE
        if found is not None and found[1]:   # only a complete success is kept; otherwise the next open retries
            self._suggested = (found[0], found[1], country)
        if self.entry.get_text().strip():
            if self.status.get_label() == self._("Loading suggestions…"):
                self._say("")   # the user is typing meanwhile (a search on its way keeps its "Searching…")
            return GLib.SOURCE_REMOVE
        self._clear()
        if found is None or not (found[0] or found[1]):
            self._say(self._("Couldn't reach the station directory. Try again."))
        else:
            self._render_suggestions(found[0], found[1], country)
        return GLib.SOURCE_REMOVE

    def _render_suggestions(self, recommended: list[DirectoryStation] | None = None,
                            popular: list[DirectoryStation] | None = None, country: str | None = None) -> None:
        if recommended is None or popular is None:
            assert self._suggested is not None
            recommended, popular, country = self._suggested
        self._say("")
        if recommended:
            self._section(self._("Recommended"), recommended)
        if popular:
            self._section(self._("Popular in your country") if country else self._("Popular worldwide"), popular)

    # ---- Adding ----

    def add(self, entry: DirectoryStation) -> None:
        if self.controller.add_station(directory.to_station(entry)) == AddResult.DUPLICATE:
            self.refresh(Change.STATIONS)

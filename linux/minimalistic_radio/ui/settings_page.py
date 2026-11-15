"""The settings page: language, start with the session, station changes, station list export/import, the
statistics, about, quit. One card per section, the same order as on Windows and macOS (no updates: Flatpak
brings them)."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from .. import APP_ID, APP_NAME, VERSION  # noqa: E402
from ..controller import Change, RadioController  # noqa: E402
from .bars import subpage_bar  # noqa: E402

if TYPE_CHECKING:
    from .window import RadioWindow

WEBSITE = "https://github.com/zal3wa/minimalistic-radio"
ICON_SIZE = 32

# The language choices (code, label). A label of None is the translated "Same as system". One line per language.
LANGUAGE_OPTIONS: list[tuple[str, str | None]] = [
    ("auto", None),
    ("pl", "Polski"),
    ("en", "English"),
    ("de", "Deutsch"),
    ("uk", "Українська"),
    ("cs", "Čeština"),
    ("es", "Español"),
    ("fr", "Français"),
    ("it", "Italiano"),
    ("pt", "Português"),
]


class SettingsPage(Adw.NavigationPage):
    def __init__(self, window: RadioWindow, controller: RadioController, _: Callable[[str], str]) -> None:
        super().__init__(tag="settings", title=_("Settings"))
        self.window = window
        self.controller = controller
        self._ = _

        # General
        general = Adw.PreferencesGroup(title=_("General"))
        labels = [label if label is not None else _("Same as system") for _code, label in LANGUAGE_OPTIONS]
        self.language_row = Adw.ComboRow(title=_("Language"), model=Gtk.StringList.new(labels))
        codes = [code for code, _label in LANGUAGE_OPTIONS]
        if controller.prefs.language in codes:
            self.language_row.set_selected(codes.index(controller.prefs.language))
        self.language_row.connect("notify::selected", self._language_chosen)
        general.add(self.language_row)

        self.autostart_row = Adw.SwitchRow(title=_("Start with the system"),
                                           subtitle=_("Waits in the tray, doesn't play by itself"),
                                           active=window.autostart_enabled())
        self._autostart_handler = self.autostart_row.connect(
            "notify::active", lambda row, _p: window.set_autostart(row.get_active()))
        general.add(self.autostart_row)

        self.popup_row = Adw.SwitchRow(title=_("Show station changes"),
                                       subtitle=_("A notification after a media key or menu switch"),
                                       active=controller.prefs.show_station_popup)
        self.popup_row.connect("notify::active", lambda row, _p: controller.set_show_station_popup(row.get_active()))
        general.add(self.popup_row)

        # Stations
        self.stations_group = Adw.PreferencesGroup(title=_("Stations"))
        self.stations_row = Adw.ActionRow(title=_("Station list"), subtitle=_("A copy in a file, e.g. for friends"))
        self.export_button = Gtk.Button(label=_("Export…"), valign=Gtk.Align.CENTER)
        self.import_button = Gtk.Button(label=_("Import…"), valign=Gtk.Align.CENTER)
        self.export_button.connect("clicked", lambda _button: self._choose_export())
        self.import_button.connect("clicked", lambda _button: self._choose_import())
        # The buttons get a row of their own: beside the text, a long translation squeezes the title to a few letters.
        buttons = Gtk.Box(spacing=6, halign=Gtk.Align.END, hexpand=True, margin_top=8, margin_bottom=8,
                          margin_start=12, margin_end=12)
        buttons.append(self.export_button)
        buttons.append(self.import_button)
        self.stations_group.add(self.stations_row)
        self.buttons_row = Adw.PreferencesRow(child=buttons, activatable=False, focusable=False)
        self.stations_group.add(self.buttons_row)

        # Statistics: a card of its own, without a heading
        statistics_group = Adw.PreferencesGroup()
        self.statistics_row = Adw.ActionRow(title=_("Statistics"),
                                            subtitle=_("Collected only on this computer, never sent anywhere"))
        self.statistics_button = Gtk.Button(label=_("Show"), valign=Gtk.Align.CENTER)
        self.statistics_button.connect("clicked", lambda _button: window.show_page("statistics"))
        self.statistics_row.add_suffix(self.statistics_button)
        self.statistics_row.set_activatable_widget(self.statistics_button)
        statistics_group.add(self.statistics_row)

        # About: the app's icon, name and version, and its page on GitHub
        about_group = Adw.PreferencesGroup(title=_("About"))
        self.about_row = Adw.ActionRow(title=APP_NAME, subtitle=f"{_('Version')} {VERSION} · MIT")
        self.about_row.add_prefix(Gtk.Image(icon_name=APP_ID, pixel_size=ICON_SIZE, valign=Gtk.Align.CENTER))
        self.website_button = Gtk.LinkButton(label="GitHub ↗", uri=WEBSITE, valign=Gtk.Align.CENTER)
        self.about_row.add_suffix(self.website_button)
        about_group.add(self.about_row)

        # Quit: a card with only the button
        quit_group = Adw.PreferencesGroup()
        self.quit_button = Gtk.Button(label=_("Quit Minimalistic Radio"), halign=Gtk.Align.START,
                                      css_classes=["destructive-action"])
        self.quit_button.connect("clicked", lambda _button: window.quit_app())
        quit_box = Gtk.Box(margin_top=8, margin_bottom=8, margin_start=12, margin_end=12)
        quit_box.append(self.quit_button)
        quit_group.add(Adw.PreferencesRow(child=quit_box, activatable=False, focusable=False))

        for widget, name in ((self.language_row, "language-row"), (self.autostart_row, "autostart-row"),
                             (self.popup_row, "popup-row"), (self.export_button, "export-button"),
                             (self.import_button, "import-button"), (self.statistics_button, "statistics-button"),
                             (self.about_row, "about-row"), (self.website_button, "website-button"),
                             (self.quit_button, "quit-button")):
            widget.set_name(name)   # the ids the tests and the screenshots find them by

        self.preferences = Adw.PreferencesPage(css_classes=["panel-preferences"])
        for group in (general, self.stations_group, statistics_group, about_group, quit_group):
            self.preferences.add(group)
        toolbar = Adw.ToolbarView(content=self.preferences)
        toolbar.add_top_bar(subpage_bar(self.get_title(), _))
        self.set_child(toolbar)

    def refresh(self, change: Change) -> None:
        """The switch follows the saved choice: the Background portal may have said no."""
        if change & Change.PREFERENCES:
            on = self.window.autostart_enabled()
            if self.autostart_row.get_active() != on:
                with self.autostart_row.handler_block(self._autostart_handler):
                    self.autostart_row.set_active(on)

    # ---- Language ----

    def _language_chosen(self, row: Adw.ComboRow, _param: object) -> None:
        code = LANGUAGE_OPTIONS[row.get_selected()][0]
        if code != self.controller.prefs.language:
            self.controller.set_language(code)
            self.window.language_changed()

    # ---- Export and import ----

    def _report(self, text: str) -> None:
        self.stations_group.set_description(text)

    def export_to(self, path: Path) -> None:
        if self.controller.export_stations(path):
            self._report(self._("Stations saved: {n}.").format(n=len(self.controller.stations)))
        else:
            self._report(self._("Couldn't save the file."))

    def import_from(self, path: Path) -> None:
        result = self.controller.import_stations(path)
        if result.error is not None:
            self._report(result.error)
        elif result.added == 0:
            self._report(self._("All stations from this file are already on the list."))
        else:
            self._report(self._("Stations added: {n}.").format(n=result.added))

    def _filters(self) -> Gio.ListStore:
        json_files = Gtk.FileFilter(name=self._("Station list") + " (*.json)")
        json_files.add_suffix("json")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(json_files)
        return store

    def _choose_export(self) -> None:
        dialog = Gtk.FileDialog(initial_name=f"{APP_NAME} - {self._('stations')}.json", filters=self._filters())

        def done(source: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
            try:
                file = source.save_finish(result)
            except GLib.Error:
                return   # cancelled
            if file is not None and file.get_path():
                self.export_to(Path(file.get_path()))

        dialog.save(self.window, None, done)

    def _choose_import(self) -> None:
        dialog = Gtk.FileDialog(filters=self._filters())

        def done(source: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
            try:
                file = source.open_finish(result)
            except GLib.Error:
                return
            if file is not None and file.get_path():
                self.import_from(Path(file.get_path()))

        dialog.open(self.window, None, done)

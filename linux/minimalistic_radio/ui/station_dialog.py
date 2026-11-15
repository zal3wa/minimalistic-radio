"""The station dialog: add a station by its address, or edit one (name, stream address, logo address)."""
from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from ..controller import AddResult  # noqa: E402
from ..core.models import Station  # noqa: E402
from ..core.streams import is_web_url  # noqa: E402


class StationDialog(Adw.Dialog):
    """`on_save(station)` returns the controller's AddResult; the dialog closes on ADDED."""

    def __init__(self, parent: Gtk.Widget, station: Station | None, on_save: Callable[[Station], AddResult],
                 _: Callable[[str], str] = lambda s: s) -> None:
        super().__init__(title=_("Edit station") if station is not None else _("Add by address"),
                         content_width=360, follows_content_size=True)
        self._ = _
        self.on_save = on_save

        self.name_row = Adw.EntryRow(title=_("Station name"))
        self.url_row = Adw.EntryRow(title=_("Stream address (HTTP or HTTPS)"))
        self.logo_row = Adw.EntryRow(title=_("Logo address (optional)"))
        if station is not None:
            self.name_row.set_text(station.name)
            self.url_row.set_text(station.url)
            self.logo_row.set_text(station.logo or "")
        group = Adw.PreferencesGroup()
        for row in (self.name_row, self.url_row, self.logo_row):
            group.add(row)
            row.connect("changed", self._edited)
            row.connect("entry-activated", self._activated)
        self.message = Gtk.Label(wrap=True, xalign=0, visible=False, css_classes=["error"])

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12, margin_bottom=12,
                       margin_start=12, margin_end=12)
        body.append(group)
        body.append(self.message)

        header = Adw.HeaderBar(show_start_title_buttons=False, show_end_title_buttons=False)
        self.cancel_button = Gtk.Button(label=_("Cancel"))
        self.cancel_button.connect("clicked", lambda _button: self.close())
        header.pack_start(self.cancel_button)
        self.save_button = Gtk.Button(label=_("Save"), css_classes=["suggested-action"])
        self.save_button.connect("clicked", lambda _button: self.save())
        header.pack_end(self.save_button)
        toolbar = Adw.ToolbarView(content=body)
        toolbar.add_top_bar(header)
        self.set_child(toolbar)
        self.set_default_widget(self.save_button)
        self.set_focus(self.name_row)
        self._edited()
        self.present(parent)

    def can_save(self) -> bool:
        return bool(self.name_row.get_text().strip()) and is_web_url(self.url_row.get_text().strip())

    def _edited(self, *_args: object) -> None:
        self.save_button.set_sensitive(self.can_save())
        self.message.set_visible(False)

    def _activated(self, _row: Adw.EntryRow) -> None:
        if self.can_save():
            self.save()

    def save(self) -> None:
        if not self.can_save():
            return
        logo = self.logo_row.get_text().strip()
        if not is_web_url(logo):
            logo = ""   # a logo address that isn't a web address is dropped
            self.logo_row.set_text("")
        result = self.on_save(Station(self.name_row.get_text().strip(), self.url_row.get_text().strip(),
                                      logo or None))
        if result == AddResult.ADDED:
            self.close()
            return
        self.message.set_label(self._("This address is already on the list.") if result == AddResult.DUPLICATE
                               else self._("Check the name and the addresses."))
        self.message.set_visible(True)

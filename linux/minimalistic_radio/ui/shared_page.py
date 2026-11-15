"""The Shared station page: a station from a share link (core/share.py), with its logo, name and stream address, and
the question whether to add and play it. Nothing is added or played without Add and play. A link without a station
shows one line instead."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, Pango  # noqa: E402

from ..controller import RadioController  # noqa: E402
from ..core.share import SharedStation, address_text  # noqa: E402
from .bars import subpage_bar  # noqa: E402
from .logos import LogoCache, LogoImage  # noqa: E402

if TYPE_CHECKING:
    from .window import RadioWindow

LOGO_SIZE = 72


def _centred(text: str = "", *classes: str, **props) -> Gtk.Label:
    return Gtk.Label(label=text, css_classes=list(classes), wrap=True, justify=Gtk.Justification.CENTER,
                     use_markup=False, **props)


class SharedPage(Adw.NavigationPage):
    def __init__(self, window: RadioWindow, controller: RadioController, logos: LogoCache,
                 _: Callable[[str], str]) -> None:
        super().__init__(tag="shared", title=_("Shared station"))
        self.window = window
        self.controller = controller
        self.station: SharedStation | None = None

        self.logo = LogoImage(logos, LOGO_SIZE)
        self.logo.set_halign(Gtk.Align.CENTER)
        self.name_label = _centred("", "title-2", margin_top=16)
        self.address_label = _centred("", "caption", "dim-label", margin_top=4,
                                      wrap_mode=Pango.WrapMode.WORD_CHAR)
        question = _centred(_("Add it to your stations and play it now?"), margin_top=16)
        self.add_button = Gtk.Button(child=Adw.ButtonContent(icon_name="media-playback-start-symbolic",
                                                             label=_("Add and play")),
                                     margin_top=20, css_classes=["pill", "suggested-action"])
        self.add_button.connect("clicked", lambda _button: self.add_and_play())
        self.cancel_button = Gtk.Button(label=_("Cancel"), margin_top=10, css_classes=["pill"])
        self.cancel_button.connect("clicked", lambda _button: self.cancel())
        card_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=28, margin_bottom=20,
                            margin_start=20, margin_end=20)
        for widget in (self.logo, self.name_label, self.address_label, question, self.add_button,
                       self.cancel_button):
            card_body.append(widget)
        self.card = Gtk.Box(css_classes=["card"], valign=Gtk.Align.START)
        self.card.append(card_body)
        card_body.set_hexpand(True)

        self.invalid = _centred(_("This link doesn't contain a station."), "dim-label", visible=False,
                                margin_top=12, margin_start=12, margin_end=12)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=12, margin_bottom=12, margin_start=12,
                       margin_end=12)
        body.append(self.card)
        body.append(self.invalid)
        scroller = Gtk.ScrolledWindow(child=Adw.Clamp(child=body, maximum_size=600), vexpand=True,
                                      hscrollbar_policy=Gtk.PolicyType.NEVER)
        toolbar = Adw.ToolbarView(content=scroller)
        toolbar.add_top_bar(subpage_bar(self.get_title(), _))
        self.set_child(toolbar)
        self.show_station(None)

    def show_station(self, station: SharedStation | None) -> None:
        """The station to ask about; None: the link didn't contain one."""
        self.station = station
        self.card.set_visible(station is not None)
        self.invalid.set_visible(station is None)
        if station is not None:
            self.logo.show_logo(station.logo)
            self.name_label.set_text(station.name)
            self.address_label.set_text(address_text(station.url))

    def add_and_play(self) -> None:
        if self.station is not None:
            self.controller.add_and_play(self.station)
        self.window.show_page("stations")

    def cancel(self) -> None:
        self.window.show_page("stations")

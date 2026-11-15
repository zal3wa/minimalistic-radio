"""The bar at the top of every page: no window title, only a ✕ on the right (whatever the system's button layout,
so no minimize or maximize), and a thin line under it. A subpage shows ‹ and its title on the left."""
from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, Pango  # noqa: E402


def close_controls(_: Callable[[str], str]) -> Gtk.WindowControls:
    """The ✕: it closes the window, which only hides it (the radio keeps playing)."""
    return Gtk.WindowControls(side=Gtk.PackType.END, decoration_layout=":close",
                              tooltip_text=_("Close (the radio keeps playing)"))


def page_bar(_: Callable[[str], str]) -> Adw.HeaderBar:
    """The stations page's bar; its buttons are packed by the window."""
    bar = Adw.HeaderBar(show_title=False, show_start_title_buttons=False, show_end_title_buttons=False,
                        css_classes=["panel-bar"])
    bar.pack_end(close_controls(_))
    return bar


def subpage_bar(title: str, _: Callable[[str], str]) -> Adw.HeaderBar:
    """‹ Title on the left (the back button comes from the navigation view), ✕ on the right."""
    bar = page_bar(_)
    bar.add_css_class("subpage-bar")
    bar.pack_start(Gtk.Label(label=title, ellipsize=Pango.EllipsizeMode.END, css_classes=["heading", "page-title"]))
    return bar

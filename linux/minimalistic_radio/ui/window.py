"""The panel window."""
from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402


class RadioWindow(Adw.ApplicationWindow):
    def __init__(self, controller, _: Callable[[str], str] = lambda s: s, application=None) -> None:
        super().__init__(application=application)

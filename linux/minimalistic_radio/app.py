"""The application: one instance per user, living in the background.

Closing the window only hides it (the radio keeps playing); Quit ends the application.
A second launch presents the window of the first. The window itself comes from _create_window().
"""
from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, APP_NAME  # noqa: E402
from .audio.player import GstPlayer  # noqa: E402
from .controller import RadioController  # noqa: E402
from .core import net  # noqa: E402
from .core.storage import default_paths  # noqa: E402
from .glib_scheduler import GLibScheduler  # noqa: E402

COVER_LIMIT = 5_000_000


def _deliver(cb: Callable[[Any], None], value: Any) -> None:
    """Calls back on the GLib main loop."""
    def run() -> bool:
        cb(value)
        return GLib.SOURCE_REMOVE
    GLib.idle_add(run)


def fetch(url: str, cb: Callable[[Any | None], None]) -> None:
    """JSON from the network without blocking the main loop; None on any failure."""
    def work() -> None:
        try:
            result = net.fetch_json(url, 10)
        except Exception:
            result = None
        _deliver(cb, result)
    threading.Thread(target=work, daemon=True).start()


def fetch_file(url: str, path: Path, cb: Callable[[bool], None]) -> None:
    """Downloads to `path` without blocking. The file appears whole (a temporary file renamed into place) or not at all."""
    def work() -> None:
        temp = None
        ok = False
        try:
            data = net.fetch_bytes(url, 10, COVER_LIMIT)
            fd, temp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".part")
            with os.fdopen(fd, "wb") as file:
                file.write(data)
            os.replace(temp, path)
            temp = None
            ok = True
        except Exception:
            ok = False
        finally:
            if temp is not None:
                try:
                    os.remove(temp)
                except OSError:
                    pass
        _deliver(cb, ok)
    threading.Thread(target=work, daemon=True).start()


class RadioApplication(Adw.Application):
    def __init__(self, translate: Callable[[str], str] = lambda s: s, application_id: str = APP_ID) -> None:
        super().__init__(application_id=application_id, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self._ = translate
        self.controller: RadioController | None = None
        self.window: Gtk.ApplicationWindow | None = None
        self.tray = None      # Task 10
        self.mpris = None     # Task 11
        self.updated = False
        self.screenshot_dir: str | None = None
        self._started = False

        _ = translate
        self.add_main_option("autostart", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             _("Start hidden, as when the session starts"), None)
        self.add_main_option("updated", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             _("Started again after an update"), None)
        self.add_main_option("self-test", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             _("Start, check that the window opens, and exit"), None)
        self.add_main_option("screenshot", 0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING,
                             _("Save screenshots of the pages in DIR and exit"), "DIR")

    # ---- Start-up ----

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        # self.hold()   # EXPERIMENT: removed to prove the app tests fail without it
        self._add_action("show-panel", self.show_window)
        self._add_action("toggle", lambda: self.controller.toggle())
        self._add_action("quit", self.quit)
        self._add_action("settings", lambda: self._open_page("settings"))
        self._add_action("history", lambda: self._open_page("history"))
        self._add_action("add-station", lambda: self._open_page("add-station"))
        self.set_accels_for_action("app.quit", ["<Ctrl>q"])
        self.set_accels_for_action("window.close", ["<Ctrl>w"])

    def _add_action(self, name: str, handler: Callable[[], None]) -> None:
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", lambda *_args: handler())
        self.add_action(action)

    def _start_radio(self, autostart: bool) -> None:
        if self._started:
            return
        self._started = True
        player = GstPlayer(
            on_started=lambda: self.controller.on_player_started(),
            on_title=lambda raw: self.controller.on_player_title(raw),
            on_error=lambda kind, detail: self.controller.on_player_error(kind, detail),
            on_eos=lambda: self.controller.on_player_eos(),
            _=self._)
        self.controller = RadioController(player, GLibScheduler(), default_paths(), fetch, fetch_file, self._)
        self.controller.start(autostart=autostart)

    def do_handle_local_options(self, options: GLib.VariantDict) -> int:
        # A self-test or screenshot run is its own instance: never handed to (and quitting) a running radio.
        if options.contains("self-test") or options.contains("screenshot"):
            self.set_flags(self.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)
        return -1

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        options = command_line.get_options_dict()
        autostart = options.contains("autostart")
        self.updated = options.contains("updated")
        shots = options.lookup_value("screenshot", GLib.VariantType("s"))
        self.screenshot_dir = shots.get_string() if shots is not None else None
        checking = options.contains("self-test") or self.screenshot_dir is not None
        self._start_radio(autostart or checking)   # a check never plays
        if options.contains("self-test"):
            self.show_window()
            print("self-test ok")
            GLib.idle_add(self._quit_idle)
        elif not autostart:
            self.show_window()
        return 0

    def _quit_idle(self) -> bool:
        self.quit()
        return GLib.SOURCE_REMOVE

    def do_shutdown(self) -> None:
        # A clean exit, like Shutdown on Windows: the stream is closed before the process ends.
        if self.controller is not None:
            self.controller.player.stop()
        Adw.Application.do_shutdown(self)

    def do_activate(self) -> None:
        # From the desktop (not the command line): the first launch behaves like a normal one.
        self._start_radio(False)
        self.show_window()

    # ---- The window ----

    def _create_window(self) -> Gtk.ApplicationWindow:
        """A placeholder: the real window replaces it (Task 9)."""
        return Adw.ApplicationWindow(application=self, title=APP_NAME, default_width=360, default_height=520)

    def show_window(self) -> None:
        if self.window is None:
            self.window = self._create_window()
            self.window.set_hide_on_close(True)
        self.window.present()

    def _open_page(self, page: str) -> None:
        self.show_window()
        opener = getattr(self.window, "open_page", None)
        if opener is not None:
            opener(page)

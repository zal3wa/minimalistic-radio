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

from . import APP_ID, VERSION, i18n  # noqa: E402
from .audio.player import GstPlayer  # noqa: E402
from .controller import Change, RadioController  # noqa: E402
from .core import net  # noqa: E402
from .core.share import is_share_link  # noqa: E402
from .core.storage import default_paths  # noqa: E402
from .glib_scheduler import GLibScheduler  # noqa: E402
from .platform.background import Autostart  # noqa: E402
from .platform.inhibit import SuspendInhibitor  # noqa: E402
from .platform.mpris import MprisService  # noqa: E402
from .platform.notifications import StationNotifier  # noqa: E402
from .platform.session import SessionWatcher  # noqa: E402
from .platform.tray import TrayIcon  # noqa: E402
from .platform.updates import UpdateMonitor  # noqa: E402
from .ui.logos import LogoCache  # noqa: E402
from .ui.window import RadioWindow  # noqa: E402

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
    """Downloads a cover picture to `path` without blocking (never from the local network). The file appears whole
    (a temporary file renamed into place) or not at all."""
    def work() -> None:
        temp = None
        ok = False
        try:
            data = net.fetch_picture(url, COVER_LIMIT)
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
    def __init__(self, translate: Callable[[str], str] = i18n.gettext, application_id: str = APP_ID) -> None:
        # ALLOW_REPLACEMENT: the version started after an update (--updated) takes over the name at once.
        super().__init__(application_id=application_id,
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE | Gio.ApplicationFlags.ALLOW_REPLACEMENT)
        self._ = translate
        self.controller: RadioController | None = None
        self.window: RadioWindow | None = None
        self.logos: LogoCache | None = None   # one for the whole run: a window built again keeps the pictures
        self.tray: TrayIcon | None = None
        self.mpris: MprisService | None = None
        self.session: SessionWatcher | None = None
        self.notifier: StationNotifier | None = None
        self.inhibitor = SuspendInhibitor(lambda s: self._(s))
        self.updated = False
        self.updates: UpdateMonitor | None = None
        self.screenshot_dir: str | None = None
        self._started = False

        _ = translate
        self.add_main_option("autostart", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             _("Start hidden, as when the session starts"), None)
        self.add_main_option("updated", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             _("Started again after an update"), None)
        self.add_main_option("stopped", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             _("Open the window without playing"), None)
        self.add_main_option("self-test", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             _("Start, check that the window opens, and exit"), None)
        self.add_main_option("screenshot", 0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING,
                             _("Save screenshots of the pages in DIR and exit"), "DIR")
        # Test-only, for CI's pictures of the tray menu on a real desktop: hidden from --help, never translated.
        self.add_main_option("demo-track", 0, GLib.OptionFlags.HIDDEN, GLib.OptionArg.STRING,
                             "Play nothing: the last station seems to play, with TEXT as its song", "TEXT")

    # ---- Start-up ----

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self.hold()   # closing the window never ends the application
        self._add_action("show-panel", self.show_window)
        self._add_action("toggle", lambda: self.controller.toggle())
        self._add_action("quit", self.quit)
        self._add_action("update", lambda: self.updates.apply() if self.updates else None)
        self._add_action("settings", lambda: self._open_page("settings"))
        self._add_action("history", lambda: self._open_page("history"))
        self._add_action("add-station", lambda: self._open_page("search"))
        self.set_accels_for_action("app.quit", ["<Ctrl>q"])
        self.set_accels_for_action("window.close", ["<Ctrl>w"])

    def _add_action(self, name: str, handler: Callable[[], None]) -> None:
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", lambda *_args: handler())
        self.add_action(action)

    def _start_radio(self, autostart: bool, demo_track: str | None = None) -> None:
        if self._started:
            return
        self._started = True
        if demo_track is None:
            player = GstPlayer(
                on_started=lambda: self.controller.on_player_started(),
                on_title=lambda raw: self.controller.on_player_title(raw),
                on_error=lambda kind, detail: self.controller.on_player_error(kind, detail),
                on_eos=lambda: self.controller.on_player_eos(),
                _=self._)
            get_json, get_file = fetch, fetch_file
        else:   # --demo-track: no sound and no network, so the song shown stays the one given
            from .selftest import SilentPlayer
            player, get_json, get_file = SilentPlayer(), (lambda url, cb: None), (lambda url, path, cb: None)
        self.controller = RadioController(player, GLibScheduler(), default_paths(), get_json, get_file, self._)
        self.controller.subscribe(self._playback_changed)   # before start(): it may begin playing
        self.controller.start(autostart=autostart)
        if demo_track is not None:
            from .selftest import play_demo
            play_demo(self.controller, demo_track)
        self.mpris = MprisService(self)
        self.mpris.publish()
        self.tray = TrayIcon(self)
        self.tray.start()
        self.notifier = StationNotifier(self)
        self.session = SessionWatcher(self.controller)
        self._start_updates()

    def _start_updates(self, flatpak_info: str = "/.flatpak-info") -> None:
        """Only in a Flatpak: the arrow and the tray item follow the portal's update monitor."""
        if self.updates is not None or not os.path.exists(flatpak_info):
            return
        self.updates = UpdateMonitor(self, flatpak_info)
        self.updates.connect_changed(self._update_changed)
        self.updates.start()

    def update_label(self) -> str | None:
        state = self.updates.state if self.updates else None
        return {"update": self._("Update"), "restart": self._("Restart to update")}.get(state)

    def _update_changed(self, _state: str | None) -> None:
        if self.window is not None:
            self.window.set_update(self.update_label())
        if self.tray is not None:
            self.tray.update_label = self.update_label()
            self.tray.refresh()

    def _playback_changed(self, change: Change) -> None:
        """Playing keeps the computer from suspending, like the Windows version."""
        if not change & Change.STATE:
            return
        if self.controller.active:
            self.inhibitor.hold()
        else:
            self.inhibitor.release()

    def _window_closing(self, _window: Gtk.Window) -> bool:
        """The first time the window is closed (✕, Escape, Ctrl+W): it says that the radio keeps playing."""
        controller = self.controller
        if not controller.prefs.no_tray_hint_shown:
            controller.set_no_tray_hint_shown()
            note = Gio.Notification.new(self._("The radio keeps playing"))
            if self.tray is not None and self.tray.visible:
                note.set_body(self._("Open it again from the tray icon."))
            else:
                note.set_body(self._("Open it again from your apps, or control it from the clock menu."))
            note.set_default_action("app.show-panel")
            self.send_notification("no-tray-hint", note)
        return False   # the window hides, as before

    def do_handle_local_options(self, options: GLib.VariantDict) -> int:
        # A self-test or screenshot run is its own instance: never handed to (and quitting) a running radio.
        if options.contains("self-test") or options.contains("screenshot"):
            self.set_flags(self.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)
        # The new version after an update: the old one may not have quit yet, and must not get this launch.
        elif options.contains("updated"):
            self.set_flags(self.get_flags() | Gio.ApplicationFlags.REPLACE)
        return -1

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        options = command_line.get_options_dict()
        autostart = options.contains("autostart")
        self.updated = options.contains("updated")
        shots = options.lookup_value("screenshot", GLib.VariantType("s"))
        self.screenshot_dir = shots.get_string() if shots is not None else None
        if options.contains("self-test") or self.screenshot_dir is not None:
            # A check runs on temporary data: no radio, no tray, no MPRIS, nothing plays.
            from . import selftest
            if self.screenshot_dir is not None:
                code = selftest.take_screenshots(self, Path(self.screenshot_dir))
            else:
                code = selftest.run_self_test(self)
                if code == 0:
                    print("self-test ok")
            GLib.idle_add(self._quit_idle)
            return code
        demo = options.lookup_value("demo-track", GLib.VariantType("s"))
        # A share link (the desktop file's %u: a link opened in the browser, or minimalistic-radio <link>). The
        # first launch then doesn't play the last station: the link's page asks what to play. A second launch
        # hands its arguments to this instance over D-Bus, so they arrive here too.
        link = next((arg for arg in command_line.get_arguments()[1:] if is_share_link(arg)), None)
        self._start_radio(autostart or options.contains("stopped") or link is not None,
                          demo.get_string() if demo is not None else None)
        if link is not None:
            self.show_window()
            self.window.open_link(link)
        elif not autostart:
            self.show_window()
            if self.updated:
                self.window.toast(self._("Updated to version {VERSION}.").replace("{VERSION}", VERSION))
        return 0

    def _quit_idle(self) -> bool:
        self.quit()
        return GLib.SOURCE_REMOVE

    def do_shutdown(self) -> None:
        # A clean exit, like Shutdown on Windows: the stream is closed before the process ends.
        self.inhibitor.release()
        if self.session is not None:
            self.session.close()
        if self.notifier is not None:
            self.notifier.close()
            self.notifier.withdraw()
        if self.mpris is not None:
            self.mpris.unpublish()
        if self.tray is not None:
            self.tray.stop()
        if self.controller is not None:
            self.controller.shutdown()   # the listening statistics end here and are saved
            self.controller.player.stop()
        Adw.Application.do_shutdown(self)

    def do_activate(self) -> None:
        # From the desktop (not the command line): the first launch behaves like a normal one.
        self._start_radio(False)
        self.show_window()

    # ---- The window ----

    def _create_window(self) -> RadioWindow:
        if self.logos is None:
            self.logos = LogoCache(self.controller.paths.cache / "logos")
        return RadioWindow(self.controller, self._, application=self, logos=self.logos)

    def show_window(self, startup_id: str | None = None) -> None:
        """`startup_id`: the desktop's activation token (the tray's), so Wayland lets the window take the focus."""
        if self.window is None:
            self._start_radio(True)   # an action from outside before any launch: the radio, but not playing
            self.window = self._create_window()
            self.window.set_hide_on_close(True)
            self.window.connect("close-request", self._window_closing)
            self.window.set_update(self.update_label())
        if startup_id:
            self.window.set_startup_id(startup_id)
        self.window.present()

    def rebuild_window(self, page: str) -> None:
        """Every label is made in the chosen language: the window is built again, on `page`, and the tray menu."""
        from . import main

        def rebuild() -> bool:
            # The controller, the player and the tray translate through i18n.gettext: they follow at once.
            i18n.install(self.controller.prefs.language, main.LOCALEDIR)
            old, self.window = self.window, None
            if old is not None:
                old.destroy()
            self.show_window()
            self.window.show_page(page)
            if self.tray is not None:
                self.tray.update_label = self.update_label()
                self.tray.refresh()
            return GLib.SOURCE_REMOVE
        GLib.idle_add(rebuild)   # not from inside the signal of a widget that is about to be destroyed

    # ---- Start with the system ----

    def autostart_enabled(self) -> bool:
        return Autostart(self.controller).enabled()

    def set_autostart(self, on: bool) -> None:
        Autostart(self.controller).set(on)

    def _open_page(self, page: str) -> None:
        self.show_window()
        self.window.show_page(page)

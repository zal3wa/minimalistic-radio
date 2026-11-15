"""--self-test and --screenshot: the real window, tray menu and MPRIS object on temporary data.

Neither plays anything or touches the user's files, the running radio or the network.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from . import i18n  # noqa: E402
from .controller import RadioController  # noqa: E402
from .core import directory  # noqa: E402
from .core.models import Station  # noqa: E402
from .core.storage import Paths, save_stations  # noqa: E402
from .glib_scheduler import GLibScheduler  # noqa: E402
from .platform.menu_model import build_tray_menu  # noqa: E402
from .platform.mpris import MprisService  # noqa: E402
from .ui.window import PAGES, RadioWindow  # noqa: E402

STATIONS = [("Radio 357", "http://s0.example/live"), ("RMF FM", "http://s1.example/live"),
            ("Polskie Radio Trójka", "http://s2.example/live"), ("Radio Nowy Świat", "http://s3.example/live"),
            ("Jazz Radio", "http://s4.example/live"), ("Chillizet", "http://s5.example/live")]
SONGS = ["Nina Simone - Feeling Good", "Miles Davis - So What", "Leonard Cohen - Everybody Knows"]
FIXTURE = Path(__file__).with_name("selftest_data") / "search-jazz.json"


class SilentPlayer:
    def play(self, url: str) -> None: pass
    def stop(self) -> None: pass
    def set_volume(self, percent: int) -> None: pass


class _AppStub:
    """What MprisService needs from the application."""
    def __init__(self, controller: RadioController) -> None:
        self.controller = controller


def pump(ms: int) -> None:
    context = GLib.MainContext.default()
    deadline = time.monotonic() + ms / 1000
    while time.monotonic() < deadline:
        context.iteration(False)
        time.sleep(0.005)


def _controller(folder: Path, stations: list[tuple[str, str]]) -> RadioController:
    paths = Paths(folder / "config", folder / "data", folder / "cache")
    save_stations(paths.config / "stations.json", [Station(name, url) for name, url in stations])
    controller = RadioController(SilentPlayer(), GLibScheduler(), paths, lambda url, cb: None,
                                 lambda url, path, cb: None)
    controller.start(autostart=True)   # never plays
    return controller


def _check(condition: bool, reason: str) -> None:
    if not condition:
        raise AssertionError(reason)


def _check_polish() -> None:
    from . import main
    saved = i18n._translation
    try:
        _ = i18n.install("pl", main.LOCALEDIR)
        _check(_("Play") == "Odtwórz", "the Polish catalogue did not load from " + main.LOCALEDIR)
    finally:
        i18n._translation = saved


def run_self_test(app: Any) -> int:
    """0 when the window and every page, the tray menu, the MPRIS object and the Polish catalogue work."""
    try:
        Adw.init()
        translate = getattr(app, "_", lambda s: s)
        with tempfile.TemporaryDirectory() as folder:
            controller = _controller(Path(folder), STATIONS[:2])
            window = RadioWindow(controller, translate)
            window.present()
            pump(300)
            for tag in PAGES:
                window.show_page(tag)
                pump(50)
                visible = window.navigation.get_visible_page()
                _check(visible is not None and visible.get_tag() == tag, f"page {tag} did not open")
            window.destroy()
            ids = [item.id for item in build_tray_menu(controller, translate, None)]
            _check({"playback", "stations", "volume", "sleep", "settings", "quit"} <= set(ids),
                   f"the tray menu is incomplete: {ids}")
            mpris = MprisService(_AppStub(controller))
            _check("PlaybackStatus" in mpris._player_properties(), "the MPRIS object has no playback status")
        _check_polish()
    except Exception as error:   # the reason goes to stderr, whatever it is
        print(f"self-test failed: {error!r}", file=sys.stderr)
        return 1
    return 0


def _render(window: Gtk.Window, path: Path) -> None:
    paintable = Gtk.WidgetPaintable.new(window)
    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, window.get_width(), window.get_height())
    texture = window.get_renderer().render_texture(snapshot.to_node(), None)
    texture.save_to_png(str(path))
    print("wrote", path)


def _prepare(window: RadioWindow, page: str) -> None:
    window.show_page(page)
    if page == "search":
        search = window.search_page
        search._suggested = ([], [], None)   # no suggestions: nothing goes to the network
        search.entry.set_text("jazz")
        found = directory.parse_results(json.loads(FIXTURE.read_text(encoding="utf-8")))
        search._found(search._generation, found)


def take_screenshots(app: Any, folder: Path) -> int:
    """Writes linux-<page>-<light|dark>.png for the stations, search, history and settings pages."""
    try:
        Adw.init()
        translate = getattr(app, "_", lambda s: s)
        folder.mkdir(parents=True, exist_ok=True)
        styles = Adw.StyleManager.get_default()
        with tempfile.TemporaryDirectory() as temp:
            controller = _controller(Path(temp), STATIONS)
            for song in SONGS[:-1]:
                controller.on_player_title(song)
            controller.select(0)
            controller.play()
            controller.on_player_started()
            controller.on_player_title(SONGS[-1])
            window = RadioWindow(controller, translate)
            window.present()
            pump(600)
            for scheme, look in ((Adw.ColorScheme.FORCE_LIGHT, "light"), (Adw.ColorScheme.FORCE_DARK, "dark")):
                styles.set_color_scheme(scheme)
                for page in PAGES:
                    _prepare(window, page)
                    pump(600)
                    _render(window, folder / f"linux-{page}-{look}.png")
            window.destroy()
    except Exception as error:
        print(f"screenshots failed: {error!r}", file=sys.stderr)
        return 1
    return 0

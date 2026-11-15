"""--self-test and --screenshot: the real window, tray menu and MPRIS object on temporary data.

Neither plays anything or touches the user's files or the running radio. The self-test stays off the network.
The screenshots show what the Windows README pictures show (the same stations, songs and cover), so like
those they get the logos, the cover and the search results from the network.
Also the silent player behind the test-only --demo-track, which CI uses for pictures of the tray menu.
"""
from __future__ import annotations

import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from . import i18n  # noqa: E402
from .controller import RadioController  # noqa: E402
from .core import directory  # noqa: E402
from .core.models import HistoryEntry, ListeningSession, SongPlay, Station, Statistics  # noqa: E402
from .core.statistics import Period  # noqa: E402
from .core.storage import Paths, save_history, save_stations  # noqa: E402
from .glib_scheduler import GLibScheduler  # noqa: E402
from .pictures import picture  # noqa: E402
from .platform.menu_model import build_tray_menu  # noqa: E402
from .platform.mpris import MprisService  # noqa: E402
from .ui.window import HISTORY_ICON, PAGES, RadioWindow  # noqa: E402

TEST_STATIONS = [Station("Radio 357", "http://s0.example/live"), Station("RMF FM", "http://s1.example/live")]

# The Windows README pictures (TakeScreenshots in src/Radio/RadioApp.cs): their station list, the third one
# playing, the songs in the history and the search.
SHOT_STATIONS = [
    Station("102.7 KIIS FM Los Angeles", "http://stream.revma.ihrhls.com/zc185",
            "https://i.iheart.com/v3/re/assets.brands/61d4a04fc786e58c38995162"
            "?ops=gravity(%22center%22),contain(360,360)&quality=80"),
    Station("Radio Nowy Świat", "https://stream.nowyswiat.online/mp3",
            "https://dabplus.live/logo/ea4141ebdcca43ef81e6f8e7351b4309.png"),
    Station("Antyradio Hard", "https://an05.cdn.eurozet.pl/ANTHAR.mp3",
            "https://gfx-player.radiozet.pl/var/player/storage/images/player-antyradio/kanaly-muzyczne/"
            "antyradio-hard/710016-10-pol-PL/Antyradio-Hard_size-228x228.jpg"),
    Station("Radio 357", "https://stream.radio357.pl/",
            "https://radio357.pl/wp-content/uploads/2022/04/c5399c0d-1b8e-43d5-b23b-e5cef1857856.png"),
    Station("RMF Classic", "http://31.192.216.8/RMFCLASSIC48"),
    Station("RMF Classic Rock", "https://rs201-krk.rmfstream.pl/rmf_classic_rock",
            "https://www.rmfon.pl/assets/images/favicon/apple-touch-icon.png"),
    Station("Polskie Radio Jedynka AAC", "http://stream3.polskieradio.pl:8950/;.mp3"),
    Station("Polskie Radio - Czwórka (Program 4) (AAC+)", "http://stream3.polskieradio.pl:8956/;"),
]
SHOT_PLAYING = 2
# (song, station) from the oldest; the last one is playing.
SHOT_SONGS = [("Daughtry - What About Now", 7), ("Dawid Podsiadło - Małomiasteczkowy", 5),
              ("Queen - A Kind Of Magic", 4), ("Editors - Shadow", 3), ("Leonard Cohen - Everybody Knows", 2)]
SHOT_SEARCH = "jazz"
NETWORK_WAIT = 20   # seconds at most for a page's logos, cover or search results
SAMPLE_SONGS = ["Leonard Cohen - Everybody Knows", "Editors - Shadow", "Queen - A Kind Of Magic",
                "Leonard Cohen - Hallelujah", "Dawid Podsiadło - Małomiasteczkowy", "Queen - Bohemian Rhapsody",
                "Daughtry - What About Now", "Editors - Papillon", "Metallica - Nothing Else Matters",
                "Leonard Cohen - Suzanne", "Kult - Arahja", "Radio jingle"]
LONG_PAGES = ("settings", "statistics")   # pictured a second time, scrolled to the end


class SilentPlayer:
    def play(self, url: str) -> None: pass
    def stop(self) -> None: pass
    def set_volume(self, percent: int) -> None: pass


class _AppStub:
    """What MprisService needs from the application."""
    def __init__(self, controller: RadioController) -> None:
        self.controller = controller


def play_demo(controller: RadioController, track: str) -> None:
    """--demo-track (test-only): the chosen station seems to play, silently, with `track` as its song. The
    application gives the controller a SilentPlayer and no network for it."""
    controller.play()
    controller.on_player_started()
    if controller.active:
        controller._show_track(track)


def pump(ms: int) -> None:
    context = GLib.MainContext.default()
    deadline = time.monotonic() + ms / 1000
    while time.monotonic() < deadline:
        context.iteration(False)
        time.sleep(0.005)


def _wait(ready: Callable[[], bool], seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while not ready() and time.monotonic() < deadline:
        pump(50)


def _controller(folder: Path, stations: list[Station], history: list[HistoryEntry] | None = None,
                network: bool = False) -> RadioController:
    paths = Paths(folder / "config", folder / "data", folder / "cache")
    save_stations(paths.config / "stations.json", stations)
    if history:
        save_history(paths.data / "history.json", history)
    if network:
        from .app import fetch, fetch_file
        get_json, get_file = fetch, fetch_file
    else:
        get_json, get_file = (lambda url, cb: None), (lambda url, path, cb: None)
    controller = RadioController(SilentPlayer(), GLibScheduler(), paths, get_json, get_file)
    controller.start(autostart=True)   # never plays
    return controller


def sample_statistics(stations: list[Station], now: datetime, days: int = 75) -> Statistics:
    """Evenings of listening over the last `days` days, for the Statistics page's picture and check: the first three
    stations with song titles (in `SAMPLE_SONGS`), the rest without."""
    stats = Statistics()
    plan = [(2, 95), (3, 70), (5, 45), (1, 30), (0, 20)]   # (station, minutes an evening)
    local_now = now.astimezone()
    for day in range(days, -1, -1):
        when = (local_now - timedelta(days=day)).replace(second=0, microsecond=0)
        for order, (index, minutes) in enumerate(plan):
            if (day + order) % 4 == 3:
                continue   # not every station every evening
            start = when.replace(hour=(17 + 2 * order + day % 3) % 24, minute=(day * 7) % 60)
            end = start + timedelta(minutes=minutes + (day % 5) * 6)
            station = stations[index % len(stations)]
            titled = order < 3
            stats.sessions.append(ListeningSession(station.name, station.url, start.astimezone(timezone.utc),
                                                   end.astimezone(timezone.utc), titled))
            if titled:
                for number, song_at in enumerate(range(0, int((end - start).total_seconds()), 240)):
                    song = SAMPLE_SONGS[(day * 3 + number * (order + 1)) % len(SAMPLE_SONGS)]
                    stats.songs.append(SongPlay(station.name, song, (start + timedelta(seconds=song_at))
                                                .astimezone(timezone.utc)))
    stats.sessions.sort(key=lambda s: s.start)
    stats.songs.sort(key=lambda s: s.time)
    return stats


def _check(condition: bool, reason: str) -> None:
    if not condition:
        raise AssertionError(reason)


def _check_statistics(window: RadioWindow) -> None:
    """The Statistics page with data, in each period (libadwaita's toggle group where there is one)."""
    controller = window.controller
    sample = sample_statistics(controller.stations, datetime.now(timezone.utc), days=40)
    controller.statistics.sessions[:] = sample.sessions
    controller.statistics.songs[:] = sample.songs
    page = window.statistics_page
    window.show_page("statistics")
    pump(50)
    _check(window.shown_pages() == ["stations", "settings", "statistics"], "Statistics doesn't open over Settings")
    for period in (Period.ALL, Period.YEAR, Period.MONTH):
        page.switch.select(period)
        page._period_chosen(period)
        pump(20)
        _check(page.stack.get_visible_child_name() == "data" and page.stations_list.get_row_at_index(0) is not None,
               f"the Statistics page shows nothing for {period.value}")
    controller.clear_statistics()
    pump(20)
    _check(page.stack.get_visible_child_name() == "empty", "the Statistics page isn't empty after clearing")
    theme = Gtk.IconTheme.get_for_display(window.get_display())
    _check(theme.has_icon(HISTORY_ICON), "the History button's icon is missing")


def _check_polish() -> None:
    from . import main
    saved = i18n._translation
    try:
        _ = i18n.install("pl", main.LOCALEDIR)
        _check(_("Play") == "Odtwórz", "the Polish catalogue did not load from " + main.LOCALEDIR)
    finally:
        i18n._translation = saved


def _check_bans() -> None:
    """main() loaded the ban list (the installed one): Radio Republika is hidden by its address and by its name."""
    by_host = directory.DirectoryStation("Republika Live", "Poland", "https://stream.radiotvrepublika.pl/live",
                                         None, "MP3", 128, "", country_code="PL")
    by_name = directory.DirectoryStation("Radio Republika", "Poland", "https://stream.example/republika",
                                         None, "MP3", 128, "", country_code="PL")
    _check(directory.is_hidden(by_host) and directory.is_hidden(by_name),
           "the banned-stations list is not loaded: Radio Republika would be shown")


def _check_pictures() -> None:
    """A PNG logo decodes and shrinks: in the Flatpak, gdk-pixbuf's decoders may not start (pictures.py)."""
    red = GLib.Bytes.new(bytes([200, 30, 30, 255]) * 16 * 16)
    png = Gdk.MemoryTexture.new(16, 16, Gdk.MemoryFormat.R8G8B8A8, red, 16 * 4).save_to_png_bytes()
    small = picture(png.get_data(), 8)
    _check(small is not None and (small.get_width(), small.get_height()) == (8, 8), "a PNG logo doesn't decode")


def run_self_test(app: Any) -> int:
    """0 when the window and every page, the tray menu, the MPRIS object, the ban list, logos and the Polish
    catalogue work."""
    try:
        Adw.init()
        _check_bans()
        _check_pictures()
        translate = getattr(app, "_", lambda s: s)
        with tempfile.TemporaryDirectory() as folder:
            controller = _controller(Path(folder), TEST_STATIONS)
            window = RadioWindow(controller, translate)
            window.present()
            pump(300)
            for tag in PAGES:
                window.show_page(tag)
                pump(50)
                visible = window.navigation.get_visible_page()
                _check(visible is not None and visible.get_tag() == tag, f"page {tag} did not open")
            _check_statistics(window)
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
    """At the display's scale: with GDK_SCALE=2 (as CI takes them) the pictures are as sharp as on a 4K screen."""
    scale = window.get_scale_factor()
    paintable = Gtk.WidgetPaintable.new(window)
    snapshot = Gtk.Snapshot()
    snapshot.scale(scale, scale)
    paintable.snapshot(snapshot, window.get_width(), window.get_height())
    texture = window.get_renderer().render_texture(snapshot.to_node(), None)
    texture.save_to_png(str(path))
    print("wrote", path)


def _scroll(page: Gtk.Widget, to_end: bool) -> None:
    """Scrolls the page's list to its start, or to its end (the second picture of a long page)."""
    pending = [page]
    while pending:
        widget = pending.pop(0)
        if isinstance(widget, Gtk.ScrolledWindow):
            adjustment = widget.get_vadjustment()
            adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size() if to_end
                                 else adjustment.get_lower())
            return
        child = widget.get_first_child()
        while child is not None:
            pending.append(child)
            child = child.get_next_sibling()


def _prepare(window: RadioWindow, page: str) -> None:
    if page == "search":
        window.search_page._suggested = ([], [], None)   # no suggestions: the search replaces them at once
    window.show_page(page)
    if page == "search":
        window.search_page.entry.set_text(SHOT_SEARCH)
        window.search_page.search()


def _arrived(window: RadioWindow, page: str) -> bool:
    """Whether what the page gets from the network is there (or has failed): logos, the cover, search results."""
    logos = window.logos
    if page == "stations":
        return (window.controller.cover_path is not None
                and all(logos.lookup(station.logo)[0] for station in window.controller.stations))
    if page == "search":
        search = window.search_page
        if search.status.get_visible() and search.status.get_label() == search._("Searching…"):
            return False
        return all(logos.lookup(row.entry.logo)[0] for row in search.rows)
    return True


def take_screenshots(app: Any, folder: Path) -> int:
    """Writes linux-<page>-<light|dark>.png for every page (the stations, search, history, settings and statistics
    pages), and linux-<page>-end-<light|dark>.png for the long ones scrolled to their end. The statistics are a
    sample made up in memory."""
    styles = None
    try:
        Adw.init()
        translate = getattr(app, "_", lambda s: s)
        folder.mkdir(parents=True, exist_ok=True)
        styles = Adw.StyleManager.get_default()
        with tempfile.TemporaryDirectory() as temp:
            now = datetime.now()
            older = [HistoryEntry(song, SHOT_STATIONS[station].name, now)
                     for song, station in reversed(SHOT_SONGS[:-1])]   # newest first, as in history.json
            controller = _controller(Path(temp), SHOT_STATIONS, older, network=True)
            sample = sample_statistics(SHOT_STATIONS, datetime.now(timezone.utc))   # in memory only
            controller.statistics.sessions[:] = sample.sessions
            controller.statistics.songs[:] = sample.songs
            controller.select(SHOT_PLAYING)
            controller.play()
            controller.on_player_started()
            controller.on_player_title(SHOT_SONGS[-1][0])   # joins the history and looks for its cover
            window = RadioWindow(controller, translate)
            window.present()
            pump(600)
            for scheme, look in ((Adw.ColorScheme.FORCE_LIGHT, "light"), (Adw.ColorScheme.FORCE_DARK, "dark")):
                styles.set_color_scheme(scheme)
                for page in PAGES:
                    _prepare(window, page)
                    _wait(lambda page=page: _arrived(window, page), NETWORK_WAIT)
                    _scroll(window.navigation.get_visible_page(), to_end=False)
                    pump(600)
                    _render(window, folder / f"linux-{page}-{look}.png")
                    if page in LONG_PAGES:
                        _scroll(window.navigation.get_visible_page(), to_end=True)
                        pump(400)
                        _render(window, folder / f"linux-{page}-end-{look}.png")
            window.destroy()
    except Exception as error:
        print(f"screenshots failed: {error!r}", file=sys.stderr)
        return 1
    finally:
        if styles is not None:
            styles.set_color_scheme(Adw.ColorScheme.DEFAULT)   # the system's light or dark again
    return 0

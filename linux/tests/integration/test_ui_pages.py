"""The history and settings pages (Task 13). File dialogs are not driven: the pages' export_to and
import_from are what the dialogs call with the chosen path."""
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import pytest

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from minimalistic_radio import VERSION, i18n  # noqa: E402
from minimalistic_radio.controller import Change, RadioController  # noqa: E402
from minimalistic_radio.core.models import HistoryEntry, ListeningSession, SongPlay, Station  # noqa: E402
from minimalistic_radio.core.statistics import Period  # noqa: E402
from minimalistic_radio.core.storage import Paths, save_stations  # noqa: E402
from minimalistic_radio.glib_scheduler import GLibScheduler  # noqa: E402
from minimalistic_radio.selftest import SHOT_STATIONS, sample_statistics  # noqa: E402
from minimalistic_radio.ui.window import PAGES, RadioWindow  # noqa: E402
from test_ui_main import FakePlayer, descendants, make, menu_labels, run_loop, texts, wait_for  # noqa: E402,F401

ROOT = Path(__file__).resolve().parents[2]   # linux/


@pytest.fixture
def launched(monkeypatch):
    uris = []

    class FakeLauncher:
        def __init__(self, uri):
            uris.append(uri)

        def launch(self, *_args):
            pass

    monkeypatch.setattr(Gtk, "UriLauncher", FakeLauncher)
    return uris


def test_history_rows(make, launched):
    window, controller = make()
    page = window.history_page
    assert "Songs the radio plays will show up here." in texts(page)
    title = "Artist - Song & more"
    controller.history.append(HistoryEntry(title, "Alpha", datetime.now().replace(hour=9, minute=5)))
    page.refresh(Change.HISTORY)
    assert len(page.rows) == 1
    row = page.rows[0]
    assert row.get_title() == title
    assert row.get_subtitle() == "Alpha · 09:05"
    assert menu_labels(row.menu_button.get_menu_model()) == ["Copy", "Search on Spotify", "Search on YouTube"]
    query = quote("Artist Song & more", safe="")
    row.activate_action("row.spotify", None)
    row.activate_action("row.youtube", None)
    assert launched == ["https://open.spotify.com/search/" + query,
                        "https://www.youtube.com/results?search_query=" + query]
    page.clear_button.emit("clicked")
    assert controller.history == [] and page.rows == []
    assert "Songs the radio plays will show up here." in texts(page)


def test_history_rows_have_the_station_logo(make):
    window, controller = make()
    controller.stations[0].logo = "https://logo.example/alpha.png"
    controller.history[:] = [HistoryEntry("A - B", "Alpha", datetime.now()), HistoryEntry("C - D", "Gone", datetime.now())]
    page = window.history_page
    page.refresh(Change.HISTORY)
    assert [row.logo.url for row in page.rows] == ["https://logo.example/alpha.png", None]
    assert page.rows[1].logo.get_icon_name() == "audio-x-generic-symbolic"   # no longer on the list
    controller.update_station(1, Station("Gone", "http://s1.example/live", "https://logo.example/gone.png"))
    assert [row.logo.url for row in page.rows] == ["https://logo.example/alpha.png", "https://logo.example/gone.png"]


MONTH = datetime(2026, 3, 1, 12).astimezone()   # local noon, 1 March 2026
NOW = (MONTH + timedelta(days=10)).astimezone(timezone.utc)


def _listened(controller):
    """Two stations in March 2026 (one with song titles), one a year before."""
    utc = timezone.utc
    month = MONTH
    controller.statistics.sessions[:] = [
        ListeningSession("Old", "http://old.example/", month.replace(year=month.year - 1).astimezone(utc),
                         (month.replace(year=month.year - 1) + timedelta(hours=9)).astimezone(utc)),
        ListeningSession("Alpha", "http://s0.example/live", month.astimezone(utc),
                         (month + timedelta(hours=2, minutes=5)).astimezone(utc), True),
        ListeningSession("Beta", "http://s1.example/live", (month + timedelta(hours=3)).astimezone(utc),
                         (month + timedelta(hours=3, minutes=30)).astimezone(utc)),
    ]
    controller.statistics.songs[:] = [
        SongPlay("Alpha", title, (month + timedelta(minutes=4 * i)).astimezone(utc))
        for i, title in enumerate(["Queen - A Kind Of Magic", "Editors - Shadow", "Queen - Bohemian Rhapsody"])]
    return month


def test_statistics_page(make, monkeypatch):
    window, controller = make()
    page = window.statistics_page
    window.show_page("statistics")
    assert wait_for(lambda: page.get_mapped())
    assert page.shown == "empty"
    assert "Nothing here yet. Listen for a while and come back." in texts(page)

    _listened(controller)
    page.update(NOW)
    assert page.shown == "data" and page.period is Period.MONTH
    assert page.period_label.get_text() == "March 2026"
    assert page.total_label.get_text() == "2 h 35 min"
    assert [label.get_text() for label in page.tile_values] == ["3", "2", "2 h 05 min"]
    rows = [row.get_child() for row in descendants(page.stations_list) if isinstance(row, Gtk.ListBoxRow)]
    assert [texts(row) for row in rows] == [["Alpha", "2 h 05 min"], ["Beta", "30 min"]]
    assert page.share_label.get_text() == "From song titles sent by the stations · 81% of listening time"
    artists = [texts(row.get_child()) for row in descendants(page.artists_list) if isinstance(row, Gtk.ListBoxRow)]
    assert artists == [["1", "Queen", "2 plays"], ["2", "Editors", "1 play"]]
    assert page.peak_label.get_text().startswith("Most often ")

    page.switch.select(Period.ALL)
    page.period = Period.ALL
    page.update(NOW)
    assert page.total_label.get_text() == "11 h 35 min"
    assert page.period_label.get_text() == "Since 1 March 2025"

    window.show_page("settings")
    window.show_page("statistics")   # opened again: this month
    assert wait_for(lambda: page.period is Period.MONTH)

    # "Clear statistics…" is in the ⋯ menu left of the ✕, not at the bottom of the page.
    assert "Clear statistics" not in texts(page)
    bar = next(w for w in descendants(page) if isinstance(w, Adw.HeaderBar))
    button = page.menu_button
    assert button.get_icon_name() == "view-more-symbolic" and button.get_tooltip_text() == "More"
    assert button in list(descendants(bar))
    ok, more = button.compute_bounds(bar)
    close = next(w for w in descendants(bar) if isinstance(w, Gtk.WindowControls))
    ok, cross = close.compute_bounds(bar)
    assert more.get_x() + more.get_width() <= cross.get_x()   # left of ✕
    assert menu_labels(button.get_menu_model()) == ["Clear statistics…"]

    answers = []
    monkeypatch.setattr(controller, "clear_statistics", lambda: answers.append("cleared"))
    page.activate_action("statistics.clear", None)
    assert wait_for(lambda: isinstance(window.get_visible_dialog(), Adw.AlertDialog))
    dialog = window.get_visible_dialog()
    assert dialog.get_heading() == "Clear statistics?"
    assert dialog.get_body() == ("Your listening statistics will be permanently deleted. Your song history will "
                                 "remain.\n\nThis can't be undone.")
    assert [dialog.get_response_label(r) for r in ("cancel", "clear")] == ["Cancel", "Clear"]
    assert dialog.get_response_appearance("clear") == Adw.ResponseAppearance.DESTRUCTIVE
    assert dialog.get_default_response() == "cancel" and dialog.get_close_response() == "cancel"
    page._clear_answered(dialog, "cancel")
    assert answers == []
    page._clear_answered(dialog, "clear")
    assert answers == ["cleared"]
    dialog.force_close()


@pytest.mark.parametrize("language", ["de", "uk"])
def test_every_page_fits_the_window_in_long_languages(language, tmp_path, monkeypatch):
    """No page asks for more than the 412 px the window has (a wider page would widen the window)."""
    msgfmt = shutil.which("msgfmt")
    if msgfmt is None:
        pytest.skip("msgfmt is missing")
    target = tmp_path / "locale" / language / "LC_MESSAGES"
    target.mkdir(parents=True)
    subprocess.run([msgfmt, "-o", str(target / "minimalistic-radio.mo"), str(ROOT / "po" / f"{language}.po")],
                   check=True)
    monkeypatch.delenv("LANGUAGE", raising=False)
    monkeypatch.setattr(i18n, "_translation", i18n._translation)   # English again for the later tests
    _ = i18n.install(language, str(tmp_path / "locale"))
    paths = Paths(tmp_path / "config", tmp_path / "data", tmp_path / "cache")
    save_stations(paths.config / "stations.json", SHOT_STATIONS)
    controller = RadioController(FakePlayer(), GLibScheduler(), paths, lambda url, cb: None,
                                 lambda url, path, cb: None, _)
    controller.start(autostart=True)
    sample = sample_statistics(SHOT_STATIONS, datetime.now(timezone.utc))
    controller.statistics.sessions[:] = sample.sessions
    controller.statistics.songs[:] = sample.songs
    window = RadioWindow(controller, _)
    window.present()
    try:
        assert wait_for(window.get_mapped)
        too_wide = {}
        for tag in PAGES:
            window.show_page(tag)
            run_loop(100)
            page = window.navigation.get_visible_page()
            needed = page.measure(Gtk.Orientation.HORIZONTAL, -1)[0]
            if needed > 412:
                too_wide[tag] = (needed, _widest(page))
        if too_wide:
            pytest.fail("\n".join(f"{tag} needs {needed} px:\n" + "\n".join(lines)
                                  for tag, (needed, lines) in too_wide.items()))
    finally:
        window.destroy()


def _widest(widget, depth=0, lines=None):
    """The widgets a page's width comes from: each visible widget of 100 px or more, indented by depth."""
    lines = [] if lines is None else lines
    width = widget.measure(Gtk.Orientation.HORIZONTAL, -1)[0]
    if widget.get_visible() and width >= 100:
        text = widget.get_text() if isinstance(widget, Gtk.Label) else ""
        classes = ".".join(widget.get_css_classes())
        lines.append(f"{'  ' * depth}{type(widget).__name__}.{classes} {width} {text!r}"
                     f" margins {widget.get_margin_start()}+{widget.get_margin_end()}")
        child = widget.get_first_child()
        while child is not None:
            _widest(child, depth + 1, lines)
            child = child.get_next_sibling()
    return lines


def test_statistics_with_too_few_titles(make):
    window, controller = make()
    page = window.statistics_page
    _listened(controller)
    # Song titles for 5 of the 35 minutes: under 20 %.
    controller.statistics.sessions[1].end = (MONTH + timedelta(minutes=5)).astimezone(timezone.utc)
    page.update(NOW)
    assert page.share_label.get_text() == "From song titles sent by the stations · 14% of listening time"
    assert not page.artists_list.get_visible() and page.too_few.get_visible()
    assert page.too_few.get_text() == "Not enough song titles yet"


def test_settings_rows(make, monkeypatch, tmp_path):
    window, controller = make(names=("Alpha",))
    page = window.settings_page
    rebuilt = []
    monkeypatch.setattr(window, "language_changed", lambda: rebuilt.append(True))
    monkeypatch.setattr(window, "quit_app", lambda: rebuilt.append("quit"))

    options = [page.language_row.get_model().get_string(i) for i in range(page.language_row.get_model().get_n_items())]
    assert options == ["Same as system", "Polski", "English", "Deutsch", "Українська", "Čeština", "Español", "Français",
                       "Italiano", "Português"]
    page.language_row.set_selected(2)
    assert controller.prefs.language == "en" and rebuilt == [True]

    assert page.popup_row.get_active() is True
    page.popup_row.set_active(False)
    assert controller.prefs.show_station_popup is False
    page.autostart_row.set_active(True)
    assert controller.prefs.autostart is True

    target = tmp_path / "out.json"
    page.export_to(target)
    assert json.loads(target.read_text(encoding="utf-8")) == [{"Name": "Alpha", "Url": "http://s0.example/live",
                                                                "Logo": None}]
    assert page.stations_group.get_description() == "Stations saved: 1."
    folder = tmp_path / "folder.json"
    folder.mkdir()
    page.export_to(folder)
    assert page.stations_group.get_description() == "Couldn't save the file."
    other = tmp_path / "in.json"
    other.write_text(json.dumps([{"Name": "Beta", "Url": "http://b.example/s", "Logo": None}]), encoding="utf-8")
    page.import_from(other)
    assert page.stations_group.get_description() == "Stations added: 1."
    assert [s.name for s in controller.stations] == ["Alpha", "Beta"]
    other.write_text("{}", encoding="utf-8")
    page.import_from(other)
    assert page.stations_group.get_description() == "This isn't a Minimalistic Radio station list."

    assert [w.get_name() for w in (page.language_row, page.autostart_row, page.popup_row, page.export_button,
                                   page.import_button, page.statistics_row, page.statistics_button, page.about_row,
                                   page.website_button, page.quit_button)] == [
        "language-row", "autostart-row", "popup-row", "export-button", "import-button", "statistics-row",
        "statistics-button", "about-row", "website-button", "quit-button"]

    # Statistics: on by default; off is saved and shown on the Statistics page; since when it collects.
    assert page.statistics_row.get_active() and page.collected_label.get_text() == "Nothing collected yet"
    page.statistics_row.set_active(False)
    assert controller.prefs.collect_statistics is False and window.statistics_page.off.get_visible()
    assert window.statistics_page.off.get_text() == "Statistics are off. Nothing new is recorded."
    page.statistics_row.set_active(True)
    assert controller.prefs.collect_statistics is True and not window.statistics_page.off.get_visible()
    controller.statistics.sessions.append(ListeningSession("Alpha", "http://s0.example/live",
                                                           datetime(2025, 3, 2, 12).astimezone(timezone.utc),
                                                           datetime(2025, 3, 2, 13).astimezone(timezone.utc)))
    page.refresh(Change.STATISTICS)   # as the controller's change does
    assert page.collected_label.get_text() == "Collected since 2 March 2025"

    # About: the round app icon, the version and a link to GitHub (no About dialog any more).
    assert page.about_row.get_subtitle() == f"Version {VERSION} · MIT"
    assert [w.get_icon_name() for w in descendants(page.about_row) if isinstance(w, Gtk.Image)][0] == \
        "io.github.zal3wa.minimalistic-radio"
    assert page.website_button.get_uri() == "https://github.com/zal3wa/minimalistic-radio"
    assert not page.about_row.get_activatable()

    # The groups: General, Stations, the statistics card, About, the Quit card; two cards have no heading.
    groups = [w for w in descendants(page) if isinstance(w, Adw.PreferencesGroup)]
    assert [g.get_title() for g in groups] == ["General", "Stations", "", "About", ""]
    assert "Collected only on this computer, never sent anywhere" in texts(groups[2])
    assert (page.quit_row.get_title(), page.quit_row.get_subtitle(), page.quit_button.get_label()) == (
        "Quit", "Stops the radio and removes it from the tray", "Quit")
    assert page.quit_row in descendants(groups[4]) and page.quit_button.has_css_class("destructive-action")

    page.statistics_button.emit("clicked")
    assert wait_for(lambda: window.shown_pages() == ["stations", "settings", "statistics"])
    page.quit_button.emit("clicked")
    assert rebuilt[-1] == "quit"


def test_no_windows_only_settings(make):
    window, _ = make()
    text = " ".join(texts(window.settings_page)).lower()
    for word in ("ffmpeg", "decod", "windhawk", "update", "windows"):
        assert word not in text

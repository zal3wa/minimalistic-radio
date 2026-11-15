"""The history and settings pages (Task 13). File dialogs are not driven: the pages' export_to and
import_from are what the dialogs call with the chosen path."""
import json
from datetime import datetime
from urllib.parse import quote

import pytest

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from minimalistic_radio import VERSION  # noqa: E402
from minimalistic_radio.controller import Change  # noqa: E402
from minimalistic_radio.core.models import HistoryEntry  # noqa: E402
from test_ui_main import descendants, make, menu_labels, texts  # noqa: E402,F401


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


def test_settings_rows(make, monkeypatch, tmp_path):
    window, controller = make(names=("Alpha",))
    page = window.settings_page
    rebuilt = []
    monkeypatch.setattr(window, "language_changed", lambda: rebuilt.append(True))
    monkeypatch.setattr(window, "quit_app", lambda: rebuilt.append("quit"))

    options = [page.language_row.get_model().get_string(i) for i in range(page.language_row.get_model().get_n_items())]
    assert options == ["Same as system", "Polski", "English"]
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
    other = tmp_path / "in.json"
    other.write_text(json.dumps([{"Name": "Beta", "Url": "http://b.example/s", "Logo": None}]), encoding="utf-8")
    page.import_from(other)
    assert page.stations_group.get_description() == "Stations added: 1."
    assert [s.name for s in controller.stations] == ["Alpha", "Beta"]
    other.write_text("{}", encoding="utf-8")
    page.import_from(other)
    assert page.stations_group.get_description() == "This isn't a Minimalistic Radio station list."

    assert [w.get_name() for w in (page.language_row, page.autostart_row, page.popup_row, page.export_button,
                                   page.import_button, page.about_row, page.quit_button)] == [
        "language-row", "autostart-row", "popup-row", "export-button", "import-button", "about-row", "quit-button"]
    page.about_row.emit("activated")
    about = page.about
    assert isinstance(about, Adw.AboutDialog)
    assert about.get_version() == VERSION
    assert about.get_license_type() == Gtk.License.MIT_X11
    assert about.get_website() == "https://github.com/zal3wa/minimalistic-radio"
    assert "Icons: Lucide (ISC)" in about.get_comments()
    about.close()

    page.quit_button.emit("clicked")
    assert rebuilt[-1] == "quit"


def test_no_windows_only_settings(make):
    window, _ = make()
    text = " ".join(texts(window.settings_page)).lower()
    for word in ("ffmpeg", "decod", "windhawk", "update", "windows"):
        assert word not in text

"""The search page with suggestions, and the station dialog (Task 12). directory.search and
directory.suggestions are replaced by fakes: nothing here touches the network."""
import threading

import pytest

from minimalistic_radio.core import directory  # noqa: E402
from minimalistic_radio.core.directory import DirectoryStation, DirectoryUnavailable  # noqa: E402
from minimalistic_radio.core.models import Station  # noqa: E402
from minimalistic_radio.ui.station_dialog import StationDialog  # noqa: E402
from test_ui_main import make, names, run_loop, texts, wait_for  # noqa: E402,F401

UNREACHABLE = "Couldn't reach the station directory. Try again."


def entry(name, url=None, tags="jazz"):
    return DirectoryStation(name, "Germany", url or f"http://{name.lower()}.example/s", None, "MP3", 128, tags)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def unreachable(*_args):
        raise DirectoryUnavailable("test")

    monkeypatch.setattr(directory, "search", unreachable)
    monkeypatch.setattr(directory, "suggestions", unreachable)
    for var in ("LC_ALL", "LC_TIME", "LC_MONETARY", "LC_PAPER", "LC_ADDRESS", "LC_MESSAGES"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", "C")


def open_search(window):
    window.controller.prefs.language = "en"
    window.show_page("search")
    return window.search_page


def search_for(page, text):
    page.entry.set_text(text)
    page.entry.emit("activate")


def row_names(page):
    return [row.get_title() for row in page.rows]


def test_suggestions_shown_when_empty(make, monkeypatch):
    calls = []
    monkeypatch.setattr(directory, "suggestions",
                        lambda country, *a: calls.append(country) or ([entry("Kexp"), entry("Fip")], [entry("Pop")]))
    window, _ = make()
    page = open_search(window)
    assert page.status.get_label() == "Loading suggestions…"
    assert wait_for(lambda: len(page.rows) == 3)
    assert row_names(page) == ["Kexp", "Fip", "Pop"]
    assert {"Recommended", "Popular worldwide"} <= set(texts(page))
    assert calls == [None]
    window.show_page("stations")
    run_loop(400)
    page.entry.set_text("leftover")
    window.show_page("search")
    assert wait_for(lambda: page.entry.get_text() == "" and len(page.rows) == 3)   # the box is cleared
    assert calls == [None]   # loaded once per run


def test_suggestions_hidden_while_searching(make, monkeypatch):
    monkeypatch.setattr(directory, "suggestions", lambda country, *a: ([entry("Kexp")], [entry("Pop")]))
    release = threading.Event()
    monkeypatch.setattr(directory, "search", lambda query, *a: release.wait(3) and [entry("Found")])
    window, _ = make()
    page = open_search(window)
    assert wait_for(lambda: len(page.rows) == 2)
    search_for(page, "jazz")
    assert page.rows == [] and "Recommended" not in texts(page)
    release.set()
    assert wait_for(lambda: row_names(page) == ["Found"])
    page.entry.set_text("")
    assert wait_for(lambda: row_names(page) == ["Kexp", "Pop"])   # clearing brings them back


def test_popular_failure_keeps_recommended(make, monkeypatch):
    calls = []
    monkeypatch.setattr(directory, "suggestions", lambda country, *a: calls.append(1) or ([entry("Kexp")], []))
    window, _ = make()
    page = open_search(window)
    assert wait_for(lambda: row_names(page) == ["Kexp"])
    assert not page.status.get_visible()
    window.show_page("stations")
    run_loop(400)
    window.show_page("search")   # not a complete success: tried again
    assert wait_for(lambda: len(calls) == 2)


def test_search_shows_results(make, monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(directory, "search",
                        lambda query, *a: release.wait(3) and [entry("Jazz FM"), entry("Known", "http://s0.example/live")])
    window, _ = make(names=("Alpha",))
    page = open_search(window)
    search_for(page, "jazz")
    assert page.status.get_label() == "Searching…"
    release.set()
    assert wait_for(lambda: len(page.rows) == 2)
    assert not page.status.get_visible()
    jazz, known = page.rows
    assert jazz.get_title() == "Jazz FM" and jazz.get_subtitle() == "Germany · MP3 128 kbps · jazz"
    assert jazz.button.get_icon_name() == "list-add-symbolic" and jazz.button.get_tooltip_text() == "Add to your stations"
    assert known.button.get_icon_name() == "object-select-symbolic"
    assert known.button.get_tooltip_text() == "Already on your list"


def test_typing_searches_once_after_a_pause(make, monkeypatch):
    calls = []
    monkeypatch.setattr(directory, "search", lambda query: calls.append(query) or [entry("Jazz FM")])
    window, _ = make()
    page = open_search(window)

    page.entry.set_text("ja")
    run_loop(100)
    page.entry.set_text("  jazz  ")
    run_loop(100)
    assert calls == []
    assert wait_for(lambda: row_names(page) == ["Jazz FM"])
    assert calls == ["jazz"]


@pytest.mark.parametrize("action", ["clear", "back", "enter", "button"])
def test_pending_search_is_cancelled(make, monkeypatch, action):
    calls = []
    monkeypatch.setattr(directory, "search", lambda query: calls.append(query) or [])
    window, _ = make()
    page = open_search(window)

    page.entry.set_text("jazz")
    if action == "clear":
        page.entry.set_text("  ")
    elif action == "back":
        window.show_page("stations")
    elif action == "enter":
        page.entry.emit("activate")
    else:
        page.search_button.emit("clicked")

    submitted = action in ("enter", "button")
    if submitted:
        assert page.status.get_label() == "Searching…"

    run_loop(500)
    assert calls == (["jazz"] if submitted else [])


def test_editing_discards_in_flight_results(make, monkeypatch):
    release = threading.Event()
    started = threading.Event()

    def lookup(query):
        if query == "jazz":
            started.set()
            if release.wait(3):
                return [entry("Jazz FM")]
        return [entry("Rock FM")]

    monkeypatch.setattr(directory, "search", lookup)
    window, _ = make()
    page = open_search(window)
    search_for(page, "jazz")
    assert started.wait(3)

    page.entry.set_text("rock")
    release.set()
    run_loop(100)
    assert "Jazz FM" not in row_names(page)
    assert wait_for(lambda: row_names(page) == ["Rock FM"])


def test_add_from_results(make, monkeypatch):
    monkeypatch.setattr(directory, "search", lambda query, *a: [entry("Jazz FM")])
    window, controller = make(names=("Alpha",))
    page = open_search(window)
    search_for(page, "jazz")
    assert wait_for(lambda: len(page.rows) == 1)
    page.rows[0].button.emit("clicked")
    assert names(controller) == ["Alpha", "Jazz FM"]
    assert page.rows[0].button.get_icon_name() == "object-select-symbolic"


def test_search_errors(make, monkeypatch):
    window, _ = make()
    page = open_search(window)
    search_for(page, "jazz")
    assert wait_for(lambda: page.status.get_label() == UNREACHABLE)
    monkeypatch.setattr(directory, "search", lambda query, *a: [])
    search_for(page, "nothing")
    assert wait_for(lambda: page.status.get_label() == "No results.")


def test_add_by_address_validation(make):
    window, controller = make(names=("Alpha",))
    saved = []

    def on_save(station):
        saved.append(station)
        return controller.add_station(station)

    dialog = StationDialog(window, None, on_save)
    assert [r.get_title() for r in (dialog.name_row, dialog.url_row, dialog.logo_row)] == [
        "Station name", "Stream address (HTTP or HTTPS)", "Logo address (optional)"]
    assert not dialog.save_button.get_sensitive()
    dialog.name_row.set_text("New")
    assert not dialog.save_button.get_sensitive()
    dialog.url_row.set_text("not an address")
    assert not dialog.save_button.get_sensitive()
    dialog.url_row.set_text("http://s0.example/live")   # Alpha's address
    assert dialog.save_button.get_sensitive()
    dialog.logo_row.set_text("junk")
    dialog.save_button.emit("clicked")
    assert dialog.message.get_visible() and dialog.message.get_label() == "This address is already on the list."
    assert saved[-1] == Station("New", "http://s0.example/live", None)   # the invalid logo was cleared
    dialog.url_row.set_text("http://new.example/live")
    dialog.save_button.emit("clicked")
    assert names(controller) == ["Alpha", "New"]
    dialog.force_close()


def test_edit_station(make):
    window, controller = make(names=("Alpha", "Beta", "Gamma"), current=1, playing=True)
    dialog = window.edit_station(1)
    assert dialog.name_row.get_text() == "Beta"
    dialog.name_row.set_text("Beta 2")
    dialog.url_row.set_text("http://new.example/live")
    dialog.save_button.emit("clicked")
    assert names(controller) == ["Alpha", "Beta 2", "Gamma"] and controller.current == 1
    assert controller.player.calls[-1] == ("play", "http://new.example/live")

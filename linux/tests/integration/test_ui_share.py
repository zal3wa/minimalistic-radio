"""Share a station (docs/superpowers/specs/2026-11-15-share-station-design.md): Share in the ⋯ menu, and share links
opened into the running radio — the Shared station page, Add and play, Cancel, a known station, a link without one,
and links pasted where a station is added."""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gdk  # noqa: E402

from minimalistic_radio.controller import Status  # noqa: E402
from minimalistic_radio.core.models import Station  # noqa: E402
from minimalistic_radio.core.share import APP_LINK, WEB_LINK, SharedStation, read_link, share_link  # noqa: E402
from test_ui_main import NO_MODIFIERS, make, run_loop, texts, wait_for  # noqa: E402,F401

NEW = Station("Antyradio Hard", "https://an05.cdn.eurozet.pl/ANTHAR.mp3", "https://logo.example/hard.png")


def names(controller):
    return [s.name for s in controller.stations]


def test_share_copies_the_link_and_says_so(make):
    window, controller = make(names=("Alpha", "Beta"))
    row = window.stations_page.rows[1]
    row.activate_action("row.share", None)
    copied = {}
    window.get_clipboard().read_text_async(None, lambda clipboard, result: copied.setdefault(
        "text", clipboard.read_text_finish(result)))
    assert wait_for(lambda: "text" in copied)
    assert copied["text"] == share_link(controller.stations[1]) == WEB_LINK + "n=Beta&u=http%3A%2F%2Fs1.example%2Flive"
    assert read_link(copied["text"]) == SharedStation("Beta", "http://s1.example/live")
    toast = window._toast
    assert toast is not None and toast.get_title() == "Link copied" and toast.get_timeout() == 2


def test_a_shared_link_asks_and_add_and_play_adds_and_plays(make):
    window, controller = make(names=("Alpha", "Beta"))
    assert window.open_link(share_link(NEW))
    assert wait_for(lambda: window.shown_pages() == ["stations", "shared"])
    page = window.shared_page
    assert page.card.get_visible() and not page.invalid.get_visible()
    assert {"Shared station", "Antyradio Hard", "an05.cdn.eurozet.pl/ANTHAR.mp3",
            "Add it to your stations and play it now?", "Add and play", "Cancel"} <= set(texts(page))
    assert page.logo.url == NEW.logo
    assert names(controller) == ["Alpha", "Beta"] and controller.status is Status.READY   # nothing yet
    page.add_button.emit("clicked")
    assert wait_for(lambda: window.shown_pages() == ["stations"])
    assert controller.stations[-1] == NEW and controller.current == 2
    assert controller.status is Status.CONNECTING and controller.player.calls[-1] == ("play", NEW.url)


def test_cancel_back_and_escape_change_nothing(make):
    window, controller = make(names=("Alpha", "Beta"))
    for leave in (lambda: window.shared_page.cancel_button.emit("clicked"),
                  lambda: window._key_pressed(None, Gdk.KEY_Escape, 0, NO_MODIFIERS),
                  lambda: window.navigation.pop()):
        window.open_link(APP_LINK + share_link(NEW).split("#", 1)[1])
        assert wait_for(lambda: window.shown_pages() == ["stations", "shared"])
        leave()
        assert wait_for(lambda: window.shown_pages() == ["stations"])
    assert names(controller) == ["Alpha", "Beta"] and controller.status is Status.READY
    assert all(call[0] != "play" for call in controller.player.calls)


def test_a_known_station_just_plays(make):
    window, controller = make(names=("Alpha", "Beta"))
    window.show_page("settings")
    assert window.open_link(share_link(Station("Another name", "HTTP://S1.EXAMPLE/live/")))
    assert wait_for(lambda: window.shown_pages() == ["stations"])
    assert names(controller) == ["Alpha", "Beta"]
    assert controller.current == 1 and controller.player.calls[-1] == ("play", "http://s1.example/live")


def test_a_link_without_a_station_says_so(make):
    window, controller = make(names=("Alpha",))
    assert window.open_link(WEB_LINK + "n=No+address")
    assert wait_for(lambda: window.shown_pages() == ["stations", "shared"])
    page = window.shared_page
    assert page.invalid.get_visible() and not page.card.get_visible()
    assert page.invalid.get_text() == "This link doesn't contain a station."
    assert not window.open_link("jazz") and window.shown_pages() == ["stations", "shared"]   # not a share link


def test_a_link_pasted_into_the_search_box_opens_its_page(make):
    window, controller = make(names=("Alpha",))
    window.show_page("search")
    assert wait_for(lambda: window.shown_pages() == ["stations", "search"])
    window.search_page.entry.set_text("  " + share_link(NEW) + " ")
    assert wait_for(lambda: window.shown_pages() == ["stations", "shared"])
    assert window.shared_page.station == SharedStation(NEW.name, NEW.url, NEW.logo)
    window.show_page("search")
    assert wait_for(lambda: window.shown_pages() == ["stations", "search"])
    window.search_page.entry.set_text("jazz")   # an ordinary search stays a search
    run_loop(400)
    assert window.shown_pages() == ["stations", "search"]


def test_a_link_pasted_into_add_by_address_opens_its_page(make):
    window, controller = make(names=("Alpha",))
    dialog = window.add_by_address()
    run_loop(100)
    dialog.url_row.set_text(share_link(NEW).replace(WEB_LINK, APP_LINK))
    assert wait_for(lambda: window.shown_pages() == ["stations", "shared"])
    assert window.shared_page.station == SharedStation(NEW.name, NEW.url, NEW.logo)
    assert names(controller) == ["Alpha"]
    assert wait_for(lambda: not dialog.get_mapped())   # the dialog closed

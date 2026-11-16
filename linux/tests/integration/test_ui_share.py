"""Share a station (docs/superpowers/specs/2026-11-15-share-station-design.md): Share in the ⋯ menu, and share links
opened into the running radio — the Shared station page, Add with or without "Play automatically"
(2026-11-16-share-play-and-clear-statistics-design.md), Cancel, a known station, a link without one, and links pasted
where a station is added."""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gdk, Gtk  # noqa: E402

from minimalistic_radio.controller import Status  # noqa: E402
from minimalistic_radio.core.models import Station  # noqa: E402
from minimalistic_radio.core.share import APP_LINK, WEB_LINK, SharedStation, read_link, share_link  # noqa: E402
from minimalistic_radio.core.storage import load_preferences  # noqa: E402
from test_ui_main import NO_MODIFIERS, make, run_loop, texts, wait_for  # noqa: E402,F401

NEW = Station("Antyradio Hard", "https://an05.cdn.eurozet.pl/ANTHAR.mp3", "https://logo.example/hard.png")
MANY = tuple(f"Station {i}" for i in range(20))   # longer than the window: the end of the list is scrolled away


def names(controller):
    return [s.name for s in controller.stations]


def plays(controller):
    return [call for call in controller.player.calls if call[0] == "play"]


def saved_choice(controller):
    return load_preferences(controller.paths.config / "preferences.json").play_shared


def shows_row(window, index):
    """Whether the station's row is inside the visible part of the list."""
    page = window.stations_page
    row = page.rows[index]
    if not row.get_mapped() or row.get_height() == 0:
        return False
    ok, bounds = row.compute_bounds(page.scrolled)
    return ok and bounds.get_y() >= 0 and bounds.get_y() + bounds.get_height() <= page.scrolled.get_height()


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


def test_a_shared_link_asks_and_add_adds_and_plays(make):
    window, controller = make(names=("Alpha", "Beta"))
    assert window.open_link(share_link(NEW))
    assert wait_for(lambda: window.shown_pages() == ["stations", "shared"])
    page = window.shared_page
    assert page.card.get_visible() and not page.invalid.get_visible()
    assert {"Shared station", "Antyradio Hard", "an05.cdn.eurozet.pl/ANTHAR.mp3",
            "Add it to your stations?", "Add", "Play automatically", "Cancel"} <= set(texts(page))
    assert page.logo.url == NEW.logo
    assert page.play_check.get_active()   # checked the first time
    assert page.play_check.get_halign() == Gtk.Align.CENTER and page.play_check.get_focusable()
    assert names(controller) == ["Alpha", "Beta"] and controller.status is Status.READY   # nothing yet
    page.add_button.emit("clicked")
    assert wait_for(lambda: window.shown_pages() == ["stations"])
    assert controller.stations[-1] == NEW and controller.current == 2
    assert controller.status is Status.CONNECTING and controller.player.calls[-1] == ("play", NEW.url)
    assert saved_choice(controller) is True


def test_add_unchecked_keeps_what_plays_and_shows_the_new_station(make):
    window, controller = make(names=MANY, current=0, playing=True)
    before = list(controller.player.calls)
    window.open_link(share_link(NEW))
    assert wait_for(lambda: window.shown_pages() == ["stations", "shared"])
    page = window.shared_page
    page.play_check.set_active(False)
    page.add_button.emit("clicked")
    assert wait_for(lambda: window.shown_pages() == ["stations"])
    assert controller.stations[-1] == NEW and controller.current == 0 and controller.status is Status.PLAYING
    assert controller.player.calls == before
    assert wait_for(lambda: shows_row(window, len(MANY)))   # scrolled to it
    assert saved_choice(controller) is False


def test_the_checkbox_keeps_the_last_choice_and_cancel_forgets_it(make):
    window, controller = make(names=("Alpha",))
    page = window.shared_page
    window.open_link(share_link(NEW))
    page.play_check.set_active(False)
    page.add_button.emit("clicked")   # remembered
    assert wait_for(lambda: window.shown_pages() == ["stations"])
    other = Station("Other", "https://other.example/live")
    window.open_link(share_link(other))
    assert wait_for(lambda: window.shown_pages() == ["stations", "shared"])
    assert not page.play_check.get_active()
    page.play_check.set_active(True)
    page.cancel_button.emit("clicked")   # not remembered
    assert wait_for(lambda: window.shown_pages() == ["stations"])
    assert controller.prefs.play_shared is False and saved_choice(controller) is False
    window.open_link(share_link(other))
    assert wait_for(lambda: window.shown_pages() == ["stations", "shared"])
    assert not page.play_check.get_active()


def test_enter_adds_with_the_checkbox_as_it_is(make):
    window, controller = make(names=("Alpha",))
    page = window.shared_page
    window.open_link(share_link(NEW))
    assert wait_for(lambda: window.shown_pages() == ["stations", "shared"])
    assert wait_for(lambda: window.get_focus() is page.add_button)   # Enter adds from the start
    page.play_check.set_active(False)
    page.play_check.grab_focus()   # Enter on the checkbox adds too; Space toggles it (GTK's own)
    assert page._key_pressed(None, Gdk.KEY_Return, 0, NO_MODIFIERS)
    assert wait_for(lambda: window.shown_pages() == ["stations"])
    assert controller.stations[-1] == NEW and plays(controller) == []
    window.open_link(share_link(Station("Other", "https://other.example/live")))
    assert wait_for(lambda: window.shown_pages() == ["stations", "shared"])
    page.cancel_button.grab_focus()
    assert not page._key_pressed(None, Gdk.KEY_Return, 0, NO_MODIFIERS)   # a focused Cancel cancels
    assert not page._key_pressed(None, Gdk.KEY_a, 0, NO_MODIFIERS)
    assert names(controller) == ["Alpha", "Antyradio Hard"]


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


def test_a_known_station_unchecked_is_shown_and_nothing_plays(make):
    window, controller = make(names=MANY, current=0, playing=True)
    controller.prefs.play_shared = False   # unchecked on the last Add
    before = list(controller.player.calls)
    window.show_page("settings")
    assert window.open_link(share_link(Station("Another name", "HTTP://S19.EXAMPLE/live/")))
    assert wait_for(lambda: window.shown_pages() == ["stations"])
    assert names(controller) == list(MANY) and controller.current == 0 and controller.player.calls == before
    assert window._toast is not None and window._toast.get_title() == "Already on your list"
    assert wait_for(lambda: shows_row(window, 19))


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

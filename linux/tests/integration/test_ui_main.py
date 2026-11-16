"""The window (Task 9): the stations page, drag to reorder, and the footer.

Gestures and keys are driven by calling the handlers the window connects, not by faking GDK events.
"""
import itertools
import time

import pytest

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from minimalistic_radio.controller import RadioController, Status  # noqa: E402
from minimalistic_radio.core.models import Preferences, Station  # noqa: E402
from minimalistic_radio.core.storage import Paths, save_preferences, save_stations  # noqa: E402
from minimalistic_radio.glib_scheduler import GLibScheduler  # noqa: E402
from minimalistic_radio.ui.window import RadioWindow  # noqa: E402

Adw.init()

ALT = Gdk.ModifierType.ALT_MASK
NO_MODIFIERS = Gdk.ModifierType(0)
CORRUPT = "Your station list couldn't be read. It was saved as stations.json.bad."


class FakePlayer:
    def __init__(self):
        self.calls = []

    def play(self, url):
        self.calls.append(("play", url))

    def stop(self):
        self.calls.append(("stop",))

    def set_volume(self, percent):
        self.calls.append(("volume", percent))


def run_loop(ms):
    context = GLib.MainContext.default()
    deadline = time.monotonic() + ms / 1000
    while time.monotonic() < deadline:
        context.iteration(False)
        time.sleep(0.005)


def wait_for(condition, timeout=3.0):
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            return False
        context.iteration(False)
        time.sleep(0.005)
    return True


def descendants(widget):
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from descendants(child)
        child = child.get_next_sibling()


def texts(widget):
    return [w.get_text() for w in descendants(widget) if isinstance(w, Gtk.Label)]


def menu_labels(model):
    return [model.get_item_attribute_value(i, Gio.MENU_ATTRIBUTE_LABEL, GLib.VariantType("s")).get_string()
            for i in range(model.get_n_items())]


def names(controller):
    return [s.name for s in controller.stations]


def record_moves(controller):
    moves = []
    move = controller.move_station

    def recording(index, delta):
        moves.append((index, delta))
        move(index, delta)

    controller.move_station = recording
    return moves


@pytest.fixture
def make(tmp_path):
    """Builds a window over a controller with these stations (a fake player, no network) and shows it."""
    counter = itertools.count()
    windows = []

    def build(names=("Alpha", "Beta"), current=None, playing=False, volume=30, stations_text=None):
        root = tmp_path / f"w{next(counter)}"
        paths = Paths(root / "config", root / "data", root / "cache")
        if stations_text is None:
            save_stations(paths.config / "stations.json",
                          [Station(name, f"http://s{i}.example/live") for i, name in enumerate(names)])
        else:
            paths.config.mkdir(parents=True)
            (paths.config / "stations.json").write_text(stations_text)
        save_preferences(paths.config / "preferences.json", Preferences(volume=volume))
        controller = RadioController(FakePlayer(), GLibScheduler(), paths,
                                     lambda url, cb: None, lambda url, path, cb: None)
        controller.start(autostart=True)
        if current is not None:
            controller.select(current)
        if playing:
            controller.play()
            controller.on_player_started()
        window = RadioWindow(controller, str)
        windows.append(window)
        window.present()
        assert wait_for(window.get_mapped)
        run_loop(150)
        return window, controller

    yield build
    for window in windows:
        window.destroy()
    run_loop(50)


def test_header_buttons(make):
    window, _ = make()
    assert window.get_default_size() == (412, 602)
    header = window.stations_page.header
    tooltips = {w.get_tooltip_text() for w in descendants(header) if isinstance(w, Gtk.Button)}
    assert {"Add a station", "Song history", "Settings"} <= tooltips
    assert {"Station", "History"} <= set(texts(header))
    assert not [w for w in descendants(header)   # no title
                if isinstance(w, Gtk.Label) and w.get_text() == "Minimalistic Radio" and w.get_mapped()]
    buttons = [w for w in descendants(header) if isinstance(w, Gtk.Button) and w.get_mapped()]
    assert [w for w in buttons if w.has_css_class("close")]
    assert not [w for w in buttons if w.has_css_class("minimize") or w.has_css_class("maximize")]
    controls = [w for w in descendants(header) if isinstance(w, Gtk.WindowControls) and w.get_mapped()]
    assert [(c.get_decoration_layout(), c.get_tooltip_text()) for c in controls] == [
        (":close", "Close (the radio keeps playing)")]
    assert Gtk.IconTheme.get_for_display(window.get_display()).has_icon(
        "io.github.zal3wa.minimalistic-radio-history-symbolic")
    window.history_button.emit("clicked")
    assert wait_for(lambda: window.shown_pages() == ["stations", "history"])
    window.add_button.emit("clicked")
    assert wait_for(lambda: window.shown_pages() == ["stations", "search"])


def test_subpages_have_back_and_title(make):
    window, _ = make()
    for page, title in ((window.history_page, "Song history"), (window.settings_page, "Settings"),
                        (window.statistics_page, "Statistics"), (window.search_page, "Add a station")):
        bars = [w for w in descendants(page) if isinstance(w, Adw.HeaderBar)]
        assert len(bars) == 1 and not bars[0].get_show_title() and bars[0].has_css_class("subpage-bar")
        assert title in texts(bars[0])
        assert ":close" in [c.get_decoration_layout() for c in descendants(bars[0])
                            if isinstance(c, Gtk.WindowControls)]


def test_statistics_opens_over_settings_or_history_and_escape_goes_back(make):
    window, _ = make()
    window.show_page("statistics")
    assert wait_for(lambda: window.shown_pages() == ["stations", "settings", "statistics"])
    window._key_pressed(None, Gdk.KEY_Escape, 0, NO_MODIFIERS)
    assert wait_for(lambda: window.shown_pages() == ["stations", "settings"])
    window.show_page("statistics")
    assert wait_for(lambda: window.shown_pages() == ["stations", "settings", "statistics"])
    window.show_page("history")
    assert wait_for(lambda: window.shown_pages() == ["stations", "history"])
    # From Song history, its [Statistics] button: back (and Escape) return to Song history.
    button = window.history_page.statistics_button
    assert "Statistics" in texts(button) and button.has_css_class("raised")
    assert any(isinstance(w, Gtk.Image) and w.get_icon_name() == "io.github.zal3wa.minimalistic-radio-statistics-symbolic"
               for w in descendants(button))
    assert Gtk.IconTheme.get_for_display(window.get_display()).has_icon(
        "io.github.zal3wa.minimalistic-radio-statistics-symbolic")
    button.emit("clicked")
    assert wait_for(lambda: window.shown_pages() == ["stations", "history", "statistics"])
    window._key_pressed(None, Gdk.KEY_Escape, 0, NO_MODIFIERS)
    assert wait_for(lambda: window.shown_pages() == ["stations", "history"])
    window.show_page("stations")
    assert wait_for(lambda: window.shown_pages() == ["stations"])
    window.show_page("statistics")   # from elsewhere (the stations page): over Settings
    assert wait_for(lambda: window.shown_pages() == ["stations", "settings", "statistics"])


def test_station_rows(make):
    window, _ = make(names=("Alpha", "Beta"), current=0, playing=True)
    rows = window.stations_page.rows
    assert [row.get_title() for row in rows] == ["Alpha", "Beta"]
    assert rows[0].has_css_class("playing") and not rows[1].has_css_class("playing")
    for row in rows:
        assert menu_labels(row.menu_button.get_menu_model()) == ["Edit", "Share", "Remove"]


# ---- Drag to reorder (docs/superpowers/specs/2026-11-14-drag-to-reorder-design.md) ----

def test_hold_lifts(make):
    window, _ = make(names=("A", "B", "C", "D"))
    page = window.stations_page
    row = page.rows[1]
    page._drag_begin(row.drag, 20, 10, row)
    run_loop(120)
    assert not row.has_css_class("dragging")
    run_loop(280)
    assert row.has_css_class("dragging")
    page._drag_end(row.drag, 0, 0, row)


def test_quick_click_plays(make):
    window, controller = make(names=("A", "B", "C", "D"), current=0)
    page = window.stations_page
    row = page.rows[1]
    page._drag_begin(row.drag, 20, 10, row)
    run_loop(50)
    page._drag_end(row.drag, 0, 0, row)
    assert controller.current == 1 and controller.active
    assert ("play", controller.stations[1].url) in controller.player.calls
    run_loop(300)   # the hold timer was cancelled by the release
    assert not any(r.has_css_class("dragging") for r in page.rows)


def test_drag_drop_reorders(make):
    window, controller = make(names=("A", "B", "C", "D"), current=2, playing=True)
    page = window.stations_page
    chosen = controller.stations[controller.current]
    calls = list(controller.player.calls)
    moves = record_moves(controller)
    row = page.rows[1]
    height = row.get_height()
    page._drag_begin(row.drag, 20, height / 2, row)
    page._drag_update(row.drag, 0, 2.6 * height, row)
    assert row.has_css_class("dragging")   # past the drag threshold: lifted without waiting
    run_loop(200)
    page._drag_end(row.drag, 0, 2.6 * height, row)
    assert moves == [(1, 2)]
    assert names(controller) == ["A", "C", "D", "B"]
    assert [r.get_title() for r in page.rows] == ["A", "C", "D", "B"]
    assert controller.stations[controller.current] is chosen
    assert controller.player.calls == calls and controller.status is Status.PLAYING
    assert not any(r.has_css_class("dragging") for r in page.rows)


def test_escape_cancels(make):
    window, controller = make(names=("A", "B", "C", "D"))
    page = window.stations_page
    stations_file = controller.paths.config / "stations.json"
    saved = stations_file.read_bytes()
    moves = record_moves(controller)
    row = page.rows[1]
    height = row.get_height()
    page._drag_begin(row.drag, 20, height / 2, row)
    page._drag_update(row.drag, 0, 2.6 * height, row)
    assert row.has_css_class("dragging")
    assert window._key_pressed(None, Gdk.KEY_Escape, 0, NO_MODIFIERS)
    page._drag_end(row.drag, 0, 2.6 * height, row)   # the button comes up after Escape
    assert wait_for(lambda: not row.has_css_class("dragging"))
    assert names(controller) == ["A", "B", "C", "D"] and moves == []
    assert stations_file.read_bytes() == saved
    assert window.get_visible()   # Escape ended the drag, not the window


def test_alt_arrows_move(make):
    window, controller = make(names=("A", "B", "C", "D"))
    page = window.stations_page
    assert page.rows[1].grab_focus()
    assert page._row_key(None, Gdk.KEY_Down, 0, ALT, page.rows[1])
    assert names(controller) == ["A", "C", "B", "D"]
    assert window.get_focus() is page.rows[2]
    assert page._row_key(None, Gdk.KEY_Up, 0, ALT, page.rows[2])
    assert names(controller) == ["A", "B", "C", "D"]
    assert window.get_focus() is page.rows[1]


def test_lift_does_not_play(make):
    window, controller = make(names=("A", "B", "C", "D"), current=0)
    page = window.stations_page
    row = page.rows[1]
    page._drag_begin(row.drag, 20, 10, row)
    run_loop(400)
    assert row.has_css_class("dragging")
    page._drag_end(row.drag, 0, 0, row)
    assert wait_for(lambda: not any(r.has_css_class("dragging") for r in page.rows))
    assert controller.current == 0 and not controller.active
    assert not any(call[0] == "play" for call in controller.player.calls)
    assert names(controller) == ["A", "B", "C", "D"]


# ---- The volume row, like Windows 11 ----

def test_volume_icon_levels(make):
    window, controller = make()
    button = window.footer.volume_button
    for volume, level in ((0, "muted"), (1, "low"), (33, "low"), (34, "medium"), (66, "medium"),
                          (67, "high"), (100, "high")):
        controller.set_volume(volume)
        assert button.get_icon_name() == f"audio-volume-{level}-symbolic", volume
    assert window.footer.volume_scale.get_value() == 100


def test_volume_icon_mutes(make):
    window, controller = make(volume=60)
    button = window.footer.volume_button
    assert button.get_tooltip_text() == "Mute"
    button.emit("clicked")
    assert controller.volume == 0 and button.get_tooltip_text() == "Unmute"
    assert button.get_icon_name() == "audio-volume-muted-symbolic"
    button.emit("clicked")
    assert controller.volume == 60 and button.get_tooltip_text() == "Mute"

    window, controller = make(volume=0)   # nothing to go back to: the default level
    window.footer.volume_button.emit("clicked")
    assert controller.volume == 30


def test_volume_bubble(make):
    window, controller = make()
    footer = window.footer
    assert not footer.volume_bubble.get_visible()
    footer.volume_scale.set_value(45)
    assert controller.volume == 45
    assert footer.volume_bubble.get_visible() and footer.volume_bubble_label.get_text() == "45"
    run_loop(600)
    footer.volume_scale.set_value(50)
    assert footer.volume_bubble_label.get_text() == "50"
    run_loop(600)
    assert footer.volume_bubble.get_visible()   # about 1 s after the last change, not the first
    assert wait_for(lambda: not footer.volume_bubble.get_visible(), 2.0)
    controller.set_volume(20)   # a change from elsewhere (the tray) moves the slider without a bubble
    run_loop(50)
    assert footer.volume_scale.get_value() == 20 and not footer.volume_bubble.get_visible()
    assert not any("Volume" in text for text in texts(window))   # no "Volume N%" label


def test_footer(make):
    window, controller = make(names=("Alpha", "Beta"), current=0)
    footer = window.footer
    assert footer.play_content.get_label() == "Play"
    assert "Now playing" in texts(footer)
    footer.play_button.emit("clicked")
    controller.on_player_started()
    assert controller.active and footer.play_content.get_label() == "Stop"
    assert footer.now_label.get_text() == "The station doesn't send song titles"
    controller.on_player_title("Leonard Cohen - Everybody Knows")
    assert footer.now_label.get_text() == "Leonard Cohen - Everybody Knows"
    footer.play_button.emit("clicked")
    assert not controller.active and footer.play_content.get_label() == "Play"

    footer.volume_scale.set_value(55)
    assert controller.volume == 55

    menu = footer.sleep_button.get_menu_model()
    assert menu_labels(menu) == ["15 min", "30 min", "45 min", "60 min", "90 min", "Off"]
    footer.sleep_button.popup()
    assert wait_for(lambda: footer.sleep_button.get_popover() is not None
                    and footer.sleep_button.get_popover().get_visible())
    footer.sleep_button.popdown()


def test_copy_button(make):
    window, controller = make(current=0, playing=True)
    controller.on_player_title("Leonard Cohen - Everybody Knows")
    window.footer.copy_button.emit("clicked")
    got = {}
    window.get_clipboard().read_text_async(
        None, lambda clipboard, result: got.setdefault("text", clipboard.read_text_finish(result)))
    assert wait_for(lambda: "text" in got)
    assert got["text"] == "Leonard Cohen - Everybody Knows"
    assert wait_for(lambda: "Copied" in texts(window.toasts))


def test_long_names_ellipsize(make):
    long_name = "Radio" + "x" * 95   # 100 characters, the longest a name can be
    window, _ = make(names=(long_name, "Beta"), current=0, playing=True)
    labels = [w for w in descendants(window.stations_page.rows[0])
              if isinstance(w, Gtk.Label) and w.get_text() == long_name]
    assert labels and labels[0].get_ellipsize() == Pango.EllipsizeMode.END
    assert window.get_width() <= 420


def test_empty_state(make):
    window, _ = make(names=())
    page = window.stations_page
    assert page.stack.get_visible_child() is page.empty
    assert isinstance(page.empty, Adw.StatusPage) and page.empty.get_title() == "No stations yet"
    assert any(isinstance(w, Gtk.Button) and w.get_label() == "Add a station" for w in descendants(page.empty))
    assert not window.footer.play_button.get_sensitive()


def test_corrupt_list_toast(make):
    window, controller = make(stations_text="{ not a station list")
    assert wait_for(lambda: CORRUPT in texts(window.toasts))
    assert not controller.corrupt_stations   # told once: a window built again (a language change) doesn't repeat it

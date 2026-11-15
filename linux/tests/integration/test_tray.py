"""The tray (Task 11): StatusNotifierItem and dbusmenu on the session bus (dbus-run-session in CI), with a fake watcher.

The app is a real RadioApplication with a test controller (a fake player, files in a temporary folder), so the
panel, its actions and its copy logic are the real ones.
"""
import time
import uuid

import pytest

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from fake_watcher import FakeWatcher  # noqa: E402
from minimalistic_radio import APP_ID  # noqa: E402
from minimalistic_radio.app import RadioApplication  # noqa: E402
from minimalistic_radio.controller import Change, RadioController  # noqa: E402
from minimalistic_radio.core.models import Preferences, Station  # noqa: E402
from minimalistic_radio.core.storage import Paths, save_preferences, save_stations  # noqa: E402
from minimalistic_radio.glib_scheduler import GLibScheduler  # noqa: E402
from minimalistic_radio.platform.menu_model import build_tray_menu, tooltip  # noqa: E402
from minimalistic_radio.platform.tray import TrayIcon  # noqa: E402

ITEM = "org.kde.StatusNotifierItem"
ITEM_PATH = "/StatusNotifierItem"
MENU = "com.canonical.dbusmenu"
MENU_PATH = "/MenuBar"
TRACK = "Leonard Cohen - Everybody Knows"


class FakePlayer:
    def play(self, url):
        pass

    def stop(self):
        pass

    def set_volume(self, percent):
        pass


def pump(condition, timeout=10.0):
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            return False
        context.iteration(False)
        time.sleep(0.005)
    return True


def settle(ms=100):
    pump(lambda: False, ms / 1000)


def unique_name():
    return Gio.bus_get_sync(Gio.BusType.SESSION, None).get_unique_name()


class Client:
    def __init__(self, path, interface):
        self.proxy = None
        self.signals = []
        Gio.DBusProxy.new_for_bus(Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None, unique_name(), path,
                                  interface, None, self._ready)
        assert pump(lambda: self.proxy is not None), "no proxy"
        self.proxy.connect("g-signal", lambda p, sender, name, params: self.signals.append((name, params.unpack())))

    def _ready(self, source, result):
        self.proxy = Gio.DBusProxy.new_for_bus_finish(result)

    def call(self, method, params=None):
        done = []
        self.proxy.call(method, params, Gio.DBusCallFlags.NONE, 5000, None,
                        lambda p, r: done.append(p.call_finish(r)))
        assert pump(lambda: done), f"{method} did not return"
        return done[0].unpack()

    def get(self, name):
        value = self.proxy.get_cached_property(name)
        return None if value is None else value.unpack()


def layout(menu):
    """GetLayout(0, -1, []): (revision, the root's children)."""
    revision, (root, props, children) = menu.call("GetLayout", GLib.Variant("(iias)", (0, -1, [])))
    assert root == 0 and props["children-display"] == "submenu"
    return revision, children


def event(menu, number, name="clicked"):
    menu.call("Event", GLib.Variant("(isvu)", (number, name, GLib.Variant("s", ""), 0)))


def descendants(widget):
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from descendants(child)
        child = child.get_next_sibling()


def texts(widget):
    return [w.get_text() for w in descendants(widget) if isinstance(w, Gtk.Label)]


@pytest.fixture
def watcher():
    w = FakeWatcher()
    w.start()
    yield w
    w.stop()


@pytest.fixture
def make(tmp_path):
    made = []

    def build(names=("Alpha", "Beta")):
        paths = Paths(tmp_path / "config", tmp_path / "data", tmp_path / "cache")
        save_stations(paths.config / "stations.json",
                      [Station(n, f"http://s{i}.example/live") for i, n in enumerate(names)])
        save_preferences(paths.config / "preferences.json", Preferences(volume=30))
        controller = RadioController(FakePlayer(), GLibScheduler(), paths,
                                     lambda url, cb: None, lambda url, path, cb: None)
        controller.start(autostart=True)
        app = RadioApplication(application_id=APP_ID + "TrayTest" + uuid.uuid4().hex[:8])
        assert app.register()
        app.controller = controller
        app._started = True   # the test's controller and player, not real ones
        tray = TrayIcon(app)
        hosts = []
        tray.connect("host-changed", lambda _tray, visible: hosts.append(visible))
        tray.start()
        made.append((app, tray))
        assert tray.error is None, tray.error
        events = []
        controller.subscribe(events.append)
        return app, controller, tray, hosts, events

    yield build
    for app, tray in made:
        tray.stop()
        if app.window is not None:
            app.window.destroy()
        app.quit()
    settle(50)


def test_registers_by_object_path(make, watcher):
    _, _, tray, hosts, _ = make()
    assert pump(lambda: watcher.registered), "the item never registered"
    assert watcher.registered == [(unique_name(), "/StatusNotifierItem")]
    assert pump(lambda: tray.visible)
    assert hosts == [True]
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    names = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "ListNames",
                          None, GLib.VariantType("(as)"), Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
    assert not [n for n in names if n.startswith("org.kde.StatusNotifierItem-")]


def test_item_properties(make, watcher):
    _, c, _, _, _ = make()
    c.select(0)
    item = Client(ITEM_PATH, ITEM)
    assert item.get("Id") == APP_ID
    assert item.get("Category") == "ApplicationStatus"
    assert item.get("Status") == "Active"
    assert item.get("IconName") == "io.github.zal3wa.minimalistic-radio-symbolic"
    assert item.get("IconThemePath") == ""   # the icon is in the host's theme
    pixmaps = item.get("IconPixmap")
    assert [(w, h) for w, h, _ in pixmaps] == [(16, 16), (22, 22), (32, 32), (48, 48)]
    for w, h, data in pixmaps:
        assert len(data) == w * h * 4
    _, _, data = pixmaps[-1]
    assert data[0] == 0                         # ARGB: the corner of the round icon is transparent
    assert data[(24 * 48 + 24) * 4] == 255      # and its middle opaque
    _, _, title, body = item.get("ToolTip")
    assert (title, body) == tooltip(c)
    assert item.get("Menu") == "/MenuBar"
    assert item.get("ItemIsMenu") is False


def test_icon_theme_path_in_the_snap(make, watcher, monkeypatch):
    """The host finds the symbolic icon in the snap's folder, which it can read."""
    monkeypatch.setenv("SNAP_NAME", "minimalistic-radio")
    monkeypatch.setenv("SNAP", "/snap/minimalistic-radio/x1")
    make()
    assert Client(ITEM_PATH, ITEM).get("IconThemePath") == "/snap/minimalistic-radio/x1/usr/share/icons"


def test_activate_shows_panel(make, watcher):
    app, _, _, _, _ = make()
    Client(ITEM_PATH, ITEM).call("Activate", GLib.Variant("(ii)", (0, 0)))
    assert pump(lambda: app.window is not None and app.window.is_visible())


def test_scroll_changes_volume(make, watcher):
    _, c, _, _, _ = make()
    item = Client(ITEM_PATH, ITEM)
    item.call("Scroll", GLib.Variant("(is)", (120, "vertical")))   # KDE: 120 a notch, positive is up
    assert c.volume == 35
    item.call("Scroll", GLib.Variant("(is)", (-120, "vertical")))
    assert c.volume == 30
    item.call("Scroll", GLib.Variant("(is)", (60, "vertical")))    # half a notch (a touchpad): not yet a step
    assert c.volume == 30
    item.call("Scroll", GLib.Variant("(is)", (60, "vertical")))
    assert c.volume == 35


def test_scroll_the_gtk_way(make, watcher):
    _, c, _, _, _ = make()
    item = Client(ITEM_PATH, ITEM)
    item.call("Scroll", GLib.Variant("(is)", (1, "vertical")))     # AppIndicator, Xfce: 1 a notch, positive is down
    assert c.volume == 25
    item.call("Scroll", GLib.Variant("(is)", (-1, "vertical")))
    assert c.volume == 30


def test_secondary_activate_toggles(make, watcher):
    _, c, _, _, _ = make()
    c.select(0)
    item = Client(ITEM_PATH, ITEM)
    item.call("SecondaryActivate", GLib.Variant("(ii)", (0, 0)))
    assert c.active
    item.call("SecondaryActivate", GLib.Variant("(ii)", (0, 0)))
    assert not c.active


def check_layout(items, nodes):
    assert len(nodes) == len(items)
    for m, (_, props, children) in zip(items, nodes):
        if m.separator:
            assert props["type"] == "separator"
            continue
        assert props["label"] == m.label.replace("_", "__")
        assert props.get("enabled", True) == m.enabled
        if m.children:
            assert props["children-display"] == "submenu"
            check_layout(m.children, children)
        if m.toggle:
            assert props["toggle-type"] == "radio"
            assert props["toggle-state"] == (1 if m.checked else 0)


def test_dbusmenu_layout(make, watcher):
    _, c, _, _, _ = make()
    c.select(0)
    c.play()
    c.on_player_started()
    c.on_player_title(TRACK)
    _, children = layout(Client(MENU_PATH, MENU))
    check_layout(build_tray_menu(c, str, None), children)


def test_underscore_is_not_a_mnemonic(make, watcher):
    make(names=("Radio_X", "Beta"))
    _, children = layout(Client(MENU_PATH, MENU))
    stations = children[1][2]
    assert stations[0][1]["label"] == "Radio__X"   # the desktop shows "Radio_X"


def test_dbusmenu_event_runs_action(make, watcher):
    _, c, tray, _, events = make()
    c.select(0)
    events.clear()
    event(Client(MENU_PATH, MENU), tray.menu.id_of("station:1"))
    assert c.current == 1
    assert any(Change.SWITCHED in e for e in events)


def test_now_track_opens_panel_and_copies(make, watcher):
    app, c, tray, _, _ = make()
    c.select(0)
    c.play()
    c.on_player_started()
    c.on_player_title(TRACK)
    event(Client(MENU_PATH, MENU), tray.menu.id_of("now:track"))
    assert pump(lambda: app.window is not None and app.window.is_visible())
    assert pump(lambda: "Copied" in texts(app.window.toasts))
    got = {}
    app.window.get_clipboard().read_text_async(
        None, lambda clipboard, result: got.setdefault("text", clipboard.read_text_finish(result)))
    assert pump(lambda: "text" in got)
    assert got["text"] == TRACK


def test_layout_updated_on_change(make, watcher):
    _, c, tray, _, _ = make()
    menu = Client(MENU_PATH, MENU)
    revision, _ = layout(menu)
    c.set_volume(55)
    assert pump(lambda: any(name == "LayoutUpdated" for name, _ in menu.signals))
    updated = [params for name, params in menu.signals if name == "LayoutUpdated"]
    assert updated[-1][0] > revision
    assert layout(menu)[0] > revision
    # Sent first. GNOME's AppIndicator extension updates the items it shows only from this, not from the layout.
    changed = [params for name, params in menu.signals if name == "ItemsPropertiesUpdated"]
    assert changed and (tray.menu.id_of("volume"), {"label": "Volume (55%)"}) in changed[-1][0]


def test_about_to_show_after_a_change(make, watcher):
    _, c, tray, _, _ = make()
    menu = Client(MENU_PATH, MENU)
    stations = tray.menu.id_of("stations")
    menu.call("GetLayout", GLib.Variant("(iias)", (stations, 1, [])))
    assert menu.call("AboutToShow", GLib.Variant("(i)", (stations,))) == (False,)
    c.select(1)
    assert menu.call("AboutToShow", GLib.Variant("(i)", (stations,))) == (True,)   # KDE reads the submenu again
    _, (_, _, children) = menu.call("GetLayout", GLib.Variant("(iias)", (stations, 1, [])))
    toggles = {number: props["toggle-state"] for number, props, _ in children}
    assert toggles[tray.menu.id_of("station:1")] == 1


def test_watcher_restart_reregisters(make, watcher):
    _, _, tray, hosts, _ = make()
    assert pump(lambda: tray.visible)
    watcher.stop()
    assert pump(lambda: not tray.visible)
    watcher.registered.clear()
    watcher.start()
    assert pump(lambda: watcher.registered), "the item did not register with the new watcher"
    assert watcher.registered[0][1] == "/StatusNotifierItem"
    assert pump(lambda: tray.visible)
    assert hosts == [True, False, True]


def test_no_host_means_no_tray(make):
    _, _, tray, hosts, _ = make()
    assert pump(lambda: hosts), "host-changed was never emitted"
    assert hosts == [False]
    assert tray.visible is False

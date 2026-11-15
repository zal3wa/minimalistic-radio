"""MPRIS (Task 10): a Gio.DBusProxy client against the service, on the session bus (dbus-run-session in CI)."""
import time
import uuid

import pytest

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gio, GLib  # noqa: E402

from minimalistic_radio import APP_ID  # noqa: E402
from minimalistic_radio.controller import Change, RadioController, Status  # noqa: E402
from minimalistic_radio.core.models import Preferences, Station  # noqa: E402
from minimalistic_radio.core.storage import Paths, save_preferences, save_stations  # noqa: E402
from minimalistic_radio.glib_scheduler import GLibScheduler  # noqa: E402
from minimalistic_radio.platform.mpris import MprisService  # noqa: E402

PATH = "/org/mpris/MediaPlayer2"
ROOT = "org.mpris.MediaPlayer2"
PLAYER = "org.mpris.MediaPlayer2.Player"


class FakePlayer:
    def play(self, url):
        pass

    def stop(self):
        pass

    def set_volume(self, percent):
        pass


class StubApp:
    def __init__(self, controller):
        self.controller = controller
        self.shown = 0

    def show_window(self):
        self.shown += 1

    def quit(self):
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


class Client:
    def __init__(self, name, interface):
        self.proxy = None
        self.interface = interface
        self.changes = []
        Gio.DBusProxy.new_for_bus(Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None, name, PATH, interface,
                                  None, self._ready)
        assert pump(lambda: self.proxy is not None), "no proxy"
        self.proxy.connect("g-properties-changed", lambda p, changed, inv: self.changes.append(changed.unpack()))

    def _ready(self, source, result):
        self.proxy = Gio.DBusProxy.new_for_bus_finish(result)

    def call(self, method, params=None):
        done = []
        self.proxy.call(method, params, Gio.DBusCallFlags.NONE, 5000, None,
                        lambda p, r: done.append(p.call_finish(r)))
        assert pump(lambda: done), f"{method} did not return"

    def get(self, name):
        value = self.proxy.get_cached_property(name)
        return None if value is None else value.unpack()

    def set(self, name, variant):
        done = []
        self.proxy.get_connection().call(
            self.proxy.get_name(), PATH, "org.freedesktop.DBus.Properties", "Set",
            GLib.Variant("(ssv)", (self.interface, name, variant)), None, Gio.DBusCallFlags.NONE, 5000, None,
            lambda c, r: done.append(c.call_finish(r)))
        assert pump(lambda: done), "Set did not return"


@pytest.fixture
def make(tmp_path):
    services = []

    def build(names=("Alpha", "Beta")):
        paths = Paths(tmp_path / "config", tmp_path / "data", tmp_path / "cache")
        save_stations(paths.config / "stations.json",
                      [Station(n, f"http://s{i}.example/live") for i, n in enumerate(names)])
        save_preferences(paths.config / "preferences.json", Preferences(volume=30))
        controller = RadioController(FakePlayer(), GLibScheduler(), paths,
                                     lambda url, cb: None, lambda url, path, cb: None)
        controller.start(autostart=True)
        app = StubApp(controller)
        name = "org.mpris.MediaPlayer2.test" + uuid.uuid4().hex[:8]
        service = MprisService(app, name)
        service.publish()
        services.append(service)
        assert pump(lambda: service.acquired), f"the bus name was not acquired (lost={service.lost}, name={name})"
        events = []
        controller.subscribe(events.append)
        return app, controller, name, events

    yield build
    for service in services:
        service.unpublish()
    settle(50)


def test_identity(make):
    _, _, name, _ = make()
    root = Client(name, ROOT)
    assert root.get("Identity") == "Minimalistic Radio"
    assert root.get("DesktopEntry") == APP_ID
    assert root.get("CanRaise") is True
    assert root.get("CanQuit") is True


def test_controls(make):
    _, c, name, events = make()
    player = Client(name, PLAYER)
    player.call("PlayPause")
    assert c.active
    player.call("PlayPause")
    assert c.status is Status.STOPPED
    player.call("Play")
    assert c.active
    player.call("Pause")
    assert c.status is Status.STOPPED
    player.call("Play")
    player.call("Stop")
    assert c.status is Status.STOPPED
    player.call("Next")
    assert c.current == 1
    assert any(Change.SWITCHED in e for e in events)
    events.clear()
    player.call("Previous")
    assert c.current == 0
    assert any(Change.SWITCHED in e for e in events)


def test_properties(make):
    _, c, name, _ = make()
    player = Client(name, PLAYER)
    assert player.get("PlaybackStatus") == "Stopped"
    player.changes.clear()
    c.play()
    assert pump(lambda: any(ch.get("PlaybackStatus") == "Playing" for ch in player.changes))
    assert player.get("PlaybackStatus") == "Playing"
    c.stop()
    assert pump(lambda: player.get("PlaybackStatus") == "Stopped")

    assert player.get("Volume") == pytest.approx(0.3)
    player.set("Volume", GLib.Variant("d", 0.8))
    assert c.volume == 80
    assert pump(lambda: player.get("Volume") == pytest.approx(0.8))
    assert player.get("CanGoNext") is True
    assert player.get("CanSeek") is False


def test_single_station_cannot_go_next(make):
    _, _, name, _ = make(names=("Alpha",))
    assert Client(name, PLAYER).get("CanGoNext") is False


def test_metadata_signal(make):
    _, c, name, _ = make()
    player = Client(name, PLAYER)
    c.play()
    c.on_player_started()
    settle()
    player.changes.clear()
    c.on_player_title("Some Artist - A New Song")
    assert pump(lambda: any("Metadata" in ch for ch in player.changes))
    metadata = player.get("Metadata")
    assert metadata["xesam:title"] == "A New Song"
    assert metadata["xesam:artist"] == ["Some Artist"]
    assert metadata["xesam:album"] == "Alpha"
    assert metadata["mpris:trackid"] == "/io/github/zal3wa/MinimalisticRadio/Track"


def test_raise_opens_panel(make):
    app, _, name, _ = make()
    Client(name, ROOT).call("Raise")
    assert app.shown == 1

"""Autostart file, suspend inhibit, network return, station notification and the no-tray hint (Task 14)."""
import time
import uuid

import pytest

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gio, GLib  # noqa: E402

from minimalistic_radio.app import RadioApplication  # noqa: E402
from minimalistic_radio.controller import RadioController  # noqa: E402
from minimalistic_radio.core.models import Preferences, Station  # noqa: E402
from minimalistic_radio.core.storage import Paths, save_preferences, save_stations  # noqa: E402
from minimalistic_radio.glib_scheduler import GLibScheduler  # noqa: E402
from minimalistic_radio.platform.background import Autostart  # noqa: E402
from minimalistic_radio.platform.notifications import StationNotifier  # noqa: E402
from minimalistic_radio.platform.session import SessionWatcher  # noqa: E402


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
        time.sleep(0.01)
    return True


def settle(ms):
    pump(lambda: False, ms / 1000)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("SNAP", raising=False)
    made = []

    def build(popup=True):
        paths = Paths(tmp_path / "config", tmp_path / "data", tmp_path / "cache")
        save_stations(paths.config / "stations.json",
                      [Station("Alpha", "http://a.example/live"), Station("Beta", "http://b.example/live")])
        save_preferences(paths.config / "preferences.json", Preferences(show_station_popup=popup))
        controller = RadioController(FakePlayer(), GLibScheduler(), paths,
                                     lambda url, cb: None, lambda url, path, cb: None)
        controller.start(autostart=True)
        app = RadioApplication(application_id="io.github.zal3wa.minimalistic_radio_test" + uuid.uuid4().hex[:8])
        assert app.register()
        app.controller = controller
        app._started = True
        made.append(app)
        return app, controller

    yield build
    for app in made:
        if app.window is not None:
            app.window.destroy()
        app.quit()
    settle(50)


def test_host_autostart_file(setup, tmp_path):
    _, controller = setup()
    autostart = Autostart(controller)
    file = tmp_path / "home" / ".config" / "autostart" / "io.github.zal3wa.minimalistic_radio.desktop"
    autostart.set(True)
    assert file.exists() and "Exec=minimalistic-radio --autostart" in file.read_text()
    assert autostart.enabled()
    autostart.set(False)
    assert not file.exists() and not autostart.enabled()


PORTAL_XML = """
<node>
  <interface name="org.freedesktop.portal.Inhibit">
    <method name="Inhibit">
      <arg type="s" direction="in"/><arg type="u" direction="in"/><arg type="a{sv}" direction="in"/>
      <arg type="o" direction="out"/>
    </method>
  </interface>
</node>"""
REQUEST_XML = """
<node><interface name="org.freedesktop.portal.Request"><method name="Close"/></interface></node>"""
REQUEST_PATH = "/org/freedesktop/portal/desktop/request/fake/1"


class FakePortal:
    def __init__(self):
        self.inhibits, self.closes = [], []
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.owned = False
        self.ids = []
        self.ids.append(self.bus.register_object(
            "/org/freedesktop/portal/desktop", Gio.DBusNodeInfo.new_for_xml(PORTAL_XML).interfaces[0],
            self._inhibit, None, None))
        self.name = Gio.bus_own_name_on_connection(self.bus, "org.freedesktop.portal.Desktop",
                                                   Gio.BusNameOwnerFlags.NONE,
                                                   lambda *_a: setattr(self, "owned", True), None)

    def _inhibit(self, _c, _s, _p, _i, _m, params, invocation):
        _window, flags, options = params.unpack()
        self.inhibits.append((flags, options["reason"]))
        self.ids.append(self.bus.register_object(
            REQUEST_PATH, Gio.DBusNodeInfo.new_for_xml(REQUEST_XML).interfaces[0],
            lambda _c, _s, path, _i, _m, _p, inv: (self.closes.append(path), inv.return_value(None)), None, None))
        invocation.return_value(GLib.Variant("(o)", (REQUEST_PATH,)))

    def stop(self):
        Gio.bus_unown_name(self.name)
        for i in self.ids:
            self.bus.unregister_object(i)


def test_inhibit_follows_playback(setup):
    app, controller = setup()
    portal = FakePortal()
    try:
        assert pump(lambda: portal.owned)
        controller.subscribe(app._playback_changed)
        controller.select(0)
        controller.play()
        controller.play()
        assert pump(lambda: portal.inhibits)
        assert portal.inhibits == [(4, "Playing internet radio")]
        controller.stop()
        assert pump(lambda: portal.closes)
        assert portal.closes == [REQUEST_PATH] and len(portal.inhibits) == 1
    finally:
        portal.stop()


def test_inhibit_without_portal_is_quiet(setup):
    app, controller = setup()
    controller.subscribe(app._playback_changed)
    controller.select(0)
    controller.play()
    settle(300)
    controller.stop()
    settle(300)


def test_network_return_calls_controller(setup):
    _, controller = setup()
    calls = []
    controller.network_available = lambda: calls.append(1)
    watcher = SessionWatcher(controller)
    try:
        monitor = watcher._monitor
        monitor.emit("network-changed", True)
        monitor.emit("network-changed", True)
        assert pump(lambda: calls, 5)
        settle(2500)
        assert calls == [1]
    finally:
        watcher.close()


def test_switch_notification(setup, monkeypatch):
    app, controller = setup()
    sent = []
    monkeypatch.setattr(app, "send_notification", lambda nid, n: sent.append(nid))
    notifier = StationNotifier(app)
    controller.select(0)
    controller.next_station()
    assert sent == ["station"] and notifier.last_title == "Beta"
    controller.prefs.show_station_popup = False
    controller.next_station()
    assert len(sent) == 1
    notifier.close()


def test_no_tray_hint_once(setup, monkeypatch):
    app, controller = setup()
    sent = []
    monkeypatch.setattr(app, "send_notification", lambda nid, n: sent.append(nid))
    app.tray = None
    app.show_window()
    app.window.close()
    app.window.present()
    app.window.close()
    assert sent == ["no-tray-hint"]
    assert controller.prefs.no_tray_hint_shown

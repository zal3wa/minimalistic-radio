"""Autostart file, suspend inhibit, network return, station notification and the no-tray hint (Task 14)."""
import time
import uuid

import pytest

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gio, GLib, GObject  # noqa: E402

from minimalistic_radio.app import RadioApplication  # noqa: E402
from minimalistic_radio.controller import RadioController, Status  # noqa: E402
from minimalistic_radio.core.models import Preferences, Station  # noqa: E402
from minimalistic_radio.core.storage import Paths, save_preferences, save_stations  # noqa: E402
from minimalistic_radio.glib_scheduler import GLibScheduler  # noqa: E402
from minimalistic_radio.platform import background, session  # noqa: E402
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
        app = RadioApplication(application_id="io.github.zal3wa.minimalistic-radio-test" + uuid.uuid4().hex[:8])
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
    file = tmp_path / "home" / ".config" / "autostart" / "io.github.zal3wa.minimalistic-radio.desktop"
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


class FakeMonitor(GObject.Object):
    """Stands in for Gio.NetworkMonitor: the test says when the network changes."""
    __gsignals__ = {"network-changed": (GObject.SignalFlags.RUN_LAST, None, (bool,))}

    def __init__(self):
        super().__init__()
        self.available = True

    def get_network_available(self):
        return self.available


def test_network_return_calls_controller(setup):
    _, controller = setup()
    calls = []
    controller.network_available = lambda was_down: calls.append(was_down)
    watcher = SessionWatcher(controller, FakeMonitor())
    try:
        monitor = watcher._monitor
        monitor.emit("network-changed", True)
        monitor.emit("network-changed", True)
        assert pump(lambda: calls, 5)
        settle(2500)
        assert calls == [False]
    finally:
        watcher.close()


def test_playing_station_restarts_only_if_the_network_was_down(setup, monkeypatch):
    monkeypatch.setattr(session, "DEBOUNCE_MS", 100)
    _, controller = setup()
    plays = []
    controller.player.play = plays.append
    monitor = FakeMonitor()
    watcher = SessionWatcher(controller, monitor)
    try:
        controller.select(0)
        controller.play()
        controller.on_player_started()
        assert controller.status is Status.PLAYING and len(plays) == 1
        monitor.emit("network-changed", True)    # a VPN or a new interface: the connection is still good
        settle(500)
        assert controller.status is Status.PLAYING and len(plays) == 1
        monitor.emit("network-changed", False)   # down, then back
        monitor.emit("network-changed", True)
        assert pump(lambda: len(plays) == 2, 5)
        assert controller.status is Status.CONNECTING
    finally:
        watcher.close()


BACKGROUND_XML = """
<node>
  <interface name="org.freedesktop.portal.Background">
    <method name="RequestBackground">
      <arg type="s" direction="in"/><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/>
    </method>
  </interface>
</node>"""


class FakeBackgroundPortal:
    """Answers every request "no", a moment later, as a user who denies it would."""

    def __init__(self):
        self.requests = []
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.owned = False
        self.id = self.bus.register_object(
            "/org/freedesktop/portal/desktop", Gio.DBusNodeInfo.new_for_xml(BACKGROUND_XML).interfaces[0],
            self._request, None, None)
        self.name = Gio.bus_own_name_on_connection(self.bus, "org.freedesktop.portal.Desktop",
                                                   Gio.BusNameOwnerFlags.NONE,
                                                   lambda *_a: setattr(self, "owned", True), None)

    def _request(self, connection, sender, _p, _i, _m, params, invocation):
        _window, options = params.unpack()
        self.requests.append(options)
        handle = ("/org/freedesktop/portal/desktop/request/" + sender[1:].replace(".", "_") + "/"
                  + options["handle_token"])
        invocation.return_value(GLib.Variant("(o)", (handle,)))

        def deny():
            connection.emit_signal(None, handle, "org.freedesktop.portal.Request", "Response",
                                   GLib.Variant("(ua{sv})", (1, {})))
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(100, deny)

    def stop(self):
        Gio.bus_unown_name(self.name)
        self.bus.unregister_object(self.id)


def test_background_portal_denial_turns_the_switch_off(setup, tmp_path, monkeypatch):
    flatpak_info = tmp_path / "flatpak-info"
    flatpak_info.write_text("")
    monkeypatch.setattr(background, "FLATPAK_INFO", str(flatpak_info))
    app, controller = setup()
    portal = FakeBackgroundPortal()
    try:
        assert pump(lambda: portal.owned)
        app.show_window()
        row = app.window.settings_page.autostart_row
        row.set_active(True)
        assert pump(lambda: portal.requests)
        assert portal.requests[0]["autostart"] is True and portal.requests[0]["handle_token"]
        assert portal.requests[0]["reason"] == "Start the radio with the system"
        assert pump(lambda: not row.get_active(), 5)
        assert controller.prefs.autostart is False and len(portal.requests) == 1   # turning it off asked nothing
    finally:
        portal.stop()


def test_switch_notification(setup, monkeypatch):
    app, controller = setup()
    sent = []
    monkeypatch.setattr(app, "send_notification", lambda nid, n: sent.append(nid))
    notifier = StationNotifier(app)
    controller.select(0)
    controller.next_station()
    assert sent == ["station"] and notifier.last_title == "Beta"
    assert notifier.last_body == "Ready to play"   # switched while stopped: the status, not "Connecting…"
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


def test_the_hint_shows_once_with_a_tray_too(setup, monkeypatch):
    app, controller = setup()
    sent = []
    monkeypatch.setattr(app, "send_notification", lambda nid, n: sent.append((nid, n)))

    class VisibleTray:
        visible = True

        def stop(self):
            pass

    app.tray = VisibleTray()
    app.show_window()
    app.window.close()
    app.window.present()
    app.window.close()
    assert [nid for nid, _note in sent] == ["no-tray-hint"]
    assert controller.prefs.no_tray_hint_shown

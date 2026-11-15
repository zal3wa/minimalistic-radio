"""Updates through a fake org.freedesktop.portal.Flatpak on the private session bus (Task 16)."""
from types import SimpleNamespace

import pytest

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gio, GLib  # noqa: E402

from test_platform import pump, setup  # noqa: E402,F401  (the app fixture)

PORTAL_XML = """
<node>
  <interface name="org.freedesktop.portal.Flatpak">
    <property name="version" type="u" access="read"/>
    <method name="CreateUpdateMonitor">
      <arg type="a{sv}" direction="in"/><arg type="o" direction="out"/>
    </method>
    <method name="Spawn">
      <arg type="ay" direction="in"/><arg type="aay" direction="in"/><arg type="a{uh}" direction="in"/>
      <arg type="a{ss}" direction="in"/><arg type="u" direction="in"/><arg type="a{sv}" direction="in"/>
      <arg type="u" direction="out"/>
    </method>
  </interface>
</node>"""
MONITOR_XML = """
<node>
  <interface name="org.freedesktop.portal.Flatpak.UpdateMonitor">
    <method name="Update"><arg type="s" direction="in"/><arg type="a{sv}" direction="in"/></method>
    <signal name="UpdateAvailable"><arg type="a{sv}"/></signal>
    <signal name="Progress"><arg type="a{sv}"/></signal>
  </interface>
</node>"""
PORTAL_PATH = "/org/freedesktop/portal/Flatpak"
MONITOR_PATH = "/org/freedesktop/portal/Flatpak/update_monitor/fake/1"
IFACE = "org.freedesktop.portal.Flatpak.UpdateMonitor"


class FakeFlatpakPortal:
    def __init__(self, version=2):
        self.version = version
        self.updates, self.spawns = [], []
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.owned = False
        self.ids = [
            self.bus.register_object(PORTAL_PATH, Gio.DBusNodeInfo.new_for_xml(PORTAL_XML).interfaces[0],
                                     self._call, lambda *_a: GLib.Variant("u", self.version), None),
            self.bus.register_object(MONITOR_PATH, Gio.DBusNodeInfo.new_for_xml(MONITOR_XML).interfaces[0],
                                     self._monitor_call, None, None)]
        self.name = Gio.bus_own_name_on_connection(self.bus, "org.freedesktop.portal.Flatpak",
                                                   Gio.BusNameOwnerFlags.NONE,
                                                   lambda *_a: setattr(self, "owned", True), None)

    def _call(self, _c, _s, _p, _i, method, params, invocation):
        if method == "CreateUpdateMonitor":
            invocation.return_value(GLib.Variant("(o)", (MONITOR_PATH,)))
        else:
            cwd, argv, _fds, _env, flags, _options = params.unpack()
            self.spawns.append(([bytes(a).rstrip(b"\0").decode() for a in argv], flags))
            invocation.return_value(GLib.Variant("(u)", (4242,)))

    def _monitor_call(self, _c, _s, _p, _i, _m, params, invocation):
        self.updates.append(params.unpack())
        invocation.return_value(None)

    def emit(self, signal, **info):
        values = {k: GLib.Variant("s" if isinstance(v, str) else "u", v) for k, v in info.items()}
        self.bus.emit_signal(None, MONITOR_PATH, IFACE, signal, GLib.Variant("(a{sv})", (values,)))

    def stop(self):
        Gio.bus_unown_name(self.name)
        for i in self.ids:
            self.bus.unregister_object(i)


@pytest.fixture
def started(setup, tmp_path):
    flatpak_info = tmp_path / "flatpak-info"
    flatpak_info.write_text("")
    portals = []

    def build(version=2, window=True):
        app, controller = setup()
        portal = FakeFlatpakPortal(version)
        portals.append(portal)
        assert pump(lambda: portal.owned)
        app.tray = SimpleNamespace(update_label=None, refresh=lambda: None)
        app.quits = []
        app.quit = lambda: app.quits.append(True)
        if window:
            app.show_window()
        app._start_updates(str(flatpak_info))
        return app, controller, portal
    yield build
    for portal in portals:
        portal.stop()


def test_update_shows_arrow_and_tray_item(started):
    app, _, portal = started()
    assert pump(lambda: app.updates.monitor is not None)
    assert not app.window.update_arrow.get_visible()
    portal.emit("UpdateAvailable", **{"running-commit": "a", "local-commit": "a", "remote-commit": "b"})
    assert pump(lambda: app.window.update_arrow.get_visible())
    assert app.window.update_arrow.get_tooltip_text() == "Update"
    assert app.tray.update_label == "Update"
    portal.emit("UpdateAvailable", **{"running-commit": "a", "local-commit": "b", "remote-commit": "b"})
    assert pump(lambda: app.window.update_arrow.get_tooltip_text() == "Restart to update")
    assert app.tray.update_label == "Restart to update"


def test_apply_updates_then_restarts(started):
    app, controller, portal = started()
    assert pump(lambda: app.updates.monitor is not None)
    portal.emit("UpdateAvailable", **{"running-commit": "a", "local-commit": "a", "remote-commit": "b"})
    assert pump(lambda: app.updates.state == "update")
    app.updates.apply()
    assert pump(lambda: portal.updates)
    assert portal.updates == [("", {})] and not portal.spawns
    portal.emit("Progress", status=2)
    assert pump(lambda: app.quits)
    # Not playing, with the window open: the new version opens its window, without playing.
    assert portal.spawns == [(["minimalistic-radio", "--updated", "--stopped"], 2)]
    # Not playing, with the window hidden (the tray's item): it starts hidden.
    app.window.set_visible(False)
    app.updates._restart()
    assert pump(lambda: len(app.quits) == 2)
    assert portal.spawns[-1] == (["minimalistic-radio", "--updated", "--autostart"], 2)


def test_restart_while_playing_keeps_playing(started):
    app, controller, portal = started()
    assert pump(lambda: app.updates.monitor is not None)
    controller.select(0)
    controller.play()
    portal.emit("UpdateAvailable", **{"running-commit": "a", "local-commit": "b", "remote-commit": "b"})
    assert pump(lambda: app.updates.state == "restart")
    app.updates.apply()
    assert pump(lambda: app.quits)
    assert portal.updates == []
    assert portal.spawns == [(["minimalistic-radio", "--updated"], 2)]


def test_failed_update_toasts(started):
    app, _, portal = started()
    assert pump(lambda: app.updates.monitor is not None)
    portal.emit("UpdateAvailable", **{"running-commit": "a", "local-commit": "a", "remote-commit": "b"})
    assert pump(lambda: app.updates.state == "update")
    app.updates.apply()
    assert pump(lambda: portal.updates)
    portal.emit("Progress", status=3)
    assert pump(lambda: app.window._toast is not None)
    assert app.window._toast.get_title() == "Couldn't update. Try again later."
    assert not app.quits


def test_old_portal_never_shows(started):
    app, _, portal = started(version=1)
    assert pump(lambda: app.updates.checked)
    portal.emit("UpdateAvailable", **{"running-commit": "a", "local-commit": "a", "remote-commit": "b"})
    assert not pump(lambda: app.window.update_arrow.get_visible(), 0.5)


def test_missing_portal_never_shows(setup, tmp_path):
    app, _ = setup()
    app.show_window()
    info = tmp_path / "flatpak-info"
    info.write_text("")
    app._start_updates(str(info))
    assert pump(lambda: app.updates.checked)
    assert not app.window.update_arrow.get_visible() and app.updates.state is None

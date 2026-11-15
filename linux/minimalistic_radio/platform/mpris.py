"""MPRIS over D-Bus: the media keys, the GNOME shell media widget and playerctl control the radio.

Pause means Stop, like on Windows: a radio stream has nothing to resume.
"""
from __future__ import annotations

import os
from typing import Any

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from .. import APP_ID, APP_NAME  # noqa: E402
from ..controller import Change, Status  # noqa: E402
from .menu_model import mpris_metadata  # noqa: E402

OBJECT_PATH = "/org/mpris/MediaPlayer2"
ROOT_IFACE = "org.mpris.MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
PROPERTIES_IFACE = "org.freedesktop.DBus.Properties"

INTROSPECTION = f"""
<node>
  <interface name="{ROOT_IFACE}">
    <method name="Raise"/>
    <method name="Quit"/>
    <property name="CanQuit" type="b" access="read"/>
    <property name="CanRaise" type="b" access="read"/>
    <property name="HasTrackList" type="b" access="read"/>
    <property name="Identity" type="s" access="read"/>
    <property name="DesktopEntry" type="s" access="read"/>
    <property name="SupportedUriSchemes" type="as" access="read"/>
    <property name="SupportedMimeTypes" type="as" access="read"/>
  </interface>
  <interface name="{PLAYER_IFACE}">
    <method name="Next"/>
    <method name="Previous"/>
    <method name="Pause"/>
    <method name="PlayPause"/>
    <method name="Stop"/>
    <method name="Play"/>
    <method name="Seek"><arg direction="in" name="Offset" type="x"/></method>
    <method name="SetPosition">
      <arg direction="in" name="TrackId" type="o"/>
      <arg direction="in" name="Position" type="x"/>
    </method>
    <method name="OpenUri"><arg direction="in" name="Uri" type="s"/></method>
    <signal name="Seeked"><arg name="Position" type="x"/></signal>
    <property name="PlaybackStatus" type="s" access="read"/>
    <property name="LoopStatus" type="s" access="readwrite"/>
    <property name="Rate" type="d" access="readwrite"/>
    <property name="Shuffle" type="b" access="readwrite"/>
    <property name="Metadata" type="a{{sv}}" access="read"/>
    <property name="Volume" type="d" access="readwrite"/>
    <property name="Position" type="x" access="read"/>
    <property name="MinimumRate" type="d" access="read"/>
    <property name="MaximumRate" type="d" access="read"/>
    <property name="CanGoNext" type="b" access="read"/>
    <property name="CanGoPrevious" type="b" access="read"/>
    <property name="CanPlay" type="b" access="read"/>
    <property name="CanPause" type="b" access="read"/>
    <property name="CanSeek" type="b" access="read"/>
    <property name="CanControl" type="b" access="read"/>
  </interface>
</node>
"""

# Metadata keys and their D-Bus types.
_METADATA_TYPES = {
    "mpris:trackid": "o",
    "xesam:title": "s",
    "xesam:artist": "as",
    "xesam:album": "s",
    "mpris:artUrl": "s",
}


def bus_name() -> str:
    if os.environ.get("SNAP_NAME"):
        return "org.mpris.MediaPlayer2.minimalistic_radio"
    return "org.mpris.MediaPlayer2." + APP_ID


class MprisService:
    def __init__(self, app: Any, name: str | None = None) -> None:
        self.app = app
        self._name = name
        self._connection: Gio.DBusConnection | None = None
        self._registrations: list[int] = []
        self._owner = 0
        self.acquired = False   # the bus name is ours
        self.error: str | None = None   # why publishing failed
        self.lost = False       # the bus name was refused or taken
        self._last: dict[str, Any] = {}
        self._subscribed = False
        nodes = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION)
        self._root_info = nodes.lookup_interface(ROOT_IFACE)
        self._player_info = nodes.lookup_interface(PLAYER_IFACE)

    @property
    def controller(self):
        return self.app.controller

    # ---- Publishing ----

    def publish(self) -> None:
        if self._connection is not None:
            return
        try:
            self._connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            for info in (self._root_info, self._player_info):
                self._registrations.append(self._connection.register_object(
                    OBJECT_PATH, info, self._on_method_call, self._on_get_property, self._on_set_property))
        except GLib.Error as error:
            self.error = error.message
            self._connection = None   # no session bus: the radio works without media keys
            return
        if not self._subscribed:
            self._subscribed = True
            self.controller.subscribe(self._on_change)
        self._last = self._player_properties()
        # The same shared session connection the objects are registered on.
        self._owner = Gio.bus_own_name(
            Gio.BusType.SESSION, self._name or bus_name(), Gio.BusNameOwnerFlags.NONE, None,
            lambda connection, name: setattr(self, "acquired", True),
            lambda connection, name: setattr(self, "lost", True))

    def unpublish(self) -> None:
        if self._connection is None:
            return
        if self._owner:
            Gio.bus_unown_name(self._owner)
            self._owner = 0
            self.acquired = False
        for registration in self._registrations:
            self._connection.unregister_object(registration)
        self._registrations = []
        self._connection = None

    # ---- Properties ----

    def _metadata(self) -> GLib.Variant:
        values = {key: GLib.Variant(_METADATA_TYPES[key], value)
                  for key, value in mpris_metadata(self.controller).items() if key in _METADATA_TYPES}
        return GLib.Variant("a{sv}", values)

    def _player_properties(self) -> dict[str, GLib.Variant]:
        c = self.controller
        playing = c.status in (Status.CONNECTING, Status.PLAYING, Status.RETRYING)
        many = len(c.stations) > 1
        return {
            "PlaybackStatus": GLib.Variant("s", "Playing" if playing else "Stopped"),
            "Metadata": self._metadata(),
            "Volume": GLib.Variant("d", c.volume / 100),
            "CanGoNext": GLib.Variant("b", many),
            "CanGoPrevious": GLib.Variant("b", many),
            "CanPlay": GLib.Variant("b", bool(c.stations)),
            "CanPause": GLib.Variant("b", True),
        }

    @staticmethod
    def _static_player_properties() -> dict[str, GLib.Variant]:
        return {
            "LoopStatus": GLib.Variant("s", "None"),
            "Rate": GLib.Variant("d", 1.0),
            "Shuffle": GLib.Variant("b", False),
            "Position": GLib.Variant("x", 0),
            "MinimumRate": GLib.Variant("d", 1.0),
            "MaximumRate": GLib.Variant("d", 1.0),
            "CanSeek": GLib.Variant("b", False),
            "CanControl": GLib.Variant("b", True),
        }

    @staticmethod
    def _root_properties() -> dict[str, GLib.Variant]:
        return {
            "CanQuit": GLib.Variant("b", True),
            "CanRaise": GLib.Variant("b", True),
            "HasTrackList": GLib.Variant("b", False),
            "Identity": GLib.Variant("s", APP_NAME),
            "DesktopEntry": GLib.Variant("s", APP_ID),
            "SupportedUriSchemes": GLib.Variant("as", []),
            "SupportedMimeTypes": GLib.Variant("as", []),
        }

    def _on_get_property(self, connection, sender, path, interface, name):
        if interface == ROOT_IFACE:
            return self._root_properties().get(name)
        return {**self._static_player_properties(), **self._player_properties()}.get(name)

    def _on_set_property(self, connection, sender, path, interface, name, value) -> bool:
        if interface == PLAYER_IFACE and name == "Volume":
            self.controller.set_volume(round(value.get_double() * 100))
            return True
        return interface == PLAYER_IFACE and name in ("LoopStatus", "Rate", "Shuffle")   # accepted, ignored

    def _on_change(self, change: Change) -> None:
        if self._connection is None:
            return
        current = self._player_properties()
        changed = {k: v for k, v in current.items() if k not in self._last or not v.equal(self._last[k])}
        self._last = current
        if not changed:
            return
        try:
            self._connection.emit_signal(
                None, OBJECT_PATH, PROPERTIES_IFACE, "PropertiesChanged",
                GLib.Variant("(sa{sv}as)", (PLAYER_IFACE, changed, [])))
        except GLib.Error:
            pass

    # ---- Methods ----

    def _on_method_call(self, connection, sender, path, interface, method, parameters, invocation) -> None:
        c = self.controller
        if interface == ROOT_IFACE:
            if method == "Raise":
                self.app.show_window()
            elif method == "Quit":
                self.app.quit()
        elif method == "PlayPause":
            c.toggle()
        elif method == "Play":
            c.play()
        elif method in ("Pause", "Stop"):
            c.stop()
        elif method == "Next":
            c.next_station()
        elif method == "Previous":
            c.previous_station()
        # Seek, SetPosition and OpenUri: nothing to seek in a live stream.
        invocation.return_value(None)

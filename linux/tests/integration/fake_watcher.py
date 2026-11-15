"""A StatusNotifierWatcher for the tray tests.

It owns org.kde.StatusNotifierWatcher on its own connection to the session bus (so the tray sees another
peer, as with a real desktop), records RegisterStatusNotifierItem calls and answers
IsStatusNotifierHostRegistered. stop() and start() play a desktop panel restarting.
"""
import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

NAME = "org.kde.StatusNotifierWatcher"
PATH = "/StatusNotifierWatcher"
DO_NOT_QUEUE = 4
PRIMARY_OWNER = 1

INTROSPECTION = f"""
<node>
  <interface name="{NAME}">
    <method name="RegisterStatusNotifierItem"><arg direction="in" name="service" type="s"/></method>
    <method name="RegisterStatusNotifierHost"><arg direction="in" name="service" type="s"/></method>
    <property name="RegisteredStatusNotifierItems" type="as" access="read"/>
    <property name="IsStatusNotifierHostRegistered" type="b" access="read"/>
    <property name="ProtocolVersion" type="i" access="read"/>
    <signal name="StatusNotifierItemRegistered"><arg type="s"/></signal>
    <signal name="StatusNotifierItemUnregistered"><arg type="s"/></signal>
    <signal name="StatusNotifierHostRegistered"/>
    <signal name="StatusNotifierHostUnregistered"/>
  </interface>
</node>
"""


class FakeWatcher:
    def __init__(self, host: bool = True) -> None:
        self.host = host
        self.registered: list[tuple[str, str]] = []   # (sender, service) per RegisterStatusNotifierItem
        self._connection: Gio.DBusConnection | None = None
        self._registration = 0
        self._info = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION).lookup_interface(NAME)

    def start(self) -> None:
        address = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
        self._connection = Gio.DBusConnection.new_for_address_sync(
            address,
            Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
            None, None)
        self._registration = self._connection.register_object(PATH, self._info, self._on_call, self._on_get, None)
        reply = self._connection.call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "RequestName",
            GLib.Variant("(su)", (NAME, DO_NOT_QUEUE)), GLib.VariantType("(u)"), Gio.DBusCallFlags.NONE, 5000, None)
        assert reply.unpack()[0] == PRIMARY_OWNER, "another watcher owns the name"

    def stop(self) -> None:
        """Leaves the bus, as a panel that quits: the name vanishes."""
        if self._connection is None:
            return
        self._connection.unregister_object(self._registration)
        self._connection.close_sync(None)
        self._connection = None

    def _on_call(self, connection, sender, path, interface, method, parameters, invocation) -> None:
        if method == "RegisterStatusNotifierItem":
            service = parameters.unpack()[0]
            self.registered.append((sender, service))
            connection.emit_signal(None, PATH, NAME, "StatusNotifierItemRegistered",
                                   GLib.Variant("(s)", (sender + service,)))
        invocation.return_value(None)

    def _on_get(self, connection, sender, path, interface, name):
        if name == "IsStatusNotifierHostRegistered":
            return GLib.Variant("b", self.host)
        if name == "RegisteredStatusNotifierItems":
            return GLib.Variant("as", [s + service for s, service in self.registered])
        if name == "ProtocolVersion":
            return GLib.Variant("i", 0)
        return None

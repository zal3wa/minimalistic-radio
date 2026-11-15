"""com.canonical.dbusmenu (version 3): the tray menu as data on D-Bus; the desktop draws it.

Items are numbered on first sight and keep their number for as long as the menu exists, so a number is
stable within a layout revision (and across them). The root is 0.
"""
from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from .menu_model import MenuItem  # noqa: E402

IFACE = "com.canonical.dbusmenu"
ROOT = 0

INTROSPECTION = f"""
<node>
  <interface name="{IFACE}">
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
    <method name="GetLayout">
      <arg direction="in" name="parentId" type="i"/>
      <arg direction="in" name="recursionDepth" type="i"/>
      <arg direction="in" name="propertyNames" type="as"/>
      <arg direction="out" name="revision" type="u"/>
      <arg direction="out" name="layout" type="(ia{{sv}}av)"/>
    </method>
    <method name="GetGroupProperties">
      <arg direction="in" name="ids" type="ai"/>
      <arg direction="in" name="propertyNames" type="as"/>
      <arg direction="out" name="properties" type="a(ia{{sv}})"/>
    </method>
    <method name="GetProperty">
      <arg direction="in" name="id" type="i"/>
      <arg direction="in" name="name" type="s"/>
      <arg direction="out" name="value" type="v"/>
    </method>
    <method name="Event">
      <arg direction="in" name="id" type="i"/>
      <arg direction="in" name="eventId" type="s"/>
      <arg direction="in" name="data" type="v"/>
      <arg direction="in" name="timestamp" type="u"/>
    </method>
    <method name="EventGroup">
      <arg direction="in" name="events" type="a(isvu)"/>
      <arg direction="out" name="idErrors" type="ai"/>
    </method>
    <method name="AboutToShow">
      <arg direction="in" name="id" type="i"/>
      <arg direction="out" name="needUpdate" type="b"/>
    </method>
    <method name="AboutToShowGroup">
      <arg direction="in" name="ids" type="ai"/>
      <arg direction="out" name="updatesNeeded" type="ai"/>
      <arg direction="out" name="idErrors" type="ai"/>
    </method>
    <signal name="ItemsPropertiesUpdated">
      <arg name="updatedProps" type="a(ia{{sv}})"/>
      <arg name="removedProps" type="a(ias)"/>
    </signal>
    <signal name="LayoutUpdated">
      <arg name="revision" type="u"/>
      <arg name="parent" type="i"/>
    </signal>
    <signal name="ItemActivationRequested">
      <arg name="id" type="i"/>
      <arg name="timestamp" type="u"/>
    </signal>
  </interface>
</node>
"""

_MENU_PROPERTIES = {
    "Version": GLib.Variant("u", 3),
    "TextDirection": GLib.Variant("s", "ltr"),
    "Status": GLib.Variant("s", "normal"),
    "IconThemePath": GLib.Variant("as", []),
}


def label(text: str) -> str:
    """DBusMenu reads "_" as the mark of a keyboard shortcut; doubled, a station or song keeps its "_"."""
    return text.replace("_", "__")


def _properties(item: MenuItem) -> dict[str, GLib.Variant]:
    if item.separator:
        return {"type": GLib.Variant("s", "separator")}
    props = {"label": GLib.Variant("s", label(item.label))}
    if not item.enabled:
        props["enabled"] = GLib.Variant("b", False)
    if item.icon:
        props["icon-name"] = GLib.Variant("s", item.icon)
    if item.toggle:
        props["toggle-type"] = GLib.Variant("s", item.toggle)
        props["toggle-state"] = GLib.Variant("i", 1 if item.checked else 0)
    if item.children:
        props["children-display"] = GLib.Variant("s", "submenu")
    return props


class DBusMenu:
    def __init__(self, connection: Gio.DBusConnection, path: str = "/MenuBar") -> None:
        """Exports the (empty) menu at `path`. A D-Bus error is raised, never hidden."""
        self.connection = connection
        self.path = path
        self.activated: Callable[[str], None] = lambda key: None   # called with the MenuItem id of a click
        self.revision = 0
        self._items: list[MenuItem] | None = None
        self._numbers: dict[str, int] = {}          # MenuItem id -> number, for as long as the menu exists
        self._nodes: dict[int, MenuItem] = {}       # the current layout, by number
        self._served: dict[int, int] = {}           # number -> the revision whose children GetLayout last sent
        info = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION).lookup_interface(IFACE)
        self._registration = connection.register_object(path, info, self._on_method_call, self._on_get_property, None)

    def unregister(self) -> None:
        if self._registration:
            self.connection.unregister_object(self._registration)
            self._registration = 0

    def id_of(self, key: str) -> int:
        """The number of the item with MenuItem id `key` in the current layout."""
        number = self._numbers[key]
        if number not in self._nodes:
            raise KeyError(key)
        return number

    def set_items(self, items: list[MenuItem]) -> None:
        """Shows `items`; the desktop is told (LayoutUpdated) only when something changed."""
        if items == self._items:
            return
        self._items = items
        self._nodes = {}
        self._index(items)
        self.revision += 1
        try:
            self.connection.emit_signal(None, self.path, IFACE, "LayoutUpdated",
                                        GLib.Variant("(ui)", (self.revision, ROOT)))
        except GLib.Error:
            pass   # the bus is gone: nothing listens

    def _index(self, items: list[MenuItem]) -> None:
        for item in items:
            number = self._numbers.setdefault(item.id, len(self._numbers) + 1)
            self._nodes[number] = item
            self._index(item.children)

    # ---- Layout ----

    def _item_properties(self, number: int, names: list[str]) -> dict[str, GLib.Variant]:
        if number == ROOT:
            props = {"children-display": GLib.Variant("s", "submenu")}
        else:
            props = _properties(self._nodes[number])
        return {k: v for k, v in props.items() if k in names} if names else props

    def _layout(self, number: int, depth: int, names: list[str]) -> tuple:
        children = (self._items or []) if number == ROOT else self._nodes[number].children
        nested = []
        if depth != 0:
            self._served[number] = self.revision
            nested = [GLib.Variant("(ia{sv}av)", self._layout(self._numbers[child.id], depth - 1, names))
                      for child in children]
        return number, self._item_properties(number, names), nested

    def _known(self, number: int) -> bool:
        return number == ROOT or number in self._nodes

    # ---- D-Bus ----

    def _on_get_property(self, connection, sender, path, interface, name):
        return _MENU_PROPERTIES.get(name)

    def _on_method_call(self, connection, sender, path, interface, method, parameters, invocation) -> None:
        args = parameters.unpack()
        if method == "GetLayout":
            parent, depth, names = args
            if not self._known(parent):
                invocation.return_dbus_error("org.freedesktop.DBus.Error.InvalidArgs", f"No menu item {parent}")
                return
            invocation.return_value(GLib.Variant("(u(ia{sv}av))", (self.revision, self._layout(parent, depth, names))))
        elif method == "GetGroupProperties":
            ids, names = args
            wanted = [n for n in ids if self._known(n)] if ids else [ROOT, *self._nodes]
            invocation.return_value(GLib.Variant(
                "(a(ia{sv}))", ([(n, self._item_properties(n, names)) for n in wanted],)))
        elif method == "GetProperty":
            number, name = args
            value = self._item_properties(number, [name]).get(name) if self._known(number) else None
            if value is None:
                invocation.return_dbus_error("org.freedesktop.DBus.Error.InvalidArgs", f"No {name} on {number}")
                return
            invocation.return_value(GLib.Variant("(v)", (value,)))
        elif method == "Event":
            number, event = args[0], args[1]
            invocation.return_value(None)   # answered first: the click may open a window or quit
            self._event(number, event)
        elif method == "EventGroup":
            events = args[0]
            invocation.return_value(GLib.Variant("(ai)", ([e[0] for e in events if not self._known(e[0])],)))
            for number, event, _data, _time in events:
                self._event(number, event)
        elif method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (self._stale(args[0]),)))
        elif method == "AboutToShowGroup":
            ids = args[0]
            invocation.return_value(GLib.Variant("(aiai)", ([n for n in ids if self._stale(n)],
                                                            [n for n in ids if not self._known(n)])))
        else:
            invocation.return_value(None)

    def _stale(self, number: int) -> bool:
        """The desktop's copy of this submenu is older than the menu: KDE reads it again only when told so."""
        return self._known(number) and self._served.get(number) != self.revision

    def _event(self, number: int, event: str) -> None:
        item = self._nodes.get(number)
        if event == "clicked" and item is not None and item.enabled and not item.separator:
            self.activated(item.id)

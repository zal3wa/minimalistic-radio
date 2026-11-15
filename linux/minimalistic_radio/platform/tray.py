"""The tray icon next to the clock: a StatusNotifierItem whose menu is a dbusmenu, both on the session bus.

The item registers with the StatusNotifierWatcher by object path, on the app's unique bus name: a PID-based
well-known name (org.kde.StatusNotifierItem-PID-ID) fails in Flatpak. When the watcher restarts (a panel
restarting) the item registers again. Without a watcher with a registered host (plain GNOME), `visible` is
False and the app is an ordinary window app.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib, GObject  # noqa: E402

from .. import APP_ID, APP_NAME  # noqa: E402
from .. import main as entry  # noqa: E402
from . import in_snap  # noqa: E402
from .dbusmenu import DBusMenu  # noqa: E402
from .menu_model import build_tray_menu, tooltip  # noqa: E402

ITEM_PATH = "/StatusNotifierItem"
ITEM_IFACE = "org.kde.StatusNotifierItem"
MENU_PATH = "/MenuBar"
WATCHER = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
PROPERTIES_IFACE = "org.freedesktop.DBus.Properties"
ICON_NAME = APP_ID + "-symbolic"
PIXMAP_SIZES = (16, 22, 32, 48)
SCROLL_NOTCH = 120       # one wheel notch, as KDE counts it
GTK_SCROLL_MAX = 2       # a delta this small is counted in notches, the GDK way (positive = down)
VOLUME_STEP = 5
FOCUS_WAIT_MS = 1000

INTROSPECTION = f"""
<node>
  <interface name="{ITEM_IFACE}">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="i" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconPixmap" type="a(iiay)" access="read"/>
    <property name="OverlayIconName" type="s" access="read"/>
    <property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
    <property name="AttentionIconName" type="s" access="read"/>
    <property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
    <property name="AttentionMovieName" type="s" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <method name="ContextMenu"><arg direction="in" name="x" type="i"/><arg direction="in" name="y" type="i"/></method>
    <method name="Activate"><arg direction="in" name="x" type="i"/><arg direction="in" name="y" type="i"/></method>
    <method name="SecondaryActivate">
      <arg direction="in" name="x" type="i"/><arg direction="in" name="y" type="i"/>
    </method>
    <method name="Scroll">
      <arg direction="in" name="delta" type="i"/><arg direction="in" name="orientation" type="s"/>
    </method>
    <method name="ProvideXdgActivationToken"><arg direction="in" name="token" type="s"/></method>
    <signal name="NewTitle"/>
    <signal name="NewIcon"/>
    <signal name="NewAttentionIcon"/>
    <signal name="NewOverlayIcon"/>
    <signal name="NewToolTip"/>
    <signal name="NewStatus"><arg name="status" type="s"/></signal>
  </interface>
</node>
"""


def _warn(text: str) -> None:
    print(f"{APP_NAME}: {text}", file=sys.stderr)


def _icon_file() -> Path | None:
    """The full-colour app icon: installed (XDG data dirs, the launcher's prefix) or in the source tree."""
    relative = Path("icons", "hicolor", "scalable", "apps", APP_ID + ".svg")
    roots = [Path(GLib.get_user_data_dir()), *map(Path, GLib.get_system_data_dirs()),
             Path(entry.PKGDATADIR).parent, Path(__file__).resolve().parents[2] / "data"]
    return next((root / relative for root in roots if (root / relative).is_file()), None)


def icon_theme_path() -> str:
    """In the Snap, the snap's icons folder, which the host can read: the host's icon theme doesn't have the
    symbolic icon, so the host would show the full-colour pixmaps. Elsewhere the icon is in the host's theme."""
    snap = os.environ.get("SNAP")
    return os.path.join(snap, "usr", "share", "icons") if in_snap() and snap else ""


def _argb(pixbuf: GdkPixbuf.Pixbuf) -> bytes:
    """ARGB32 in network byte order (A, R, G, B per pixel), rows without padding, as SNI wants."""
    if not pixbuf.get_has_alpha():
        pixbuf = pixbuf.add_alpha(False, 0, 0, 0)
    width, height, stride = pixbuf.get_width(), pixbuf.get_height(), pixbuf.get_rowstride()
    raw = pixbuf.read_pixel_bytes().get_data()
    rgba = b"".join(raw[row * stride:row * stride + width * 4] for row in range(height))
    argb = bytearray(len(rgba))
    argb[0::4] = rgba[3::4]
    argb[1::4] = rgba[0::4]
    argb[2::4] = rgba[1::4]
    argb[3::4] = rgba[2::4]
    return bytes(argb)


def icon_pixmaps() -> list[tuple[int, int, bytes]]:
    """The app icon at 16, 22, 32 and 48 px, for hosts that can't find it by name (such as for the Snap).

    The full-colour icon: a symbolic pixmap can't follow the panel's colours."""
    path = _icon_file()
    if path is None:
        _warn("the app icon wasn't found; the tray shows it by name only")
        return []
    images = []
    for size in PIXMAP_SIZES:
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(path), size, size)
        except GLib.Error as error:
            _warn(f"the app icon couldn't be drawn ({error.message}); the tray shows it by name only")
            return []
        images.append((pixbuf.get_width(), pixbuf.get_height(), _argb(pixbuf)))
    return images


def pixmap_variant(images: list[tuple[int, int, bytes]]) -> GLib.Variant:
    """a(iiay), with each image's bytes as they are."""
    builder = GLib.VariantBuilder.new(GLib.VariantType("a(iiay)"))
    for width, height, data in images:
        image = GLib.VariantBuilder.new(GLib.VariantType("(iiay)"))
        image.add_value(GLib.Variant("i", width))
        image.add_value(GLib.Variant("i", height))
        image.add_value(GLib.Variant.new_from_bytes(GLib.VariantType("ay"), GLib.Bytes.new(data), True))
        builder.add_value(image.end())
    return builder.end()


def _on_wayland(window: Any) -> bool:
    """On Wayland only the focused app may set the clipboard; on X11 any app can."""
    return window.get_display().__gtype__.name.startswith("GdkWayland")


def _when_focused(window: Any, focused: Callable[[], None], unfocused: Callable[[], None]) -> None:
    """Runs `focused` once `window` has the focus, or `unfocused` after FOCUS_WAIT_MS if it never gets it."""
    if window.is_active():
        focused()
        return
    done = []

    def finish(callback: Callable[[], None]) -> None:
        if not done:
            done.append(True)
            window.disconnect(handler)
            callback()

    def on_active(_window: Any, _pspec: Any) -> None:
        if window.is_active():
            GLib.source_remove(timer)
            finish(focused)

    def on_timeout() -> bool:
        finish(unfocused)
        return GLib.SOURCE_REMOVE

    handler = window.connect("notify::is-active", on_active)
    timer = GLib.timeout_add(FOCUS_WAIT_MS, on_timeout)


class TrayIcon(GObject.Object):
    __gsignals__ = {
        # Whether a tray shows the icon: a watcher with a registered host exists.
        "host-changed": (GObject.SignalFlags.RUN_LAST, None, (bool,)),
    }

    def __init__(self, app: Any) -> None:
        super().__init__()
        self.app = app
        self.menu: DBusMenu | None = None
        self.error: str | None = None          # why the tray couldn't be shown
        self.update_label: str | None = None   # the menu's "Update" item, when an update is ready (Task 16)
        self._connection: Gio.DBusConnection | None = None
        self._registration = 0
        self._watch = 0
        self._watcher: str | None = None       # the watcher's unique name, while it exists
        self._watcher_signals = 0
        self._visible: bool | None = None      # None until known
        self._tooltip: tuple[str, str] | None = None
        self._pixmaps = GLib.Variant("a(iiay)", [])
        self._scroll_rest = 0                  # KDE's wheel: the part of a notch not yet turned into a step
        self._activation_token: str | None = None   # from the desktop, for the next window shown (KDE Wayland)
        self._subscribed = False
        self._info = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION).lookup_interface(ITEM_IFACE)

    @property
    def controller(self):
        return self.app.controller

    @property
    def visible(self) -> bool:
        return bool(self._visible)

    def _set_visible(self, visible: bool) -> None:
        if visible != self._visible:
            self._visible = visible
            self.emit("host-changed", visible)

    # ---- Start and stop ----

    def start(self) -> None:
        if self._connection is not None:
            return
        try:
            connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self.menu = DBusMenu(connection, MENU_PATH)
            self._registration = connection.register_object(
                ITEM_PATH, self._info, self._on_method_call, self._on_get_property, None)
        except GLib.Error as error:
            self.error = error.message
            _warn(f"no tray icon: {error.message}")
            if self.menu is not None:
                self.menu.unregister()
                self.menu = None
            self._set_visible(False)
            return
        self._connection = connection
        self.menu.activated = self._on_menu
        self._pixmaps = pixmap_variant(icon_pixmaps())
        if not self._subscribed:
            self._subscribed = True
            self.controller.subscribe(lambda change: self.refresh())
        self.refresh()
        self._watch = Gio.bus_watch_name(Gio.BusType.SESSION, WATCHER, Gio.BusNameWatcherFlags.NONE,
                                         self._watcher_appeared, self._watcher_vanished)

    def stop(self) -> None:
        if self._watch:
            Gio.bus_unwatch_name(self._watch)
            self._watch = 0
        self._forget_watcher()
        if self._connection is None:
            return
        self._connection.unregister_object(self._registration)
        self._registration = 0
        self.menu.unregister()
        self.menu = None
        self._connection = None
        self._set_visible(False)

    def refresh(self) -> None:
        """Builds the menu and the tooltip again from the controller (and `update_label`)."""
        if self._connection is None:
            return
        self.menu.set_items(build_tray_menu(self.controller, self.app._, self.update_label))
        tip = tooltip(self.controller)
        if tip != self._tooltip:
            self._tooltip = tip
            self._emit("NewToolTip")

    def _emit(self, signal: str) -> None:
        try:
            self._connection.emit_signal(None, ITEM_PATH, ITEM_IFACE, signal, None)
        except GLib.Error:
            pass   # the bus is gone: nothing listens

    # ---- The watcher ----

    def _watcher_appeared(self, connection: Gio.DBusConnection, name: str, owner: str) -> None:
        self._forget_watcher()
        if self._connection is None:
            return
        self._watcher = owner
        self._watcher_signals = self._connection.signal_subscribe(
            owner, WATCHER, None, WATCHER_PATH, None, Gio.DBusSignalFlags.NONE, self._on_watcher_signal)
        self._connection.call(
            owner, WATCHER_PATH, WATCHER, "RegisterStatusNotifierItem", GLib.Variant("(s)", (ITEM_PATH,)),
            None, Gio.DBusCallFlags.NONE, -1, None, lambda c, result: self._registered(c, result, owner))

    def _watcher_vanished(self, connection: Gio.DBusConnection | None, name: str) -> None:
        self._forget_watcher()
        self._set_visible(False)

    def _forget_watcher(self) -> None:
        if self._watcher_signals and self._connection is not None:
            self._connection.signal_unsubscribe(self._watcher_signals)
        self._watcher_signals = 0
        self._watcher = None

    def _registered(self, connection: Gio.DBusConnection, result: Gio.AsyncResult, owner: str) -> None:
        try:
            connection.call_finish(result)
        except GLib.Error as error:
            if owner == self._watcher:
                self.error = error.message
                _warn(f"the tray refused the icon: {error.message}")
                self._set_visible(False)
            return
        if owner == self._watcher:
            self._ask_for_host(owner)

    def _ask_for_host(self, owner: str) -> None:
        def answered(connection: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                host = bool(connection.call_finish(result).unpack()[0])
            except GLib.Error:
                host = False
            if owner == self._watcher:
                self._set_visible(host)

        self._connection.call(
            owner, WATCHER_PATH, PROPERTIES_IFACE, "Get",
            GLib.Variant("(ss)", (WATCHER, "IsStatusNotifierHostRegistered")), GLib.VariantType("(v)"),
            Gio.DBusCallFlags.NONE, -1, None, answered)

    def _on_watcher_signal(self, connection, sender, path, interface, signal, parameters) -> None:
        if signal in ("StatusNotifierHostRegistered", "StatusNotifierHostUnregistered") and self._watcher:
            self._ask_for_host(self._watcher)

    # ---- The item ----

    def _on_get_property(self, connection, sender, path, interface, name):
        if name == "ToolTip":
            title, body = tooltip(self.controller)
            if any(mark in body for mark in "&<>"):
                # Xfce reads the body as markup and KDE guesses: escaped in a <span>, both show the text as it is.
                body = f"<span>{GLib.markup_escape_text(body, -1)}</span>"
            return GLib.Variant("(sa(iiay)ss)", ("", [], title, body))
        if name == "IconPixmap":
            return self._pixmaps
        return {
            "Category": GLib.Variant("s", "ApplicationStatus"),
            "Id": GLib.Variant("s", APP_ID),
            "Title": GLib.Variant("s", APP_NAME),
            "Status": GLib.Variant("s", "Active"),
            "WindowId": GLib.Variant("i", 0),
            "IconThemePath": GLib.Variant("s", icon_theme_path()),
            "IconName": GLib.Variant("s", ICON_NAME),
            "OverlayIconName": GLib.Variant("s", ""),
            "OverlayIconPixmap": GLib.Variant("a(iiay)", []),
            "AttentionIconName": GLib.Variant("s", ""),
            "AttentionIconPixmap": GLib.Variant("a(iiay)", []),
            "AttentionMovieName": GLib.Variant("s", ""),
            "ItemIsMenu": GLib.Variant("b", False),
            "Menu": GLib.Variant("o", MENU_PATH),
        }.get(name)

    def _on_method_call(self, connection, sender, path, interface, method, parameters, invocation) -> None:
        invocation.return_value(None)   # answered first: the click may open the window
        if method == "ProvideXdgActivationToken":
            self._activation_token = parameters.unpack()[0] or None
        elif method == "Activate":
            self._show_panel()
        elif method == "SecondaryActivate":
            self.controller.toggle()
        elif method == "Scroll":
            delta, orientation = parameters.unpack()
            self._scroll(delta, orientation)
        # ContextMenu: the desktop draws the menu itself, from Menu.

    def _scroll(self, delta: int, orientation: str) -> None:
        """A notch up is 5 % louder. KDE sends 120 per notch, positive up (a touchpad sends parts of it); the
        Ubuntu AppIndicator extension and Xfce send 1 per notch, positive down, as GDK counts."""
        if orientation.lower() != "vertical" or delta == 0:
            return
        if abs(delta) <= GTK_SCROLL_MAX:
            steps = -delta
        else:
            self._scroll_rest += delta
            steps = int(self._scroll_rest / SCROLL_NOTCH)   # toward zero: the rest waits for the next part
            self._scroll_rest -= steps * SCROLL_NOTCH
        if steps:
            self.controller.set_volume(self.controller.volume + steps * VOLUME_STEP)

    # ---- The menu ----

    def _action(self, name: str) -> None:
        if self.app.lookup_action(name) is not None:
            self.app.activate_action(name, None)

    def _show_panel(self) -> None:
        """Opens the panel with the desktop's activation token, if it sent one, so KDE on Wayland focuses it."""
        token, self._activation_token = self._activation_token, None
        self.app.show_window(token)

    def _on_menu(self, key: str) -> None:
        c = self.controller
        kind, _, value = key.partition(":")
        if key == "playback":
            c.toggle()
        elif kind == "station":
            c.select(int(value), switched=True)   # the desktop shows the station change, like Windows
        elif key == "volume:up":
            c.set_volume(c.volume + VOLUME_STEP)
        elif key == "volume:down":
            c.set_volume(c.volume - VOLUME_STEP)
        elif kind == "volume":
            c.set_volume(int(value))
        elif key == "sleep:off":
            c.set_sleep_timer(None)
        elif kind == "sleep":
            c.set_sleep_timer(int(value))
        elif key == "now:track":
            self._copy_track()
        elif key in ("settings", "quit", "update"):
            self._action(key)

    def _copy_track(self) -> None:
        """The panel copies the song: on Wayland only the focused app can set the clipboard, and a click in
        the desktop's tray menu leaves the focus with the desktop. Without the focus on Wayland, the panel
        asks for its Copy button instead of claiming it copied."""
        self._show_panel()
        window = self.app.window
        if window is not None:
            _when_focused(window, window.copy_track,
                          window.ask_to_copy if _on_wayland(window) else window.copy_track)

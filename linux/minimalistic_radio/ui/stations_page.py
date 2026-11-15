"""The stations page: a boxed list of stations (logo, name, playing mark, a ⋯ menu), with drag to reorder.

Drag to reorder follows docs/superpowers/specs/2026-11-14-drag-to-reorder-design.md. A row lifts when it is
held for 250 ms or moved past the drag threshold. A floating copy of it follows the pointer while the row
itself stays in the list, invisible, so its gesture keeps the pointer. The other rows slide apart (a CSS
transform per row, animated with Adw.TimedAnimation) to open a gap where it would land.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Graphene", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, Graphene, Gtk  # noqa: E402

from .. import APP_NAME  # noqa: E402
from ..controller import Change, RadioController  # noqa: E402
from ..core.models import Station  # noqa: E402
from .logos import LogoCache, Texture  # noqa: E402
from .reorder import HOLD_MS, SLIDE_MS, drop_index, gap_offsets, scroll_step  # noqa: E402

if TYPE_CHECKING:
    from .window import RadioWindow

LOGO_SIZE = 40
FALLBACK_ICON = "audio-x-generic-symbolic"
SCROLL_TICK_MS = 16
UP_KEYS = (Gdk.KEY_Up, Gdk.KEY_KP_Up)
DOWN_KEYS = (Gdk.KEY_Down, Gdk.KEY_KP_Down)
PLAY_KEYS = (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_ISO_Enter, Gdk.KEY_space, Gdk.KEY_KP_Space)
MODIFIERS = (Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
             | Gdk.ModifierType.SUPER_MASK)


def _point(x: float, y: float) -> Graphene.Point:
    return Graphene.Point().init(x, y)


class StationRow(Adw.ActionRow):
    """One station. Rows stay at their place in the list; a change of the list changes what they show."""

    def __init__(self, page: StationsPage, _: Callable[[str], str]) -> None:
        # The list's own activation ("row-activated") isn't used: the drag gesture below tells a click
        # (plays the station) from a hold or a drag, and the row's key handler plays on Enter.
        super().__init__(use_markup=False, title_lines=1)
        self.index = -1
        self.logo_url: str | None = None
        self._logo: Texture | None = None
        self._logo_drawn = False

        self.logo = Gtk.Image(css_classes=["station-logo"], overflow=Gtk.Overflow.HIDDEN, valign=Gtk.Align.CENTER)
        self.logo.set_size_request(LOGO_SIZE, LOGO_SIZE)
        self.add_prefix(self.logo)
        self.playing_icon = Gtk.Image(icon_name="media-playback-start-symbolic", visible=False,
                                      css_classes=["accent"])
        self.add_suffix(self.playing_icon)
        menu = Gio.Menu()
        menu.append(_("Edit"), "row.edit")
        menu.append(_("Remove"), "row.remove")
        self.menu_button = Gtk.MenuButton(icon_name="view-more-symbolic", menu_model=menu,
                                          tooltip_text=_("Station options"), valign=Gtk.Align.CENTER,
                                          css_classes=["flat"])
        self.add_suffix(self.menu_button)
        actions = Gio.SimpleActionGroup()
        for name, handler in (("edit", page.edit), ("remove", page.remove)):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _action, _param, handler=handler: handler(self.index))
            actions.add_action(action)
        self.insert_action_group("row", actions)

        self.drag = Gtk.GestureDrag()
        self.drag.connect("drag-begin", page._drag_begin, self)
        self.drag.connect("drag-update", page._drag_update, self)
        self.drag.connect("drag-end", page._drag_end, self)
        self.drag.connect("cancel", page._drag_cancelled, self)
        self.add_controller(self.drag)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", page._row_key, self)
        self.add_controller(keys)

    def set_station(self, index: int, station: Station) -> None:
        self.index = index
        if self.get_title() != station.name:
            self.set_title(station.name)

    def set_logo(self, texture: Texture | None) -> None:
        if self._logo_drawn and texture is self._logo:
            return   # the same picture: drawing it again could flicker
        self._logo, self._logo_drawn = texture, True
        if texture is not None:
            self.logo.set_from_paintable(texture)
            self.logo.set_pixel_size(LOGO_SIZE)
        else:
            self.logo.set_from_icon_name(FALLBACK_ICON)
            self.logo.set_pixel_size(24)


@dataclass
class _Drag:
    row: StationRow
    gesture: Gtk.GestureDrag
    origin: int
    start_x: float
    start_y: float
    hold: int = 0                 # the hold timer
    moved: bool = False           # moved past the drag threshold: not a click any more
    lifted: bool = False
    dy: float = 0.0               # the pointer's offset at the last motion event, in the list
    scroll_at: float = 0.0        # where the list was scrolled at that event
    view_y: float = 0.0           # the pointer in the visible part of the list
    speed: float = 0.0            # auto-scroll, px per tick
    left: float = 0.0
    top: float = 0.0              # the floating copy's top, in the list
    height: float = 0.0
    list_height: float = 0.0
    tops: list[float] = field(default_factory=list)       # the rows' tops before the drag
    centers: list[float] = field(default_factory=list)    # and their centres
    target: int = 0
    picture: Gtk.Picture | None = None


class StationsPage(Adw.NavigationPage):
    def __init__(self, window: RadioWindow, controller: RadioController, logos: LogoCache,
                 _: Callable[[str], str]) -> None:
        super().__init__(title=APP_NAME, tag="stations")
        self.window = window
        self.controller = controller
        self.logos = logos
        self._ = _
        self.rows: list[StationRow] = []
        self._drag: _Drag | None = None
        self._returning: _Drag | None = None     # cancelled, sliding back to its place
        self._scroll_timer = 0
        self._offsets: list[float] = []
        self._slide_from: list[float] = []
        self._slide_to: list[float] = []
        self._top_from = self._top_to = 0.0
        # Each row has a class of its own; this stylesheet moves them while a drag is on.
        self._slot = f"mr-slot-{id(self):x}-"
        self._slots_css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self._slots_css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.header = Adw.HeaderBar()
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, valign=Gtk.Align.START,
                                   css_classes=["boxed-list"])
        self._float = Gtk.Fixed(can_target=False)
        self.overlay = Gtk.Overlay(child=self.listbox, valign=Gtk.Align.START,
                                   margin_start=12, margin_end=12, margin_top=6, margin_bottom=12)
        self.overlay.add_overlay(self._float)
        self.scrolled = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, child=self.overlay)

        self.empty = Adw.StatusPage(title=_("No stations yet"), icon_name=FALLBACK_ICON, vexpand=True)
        add = Gtk.Button(label=_("Add a station"), halign=Gtk.Align.CENTER, css_classes=["pill", "suggested-action"])
        add.connect("clicked", lambda _button: window.show_page("search"))
        self.empty.set_child(add)

        self.stack = Gtk.Stack()
        self.stack.add_named(self.scrolled, "list")
        self.stack.add_named(self.empty, "empty")
        self.toolbar = Adw.ToolbarView(content=self.stack)
        self.toolbar.add_top_bar(self.header)
        self.set_child(self.toolbar)

        self._animation = Adw.TimedAnimation.new(self.listbox, 0, 1, SLIDE_MS,
                                                 Adw.CallbackAnimationTarget.new(self._animate))
        self._animation.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        self._animation.connect("done", self._animation_done)

    def release(self) -> None:
        """Called when the window is destroyed: no timer may fire on it afterwards."""
        self._abort()
        Gtk.StyleContext.remove_provider_for_display(Gdk.Display.get_default(), self._slots_css)

    # ---- From the controller ----

    def refresh(self, change: Change) -> None:
        if change & Change.STATIONS:
            self._abort()   # the list changed under a drag (e.g. removed from the tray): drop the drag
            self.sync()
        elif change & Change.STATE:
            self.mark()

    def sync(self) -> None:
        stations = self.controller.stations
        while len(self.rows) > len(stations):
            self.listbox.remove(self.rows.pop())
        while len(self.rows) < len(stations):
            row = StationRow(self, self._)
            row.add_css_class(f"{self._slot}{len(self.rows)}")
            self.rows.append(row)
            self.listbox.append(row)
        for index, (row, station) in enumerate(zip(self.rows, stations)):
            row.set_station(index, station)
            self._show_logo(row, station.logo)
        self.stack.set_visible_child_name("list" if stations else "empty")
        self.mark()

    def mark(self) -> None:
        c = self.controller
        for index, row in enumerate(self.rows):
            current = index == c.current
            playing = current and c.active
            for name, on in (("current", current), ("playing", playing)):
                if on:
                    row.add_css_class(name)
                else:
                    row.remove_css_class(name)
            row.playing_icon.set_visible(playing)

    def _show_logo(self, row: StationRow, url: str | None) -> None:
        known, texture = self.logos.lookup(url)
        row.logo_url = url
        row.set_logo(texture)
        if not known:
            def arrived(texture: Texture | None, row: StationRow = row, url: str | None = url) -> None:
                if row.logo_url == url:
                    row.set_logo(texture)
            self.logos.load(url, arrived)

    # ---- Row actions ----

    def play(self, index: int) -> None:
        self.controller.select(index)
        self.controller.play()

    def edit(self, index: int) -> None:
        self.window.edit_station(index)

    def remove(self, index: int) -> None:
        self.controller.remove_station(index)

    def _row_key(self, _keys: Gtk.EventControllerKey, keyval: int, _keycode: int,
                 state: Gdk.ModifierType, row: StationRow) -> bool:
        modifiers = state & MODIFIERS
        if modifiers == Gdk.ModifierType.ALT_MASK and keyval in UP_KEYS + DOWN_KEYS:
            # Alt+↑ / Alt+↓ move the station one place; focus stays on it.
            if self._drag is not None:
                return True
            delta = -1 if keyval in UP_KEYS else 1
            target = row.index + delta
            if 0 <= target < len(self.rows):
                self.controller.move_station(row.index, delta)
                self.rows[target].grab_focus()
            return True
        if not modifiers and keyval in PLAY_KEYS:
            self.play(row.index)
            return True
        return False

    # ---- Drag to reorder ----

    @property
    def lifted(self) -> bool:
        return self._drag is not None and self._drag.lifted

    def _threshold(self) -> float:
        return self.get_settings().get_property("gtk-dnd-drag-threshold")

    def _drag_begin(self, gesture: Gtk.GestureDrag, x: float, y: float, row: StationRow) -> None:
        picked = row.pick(x, y, Gtk.PickFlags.DEFAULT)
        if picked is not None and (picked is row.menu_button or picked.is_ancestor(row.menu_button)):
            gesture.set_state(Gtk.EventSequenceState.DENIED)   # the ⋯ menu never starts a drag
            return
        self._abort()   # one still sliding back lands at once
        drag = _Drag(row, gesture, row.index, x, y)
        if len(self.rows) > 1:   # one station or none: nothing to drag
            drag.hold = GLib.timeout_add(HOLD_MS, self._held, drag)
        self._drag = drag
        row.grab_focus()

    def _held(self, drag: _Drag) -> bool:
        drag.hold = 0
        if self._drag is drag and not drag.lifted:
            self._lift(drag)
        return GLib.SOURCE_REMOVE

    def _drag_update(self, _gesture: Gtk.GestureDrag, dx: float, dy: float, row: StationRow) -> None:
        drag = self._drag
        if drag is None or drag.row is not row:
            return
        if not drag.lifted:
            if math.hypot(dx, dy) <= self._threshold():
                return
            drag.moved = True
            if len(self.rows) < 2:
                self._cancel_hold(drag)
                return
            self._lift(drag)
        drag.dy = dy
        drag.scroll_at = self.scrolled.get_vadjustment().get_value()
        ok, point = row.compute_point(self.scrolled, _point(drag.start_x + dx, drag.start_y + dy))
        if ok:
            drag.view_y = point.y
        self._follow(drag, dy)
        drag.speed = scroll_step(drag.view_y, self.scrolled.get_height())
        if drag.speed and not self._scroll_timer:
            self._scroll_timer = GLib.timeout_add(SCROLL_TICK_MS, self._scroll_tick)

    def _drag_end(self, _gesture: Gtk.GestureDrag, dx: float, dy: float, row: StationRow) -> None:
        drag = self._drag
        if drag is None or drag.row is not row:
            return   # e.g. the button coming up after Escape
        self._drag = None
        self._stop_scrolling()
        self._cancel_hold(drag)
        if not drag.lifted:
            if not drag.moved and math.hypot(dx, dy) <= self._threshold():
                self.play(drag.origin)   # a click
            return
        if not self._inside(drag, dx, dy):
            self._return(drag)   # released outside the list
            return
        target = drop_index(drag.centers, drag.origin, drag.tops[drag.origin] + dy + drag.height / 2)
        self._put_down(drag)
        if target != drag.origin:
            self.controller.move_station(drag.origin, target - drag.origin)
            self.rows[target].grab_focus()

    def _drag_cancelled(self, _gesture: Gtk.GestureDrag, _sequence: Gdk.EventSequence | None,
                        row: StationRow) -> None:
        """The pointer was taken away (a grab, the window hidden…)."""
        drag = self._drag
        if drag is None or drag.row is not row:
            return
        self._drag = None
        self._stop_scrolling()
        self._cancel_hold(drag)
        if drag.lifted:
            self._return(drag)

    def cancel_drag(self) -> bool:
        """Escape while a station is lifted: it goes back to its place and nothing is saved."""
        drag = self._drag
        if drag is None or not drag.lifted:
            return False
        self._drag = None
        self._stop_scrolling()
        self._return(drag)
        return True

    @staticmethod
    def _cancel_hold(drag: _Drag) -> None:
        if drag.hold:
            GLib.source_remove(drag.hold)
            drag.hold = 0

    def _lift(self, drag: _Drag) -> None:
        self._cancel_hold(drag)
        row = drag.row
        drag.gesture.set_state(Gtk.EventSequenceState.CLAIMED)   # the press is a drag now, not a click
        bounds = []
        for each in self.rows:
            ok, rect = each.compute_bounds(self.listbox)
            bounds.append(rect if ok else Graphene.Rect().init(0, 0, 0, 0))
        drag.tops = [rect.get_y() for rect in bounds]
        drag.centers = [rect.get_y() + rect.get_height() / 2 for rect in bounds]
        own = bounds[drag.origin]
        drag.left, drag.top, drag.height = own.get_x(), own.get_y(), own.get_height()
        drag.list_height = self.listbox.get_height()
        drag.target = drag.origin
        self._offsets = [0.0] * len(self.rows)

        picture = Gtk.Picture(paintable=self._image_of(row, own), can_target=False,
                              overflow=Gtk.Overflow.HIDDEN, css_classes=["drag-lift"])
        picture.set_size_request(round(own.get_width()), round(drag.height))
        self._float.put(picture, drag.left, drag.top)
        drag.picture = picture
        drag.lifted = True
        row.add_css_class("dragging")
        row.set_opacity(0)   # the floating copy stands in for it
        row.set_cursor_from_name("grabbing")

    def _image_of(self, row: StationRow, bounds: Graphene.Rect) -> Gdk.Paintable:
        """A still picture of the row as it looks now. Drawn here: the last frame may not have drawn it
        since it last changed (the press focuses it), so Gtk.WidgetPaintable could still be empty."""
        snapshot = Gtk.Snapshot()
        snapshot.translate(_point(-bounds.get_x(), -bounds.get_y()))
        self.listbox.snapshot_child(row, snapshot)
        return snapshot.to_paintable(Graphene.Size().init(bounds.get_width(), bounds.get_height()))

    def _follow(self, drag: _Drag, dy: float) -> None:
        """Moves the floating copy with the pointer (within the list) and the gap with it."""
        free_top = drag.tops[drag.origin] + dy
        drag.top = min(max(free_top, 0.0), max(0.0, drag.list_height - drag.height))
        self._float.move(drag.picture, drag.left, drag.top)
        target = drop_index(drag.centers, drag.origin, free_top + drag.height / 2)
        if target != drag.target:
            drag.target = target
            self._slide(gap_offsets(len(self.rows), drag.origin, target, drag.height), None)

    def _inside(self, drag: _Drag, dx: float, dy: float) -> bool:
        ok, point = drag.row.compute_point(self.scrolled, _point(drag.start_x + dx, drag.start_y + dy))
        return ok and 0 <= point.x <= self.scrolled.get_width() and 0 <= point.y <= self.scrolled.get_height()

    def _scroll_tick(self) -> bool:
        """Near the top or bottom edge, the list scrolls by itself (faster closer to the edge)."""
        drag = self._drag
        if drag is None or not drag.lifted or not drag.speed:
            self._scroll_timer = 0
            return GLib.SOURCE_REMOVE
        adjustment = self.scrolled.get_vadjustment()
        old = adjustment.get_value()
        lowest = adjustment.get_lower()
        new = min(max(old + drag.speed, lowest), max(lowest, adjustment.get_upper() - adjustment.get_page_size()))
        if new == old:
            self._scroll_timer = 0
            return GLib.SOURCE_REMOVE
        adjustment.set_value(new)
        self._follow(drag, drag.dy + new - drag.scroll_at)   # the pointer stays, the list moves under it
        return GLib.SOURCE_CONTINUE

    def _stop_scrolling(self) -> None:
        if self._scroll_timer:
            GLib.source_remove(self._scroll_timer)
            self._scroll_timer = 0

    def _slide(self, offsets: list[float], returning: _Drag | None) -> None:
        """Animates the rows (and a returning copy) to `offsets`; jumps when animations are off."""
        self._slide_from = list(self._offsets) or [0.0] * len(offsets)
        self._slide_to = offsets
        if returning is not None:
            self._top_from, self._top_to = returning.top, returning.tops[returning.origin]
        self._animation.play()

    def _animate(self, value: float) -> None:
        if not self._slide_to:
            return
        self._offsets = [a + (b - a) * value for a, b in zip(self._slide_from, self._slide_to)]
        rules = [f".{self._slot}{index} {{ transform: translateY({offset:.2f}px); }}"
                 for index, offset in enumerate(self._offsets) if abs(offset) >= 0.01]
        self._slots_css.load_from_string("\n".join(rules))
        drag = self._returning
        if drag is not None and drag.picture is not None:
            drag.top = self._top_from + (self._top_to - self._top_from) * value
            self._float.move(drag.picture, drag.left, drag.top)

    def _animation_done(self, _animation: Adw.Animation) -> None:
        drag, self._returning = self._returning, None
        if drag is not None:
            self._put_down(drag)

    def _return(self, drag: _Drag) -> None:
        """Back to its place, with animation; nothing is saved."""
        self._returning = drag
        self._slide([0.0] * len(self.rows), drag)

    def _put_down(self, drag: _Drag) -> None:
        """Ends the drag's drawing: the rows back in place, the floating copy gone, the row visible again."""
        self._slide_from, self._slide_to = [], []
        if self._animation.get_state() == Adw.AnimationState.PLAYING:
            self._animation.reset()
        self._offsets = []
        self._slots_css.load_from_string("")
        if drag.picture is not None:
            self._float.remove(drag.picture)
            drag.picture = None
        drag.row.set_opacity(1)
        drag.row.remove_css_class("dragging")
        drag.row.set_cursor(None)

    def _abort(self) -> None:
        """Ends any drag at once, without animation."""
        drag, self._drag = self._drag, None
        self._stop_scrolling()
        if drag is not None:
            self._cancel_hold(drag)
            if drag.lifted:
                self._put_down(drag)
        returning, self._returning = self._returning, None
        if returning is not None:
            self._put_down(returning)

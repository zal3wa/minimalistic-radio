"""The tray menu (with its dbusmenu properties) and the MPRIS metadata as plain data (no gi), so they are tested
without a desktop."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Hashable, TypeVar

from .. import APP_NAME
from ..controller import RadioController
from ..core.titles import split_track

TRACK_ID = "/io/github/zal3wa/MinimalisticRadio/Track"
TOOLTIP_BODY_MAX = 120
SLEEP_MINUTES = (15, 30, 45, 60, 90)
VOLUME_PRESETS = (0, 25, 50, 75, 100)
# The dbusmenu properties an item can have, with their D-Bus types.
PROPERTY_TYPES = {"type": "s", "label": "s", "enabled": "b", "icon-name": "s", "toggle-type": "s",
                  "toggle-state": "i", "children-display": "s"}

Properties = dict[str, str | int | bool]
Key = TypeVar("Key", bound=Hashable)


@dataclass
class MenuItem:
    id: str
    label: str = ""
    enabled: bool = True
    separator: bool = False
    toggle: str | None = None      # "radio": a choice among siblings, shown with `checked`
    checked: bool = False
    icon: str | None = None        # a symbolic icon name from the system theme
    children: list["MenuItem"] = field(default_factory=list)


def _separator(name: int | str) -> MenuItem:
    return MenuItem(f"sep:{name}", separator=True)


def _shorten(text: str) -> str:
    """At most TOOLTIP_BODY_MAX characters, ending with "…" when cut (a song or a station name can be very long)."""
    return text if len(text) <= TOOLTIP_BODY_MAX else text[:TOOLTIP_BODY_MAX - 1] + "…"


def build_tray_menu(c: RadioController, _: Callable[[str], str], update: str | None) -> list[MenuItem]:
    """The same menu as the Windows tray; `update` is the label of the ready update, if any."""
    volume = c.volume
    items = [
        MenuItem("playback", _("Stop") if c.active else _("Play"),
                 enabled=c.active or bool(c.stations),
                 icon="media-playback-stop-symbolic" if c.active else "media-playback-start-symbolic"),
        MenuItem("stations", _("Station"), icon="audio-input-microphone-symbolic", children=[
            MenuItem(f"station:{i}", s.name, toggle="radio", checked=i == c.current)
            for i, s in enumerate(c.stations)]),
    ]

    levels = [
        MenuItem("volume:up", _("Up 5%"), enabled=volume < 100, icon="list-add-symbolic"),
        MenuItem("volume:down", _("Down 5%"), enabled=volume > 0, icon="list-remove-symbolic"),
        _separator("volume"),
    ]
    levels += [MenuItem(f"volume:{p}", _("Mute") if p == 0 else f"{p}%", toggle="radio", checked=volume == p)
               for p in VOLUME_PRESETS]
    items.append(MenuItem("volume", _("Volume") + f" ({volume}%)", icon="audio-volume-high-symbolic", children=levels))

    sleeping = c.sleep_at is not None
    label = _("Stops at {time}").format(time=f"{c.sleep_at:%H:%M}") if sleeping else _("Sleep timer")
    timer = [MenuItem(f"sleep:{m}", _("{n} min").format(n=m), toggle="radio", checked=c.sleep_minutes == m)
             for m in SLEEP_MINUTES]
    timer.append(MenuItem("sleep:off", _("Off"), toggle="radio", checked=not sleeping))
    items.append(MenuItem("sleep", label, icon="weather-clear-night-symbolic", children=timer))

    items.append(_separator(1))
    name = c.station_name
    if name is not None:
        items.append(MenuItem("now:station", name, enabled=False))
        if c.track:
            items.append(MenuItem("now:track", _shorten(c.track)))   # a click copies it, like Windows
    items.append(_separator(2))
    if update:
        items.append(MenuItem("update", update, icon="software-update-available-symbolic"))
    items.append(MenuItem("settings", _("Settings"), icon="preferences-system-symbolic"))
    items.append(MenuItem("quit", _("Quit"), icon="application-exit-symbolic"))
    return items


def item_properties(item: MenuItem) -> Properties:
    """The item's dbusmenu properties (PROPERTY_TYPES); one at its default value is left out. DBusMenu reads "_" as
    the mark of a keyboard shortcut: doubled, a station or song keeps its "_"."""
    if item.separator:
        return {"type": "separator"}
    props: Properties = {"label": item.label.replace("_", "__")}
    if not item.enabled:
        props["enabled"] = False
    if item.icon:
        props["icon-name"] = item.icon
    if item.toggle:
        props["toggle-type"] = item.toggle
        props["toggle-state"] = 1 if item.checked else 0
    if item.children:
        props["children-display"] = "submenu"
    return props


def property_changes(shown: dict[Key, Properties], now: dict[Key, Properties]
                     ) -> tuple[list[tuple[Key, Properties]], list[tuple[Key, list[str]]]]:
    """ItemsPropertiesUpdated's two lists: for each item in `now` that was shown before (`shown`) with other
    properties, the properties that changed, and those that are gone (back to their default).

    A desktop updates an item it already shows only from these: when the layout changes, Ubuntu's AppIndicator
    extension (GNOME) reads the type of each item and nothing else."""
    updated, removed = [], []
    for key, props in now.items():
        before = shown.get(key)
        if before is None or before == props:
            continue
        changed = {name: value for name, value in props.items() if name not in before or before[name] != value}
        gone = [name for name in before if name not in props]
        if changed:
            updated.append((key, changed))
        if gone:
            removed.append((key, gone))
    return updated, removed


def tooltip(c: RadioController) -> tuple[str, str]:
    name = c.station_name
    title = f"{APP_NAME} · {name}" if name else APP_NAME
    return _shorten(title), _shorten(c.track or "")


def mpris_metadata(c: RadioController) -> dict[str, Any]:
    meta: dict[str, Any] = {"mpris:trackid": TRACK_ID}
    name = c.station_name
    artist, title = split_track(c.track)
    if title:
        meta["xesam:title"] = title
        if artist:
            meta["xesam:artist"] = [artist]
    elif name:
        meta["xesam:title"] = name
    if name:
        meta["xesam:album"] = name
    if c.cover_path is not None:
        meta["mpris:artUrl"] = c.cover_path.as_uri()
    return meta

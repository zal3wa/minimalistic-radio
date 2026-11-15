#!/usr/bin/env python3
"""Checks, on Ubuntu's desktop, that the radio's tray menu follows the radio and that its items work.

The tray menu is drawn by GNOME Shell's AppIndicator extension from the radio's dbusmenu, so only a real shell shows
whether the two agree. GNOME Shell, the extension and the installed radio start as in linux-tray-screenshot.py (the
radio with --demo-track: it plays nothing, Antyradio Hard seems to play at 30 %). Then:

1. the menu is opened and read;
2. the radio is changed outside the menu (volume and station through MPRIS, as the panel or a media key would), and the
   menu, opened again, must show the new volume and station;
3. Stop, Play, a station and a volume are clicked in the open menu with a virtual pointer, as a person clicks; the radio
   must follow (read back through MPRIS), and so must the menu.

    dbus-run-session -- python3 linux-tray-check.py LOG_DIR

XDG_CONFIG_HOME and XDG_RUNTIME_DIR must be set before dbus-run-session. Exits 1 if a check fails.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import traceback
from pathlib import Path

from gi.repository import GLib

_spec = importlib.util.spec_from_file_location("tray_shots", Path(__file__).with_name("linux-tray-screenshot.py"))
shots = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shots)
log, shell, js, call, wait = shots.log, shots.shell, shots.js, shots.call, shots.wait

MPRIS = "org.mpris.MediaPlayer2." + shots.APP_ID
MPRIS_PATH = "/org/mpris/MediaPlayer2"
PLAYER = "org.mpris.MediaPlayer2.Player"
PROPERTIES = "org.freedesktop.DBus.Properties"
OPEN_WAIT = 2.5      # seconds: the extension reads the radio's menu again as it opens

# The menu as data: each item's label, its ornament (the dot of a radio item) and whether it can be clicked.
READ = """const read = m => m._getMenuItems().map(i => {
        const entry = {label: (i.label && i.label.text) || '', ornament: i._ornament ?? null, reactive: !!i.reactive};
        if (i.menu && i.menu !== m && i.menu._getMenuItems) entry.children = read(i.menu);
        return entry; });
    return read(button.menu);"""


def mpris(name: str):
    return call(MPRIS, MPRIS_PATH, PROPERTIES, "Get", GLib.Variant("(ss)", (PLAYER, name)), "(v)")[0]


def set_mpris(name: str, value: GLib.Variant) -> None:
    call(MPRIS, MPRIS_PATH, PROPERTIES, "Set", GLib.Variant("(ssv)", (PLAYER, name, value)), None)


def station_playing() -> str | None:
    return mpris("Metadata").get("xesam:album")


class Check:
    def __init__(self, desktop) -> None:
        self.desktop = desktop
        self.failures: list[str] = []
        self.dot = None      # the ornament of the chosen station

    def expect(self, what: str, ok: bool, seen: object) -> None:
        log(f"  {'PASS' if ok else 'FAIL'}: {what} (seen: {seen})")
        if not ok:
            self.failures.append(what)

    # ---- The menu ----

    def open(self) -> list[dict]:
        self.desktop.alive()
        shell(js("button.menu.open(0); return button.menu.isOpen;"))
        time.sleep(OPEN_WAIT)
        items = shell(js(READ))
        log("  menu:", json.dumps(items, ensure_ascii=False))
        return items

    def close(self) -> None:
        shell(js("button.menu.close(0); return true;"))
        time.sleep(0.5)

    def is_open(self) -> bool:
        return shell(js("return button.menu.isOpen;"))

    def open_submenu(self, label: str) -> None:
        shell(js(f"""const i = button.menu._getMenuItems().find(i => i.label && i.label.text.startsWith({json.dumps(label)}));
            i.menu.open(false); return i.menu.isOpen;"""))
        time.sleep(1)

    def click(self, label: str | None, parent: str | None = None) -> None:
        """A click with a virtual pointer (moved onto the item, pressed, released) on the item with this label, or
        with None on the first item (Play or Stop), whatever it says."""
        menu = (f"button.menu._getMenuItems().find(i => i.label && i.label.text.startsWith({json.dumps(parent)})).menu"
                if parent else "button.menu")
        pick = "items[0]" if label is None else f"items.find(i => i.label && i.label.text === {json.dumps(label)})"
        where = shell(js(f"""const items = {menu}._getMenuItems(); const i = {pick};
            if (!i) return null; return {{...box(i), label: i.label.text, mapped: i.mapped, reactive: i.reactive}};"""))
        log(f"  clicking {label or 'the first item'!r}: {where}")
        if not where:
            raise RuntimeError(f"no menu item {label!r}")
        x, y = where["x"] + where["w"] / 2, where["y"] + where["h"] / 2
        shell(f"""(() => {{
            if (!globalThis._trayCheckPointer) {{
                const context = global.stage.get_context ? global.stage.get_context() : null;
                const backend = context ? context.get_backend() : imports.gi.Clutter.get_default_backend();
                globalThis._trayCheckPointer = backend.get_default_seat().create_virtual_device(0);   // a pointer
            }}
            globalThis._trayCheckPointer.notify_absolute_motion(GLib.get_monotonic_time(), {x}, {y});
            return true; }})()""")
        time.sleep(0.4)
        for state in (1, 0):   # pressed, released (button 1: the primary one)
            shell(f"globalThis._trayCheckPointer.notify_button(GLib.get_monotonic_time(), 1, {state}); true")
            time.sleep(0.15)
        try:
            wait("the menu to close after the click", lambda: not self.is_open(), 5)
        except TimeoutError as error:
            log(f"  note: {error}")
            self.close()

    # ---- The checks ----

    def run(self) -> None:
        items = self.open()
        labels = [i["label"] for i in items]
        stations = next((i["children"] for i in items if i["label"] == "Station"), [])
        ornaments = {s["label"]: s["ornament"] for s in stations}
        self.dot = ornaments.get("Antyradio Hard")
        log(f"  stations' ornaments: {ornaments}")
        self.expect("at the start the menu offers Stop", labels[:1] == ["Stop"], labels[:1])
        self.expect("at the start the menu shows the volume, 30 %", "Volume (30%)" in labels, labels)
        self.expect("at the start the menu shows Antyradio Hard", "Antyradio Hard" in labels, labels)
        self.expect("the chosen station has its own ornament",
                    list(ornaments.values()).count(self.dot) == 1, ornaments)
        self.close()

        log("- The volume and the station changed outside the menu (MPRIS)")
        set_mpris("Volume", GLib.Variant("d", 1.0))
        call(MPRIS, MPRIS_PATH, PLAYER, "Previous", None, None)   # Antyradio Hard -> RMF FM
        wait("the radio to take the new volume and station",
             lambda: mpris("Volume") == 1.0 and station_playing() == "RMF FM", 10)
        time.sleep(1)
        self.check_menu("after the changes outside the menu", volume=100, station="RMF FM", playing=True)

        log("- Stop, clicked in the menu")
        self.open()
        self.click(None)   # it says Stop
        self.expect_radio("the radio stopped", lambda: mpris("PlaybackStatus") == "Stopped")
        self.check_menu("after Stop", volume=100, station="RMF FM", playing=False)

        log("- Play, clicked in the menu")
        self.open()
        self.click(None)   # it should say Play (checked above): clicked whatever it says, to see what a click does
        self.expect_radio("the radio plays again", lambda: mpris("PlaybackStatus") == "Playing")
        self.check_menu("after Play", volume=100, station="RMF FM", playing=True)

        log("- A station, clicked in the menu")
        self.open()
        self.open_submenu("Station")
        self.click("Radio 357", parent="Station")
        self.expect_radio("the radio switched to Radio 357", lambda: station_playing() == "Radio 357")
        self.check_menu("after the station click", volume=100, station="Radio 357", playing=True)

        log("- A volume, clicked in the menu")
        self.open()
        self.open_submenu("Volume")
        self.click("50%", parent="Volume")
        self.expect_radio("the radio's volume is 50 %", lambda: mpris("Volume") == 0.5)
        self.check_menu("after the volume click", volume=50, station="Radio 357", playing=True)

    def expect_radio(self, what: str, done) -> None:
        try:
            wait(what, done, 5)
            ok = True
        except TimeoutError as error:
            log(f"  {error}")
            ok = False
        self.expect(what, ok, {"status": mpris("PlaybackStatus"), "volume": mpris("Volume"),
                               "station": station_playing()})

    def check_menu(self, when: str, volume: int, station: str, playing: bool) -> None:
        items = self.open()
        labels = [i["label"] for i in items]
        stations = next((i["children"] for i in items if i["label"] == "Station"), [])
        marked = [s["label"] for s in stations if s["ornament"] == self.dot]
        levels = next((i["children"] for i in items if i["label"].startswith("Volume")), [])
        level = [v["label"] for v in levels if v["ornament"] == self.dot]
        self.expect(f"{when}: the menu offers {'Stop' if playing else 'Play'}",
                    labels[:1] == ["Stop" if playing else "Play"], labels[:1])
        self.expect(f"{when}: the menu shows the volume, {volume} %", f"Volume ({volume}%)" in labels, labels)
        self.expect(f"{when}: the volume submenu marks {volume}%", level == [f"{volume}%"], level)
        self.expect(f"{when}: the menu shows {station}", station in labels, labels)
        self.expect(f"{when}: the station submenu marks {station}", marked == [station], marked)
        self.close()


def check(display: str, logs: Path) -> list[str]:
    desktop = shots.Desktop(display, "light", logs)
    try:
        desktop.start_shell()
        desktop.start_radio()
        desktop.wait_for_icon()
        desktop.tidy()
        log("  radio:", {"status": mpris("PlaybackStatus"), "volume": mpris("Volume"), "station": station_playing()})
        checker = Check(desktop)
        try:
            checker.run()
        except Exception as error:   # a check that couldn't go on: the desktop worked, so no other display server
            traceback.print_exc(file=sys.stdout)
            checker.failures.append(f"the check stopped: {error}")
        finally:
            try:
                desktop.screenshot(logs / f"check-{display}-last-full.png")
            except Exception:
                pass
        return checker.failures
    finally:
        desktop.stop()


def main() -> int:
    logs = Path(sys.argv[1]).resolve()
    logs.mkdir(parents=True, exist_ok=True)
    shots.prepare_settings("light")
    sound = shots.start_sound(logs)
    failures: list[str] | None = None
    try:
        for display in ("wayland", "x11"):
            log(f"=== on {display} ===")
            try:
                failures = check(display, logs)
                break
            except Exception:
                log(f"the check on {display} couldn't run:")
                traceback.print_exc(file=sys.stdout)
    finally:
        if sound is not None and sound.poll() is None:
            sound.terminate()
            sound.wait(10)
    if failures is None:
        log("The check couldn't run.")
        return 1
    summary = "All checks passed." if not failures else "Failed:\n" + "\n".join(f"- {f}" for f in failures)
    log(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as file:
            file.write("### Tray menu on GNOME Shell\n" + summary + "\n")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

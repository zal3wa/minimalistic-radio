#!/usr/bin/env python3
"""Real pictures of the radio's tray icon and its open menu on Ubuntu's desktop, for the README.

The tray menu is drawn by the desktop (GNOME Shell's AppIndicator extension), so the app's --screenshot can't take
it. Run on Ubuntu 24.04 with GNOME Shell, the AppIndicator extension, the Yaru theme and the installed radio:

    dbus-run-session -- python3 linux-tray-screenshot.py OUT_DIR LOG_DIR

XDG_CONFIG_HOME and XDG_RUNTIME_DIR must be set before dbus-run-session, so the settings service shares them.

For each look (light, dark): GNOME Shell starts headless on a Wayland virtual monitor (or, if that fails, on Xvfb
with X11), the radio starts as at login (--autostart) from a temporary config, with the test-only --demo-track (it
plays nothing and shows a known song). The radio's menu is opened through org.gnome.Shell.Eval, and
org.gnome.Shell.Screenshot takes the picture, cropped to the top-right corner: the clock, the icon and the menu.
Then the same with the radio's window, opened as a left click opens it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib  # noqa: E402

APP_ID = "io.github.zal3wa.minimalistic-radio"
APP_NAME = "Minimalistic Radio"
APPINDICATOR = "ubuntu-appindicators@ubuntu.com"
MODES = Path("/usr/share/gnome-shell/modes")
WIDTH, HEIGHT = 1366, 768
XDISPLAY = ":99"
WAYLAND_SOCKET = "wayland-shot"
MARGIN = 24                     # around the menu (or the window) in the cropped picture
SONG = "Leonard Cohen - Everybody Knows"
STATIONS = [                    # from radio-browser.info
    ("102.7 KIIS FM Los Angeles", "http://stream.revma.ihrhls.com/zc185"),
    ("Radio 357", "https://stream.radio357.pl/"),
    ("RMF FM", "https://rs101-krk.rmfstream.pl/rmf_fm"),
    ("Antyradio Hard", "https://an01.cdn.eurozet.pl/ANTHAR.mp3"),
]
PLAYING = "https://stream.radio357.pl/"
LOOKS = {                       # color-scheme, GTK theme, icon theme: what Ubuntu's Appearance settings set
    "light": ("default", "Yaru", "Yaru"),
    "dark": ("prefer-dark", "Yaru-dark", "Yaru-dark"),
}

BUS = Gio.bus_get_sync(Gio.BusType.SESSION, None)
RUNTIME = Path(os.environ["XDG_RUNTIME_DIR"])
CONFIG = Path(os.environ["XDG_CONFIG_HOME"])

# Clutter boxes, and the radio's PanelMenu.Button: the AppIndicator extension keeps the item in _indicator.
JS_PRELUDE = f"""
const box = a => {{ const [x, y] = a.get_transformed_position(); const [w, h] = a.get_transformed_size();
                   return {{x, y, w, h}}; }};
const button = Object.values(Main.panel.statusArea).find(b => b && b._indicator &&
    (b._indicator.id === '{APP_ID}' || b._indicator.title === '{APP_NAME}'));
const labels = m => m._getMenuItems().map(i => (i.label && i.label.text) || '-');
"""
# Hides the indicator GNOME Shell shows while --unsafe-mode is on; returns the icons left in the system area.
HIDE_UNSAFE_MODE = """(() => {
    const icons = [];
    const walk = actor => { for (const child of actor.get_children()) {
        if (child.icon_name === 'channel-insecure-symbolic') child.visible = false;
        else if (child.icon_name && child.visible) icons.push(child.icon_name);
        walk(child); } };
    walk(Main.panel.statusArea.quickSettings);
    return icons; })()"""
# Removes every notification (and so its banner); returns their titles.
CLEAR_NOTIFICATIONS = """(() => {
    const titles = [];
    for (const source of Main.messageTray.getSources()) {
        for (const n of source.notifications || []) titles.push(n.title);
        source.destroy();
    }
    return titles; })()"""


def log(*parts: object) -> None:
    print(*parts, flush=True)


def js(body: str) -> str:
    return f"(() => {{{JS_PRELUDE}\n{body}\n}})()"


class Died(Exception):
    """A process of the desktop exited."""


def call(name: str, path: str, iface: str, method: str, args: GLib.Variant | None, reply: str | None,
         timeout: int = 15000):
    result = BUS.call_sync(name, path, iface, method, args, GLib.VariantType(reply) if reply else None,
                           Gio.DBusCallFlags.NONE, timeout, None)
    return result.unpack() if result is not None else None


def has_owner(name: str) -> bool:
    return call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "NameHasOwner",
                GLib.Variant("(s)", (name,)), "(b)")[0]


def shell(code: str):
    """org.gnome.Shell.Eval (allowed by --unsafe-mode): the value, from JSON."""
    ok, text = call("org.gnome.Shell", "/org/gnome/Shell", "org.gnome.Shell", "Eval",
                    GLib.Variant("(s)", (code,)), "(bs)")
    if not ok:
        raise RuntimeError(f"Eval failed: {text or '(no message: is unsafe mode on?)'}")
    return json.loads(text) if text else None


def info(code: str):
    """For the log only: what Eval says, or why it couldn't."""
    try:
        return shell(code)
    except (GLib.Error, RuntimeError, ValueError) as error:
        return f"({error})"


def wait(what: str, check, timeout: float, interval: float = 0.5):
    """check()'s first true value. A Died stops the wait at once."""
    deadline = time.monotonic() + timeout
    last: object = None
    while True:
        try:
            value = check()
            if value:
                return value
            last = value
        except (GLib.Error, RuntimeError, ValueError, KeyError) as error:
            last = error
        if time.monotonic() > deadline:
            raise TimeoutError(f"{what}: gave up after {timeout:.0f} s (last: {last!r})")
        time.sleep(interval)


def gsettings(schema: str, key: str, value: str) -> None:
    done = subprocess.run(["gsettings", "set", schema, key, value], capture_output=True, text=True)
    if done.returncode != 0:
        log(f"  gsettings set {schema} {key} {value}: {done.stderr.strip()}")


def prepare_settings(look: str) -> None:
    """Ubuntu's defaults (its ubuntu-settings package, which also changes the network setup, so it isn't installed)
    and the look. Animations are off, so the menu is drawn whole at once."""
    scheme, gtk, icons = LOOKS[look]
    interface = "org.gnome.desktop.interface"
    gsettings(interface, "color-scheme", f"'{scheme}'")
    gsettings(interface, "gtk-theme", f"'{gtk}'")
    gsettings(interface, "icon-theme", f"'{icons}'")
    gsettings(interface, "cursor-theme", "'Yaru'")
    gsettings(interface, "font-name", "'Ubuntu Sans 11'")
    gsettings(interface, "document-font-name", "'Sans 11'")
    gsettings(interface, "monospace-font-name", "'Ubuntu Sans Mono 13'")
    gsettings(interface, "font-antialiasing", "'grayscale'")   # Ubuntu's rgba would tint the edges in a picture
    gsettings(interface, "enable-hot-corners", "false")
    gsettings(interface, "enable-animations", "false")
    gsettings("org.gnome.desktop.background", "picture-uri", "'file:///usr/share/backgrounds/warty-final-ubuntu.png'")
    gsettings("org.gnome.desktop.background", "picture-uri-dark", "'file:///usr/share/backgrounds/ubuntu-wallpaper-d.png'")
    gsettings("org.gnome.desktop.wm.preferences", "button-layout", "':minimize,maximize,close'")
    gsettings("org.gnome.desktop.session", "idle-delay", "uint32 0")
    # Without GDM the shell announces "Screen Lock disabled": no locking, and no banners over the pictures.
    gsettings("org.gnome.desktop.screensaver", "lock-enabled", "false")
    gsettings("org.gnome.desktop.lockdown", "disable-lock-screen", "true")
    gsettings("org.gnome.desktop.notifications", "show-banners", "false")
    gsettings("org.gnome.shell", "welcome-dialog-last-shown-version", "'999'")
    gsettings("org.gnome.shell", "enabled-extensions", f"['{APPINDICATOR}']")
    for schema, key in (("org.gnome.desktop.interface", "color-scheme"), ("org.gnome.desktop.interface", "gtk-theme"),
                        ("org.gnome.desktop.interface", "icon-theme"), ("org.gnome.desktop.interface", "font-name"),
                        ("org.gnome.desktop.background", "picture-uri"),
                        ("org.gnome.desktop.background", "picture-uri-dark"), ("org.gnome.shell", "enabled-extensions")):
        value = subprocess.run(["gsettings", "get", schema, key], capture_output=True, text=True).stdout.strip()
        log(f"  {schema} {key} = {value}")


def write_radio_config() -> None:
    """3-4 stations, Radio 357 last played, in English."""
    folder = CONFIG / "minimalistic-radio"
    folder.mkdir(parents=True, exist_ok=True)
    stations = [{"Name": name, "Url": url, "Logo": None} for name, url in STATIONS]
    (folder / "stations.json").write_text(json.dumps(stations, indent=2), encoding="utf-8")
    (folder / "preferences.json").write_text(json.dumps({"LastPlayed": PLAYING, "Language": "en"}), encoding="utf-8")


def crop(source: Path, target: Path, left: float, top: float, right: float, bottom: float) -> None:
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(source))
    left, top = max(0, int(left)), max(0, int(top))
    right, bottom = min(pixbuf.get_width(), int(right)), min(pixbuf.get_height(), int(bottom))
    pixbuf.new_subpixbuf(left, top, right - left, bottom - top).copy().savev(str(target), "png", [], [])
    log(f"  wrote {target} ({right - left}x{bottom - top})")


class Desktop:
    """GNOME Shell (and Xvfb for X11) and the radio, for one look."""

    def __init__(self, display: str, look: str, logs: Path) -> None:
        self.display, self.look, self.logs = display, look, logs
        self.processes: list[tuple[str, subprocess.Popen, object]] = []
        self.width = WIDTH

    # ---- Processes ----

    def _spawn(self, name: str, args: list[str], env: dict[str, str]) -> subprocess.Popen:
        output = open(self.logs / f"{self.look}-{self.display}-{name}.log", "w")
        log(f"  starting {name}: {' '.join(args)}")
        process = subprocess.Popen(args, env=env, stdout=output, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        self.processes.append((name, process, output))
        return process

    def alive(self) -> bool:
        for name, process, _output in self.processes:
            if process.poll() is not None:
                raise Died(f"{name} exited with {process.returncode} (see {self.look}-{self.display}-{name}.log)")
        return True

    def stop(self) -> None:
        for name, process, output in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            output.close()
        self.processes.clear()

    # ---- The shell ----

    def start_shell(self) -> None:
        env = dict(os.environ)
        mode = "ubuntu" if (MODES / "ubuntu.json").is_file() else "user"
        args = ["gnome-shell", "--unsafe-mode", f"--mode={mode}"]
        if self.display == "wayland":
            env.pop("DISPLAY", None)
            env.pop("WAYLAND_DISPLAY", None)
            env["XDG_SESSION_TYPE"] = "wayland"
            args += ["--headless", "--virtual-monitor", f"{WIDTH}x{HEIGHT}", "--wayland-display", WAYLAND_SOCKET]
        else:
            self._spawn("xvfb", ["Xvfb", XDISPLAY, "-screen", "0", f"{WIDTH}x{HEIGHT}x24", "-nolisten", "tcp",
                                 "+extension", "GLX"], env)
            wait("Xvfb", lambda: self.alive() and Path("/tmp/.X11-unix/X" + XDISPLAY[1:]).exists(), 30)
            env.pop("WAYLAND_DISPLAY", None)
            env["DISPLAY"] = XDISPLAY
            env["XDG_SESSION_TYPE"] = "x11"
            args += ["--x11", "--replace"]
        self._spawn("gnome-shell", args, env)
        wait("GNOME Shell on the session bus", lambda: self.alive() and has_owner("org.gnome.Shell"), 120)
        wait("GNOME Shell to finish starting", lambda: self.alive() and shell("!Main.layoutManager._startingUp"), 90)
        shell("Main.overview.hide(); true")
        self.width = shell("global.stage.width")
        log("  shell:", info("""({mode: Main.sessionMode.currentMode, stage: [global.stage.width, global.stage.height],
            panel: Main.panel.height, status: Object.keys(Main.panel.statusArea), overview: Main.overview.visible})"""))
        log("  stylesheet:", info("Main.getThemeStylesheet()?.get_path() ?? 'the default'"))
        extension = shell(f"""(() => {{ const e = Main.extensionManager.lookup('{APPINDICATOR}');
            return e ? {{state: e.state, error: e.error ? String(e.error) : null, path: e.path}} : null; }})()""")
        log(f"  AppIndicator extension: {extension}")
        if extension is None:
            raise RuntimeError("the AppIndicator extension isn't installed")
        if extension["state"] != 1:
            log("  enabling it: ", shell(f"Main.extensionManager.enableExtension('{APPINDICATOR}')"))
        wait("the AppIndicator extension's StatusNotifierWatcher",
             lambda: self.alive() and has_owner("org.kde.StatusNotifierWatcher"), 30)

    def tidy(self) -> None:
        """The warning icon of --unsafe-mode and the shell's own notices belong to this way of taking the pictures,
        not to the desktop. (Done late: the shell adds its system icons a moment after it starts.)"""
        log("  unsafe-mode icon hidden; system icons left:", info(HIDE_UNSAFE_MODE))
        log("  notifications cleared:", info(CLEAR_NOTIFICATIONS))
        time.sleep(0.5)   # a frame or two, so the next picture has them gone

    def screenshot(self, path: Path) -> Path:
        ok, used = call("org.gnome.Shell.Screenshot", "/org/gnome/Shell/Screenshot", "org.gnome.Shell.Screenshot",
                        "Screenshot", GLib.Variant("(bbs)", (False, False, str(path))), "(bs)", 30000)
        if not ok:
            raise RuntimeError(f"the screenshot of {path} failed")
        return Path(used)

    # ---- The radio ----

    def start_radio(self) -> None:
        write_radio_config()
        # No settings portal here: libadwaita reads light or dark from GSettings (what the portal would pass on).
        env = dict(os.environ, GTK_A11Y="none", ADW_DISABLE_PORTAL="1")
        if self.display == "wayland":
            env.pop("DISPLAY", None)
            env.update(GDK_BACKEND="wayland", WAYLAND_DISPLAY=WAYLAND_SOCKET)
        else:
            env.pop("WAYLAND_DISPLAY", None)
            env.update(GDK_BACKEND="x11", DISPLAY=XDISPLAY)
        self._spawn("radio", ["minimalistic-radio", "--autostart", "--demo-track", SONG], env)

    def wait_for_icon(self) -> dict:
        state = js("""if (!button) return {found: false, status: Object.keys(Main.panel.statusArea)};
            return {found: true, ...box(button), mapped: button.mapped, items: labels(button.menu),
                    ready: button._indicator.isReady, icon: !!(button._icon && button._icon.gicon)};""")
        seen: dict = {}

        def shown():
            self.alive()
            seen.update(shell(state))
            # Before its first layout the button has no size yet (NaN, null in JSON).
            return seen if seen.get("found") and seen["mapped"] and (seen["w"] or 0) > 0 and seen["items"] else None

        try:
            wait("the radio's icon in the top bar", shown, 60)
        finally:
            log(f"  icon: {seen}")
        try:
            wait("the song in the menu", lambda: SONG in shell(state)["items"], 30)
        except TimeoutError as error:
            log(f"  WARNING: {error}")
        try:
            wait("the icon's picture", lambda: shell(state)["icon"], 10)
        except TimeoutError as error:
            log(f"  note: {error}")
        time.sleep(1)
        return seen

    def shoot_menu(self, out: Path) -> None:
        self.tidy()
        opened = shell(js("button.menu.open(0); return button.menu.isOpen;"))
        log(f"  menu open: {opened}")
        time.sleep(2.5)   # the extension asks the radio for the newest layout as the menu opens
        where = shell(js("""return {open: button.menu.isOpen, menu: box(button.menu.actor),
            clock: box(Main.panel.statusArea.dateMenu), items: labels(button.menu)};"""))
        log(f"  menu: {where}")
        if not where["open"]:
            raise RuntimeError("the menu closed again")
        full = self.screenshot(self.logs / f"{self.look}-{self.display}-menu-full.png")
        menu, clock = where["menu"], where["clock"]
        crop(full, out / f"linux-tray-menu-{self.look}.png",
             min(menu["x"], clock["x"]) - MARGIN, 0, self.width, menu["y"] + menu["h"] + MARGIN)
        shell(js("button.menu.close(0); return true;"))

    def shoot_panel(self, out: Path) -> None:
        """A left click: the item's Activate, as the AppIndicator extension sends it."""
        owner = call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "GetNameOwner",
                     GLib.Variant("(s)", (APP_ID,)), "(s)")[0]
        call(owner, "/StatusNotifierItem", "org.kde.StatusNotifierItem", "Activate", GLib.Variant("(ii)", (0, 0)), None)
        windows = js(f"""const wins = global.get_window_actors().map(a => a.meta_window)
                .filter(w => w.get_gtk_application_id() === '{APP_ID}' || w.get_wm_class() === '{APP_ID}');
            if (!wins.length) return null;
            const r = wins[0].get_frame_rect();
            return {{x: r.x, y: r.y, w: r.width, h: r.height, title: wins[0].get_title(),
                     clock: box(Main.panel.statusArea.dateMenu)}};""")
        window = wait("the radio's window", lambda: self.alive() and shell(windows), 30)
        time.sleep(2.5)
        window = shell(windows)
        log(f"  window: {window}")
        self.tidy()
        full = self.screenshot(self.logs / f"{self.look}-{self.display}-panel-full.png")
        crop(full, out / f"linux-tray-panel-{self.look}.png",
             min(window["x"], window["clock"]["x"]) - MARGIN, 0, self.width, window["y"] + window["h"] + MARGIN)


def take(look: str, display: str, out: Path, logs: Path) -> None:
    desktop = Desktop(display, look, logs)
    try:
        desktop.start_shell()
        desktop.start_radio()
        desktop.wait_for_icon()
        desktop.tidy()
        desktop.screenshot(logs / f"{look}-{display}-icon-full.png")
        desktop.shoot_menu(out)
        try:
            desktop.shoot_panel(out)
        except Exception:   # optional
            log("  the panel picture failed (optional):")
            traceback.print_exc(file=sys.stdout)
    except Exception:
        try:
            if has_owner("org.gnome.Shell.Screenshot"):
                desktop.screenshot(logs / f"{look}-{display}-failed-full.png")
        except Exception:
            pass
        raise
    finally:
        desktop.stop()


def start_sound(logs: Path) -> subprocess.Popen | None:
    """A sound server without a sound card (PulseAudio's null sink), as a desktop has one: the top bar shows its
    volume icon. Optional."""
    try:
        output = open(logs / "pulseaudio.log", "w")
        server = subprocess.Popen(["pulseaudio", "--daemonize=no", "--exit-idle-time=-1", "--log-target=stderr"],
                                  stdout=output, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    except OSError as error:
        log(f"no sound server: {error}")
        return None
    time.sleep(2)
    log("sound server:", "running" if server.poll() is None else f"exited with {server.returncode}")
    return server


def main() -> int:
    out, logs = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    log("session modes:", sorted(p.name for p in MODES.glob("*.json")))
    log("extensions:", sorted(p.name for p in Path("/usr/share/gnome-shell/extensions").glob("*")))
    sound = start_sound(logs)
    try:
        used = take_all(out, logs)
    finally:
        if sound is not None and sound.poll() is None:
            sound.terminate()
            sound.wait(10)
    summary = "\n".join(f"- {look}: {used.get(look, 'FAILED')}" for look in LOOKS)
    log("Display server used:\n" + summary)
    (logs / "summary.txt").write_text(summary + "\n", encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as file:
            file.write("### Tray screenshots\n" + summary + "\n")
    return 0 if len(used) == len(LOOKS) else 1


def take_all(out: Path, logs: Path) -> dict[str, str]:
    """Each look's pictures; returns the display server each look used."""
    displays = ["wayland", "x11"]
    used: dict[str, str] = {}
    for look in LOOKS:
        log(f"=== {look} ===")
        prepare_settings(look)
        for display in displays:
            log(f"--- {look} on {display} ---")
            try:
                take(look, display, out, logs)
            except Exception:
                log(f"{look} on {display} failed:")
                traceback.print_exc(file=sys.stdout)
                continue
            used[look] = display
            displays = [display]   # the next look goes straight to what worked
            break
    return used


if __name__ == "__main__":
    sys.exit(main())

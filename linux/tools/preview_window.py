"""Renders the window to PNG files for review in CI (until Task 15's --screenshot mode replaces it).

Usage: python3 tools/preview_window.py OUTPUT_DIR   (under xvfb-run, from linux/)
Writes stations-, dragging- and empty- pictures, in light and dark.
"""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from minimalistic_radio.controller import RadioController  # noqa: E402
from minimalistic_radio.core.models import Station  # noqa: E402
from minimalistic_radio.core.storage import Paths, save_stations  # noqa: E402
from minimalistic_radio.glib_scheduler import GLibScheduler  # noqa: E402
from minimalistic_radio.ui.window import RadioWindow  # noqa: E402

STATIONS = ["Radio 357", "RMF FM", "Polskie Radio Trójka", "Radio Nowy Świat", "Jazz Radio", "Chillizet"]


class SilentPlayer:
    def play(self, url): pass
    def stop(self): pass
    def set_volume(self, percent): pass


def pump(ms):
    context = GLib.MainContext.default()
    deadline = time.monotonic() + ms / 1000
    while time.monotonic() < deadline:
        context.iteration(False)
        time.sleep(0.005)


def render(window, path):
    paintable = Gtk.WidgetPaintable.new(window)
    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, window.get_width(), window.get_height())
    texture = window.get_renderer().render_texture(snapshot.to_node(), None)
    texture.save_to_png(str(path))
    print("wrote", path)


def window_with(folder, names, playing):
    paths = Paths(folder / "config", folder / "data", folder / "cache")
    save_stations(paths.config / "stations.json",
                  [Station(name, f"http://s{i}.example/live") for i, name in enumerate(names)])
    controller = RadioController(SilentPlayer(), GLibScheduler(), paths, lambda url, cb: None,
                                 lambda url, path, cb: None)
    controller.start(autostart=True)
    if playing:
        controller.select(0)
        controller.play()
        controller.on_player_started()
        controller.on_player_title("Leonard Cohen - Everybody Knows")
    window = RadioWindow(controller)
    window.present()
    pump(600)
    return window


def main(out):
    out.mkdir(parents=True, exist_ok=True)
    Adw.init()
    styles = Adw.StyleManager.get_default()
    with tempfile.TemporaryDirectory() as temp:
        for n, (scheme, look) in enumerate(((Adw.ColorScheme.FORCE_LIGHT, "light"),
                                            (Adw.ColorScheme.FORCE_DARK, "dark"))):
            styles.set_color_scheme(scheme)
            window = window_with(Path(temp) / f"full{n}", STATIONS, playing=True)
            render(window, out / f"stations-{look}.png")
            page = window.stations_page
            row = page.rows[4]
            height = row.get_height()
            page._drag_begin(row.drag, 30, height / 2, row)
            page._drag_update(row.drag, 0, -1.7 * height, row)
            pump(400)
            render(window, out / f"dragging-{look}.png")
            page._drag_end(row.drag, 0, -1.7 * height, row)
            window.destroy()
            window = window_with(Path(temp) / f"empty{n}", [], playing=False)
            render(window, out / f"empty-{look}.png")
            window.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))

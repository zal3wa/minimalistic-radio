"""The application shell, in-process, on the session bus (the CI job runs under dbus-run-session)."""
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gio, GLib  # noqa: E402

from minimalistic_radio import i18n  # noqa: E402
from minimalistic_radio.app import RadioApplication  # noqa: E402
from minimalistic_radio.controller import Status  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]   # linux/


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    for var, folder in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache")):
        monkeypatch.setenv(var, str(tmp_path / folder))


@pytest.fixture
def app_id():
    return "io.github.zal3wa.minimalistic-radio-test" + uuid.uuid4().hex[:8]


def pump(condition, timeout=10.0):
    """Runs the main loop until `condition()` holds."""
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            return False
        context.iteration(False)
        time.sleep(0.01)
    return True


def once_after(ms, fired, name, callback):
    """A one-shot timeout that records in `fired` that it ran; returns its source id."""
    def run():
        fired.add(name)
        callback()
        return GLib.SOURCE_REMOVE
    return GLib.timeout_add(ms, run)


def remove_unfired(fired, sources):
    """Removes the timeouts that never ran, so they can't fire inside a later test's main loop."""
    for name, source_id in sources.items():
        if name not in fired:
            GLib.source_remove(source_id)


def seed_station(tmp_path):
    config = tmp_path / "config" / "minimalistic-radio"
    config.mkdir(parents=True)
    (config / "stations.json").write_text('[{"Name": "Nowhere", "Url": "http://127.0.0.1:9/stream", "Logo": null}]')
    (config / "preferences.json").write_text('{"LastPlayed": "http://127.0.0.1:9/stream"}')


def test_second_launch_opens_panel(app_id):
    first = RadioApplication(application_id=app_id)
    assert first.register()
    second = subprocess.Popen(
        [sys.executable, "-c",
         "import sys; from minimalistic_radio.app import RadioApplication;"
         "sys.exit(RadioApplication(application_id=sys.argv[1]).run(['minimalistic-radio']))", app_id],
        cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)})
    try:
        assert pump(lambda: first.window is not None and first.window.is_visible()), "no window presented"
        assert pump(lambda: second.poll() is not None)
        assert second.returncode == 0
    finally:
        if second.poll() is None:
            second.kill()
        first.quit()
        # It never ran its main loop, so no shutdown: free its D-Bus objects for later tests.
        if first.mpris is not None:
            first.mpris.unpublish()
        if first.tray is not None:
            first.tray.stop()


def test_autostart_stays_hidden(app_id, tmp_path):
    seed_station(tmp_path)
    app = RadioApplication(application_id=app_id)
    fired = set()
    sources = {"quit": once_after(500, fired, "quit", app.quit)}
    try:
        assert app.run(["minimalistic-radio", "--autostart"]) == 0
    finally:
        remove_unfired(fired, sources)
    assert "quit" in fired, "with no window, the app quit at once instead of staying in the background"
    assert app.window is None
    assert app.controller.status in (Status.READY, Status.STOPPED)
    assert app.controller.current == 0   # the last station is chosen, but not played


def test_demo_track_seems_to_play_silently(app_id, tmp_path):
    from minimalistic_radio.selftest import SilentPlayer
    seed_station(tmp_path)
    app = RadioApplication(application_id=app_id)
    fired = set()
    sources = {"quit": once_after(500, fired, "quit", app.quit)}
    try:
        assert app.run(["minimalistic-radio", "--autostart", "--demo-track", "Leonard Cohen - Everybody Knows"]) == 0
    finally:
        remove_unfired(fired, sources)
    assert "quit" in fired
    assert app.window is None
    assert isinstance(app.controller.player, SilentPlayer)
    assert app.controller.status is Status.PLAYING
    assert app.controller.station_name == "Nowhere"
    assert app.controller.track == "Leonard Cohen - Everybody Knows"


def test_normal_launch_shows_the_window_and_plays(app_id, tmp_path):
    seed_station(tmp_path)
    app = RadioApplication(application_id=app_id)
    GLib.timeout_add(500, lambda: (app.quit(), GLib.SOURCE_REMOVE)[1])
    assert app.run(["minimalistic-radio"]) == 0
    assert app.window is not None
    assert app.controller.status is not Status.READY


def test_close_hides_not_quits(app_id):
    app = RadioApplication(application_id=app_id)
    fired, seen = set(), {}

    def check():
        # The window still belongs to the app (a destroyed one would have left the list) and is hidden.
        seen["kept"] = app.window in app.get_windows()
        seen["hidden"] = not app.window.is_visible()
        seen["checked_at"] = time.monotonic()
        # Another process finds this instance on the bus. It runs while this main loop keeps serving.
        seen["probe"] = subprocess.Popen(
            [sys.executable, "-c",
             "import sys; from gi.repository import Gio; a = Gio.Application(application_id=sys.argv[1]);"
             "a.register(); sys.exit(0 if a.get_is_remote() else 3)", app_id],
            env=os.environ)
        GLib.timeout_add(50, finish)

    def finish():
        if seen["probe"].poll() is None and time.monotonic() - seen["checked_at"] < 20:
            return GLib.SOURCE_CONTINUE
        app.quit()
        return GLib.SOURCE_REMOVE

    sources = {"close": once_after(300, fired, "close", lambda: app.window.close()),
               "check": once_after(1500, fired, "check", check)}
    try:
        assert app.run(["minimalistic-radio"]) == 0
    finally:
        remove_unfired(fired, sources)
    assert "close" in fired, "run() returned before the window was closed"
    assert "check" in fired, "run() returned after the window was closed: closing quit the app"
    assert seen["kept"] and seen["hidden"]
    assert seen["probe"].returncode == 0


def test_polish_strings(tmp_path, monkeypatch):
    msgfmt = shutil.which("msgfmt")
    if msgfmt is None:
        pytest.skip("msgfmt is missing")
    target = tmp_path / "locale" / "pl" / "LC_MESSAGES"
    target.mkdir(parents=True)
    subprocess.run([msgfmt, "-o", str(target / "minimalistic-radio.mo"), str(ROOT / "po" / "pl.po")], check=True)
    monkeypatch.delenv("LANGUAGE", raising=False)
    monkeypatch.setattr(i18n, "_translation", i18n._translation)   # English again for the later tests
    _ = i18n.install("pl", str(tmp_path / "locale"))
    assert _("Play") == "Odtwórz"
    assert _("The broadcast has ended") == "Transmisja zakończyła się"

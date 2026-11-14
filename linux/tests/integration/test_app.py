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
    return "io.github.zal3wa.MinimalisticRadioTest" + uuid.uuid4().hex[:8]


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


def test_autostart_stays_hidden(app_id, tmp_path):
    seed_station(tmp_path)
    app = RadioApplication(application_id=app_id)
    GLib.timeout_add(500, lambda: (app.quit(), GLib.SOURCE_REMOVE)[1])
    assert app.run(["minimalistic-radio", "--autostart"]) == 0
    assert app.window is None
    assert app.controller.status in (Status.READY, Status.STOPPED)
    assert app.controller.current == 0   # the last station is chosen, but not played


def test_normal_launch_shows_the_window_and_plays(app_id, tmp_path):
    seed_station(tmp_path)
    app = RadioApplication(application_id=app_id)
    GLib.timeout_add(500, lambda: (app.quit(), GLib.SOURCE_REMOVE)[1])
    assert app.run(["minimalistic-radio"]) == 0
    assert app.window is not None
    assert app.controller.status is not Status.READY


def test_close_hides_not_quits(app_id):
    app = RadioApplication(application_id=app_id)
    assert app.register()
    app.activate()
    assert pump(lambda: app.window is not None and app.window.is_visible())
    app.window.close()
    assert pump(lambda: not app.window.is_visible())
    assert app.get_is_registered()
    # Another instance finds this one on the bus.
    other = Gio.Application(application_id=app_id)
    assert other.register()
    assert other.get_is_remote()
    app.quit()


def test_polish_strings(tmp_path, monkeypatch):
    msgfmt = shutil.which("msgfmt")
    if msgfmt is None:
        pytest.skip("msgfmt is missing")
    target = tmp_path / "locale" / "pl" / "LC_MESSAGES"
    target.mkdir(parents=True)
    subprocess.run([msgfmt, "-o", str(target / "minimalistic-radio.mo"), str(ROOT / "po" / "pl.po")], check=True)
    monkeypatch.delenv("LANGUAGE", raising=False)
    _ = i18n.install("pl", str(tmp_path / "locale"))
    assert _("Play") == "Odtwórz"
    assert _("The broadcast has ended") == "Transmisja zakończyła się"

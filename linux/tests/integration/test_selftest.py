"""--self-test and --screenshot, in-process (Task 15)."""
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from minimalistic_radio import main  # noqa: E402
from minimalistic_radio.app import RadioApplication  # noqa: E402
from minimalistic_radio.selftest import run_self_test, take_screenshots  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]   # linux/


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    for var, folder in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache")):
        monkeypatch.setenv(var, str(tmp_path / folder))


def png_width(path):
    return struct.unpack(">I", path.read_bytes()[16:20])[0]


def test_self_test_passes(tmp_path, monkeypatch, capsys):
    msgfmt = shutil.which("msgfmt")
    if msgfmt is None:
        pytest.skip("msgfmt is missing")
    target = tmp_path / "locale" / "pl" / "LC_MESSAGES"
    target.mkdir(parents=True)
    subprocess.run([msgfmt, "-o", str(target / "minimalistic-radio.mo"), str(ROOT / "po" / "pl.po")], check=True)
    monkeypatch.setattr(main, "LOCALEDIR", str(tmp_path / "locale"))
    monkeypatch.delenv("LANGUAGE", raising=False)
    assert run_self_test(RadioApplication(application_id="io.github.zal3wa.MinimalisticRadioSelfTest")) == 0, \
        capsys.readouterr().err


def test_screenshots_written(tmp_path):
    folder = tmp_path / "shots"
    assert take_screenshots(RadioApplication(application_id="io.github.zal3wa.MinimalisticRadioShots"), folder) == 0
    files = sorted(folder.glob("linux-*.png"))
    assert len(files) == 8
    for file in files:
        assert 300 < png_width(file) <= 380, file.name

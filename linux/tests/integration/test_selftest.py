"""--self-test and --screenshot, in-process (Task 15)."""
import json
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
from minimalistic_radio.core import directory  # noqa: E402
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
    monkeypatch.setattr(main, "PKGDATADIR", str(ROOT / "data"))   # as installed
    monkeypatch.setattr(directory, "_active_bans", directory.NO_BANS)
    main.load_bans()   # what main() does before the application runs
    monkeypatch.delenv("LANGUAGE", raising=False)
    assert run_self_test(RadioApplication(application_id="io.github.zal3wa.minimalistic-radio-selftest")) == 0, \
        capsys.readouterr().err


def test_screenshots_written(tmp_path):
    folder = tmp_path / "shots"
    assert take_screenshots(RadioApplication(application_id="io.github.zal3wa.minimalistic-radio-shots"), folder) == 0
    files = sorted(folder.glob("linux-*.png"))
    # Six pages in light and dark, the settings and statistics scrolled to their end, the Share menu and its toast,
    # and the landing page's four demo frames.
    assert len(files) == 28
    assert {f.name for f in files} >= {"linux-statistics-light.png", "linux-settings-end-dark.png",
                                       "linux-shared-dark.png", "linux-share-menu-light.png",
                                       "linux-share-copied-dark.png", "linux-demo-history-menu-dark.png"}
    widths = {file.name: png_width(file) for file in files}
    assert all(300 < width <= 412 for width in widths.values()), widths   # nothing widens the window

    # Where the demo's pointer clicks: every frame, inside its picture.
    demo = json.loads((folder / "linux-demo-hotspots.json").read_text(encoding="utf-8"))
    width, height = demo["size"]
    assert set(demo["frames"]) == {f"linux-demo-{frame}-{look}.png" for look in ("light", "dark")
                                   for frame in ("stations", "history", "history-menu", "statistics")}
    assert {name: sorted(spots) for name, spots in demo["frames"].items() if name.endswith("-light.png")} == {
        "linux-demo-stations-light.png": ["history"],
        "linux-demo-history-light.png": ["song-menu", "statistics"],
        "linux-demo-history-menu-light.png": ["search-on-spotify"],
        "linux-demo-statistics-light.png": ["back"]}
    for name, spots in demo["frames"].items():
        assert png_width(folder / name) == width
        for x, y in spots.values():
            assert 0 < x < width and 0 < y < height, (name, spots)
    stations = demo["frames"]["linux-demo-stations-light.png"]["history"]
    assert stations[1] < height / 10 and stations[0] < width / 2   # [History] is in the bar, on the left

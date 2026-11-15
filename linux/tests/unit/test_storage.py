import json
from datetime import datetime
from pathlib import Path

import pytest

from minimalistic_radio.core.models import HistoryEntry, Preferences, Station
from minimalistic_radio.core.storage import (
    Paths, default_paths, load_history, load_preferences, load_stations,
    save_history, save_preferences, save_stations,
)


def test_default_paths_follow_xdg(tmp_path):
    p = default_paths({"XDG_CONFIG_HOME": "/c", "XDG_DATA_HOME": "/d", "XDG_CACHE_HOME": "/k", "HOME": "/h"})
    assert p == Paths(Path("/c/minimalistic-radio"), Path("/d/minimalistic-radio"), Path("/k/minimalistic-radio"))
    assert default_paths({"HOME": "/h"}).config == Path("/h/.config/minimalistic-radio")


def test_reads_windows_station_file_with_bom(tmp_path):
    f = tmp_path / "stations.json"
    f.write_bytes('\ufeff[{"Name":"RMF FM","Url":"http://rs6.rmf.pl/rmf_fm","Logo":null},{"Name":"","Url":"http://x.pl/a","Logo":null},{"Name":"Bad","Url":"ftp://x","Logo":null}]'.encode("utf-8"))
    assert load_stations(f) == ([Station("RMF FM", "http://rs6.rmf.pl/rmf_fm", None)], False)


def test_saved_stations_use_windows_shape(tmp_path):
    f = tmp_path / "stations.json"
    save_stations(f, [Station("Radio 357", "https://stream.radio357.pl/", "https://x/l.png")])
    assert json.loads(f.read_text("utf-8")) == [{"Name": "Radio 357", "Url": "https://stream.radio357.pl/", "Logo": "https://x/l.png"}]


def test_corrupt_stations_moved_aside(tmp_path):
    f = tmp_path / "stations.json"
    f.write_text("[{", "utf-8")
    assert load_stations(f) == ([], True)
    assert (tmp_path / "stations.json.bad").read_text("utf-8") == "[{" and not f.exists()


def test_missing_files_give_defaults(tmp_path):
    assert load_stations(tmp_path / "none.json") == ([], False)
    assert load_preferences(tmp_path / "none.json") == Preferences()
    assert load_history(tmp_path / "none.json") == []


def test_preferences_are_clamped_and_validated(tmp_path):
    f = tmp_path / "p.json"
    f.write_text('{"Volume": 150, "Language": "ru", "LastPlayed": "http://a/b", "ShowStationPopup": false}', "utf-8")
    assert load_preferences(f) == Preferences(volume=100, last_played="http://a/b", language="auto", show_station_popup=False)


def test_preferences_round_trip_and_corrupt_fallback(tmp_path):
    f = tmp_path / "p.json"
    prefs = Preferences(volume=55, last_played="http://a/b", language="pl", autostart=True, no_tray_hint_shown=True)
    save_preferences(f, prefs)
    assert load_preferences(f) == prefs
    f.write_text("{oops", "utf-8")
    assert load_preferences(f) == Preferences()
    assert f.exists()


def test_history_round_trip_keeps_100(tmp_path):
    f = tmp_path / "h.json"
    entries = [HistoryEntry(f"Song {i}", "S", datetime(2026, 11, 14, 19, 52)) for i in range(120)]
    save_history(f, entries)
    assert load_history(f) == entries[:100]


def test_save_is_atomic(tmp_path, monkeypatch):
    f = tmp_path / "stations.json"
    save_stations(f, [Station("A", "http://a/1")])
    monkeypatch.setattr(json, "dump", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        save_stations(f, [])
    assert load_stations(f)[0] == [Station("A", "http://a/1")]

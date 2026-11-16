import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import HistoryEntry, ListeningSession, Preferences, SongPlay, Station, Statistics
from .statistics import SONGS_KEPT
from .streams import is_web_url
from .text import clean_name

_DIR = "minimalistic-radio"
_LANGUAGES = ("auto", "pl", "en", "de", "uk", "cs", "es", "fr", "it", "pt")
HISTORY_LIMIT = 100


@dataclass(frozen=True)
class Paths:
    config: Path
    data: Path
    cache: Path


def default_paths(env: Mapping[str, str] = os.environ) -> Paths:
    home = Path(env["HOME"]) if env.get("HOME") else Path.home()

    def pick(var: str, fallback: Path) -> Path:
        value = env.get(var)
        return (Path(value) if value else fallback) / _DIR

    return Paths(
        config=pick("XDG_CONFIG_HOME", home / ".config"),
        data=pick("XDG_DATA_HOME", home / ".local" / "share"),
        cache=pick("XDG_CACHE_HOME", home / ".cache"),
    )


def logo_name(url: str) -> str:
    """A logo's file name in the cache's logos folder: made from its address."""
    return hashlib.sha1(url.encode("utf-8"), usedforsecurity=False).hexdigest()


def _read_json(path: Path):
    """Parsed JSON, None when the file is missing; ValueError when it is corrupt."""
    try:
        with open(path, encoding="utf-8-sig") as file:
            return json.load(file)
    except FileNotFoundError:
        return None
    except UnicodeDecodeError as error:
        raise ValueError(str(error)) from error


def _write_json(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def load_stations(path: Path) -> tuple[list[Station], bool]:
    path = Path(path)
    try:
        data = _read_json(path)
        if data is None:
            return [], False
        if not isinstance(data, list):
            raise ValueError("not a list")
    except ValueError:
        os.replace(path, path.with_name(path.name + ".bad"))
        return [], True
    stations = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name, url, logo = item.get("Name"), item.get("Url"), item.get("Logo")
        name = clean_name(name) if isinstance(name, str) else ""
        if not name or not isinstance(url, str) or not is_web_url(url):
            continue
        stations.append(Station(name, url, logo if isinstance(logo, str) else None))
    return stations, False


def save_stations(path: Path, stations: list[Station]) -> None:
    _write_json(path, [{"Name": s.name, "Url": s.url, "Logo": s.logo} for s in stations])


def load_preferences(path: Path) -> Preferences:
    try:
        data = _read_json(Path(path))
    except ValueError:
        return Preferences()
    if not isinstance(data, dict):
        return Preferences()
    prefs = Preferences()
    volume = data.get("Volume")
    if isinstance(volume, int) and not isinstance(volume, bool):
        prefs.volume = max(0, min(100, volume))
    last = data.get("LastPlayed")
    if isinstance(last, str):
        prefs.last_played = last
    if data.get("Language") in _LANGUAGES:
        prefs.language = data["Language"]
    for key, attr in (("ShowStationPopup", "show_station_popup"), ("Autostart", "autostart"),
                      ("NoTrayHintShown", "no_tray_hint_shown"), ("CollectStatistics", "collect_statistics")):
        if isinstance(data.get(key), bool):
            setattr(prefs, attr, data[key])
    return prefs


def save_preferences(path: Path, prefs: Preferences) -> None:
    _write_json(path, {
        "Volume": prefs.volume,
        "LastPlayed": prefs.last_played,
        "Language": prefs.language,
        "ShowStationPopup": prefs.show_station_popup,
        "Autostart": prefs.autostart,
        "NoTrayHintShown": prefs.no_tray_hint_shown,
        "CollectStatistics": prefs.collect_statistics,
    })


def load_history(path: Path) -> list[HistoryEntry]:
    try:
        data = _read_json(Path(path))
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    entries = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title, station, time = item.get("Title"), item.get("Station"), item.get("Time")
        if not isinstance(title, str) or not isinstance(station, str) or not isinstance(time, str):
            continue
        try:
            entries.append(HistoryEntry(title, station, datetime.fromisoformat(time)))
        except ValueError:
            continue
    return entries[:HISTORY_LIMIT]


def save_history(path: Path, entries: list[HistoryEntry]) -> None:
    _write_json(path, [
        {"Title": e.title, "Station": e.station, "Time": e.time.isoformat(timespec="seconds")}
        for e in entries[:HISTORY_LIMIT]
    ])


def _utc_text(when: datetime) -> str:
    """2026-11-15T19:02:00Z"""
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_time(value) -> datetime | None:
    """An aware time from the file's text (a time without a zone is taken as UTC); None if it isn't one."""
    if not isinstance(value, str):
        return None
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when.astimezone(timezone.utc)


def load_statistics(path: Path) -> Statistics:
    """Empty when the file is missing; ValueError when it is corrupt. Entries that make no sense are skipped."""
    data = _read_json(Path(path))
    if data is None:
        return Statistics()
    if not isinstance(data, dict):
        raise ValueError("not an object")
    stats = Statistics()
    sessions, songs = data.get("sessions"), data.get("songs")
    for item in sessions if isinstance(sessions, list) else []:
        if not isinstance(item, dict):
            continue
        station, url = item.get("station"), item.get("url")
        start, end = _utc_time(item.get("start")), _utc_time(item.get("end"))
        if not isinstance(station, str) or not isinstance(url, str) or start is None or end is None or end < start:
            continue
        stats.sessions.append(ListeningSession(station, url, start, end, item.get("titles") is True))
    for item in songs if isinstance(songs, list) else []:
        if not isinstance(item, dict):
            continue
        station, title, time = item.get("station"), item.get("title"), _utc_time(item.get("time"))
        if isinstance(station, str) and isinstance(title, str) and time is not None:
            stats.songs.append(SongPlay(station, title, time))
    del stats.songs[:-SONGS_KEPT]   # a file from before the limit: its newest plays
    return stats


def save_statistics(path: Path, stats: Statistics) -> None:
    _write_json(path, {
        "version": 1,
        "sessions": [{"station": s.station, "url": s.url, "start": _utc_text(s.start), "end": _utc_text(s.end),
                      "titles": s.titles} for s in stats.sessions],
        "songs": [{"station": s.station, "title": s.title, "time": _utc_text(s.time)} for s in stats.songs],
    })

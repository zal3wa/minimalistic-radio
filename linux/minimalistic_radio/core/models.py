from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Station:
    name: str
    url: str
    logo: str | None = None


@dataclass
class Preferences:
    volume: int = 30
    last_played: str | None = None
    language: str = "auto"
    show_station_popup: bool = True
    autostart: bool = False
    no_tray_hint_shown: bool = False   # "The radio keeps playing", shown the first time the window is closed


@dataclass
class HistoryEntry:
    title: str
    station: str
    time: datetime


@dataclass
class ListeningSession:
    """A stretch of time a station actually played. Times are aware (UTC)."""
    station: str
    url: str
    start: datetime
    end: datetime
    titles: bool = False   # the station sent at least one song title meanwhile


@dataclass
class SongPlay:
    """A song that joined the song history (same filters: no ads, station names or repeats)."""
    station: str
    title: str
    time: datetime


@dataclass
class Statistics:
    """What statistics.json keeps, oldest first."""
    sessions: list[ListeningSession] = field(default_factory=list)
    songs: list[SongPlay] = field(default_factory=list)

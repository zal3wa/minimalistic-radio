from dataclasses import dataclass
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
    no_tray_hint_shown: bool = False


@dataclass
class HistoryEntry:
    title: str
    station: str
    time: datetime

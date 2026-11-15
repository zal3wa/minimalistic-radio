"""Listening statistics: recording what is listened to, and counting it for the Statistics page.

Kept only on this computer, in statistics.json next to the song history (see core/storage.py), and never sent
anywhere. Separate from the song history: clearing one leaves the other.

- A session runs while a station actually plays: from the sound starting to Stop, a station change, the sleep
  timer, an error or quitting. A reconnect to the same station within MERGE_GAP continues it.
- A song is recorded when the song history gets a new entry.
- Periods are in local time; a session that crosses a boundary counts only its part inside the period.

Times are aware datetimes (UTC in the file). `tz` is the local zone; None means the system's.
Texts are translated by the functions passed in (gettext, pgettext, ngettext), so this stays free of GTK.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, tzinfo
from enum import Enum
from typing import Callable

from .models import ListeningSession, SongPlay, Statistics
from .titles import split_track

MERGE_GAP = timedelta(minutes=2)                  # a reconnect within this continues the session
SAVE_SECONDS = 300                                # a running session is saved this often
CLOCK_JUMP = timedelta(seconds=SAVE_SECONDS + 60)   # longer between two updates: the computer slept
TITLES_SHARE = 0.2                                # less of the time with song titles: too few for Top artists
TOP = 5


def _same(text: str) -> str:
    return text


def _same_in(_context: str, text: str) -> str:
    return text


def _plural(singular: str, plural: str, n: int) -> str:
    return singular if n == 1 else plural


# ---- Recording ----

class Recorder:
    """Turns playback into sessions and songs in `stats`. The controller saves the file."""

    def __init__(self, stats: Statistics) -> None:
        self.stats = stats
        self.current: ListeningSession | None = None
        self._asleep = False            # suspend() was called: the session ended there
        self._titles_waiting = False    # a title came while connecting, before the sound started

    def started(self, station: str, url: str, now: datetime) -> None:
        """The sound started."""
        if self.current is not None:
            self.stopped(now)
        last = self.stats.sessions[-1] if self.stats.sessions else None
        if last is not None and last.url == url and timedelta(0) <= now - last.end <= MERGE_GAP:
            last.end = now   # a reconnect: the same session goes on
            self.current = last
        else:
            self.current = ListeningSession(station, url, now, now)
            self.stats.sessions.append(self.current)
        if self._titles_waiting:
            self.current.titles = True
            self._titles_waiting = False

    def alive(self, now: datetime) -> bool:
        """The session went on until `now`. False (and the session has ended at its last update) when the clock
        jumped since that update, forward (the computer slept) or back, or the computer went to sleep."""
        session = self.current
        if session is None:
            return False
        if self._asleep or now < session.end or now - session.end > CLOCK_JUMP:
            self.current = None
            self._asleep = False
            return False
        session.end = now
        return True

    def suspend(self, now: datetime) -> None:
        """The computer is going to sleep: the session ends now, whatever the clock says after waking up."""
        if self.alive(now):
            self._asleep = True

    def stopped(self, now: datetime) -> None:
        """The sound stopped (Stop, another station, the sleep timer, an error, quitting)."""
        self.alive(now)
        self.current = None
        self._asleep = False
        self._titles_waiting = False

    def song(self, station: str, title: str, now: datetime) -> None:
        self.stats.songs.append(SongPlay(station, title, now))
        if self.current is not None:
            self.current.titles = True
        else:
            self._titles_waiting = True

    def clear(self, now: datetime) -> None:
        """Forgets everything; a station that is playing counts again from now."""
        running = self.current
        self.stats.sessions.clear()
        self.stats.songs.clear()
        self.current = None
        self._asleep = False
        if running is not None:
            self.current = ListeningSession(running.station, running.url, now, now)
            self.stats.sessions.append(self.current)


# ---- Counting ----

class Period(Enum):
    ALL = "all"
    YEAR = "year"
    MONTH = "month"


@dataclass
class TopStation:
    name: str      # as last listened to
    url: str
    seconds: float


@dataclass
class Summary:
    period: Period
    since: datetime | None = None      # where the period starts (All: the first session)
    total: float = 0.0                 # seconds
    per_day: float = 0.0
    songs: int = 0                     # song titles received
    stations: int = 0                  # stations listened to
    longest: float = 0.0               # the longest single session
    top_stations: list[TopStation] = field(default_factory=list)
    top_artists: list[tuple[str, int]] = field(default_factory=list)   # (artist, plays)
    titles_share: float = 0.0          # of the listening time, the part with song titles
    hours: list[float] = field(default_factory=lambda: [0.0] * 24)    # seconds in each hour of the day
    peak_hour: int | None = None

    @property
    def empty(self) -> bool:
        return self.total <= 0


def _midnight(year: int, month: int, day: int, tz: tzinfo | None) -> datetime:
    """The local start of that day, aware."""
    if tz is None:
        return datetime(year, month, day).astimezone()   # the system's zone, with that day's offset
    return datetime(year, month, day, tzinfo=tz)


def _bounds(period: Period, today: date, tz: tzinfo | None) -> tuple[datetime | None, datetime | None]:
    if period is Period.MONTH:
        after = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        return _midnight(today.year, today.month, 1, tz), _midnight(*after, 1, tz)
    if period is Period.YEAR:
        return _midnight(today.year, 1, 1, tz), _midnight(today.year + 1, 1, 1, tz)
    return None, None


def artist_of(title: str) -> str | None:
    """The part before the first " - " (or a dash like it); None for a title without one."""
    artist, _song = split_track(title)
    return artist or None


def _add_hours(hours: list[float], start: datetime, end: datetime, tz: tzinfo | None) -> None:
    """Spreads start…end over the local hours of the day, stepping in real time (right across DST changes)."""
    at = start
    while at < end:
        local = at.astimezone(tz)
        into = timedelta(minutes=local.minute, seconds=local.second, microseconds=local.microsecond)
        step = min(timedelta(hours=1) - into, end - at)
        hours[local.hour] += step.total_seconds()
        at += step


def count(stats: Statistics, period: Period, now: datetime, tz: tzinfo | None = None) -> Summary:
    """Everything the Statistics page shows for `period`, as of `now`."""
    today = now.astimezone(tz).date()
    begin, finish = _bounds(period, today, tz)
    finish = now if finish is None else min(finish, now)
    summary = Summary(period)
    if period is Period.ALL:
        if not stats.sessions:
            return summary
        begin = min(s.start for s in stats.sessions)
    summary.since = begin

    by_station: dict[str, list] = {}   # url → [seconds, name, latest start]
    titled = 0.0
    for session in stats.sessions:
        start, end = max(session.start, begin), min(session.end, finish)
        if end <= start:
            continue
        seconds = (end - start).total_seconds()
        summary.total += seconds
        summary.longest = max(summary.longest, seconds)
        if session.titles:
            titled += seconds
        entry = by_station.setdefault(session.url, [0.0, session.station, session.start])
        entry[0] += seconds
        if session.start >= entry[2]:
            entry[1], entry[2] = session.station, session.start
        _add_hours(summary.hours, start, end, tz)
    if summary.empty:
        return Summary(period, since=summary.since)

    if period is Period.MONTH:
        days = today.day
    elif period is Period.YEAR:
        days = today.timetuple().tm_yday
    else:
        days = (today - begin.astimezone(tz).date()).days + 1
    summary.per_day = summary.total / max(1, days)
    summary.stations = len(by_station)
    ranked = sorted(by_station.items(), key=lambda item: (-item[1][0], item[1][1].casefold()))
    summary.top_stations = [TopStation(name, url, seconds) for url, (seconds, name, _start) in ranked[:TOP]]
    summary.titles_share = titled / summary.total

    plays: Counter[str] = Counter()
    spellings: dict[str, Counter[str]] = {}
    for song in stats.songs:
        if not begin <= song.time < finish:
            continue
        summary.songs += 1
        artist = artist_of(song.title)
        if artist is not None:
            key = artist.casefold()
            plays[key] += 1
            spellings.setdefault(key, Counter())[artist] += 1
    top = sorted(plays.items(), key=lambda item: (-item[1], item[0]))[:TOP]
    summary.top_artists = [(spellings[key].most_common(1)[0][0], n) for key, n in top]

    summary.peak_hour = max(range(24), key=lambda hour: (summary.hours[hour], -hour))
    return summary


def enough_titles(summary: Summary) -> bool:
    """Top artists only when stations with song titles make up enough of the listening time."""
    return bool(summary.top_artists) and summary.titles_share >= TITLES_SHARE


# ---- Texts ----

def format_count(n: int) -> str:
    """5 731: thousands apart with a narrow no-break space."""
    return f"{n:,}".replace(",", " ")


def format_duration(seconds: float, _: Callable[[str], str] = _same) -> str:
    """Under an hour "18 min", under 100 hours "42 h 18 min", from 100 hours "386 h"."""
    minutes = int(seconds // 60)
    if minutes < 60:
        return _("{n} min").format(n=minutes)
    hours, rest = divmod(minutes, 60)
    if hours < 100:
        return _("{h} h {min} min").format(h=hours, min=f"{rest:02d}")
    return _("{h} h").format(h=format_count(hours))


def plays_text(n: int, N_: Callable[[str, str, int], str] = _plural) -> str:
    return N_("{n} play", "{n} plays", n).format(n=format_count(n))


def format_hours(hour: int) -> str:
    """20:00–21:00"""
    return f"{hour:02d}:00–{(hour + 1) % 24:02d}:00"


def _month(month: int, C_: Callable[[str, str], str]) -> str:
    """The month's name on its own ("November 2026")."""
    return (C_("month", "January"), C_("month", "February"), C_("month", "March"), C_("month", "April"),
            C_("month", "May"), C_("month", "June"), C_("month", "July"), C_("month", "August"),
            C_("month", "September"), C_("month", "October"), C_("month", "November"),
            C_("month", "December"))[month - 1]


def _month_in_date(month: int, C_: Callable[[str, str], str]) -> str:
    """The month's name in a date ("2 March 2025"): some languages change it there."""
    return (C_("date", "January"), C_("date", "February"), C_("date", "March"), C_("date", "April"),
            C_("date", "May"), C_("date", "June"), C_("date", "July"), C_("date", "August"),
            C_("date", "September"), C_("date", "October"), C_("date", "November"),
            C_("date", "December"))[month - 1]


def period_label(period: Period, today: date, _: Callable[[str], str] = _same,
                 C_: Callable[[str, str], str] = _same_in) -> str:
    """"November 2026" for Month, "2026" for Year (All: since_label)."""
    if period is Period.YEAR:
        return str(today.year)
    text = _("{month} {year}").format(month=_month(today.month, C_), year=today.year)
    return text[:1].upper() + text[1:]


def since_label(first: date, _: Callable[[str], str] = _same, C_: Callable[[str, str], str] = _same_in) -> str:
    """"Since 2 March 2025"."""
    when = _("{day} {month} {year}").format(day=first.day, month=_month_in_date(first.month, C_), year=first.year)
    return _("Since {date}").format(date=when)

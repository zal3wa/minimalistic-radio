"""The radio itself: what plays, reconnecting, the sleep timer, song history, statistics and the station list.

A port of the playback side of src/Radio/RadioApp.cs (and the station edits of RadioPanel.cs).
Everything here runs on one thread, the GLib main loop. It never imports gi: the player, the timers
and the network are handed in, so the tests drive it with fakes.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum, Flag, auto
from pathlib import Path
from typing import Any, Callable, Protocol

from . import APP_NAME
from .core.covers import CoverCache, itunes_search_url, pick_cover
from .core.imagesize import fits
from .core.models import HistoryEntry, Preferences, Station, Statistics
from .core.share import SharedStation
from .core.statistics import SAVE_SECONDS, Recorder
from .core.storage import (
    HISTORY_LIMIT, Paths, load_history, load_preferences, load_statistics, load_stations,
    save_history, save_preferences, save_statistics, save_stations,
)
from .core.streams import is_web_url, same_stream, stream_key
from .core.text import clean_name
from .core.titles import (
    RADIO357_NOW_URL, artwork_from_raw, parse_title, radio357_title, split_track, station_kind,
)

BACKOFF = (2, 3, 5, 10, 15, 30)              # seconds before each retry
RETRIES_ONCE_PLAYED, RETRIES_NEVER_PLAYED = 10, 2
LONG_CONNECTION = timedelta(seconds=60)      # a connection that lasted longer resets the retry count
NETWORK_RETURN_WINDOW = timedelta(minutes=10)
FADE_SECONDS = 30                            # the sleep timer fades out over its last 30 seconds
RADIO357_POLL_SECONDS = 10
TITLE_SECONDS = 5                            # a stream's title changes are applied at most this often
COVERS_KEPT = 200                            # pictures kept in the cover cache
VOLUME_BURST = timedelta(seconds=1)          # volume changes closer than this are one (a drag, the wheel, keys)
SWITCH_SETTLE = 0.3                          # a media key or tray switch connects once switching pauses this long
LANGUAGES = ("auto", "pl", "en", "de", "uk", "cs", "es", "fr", "it", "pt")


class ErrorKind(Enum):
    NETWORK = auto()       # the connection failed or dropped: retried
    REFUSED = auto()       # the station said no: stops at once
    UNSUPPORTED = auto()   # a format the player can't decode: stops at once


class Status(Enum):
    READY = auto()
    CONNECTING = auto()
    PLAYING = auto()
    RETRYING = auto()
    STOPPED = auto()


class Change(Flag):
    STATE = auto()         # status, its message or the chosen station
    STATIONS = auto()
    TRACK = auto()
    COVER = auto()
    HISTORY = auto()
    VOLUME = auto()
    SLEEP = auto()
    PREFERENCES = auto()
    SWITCHED = auto()      # the station was changed by a media key or the tray menu
    MESSAGE = auto()       # a notice for the user (the station list couldn't be saved)
    STATISTICS = auto()    # the listening statistics


class AddResult(Enum):
    ADDED = auto()
    DUPLICATE = auto()
    INVALID = auto()


@dataclass
class ImportResult:
    added: int
    error: str | None


class Player(Protocol):
    """The audio player. The controller has no session token for its callbacks, so it relies on this contract:

    - Once play() or stop() returns, no callback (on_player_started, _title, _error, _eos) for an
      earlier stream may be delivered. With GStreamer, the bus's auto-flush on going to NULL covers bus
      messages, but not anything already queued through GLib.idle_add: those must be dropped too.
    - Callbacks are never delivered synchronously from inside play(), stop() or set_volume().
    - The volume from set_volume() persists across play() calls. The controller never sends it again
      when it connects, so a fresh playbin per play() must get the last volume (or a sleep-timer fade
      would play at 100%).
    """

    def play(self, url: str) -> None: ...
    def stop(self) -> None: ...
    def set_volume(self, percent: int) -> None: ...


class Scheduler(Protocol):
    def call_later(self, seconds: float, cb: Callable[[], None]) -> object: ...
    def cancel(self, handle: object) -> None: ...
    def now(self) -> datetime: ...


Fetch = Callable[[str, Callable[[Any | None], None]], None]          # async JSON: calls back with None on failure
FetchFile = Callable[[str, Path, Callable[[bool], None]], None]      # async download to a file


class RadioController:
    def __init__(self, player: Player, scheduler: Scheduler, paths: Paths, fetch: Fetch,
                 fetch_file: FetchFile, _: Callable[[str], str] = lambda s: s) -> None:
        self.player = player
        self.scheduler = scheduler
        self.paths = paths
        self.fetch = fetch
        self.fetch_file = fetch_file
        self._ = _

        self.stations: list[Station] = []
        self.current = -1
        self.status = Status.READY
        self.message: str | None = None   # the status's own text ("Connection lost…"), None for the usual one
        self.notice: str | None = None    # the last notice, sent with Change.MESSAGE; never a status
        self.track: str | None = None
        self.cover_path: Path | None = None
        self.prefs = Preferences()
        self.volume = self.prefs.volume
        self.sleep_at: datetime | None = None
        self.sleep_minutes: int | None = None
        self.history: list[HistoryEntry] = []
        self.statistics = Statistics()
        self.corrupt_stations = False
        # Set when the retries ran out on NETWORK errors: network_available() starts again within 10 minutes.
        self.gave_up_on_network_at: datetime | None = None

        self._listeners: list[Callable[[Change], None]] = []
        self._pending = Change(0)                  # sent with the next change (statistics updated meanwhile)
        self._covers = CoverCache()
        self._fade = 100
        self._sleep_timer: object | None = None
        # Muting: unmute goes back to the level from before the last burst of changes (see set_volume).
        self._unmute_volume = self._volume_before = Preferences().volume
        self._volume_changed_at: datetime | None = None
        # The playback session: one per play(), until stop() or the next play().
        self._session = 0
        self._url = ""
        self._kind = "generic"
        self._attempt = 0
        self._ever_played = False
        self._attempt_started = datetime.min
        self._retry_timer: object | None = None
        self._poll_timer: object | None = None
        self._switch_timer: object | None = None   # set while a switched station waits to connect
        self._title_timer: object | None = None    # set for TITLE_SECONDS after a title was applied
        self._title_waiting: tuple[str | None] | None = None   # (raw,): the newest title that came meanwhile
        self._polling = False
        # Listening statistics: the sessions and songs go to statistics.json, the running session every 5 minutes.
        self._recorder = Recorder(self.statistics)
        self._statistics_timer: object | None = None
        self._statistics_unsaved = False

    # ---- State ----

    @property
    def station_name(self) -> str | None:
        return self.stations[self.current].name if 0 <= self.current < len(self.stations) else None

    @property
    def effective_volume(self) -> int:
        """What the player gets: the chosen volume, lowered while the sleep timer fades out."""
        return self.volume * self._fade // 100

    @property
    def active(self) -> bool:
        """A station is on (connecting, playing or waiting to retry): the tray offers Stop."""
        return self.status in (Status.CONNECTING, Status.PLAYING, Status.RETRYING)

    def subscribe(self, listener: Callable[[Change], None]) -> None:
        self._listeners.append(listener)

    def unsubscribe(self, listener: Callable[[Change], None]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _emit(self, change: Change) -> None:
        change, self._pending = change | self._pending, Change(0)
        if change:
            for listener in list(self._listeners):
                listener(change)

    # ---- Files ----

    @property
    def _stations_file(self) -> Path:
        return self.paths.config / "stations.json"

    @property
    def _preferences_file(self) -> Path:
        return self.paths.config / "preferences.json"

    @property
    def _history_file(self) -> Path:
        return self.paths.data / "history.json"

    @property
    def _statistics_file(self) -> Path:
        return self.paths.data / "statistics.json"

    def start(self, autostart: bool) -> None:
        """Loads the files and, unless started with the system, plays the last station."""
        try:
            self.stations, self.corrupt_stations = load_stations(self._stations_file)
        except OSError:
            self.stations, self.corrupt_stations = [], False
        try:
            self.prefs = load_preferences(self._preferences_file)
        except OSError:
            self.prefs = Preferences()
        try:
            self.history = load_history(self._history_file)
        except OSError:
            self.history = []
        self.statistics = self._load_statistics()
        self._recorder = Recorder(self.statistics)
        self.volume = self.prefs.volume
        self._prune_covers()
        self.current = next((i for i, s in enumerate(self.stations) if s.url == self.prefs.last_played), -1)
        self.player.set_volume(self.effective_volume)
        self._emit(Change.STATE | Change.STATIONS | Change.VOLUME | Change.HISTORY | Change.PREFERENCES
                   | Change.STATISTICS)
        if self.current >= 0 and not autostart:
            self.play()

    def _prune_covers(self) -> None:
        """Keeps only the newest cover pictures, so the cache doesn't grow with every song."""
        try:
            entries = list(os.scandir(self.paths.cache / "covers"))
        except OSError:
            return
        files = []
        for entry in entries:
            try:
                if entry.is_file():
                    files.append((entry.stat().st_mtime, entry.path))
            except OSError:
                continue
        files.sort(reverse=True)
        for _mtime, path in files[COVERS_KEPT:]:
            try:
                os.remove(path)
            except OSError:
                pass

    # Saving never stops the radio. Only a station list that couldn't be saved is worth telling (as Windows).
    def _stations_changed(self, extra: Change = Change(0)) -> None:
        changes = Change.STATIONS | extra
        try:
            save_stations(self._stations_file, self.stations)
        except OSError:
            self.notice = self._("Couldn't save the station list.")
            changes |= Change.MESSAGE
        self._emit(changes)

    def _save_preferences(self) -> None:
        try:
            save_preferences(self._preferences_file, self.prefs)
        except OSError:
            pass

    def _save_history(self) -> None:
        try:
            save_history(self._history_file, self.history)
        except OSError:
            pass

    def _load_statistics(self) -> Statistics:
        """A file that can't be read is kept as statistics.json.bad, so the next save doesn't lose it."""
        path = self._statistics_file
        try:
            return load_statistics(path)
        except ValueError:
            try:
                os.replace(path, path.with_name(path.name + ".bad"))
            except OSError:
                pass
        except OSError:
            pass
        return Statistics()

    def _save_statistics(self) -> None:
        self._statistics_unsaved = False
        try:
            save_statistics(self._statistics_file, self.statistics)
        except OSError:
            pass

    # ---- Playback ----

    def play(self) -> None:
        """Starts the chosen station (the first one if none is chosen). A station already on keeps going."""
        if not self.active:
            self._start()

    def _start(self) -> None:
        """A new connection to the chosen station, dropping the current one (StartPlayback on Windows)."""
        if not self.stations:
            return
        if not 0 <= self.current < len(self.stations):
            self.current = 0
        self._end_session()
        self._url = self.stations[self.current].url
        self._kind = station_kind(self._url)
        self._attempt = 0
        self._ever_played = False
        self._polling = False
        self._connect()
        self._emit(Change.STATE | Change.TRACK | Change.COVER)

    def stop(self, message: str | None = None) -> None:
        self._end_session()
        self.player.stop()
        self.status = Status.STOPPED
        self.message = message
        self._emit(Change.STATE | Change.TRACK | Change.COVER)

    def toggle(self) -> None:
        if self.active:
            self.stop()
        else:
            self.play()

    def _end_session(self) -> None:
        """Forgets the current session: callbacks still on their way are ignored from now on."""
        self._listening_ended()
        self._session += 1
        for timer in (self._retry_timer, self._poll_timer, self._switch_timer):
            if timer is not None:
                self.scheduler.cancel(timer)
        self._retry_timer = self._poll_timer = self._switch_timer = None
        self._forget_titles()
        self.gave_up_on_network_at = None
        self.track = None
        self.cover_path = None

    def _connect(self) -> None:
        self._retry_timer = None
        self.status = Status.CONNECTING
        self.message = None
        self._attempt_started = self.scheduler.now()
        self.player.play(self._url)

    def _retry(self, session: int) -> None:
        if session == self._session and self.status is Status.RETRYING:
            self._connect()
            self._emit(Change.STATE)

    def _connection_ended(self, error: str | None) -> None:
        """The stream broke (`error`) or simply ended (None). Mirrors the retry loop of StartPlayback."""
        now = self.scheduler.now()
        if now - self._attempt_started > LONG_CONNECTION:
            self._attempt = 0
        if self._attempt >= (RETRIES_ONCE_PLAYED if self._ever_played else RETRIES_NEVER_PLAYED):
            if error is None:
                self.stop(self._("The broadcast has ended"))
            else:
                self.stop(error)
                self.gave_up_on_network_at = now
            return
        delay = BACKOFF[min(self._attempt, len(BACKOFF) - 1)]
        self._attempt += 1
        self._listening_ended()   # a reconnect within 2 minutes continues the same statistics session
        self.player.stop()
        self._forget_titles()
        self.track = None
        self.cover_path = None
        self.status = Status.RETRYING
        self.message = self._("Connection lost. Retrying in {n} s…").format(n=delay)
        session = self._session
        self._retry_timer = self.scheduler.call_later(delay, lambda: self._retry(session))
        self._emit(Change.STATE | Change.TRACK | Change.COVER)

    def network_available(self, was_down: bool = True) -> None:
        """The network settled: connect now instead of waiting out a retry, or start again
        if the retries ran out because the connection was lost less than 10 minutes ago.
        A playing station kept its connection (a VPN, a new interface), unless the network was down in between."""
        if self.status is Status.PLAYING and not was_down:
            return
        self._come_back()

    def resumed(self) -> None:
        """Back from sleep: the old connection is dead."""
        self._come_back()

    def _come_back(self) -> None:
        if self.active or (self.gave_up_on_network_at is not None
                           and self.scheduler.now() - self.gave_up_on_network_at < NETWORK_RETURN_WINDOW):
            self._start()

    # ---- Called by the player (on the main loop) ----

    def _connected(self) -> bool:
        # While a switch waits to connect, the player still plays the station from before: not this one's news.
        return self._switch_timer is None and self.status in (Status.CONNECTING, Status.PLAYING)

    def on_player_started(self) -> None:
        if self.status is not Status.CONNECTING or self._switch_timer is not None:
            return
        self._ever_played = True
        self.status = Status.PLAYING
        self.message = None
        self.prefs.last_played = self._url
        self._save_preferences()
        self._listening_started()
        self._emit(Change.STATE)
        if self._kind == "radio357" and not self._polling:
            self._polling = True
            self._poll_radio357(self._session)

    def on_player_title(self, raw: str) -> None:
        # Radio 357 sends a fixed slogan in the stream; its songs come from playing.json.
        if self._connected() and self._kind != "radio357":
            self._offer_title(raw)

    def on_player_error(self, kind: ErrorKind, detail: str) -> None:
        if not self._connected():
            return
        if kind is ErrorKind.NETWORK:
            self._connection_ended(detail)
        else:
            self.stop(detail)

    def on_player_eos(self) -> None:
        if self._connected():
            self._connection_ended(None)

    # ---- Titles, covers, history ----

    def _offer_title(self, raw: str | None) -> None:
        """A title from the stream. Changes are applied at most once every TITLE_SECONDS, so a station sending
        titles by the hundred can't slow the radio down (each one is saved in the history and the statistics, and
        looks for a cover): the first at once, and of those that come in the next TITLE_SECONDS the newest when
        they are over, so the title shown is never an old one. Everything after a title sees only applied ones."""
        if self._title_timer is not None:
            self._title_waiting = (raw,)
            return
        if parse_title(raw, self._kind) == self.track:
            return   # no change: nothing to hold the next one back for
        self._show_track(raw)
        self._title_timer = self.scheduler.call_later(TITLE_SECONDS, self._title_due)

    def _title_due(self) -> None:
        self._title_timer = None
        waiting, self._title_waiting = self._title_waiting, None
        if waiting is not None and self._connected():
            self._offer_title(waiting[0])

    def _forget_titles(self) -> None:
        """A new station or connection: its first title is applied at once, and none from before."""
        if self._title_timer is not None:
            self.scheduler.cancel(self._title_timer)
        self._title_timer = None
        self._title_waiting = None

    def _show_track(self, raw: str | None) -> None:
        title = parse_title(raw, self._kind)
        artwork = artwork_from_raw(raw) if title is not None else None
        if title == self.track:
            return
        self.track = title
        self.cover_path = None
        changes = Change.TRACK | Change.COVER
        if title is not None and self._add_to_history(title):
            changes |= Change.HISTORY
        self._emit(changes)
        if title is None:
            return
        if artwork is not None:
            self._download_cover(artwork, title)
        else:
            self._find_cover(title)

    def _add_to_history(self, title: str) -> bool:
        station = self.station_name or APP_NAME
        if self.history and self.history[0].title == title and self.history[0].station == station:
            return False
        self.history.insert(0, HistoryEntry(title, station, self.scheduler.now()))
        del self.history[HISTORY_LIMIT:]
        self._save_history()
        if self.prefs.collect_statistics:
            self._recorder.song(station, title, self._statistics_now())   # saved with the session
            self._statistics_unsaved = True
            self._pending |= Change.STATISTICS
        return True

    def clear_history(self) -> None:
        self.history.clear()
        self._save_history()
        self._emit(Change.HISTORY)

    # ---- Listening statistics ----

    def _statistics_now(self) -> datetime:
        return self.scheduler.now().astimezone(timezone.utc)

    def _listening_started(self) -> None:
        """The sound started: a statistics session begins (or a reconnect continues the last one)."""
        if not self.prefs.collect_statistics:
            return
        self._recorder.started(self.station_name or APP_NAME, self._url, self._statistics_now())
        self._save_statistics()
        if self._statistics_timer is not None:
            self.scheduler.cancel(self._statistics_timer)
        self._statistics_timer = self.scheduler.call_later(SAVE_SECONDS, self._statistics_tick)
        self._pending |= Change.STATISTICS

    def _listening_ended(self) -> None:
        """The sound stopped (Stop, another station, the sleep timer, an error, a lost connection, quitting)."""
        if self._statistics_timer is not None:
            self.scheduler.cancel(self._statistics_timer)
            self._statistics_timer = None
        running = self._recorder.current is not None
        self._recorder.stopped(self._statistics_now())
        if running or self._statistics_unsaved:
            self._save_statistics()
            self._pending |= Change.STATISTICS

    def _keep_listening(self) -> None:
        """The running session goes on until now; after the computer slept, a new one starts now."""
        now = self._statistics_now()
        if not self._recorder.alive(now) and self.status is Status.PLAYING and self._switch_timer is None \
                and self.prefs.collect_statistics:
            self._recorder.started(self.station_name or APP_NAME, self._url, now)

    def _statistics_tick(self) -> None:
        """Every 5 minutes while playing: the session is saved, so a crash loses at most that much."""
        self._statistics_timer = None
        self._keep_listening()
        self._save_statistics()
        if self._recorder.current is not None:
            self._statistics_timer = self.scheduler.call_later(SAVE_SECONDS, self._statistics_tick)
        self._emit(Change.STATISTICS)

    def refresh_statistics(self) -> None:
        """Brings the running session up to now, for the Statistics page."""
        self._keep_listening()

    def suspending(self) -> None:
        """The computer is about to sleep: the running session ends here, not when the radio notices it woke up."""
        if self._recorder.current is not None:
            self._recorder.suspend(self._statistics_now())
            self._save_statistics()

    def shutdown(self) -> None:
        """Quitting: the running session ends now and the statistics are saved."""
        self._listening_ended()
        if self._statistics_unsaved:
            self._save_statistics()

    def clear_statistics(self) -> None:
        """Deletes the statistics (not the song history); a station that is playing counts again from now."""
        self._recorder.clear(self._statistics_now())
        self._save_statistics()
        self._emit(Change.STATISTICS)

    def _still_showing(self, session: int, title: str) -> bool:
        return session == self._session and self.track == title

    def _find_cover(self, title: str) -> None:
        known, url = self._covers.get(title)
        if known:
            if url is not None:
                self._download_cover(url, title)
            return
        search = itunes_search_url(title)
        if search is None:
            return
        session = self._session

        def answered(payload: Any | None) -> None:
            if payload is None:
                return   # a failed lookup isn't remembered: the song is looked up again next time
            cover = pick_cover(split_track(title)[0], payload)
            self._covers.put(title, cover)
            if cover is not None and self._still_showing(session, title):
                self._download_cover(cover, title)

        self.fetch(search, answered)

    def _download_cover(self, url: str, title: str) -> None:
        name = hashlib.sha1(url.encode("utf-8"), usedforsecurity=False).hexdigest() + ".jpg"
        path = self.paths.cache / "covers" / name
        if path.is_file():
            self._show_cover(path)
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        session = self._session

        def done(ok: bool) -> None:
            if ok and self._still_showing(session, title):
                self._show_cover(path)

        self.fetch_file(url, path, done)

    def _show_cover(self, path: Path) -> None:
        """Only a picture whose declared size is read and fits (core/imagesize.py), downloaded now or kept from
        before: the footer, the notification and the desktop's media controls (MPRIS) all decode it. Any other file
        is deleted."""
        try:
            ok = fits(path.read_bytes())
        except OSError:
            return
        if not ok:
            try:
                os.remove(path)
            except OSError:
                pass
            return
        self.cover_path = path
        self._emit(Change.COVER)

    def _poll_radio357(self, session: int) -> None:
        """Every 10 s after each answer, while this session lasts."""
        self._poll_timer = None
        if session != self._session:
            return

        def answered(payload: Any | None) -> None:
            if session != self._session:
                return
            if self._connected():
                self._offer_title(radio357_title(payload))
            self._poll_timer = self.scheduler.call_later(
                RADIO357_POLL_SECONDS, lambda: self._poll_radio357(session))

        self.fetch(RADIO357_NOW_URL, answered)

    # ---- Volume and sleep timer ----

    def set_volume(self, percent: int) -> None:
        value = max(0, min(100, round(percent)))
        if value == self.volume:
            return
        # Changes less than a second apart count as one (as on Windows): turned down to 0 that way,
        # unmuting brings back the level from before them, not the 1 % passed last.
        now = self.scheduler.now()
        if self._volume_changed_at is None or now - self._volume_changed_at > VOLUME_BURST:
            self._volume_before = self.volume
        self._volume_changed_at = now
        if value == 0 and self._volume_before > 0:
            self._unmute_volume = self._volume_before
        self.volume = self.prefs.volume = value
        self.player.set_volume(self.effective_volume)
        self._save_preferences()
        self._emit(Change.VOLUME)

    def toggle_mute(self) -> None:
        """The speaker button: mutes, or unmutes to the level from before (30 if there was none)."""
        before = self.volume
        self.set_volume(self._unmute_volume if before == 0 else 0)
        if before > 0:
            self._unmute_volume = before

    def set_sleep_timer(self, minutes: int | None) -> None:
        if self._sleep_timer is not None:
            self.scheduler.cancel(self._sleep_timer)
            self._sleep_timer = None
        if minutes is not None and minutes <= 0:
            minutes = None
        self.sleep_minutes = minutes
        self.sleep_at = None if minutes is None else self.scheduler.now() + timedelta(minutes=minutes)
        self._set_fade(100)
        if minutes is not None:
            self._sleep_timer = self.scheduler.call_later(1, self._sleep_tick)
        self._emit(Change.SLEEP)

    def _sleep_tick(self) -> None:
        self._sleep_timer = None
        if self.sleep_at is None:
            return
        left = (self.sleep_at - self.scheduler.now()).total_seconds()
        if left <= 0:
            if self.active:
                self.stop(self._("Stopped by the sleep timer"))
            else:
                self.gave_up_on_network_at = None   # the network coming back must not start it again
            self.set_sleep_timer(None)   # after stopping, so the full volume never sounds
            return
        self._set_fade(100 if left >= FADE_SECONDS else int(left * 100 / FADE_SECONDS))
        self._sleep_timer = self.scheduler.call_later(1, self._sleep_tick)

    def _set_fade(self, fade: int) -> None:
        if fade != self._fade:
            self._fade = fade
            self.player.set_volume(self.effective_volume)

    # ---- Choosing a station ----

    def select(self, index: int, switched: bool = False) -> None:
        """`switched`: by a media key or the tray menu, so the desktop shows which station is on.

        A switch while on shows the new station at once, but connects only after SWITCH_SETTLE without another
        switch: skipping through stations doesn't connect to each one, and the player never stops a stream it has
        just started (GStreamer can crash on that)."""
        if not 0 <= index < len(self.stations):
            return
        changes = Change.SWITCHED if switched else Change(0)
        if index != self.current:
            self.current = index
            if self.active and switched:
                self._end_session()   # also drops a switch still waiting
                self.status = Status.CONNECTING
                self.message = None
                self._switch_timer = self.scheduler.call_later(SWITCH_SETTLE, self._switch_settled)
                changes |= Change.STATE | Change.TRACK | Change.COVER
            elif self.active:
                self._start()
            else:
                self.gave_up_on_network_at = None   # another station chosen: don't bring back the lost one
                self.status = Status.READY
                self.message = None
                changes |= Change.STATE
        self._emit(changes)

    def _switch_settled(self) -> None:
        self._switch_timer = None
        self._start()

    def next_station(self) -> None:
        if self.stations:
            self.select((self.current + 1) % len(self.stations), switched=True)

    def previous_station(self) -> None:
        count = len(self.stations)
        if count:
            self.select((self.current - 1) % count if self.current >= 0 else count - 1, switched=True)

    # ---- Editing the station list ----

    @staticmethod
    def _cleaned(s: Station) -> Station | None:
        """The station form, radio-browser and share links all add through here."""
        name, url, logo = clean_name(s.name), (s.url or "").strip(), (s.logo or "").strip()
        if not name or not is_web_url(url) or (logo and not is_web_url(logo)):
            return None
        return Station(name, url, logo or None)

    def add_station(self, s: Station) -> AddResult:
        station = self._cleaned(s)
        if station is None:
            return AddResult.INVALID
        if any(same_stream(known.url, station.url) for known in self.stations):
            return AddResult.DUPLICATE
        self.stations.append(station)
        if self.current < 0:
            self.select(len(self.stations) - 1)
        self._stations_changed()
        return AddResult.ADDED

    def update_station(self, index: int, s: Station) -> AddResult:
        station = self._cleaned(s)
        if station is None or not 0 <= index < len(self.stations):
            return AddResult.INVALID
        if any(i != index and same_stream(known.url, station.url) for i, known in enumerate(self.stations)):
            return AddResult.DUPLICATE
        old = self.stations[index]
        self.stations[index] = station
        if self.prefs.last_played is not None and self.prefs.last_played == old.url:
            self.prefs.last_played = station.url
            self._save_preferences()
        if index == self.current and self.active and old.url != station.url:
            self._start()
        elif self.current < 0:
            self.select(index)
        self._stations_changed(Change.STATE if index == self.current else Change(0))
        return AddResult.ADDED

    def move_station(self, index: int, delta: int) -> None:
        count, target = len(self.stations), index + delta
        if delta == 0 or not 0 <= index < count or not 0 <= target < count:
            return
        chosen = self.stations[self.current] if 0 <= self.current < count else None
        self.stations.insert(target, self.stations.pop(index))
        before = self.current
        if chosen is not None:
            self.current = next(i for i, s in enumerate(self.stations) if s is chosen)
        self._stations_changed(Change.STATE if self.current != before else Change(0))

    def remove_station(self, index: int) -> None:
        if not 0 <= index < len(self.stations):
            return
        removed = self.stations.pop(index)
        changes = Change(0)
        if index == self.current:
            self.current = -1
            self.stop()
        elif index < self.current:
            self.current -= 1
            changes = Change.STATE
        if self.prefs.last_played == removed.url:
            self.prefs.last_played = None
            self._save_preferences()
        self._stations_changed(changes)

    # ---- Shared stations (core/share.py) ----

    def find_station(self, url: str) -> int:
        """The index of the station on the list with this stream address (the duplicate rule), -1 if none."""
        return next((i for i, s in enumerate(self.stations) if same_stream(s.url, url)), -1)

    def play_station(self, index: int) -> None:
        """Plays the station at `index`; one that is already on keeps going."""
        if 0 <= index < len(self.stations):
            self.select(index)
            self.play()

    def add_and_play(self, shared: SharedStation) -> AddResult:
        """Add and play on the Shared station page: appended at the end and played. One that is on the list
        already (the link was opened twice) just plays."""
        result = self.add_station(Station(shared.name, shared.url, shared.logo))
        if result is AddResult.ADDED:
            self.play_station(len(self.stations) - 1)
        elif result is AddResult.DUPLICATE:
            self.play_station(self.find_station(shared.url))
        return result

    def import_stations(self, path: Path) -> ImportResult:
        """Adds the stations from a list exported here or on Windows, skipping the ones already here."""
        try:
            with open(path, encoding="utf-8-sig") as file:
                data = json.load(file)
        except (OSError, ValueError, RecursionError):
            data = None
        if not isinstance(data, list):
            return ImportResult(0, self._("This isn't a Minimalistic Radio station list."))
        known = {stream_key(s.url) for s in self.stations}
        fresh = []
        for item in data:
            if not isinstance(item, dict):
                continue
            name, url, logo = item.get("Name"), item.get("Url"), item.get("Logo")
            name = clean_name(name) if isinstance(name, str) else ""
            if not name or not isinstance(url, str) or not is_web_url(url):
                continue
            key = stream_key(url)
            if key in known:
                continue
            known.add(key)
            fresh.append(Station(name, url, logo if isinstance(logo, str) and is_web_url(logo) else None))
        if fresh:
            self.stations.extend(fresh)
            self._stations_changed()
        return ImportResult(len(fresh), None)

    def export_stations(self, path: Path) -> bool:
        """Writes the list the way Windows does. False if the file couldn't be saved."""
        try:
            save_stations(path, self.stations)
        except OSError:
            return False
        return True

    # ---- Preferences ----

    def set_language(self, code: str) -> None:
        if code not in LANGUAGES or code == self.prefs.language:
            return
        self.prefs.language = code
        self._save_preferences()
        self._emit(Change.PREFERENCES)

    def set_show_station_popup(self, on: bool) -> None:
        if on == self.prefs.show_station_popup:
            return
        self.prefs.show_station_popup = on
        self._save_preferences()
        self._emit(Change.PREFERENCES)

    def set_collect_statistics(self, on: bool) -> None:
        """Settings › Statistics. Off: nothing new is recorded and a running session ends now; what was collected
        stays. On while a station plays: it counts from now."""
        if on == self.prefs.collect_statistics:
            return
        self.prefs.collect_statistics = on
        self._save_preferences()
        if on:
            if self.status is Status.PLAYING and self._switch_timer is None:
                self._listening_started()
        else:
            self._listening_ended()
        self._emit(Change.PREFERENCES | Change.STATISTICS)

    def set_no_tray_hint_shown(self) -> None:
        if not self.prefs.no_tray_hint_shown:
            self.prefs.no_tray_hint_shown = True
            self._save_preferences()

    def set_autostart_preference(self, on: bool) -> None:
        """Remembers the "Start with the system" choice (the application makes it happen). Always announced:
        when the Background portal says no, the switch goes back off even though nothing changed here."""
        if on != self.prefs.autostart:
            self.prefs.autostart = on
            self._save_preferences()
        self._emit(Change.PREFERENCES)

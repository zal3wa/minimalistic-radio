"""Listening statistics (core/statistics.py): recording sessions and songs, and counting them for the page."""
from datetime import date, datetime, timedelta, timezone

import pytest

from minimalistic_radio.core.models import ListeningSession, SongPlay, Statistics
from minimalistic_radio.core.statistics import (
    Period, Recorder, artist_of, count, enough_titles, format_count, format_duration, format_hours, period_label,
    plays_text, since_label,
)
from minimalistic_radio.core.storage import load_statistics, save_statistics

UTC = timezone.utc
WARSAW_WINTER = timezone(timedelta(hours=1))   # a fixed offset: the tests don't depend on the machine's zone


def at(*args, tz=UTC):
    return datetime(*args, tzinfo=tz)


def session(start, end, station="Antyradio Hard", url="https://hard.example/live", titles=False):
    return ListeningSession(station, url, start, end, titles)


def stats_of(*sessions, songs=()):
    return Statistics(list(sessions), list(songs))


# ---- The file ----

def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "statistics.json"
    stats = stats_of(session(at(2026, 11, 15, 19, 2), at(2026, 11, 15, 20, 41, 30), titles=True),
                     songs=[SongPlay("Antyradio Hard", "Leonard Cohen - Everybody Knows", at(2026, 11, 15, 19, 5, 12))])
    save_statistics(path, stats)
    text = path.read_text(encoding="utf-8")
    assert '"version": 1' in text and '"start": "2026-11-15T19:02:00Z"' in text and '"titles": true' in text
    assert '"time": "2026-11-15T19:05:12Z"' in text
    assert load_statistics(path) == stats


def test_times_are_saved_in_utc(tmp_path):
    path = tmp_path / "statistics.json"
    save_statistics(path, stats_of(session(at(2026, 11, 15, 20, 0, tz=WARSAW_WINTER),
                                           at(2026, 11, 15, 21, 0, tz=WARSAW_WINTER))))
    assert '"start": "2026-11-15T19:00:00Z"' in path.read_text(encoding="utf-8")


def test_missing_file_is_empty(tmp_path):
    assert load_statistics(tmp_path / "none.json") == Statistics()


def test_corrupt_file_raises(tmp_path):
    path = tmp_path / "statistics.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_statistics(path)
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_statistics(path)


def test_bad_entries_are_skipped(tmp_path):
    path = tmp_path / "statistics.json"
    path.write_text("""{"version": 1,
      "sessions": [{"station": "A", "url": "http://a", "start": "2026-11-15T19:00:00Z", "end": "2026-11-15T20:00:00Z"},
                   {"station": "B", "url": "http://b", "start": "yesterday", "end": "2026-11-15T20:00:00Z"},
                   {"station": "C", "url": "http://c", "start": "2026-11-15T21:00:00Z", "end": "2026-11-15T20:00:00Z"},
                   "nonsense", {"station": 5}],
      "songs": [{"station": "A", "title": "X - Y", "time": "2026-11-15T19:30:00+00:00"}, {"title": "no time"}]}""",
                    encoding="utf-8")
    stats = load_statistics(path)
    assert [s.station for s in stats.sessions] == ["A"] and stats.sessions[0].titles is False
    assert stats.songs == [SongPlay("A", "X - Y", at(2026, 11, 15, 19, 30))]


# ---- Recording ----

def test_a_session_runs_from_start_to_stop():
    stats = Statistics()
    recorder = Recorder(stats)
    recorder.started("Radio 357", "https://357.example/", at(2026, 11, 15, 19, 0))
    recorder.alive(at(2026, 11, 15, 19, 5))
    assert stats.sessions[0].end == at(2026, 11, 15, 19, 5)
    recorder.stopped(at(2026, 11, 15, 19, 7))
    assert stats.sessions == [session(at(2026, 11, 15, 19, 0), at(2026, 11, 15, 19, 7), "Radio 357",
                                      "https://357.example/")]
    assert recorder.current is None


def listen(recorder, url, start, end):
    """Plays `url` from start to end, with the controller's update every five minutes."""
    recorder.started(url.upper(), url, start)
    tick = start + timedelta(minutes=5)
    while tick < end:
        recorder.alive(tick)
        tick += timedelta(minutes=5)
    recorder.stopped(end)


def test_a_reconnect_within_two_minutes_continues_the_session():
    stats = Statistics()
    recorder = Recorder(stats)
    listen(recorder, "http://a", at(2026, 11, 15, 19, 0), at(2026, 11, 15, 19, 30))
    listen(recorder, "http://a", at(2026, 11, 15, 19, 32), at(2026, 11, 15, 20, 0))
    assert stats.sessions == [session(at(2026, 11, 15, 19, 0), at(2026, 11, 15, 20, 0), "HTTP://A", "http://a")]


def test_a_later_reconnect_or_another_station_is_a_new_session():
    stats = Statistics()
    recorder = Recorder(stats)
    listen(recorder, "http://a", at(2026, 11, 15, 19, 0), at(2026, 11, 15, 19, 30))
    listen(recorder, "http://a", at(2026, 11, 15, 19, 32, 1), at(2026, 11, 15, 19, 40))   # 2 min 1 s later
    listen(recorder, "http://b", at(2026, 11, 15, 19, 40), at(2026, 11, 15, 19, 50))   # at once, another station
    assert [(s.url, s.start.minute, s.end.minute) for s in stats.sessions] == [
        ("http://a", 0, 30), ("http://a", 32, 40), ("http://b", 40, 50)]


def test_without_updates_for_too_long_the_session_ends_at_the_last_one():
    stats = Statistics()
    recorder = Recorder(stats)
    recorder.started("A", "http://a", at(2026, 11, 15, 19, 0))
    recorder.alive(at(2026, 11, 15, 19, 5))
    recorder.alive(at(2026, 11, 15, 19, 11))   # six minutes later: still the same session
    recorder.stopped(at(2026, 11, 15, 19, 17, 1))   # six minutes and a second later: the clock jumped
    assert stats.sessions[0].end == at(2026, 11, 15, 19, 11)


def test_a_title_marks_the_session_and_is_recorded():
    stats = Statistics()
    recorder = Recorder(stats)
    recorder.started("A", "http://a", at(2026, 11, 15, 19, 0))
    recorder.song("A", "Queen - A Kind Of Magic", at(2026, 11, 15, 19, 1))
    recorder.stopped(at(2026, 11, 15, 19, 10))
    assert stats.sessions[0].titles is True
    assert stats.songs == [SongPlay("A", "Queen - A Kind Of Magic", at(2026, 11, 15, 19, 1))]


def test_a_title_before_the_sound_starts_counts_for_the_session():
    stats = Statistics()
    recorder = Recorder(stats)
    recorder.song("A", "Queen - A Kind Of Magic", at(2026, 11, 15, 19, 0))   # while connecting
    recorder.started("A", "http://a", at(2026, 11, 15, 19, 0, 2))
    assert stats.sessions[0].titles is True
    recorder.stopped(at(2026, 11, 15, 19, 10))
    recorder.started("A", "http://a", at(2026, 11, 15, 21, 0))
    assert stats.sessions[1].titles is False


def test_a_clock_jump_ends_the_session_at_its_last_update():
    stats = Statistics()
    recorder = Recorder(stats)
    recorder.started("A", "http://a", at(2026, 11, 15, 19, 0))
    assert recorder.alive(at(2026, 11, 15, 19, 5)) is True
    assert recorder.alive(at(2026, 11, 15, 23, 0)) is False   # the computer slept
    assert recorder.current is None and stats.sessions[0].end == at(2026, 11, 15, 19, 5)
    recorder.stopped(at(2026, 11, 15, 23, 1))
    assert stats.sessions[0].end == at(2026, 11, 15, 19, 5)


def test_a_clock_going_back_ends_the_session_too():
    stats = Statistics()
    recorder = Recorder(stats)
    recorder.started("A", "http://a", at(2026, 11, 15, 19, 0))
    recorder.stopped(at(2026, 11, 15, 18, 0))
    assert stats.sessions[0].end == at(2026, 11, 15, 19, 0)


def test_going_to_sleep_ends_the_session_there():
    stats = Statistics()
    recorder = Recorder(stats)
    recorder.started("A", "http://a", at(2026, 11, 15, 19, 0))
    recorder.suspend(at(2026, 11, 15, 19, 3))
    assert stats.sessions[0].end == at(2026, 11, 15, 19, 3)
    assert recorder.alive(at(2026, 11, 15, 19, 4)) is False   # awake again a minute later: not counted
    assert stats.sessions[0].end == at(2026, 11, 15, 19, 3)


def test_clearing_keeps_the_running_session_going_from_now():
    stats = stats_of(session(at(2026, 11, 1, 10), at(2026, 11, 1, 11)),
                     songs=[SongPlay("A", "X - Y", at(2026, 11, 1, 10, 30))])
    recorder = Recorder(stats)
    recorder.started("B", "http://b", at(2026, 11, 15, 19, 0))
    recorder.clear(at(2026, 11, 15, 19, 30))
    assert stats.songs == []
    assert stats.sessions == [session(at(2026, 11, 15, 19, 30), at(2026, 11, 15, 19, 30), "B", "http://b")]
    assert recorder.current is stats.sessions[0]
    stopped = Recorder(stats_of(session(at(2026, 11, 1, 10), at(2026, 11, 1, 11))))
    stopped.clear(at(2026, 11, 15, 19, 30))
    assert stopped.stats == Statistics()


# ---- Counting: periods ----

NOW = at(2026, 11, 15, 20, 30)   # Sunday 15 November 2026, in UTC


def test_month_counts_only_this_month():
    stats = stats_of(session(at(2026, 11, 3, 10), at(2026, 11, 3, 12)),
                     session(at(2026, 10, 30, 10), at(2026, 10, 30, 11)))
    summary = count(stats, Period.MONTH, NOW, UTC)
    assert summary.total == 2 * 3600
    assert summary.since == at(2026, 11, 1)


def test_a_session_across_midnight_at_the_month_start_counts_its_part():
    stats = stats_of(session(at(2026, 10, 31, 23), at(2026, 11, 1, 1)))
    assert count(stats, Period.MONTH, NOW, UTC).total == 3600
    assert count(stats, Period.YEAR, NOW, UTC).total == 2 * 3600


def test_a_session_across_new_year_counts_its_part():
    stats = stats_of(session(at(2025, 12, 31, 23, 30), at(2026, 1, 1, 0, 45)))
    assert count(stats, Period.YEAR, NOW, UTC).total == 45 * 60
    assert count(stats, Period.ALL, NOW, UTC).total == 75 * 60


def test_periods_follow_local_time():
    # 23:30 UTC on 31 October is already 00:30 on 1 November in Warsaw (UTC+1).
    stats = stats_of(session(at(2026, 10, 31, 23, 30), at(2026, 10, 31, 23, 50)))
    assert count(stats, Period.MONTH, NOW, WARSAW_WINTER).total == 20 * 60
    assert count(stats, Period.MONTH, NOW, UTC).total == 0


def test_all_starts_at_the_first_session():
    stats = stats_of(session(at(2026, 11, 3, 10), at(2026, 11, 3, 11)), session(at(2025, 3, 2, 18), at(2025, 3, 2, 19)))
    summary = count(stats, Period.ALL, NOW, UTC)
    assert summary.since == at(2025, 3, 2, 18) and summary.total == 2 * 3600


def test_nothing_in_the_period():
    summary = count(stats_of(session(at(2025, 3, 2, 18), at(2025, 3, 2, 19))), Period.MONTH, NOW, UTC)
    assert summary.empty and summary.total == 0 and summary.peak_hour is None and summary.top_stations == []
    assert count(Statistics(), Period.ALL, NOW, UTC).empty


# ---- Counting: per day ----

def test_per_day_divides_by_the_days_so_far():
    stats = stats_of(session(at(2026, 11, 2, 10), at(2026, 11, 2, 17, 30)))   # 7.5 h
    assert count(stats, Period.MONTH, NOW, UTC).per_day == 7.5 * 3600 / 15             # 15 November
    assert count(stats, Period.YEAR, NOW, UTC).per_day == 7.5 * 3600 / 319             # day 319 of 2026
    assert count(stats, Period.ALL, NOW, UTC).per_day == 7.5 * 3600 / 14              # 2 to 15 November


def test_per_day_for_all_is_at_least_one_day():
    stats = stats_of(session(at(2026, 11, 15, 18), at(2026, 11, 15, 20)))
    assert count(stats, Period.ALL, NOW, UTC).per_day == 2 * 3600


# ---- Counting: tiles, top lists, the share, the hours ----

def test_tiles():
    stats = stats_of(session(at(2026, 11, 3, 10), at(2026, 11, 3, 14, 50)),
                     session(at(2026, 11, 4, 10), at(2026, 11, 4, 11), "Radio 357", "https://357.example/"),
                     session(at(2026, 11, 5, 10), at(2026, 11, 5, 11)),
                     session(at(2026, 10, 1, 10), at(2026, 10, 1, 20), "Old", "http://old"),
                     songs=[SongPlay("A", "X - Y", at(2026, 11, 3, 10, 5)), SongPlay("A", "Z", at(2026, 11, 3, 10, 9)),
                            SongPlay("A", "Old - Song", at(2026, 10, 1, 10, 9))])
    summary = count(stats, Period.MONTH, NOW, UTC)
    assert summary.songs == 2
    assert summary.stations == 2
    assert summary.longest == 4 * 3600 + 50 * 60


def test_the_longest_session_counts_only_its_part_in_the_period():
    stats = stats_of(session(at(2026, 10, 31, 14), at(2026, 11, 1, 2)), session(at(2026, 11, 4, 10), at(2026, 11, 4, 13)))
    assert count(stats, Period.MONTH, NOW, UTC).longest == 3 * 3600


def test_top_stations_by_time_up_to_five():
    sessions = [session(at(2026, 11, 2 + i, 10), at(2026, 11, 2 + i, 10) + timedelta(minutes=10 * (i + 1)),
                        f"S{i}", f"http://s{i}") for i in range(6)]
    sessions.append(session(at(2026, 11, 10, 10), at(2026, 11, 10, 10, 15), "S0 renamed", "http://s0"))
    summary = count(stats_of(*sessions), Period.MONTH, NOW, UTC)
    assert [(t.name, t.url, t.seconds) for t in summary.top_stations] == [
        ("S5", "http://s5", 3600), ("S4", "http://s4", 3000), ("S3", "http://s3", 2400),
        ("S2", "http://s2", 1800), ("S0 renamed", "http://s0", 1500)]


def test_top_artists_by_plays():
    songs = ([SongPlay("A", "Queen - A Kind Of Magic", at(2026, 11, 3, 10))] * 3
             + [SongPlay("A", "Leonard Cohen - Everybody Knows", at(2026, 11, 3, 11))] * 2
             + [SongPlay("A", "QUEEN - Bohemian Rhapsody", at(2026, 11, 3, 12))]
             + [SongPlay("A", "Only a title", at(2026, 11, 3, 12))] * 9
             + [SongPlay("A", f"Artist {i} - Song", at(2026, 11, 3, 13)) for i in range(5)]
             + [SongPlay("A", "Editors - Shadow", at(2026, 10, 3, 13))] * 9)   # last month
    stats = stats_of(session(at(2026, 11, 3, 10), at(2026, 11, 3, 14), titles=True), songs=songs)
    summary = count(stats, Period.MONTH, NOW, UTC)
    assert summary.top_artists == [("Queen", 4), ("Leonard Cohen", 2), ("Artist 0", 1), ("Artist 1", 1),
                                   ("Artist 2", 1)]
    assert summary.songs == 20


def test_the_artist_is_before_the_first_separator():
    assert artist_of("Leonard Cohen - Everybody Knows") == "Leonard Cohen"
    assert artist_of("Daft Punk – One More Time") == "Daft Punk"
    assert artist_of("AC/DC - Back In Black - Remastered") == "AC/DC"
    assert artist_of("Only a title") is None
    assert artist_of(" - starts with a dash") is None


def test_the_titles_share_and_its_threshold():
    titled = session(at(2026, 11, 3, 10), at(2026, 11, 3, 11), titles=True)
    plain = session(at(2026, 11, 4, 10), at(2026, 11, 4, 14), "Plain", "http://plain")
    songs = [SongPlay("Antyradio Hard", "Queen - A Kind Of Magic", at(2026, 11, 3, 10, 30))]
    summary = count(stats_of(titled, plain, songs=songs), Period.MONTH, NOW, UTC)
    assert summary.titles_share == 0.2 and enough_titles(summary)
    plain.end = at(2026, 11, 4, 14, 1)
    summary = count(stats_of(titled, plain, songs=songs), Period.MONTH, NOW, UTC)
    assert summary.titles_share < 0.2 and not enough_titles(summary)


def test_no_artists_is_not_enough_titles():
    summary = count(stats_of(session(at(2026, 11, 3, 10), at(2026, 11, 3, 11), titles=True),
                             songs=[SongPlay("A", "Just a title", at(2026, 11, 3, 10, 5))]), Period.MONTH, NOW, UTC)
    assert summary.titles_share == 1 and not enough_titles(summary)


def test_hours_split_a_session_across_hours_and_midnight():
    stats = stats_of(session(at(2026, 11, 3, 22, 45), at(2026, 11, 4, 1, 15)))
    summary = count(stats, Period.MONTH, NOW, UTC)
    assert summary.hours[22] == 15 * 60 and summary.hours[23] == 3600 and summary.hours[0] == 3600
    assert summary.hours[1] == 15 * 60 and sum(summary.hours) == summary.total
    assert summary.peak_hour == 0   # 23 and 0 tie: the earlier hour of the day


def test_hours_across_a_daylight_saving_change():
    zoneinfo = pytest.importorskip("zoneinfo")
    try:
        warsaw = zoneinfo.ZoneInfo("Europe/Warsaw")
    except zoneinfo.ZoneInfoNotFoundError:
        pytest.skip("no time zone database")
    # 25 October 2026, 03:00 summer time goes back to 02:00: three real hours, the hour 02 twice.
    stats = stats_of(session(at(2026, 10, 25, 0), at(2026, 10, 25, 3)))
    summary = count(stats, Period.MONTH, at(2026, 10, 26, 12), warsaw)
    assert summary.total == 3 * 3600 and summary.hours[2] == 2 * 3600 and summary.hours[3] == 3600
    assert summary.since == datetime(2026, 10, 1, tzinfo=warsaw)


def test_hours_are_local_and_clipped_to_the_period():
    # Starts 31 October 23:30 Warsaw time (22:30 UTC): only the November part counts, from local midnight.
    stats = stats_of(session(at(2026, 10, 31, 22, 30), at(2026, 11, 1, 0, 30)))
    summary = count(stats, Period.MONTH, NOW, WARSAW_WINTER)
    assert summary.total == 90 * 60
    assert summary.hours[0] == 3600 and summary.hours[1] == 30 * 60 and summary.hours[23] == 0
    assert summary.peak_hour == 0


def test_the_peak_is_the_first_busiest_hour():
    stats = stats_of(session(at(2026, 11, 3, 8), at(2026, 11, 3, 9)), session(at(2026, 11, 3, 20), at(2026, 11, 3, 21)))
    assert count(stats, Period.MONTH, NOW, UTC).peak_hour == 8


def test_a_running_session_in_the_future_is_cut_at_now():
    stats = stats_of(session(at(2026, 11, 15, 20), at(2026, 11, 15, 22)))   # a clock that was ahead
    assert count(stats, Period.MONTH, NOW, UTC).total == 30 * 60


# ---- Texts ----

def test_duration_format():
    assert format_duration(0) == "0 min"
    assert format_duration(18 * 60 + 59) == "18 min"
    assert format_duration(59 * 60 + 59) == "59 min"
    assert format_duration(3600) == "1 h 00 min"
    assert format_duration(42 * 3600 + 18 * 60) == "42 h 18 min"
    assert format_duration(99 * 3600 + 59 * 60 + 59) == "99 h 59 min"
    assert format_duration(100 * 3600) == "100 h"
    assert format_duration(386 * 3600 + 59 * 60) == "386 h"


def test_duration_format_is_translated():
    polish = {"{n} min": "{n} min", "{h} h {min} min": "{h} godz. {min} min", "{h} h": "{h} godz."}
    assert format_duration(2 * 3600 + 5 * 60, polish.get) == "2 godz. 05 min"
    assert format_duration(120 * 3600, polish.get) == "120 godz."


def test_plays_use_plural_forms():
    def polish(singular, plural, n):
        form = 0 if n == 1 else 1 if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 2
        return ("{n} odtworzenie", "{n} odtworzenia", "{n} odtworzeń")[form]
    assert plays_text(1) == "1 play" and plays_text(14) == "14 plays"
    assert [plays_text(n, polish) for n in (1, 3, 5, 22, 1234)] == [
        "1 odtworzenie", "3 odtworzenia", "5 odtworzeń", "22 odtworzenia", "1 234 odtworzenia"]


def test_counts_and_hours():
    assert format_count(612) == "612" and format_count(5731) == "5 731" and format_count(1234567) == "1 234 567"
    assert format_hours(20) == "20:00–21:00" and format_hours(0) == "00:00–01:00" and format_hours(23) == "23:00–00:00"


def test_period_labels():
    assert period_label(Period.MONTH, date(2026, 11, 15)) == "November 2026"
    assert period_label(Period.YEAR, date(2026, 11, 15)) == "2026"
    assert since_label(date(2025, 3, 2)) == "Since 2 March 2025"


def test_period_labels_are_translated():
    standalone = {"November": "listopad", "March": "marzec"}
    in_a_date = {"November": "listopada", "March": "marca"}
    texts = {"{month} {year}": "{month} {year}", "Since {date}": "Od {date}", "{day} {month} {year}": "{day} {month} {year}"}

    def C_(context, message):
        return (standalone if context == "month" else in_a_date).get(message, message)

    assert period_label(Period.MONTH, date(2026, 11, 1), texts.get, C_) == "Listopad 2026"   # capitalised
    assert since_label(date(2025, 3, 2), texts.get, C_) == "Od 2 marca 2025"

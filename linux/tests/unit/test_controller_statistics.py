"""The controller records listening statistics into statistics.json (sessions while a station plays, songs)."""
from datetime import timedelta, timezone

from fakes import A, B
from minimalistic_radio.controller import Change, ErrorKind, Status
from minimalistic_radio.core.models import ListeningSession, Preferences, SongPlay, Statistics
from minimalistic_radio.core.storage import load_history, load_preferences, load_statistics, save_statistics


def utc(ctl, seconds=0):
    """The controller's clock in UTC, `seconds` after it started."""
    return (ctl.scheduler.start + timedelta(seconds=seconds)).astimezone(timezone.utc)


def saved(ctl):
    return load_statistics(ctl.paths.data / "statistics.json")


def start_playing(ctl, index=0):
    ctl.select(index)
    ctl.play()
    ctl.on_player_started()


def test_a_session_runs_while_the_station_plays(ctl):
    seen = []
    ctl.subscribe(seen.append)
    ctl.select(0)
    ctl.play()
    ctl.scheduler.advance(3)                       # connecting: not listening yet
    ctl.on_player_started()
    assert Change.STATISTICS in seen[-1]
    assert saved(ctl).sessions == [ListeningSession("Alpha", A.url, utc(ctl, 3), utc(ctl, 3))]
    ctl.scheduler.advance(600)
    ctl.stop()
    assert saved(ctl).sessions == [ListeningSession("Alpha", A.url, utc(ctl, 3), utc(ctl, 603))]
    assert ctl.statistics.sessions == saved(ctl).sessions


def test_a_running_session_is_saved_every_five_minutes(ctl):
    start_playing(ctl)
    ctl.scheduler.advance(299)
    assert saved(ctl).sessions[0].end == utc(ctl, 0)
    ctl.scheduler.advance(1)
    assert saved(ctl).sessions[0].end == utc(ctl, 300)
    ctl.scheduler.advance(300)
    assert saved(ctl).sessions[0].end == utc(ctl, 600)
    ctl.stop()
    ctl.scheduler.advance(900)
    assert saved(ctl).sessions[0].end == utc(ctl, 600)   # no more updates once stopped


def test_a_reconnect_within_two_minutes_is_the_same_session(ctl):
    start_playing(ctl)
    ctl.scheduler.advance(120)
    ctl.on_player_error(ErrorKind.NETWORK, "lost")   # ends at once, retries in 2 s
    assert saved(ctl).sessions[0].end == utc(ctl, 120)
    ctl.scheduler.advance(2)
    ctl.on_player_started()
    ctl.scheduler.advance(60)
    ctl.stop()
    assert saved(ctl).sessions == [ListeningSession("Alpha", A.url, utc(ctl, 0), utc(ctl, 182))]


def test_another_station_is_another_session(ctl):
    start_playing(ctl)
    ctl.scheduler.advance(60)
    ctl.select(1)                                  # from the list: connects at once
    ctl.scheduler.advance(1)
    ctl.on_player_started()
    ctl.scheduler.advance(60)
    ctl.stop()
    assert [(s.station, s.start, s.end) for s in saved(ctl).sessions] == [
        ("Alpha", utc(ctl, 0), utc(ctl, 60)), ("Beta", utc(ctl, 61), utc(ctl, 121))]


def test_a_media_key_switch_ends_the_session_at_once(ctl):
    start_playing(ctl)
    ctl.scheduler.advance(60)
    ctl.next_station()
    assert ctl.statistics.sessions[0].end == utc(ctl, 60)


def test_the_sleep_timer_and_errors_end_the_session(ctl):
    ctl.set_sleep_timer(5)
    start_playing(ctl)
    ctl.scheduler.advance(5 * 60 + 1)
    assert ctl.status is Status.STOPPED
    assert saved(ctl).sessions[0].end == utc(ctl, 300)
    start_playing(ctl, 1)
    ctl.scheduler.advance(30)
    ctl.on_player_error(ErrorKind.UNSUPPORTED, "no")
    assert saved(ctl).sessions[1].end == utc(ctl, 331)


def test_songs_are_recorded_with_the_history(ctl):
    start_playing(ctl)
    ctl.on_player_title("Queen - A Kind Of Magic")
    ctl.on_player_title("Queen - A Kind Of Magic")   # a repeat: not in the history, not counted
    ctl.on_player_title("***")                       # not a title
    assert ctl.statistics.songs == [SongPlay("Alpha", "Queen - A Kind Of Magic", utc(ctl))]
    assert ctl.statistics.sessions[0].titles is True
    ctl.stop()
    assert saved(ctl).songs == ctl.statistics.songs and saved(ctl).sessions[0].titles is True


def test_clearing_one_keeps_the_other(ctl):
    start_playing(ctl)
    ctl.on_player_title("Queen - A Kind Of Magic")
    ctl.scheduler.advance(60)
    ctl.stop()
    ctl.clear_history()
    assert ctl.history == [] and len(saved(ctl).songs) == 1
    ctl.on_player_title("ignored while stopped")
    start_playing(ctl)
    ctl.on_player_title("Editors - Shadow")
    seen = []
    ctl.subscribe(seen.append)
    ctl.clear_statistics()
    assert seen == [Change.STATISTICS]
    assert [h.title for h in load_history(ctl.paths.data / "history.json")] == ["Editors - Shadow"]
    assert saved(ctl) == Statistics([ListeningSession("Alpha", A.url, utc(ctl, 60), utc(ctl, 60))], [])


def test_removing_a_station_keeps_its_statistics(ctl):
    start_playing(ctl)
    ctl.scheduler.advance(60)
    ctl.remove_station(0)
    assert [s.station for s in saved(ctl).sessions] == ["Alpha"]


def test_quitting_ends_and_saves_the_session(ctl):
    start_playing(ctl)
    ctl.on_player_title("Queen - A Kind Of Magic")
    ctl.scheduler.advance(100)
    ctl.shutdown()
    assert saved(ctl).sessions[0].end == utc(ctl, 100) and len(saved(ctl).songs) == 1


def test_sleep_ends_the_session_when_the_computer_goes_to_sleep(ctl):
    start_playing(ctl)
    ctl.scheduler.advance(100)
    ctl.suspending()
    first = (utc(ctl, 0), utc(ctl, 100))
    assert (saved(ctl).sessions[0].start, saved(ctl).sessions[0].end) == first
    ctl.scheduler.start += timedelta(hours=1)      # asleep for an hour: the timers didn't run meanwhile
    ctl.scheduler.advance(2)
    ctl.resumed()                                  # awake: the radio connects again
    ctl.on_player_started()
    ctl.scheduler.advance(60)
    ctl.stop()
    assert [(s.start, s.end) for s in saved(ctl).sessions] == [first, (utc(ctl, 102), utc(ctl, 162))]


def test_a_clock_jump_without_notice_starts_a_new_session(ctl):
    start_playing(ctl)
    ctl.scheduler.advance(300)                     # saved at 5 min
    ctl.scheduler.start += timedelta(hours=3)      # the wall clock jumps (a suspend nobody announced)
    ctl.scheduler.advance(300)
    assert [(s.start, s.end) for s in saved(ctl).sessions] == [
        (utc(ctl, 0) - timedelta(hours=3), utc(ctl, 300) - timedelta(hours=3)), (utc(ctl, 600), utc(ctl, 600))]


def test_the_page_brings_the_running_session_up_to_now(ctl):
    start_playing(ctl)
    ctl.scheduler.advance(100)
    ctl.refresh_statistics()
    assert ctl.statistics.sessions[0].end == utc(ctl, 100)


def test_statistics_load_and_a_corrupt_file_is_kept(ctl_factory):
    c = ctl_factory()
    old = Statistics([ListeningSession("Old", "http://old", utc(c, -7200), utc(c, -3600))], [])
    save_statistics(c.paths.data / "statistics.json", old)
    c.start(autostart=True)
    assert c.statistics == old
    bad = ctl_factory()
    bad.paths.data.mkdir(parents=True)
    (bad.paths.data / "statistics.json").write_text("{oops", encoding="utf-8")
    bad.start(autostart=True)
    assert bad.statistics == Statistics()
    assert (bad.paths.data / "statistics.json.bad").read_text(encoding="utf-8") == "{oops"


def test_switched_off_nothing_new_is_recorded(ctl_factory):
    c = ctl_factory(prefs=Preferences(collect_statistics=False))
    c.start(autostart=True)
    start_playing(c)
    c.on_player_title("Queen - A Kind Of Magic")
    c.scheduler.advance(600)
    c.stop()
    assert c.statistics == Statistics() and not (c.paths.data / "statistics.json").exists()
    assert [h.title for h in c.history] == ["Queen - A Kind Of Magic"]   # the history doesn't depend on it


def test_switching_off_ends_the_running_session_and_keeps_the_data(ctl):
    seen = []
    ctl.subscribe(seen.append)
    start_playing(ctl)
    ctl.scheduler.advance(120)
    ctl.set_collect_statistics(False)
    assert Change.PREFERENCES in seen[-1] and Change.STATISTICS in seen[-1]
    assert load_preferences(ctl.paths.config / "preferences.json").collect_statistics is False
    assert saved(ctl).sessions == [ListeningSession("Alpha", A.url, utc(ctl, 0), utc(ctl, 120))]
    ctl.on_player_title("Queen - A Kind Of Magic")
    ctl.scheduler.advance(600)
    assert saved(ctl).sessions[0].end == utc(ctl, 120) and saved(ctl).songs == []
    ctl.set_collect_statistics(True)                 # on again while playing: counts from now
    ctl.scheduler.advance(60)
    ctl.stop()
    assert [(s.start, s.end) for s in saved(ctl).sessions] == [(utc(ctl, 0), utc(ctl, 120)),
                                                             (utc(ctl, 720), utc(ctl, 780))]


def test_saving_failures_keep_the_radio_playing(ctl, monkeypatch):
    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr("minimalistic_radio.controller.save_statistics", fail)
    start_playing(ctl, 1)
    ctl.on_player_title("Queen - A Kind Of Magic")
    ctl.scheduler.advance(600)
    ctl.stop()
    assert ctl.status is Status.STOPPED and ctl.statistics.sessions[0].station == B.name

import hashlib
import json
import os

from fakes import A, B, C
from minimalistic_radio.controller import AddResult, Change, ErrorKind, ImportResult, Status
from minimalistic_radio.core.models import Preferences, Station
from minimalistic_radio.core.storage import load_history, load_preferences, load_stations
from minimalistic_radio.core.titles import RADIO357_NOW_URL

NOT_A_LIST = "This isn't a Minimalistic Radio station list."
ITUNES = {"results": [{"artistName": "Leonard Cohen", "artworkUrl100": "https://is1.example/a/100x100bb.jpg"}]}
BIG_COVER = "https://is1.example/a/600x600bb.jpg"


def playing(ctl, index=0):
    ctl.select(index); ctl.play(); ctl.on_player_started()


def give_up_on_network(ctl):
    """The first station never starts: two retries, then the third NETWORK error stops it."""
    ctl.select(0); ctl.play()
    for d in (2, 3): ctl.on_player_error(ErrorKind.NETWORK, "x"); ctl.scheduler.advance(d)
    ctl.on_player_error(ErrorKind.NETWORK, "x")
    assert ctl.status is Status.STOPPED


def cover_file(ctl, url):
    return ctl.paths.cache / "covers" / (hashlib.sha1(url.encode("utf-8")).hexdigest() + ".jpg")


def saved_names(ctl):
    return [s.name for s in load_stations(ctl.paths.config / "stations.json")[0]]


# ---- Playback and reconnecting ----

def test_start_plays_last_station_unless_autostart(ctl_factory):
    c = ctl_factory(stations=[A, B], prefs=Preferences(last_played=B.url)); c.start(autostart=False)
    assert c.current == 1 and c.player.calls[-1] == ("play", B.url) and c.status is Status.CONNECTING
    c2 = ctl_factory(stations=[A, B], prefs=Preferences(last_played=B.url)); c2.start(autostart=True)
    assert c2.current == 1 and ("play", B.url) not in c2.player.calls
def test_started_saves_last_played_and_status(ctl):
    ctl.select(0); ctl.play(); ctl.on_player_started()
    assert ctl.status is Status.PLAYING and load_preferences(ctl.paths.config / "preferences.json").last_played == A.url
def test_reconnect_backoff_after_playing(ctl):
    ctl.select(0); ctl.play(); ctl.on_player_started()
    delays = []
    for _ in range(10):
        ctl.on_player_error(ErrorKind.NETWORK, "lost"); delays.append(ctl.scheduler.next_delay()); ctl.scheduler.advance(delays[-1])
    assert delays == [2, 3, 5, 10, 15, 30, 30, 30, 30, 30]
    ctl.on_player_error(ErrorKind.NETWORK, "lost")
    assert ctl.status is Status.STOPPED and ctl.message == "lost"
def test_never_played_gets_two_retries(ctl):
    ctl.select(0); ctl.play()
    for d in (2, 3): ctl.on_player_error(ErrorKind.NETWORK, "x"); ctl.scheduler.advance(d)
    ctl.on_player_error(ErrorKind.NETWORK, "x"); assert ctl.status is Status.STOPPED
def test_retry_counter_resets_after_a_minute_of_playing(ctl):
    playing(ctl)
    ctl.on_player_error(ErrorKind.NETWORK, "x"); assert ctl.scheduler.next_delay() == 2      # t = 0
    ctl.scheduler.advance(2); ctl.on_player_started(); ctl.scheduler.advance(61)              # played 61 s
    ctl.on_player_error(ErrorKind.NETWORK, "x"); assert ctl.scheduler.next_delay() == 2
    ctl.scheduler.advance(2); ctl.on_player_started(); ctl.scheduler.advance(59)              # only 59 s: no reset
    ctl.on_player_error(ErrorKind.NETWORK, "x"); assert ctl.scheduler.next_delay() == 3
def test_retrying_message(ctl):
    ctl.select(0); ctl.play(); ctl.on_player_started(); ctl.on_player_error(ErrorKind.NETWORK, "x")
    assert ctl.status is Status.RETRYING and ctl.message == "Connection lost. Retrying in 2 s…"
def test_refused_and_unsupported_stop_at_once(ctl):
    for kind in (ErrorKind.REFUSED, ErrorKind.UNSUPPORTED):
        ctl.select(0); ctl.play(); ctl.on_player_error(kind, "nope")
        assert ctl.status is Status.STOPPED and ctl.scheduler.pending() == 0
def test_eos_retries_then_says_broadcast_ended(ctl):
    playing(ctl)
    for delay in (2, 3, 5, 10, 15, 30, 30, 30, 30, 30):
        ctl.on_player_eos()
        assert ctl.status is Status.RETRYING and ctl.scheduler.next_delay() == delay
        ctl.scheduler.advance(delay)
        assert ctl.status is Status.CONNECTING and ctl.player.calls[-1] == ("play", A.url)
    ctl.on_player_eos()
    assert ctl.status is Status.STOPPED and ctl.message == "The broadcast has ended" and ctl.scheduler.pending() == 0
    # The last failure decides: an error after an end of stream is reported as the error.
    ctl.select(1); ctl.play()
    ctl.on_player_eos(); ctl.scheduler.advance(2); ctl.on_player_eos(); ctl.scheduler.advance(3)
    ctl.on_player_error(ErrorKind.NETWORK, "timeout")
    assert ctl.status is Status.STOPPED and ctl.message == "timeout"
def test_network_return_restarts_after_giving_up_on_network(ctl):
    give_up_on_network(ctl)
    ctl.scheduler.advance(9 * 60)
    ctl.network_available()
    assert ctl.status is Status.CONNECTING and ctl.current == 0 and ctl.player.calls[-1] == ("play", A.url)
    give_up_on_network(ctl)
    ctl.scheduler.advance(10 * 60 + 1)
    calls = list(ctl.player.calls)
    ctl.network_available()
    assert ctl.status is Status.STOPPED and ctl.player.calls == calls
def test_network_return_does_not_restart_after_user_stop(ctl):
    def assert_no_restart():
        calls = list(ctl.player.calls)
        ctl.network_available()
        assert ctl.status is Status.STOPPED and ctl.player.calls == calls

    playing(ctl); ctl.stop(); assert_no_restart()                                          # stopped by the user
    give_up_on_network(ctl); ctl.stop(); assert_no_restart()                               # gave up, then Stop
    ctl.play(); ctl.on_player_error(ErrorKind.REFUSED, "403 Forbidden"); assert_no_restart()  # refused
    playing(ctl); ctl.set_sleep_timer(15); ctl.scheduler.advance(15 * 60)
    assert ctl.message == "Stopped by the sleep timer"; assert_no_restart()                # sleep timer
    playing(ctl)
    for d in (2, 3, 5, 10, 15, 30, 30, 30, 30, 30): ctl.on_player_eos(); ctl.scheduler.advance(d)
    ctl.on_player_eos()
    assert ctl.message == "The broadcast has ended"; assert_no_restart()                   # broadcast ended
    give_up_on_network(ctl); ctl.select(1)                                                 # another station chosen
    calls = list(ctl.player.calls); ctl.network_available()
    assert ctl.status is Status.READY and ctl.player.calls == calls
def test_network_return_skips_backoff_while_retrying(ctl):
    playing(ctl)
    for d in (2, 3, 5, 10, 15): ctl.on_player_error(ErrorKind.NETWORK, "x"); ctl.scheduler.advance(d)
    ctl.on_player_error(ErrorKind.NETWORK, "x")
    assert ctl.status is Status.RETRYING and ctl.scheduler.next_delay() == 30
    ctl.network_available()
    assert ctl.status is Status.CONNECTING and ctl.player.calls[-1] == ("play", A.url) and ctl.scheduler.pending() == 0
def test_resumed_restarts_active_session(ctl):
    playing(ctl); ctl.player.calls.clear()
    ctl.resumed()
    assert ctl.status is Status.CONNECTING and ctl.player.calls[-1] == ("play", A.url)
    ctl.stop(); ctl.player.calls.clear()
    ctl.resumed()
    assert ctl.status is Status.STOPPED and ctl.player.calls == []
    give_up_on_network(ctl); ctl.resumed()                                   # same rule as the network
    assert ctl.status is Status.CONNECTING and ctl.player.calls[-1] == ("play", A.url)
def test_play_keeps_a_station_that_is_already_on(ctl):
    playing(ctl); ctl.player.calls.clear()
    ctl.play()
    assert ctl.status is Status.PLAYING and ctl.player.calls == []
def test_select_switches_only_while_playing(ctl):
    playing(ctl); ctl.select(1)
    assert ctl.current == 1 and ctl.status is Status.CONNECTING and ctl.player.calls[-1] == ("play", B.url)
    ctl.stop(); ctl.player.calls.clear(); ctl.select(2)
    assert ctl.current == 2 and ctl.status is Status.READY and ctl.player.calls == []
def test_toggle_plays_the_first_station_when_none_is_chosen(ctl):
    ctl.toggle(); assert ctl.current == 0 and ctl.status is Status.CONNECTING and ctl.player.calls[-1] == ("play", A.url)
    ctl.toggle(); assert ctl.status is Status.STOPPED and ctl.player.calls[-1] == ("stop",)


# ---- Sleep timer ----

def test_sleep_timer_fades_last_30_seconds_then_stops(ctl):
    ctl.select(0); ctl.play(); ctl.on_player_started(); ctl.set_volume(60); ctl.set_sleep_timer(15)
    ctl.scheduler.advance(15 * 60 - 15); assert ctl.effective_volume == 30
    ctl.scheduler.advance(15); assert ctl.status is Status.STOPPED and ctl.message == "Stopped by the sleep timer" and ctl.sleep_at is None
def test_sleep_timer_off(ctl): ctl.set_sleep_timer(30); ctl.set_sleep_timer(None); assert ctl.sleep_at is None and ctl.scheduler.pending() == 0
def test_sleep_timer_end_cancels_a_network_comeback(ctl):
    playing(ctl); ctl.set_sleep_timer(15)
    ctl.scheduler.advance(10 * 60)                                           # the Wi-Fi drops at minute 10
    for d in (2, 3, 5, 10, 15, 30, 30, 30, 30, 30): ctl.on_player_error(ErrorKind.NETWORK, "lost"); ctl.scheduler.advance(d)
    ctl.on_player_error(ErrorKind.NETWORK, "lost")                           # gives up around minute 13
    assert ctl.status is Status.STOPPED and ctl.gave_up_on_network_at is not None
    ctl.scheduler.advance(5 * 60)                                            # the timer ends at minute 15
    assert ctl.sleep_at is None and ctl.gave_up_on_network_at is None
    calls = list(ctl.player.calls)
    ctl.network_available(); ctl.resumed()                                   # the network is back at minute 18
    assert ctl.status is Status.STOPPED and ctl.player.calls == calls
def test_sleep_timer_restores_volume_when_turned_off(ctl):
    playing(ctl); ctl.set_volume(60); ctl.set_sleep_timer(15)
    assert ctl.sleep_minutes == 15 and ctl.sleep_at == ctl.scheduler.now().replace(minute=15)
    ctl.scheduler.advance(15 * 60 - 6); assert ctl.player.calls[-1] == ("set_volume", 12)
    ctl.set_sleep_timer(None)
    assert ctl.effective_volume == 60 and ctl.player.calls[-1] == ("set_volume", 60) and ctl.sleep_minutes is None


# ---- Titles, covers, history ----

def test_title_goes_to_history_once_and_looks_up_cover(ctl):
    playing(ctl); ctl.on_player_title("Leonard Cohen - Everybody Knows"); ctl.on_player_title("Leonard Cohen - Everybody Knows")
    assert [h.title for h in ctl.history] == ["Leonard Cohen - Everybody Knows"]
    assert ctl.fetch.urls[-1].startswith("https://itunes.apple.com/search?")
def test_radio357_ignores_icy_and_polls_every_10_s(ctl_factory):
    c = ctl_factory(stations=[Station("Radio 357", "https://stream.radio357.pl/")]); c.start(autostart=True)
    c.fetch.responses[RADIO357_NOW_URL] = {"s": "Kult - Arahja"}

    def polls():
        return c.fetch.urls.count(RADIO357_NOW_URL)

    c.select(0); c.play(); c.on_player_started()
    assert polls() == 1 and c.track == "Kult - Arahja"                     # t = 0
    c.on_player_title("Leonard Cohen - Everybody Knows")
    assert c.track == "Kult - Arahja"                                        # ICY titles are ignored
    c.scheduler.advance(10); assert polls() == 2                             # t = 10
    c.fetch.responses[RADIO357_NOW_URL] = None                               # the lookup fails
    c.scheduler.advance(10); assert polls() == 3 and c.track is None         # t = 20
    c.stop(); c.scheduler.advance(60); assert polls() == 3
def test_itunes_cover_is_downloaded_then_shown(ctl):
    playing(ctl); seen = []; ctl.subscribe(seen.append)
    ctl.on_player_title("Leonard Cohen - Everybody Knows"); ctl.fetch.reply(ITUNES)
    assert [d[:2] for d in ctl.fetch.downloads] == [(BIG_COVER, cover_file(ctl, BIG_COVER))] and ctl.cover_path is None
    ctl.fetch.finish_download()
    assert ctl.cover_path == cover_file(ctl, BIG_COVER) and Change.COVER in seen[-1]
def test_cover_lookups_are_cached(ctl):
    playing(ctl)
    ctl.on_player_title("Leonard Cohen - Everybody Knows"); ctl.fetch.reply(ITUNES); ctl.fetch.finish_download()
    ctl.on_player_title("Dżingiel")                                          # no artist: no lookup, no cover
    assert ctl.cover_path is None and len(ctl.fetch.urls) == 1
    ctl.on_player_title("Leonard Cohen - Everybody Knows")                   # known song, picture already saved
    assert len(ctl.fetch.urls) == 1 and ctl.fetch.downloads == [] and ctl.cover_path == cover_file(ctl, BIG_COVER)
    ctl.on_player_title("Queen - A Kind Of Magic"); ctl.fetch.reply(None)   # failed: asked again next time
    ctl.on_player_title("Editors - Shadow"); ctl.fetch.reply({"results": []})  # no cover: remembered
    ctl.on_player_title("Queen - A Kind Of Magic"); ctl.on_player_title("Editors - Shadow")
    assert len(ctl.fetch.urls) == 4 and ctl.fetch.urls[-1].endswith("Queen%20A%20Kind%20Of%20Magic")
def test_late_cover_for_an_earlier_song_is_not_shown(ctl):
    playing(ctl)
    ctl.on_player_title("Leonard Cohen - Everybody Knows"); ctl.on_player_title("Queen - A Kind Of Magic")
    ctl.fetch.reply(ITUNES)
    assert ctl.fetch.downloads == [] and ctl.cover_path is None
def test_stream_artwork_is_used_only_with_a_title(ctl_factory):
    c = ctl_factory(stations=[Station("KIIS", "https://stream.revma.ihrhls.com/zc185")]); c.start(autostart=True); playing(c)
    c.on_player_title('Promo - text="Reklama" song_spot="A" amgArtworkURL="https://img.example/ad.jpg"')
    assert c.track is None and c.fetch.downloads == []
    art = "https://img.example/cover.jpg"
    c.on_player_title(f'Sienna Spiro - text="Great Expectation" song_spot="M" amgArtworkURL="{art}"')
    assert c.track == "Sienna Spiro – Great Expectation" and c.fetch.urls == []
    assert [d[:2] for d in c.fetch.downloads] == [(art, cover_file(c, art))]
    c.fetch.finish_download(); assert c.cover_path == cover_file(c, art)
def test_history_skips_repeats_keeps_100_and_clears(ctl):
    playing(ctl)
    ctl.on_player_title("Queen - A Kind Of Magic"); ctl.on_player_title("***"); ctl.on_player_title("Queen - A Kind Of Magic")
    assert [h.title for h in ctl.history] == ["Queen - A Kind Of Magic"] and ctl.history[0].station == "Alpha"
    assert ctl.history[0].time == ctl.scheduler.now()
    for n in range(105): ctl.on_player_title(f"Artist - Song {n}")
    assert len(ctl.history) == 100 and ctl.history[0].title == "Artist - Song 104"
    assert [h.title for h in load_history(ctl.paths.data / "history.json")] == [h.title for h in ctl.history]
    ctl.clear_history()
    assert ctl.history == [] and load_history(ctl.paths.data / "history.json") == []


# ---- The station list ----

def test_next_previous_wrap_and_flag_switch(ctl):
    ctl.select(0); seen = []; ctl.subscribe(seen.append); ctl.previous_station()
    assert ctl.current == len(ctl.stations) - 1 and any(Change.SWITCHED in c for c in seen)
    ctl.next_station(); assert ctl.current == 0
def test_add_station_rejects_invalid_and_duplicates(ctl):
    assert ctl.add_station(Station("", "http://x/a")) is AddResult.INVALID
    assert ctl.add_station(Station("Copy", A.url.replace("http:", "https:") + "/")) is AddResult.DUPLICATE
    assert ctl.add_station(Station(" New ", "http://new/s")) is AddResult.ADDED and ctl.stations[-1].name == "New"
    assert ctl.add_station(Station("Logo", "http://logo/s", "javascript:alert(1)")) is AddResult.INVALID
    assert saved_names(ctl) == ["Alpha", "Beta", "Gamma", "New"]
def test_update_station_follows_the_playing_station(ctl):
    playing(ctl, 1)
    assert ctl.update_station(1, Station("Beta FM", B.url, B.logo)) is AddResult.ADDED          # renamed only
    assert ctl.station_name == "Beta FM" and ctl.status is Status.PLAYING
    assert ctl.update_station(1, Station("Beta FM", A.url)) is AddResult.DUPLICATE
    assert ctl.update_station(1, Station("Beta FM", "not an address")) is AddResult.INVALID
    assert ctl.update_station(9, Station("Beta FM", "http://b.example/hd")) is AddResult.INVALID
    assert ctl.update_station(1, Station(" Beta HD ", "http://b.example/hd")) is AddResult.ADDED  # new address
    assert ctl.player.calls[-1] == ("play", "http://b.example/hd") and ctl.status is Status.CONNECTING
    assert load_stations(ctl.paths.config / "stations.json")[0][1] == Station("Beta HD", "http://b.example/hd", None)
    assert load_preferences(ctl.paths.config / "preferences.json").last_played == "http://b.example/hd"
def test_move_and_remove_keep_current_station(ctl):
    playing(ctl, 1)                                                          # Beta
    ctl.move_station(1, -1)
    assert [s.name for s in ctl.stations] == ["Beta", "Alpha", "Gamma"] and ctl.current == 0
    assert saved_names(ctl) == ["Beta", "Alpha", "Gamma"]
    ctl.move_station(0, -1); ctl.move_station(2, 1)                          # past either end: nothing
    assert [s.name for s in ctl.stations] == ["Beta", "Alpha", "Gamma"]
    ctl.move_station(0, 1)
    assert [s.name for s in ctl.stations] == ["Alpha", "Beta", "Gamma"] and ctl.current == 1
    ctl.remove_station(0)
    assert [s.name for s in ctl.stations] == ["Beta", "Gamma"] and ctl.current == 0 and ctl.status is Status.PLAYING
    ctl.remove_station(0)                                                    # the playing station
    assert [s.name for s in ctl.stations] == ["Gamma"] and ctl.current == -1 and ctl.status is Status.STOPPED
    assert ctl.player.calls[-1] == ("stop",) and saved_names(ctl) == ["Gamma"]
    assert load_preferences(ctl.paths.config / "preferences.json").last_played is None
def test_import_merges_like_windows(ctl, tmp_path):
    f = tmp_path / "list.json"
    f.write_bytes(("﻿" + json.dumps([
        {"Name": "Alpha again", "Url": A.url.replace("http:", "https:"), "Logo": None},   # known stream
        {"Name": " Delta ", "Url": "http://d.example/live", "Logo": "ftp://d.example/logo.png"},
        {"Name": "Delta copy", "Url": "http://D.example/live/", "Logo": None},           # same stream as Delta
        {"Name": "Echo", "Url": "https://e.example/stream", "Logo": "https://e.example/logo.png"},
        {"Name": "  ", "Url": "http://f.example/live", "Logo": None},
        {"Name": "Local", "Url": "file:///etc/passwd", "Logo": None},
        "junk",
    ])).encode("utf-8"))
    assert ctl.import_stations(f) == ImportResult(2, None)
    assert ctl.stations[3:] == [Station("Delta", "http://d.example/live", None),
                                Station("Echo", "https://e.example/stream", "https://e.example/logo.png")]
    assert load_stations(ctl.paths.config / "stations.json")[0] == ctl.stations
    assert ctl.import_stations(f) == ImportResult(0, None) and len(ctl.stations) == 5   # all already there
    for content in ('{"Name": "Alpha"}', "[{", ""):
        f.write_text(content, "utf-8")
        assert ctl.import_stations(f) == ImportResult(0, NOT_A_LIST)
    assert f.exists()                                                        # never moved aside
    assert ctl.import_stations(tmp_path / "missing.json") == ImportResult(0, NOT_A_LIST)
    assert len(ctl.stations) == 5
def test_export_writes_windows_list_and_reports_failure(ctl, tmp_path):
    out = tmp_path / "export.json"
    assert ctl.export_stations(out) is True
    assert json.loads(out.read_text("utf-8")) == [{"Name": s.name, "Url": s.url, "Logo": s.logo} for s in (A, B, C)]
    folder = tmp_path / "folder.json"; folder.mkdir()
    assert ctl.export_stations(folder) is False
    assert ctl.message is None and ctl.notice is None
def test_save_failures_keep_the_controller_working(ctl, monkeypatch):
    def fail(*args):
        raise OSError("disk full")

    for name in ("save_stations", "save_preferences", "save_history"):
        monkeypatch.setattr(f"minimalistic_radio.controller.{name}", fail)
    seen = []; ctl.subscribe(seen.append)
    assert ctl.add_station(Station("Delta", "http://d.example/live")) is AddResult.ADDED
    assert ctl.stations[-1].name == "Delta" and ctl.notice == "Couldn't save the station list."
    assert any(Change.MESSAGE in c for c in seen)
    playing(ctl); ctl.set_volume(70); ctl.on_player_title("Queen - A Kind Of Magic"); ctl.set_language("en")
    assert ctl.volume == 70 and ctl.history[0].title == "Queen - A Kind Of Magic" and ctl.prefs.language == "en"
    assert ctl.status is Status.PLAYING and ctl.message is None
    assert ctl.update_station(0, Station("Alpha 2", "http://a.example/2")) is AddResult.ADDED   # restarts it
    assert ctl.status is Status.CONNECTING and ctl.notice == "Couldn't save the station list."
    assert ctl.message is None   # a notice is never the status line


# ---- Preferences ----

def test_volume_clamped_saved_and_sent(ctl):
    ctl.set_volume(130); assert ctl.volume == 100 and ctl.player.calls[-1] == ("set_volume", 100)
    assert load_preferences(ctl.paths.config / "preferences.json").volume == 100
def test_unmute_goes_back_to_before_a_quick_slide_to_zero(ctl):
    ctl.set_volume(60); ctl.scheduler.advance(5)
    for level in (40, 1, 0):   # less than a second apart, like a drag to 0
        ctl.set_volume(level); ctl.scheduler.advance(0.1)
    ctl.toggle_mute()
    assert ctl.volume == 60
def test_unknown_language_ignored(ctl): ctl.set_language("de"); assert ctl.prefs.language == "auto"
def test_language_and_station_popup_saved(ctl):
    seen = []; ctl.subscribe(seen.append)
    ctl.set_language("pl"); ctl.set_show_station_popup(False)
    saved = load_preferences(ctl.paths.config / "preferences.json")
    assert saved.language == "pl" and saved.show_station_popup is False and all(Change.PREFERENCES in c for c in seen)
def test_start_loads_files_and_reports_a_corrupt_station_list(ctl_factory):
    c = ctl_factory(prefs=Preferences(volume=55))
    (c.paths.config / "stations.json").write_text("[{", "utf-8")
    c.start(autostart=False)
    assert c.corrupt_stations and c.stations == [] and c.current == -1 and c.status is Status.READY
    assert c.volume == 55 and c.player.calls == [("set_volume", 55)]
def test_start_keeps_the_200_newest_covers(ctl_factory):
    c = ctl_factory()
    covers = c.paths.cache / "covers"; covers.mkdir(parents=True)
    for n in range(205):
        f = covers / f"{n:03}.jpg"; f.write_bytes(b"cover"); os.utime(f, (1_700_000_000 + n, 1_700_000_000 + n))
    c.start(autostart=True)
    assert sorted(p.name for p in covers.iterdir()) == [f"{n:03}.jpg" for n in range(5, 205)]

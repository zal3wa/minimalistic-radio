"""The controller's side of a shared station: finding it on the list, adding it with or without playing it (the
remembered "Play automatically"), and a link to a station that is on the list already."""
from fakes import A, B, C
from minimalistic_radio.controller import AddResult, SharedLink, Status
from minimalistic_radio.core.models import Preferences, Station
from minimalistic_radio.core.share import SharedStation, read_link, share_link
from minimalistic_radio.core.storage import load_preferences, load_stations

DELTA = SharedStation("Delta", "https://d.example/live", "https://d.example/logo.png")


def saved_choice(ctl):
    return load_preferences(ctl.paths.config / "preferences.json").play_shared


def plays(ctl):
    return [call for call in ctl.player.calls if call[0] == "play"]


def test_a_shared_station_is_found_by_its_stream_address(ctl):
    assert ctl.find_station("http://B.EXAMPLE/live/") == 1
    assert ctl.find_station("https://c.example/stream") == 2
    assert ctl.find_station("http://elsewhere.example/live") == -1


def test_add_with_play_appends_and_plays(ctl):
    assert ctl.add_shared(DELTA, play=True) is AddResult.ADDED
    assert ctl.stations[-1] == Station("Delta", "https://d.example/live", "https://d.example/logo.png")
    assert [s.name for s in load_stations(ctl.paths.config / "stations.json")[0]][-1] == "Delta"
    assert ctl.current == 3 and ctl.status is Status.CONNECTING and ctl.player.calls[-1] == ("play", DELTA.url)


def test_add_with_play_while_another_station_plays_switches_to_it(ctl):
    ctl.select(0)
    ctl.play()
    ctl.on_player_started()
    ctl.add_shared(SharedStation("Delta", "https://d.example/live"), play=True)
    assert ctl.current == 3 and ctl.player.calls[-1] == ("play", "https://d.example/live")


def test_add_without_play_keeps_what_plays(ctl):
    ctl.select(0)
    ctl.play()
    ctl.on_player_started()
    before = list(ctl.player.calls)
    assert ctl.add_shared(DELTA, play=False) is AddResult.ADDED
    assert ctl.stations[-1].name == "Delta" and [s.name for s in load_stations(ctl.paths.config / "stations.json")[0]][-1] == "Delta"
    assert ctl.current == 0 and ctl.status is Status.PLAYING and ctl.player.calls == before


def test_add_without_play_starts_nothing(ctl):
    assert ctl.add_shared(DELTA, play=False) is AddResult.ADDED
    assert ctl.stations[-1].name == "Delta"
    assert not ctl.active and ctl.status is Status.READY and plays(ctl) == []


def test_add_remembers_the_choice(ctl):
    assert ctl.prefs.play_shared is True   # checked the first time
    ctl.add_shared(DELTA, play=False)
    assert ctl.prefs.play_shared is False and saved_choice(ctl) is False
    ctl.add_shared(SharedStation("Echo", "https://e.example/live"), play=True)
    assert ctl.prefs.play_shared is True and saved_choice(ctl) is True


def test_a_station_already_added_plays_only_with_play(ctl):
    """The page was still open when the same link had added it (the link opened twice)."""
    assert ctl.add_shared(SharedStation("Another name", "http://b.example/live/"), play=False) is AddResult.DUPLICATE
    assert [s.name for s in ctl.stations] == [A.name, B.name, C.name] and plays(ctl) == []
    assert ctl.add_shared(SharedStation("Another name", "http://b.example/live/"), play=True) is AddResult.DUPLICATE
    assert [s.name for s in ctl.stations] == [A.name, B.name, C.name]
    assert ctl.current == 1 and ctl.player.calls[-1] == ("play", B.url)


def test_a_link_to_a_new_station_asks(ctl):
    assert ctl.open_shared(DELTA) == (SharedLink.ASK, -1)
    assert ctl.open_shared(None) == (SharedLink.ASK, -1)   # a link without a station: its page says so
    assert len(ctl.stations) == 3 and plays(ctl) == []


def test_a_link_to_a_known_station_plays_it_when_play_automatically_is_on(ctl):
    assert ctl.open_shared(SharedStation("Another name", "http://b.example/live/")) == (SharedLink.PLAYED, 1)
    assert [s.name for s in ctl.stations] == [A.name, B.name, C.name]
    assert ctl.current == 1 and ctl.player.calls[-1] == ("play", B.url)
    ctl.on_player_started()
    calls = len(ctl.player.calls)
    ctl.open_shared(SharedStation("B", B.url))   # already playing: nothing restarts
    assert len(ctl.player.calls) == calls and ctl.status is Status.PLAYING


def test_a_link_to_a_known_station_changes_nothing_when_play_automatically_is_off(ctl_factory):
    ctl = ctl_factory(prefs=Preferences(play_shared=False))
    ctl.start(autostart=True)
    ctl.select(0)
    ctl.play()
    ctl.on_player_started()
    before = list(ctl.player.calls)
    assert ctl.open_shared(SharedStation("Another name", "http://C.example/stream")) == (SharedLink.ON_LIST, 2)
    assert ctl.current == 0 and ctl.status is Status.PLAYING and ctl.player.calls == before
    assert saved_choice(ctl) is False


def test_a_station_survives_the_trip_through_its_link(ctl):
    assert read_link(share_link(B)) == SharedStation(B.name, B.url, B.logo)

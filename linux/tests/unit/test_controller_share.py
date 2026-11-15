"""The controller's side of a shared station: finding it on the list, adding and playing it."""
from fakes import A, B, C
from minimalistic_radio.controller import AddResult, Status
from minimalistic_radio.core.models import Station
from minimalistic_radio.core.share import SharedStation, read_link, share_link
from minimalistic_radio.core.storage import load_stations


def test_a_shared_station_is_found_by_its_stream_address(ctl):
    assert ctl.find_station("http://B.EXAMPLE/live/") == 1
    assert ctl.find_station("https://c.example/stream") == 2
    assert ctl.find_station("http://elsewhere.example/live") == -1


def test_add_and_play_appends_and_plays(ctl):
    shared = SharedStation("Delta", "https://d.example/live", "https://d.example/logo.png")
    assert ctl.add_and_play(shared) is AddResult.ADDED
    assert ctl.stations[-1] == Station("Delta", "https://d.example/live", "https://d.example/logo.png")
    assert [s.name for s in load_stations(ctl.paths.config / "stations.json")[0]][-1] == "Delta"
    assert ctl.current == 3 and ctl.status is Status.CONNECTING and ctl.player.calls[-1] == ("play", shared.url)


def test_add_and_play_while_another_station_plays_switches_to_it(ctl):
    ctl.select(0)
    ctl.play()
    ctl.on_player_started()
    ctl.add_and_play(SharedStation("Delta", "https://d.example/live"))
    assert ctl.current == 3 and ctl.player.calls[-1] == ("play", "https://d.example/live")


def test_a_known_station_just_plays(ctl):
    assert ctl.add_and_play(SharedStation("Another name", "http://b.example/live/")) is AddResult.DUPLICATE
    assert [s.name for s in ctl.stations] == [A.name, B.name, C.name]
    assert ctl.current == 1 and ctl.player.calls[-1] == ("play", B.url)
    ctl.on_player_started()
    calls = len(ctl.player.calls)
    ctl.play_station(1)   # already playing: nothing restarts
    assert len(ctl.player.calls) == calls and ctl.status is Status.PLAYING


def test_a_station_survives_the_trip_through_its_link(ctl):
    assert read_link(share_link(B)) == SharedStation(B.name, B.url, B.logo)

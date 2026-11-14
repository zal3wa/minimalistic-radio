import pytest

from minimalistic_radio.core.directory import (
    DirectoryStation, DirectoryUnavailable, parse_results, search, search_url,
    subtitle, to_station)
from minimalistic_radio.core.models import Station
from minimalistic_radio.core.net import NetworkError


def test_search_url():
    assert search_url("de1.api.radio-browser.info", "rock & roll") == \
        "https://de1.api.radio-browser.info/json/stations/search?hidebroken=true&limit=30&order=clickcount&reverse=true&name=rock%20%26%20roll"


def test_parse_prefers_resolved_url_and_dedupes():
    items = [{"name": "Jazz", "url": "http://a/pls", "url_resolved": "http://a/stream", "favicon": "https://a/i.png", "codec": "MP3", "bitrate": 192, "tags": "jazz,smooth jazz,lounge", "country": "Germany"},
             {"name": "Jazz copy", "url": "http://a/stream", "url_resolved": "", "codec": "MP3"},
             {"name": "", "url": "http://b/s"}, {"name": "NoUrl", "url": "nope"}]
    found = parse_results(items)
    assert [s.name for s in found] == ["Jazz"] and found[0].url == "http://a/stream"


def test_subtitle_matches_windows_format():
    e = DirectoryStation("X", "Germany ", "http://a/s", None, "mp3", 192, "jazz, smooth jazz ,lounge")
    assert subtitle(e) == "Germany · MP3 192 kbps · jazz, smooth jazz"
    assert subtitle(DirectoryStation("X", "", "http://a/s", None, "UNKNOWN", 0, "")) == ""


def test_to_station_drops_bad_logo():
    assert to_station(DirectoryStation(" Jazz ", "", "http://a/s", "data:x", "MP3", 0, "")) == Station("Jazz", "http://a/s", None)


def test_search_falls_back_to_second_server():
    calls = []

    def fetch(url):
        calls.append(url)
        if "de1" in url:
            raise NetworkError("down")
        return [{"name": "A", "url": "http://a/s"}]
    assert [s.name for s in search("a", fetch)] == ["A"] and len(calls) == 2


def test_search_all_servers_down():
    def fetch(url):
        raise NetworkError("down")
    with pytest.raises(DirectoryUnavailable):
        search("a", fetch)

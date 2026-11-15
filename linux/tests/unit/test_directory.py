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


# ---- Suggestions ----

from minimalistic_radio.core.directory import (  # noqa: E402
    RECOMMENDED_IDS, clean_popular, country_for, country_from_locale, looks_like_spam, name_key, popular_url,
    recommended_url, suggestions)


def _entry(name, url=None, id=""):
    return DirectoryStation(name, "", url or f"http://x/{name}", None, "MP3", 128, "", id)


@pytest.mark.parametrize("name", ["-- # TOP 100 CHARTS ---", "0R - LO-FI || LoFi, Chill, Study, Hip Hop, Relax",
                                  "*Chill", "Lofi || Chill", "Hits #1", "Top ***", "a, b, c, d, e"])
def test_spam(name):
    assert looks_like_spam(name)


@pytest.mark.parametrize("name", ["RMF FM", "102.7 KIIS FM Los Angeles", "Radio ZET Chilli", "Rock, Pop, Jazz, Blues"])
def test_not_spam(name):
    assert not looks_like_spam(name)


def test_name_key():
    assert name_key("Radio RMF FM") == name_key("RMF FM") == "rmffm"
    assert name_key("Radio") == ""


def test_clean_popular_rules():
    names = lambda items: [e.name for e in items]
    assert names(clean_popular([_entry(n) for n in ["RMF FM", "Radio RMF FM", "Radio ZET", "Radio ZET Chilli"]], [])) \
        == ["RMF FM", "Radio ZET", "Radio ZET Chilli"]
    assert names(clean_popular([_entry("Radio", "http://a"), _entry("Radio", "http://b")], [])) == ["Radio", "Radio"]
    assert names(clean_popular([_entry("A", "http://s"), _entry("B", "http://s/")], [])) == ["A"]
    assert names(clean_popular([_entry("KEXP"), _entry("Other", "http://r"), _entry("Third")],
                               [_entry("Radio KEXP"), _entry("Z", "http://r")])) == ["Third"]
    assert len(clean_popular([_entry(f"S{i}") for i in range(30)], [])) == 15


@pytest.mark.parametrize("language,system,expected", [
    ("pl", "US", "PL"), ("pl", None, "PL"), ("es", "MX", "MX"), ("es", "US", "ES"), ("en", "US", "US"),
    ("en", None, None), ("de", "AT", "AT"), ("pt", "BR", "BR")])
def test_country_for(language, system, expected):
    assert country_for(language, system) == expected


def test_country_from_locale():
    assert country_from_locale({"LANG": "pl_PL.UTF-8"}) == "PL"
    assert country_from_locale({"LC_ALL": "en_US", "LANG": "pl_PL.UTF-8"}) == "US"
    assert country_from_locale({"LANG": "en_US.UTF-8", "LC_TIME": "pl_PL.UTF-8"}) == "PL"   # the "Formats" region
    assert country_from_locale({"LANG": "C"}) is None and country_from_locale({"LANG": "POSIX"}) is None
    assert country_from_locale({}) is None


def test_suggestion_urls():
    assert recommended_url("s").startswith("https://s/json/stations/byuuid?uuids=2e6fabb2")
    assert popular_url("s", "PL").endswith("limit=40&countrycode=PL")
    assert "countrycode" not in popular_url("s", None)


def _suggest_fetch(popular_ok=True, recommended_ok=True):
    def fetch(url):
        if "byuuid" in url:
            if not recommended_ok:
                raise NetworkError("x")
            return [{"name": "K", "url": "http://k", "stationuuid": RECOMMENDED_IDS[3]},
                    {"name": "Dead", "url": "http://d", "stationuuid": RECOMMENDED_IDS[0], "lastcheckok": 0},
                    {"name": "P", "url": "http://p", "stationuuid": RECOMMENDED_IDS[2]}]
        if not popular_ok:
            raise NetworkError("x")
        return [{"name": "Pop", "url": "http://pop"}, {"name": "Down", "url": "http://dn", "lastcheckok": 0}]
    return fetch


def test_suggestions_order_and_filters():
    recommended, popular = suggestions("PL", _suggest_fetch())
    assert [e.name for e in recommended] == ["P", "K"] and [e.name for e in popular] == ["Pop"]


def test_suggestions_popular_failure_and_total_failure():
    recommended, popular = suggestions(None, _suggest_fetch(popular_ok=False))
    assert len(recommended) == 2 and popular == []
    with pytest.raises(DirectoryUnavailable):
        suggestions(None, _suggest_fetch(popular_ok=False, recommended_ok=False))


# ---- Banned stations (data/banned-stations.json, shared with Windows) ----

from pathlib import Path  # noqa: E402

from minimalistic_radio.core.directory import is_hidden, load_banned  # noqa: E402

REPO_LIST = Path(__file__).resolve().parents[3] / "data" / "banned-stations.json"
BANS = load_banned(REPO_LIST)


def _banned(name, code, url, uuid=""):
    return DirectoryStation(name, "", url, None, "MP3", 128, "", uuid, True, code)


def test_banned_station_rules():
    assert is_hidden(_banned("Radio Republika", "PL", "https://ssl-1.radiotvrepublika.pl:12698/stream"), BANS)
    assert is_hidden(_banned("Republika", "PL", "http://example.com/live"), BANS)
    assert is_hidden(_banned("X", "DE", "http://example.com/x", "F837704E-40DF-4302-B546-C8401348E51C"), BANS)
    assert is_hidden(_banned("X", "", "http://a.b.tvrepublika.pl/x"), BANS)
    assert not is_hidden(_banned("Dominikánská Republika", "CZ", "http://example.com/a"), BANS)
    assert not is_hidden(_banned("Republika ni Juan 87.5", "PH", "http://example.com/b"), BANS)


def test_banned_station_filtered_from_results_and_popular():
    item = {"name": "Radio Republika", "countrycode": "PL", "url": "https://ssl-1.radiotvrepublika.pl:12698/stream"}
    other = {"name": "Dominikánská Republika", "countrycode": "CZ", "url": "http://example.com/a"}
    assert [e.name for e in parse_results([item, other], bans=BANS)] == ["Dominikánská Republika"]
    hidden = _banned("Radio Republika", "PL", "https://ssl-1.radiotvrepublika.pl:12698/stream")
    other_entry = _banned("Other", "PL", "http://o/x")
    assert clean_popular([hidden, other_entry], [], bans=BANS) == [other_entry]


def test_malformed_or_missing_ban_file_hides_nothing(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    entry = _banned("Radio Republika", "PL", "https://ssl-1.radiotvrepublika.pl/stream")
    assert not is_hidden(entry, load_banned(bad))
    assert not is_hidden(entry, load_banned(tmp_path / "missing.json"))


def test_packaged_copy_matches_the_repo_list():
    assert (REPO_LIST.parent.parent / "linux" / "data" / "banned-stations.json").read_bytes() == REPO_LIST.read_bytes()

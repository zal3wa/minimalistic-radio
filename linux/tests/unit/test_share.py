"""Share links (core/share.py): building, reading, checking, and matching a shared station with the list."""
from urllib.parse import quote

import pytest

from minimalistic_radio.core.models import Station
from minimalistic_radio.core.share import (
    APP_LINK, MAX_ADDRESS, MAX_NAME, WEB_LINK, SharedStation, address_text, is_share_link, read_link, share_link,
)
from minimalistic_radio.core.streams import same_stream

HARD = Station("Antyradio Hard", "https://an05.cdn.eurozet.pl/ANTHAR.mp3")


def test_the_link_of_the_spec():
    assert share_link(HARD) == "https://minimalistic-radio.github.io/#n=Antyradio+Hard&u=https%3A%2F%2Fan05.cdn.eurozet.pl%2FANTHAR.mp3"
    assert WEB_LINK == "https://minimalistic-radio.github.io/#" and APP_LINK == "minimalistic-radio://add?"


def test_round_trip_with_a_logo_and_odd_characters():
    station = Station("Radio Nowy Świat & friends + 100% \"jazz\"", "https://stream.example/live?x=1&y=2#frag",
                      "https://logo.example/a b.png")
    link = share_link(station)
    assert "&l=" in link
    assert read_link(link) == SharedStation(station.name, station.url, station.logo)


def test_the_app_link_carries_the_same_query():
    web = share_link(HARD)
    app = APP_LINK + web[len(WEB_LINK):]
    assert read_link(app) == read_link(web) == SharedStation(HARD.name, HARD.url, None)


def test_plus_and_percent_twenty_are_spaces():
    assert read_link(WEB_LINK + "n=Radio%20357&u=https%3A%2F%2F357.example%2F").name == "Radio 357"
    assert read_link(WEB_LINK + "n=Radio+357&u=https://357.example/").name == "Radio 357"
    assert read_link(WEB_LINK + "n=1%2B1&u=https://357.example/").name == "1+1"


def test_an_http_or_https_logo_goes_into_the_link():
    favicon = Station("My Radios", "http://www.my-radios.com/live", "http://www.my-radios.com/favicon.ico")
    assert "&l=http%3A%2F%2Fwww.my-radios.com%2Ffavicon.ico" in share_link(favicon)
    assert read_link(share_link(favicon)).logo == "http://www.my-radios.com/favicon.ico"
    assert "l=" in share_link(Station("A", "http://a.example/", "https://a.example/logo.png"))
    for logo in ("https://a.example/" + "x" * MAX_ADDRESS, "ftp://a.example/logo.png", "javascript:alert(1)",
                 "logo.png", "", None):
        assert "l=" not in share_link(Station("A", "http://a.example/", logo)), logo


@pytest.mark.parametrize("query", [
    "",                                                  # nothing
    "u=https://a.example/",                              # no name
    "n=A",                                               # no address
    "n=+++&u=https://a.example/",                        # a name of spaces
    "n=%01%02&u=https://a.example/",                     # only control characters
    "n=A&u=ftp://a.example/",                            # not http(s)
    "n=A&u=a.example/live",                              # not absolute
    "n=A&u=javascript:alert(1)",
    "n=A&u=https://" + "a" * MAX_ADDRESS,                # too long
    "n=A&u=",
])
def test_links_without_a_station(query):
    assert is_share_link(WEB_LINK + query) and read_link(WEB_LINK + query) is None
    assert is_share_link(APP_LINK + query) and read_link(APP_LINK + query) is None


def test_the_name_is_cleaned_and_cut():
    shared = read_link(WEB_LINK + "n=%20%20Radio%0A%09357%20&u=https://357.example/")
    assert shared.name == "Radio357"
    long = read_link(WEB_LINK + "n=" + "x" * 300 + "&u=https://357.example/")
    assert long.name == "x" * MAX_NAME


def test_an_http_or_https_logo_is_kept():
    for logo in ("http://logo.example/a.png", "https://logo.example/a.png", "HTTP://LOGO.example/favicon.ico"):
        shared = read_link(WEB_LINK + "n=A&u=https://a.example/&l=" + quote(logo, safe=""))
        assert shared == SharedStation("A", "https://a.example/", logo), logo


def test_a_bad_logo_is_dropped_silently():
    for logo in ("javascript%3Aalert(1)", "ftp%3A%2F%2Flogo.example%2Fa.png", "logo.example%2Fa.png", "not-a-url",
                 "%2Fa.png", "https%3A%2F%2F" + "a" * MAX_ADDRESS, "http%3A%2F%2F" + "a" * MAX_ADDRESS, ""):
        shared = read_link(WEB_LINK + "n=A&u=https://a.example/&l=" + logo)
        assert shared == SharedStation("A", "https://a.example/", None), logo


def test_unknown_keys_are_ignored_and_the_first_value_counts():
    shared = read_link(WEB_LINK + "v=2&n=A&x=y&u=https://a.example/&n=B")
    assert shared == SharedStation("A", "https://a.example/", None)


def test_which_texts_are_share_links():
    for text in (WEB_LINK + "n=A", "  " + share_link(HARD) + "\n", "https://minimalistic-radio.github.io#n=A",
                 "https://Minimalistic-Radio.GitHub.io/#n=A", "https://minimalistic-radio.github.io/index.html#n=A",
                 APP_LINK + "n=A", "Minimalistic-Radio://add?n=A", "minimalistic-radio://add/?n=A",
                 "https://minimalistic-radio.github.io/"):
        assert is_share_link(text), text
    for text in ("jazz", "https://an05.cdn.eurozet.pl/ANTHAR.mp3", "https://minimalistic-radio.github.io.evil.example/#n=A",
                 "https://evil.example/#n=A&u=https://a.example/", "minimalistic-radio://remove?n=A",
                 "http://minimalistic-radio.github.io/#n=A", ""):
        assert not is_share_link(text), text
    assert read_link("https://minimalistic-radio.github.io/") is None
    assert read_link("jazz") is None


def test_the_address_is_shown_without_its_scheme():
    assert address_text("https://an05.cdn.eurozet.pl/ANTHAR.mp3") == "an05.cdn.eurozet.pl/ANTHAR.mp3"
    assert address_text("http://31.192.216.8/RMFCLASSIC48") == "31.192.216.8/RMFCLASSIC48"


def test_matching_a_shared_station_with_the_list():
    url = "https://an05.cdn.eurozet.pl/ANTHAR.mp3"
    assert same_stream(url, "  https://an05.cdn.eurozet.pl/ANTHAR.mp3  ")      # trimmed
    assert same_stream(url, "HTTPS://AN05.CDN.EUROZET.PL/ANTHAR.mp3")           # scheme and host in any case
    assert same_stream("https://357.example/live", "https://357.example/live/")   # one trailing slash
    assert not same_stream(url, "https://an05.cdn.eurozet.pl/anthar.mp3")       # the path exactly
    assert not same_stream("https://357.example/live?a=1", "https://357.example/live?a=2")


def test_the_name_loses_bidirectional_characters():
    shared = read_link(WEB_LINK + "n=Radio%E2%80%AE%20357%E2%81%A6&u=https://357.example/")
    assert shared.name == "Radio 357"

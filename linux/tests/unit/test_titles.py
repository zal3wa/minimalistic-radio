import pytest

from minimalistic_radio.core.titles import (
    artwork_from_raw, parse_title, radio357_title, split_track, station_kind)


@pytest.mark.parametrize("raw,kind,expected", [
    ('Sienna Spiro - text="Great Expectation" song_spot="M"', "iheart", "Sienna Spiro – Great Expectation"),
    ('title="The Way",artist="ARIANA GRANDE / MAC MILLER",url="song_spot=\\"F\\""', "iheart", "ARIANA GRANDE / MAC MILLER – The Way"),
    ('title="",artist="",url=""', "iheart", None),
    ("Radio 357 - Najlepszy radiowy adres na świecie!", "radio357", None),
    ("The Streets - Blinded by the Lights", "generic", "The Streets - Blinded by the Lights"),
    ('Promo - text="Reklama" song_spot="A"', "iheart", None),
    ('- text="Spot Block End" amgTrackId="9876543" length="00:00:00"', "iheart", None),
    ("Simon &amp; Garfunkel - Mrs. Robinson", "generic", "Simon & Garfunkel - Mrs. Robinson"),
    ("Radio Nowy Świat - Pion i poziom", "generic", None),
    (" --- ", "generic", None), (None, "generic", None)])
def test_parse_title(raw, kind, expected): assert parse_title(raw, kind) == expected
def test_long_title_cut_at_240(): assert parse_title("A" * 300, "generic") == "A" * 240 + "…"
def test_station_kind():
    assert station_kind("https://stream.radio357.pl/?s=www") == "radio357"
    assert station_kind("http://stream.revma.ihrhls.com/zc185") == "iheart"
    assert station_kind("http://rs6.rmf.pl/rmf_fm") == "generic"
def test_split_track():
    assert split_track("Leonard Cohen - Everybody Knows") == ("Leonard Cohen", "Everybody Knows")
    assert split_track("Dżingiel") == (None, "Dżingiel")
    assert split_track("A – B") == ("A", "B")
def test_artwork_from_raw():
    assert artwork_from_raw('x amgArtworkURL="https://i.iheart.com/a.jpg" y') == "https://i.iheart.com/a.jpg"
    assert artwork_from_raw('amgArtworkURL="javascript:x"') is None
def test_radio357_title(): assert radio357_title({"s": "Kult - Arahja"}) == "Kult - Arahja" and radio357_title([]) is None

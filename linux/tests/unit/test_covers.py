from minimalistic_radio.core.covers import CoverCache, itunes_search_url, pick_cover, same_artist


def test_itunes_url():
    assert itunes_search_url("Leonard Cohen - Everybody Knows") == "https://itunes.apple.com/search?media=music&entity=song&limit=5&term=Leonard%20Cohen%20Everybody%20Knows"
    assert itunes_search_url("Dżingiel") is None
def test_same_artist():
    assert same_artist("ARIANA GRANDE / MAC MILLER", "Ariana Grande")
    assert not same_artist("Queen", "Abba") and not same_artist("A", "A")
def test_pick_cover_needs_matching_artist():
    payload = {"results": [{"artistName": "Someone Else", "artworkUrl100": "https://x/100x100bb.jpg"},
                           {"artistName": "Leonard Cohen", "artworkUrl100": "https://y/100x100bb.jpg"}]}
    assert pick_cover("Leonard Cohen", payload) == "https://y/600x600bb.jpg"
    assert pick_cover("Leonard Cohen", {"results": []}) is None
def test_pick_cover_takes_only_http_or_https_artwork():
    def answer(*pictures):
        return {"results": [{"artistName": "Leonard Cohen", "artworkUrl100": p} for p in pictures]}
    for bad in ("ftp://x/100x100bb.jpg", "file:///etc/100x100bb.jpg", "javascript:alert(1)", "//x/100x100bb.jpg",
                "data:image/png;base64,AAAA", ""):
        assert pick_cover("Leonard Cohen", answer(bad)) is None
    assert pick_cover("Leonard Cohen", answer("ftp://x/a.jpg", "http://y/100x100bb.jpg")) == "http://y/600x600bb.jpg"
def test_cover_lookup_failure_not_cached():
    c = CoverCache(); assert c.get("A - B") == (False, None)
    c.put("A - B", None); assert c.get("A - B") == (True, None)   # "no cover" is cached; a network failure is simply never put

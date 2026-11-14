from minimalistic_radio.core.streams import is_web_url, same_stream, stream_key


def test_stream_key_ignores_scheme_case_default_port_and_trailing_slash():
    assert stream_key("HTTP://Example.COM:80/live/") == "example.com/live"
    assert stream_key("https://example.com:443/live") == "example.com/live"
    assert stream_key("http://example.com:8000/live") == "example.com:8000/live"
    assert stream_key("https://example.com/live?x=1") == "example.com/live?x=1"
    assert stream_key("  not a url ") == "not a url"


def test_same_stream():
    assert same_stream("http://a.com/s", "https://A.com/s/")
    assert not same_stream("http://a.com/s", "http://a.com/t")


def test_is_web_url():
    assert is_web_url("http://x.com/a") and is_web_url("https://x.com")
    for bad in (None, "", "example.com", "ftp://x.com", "https://user:pw@x.com/", "file:///tmp/x"):
        assert not is_web_url(bad)

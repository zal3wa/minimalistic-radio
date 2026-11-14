from minimalistic_radio.audio.playlists import first_stream, is_hls, is_playlist_type, is_playlist_url


def test_pls_first_file():
    assert first_stream("[playlist]\nFile1=http://a/s\n", "http://x/p.pls") == "http://a/s"


def test_pls_lowest_number_wins():
    text = "[playlist]\r\nNumberOfEntries=2\r\nFile2=http://b/s\r\nTitle2=B\r\nFile1=http://a/s\r\nVersion=2\r\n"
    assert first_stream(text, "http://x/p.pls") == "http://a/s"


def test_m3u_skips_comments():
    text = "#EXTM3U\n#EXTINF:-1,Radio\n\nhttp://a/s\nhttp://b/s\n"
    assert first_stream(text, "http://x/p.m3u") == "http://a/s"


def test_m3u_returns_first_http_line():
    text = "rtsp://a/s\nC:\\Music\\song.mp3\nhttps://b/s\n"
    assert first_stream(text, "http://x/p.m3u") == "https://b/s"


def test_relative_entries_resolve_against_base_url():
    assert first_stream("live/stream.mp3\n", "http://x/dir/p.m3u") == "http://x/dir/live/stream.mp3"
    assert first_stream("[playlist]\nFile1=/live\n", "https://x/dir/p.pls") == "https://x/live"


def test_byte_order_mark_is_ignored():
    assert first_stream("﻿http://a/s\n", "http://x/p.m3u") == "http://a/s"
    assert first_stream("﻿[playlist]\nFile1=http://a/s\n", "http://x/p.pls") == "http://a/s"


def test_empty_playlist_is_none():
    for text in ("", "\n\n", "#EXTM3U\n", "[playlist]\nNumberOfEntries=0\n", "ftp://a/s\n"):
        assert first_stream(text, "http://x/p.m3u") is None


def test_playlist_url_by_path():
    assert is_playlist_url("http://x/a.pls") and is_playlist_url("https://x/A.M3U?id=1")
    for url in ("http://x/a.m3u8", "http://x/a.mp3", "http://x/stream", "http://x/?f=a.pls", ""):
        assert not is_playlist_url(url)


def test_playlist_content_types():
    for value in ("audio/x-scpls", "Audio/X-MPEGURL; charset=utf-8", "audio/mpegurl"):
        assert is_playlist_type(value)
    for value in ("audio/mpeg", "application/vnd.apple.mpegurl", "audio/aacp", "", None):
        assert not is_playlist_type(value)


def test_hls_is_not_a_station_playlist():
    assert is_hls("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:10\n#EXTINF:10,\nseg1.aac\n")
    assert is_hls("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=64000\nlow/index.m3u8\n")
    assert not is_hls("#EXTM3U\n#EXTINF:-1,Radio\nhttp://a/s\n")

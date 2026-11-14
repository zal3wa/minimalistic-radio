"""Station playlists (.pls, .m3u): playbin can't play them, so the player plays their first stream.

Pure standard library, so the rules are unit-tested anywhere.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

from ..core.streams import is_web_url

PLAYLIST_TYPES = ("audio/x-scpls", "audio/x-mpegurl", "audio/mpegurl")
_PLS_ENTRY = re.compile(r"file(\d+)\s*=\s*(.*)", re.IGNORECASE)


def is_playlist_url(url: str) -> bool:
    """The address names a playlist file. .m3u8 is HLS, which playbin plays itself."""
    try:
        path = urlsplit(url).path.lower()
    except ValueError:
        return False
    return path.endswith((".pls", ".m3u"))


def is_playlist_type(content_type: str | None) -> bool:
    """The server's Content-Type says playlist (parameters such as charset are ignored)."""
    return (content_type or "").split(";")[0].strip().lower() in PLAYLIST_TYPES


def is_hls(text: str) -> bool:
    """An HLS playlist (served as audio/mpegurl, which Apple allows): playbin plays it, not its first line."""
    return "#EXT-X-" in text


def first_stream(text: str, base_url: str) -> str | None:
    """The first http(s) stream of a .pls or .m3u playlist, relative entries resolved against `base_url`."""
    lines = [line.strip() for line in text.lstrip("﻿").splitlines()]
    entries = [(int(m.group(1)), m.group(2).strip()) for m in map(_PLS_ENTRY.fullmatch, lines) if m]
    if entries or any(line.lower() == "[playlist]" for line in lines):
        candidates = [entry for _, entry in sorted(entries, key=lambda e: e[0])]
    else:
        candidates = [line for line in lines if line and not line.startswith("#")]
    for entry in candidates:
        url = urljoin(base_url, entry)
        if is_web_url(url):
            return url
    return None

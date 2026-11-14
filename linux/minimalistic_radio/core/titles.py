"""Song titles from stream metadata (a port of the Windows ParseTrack)."""
from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urlsplit

from .streams import is_web_url

RADIO357_NOW_URL = "https://stream.radio357.pl/now/playing.json"

_RICH = re.compile(r'^title="(?P<title>[^"]*)",artist="(?P<artist>[^"]*)"')
_ARTWORK = re.compile(r'amgArtworkURL="([^"]+)"')
_TITLE_FIELD = ' - text="'


def station_kind(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return "generic"
    if host == "stream.revma.ihrhls.com":
        return "iheart"
    if host == "stream.radio357.pl":
        return "radio357"
    return "generic"


def _has(text: str, part: str) -> bool:
    return part.lower() in text.lower()


def parse_title(raw: str | None, kind: str) -> str | None:
    if raw is None or not raw.strip():
        return None
    value = html.unescape(raw).strip()
    if kind == "iheart":
        rich = _RICH.match(value)
        if rich:
            title, artist = rich["title"].strip(), rich["artist"].strip()
            if not title or not artist:
                return None
            value = artist + " – " + title
        elif _has(value, "song_spot=") or _has(value, 'text="'):
            separator = value.lower().find(_TITLE_FIELD)
            if separator <= 0 or not _has(value, 'song_spot="M"'):
                return None
            start = separator + len(_TITLE_FIELD)
            end = value.lower().find('" song_spot=', start)
            if end <= start:
                return None
            value = value[:separator] + " – " + value[start:end]
    lowered = value.lower()
    if (lowered.startswith("radio 357")
            or lowered.startswith("radio nowy świat - pion i poziom")
            or not any(c.isalnum() for c in value)):
        return None
    return value[:240] + "…" if len(value) > 240 else value


def artwork_from_raw(raw: str | None) -> str | None:
    match = _ARTWORK.search(raw or "")
    if match and is_web_url(match.group(1)):
        return match.group(1)
    return None


def split_track(track: str | None) -> tuple[str | None, str | None]:
    """'Artist – Title' -> (artist, title); without a separator the whole text is the title."""
    if not track:
        return None, track
    for separator in (" – ", " — ", " - "):
        index = track.find(separator)
        if index > 0 and index + len(separator) < len(track):
            return track[:index].strip(), track[index + len(separator):].strip()
    return None, track


def radio357_title(payload: Any) -> str | None:
    if isinstance(payload, dict) and isinstance(payload.get("s"), str):
        return payload["s"]
    return None

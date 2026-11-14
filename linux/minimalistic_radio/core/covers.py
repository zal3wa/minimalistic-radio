"""Album art lookup helpers (a port of the Windows Covers, without the HTTP)."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from .titles import split_track


def itunes_search_url(track: str) -> str | None:
    artist, title = split_track(track)
    if artist is None:
        return None
    term = quote(f"{artist} {title}", safe="")
    return f"https://itunes.apple.com/search?media=music&entity=song&limit=5&term={term}"


def _clean(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum())


def same_artist(wanted: str, found: str | None) -> bool:
    if not found:
        return False
    # "ARIANA GRANDE / MAC MILLER": the first artist is enough.
    first = _clean(re.split(r"[/,&(;]", wanted, maxsplit=1)[0])
    other = _clean(found)
    return len(first) > 1 and len(other) > 1 and (first in other or other in first)


def pick_cover(artist: str, payload: Any) -> str | None:
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return None
    for item in results:
        if not isinstance(item, dict):
            continue
        name, picture = item.get("artistName"), item.get("artworkUrl100")
        if isinstance(picture, str) and isinstance(name, str) and same_artist(artist, name):
            return picture.replace("100x100bb", "600x600bb")
    return None


class CoverCache:
    """Remembers lookups, including 'no cover'. A failed lookup is simply never put."""

    def __init__(self) -> None:
        self._known: dict[str, str | None] = {}

    def get(self, track: str) -> tuple[bool, str | None]:
        if track in self._known:
            return True, self._known[track]
        return False, None

    def put(self, track: str, url: str | None) -> None:
        self._known[track] = url

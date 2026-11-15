"""Share links: a station as a link to the radio's page (https://minimalistic-radio.github.io/#n=…&u=…&l=…), and the
app link the page opens (minimalistic-radio://add?…, the same query). See docs/superpowers/specs/2026-11-15-share-
station-design.md.

The query is form-encoded, as the page's URLSearchParams writes it: n = name, u = stream address, l = logo address
(optional). Unknown keys are ignored. Reading checks everything the way the page does: a link never adds or plays
anything by itself. The part after # never reaches a server.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit

from .models import Station
from .streams import is_web_url

WEB_LINK = "https://minimalistic-radio.github.io/#"
APP_LINK = "minimalistic-radio://add?"
APP_SCHEME = "minimalistic-radio"
_PAGE_HOST = "minimalistic-radio.github.io"
MAX_ADDRESS = 2048
MAX_NAME = 100


@dataclass(frozen=True)
class SharedStation:
    name: str
    url: str
    logo: str | None = None


def _https(value: str | None) -> bool:
    return bool(value) and len(value) <= MAX_ADDRESS and is_web_url(value) and urlsplit(value).scheme.lower() == "https"


def share_link(station: Station) -> str:
    """The web link for a station (the logo only when it is one the link may carry)."""
    fields = [("n", station.name), ("u", station.url)]
    if _https(station.logo):
        fields.append(("l", station.logo))
    return WEB_LINK + urlencode(fields)


def _query(text: str) -> str | None:
    """The query of a web or app link, None if `text` is neither."""
    try:
        parts = urlsplit(text.strip())
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme == APP_SCHEME:
        return parts.query if parts.netloc.lower() == "add" and parts.path in ("", "/") else None
    if scheme == "https" and (parts.hostname or "") == _PAGE_HOST and port is None \
            and parts.path in ("", "/", "/index.html"):
        return parts.fragment
    return None


def is_share_link(text: str | None) -> bool:
    """A web or app link, with a station in it or not (pasted into the add-station box, or given on the command
    line)."""
    return bool(text) and _query(text) is not None


def _clean_name(value: str) -> str:
    kept = "".join(c for c in value if unicodedata.category(c) != "Cc").strip()
    return kept[:MAX_NAME].rstrip()


def read_link(text: str | None) -> SharedStation | None:
    """The station in a share link; None if it isn't a share link or holds no valid station."""
    query = _query(text) if text else None
    if query is None:
        return None
    fields: dict[str, str] = {}
    for key, value in parse_qsl(query, keep_blank_values=True):
        fields.setdefault(key, value)   # the first one counts, as URLSearchParams.get does
    url = fields.get("u", "").strip()
    name = _clean_name(fields.get("n", ""))
    if not name or len(url) > MAX_ADDRESS or not is_web_url(url):
        return None
    logo = fields.get("l", "").strip()
    return SharedStation(name, url, logo if _https(logo) else None)


def address_text(url: str) -> str:
    """The stream address as the Shared station page shows it: without http:// or https://."""
    for scheme in ("https://", "http://"):
        if url.lower().startswith(scheme):
            return url[len(scheme):]
    return url

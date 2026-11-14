"""radio-browser station search, mirroring Storage.Search in src/Services/Storage.cs."""
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote

from .models import Station
from .net import NetworkError, fetch_json
from .streams import is_web_url

SERVERS = ("de1.api.radio-browser.info", "nl1.api.radio-browser.info")
_LIMIT = 30


@dataclass
class DirectoryStation:
    name: str
    country: str
    url: str
    logo: str | None
    codec: str
    bitrate: int
    tags: str


class DirectoryUnavailable(Exception):
    pass


def search_url(server: str, query: str) -> str:
    return (f"https://{server}/json/stations/search?hidebroken=true&limit={_LIMIT}"
            f"&order=clickcount&reverse=true&name={quote(query, safe='')}")


def _text(item: dict, key: str) -> str:
    value = item.get(key)
    return value if isinstance(value, str) else ""


def parse_results(items: Any) -> list[DirectoryStation]:
    seen: set[str] = set()
    found: list[DirectoryStation] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        resolved, url = _text(item, "url_resolved"), _text(item, "url")
        address = resolved if is_web_url(resolved) else url
        name = _text(item, "name")
        if not name.strip() or not is_web_url(address) or address in seen:
            continue
        seen.add(address)
        bitrate = item.get("bitrate")
        found.append(DirectoryStation(
            name, _text(item, "country"), address, _text(item, "favicon") or None,
            _text(item, "codec"), bitrate if isinstance(bitrate, int) and not isinstance(bitrate, bool) else 0,
            _text(item, "tags")))
    return found[:_LIMIT]


def subtitle(entry: DirectoryStation) -> str:
    details = []
    if entry.country.strip():
        details.append(entry.country.strip())
    fmt = entry.codec.strip().upper()
    if fmt == "UNKNOWN":
        fmt = ""
    if entry.bitrate > 0:
        fmt = f"{fmt} {entry.bitrate} kbps".strip()
    if fmt:
        details.append(fmt)
    genres = ", ".join([t.strip() for t in entry.tags.split(",") if t.strip()][:2])
    if genres:
        details.append(genres)
    return " · ".join(details)


def to_station(entry: DirectoryStation) -> Station:
    return Station(entry.name.strip(), entry.url, entry.logo if is_web_url(entry.logo) else None)


def search(query: str, fetch: Callable[[str], Any] = fetch_json) -> list[DirectoryStation]:
    for server in SERVERS:
        try:
            return parse_results(fetch(search_url(server, query)))
        except NetworkError:
            continue
    raise DirectoryUnavailable("no station directory server answered")

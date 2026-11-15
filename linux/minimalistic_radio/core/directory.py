"""radio-browser station search, mirroring Storage.Search in src/Services/Storage.cs."""
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.parse import quote

from .models import Station
from .net import NetworkError, fetch_json
from .streams import is_web_url, stream_key

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
    id: str = ""
    working: bool = True


class DirectoryUnavailable(Exception):
    pass


def search_url(server: str, query: str) -> str:
    return (f"https://{server}/json/stations/search?hidebroken=true&limit={_LIMIT}"
            f"&order=clickcount&reverse=true&name={quote(query, safe='')}")


def _text(item: dict, key: str) -> str:
    value = item.get(key)
    return value if isinstance(value, str) else ""


def parse_results(items: Any, limit: int = _LIMIT) -> list[DirectoryStation]:
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
            _text(item, "tags"), _text(item, "stationuuid"), item.get("lastcheckok") != 0))
    return found[:limit]


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




def _first_answer(url_for: Callable[[str], str], fetch: Callable[[str], Any], limit: int) -> list[DirectoryStation]:
    """One request to the first server that answers, then the second."""
    for server in SERVERS:
        try:
            return parse_results(fetch(url_for(server)), limit)
        except NetworkError:
            continue
    raise DirectoryUnavailable("no station directory server answered")


def search(query: str, fetch: Callable[[str], Any] = fetch_json) -> list[DirectoryStation]:
    return _first_answer(lambda server: search_url(server, query), fetch, _LIMIT)


# ---- Station suggestions (docs/superpowers/specs/2026-11-14-station-suggestions-design.md) ----

# Our hand-picked stations (music), by radio-browser stationuuid so addresses and logos stay current.
RECOMMENDED_IDS = (
    "2e6fabb2-9a10-4b2a-91ae-25a7d535e247",   # 102.7 KIIS FM Los Angeles
    "9245e3a5-bf69-4a08-8fac-3903a55043bf",   # Antyradio Hard
    "9617a958-0601-11e8-ae97-52543be04c81",   # Radio Paradise Main Mix
    "a509502d-1ba7-4d51-9791-0be5a7d5ec34",   # KEXP 90.3 Seattle
    "961e6cac-0601-11e8-ae97-52543be04c81",   # NTS Radio 1
    "c454908c-eb81-11e9-a96c-52543be04c81",   # FIP Groove
    "9625d631-0601-11e8-ae97-52543be04c81",   # Radio Swiss Jazz
    "9aa33d22-a6ef-11e9-a787-52543be04c81",   # Radio Swiss Classic
    "960cf833-0601-11e8-ae97-52543be04c81",   # SomaFM Groove Salad
    "960e4940-0601-11e8-ae97-52543be04c81",   # Ibiza Global Radio
)
POPULAR_SHOWN = 15
_POPULAR_ASKED = 40


def recommended_url(server: str) -> str:
    return f"https://{server}/json/stations/byuuid?uuids={','.join(RECOMMENDED_IDS)}"


def popular_url(server: str, country: str | None) -> str:
    url = f"https://{server}/json/stations/search?hidebroken=true&order=clickcount&reverse=true&limit={_POPULAR_ASKED}"
    return url + (f"&countrycode={quote(country, safe='')}" if country else "")


def looks_like_spam(name: str | None) -> bool:
    """Names like "-- # TOP 100 CHARTS ---" or "a,b,c,d,e": starts with a symbol, has "||", "#" or "***", many commas."""
    name = (name or "").strip()
    return (not name or not name[0].isalnum() or "||" in name or "#" in name or "***" in name
            or name.count(",") > 3)


def name_key(name: str | None) -> str:
    """Names compared loosely: "Radio RMF FM" and "RMF FM" are one station."""
    words = [word for word in (name or "").lower().split() if word != "radio"]
    return "".join(ch for ch in "".join(words) if ch.isalnum())


def clean_popular(items: list[DirectoryStation], recommended: list[DirectoryStation],
                  limit: int = POPULAR_SHOWN) -> list[DirectoryStation]:
    """Not already recommended, no duplicates by name or stream, no spam, the first `limit`."""
    names = {name_key(entry.name) for entry in recommended}
    streams = {stream_key(entry.url) for entry in recommended}
    kept: list[DirectoryStation] = []
    for entry in items:
        if looks_like_spam(entry.name):
            continue
        key, stream = name_key(entry.name), stream_key(entry.url)
        # A name that is nothing but "Radio" has an empty key: it is not compared by name.
        if (key and key in names) or stream in streams:
            continue
        if key:
            names.add(key)
        streams.add(stream)
        kept.append(entry)
        if len(kept) == limit:
            break
    return kept


_LOCALE_COUNTRY = re.compile(r"^[A-Za-z]{2,3}_([A-Za-z]{2})(?:[.@]|$)")


def country_from_locale(env: Mapping[str, str]) -> str | None:
    """The territory of the locale (pl_PL.UTF-8 gives PL); None for C, POSIX or nothing."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = env.get(var)
        if value:
            match = _LOCALE_COUNTRY.match(value)
            return match.group(1).upper() if match else None
    return None


# Where each of the radio's languages is spoken, its home country first. English keeps the system country.
_LANGUAGE_COUNTRIES = {
    "pl": ("PL",),
    "de": ("DE", "AT", "CH", "LI", "LU"),
    "uk": ("UA",),
    "cs": ("CZ",),
    "es": ("ES", "MX", "AR", "CO", "CL", "PE", "VE", "EC", "GT", "CU", "BO", "DO", "HN", "PY", "SV", "NI",
           "CR", "PA", "UY", "PR"),
    "fr": ("FR", "BE", "CH", "LU", "MC", "CA"),
    "it": ("IT", "CH", "SM"),
    "pt": ("PT", "BR", "AO", "MZ"),
}


def country_for(language: str, system_country: str | None) -> str | None:
    """The system country if the language is spoken there, else the language's home country (None: unknown)."""
    countries = _LANGUAGE_COUNTRIES.get(language)
    if countries is None:
        return system_country
    return system_country if system_country in countries else countries[0]


def language_of(languages: list[str]) -> str:
    """The language code ("pl") of the first entry of a list like ["pl_PL.UTF-8", "en"]; "en" for none."""
    return re.split(r"[_.@-]", languages[0], maxsplit=1)[0].lower() if languages else "en"


def suggestions(country: str | None, fetch: Callable[[str], Any] = fetch_json
                ) -> tuple[list[DirectoryStation], list[DirectoryStation]]:
    """(recommended, popular). Raises DirectoryUnavailable if both are empty. If only the popular request
    fails, the recommended ones are still returned (and the popular list is empty)."""
    fetched = _first_answer(recommended_url, fetch, len(RECOMMENDED_IDS))
    by_id = {entry.id: entry for entry in fetched}
    recommended = [by_id[i] for i in RECOMMENDED_IDS if i in by_id and by_id[i].working]
    try:
        items = [entry for entry in _first_answer(lambda server: popular_url(server, country), fetch, _POPULAR_ASKED)
                 if entry.working]
        popular = clean_popular(items, recommended)
    except DirectoryUnavailable:
        popular = []
    if not recommended and not popular:
        raise DirectoryUnavailable("no suggestions")
    return recommended, popular
